"""Run scoped Stop formatting/linting without invoking another agent."""

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys


HOME = Path(__file__).resolve().parent
EXCLUDED = {"reference", ".git", ".venv", "venv", "node_modules", "build", "dist"}


class CheckError(Exception):
    pass


def command(argv, cwd):
    try:
        return subprocess.run(
            argv, cwd=cwd, capture_output=True, timeout=15, check=False
        )
    except subprocess.TimeoutExpired as error:
        raise CheckError(f"Command timed out: {argv[0]}") from error


def git(root, *args):
    result = command(["git", *args], root)
    if result.returncode:
        raise CheckError(f"git {' '.join(args)} failed (exit {result.returncode})")
    return result.stdout


def changed_files(root):
    paths = set()
    for args in (
        ("diff", "--name-only", "--diff-filter=ACMRT", "-z"),
        ("diff", "--cached", "--name-only", "--diff-filter=ACMRT", "-z"),
        ("ls-files", "--others", "--exclude-standard", "-z"),
    ):
        paths.update(os.fsdecode(p) for p in git(root, *args).split(b"\0") if p)
    selected = []
    for name in sorted(paths):
        relative = Path(name)
        if (
            relative.is_absolute()
            or ".." in relative.parts
            or set(relative.parts) & EXCLUDED
            or relative.suffix not in {".py", ".pyi"}
        ):
            continue
        path = root / relative
        if not path.is_file():
            continue
        if any(
            parent.is_symlink() for parent in [path, *path.parents] if parent != root
        ):
            continue
        if not path.resolve().is_relative_to(root):
            continue
        selected.append(name)
    return selected


def fingerprint(root, files):
    digest = hashlib.sha256()
    for name in files:
        digest.update(os.fsencode(name) + b"\0")
        digest.update(hashlib.sha256((root / name).read_bytes()).digest())
    return digest.hexdigest()


def result(status, files, detail, changed=False):
    return {"status": status, "files": files, "detail": detail, "changed": changed}


def check(root, files):
    if not files:
        return result("SKIP", files, "No changed Python files.")
    before = fingerprint(root, files)
    python = (
        root / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    )
    if not python.is_file():
        raise CheckError(
            "Ruff environment missing. Run `uv sync` in the repository root; "
            "the hook never installs dependencies."
        )
    base = [str(python), "-m", "ruff"]
    options = ["--config", str(HOME / "ruff.toml"), "--no-cache", "--force-exclude"]
    formatter = command([*base, "format", *options, "--", *files], root)
    format_text = formatter.stdout.decode("utf-8", errors="replace").strip()
    after = fingerprint(root, files)
    if formatter.returncode:
        # Ruff parse errors can echo source text; do not print raw source.
        return result(
            "ERROR",
            files,
            f"ruff format failed (exit {formatter.returncode}). "
            "Run Ruff on the listed files to inspect syntax/configuration errors.",
            before != after,
        )
    lint = command(
        [*base, "check", *options, "--output-format", "json", "--", *files], root
    )
    if lint.returncode not in (0, 1):
        return result(
            "ERROR",
            files,
            f"ruff check failed (exit {lint.returncode}). Inspect Ruff configuration.",
            before != after,
        )
    try:
        diagnostics = json.loads(lint.stdout)
    except json.JSONDecodeError as error:
        raise CheckError("Ruff returned invalid diagnostic JSON.") from error
    lines = []
    for diagnostic in diagnostics:
        location = diagnostic["location"]
        name = os.path.relpath(diagnostic["filename"], root)
        lines.append(
            f"{name}:{location['row']}:{location['column']} "
            f"{diagnostic['code'] or 'syntax'} {diagnostic['message']}"
        )
    if fingerprint(root, files) != after:
        raise CheckError("Python files changed during checks; rerun the hook.")
    status = "PASS" if lint.returncode == 0 and not lines else "FAIL"
    return result(
        status,
        files,
        "\n".join([format_text, *lines, f"ruff check: exit {lint.returncode}"]),
        before != after,
    )


def decision(report, payload):
    status = report["status"]
    failed = status in {"FAIL", "ERROR"}
    if failed:
        warning = f"[format/lint {status}] The check did not pass; see the format/lint terminal output for locations."
        print(warning, file=sys.stderr)
    elif report["changed"]:
        warning = "[format/lint] Formatting changed files; rerun affected tests and refresh your report."
    else:
        return {}
    response = payload.get("response", payload.get("last_assistant_message"))
    if isinstance(response, str):
        return {"modifiedResponse": warning + " \n\n" + response}
    return {}


def progress(message):
    print(json.dumps({"type": "progress", "message": message}), flush=True)


def run(payload):
    cwd = Path(payload.get("cwd", str(Path.cwd()))).resolve()
    root = Path(os.fsdecode(git(cwd, "rev-parse", "--show-toplevel")).strip()).resolve()
    if HOME != root / ".github" / "hooks" / "format-lint":
        raise CheckError("Run this worktree's own .github/hooks/format-lint/run.py.")
    files = changed_files(root)
    progress(f"[format/lint] Checking {len(files)} Python file(s)...")
    try:
        report = check(root, files)
    except (CheckError, OSError) as error:
        report = result("ERROR", files, str(error))
    status = report["status"]
    if status == "SKIP":
        text = "No changed Python files."
    elif status in {"FAIL", "ERROR"}:
        text = f"{len(files)} file(s).\nFiles: {json.dumps(files)}\n{report['detail']}"
    else:
        text = f"{len(files)} file(s)." + (
            " Formatting changed files; rerun affected tests."
            if report["changed"]
            else ""
        )
    progress(f"[format/lint {status}] {text}")
    return decision(report, payload)


def main():
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise CheckError("Expected a JSON object on stdin.")
        if "cwd" in payload and not isinstance(payload["cwd"], str):
            raise CheckError("Expected cwd to be a path string.")
        output = run(payload)
    except (CheckError, OSError, ValueError) as error:
        print(f"[format/lint ERROR] {error}", file=sys.stderr)
        progress(f"[format/lint ERROR] {error}")
        output = {}
    print(json.dumps(output))


if __name__ == "__main__":
    main()
