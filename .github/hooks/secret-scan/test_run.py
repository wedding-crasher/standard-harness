import json
import contextlib
import io
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import importlib.util
from unittest.mock import patch


SOURCE = Path(__file__).resolve().parent
# Deliberately synthetic, assembled at runtime: no real credentials or allowlist.
DUMMY = "ghp_" + "".join(("Ab3dE6", "gH9jK2", "mN5pQ8", "sT1vW4", "yZ7cF0", "iL3oR6"))
PRIVATE_MARKER = "-" * 5 + "BEGIN " + "PRIVATE KEY" + "-" * 5
DUMMY_API = "AKIA" + "".join(("7J3Q", "8D2M", "4V9R", "6N1T"))


class SecretHookTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="secret-scan-test-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.home = self.root / ".github/hooks/secret-scan"
        self.home.mkdir(parents=True)
        shutil.copy2(SOURCE / "run.py", self.home / "run.py")
        self.git("init", "--quiet")
        self.git("add", ".")
        self.commit()
        self.link_environment()

    def link_environment(self):
        environment = SOURCE.parents[2] / ".venv"
        self.assertTrue(environment.is_dir(), "Run `uv sync` in the repository root")
        (self.root / ".venv").symlink_to(environment, target_is_directory=True)

    def git(self, *args):
        return subprocess.run(
            ["git", *args], cwd=self.root, capture_output=True, check=True
        ).stdout

    def commit(self):
        self.git(
            "-c",
            "user.name=Hook Test",
            "-c",
            "user.email=hook@example.invalid",
            "commit",
            "--quiet",
            "-m",
            "Synthetic fixture",
        )

    def write(self, name, text):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def invoke(self, **overrides):
        process = subprocess.run(
            [sys.executable, str(self.home / "run.py")],
            input=json.dumps(
                {
                    "cwd": str(self.root),
                    "sessionId": "synthetic-test",
                    "agentId": "implementer",
                    "response": "ORIGINAL RESPONSE",
                    **overrides,
                }
            ),
            cwd=self.root,
            text=True,
            capture_output=True,
            timeout=80,
        )
        self.assertEqual(process.returncode, 0, process.stderr)
        output = [json.loads(line) for line in process.stdout.splitlines()]
        decisions = [item for item in output if item.get("type") != "progress"]
        self.assertEqual(len(decisions), 1)
        self.assertNotIn("block", decisions[0].get("decision", ""))
        self.terminal = process.stdout + process.stderr
        for text in (process.stdout, process.stderr):
            self.assertNotIn(DUMMY, text)
            self.assertNotIn(DUMMY_API, text)
            self.assertNotIn(PRIVATE_MARKER, text)
        self.assertEqual(
            [p.name for p in self.home.iterdir() if p.name != "__pycache__"],
            ["run.py"],
        )
        return decisions[0], process

    def log(self):
        return self.terminal

    def test_untracked_non_python_secret_fails_without_value_disclosure(self):
        self.write("config/a file.env", f"ACCESS_TOKEN={DUMMY}\n")
        output, process = self.invoke()
        self.assertIn("did not pass", output["modifiedResponse"])
        self.assertTrue(output["modifiedResponse"].endswith("ORIGINAL RESPONSE"))
        self.assertIn("[secret-scan FAIL]", process.stdout)
        self.assertIn("did not pass", process.stderr)
        self.assertIn("worktree:config/a file.env:1:GitHub Token", self.log())

    def test_detected_value_is_redacted_even_if_it_occurs_in_a_filename(self):
        self.write(f"config/{DUMMY}.env", DUMMY + "\n")
        self.invoke()
        self.assertIn("[REDACTED]", self.log())

    def test_staged_secret_is_checked_even_when_worktree_is_clean_or_deleted(self):
        path = self.write("config.env", f"ACCESS_TOKEN={DUMMY}\n")
        self.git("add", "config.env")
        original = self.git("show", ":config.env")
        path.write_text("safe configuration\n")
        self.invoke()
        self.assertIn("index:config.env:1:GitHub Token", self.log())
        self.assertEqual(self.git("show", ":config.env"), original)
        self.assertEqual(path.read_text(), "safe configuration\n")
        path.unlink()
        self.invoke()
        self.assertIn("index:config.env:1:GitHub Token", self.log())

    def test_unstaged_secret_and_private_key_are_detected_without_changing_files(self):
        path = self.write("settings.yaml", "enabled: true\n")
        self.git("add", "settings.yaml")
        self.commit()
        contents = f"token: {DUMMY}\n{PRIVATE_MARKER}\naccess_key: {DUMMY_API}\n"
        path.write_text(contents)
        self.invoke()
        self.assertIn("Private Key", self.log())
        self.assertIn("AWS Access Key", self.log())
        self.assertIn("settings.yaml:2:Private Key", self.log())
        self.assertEqual(path.read_text(), contents)
        self.assertEqual(self.git("show", ":settings.yaml"), b"enabled: true\n")

    def test_no_changed_files_skip_and_safe_text_passes(self):
        output, process = self.invoke()
        self.assertEqual(output, {})
        self.assertIn("[secret-scan SKIP] No in-scope changed files.", process.stdout)
        self.write("safe.txt", "hello world\n")
        self.assertEqual(self.invoke()[0], {})
        self.assertIn("[secret-scan PASS]", self.log())

    def test_result_is_stateless_and_never_blocks(self):
        self.write("app.env", DUMMY + "\n")
        first = self.invoke()
        second = self.invoke()
        self.assertEqual(first[0], second[0])
        self.assertEqual(first[1].stdout, second[1].stdout)
        self.assertEqual(first[1].stderr, second[1].stderr)
        self.assertNotIn(DUMMY, first[0]["modifiedResponse"])

    def test_failure_without_response_returns_empty_decision(self):
        self.write("app.env", DUMMY + "\n")
        output, process = self.invoke(response=None)
        self.assertEqual(output, {})
        self.assertIn("[secret-scan FAIL]", process.stdout)

    def test_exclusions_and_ignored_files_do_not_expand_scope(self):
        self.write(".gitignore", "ignored.env\n")
        self.git("add", ".gitignore")
        self.commit()
        for name in (
            "reference/clone/example.env",
            "node_modules/example.env",
            "dist/example.env",
            "build/example.env",
            "venv/example.env",
            ".github/hooks/test-run/logs/old.log",
            "ignored.env",
            "custom-env/pyvenv.cfg",
            "custom-env/example.env",
            "nested/.git/HEAD",
            "nested/example.env",
        ):
            self.write(name, DUMMY + "\n")
        self.assertEqual(self.invoke()[0], {})
        self.assertIn("SKIP", self.log())

    def test_tests_are_not_excluded_and_inline_allowlist_cannot_hide_secrets(self):
        self.write("tests/config.env", DUMMY + " # pragma: allowlist secret\n")
        self.invoke()
        self.assertIn("tests/config.env", self.log())

    def test_forced_staged_ignored_file_is_checked(self):
        self.write(".gitignore", "ignored.env\n")
        self.write("ignored.env", DUMMY + "\n")
        self.git("add", "-f", "ignored.env")
        self.invoke()
        self.assertIn("index:ignored.env", self.log())

    def test_rename_is_checked_and_deleted_files_are_not_read(self):
        self.write("old.txt", "hello world\n")
        removed = self.write("deleted.txt", "hello world\n")
        self.git("add", "old.txt", "deleted.txt")
        self.commit()
        self.git("mv", "old.txt", "renamed.txt")
        self.write("renamed.txt", DUMMY + "\n")
        removed.unlink()
        self.invoke()
        self.assertIn("renamed.txt", self.log())
        self.assertNotIn("deleted.txt", self.log())

    def test_symlinks_are_not_followed_but_regular_staged_blob_is_scanned(self):
        target = self.write("reference/value.env", DUMMY + "\n")
        (self.root / "linked.env").symlink_to(target)
        self.assertEqual(self.invoke()[0], {})
        path = self.write("staged.env", DUMMY + "\n")
        self.git("add", "staged.env")
        path.unlink()
        path.symlink_to(target)
        self.invoke()
        self.assertIn("index:staged.env", self.log())
        self.assertNotIn("worktree:", self.log())

    def test_parent_symlink_does_not_hide_regular_staged_blob(self):
        target = self.write("reference/config/app.env", "hello world\n")
        path = self.write("config/app.env", DUMMY + "\n")
        self.git("add", "config/app.env")
        path.unlink()
        path.parent.rmdir()
        path.parent.symlink_to(target.parent, target_is_directory=True)
        self.invoke()
        self.assertIn("index:config/app.env", self.log())
        self.assertNotIn("worktree:", self.log())

    def test_missing_environment_is_error_mentioning_uv_sync(self):
        self.write("safe.txt", "hello world\n")
        (self.root / ".venv").unlink()
        output, process = self.invoke()
        self.assertIn("[secret-scan ERROR]", process.stdout)
        self.assertIn("uv sync", self.log())
        self.assertIn("ERROR", output["modifiedResponse"])

    def test_invalid_encoding_binary_and_oversize_are_errors_not_passes(self):
        path = self.root / "data.bin"
        for content in (b"\xff", b"hello\0world", b"x" * (2 * 1024 * 1024 + 1)):
            path.write_bytes(content)
            self.invoke()
            self.assertIn("[secret-scan ERROR]", self.log())
            self.assertNotIn("[secret-scan PASS]", self.log())

    def test_unusual_filename_is_not_interpreted_as_pathspec(self):
        name = "config/:(glob)*\n\t.env"
        self.write(name, DUMMY + "\n")
        self.git("--literal-pathspecs", "add", name)
        self.invoke()
        self.assertIn("[secret-scan FAIL]", self.log())
        self.assertIn(":(glob)*", self.log())

    def test_infrastructure_errors_are_visible_without_raw_input_or_traceback(self):
        process = subprocess.run(
            [sys.executable, str(self.home / "run.py")],
            input="{",
            text=True,
            capture_output=True,
            check=True,
        )
        self.assertIn("[secret-scan ERROR]", process.stdout)
        self.assertIn("ERROR", process.stderr)
        self.assertNotIn("Traceback", process.stderr)
        self.assertEqual(json.loads(process.stdout.splitlines()[-1]), {})
        output, process = self.invoke(cwd=str(self.root / "missing"))
        self.assertIn("ERROR", output["modifiedResponse"])
        self.assertNotIn("Traceback", process.stderr)
        self.assertNotIn("ORIGINAL RESPONSE", process.stderr)

    def test_unmerged_files_are_errors(self):
        self.write("conflict.txt", "hello world\n")
        self.git("add", "conflict.txt")
        oid = self.git("rev-parse", ":conflict.txt").strip()
        subprocess.run(
            ["git", "update-index", "--index-info"],
            input=b"0 "
            + b"0" * 40
            + b"\tconflict.txt\n"
            + b"100644 "
            + oid
            + b" 1\tconflict.txt\n"
            + b"100644 "
            + oid
            + b" 2\tconflict.txt\n",
            cwd=self.root,
            capture_output=True,
            check=True,
        )
        self.invoke()
        self.assertIn("Unmerged", self.log())

    def test_real_scanner_does_not_connect_to_network(self):
        self.write("app.env", DUMMY + "\n")
        python = (
            self.root
            / ".venv"
            / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        )
        process = subprocess.run(
            [
                str(python),
                "-I",
                "-c",
                """
import runpy
from pathlib import Path
from unittest.mock import patch
hook = runpy.run_path(".github/hooks/secret-scan/run.py")
with patch("socket.socket.connect", side_effect=AssertionError("network forbidden")) as connect:
    report = hook["scan"](Path.cwd())
    assert report["status"] == "FAIL"
    connect.assert_not_called()
""",
            ],
            cwd=self.root,
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(process.returncode, 0, process.stderr)

    def test_mid_scan_changes_cannot_record_a_pass(self):
        self.write("safe.txt", "hello world\n")
        python = (
            self.root
            / ".venv"
            / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        )
        process = subprocess.run(
            [
                str(python),
                "-I",
                "-c",
                """
import runpy
from pathlib import Path
from unittest.mock import patch
hook = runpy.run_path(".github/hooks/secret-scan/run.py")
original = hook["scan"].__globals__["snapshots"]
calls = 0
def changing(root):
    global calls
    calls += 1
    if calls == 2:
        (root / "safe.txt").write_text("changed contents\\n")
    return original(root)
with patch.dict(hook["scan"].__globals__, snapshots=changing):
    try:
        hook["scan"](Path.cwd())
    except hook["CheckError"] as error:
        assert "changed during scanning" in str(error)
    else:
        raise AssertionError("Unstable scan must not pass")
""",
            ],
            cwd=self.root,
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(process.returncode, 0, process.stderr)


class ScannerFailureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        specification = importlib.util.spec_from_file_location(
            "secret_hook", SOURCE / "run.py"
        )
        cls.hook = importlib.util.module_from_spec(specification)
        specification.loader.exec_module(cls.hook)

    def test_tool_exit_invalid_json_and_timeout_do_not_echo_tool_output(self):
        outputs = [
            subprocess.CompletedProcess([], 1, stdout=DUMMY, stderr=DUMMY),
            subprocess.CompletedProcess([], 0, stdout=DUMMY, stderr=DUMMY),
            subprocess.CompletedProcess([], 0, stdout='{"status":"PASS"}', stderr=""),
            subprocess.CompletedProcess(
                [],
                0,
                stdout=json.dumps(
                    {
                        "status": "PASS",
                        "snapshots": 1,
                        "findings": [],
                        "detail": DUMMY,
                    }
                ),
                stderr="",
            ),
            subprocess.CompletedProcess(
                [], 0, stdout='{"status":"UNKNOWN"}', stderr=DUMMY
            ),
        ]
        for output in outputs:
            with self.subTest(output=output.returncode):
                with patch.object(self.hook.subprocess, "run", return_value=output):
                    with self.assertRaises(self.hook.CheckError) as raised:
                        self.hook.check(SOURCE)
                self.assertNotIn(DUMMY, str(raised.exception))
        with patch.object(
            self.hook.subprocess,
            "run",
            side_effect=subprocess.TimeoutExpired(
                "scanner", 60, output=DUMMY, stderr=DUMMY
            ),
        ):
            with self.assertRaisesRegex(self.hook.CheckError, "timed out"):
                self.hook.check(SOURCE)

    def test_scanner_exceptions_and_library_output_are_sanitized(self):
        def broken_scanner(root):
            print(DUMMY)
            print(DUMMY, file=sys.stderr)
            raise RuntimeError(DUMMY)

        stdout, stderr = io.StringIO(), io.StringIO()
        with (
            patch.object(self.hook, "scan", side_effect=broken_scanner),
            contextlib.redirect_stdout(stdout),
            contextlib.redirect_stderr(stderr),
        ):
            self.hook.worker()
        self.assertEqual(json.loads(stdout.getvalue())["status"], "ERROR")
        self.assertNotIn(DUMMY, stdout.getvalue() + stderr.getvalue())

    def test_only_implementer_stop_is_wired_to_scanner(self):
        profiles = SOURCE.parent.parent / "agents"
        implementer = (profiles / "implementer.agent.md").read_text()
        frontmatter = implementer.split("---", 2)[1]
        self.assertIn("hooks:\n  Stop:\n", frontmatter)
        self.assertIn("command: python3 .github/hooks/secret-scan/run.py", frontmatter)
        self.assertIn("windows: python .github/hooks/secret-scan/run.py", frontmatter)
        self.assertIn("command: python3 .github/hooks/format-lint/run.py", frontmatter)
        for profile in profiles.glob("*.agent.md"):
            if profile.name != "implementer.agent.md":
                self.assertNotIn(
                    ".github/hooks/secret-scan/run.py", profile.read_text()
                )


if __name__ == "__main__":
    unittest.main()
