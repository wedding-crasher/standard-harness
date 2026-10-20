"""Run developer-selected unittest files at main-agent Stop."""

import contextlib
import importlib
import importlib.util
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import unittest


HOME = Path(__file__).resolve().parent
ROOT = HOME.parent.parent.parent
TEST_TIMEOUT = 60
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


def progress(status, message):
    print(
        json.dumps({"type": "progress", "message": f"[test-run {status}] {message}"}),
        flush=True,
    )


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
        relative = Path(name)
        path = ROOT / relative
        if (
            relative.is_absolute()
            or ".." in relative.parts
            or set(relative.parts) & EXCLUDED
            or relative.is_relative_to(Path(".github/hooks/test-run/logs"))
            or path.suffix != ".py"
            or not path.is_file()
            or any(part.is_symlink() for part in (path, *path.parents))
            or not path.resolve().is_relative_to(ROOT)
        ):
            raise ValueError(f"Invalid selected test file: {name!r}")
    return sorted(set(files))


def worker(files):
    suite = unittest.TestSuite()
    with contextlib.redirect_stdout(sys.stderr):
        for index, name in enumerate(files):
            path = ROOT / name
            directory, module = path.parent, path.stem
            packaged = (directory / "__init__.py").is_file()
            while (directory / "__init__.py").is_file():
                module = directory.name + "." + module
                directory = directory.parent
            sys.path[:0] = [str(directory), str(ROOT)]
            if packaged:
                imported = importlib.import_module(module)
            else:
                spec = importlib.util.spec_from_file_location(
                    f"_hook_test_{index}", path
                )
                imported = importlib.util.module_from_spec(spec)
                sys.modules[spec.name] = imported
                spec.loader.exec_module(imported)
            if Path(imported.__file__).resolve() != path.resolve():
                raise ValueError("Test module resolved to a different file.")
            tests = unittest.defaultTestLoader.loadTestsFromModule(imported)
            if not tests.countTestCases():
                raise ValueError(f"No unittest tests found: {name!r}")
            suite.addTests(tests)
        result = unittest.TextTestRunner(verbosity=2).run(suite)
    status = "PASS" if result.wasSuccessful() else "FAIL"
    if result.wasSuccessful() and result.testsRun == len(result.skipped):
        status = "SKIP"
    print(
        json.dumps(
            {
                "status": status,
                "tests": result.testsRun,
                "skipped": len(result.skipped),
            }
        )
    )


def execute(files):
    started = time.monotonic()
    with subprocess.Popen(
        [sys.executable, "-B", str(HOME / "run.py"), "--tests", *files],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        errors="replace",
        start_new_session=os.name != "nt",
    ) as process:
        try:
            stdout, output = process.communicate(timeout=TEST_TIMEOUT)
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
            _, output = process.communicate(timeout=5)
            return {"status": "TIMEOUT", "tests": 0}, (
                output + f"\nSelected tests exceeded {TEST_TIMEOUT}s total.\n"
            )
    if process.returncode:
        return {"status": "ERROR", "tests": 0}, (
            output + f"\nTest process exited {process.returncode}.\n"
        )
    try:
        report = json.loads(stdout)
        if report["status"] not in {"PASS", "FAIL", "SKIP"}:
            raise ValueError
    except (ValueError, KeyError, TypeError):
        return {"status": "ERROR", "tests": 0}, (
            output + "\nTest process returned an invalid result.\n"
        )
    report["seconds"] = round(time.monotonic() - started, 2)
    return report, output


def run(payload):
    files = selection()
    if not files:
        progress("SKIP", "No test files selected.")
        return {}
    logs = HOME / "logs"
    if logs.is_symlink():
        raise ValueError("Logs must not be a symlink.")
    logs.mkdir(mode=0o700, exist_ok=True)
    if (logs / "latest.log").is_symlink():
        raise ValueError("Test log must not be a symlink.")
    progress("RUN", f"{len(files)} selected file(s), {TEST_TIMEOUT}s total limit.")
    report, output = execute(files)
    summary = (
        f"{report['status']}: {len(files)} selected file(s), {report['tests']} tests"
    )
    (logs / "latest.log").write_text(
        f"[test-run] {summary}\n{json.dumps(report)}\nFiles: {json.dumps(files)}\n{output}",
        encoding="utf-8",
    )
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
            "selection or weaken tests.",
        }
    return {}


def main():
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("Expected a hook JSON object.")
        if payload.get("agentId") or payload.get("agent_id"):
            return {}
        cwd = payload.get("cwd", str(ROOT))
        if not isinstance(cwd, str) or not Path(cwd).resolve().is_relative_to(ROOT):
            raise ValueError("Hook cwd must be inside this worktree.")
        return run(payload)
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        progress("ERROR", str(error))
        print(f"[test-run ERROR] {error}", file=sys.stderr)
        return {}


if __name__ == "__main__":
    if sys.argv[1:2] == ["--tests"]:
        worker(sys.argv[2:])
    else:
        print(json.dumps(main()))
