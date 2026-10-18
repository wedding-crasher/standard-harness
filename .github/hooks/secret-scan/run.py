"""Offline Implementer Stop scanning; never serialize scanner secrets or input."""

import contextlib
import io
import json
import os
from pathlib import Path
import stat
import subprocess
import sys


HOME = Path(__file__).resolve().parent
EXCLUDED = {
    "reference",
    "references",
    ".git",
    ".venv",
    "venv",
    "node_modules",
    "build",
    "dist",
    "__pycache__",
    ".ruff_cache",
}
MAX_FILE_BYTES = 2 * 1024 * 1024
MAX_TOTAL_BYTES = 20 * 1024 * 1024
MAX_FILES = 1000
VERSION = "1.5.0"


class CheckError(Exception):
    """Only fixed, content-free diagnostics may be used as messages."""


def git(root, *args):
    try:
        process = subprocess.run(
            ["git", "--no-optional-locks", "--literal-pathspecs", *args],
            cwd=root,
            capture_output=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        raise CheckError("Git could not run or timed out.") from None
    if process.returncode:
        raise CheckError("Git could not read the worktree/index.") from None
    return process.stdout


def in_scope(root, name):
    relative = Path(name)
    if (
        relative.is_absolute()
        or ".." in relative.parts
        or set(relative.parts) & EXCLUDED
    ):
        return False
    if any(
        relative.is_relative_to(Path(directory))
        for directory in (".github/hooks/test-run/logs",)
    ):
        return False
    for parent in reversed(relative.parents):
        if parent == Path("."):
            continue
        directory = root / parent
        if directory.is_symlink():
            # Index blobs remain in scope; do not inspect the linked directory.
            break
        if (directory / "pyvenv.cfg").exists():
            return False
        if (directory / ".git").exists():
            return False
    return True


def snapshots(root):
    groups = []
    for args in (
        (
            "diff",
            "--no-ext-diff",
            "--no-renames",
            "--name-only",
            "--diff-filter=ACMTU",
            "-z",
        ),
        (
            "diff",
            "--cached",
            "--no-ext-diff",
            "--no-renames",
            "--name-only",
            "--diff-filter=ACMTU",
            "-z",
        ),
        ("ls-files", "--others", "--exclude-standard", "-z"),
    ):
        groups.append(
            {
                os.fsdecode(name)
                for name in git(root, *args).split(b"\0")
                if name and in_scope(root, os.fsdecode(name))
            }
        )
    names = set.union(*groups)
    if len(names) > MAX_FILES:
        raise CheckError("Scope exceeds 1000 files; narrow the worktree and retry.")
    entries = {}
    for entry in git(root, "ls-files", "--stage", "-z").split(b"\0"):
        if not entry:
            continue
        metadata, name = entry.split(b"\t", 1)
        name = os.fsdecode(name)
        if name not in names:
            continue
        mode, oid, stage = metadata.split()
        if stage != b"0":
            raise CheckError(
                "Unmerged in-scope files; resolve conflicts before scanning."
            )
        entries[name] = (mode, oid)
    output = {}
    total = 0

    def add(source, name, content):
        nonlocal total
        total += len(content)
        if len(content) > MAX_FILE_BYTES or total > MAX_TOTAL_BYTES:
            raise CheckError(
                "Scan exceeds 2 MiB/file or 20 MiB total; narrow scope and retry."
            )
        output[(source, name)] = content

    for name in sorted(groups[1]):
        mode, oid = entries.get(name, (b"", b""))
        if mode in {b"120000", b"160000"}:
            continue
        if mode not in {b"100644", b"100755"}:
            raise CheckError("Cannot read a staged file's regular index entry.")
        object_id = oid.decode("ascii")
        if int(git(root, "cat-file", "-s", object_id)) > MAX_FILE_BYTES:
            raise CheckError("Staged file exceeds 2 MiB; narrow scope and retry.")
        add("index", name, git(root, "cat-file", "blob", object_id))
    for name in sorted(names):
        path = root / name
        if any((root / parent).is_symlink() for parent in reversed(Path(name).parents)):
            continue
        try:
            mode = path.lstat().st_mode
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(mode) or stat.S_ISDIR(mode):
            continue
        if not stat.S_ISREG(mode):
            raise CheckError("An in-scope path is not a regular file.")
        # Bound reads, and never follow a final-component symlink replaced mid-run.
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        with os.fdopen(descriptor, "rb") as stream:
            add("worktree", name, stream.read(MAX_FILE_BYTES + 1))
    return output


def scan(root):
    from importlib.metadata import version
    from detect_secrets.core.scan import _process_line_based_plugins
    from detect_secrets.settings import default_settings, get_plugins

    if version("detect-secrets") != VERSION:
        raise CheckError(
            "Unexpected detect-secrets version; run `uv sync` in the repository root."
        )
    before = snapshots(root)
    findings = set()
    redactions = set()
    with default_settings() as settings:
        # No verification requests, inline bypasses, or extension-based exclusions.
        settings.disable_filters(
            "detect_secrets.filters.common.is_ignored_due_to_verification_policies",
            "detect_secrets.filters.allowlist.is_line_allowlisted",
            "detect_secrets.filters.heuristic.is_non_text_file",
            "detect_secrets.filters.heuristic.is_lock_file",
            "detect_secrets.filters.heuristic.is_swagger_file",
        )
        if not get_plugins():
            raise CheckError("No scanner detectors loaded.")
        for (source, name), content in before.items():
            if b"\0" in content:
                raise CheckError(
                    "Binary/NUL-containing content is unsupported; scan incomplete."
                )
            try:
                text = content.decode("utf-8-sig")
            except UnicodeDecodeError:
                raise CheckError(
                    "Non-UTF-8 content is unsupported; scan incomplete."
                ) from None
            # The pinned engine accepts in-memory lines, avoiding raw snapshots on
            # disk and scan_file's silent read/encoding failures.
            for finding in _process_line_based_plugins(
                list(enumerate(text.splitlines(), 1)), filename=name
            ):
                findings.add((source, name, finding.line_number, finding.type))
                if finding.secret_value:
                    redactions.add(finding.secret_value)
    if before != snapshots(root):
        raise CheckError("Files/index changed during scanning; rerun the hook.")

    def safe_path(name):
        for value in sorted(redactions, key=len, reverse=True):
            name = name.replace(value, "[REDACTED]")
        return name

    return {
        "status": "FAIL" if findings else ("PASS" if before else "SKIP"),
        "snapshots": len(before),
        "findings": [
            {"source": source, "path": safe_path(name), "line": line, "type": kind}
            for source, name, line, kind in sorted(findings)
        ],
        "detail": "Potential secrets detected."
        if findings
        else ("Offline scan completed." if before else "No in-scope changed files."),
    }


def worker():
    # A child process bounds scanner execution. Discard all library output, including
    # exception text: some detectors/tool failures may include source or values.
    try:
        with (
            contextlib.redirect_stdout(io.StringIO()),
            contextlib.redirect_stderr(io.StringIO()),
        ):
            report = scan(Path.cwd())
    except CheckError as error:
        report = {"status": "ERROR", "detail": str(error)}
    except Exception:
        report = {
            "status": "ERROR",
            "detail": "Scanner failed; restore its environment and retry.",
        }
    print(json.dumps(report))


def check(root):
    python = (
        root / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    )
    if not python.is_file():
        raise CheckError(
            "Scanner environment missing. Run `uv sync` in the repository root; "
            "the hook never installs dependencies."
        )
    try:
        process = subprocess.run(
            [str(python), "-I", str(HOME / "run.py"), "--scan"],
            cwd=root,
            capture_output=True,
            timeout=60,
            check=False,
        )
    except subprocess.TimeoutExpired:
        raise CheckError(
            "Scanner timed out after 60 seconds; scan incomplete."
        ) from None
    if process.returncode:
        raise CheckError("Scanner process failed; scan incomplete.")
    try:
        report = json.loads(process.stdout)
        status = report["status"]
        details = {
            "PASS": "Offline scan completed.",
            "SKIP": "No in-scope changed files.",
            "FAIL": "Potential secrets detected.",
        }
        if status == "ERROR":
            if set(report) != {"status", "detail"} or not isinstance(
                report["detail"], str
            ):
                raise ValueError
            return report
        if (
            status not in details
            or set(report) != {"status", "detail", "snapshots", "findings"}
            or report["detail"] != details[status]
            or type(report["snapshots"]) is not int
            or report["snapshots"] < (0 if status == "SKIP" else 1)
            or (status == "SKIP" and report["snapshots"] != 0)
            or not isinstance(report["findings"], list)
            or bool(report["findings"]) != (status == "FAIL")
        ):
            raise ValueError
        for finding in report["findings"]:
            if (
                set(finding) != {"source", "path", "line", "type"}
                or finding["source"] not in {"index", "worktree"}
                or type(finding["line"]) is not int
                or finding["line"] < 1
                or not isinstance(finding["path"], str)
                or not isinstance(finding["type"], str)
            ):
                raise ValueError
        return report
    except (ValueError, KeyError, TypeError):
        raise CheckError("Scanner returned invalid output; scan incomplete.") from None


def run(payload):
    cwd = Path(payload.get("cwd", str(Path.cwd()))).resolve()
    root = Path(os.fsdecode(git(cwd, "rev-parse", "--show-toplevel")).strip()).resolve()
    if HOME != root / ".github/hooks/secret-scan":
        raise CheckError("Run this worktree's own .github/hooks/secret-scan/run.py.")
    progress("[secret-scan] Checking changed files offline...")
    try:
        report = check(root)
    except (CheckError, OSError) as error:
        report = {
            "status": "ERROR",
            "detail": str(error)
            if isinstance(error, CheckError)
            else "Scanner could not start.",
        }
    status = report["status"]
    text = report["detail"]
    for finding in report.get("findings", []):
        text += (
            f"\n{finding['source']}:{finding['path']}:{finding['line']}:"
            f"{finding['type']}"
        )
    progress(f"[secret-scan {status}] {text}")
    if status not in {"FAIL", "ERROR"}:
        return {}
    warning = (
        f"[secret-scan {status}] The check did not pass; see the secret-scan "
        "terminal output for locations. Never echo secret values."
    )
    print(warning, file=sys.stderr)
    return prepend(warning, payload)


def prepend(warning, payload):
    response = payload.get("response", payload.get("last_assistant_message"))
    if isinstance(response, str):
        return {"modifiedResponse": warning + "\n\n" + response}
    return {}


def progress(message):
    print(json.dumps({"type": "progress", "message": message}), flush=True)


def main():
    payload = {}
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict) or not isinstance(payload.get("cwd", ""), str):
            raise CheckError("Expected a JSON object with an optional cwd string.")
        output = run(payload)
    except Exception:
        warning = (
            "[secret-scan ERROR] Hook infrastructure failed; scan NOT verified. "
            "Check input, Git and permissions."
        )
        print(warning, file=sys.stderr)
        progress(warning)
        output = prepend(warning, payload) if isinstance(payload, dict) else {}
    print(json.dumps(output))


if __name__ == "__main__":
    if sys.argv[1:] == ["--scan"]:
        worker()
    else:
        main()
