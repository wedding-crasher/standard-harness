"""Run developer-selected unittest files on changed inputs at main-agent Stop."""

import contextlib
import hashlib
import importlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import unittest
from uuid import uuid4


HOME = Path(__file__).resolve().parent
ROOT = HOME.parent.parent.parent
EXCLUDED = {
    ".git",
    "reference",
    ".venv",
    "venv",
    "node_modules",
    "build",
    "dist",
    "__pycache__",
    ".ruff_cache",
    ".pytest_cache",
    ".mypy_cache",
}
TEST_TIMEOUT = 60


def atomic_write(path, text):
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        temporary.write_text(text, encoding="utf-8")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def progress(status, message):
    print(
        json.dumps({"type": "progress", "message": f"[test-run {status}] {message}"}),
        flush=True,
    )


def in_scope(name):
    path = Path(name)
    return not (
        path.is_absolute()
        or ".." in path.parts
        or set(path.parts) & EXCLUDED
        or (
            len(path.parts) > 2
            and path.parts[0] == ".github"
            and path.parts[2] in {"logs", ".scratch"}
        )
        or (
            len(path.parts) > 3
            and path.parts[:2] == (".github", "hooks")
            and path.parts[3] in {"logs", ".scratch"}
        )
    )


def git(*args):
    process = subprocess.run(
        ["git", "--no-optional-locks", *args],
        cwd=ROOT,
        capture_output=True,
        timeout=5,
        check=False,
    )
    if process.returncode:
        raise ValueError("Git could not read the worktree/index.")
    return process.stdout


def selection():
    path = HOME / "selection.local.json"
    if not path.exists():
        return []
    if path.is_symlink():
        raise ValueError("Selection must not be a symlink.")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or set(data) != {"files"}:
        raise ValueError('Selection must contain only a "files" array.')
    files = data["files"]
    if not isinstance(files, list) or any(not isinstance(name, str) for name in files):
        raise ValueError("Each selected test must be a relative file path.")
    for name in files:
        path = ROOT / name
        if (
            not in_scope(name)
            or path.suffix != ".py"
            or not path.is_file()
            or any(part.is_symlink() for part in (path, *path.parents))
            or not path.resolve().is_relative_to(ROOT)
        ):
            raise ValueError(f"Invalid selected test file: {name!r}")
    return sorted(set(files))


def snapshot(files):
    """Index blob IDs cover clean sources; read only dirty/untracked contents."""
    digest = hashlib.sha256()
    digest.update(json.dumps([files, sys.executable, sys.version]).encode())
    digest.update(Path(__file__).read_bytes())
    for entry in git("ls-files", "--stage", "-z").split(b"\0"):
        if entry and in_scope(os.fsdecode(entry.split(b"\t", 1)[1])):
            digest.update(entry + b"\0")
    changed = set()
    for args in (
        ("diff", "--no-ext-diff", "--no-renames", "--name-only", "-z"),
        ("diff", "--cached", "--no-ext-diff", "--no-renames", "--name-only", "-z"),
        ("ls-files", "--others", "--exclude-standard", "-z"),
    ):
        changed.update(
            os.fsdecode(name)
            for name in git(*args).split(b"\0")
            if name and in_scope(os.fsdecode(name))
        )
    for name in sorted(changed | set(files)):
        path = ROOT / name
        digest.update(os.fsencode(name) + b"\0")
        if any(part.is_symlink() for part in (path, *path.parents)):
            raise ValueError(f"Changed input is a symlink: {name!r}")
        if path.is_file():
            digest.update(b"file\0" + hashlib.sha256(path.read_bytes()).digest())
        elif not path.exists():
            digest.update(b"deleted\0")
        else:
            raise ValueError(f"Changed input is not a regular file: {name!r}")
    return digest.hexdigest(), bool(changed)


def run_file(name):
    # A fresh process per file avoids collisions between equally named test modules.
    path = ROOT / name
    directory, module = path.parent, path.stem
    while (directory / "__init__.py").is_file():
        module = directory.name + "." + module
        directory = directory.parent
    sys.path[:0] = [str(directory), str(ROOT)]
    with contextlib.redirect_stdout(sys.stderr):
        imported = importlib.import_module(module)
        if Path(imported.__file__).resolve() != path.resolve():
            raise ValueError("Test module resolved to a different file.")
        suite = unittest.defaultTestLoader.loadTestsFromModule(imported)
        result = unittest.TextTestRunner(verbosity=2).run(suite)
    status = "PASS" if result.wasSuccessful() else "FAIL"
    if result.testsRun == 0:
        status = "ERROR"
    elif len(result.skipped) == result.testsRun:
        status = "SKIP"
    print(
        json.dumps(
            {"status": status, "tests": result.testsRun, "skipped": len(result.skipped)}
        )
    )


def execute(files):
    started = time.monotonic()
    tests, skipped, statuses, output = 0, 0, [], []
    for name in files:
        remaining = TEST_TIMEOUT - (time.monotonic() - started)
        output.append(f"\n--- {name} ---\n")
        try:
            if remaining <= 0:
                raise subprocess.TimeoutExpired("selected tests", TEST_TIMEOUT)
            with subprocess.Popen(
                [sys.executable, "-B", str(HOME / "run.py"), "--file", name],
                cwd=ROOT,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                errors="replace",
                start_new_session=os.name != "nt",
            ) as process:
                try:
                    stdout, stderr = process.communicate(timeout=remaining)
                except subprocess.TimeoutExpired:
                    if os.name == "nt":
                        subprocess.run(
                            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                            capture_output=True,
                            timeout=5,
                            check=True,
                        )
                    else:
                        os.killpg(process.pid, signal.SIGKILL)
                    process.communicate(timeout=5)
                    raise
        except subprocess.TimeoutExpired:
            statuses.append("TIMEOUT")
            output.append(f"Selected tests exceeded {TEST_TIMEOUT}s total.\n")
            break
        output.append(stderr)
        if process.returncode:
            statuses.append("ERROR")
            output.append(f"Test process exited {process.returncode}.\n")
            break
        try:
            report = json.loads(stdout)
            status, count, skip = report["status"], report["tests"], report["skipped"]
            if (
                status not in {"PASS", "FAIL", "ERROR", "SKIP"}
                or type(count) is not int
                or type(skip) is not int
                or count < 0
                or not 0 <= skip <= count
            ):
                raise ValueError("Invalid result fields")
        except (ValueError, KeyError, TypeError):
            statuses.append("ERROR")
            output.append("Test process returned an invalid result.\n")
            break
        statuses.append(status)
        tests += count
        skipped += skip
    status = next(
        (item for item in ("TIMEOUT", "ERROR", "FAIL") if item in statuses),
        "SKIP" if tests == skipped else "PASS",
    )
    return {
        "status": status,
        "tests": tests,
        "skipped": skipped,
        "seconds": round(time.monotonic() - started, 2),
    }, "".join(output)


def run(payload, logs, force=False):
    files = selection()
    if not files:
        progress("SKIP", "No test files selected.")
        return {}
    key, dirty = snapshot(files)
    state_path = logs / "state.json"
    previous = json.loads(state_path.read_text()) if state_path.exists() else None
    if previous is not None and (
        not isinstance(previous, dict)
        or not isinstance(previous.get("fingerprint"), str)
        or previous.get("status") not in {"PASS", "FAIL", "ERROR", "TIMEOUT", "SKIP"}
    ):
        raise ValueError("Invalid test state; inspect logs/state.json.")
    if not force and previous and previous["fingerprint"] == key:
        progress(
            "CACHED",
            f"Unchanged inputs; previous result: {previous['status']}. "
            "Log: .github/hooks/test-run/logs/latest.log",
        )
        return {}
    if not force and previous is None and not dirty:
        report, output = {"status": "SKIP", "tests": 0}, "No initial changes.\n"
    else:
        progress("RUN", f"{len(files)} selected file(s), {TEST_TIMEOUT}s total limit.")
        report, output = execute(files)
        try:
            unchanged = snapshot(selection())[0] == key
        except (OSError, ValueError, subprocess.SubprocessError) as error:
            unchanged = False
            output += f"\nCould not recheck inputs: {error}\n"
        if not unchanged:
            report["status"] = "ERROR"
            output += "\nInputs changed during tests; result is not current.\n"
    summary = (
        f"{report['status']}: {len(files)} selected file(s), {report['tests']} tests"
    )
    text = f"[test-run] {summary}\n{json.dumps(report)}\nFiles: {json.dumps(files)}\n{output}"
    atomic_write(logs / "latest.log", text)
    atomic_write(state_path, json.dumps({**report, "fingerprint": key}))
    progress(
        report["status"], summary + ". Log: .github/hooks/test-run/logs/latest.log"
    )
    if report["status"] in {"FAIL", "ERROR", "TIMEOUT"} and not payload.get(
        "stop_hook_active"
    ):
        return {
            "decision": "block",
            "reason": "Selected tests did not pass. Read .github/hooks/test-run/logs/latest.log, "
            "fix only assigned code or report the blocker. Do not edit the developer's "
            "selection or weaken tests. Unchanged inputs will not rerun automatically.",
        }
    return {}


def main():
    logs = HOME / "logs"
    lock = logs / ".running"
    locked = False
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("Expected a hook JSON object.")
        if payload.get("agentId") or payload.get("agent_id"):
            return {}
        cwd = payload.get("cwd", str(ROOT))
        if not isinstance(cwd, str) or not Path(cwd).resolve().is_relative_to(ROOT):
            raise ValueError("Hook cwd must be inside this worktree.")
        if (
            Path(os.fsdecode(git("rev-parse", "--show-toplevel")).strip()).resolve()
            != ROOT
        ):
            raise ValueError("Run this worktree's own test hook.")
        if logs.is_symlink():
            raise ValueError("Logs must not be a symlink.")
        logs.mkdir(mode=0o700, exist_ok=True)
        try:
            descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            raise ValueError(
                "Test run already active; inspect logs/.running if stale."
            ) from None
        locked = True
        os.close(descriptor)
        return run(payload, logs, force=sys.argv[1:] == ["--force"])
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        progress("ERROR", str(error))
        print(f"[test-run ERROR] {error}", file=sys.stderr)
        return {}
    finally:
        if locked:
            lock.unlink(missing_ok=True)


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--file":
        run_file(sys.argv[2])
    else:
        print(json.dumps(main()))
