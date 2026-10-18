import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch


SOURCE = Path(__file__).resolve().parent
PASSING = """import unittest
class Example(unittest.TestCase):
    def test_ok(self):
        self.assertEqual(2 + 2, 4)
"""
FAILING = PASSING.replace("2 + 2, 4", "2 + 2, 5")


class HookTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="selected-tests-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.home = self.root / ".github/hooks/test-run"
        self.home.mkdir(parents=True)
        for name in ("run.py", ".gitignore"):
            shutil.copy2(SOURCE / name, self.home / name)
        self.git("init", "--quiet")
        self.commit()

    def git(self, *args):
        return subprocess.run(
            ["git", *args], cwd=self.root, capture_output=True, check=True
        ).stdout

    def commit(self):
        self.git("add", ".")
        self.git(
            "-c",
            "user.name=Hook Test",
            "-c",
            "user.email=hook@example.invalid",
            "commit",
            "--quiet",
            "-m",
            "Fixture",
        )

    def write(self, name, text):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def select(self, *files):
        self.write(
            ".github/hooks/test-run/selection.local.json", json.dumps({"files": files})
        )

    def invoke(self, force=False, **overrides):
        process = subprocess.run(
            [
                sys.executable,
                "-B",
                str(self.home / "run.py"),
                *(["--force"] if force else []),
            ],
            input=json.dumps({"cwd": str(self.root), **overrides}),
            text=True,
            capture_output=True,
            check=True,
            cwd=self.root,
            timeout=20,
        )
        lines = [json.loads(line) for line in process.stdout.splitlines()]
        self.assertEqual(
            len([line for line in lines if line.get("type") != "progress"]), 1
        )
        return lines[-1], process.stdout

    def state(self):
        return json.loads((self.home / "logs/state.json").read_text())

    def test_empty_selection_never_discovers_everything(self):
        self.write("test_unselected.py", FAILING)
        self.select()
        output, text = self.invoke()
        self.assertEqual(output, {})
        self.assertIn("SKIP", text)
        self.assertFalse((self.home / "logs/state.json").exists())

    def test_missing_selection_skips(self):
        self.assertIn("No test files selected", self.invoke()[1])

    def test_only_selected_file_runs_and_unchanged_input_is_cached(self):
        self.write("tests/test_selected.py", PASSING)
        self.write("tests/test_other.py", FAILING)
        self.write("tests/nested/__init__.py", "")
        self.write("tests/nested/test_selected.py", FAILING)
        self.select("tests/test_selected.py")
        self.assertEqual(self.invoke()[0], {})
        self.assertEqual(self.state()["status"], "PASS")
        self.assertEqual(self.state()["tests"], 1)
        log = (self.home / "logs/latest.log").read_bytes()
        self.assertIn("CACHED", self.invoke()[1])
        self.assertEqual((self.home / "logs/latest.log").read_bytes(), log)

    def test_failure_is_cached_as_failure_and_fixed_input_reruns(self):
        self.write("test_selected.py", FAILING)
        self.select("test_selected.py")
        self.assertEqual(self.invoke()[0]["decision"], "block")
        output, text = self.invoke()
        self.assertEqual(output, {})
        self.assertIn("previous result: FAIL", text)
        self.write("test_selected.py", PASSING)
        self.invoke()
        self.assertEqual(self.state()["status"], "PASS")

    def test_forced_continuation_does_not_block_again(self):
        self.write("test_selected.py", FAILING)
        self.select("test_selected.py")
        self.assertEqual(self.invoke(stop_hook_active=True)[0], {})
        self.assertEqual(self.state()["status"], "FAIL")

    def test_source_changes_and_deletions_invalidate_cache(self):
        self.write("test_selected.py", PASSING)
        self.write("app.py", "value = 1\n")
        self.select("test_selected.py")
        self.commit()
        self.assertIn("SKIP", self.invoke()[1])
        self.write("app.py", "value = 2\n")
        self.assertIn("[test-run RUN]", self.invoke()[1])
        self.git("add", "app.py")
        index = self.git("show", ":app.py")
        self.assertIn("[test-run RUN]", self.invoke()[1])
        self.assertEqual(self.git("show", ":app.py"), index)
        (self.root / "app.py").unlink()
        self.assertIn("[test-run RUN]", self.invoke()[1])

    def test_selected_file_change_on_clean_tree_runs(self):
        self.write("test_a.py", PASSING)
        self.write("test_b.py", FAILING)
        self.select("test_a.py")
        self.commit()
        self.invoke()
        self.select("test_b.py")
        self.assertIn("[test-run RUN]", self.invoke()[1])
        self.assertEqual(self.state()["status"], "FAIL")

    def test_logs_caches_and_references_do_not_trigger_tests(self):
        self.write("test_selected.py", PASSING)
        self.select("test_selected.py")
        self.invoke()
        for path in (
            "reference/example.py",
            ".venv/example.py",
            "__pycache__/example.pyc",
            ".github/hooks/format-lint/logs/latest.log",
            ".github/hooks/secret-scan/logs/latest.log",
            ".github/hooks/secret-scan/.scratch/test-fixture.py",
        ):
            self.write(path, "not an input")
        self.assertIn("CACHED", self.invoke()[1])

    def test_same_module_name_in_different_folders(self):
        self.write("one/test_run.py", PASSING)
        self.write("two/test_run.py", PASSING)
        self.select("one/test_run.py", "two/test_run.py")
        self.invoke()
        self.assertEqual(self.state()["tests"], 2)
        self.assertEqual(self.state()["status"], "PASS")

    def test_package_relative_imports(self):
        self.write("tests/__init__.py", "")
        self.write("tests/helper.py", "value = 4\n")
        self.write(
            "tests/test_package.py",
            "from .helper import value\n" + PASSING.replace("2 + 2", "value"),
        )
        self.select("tests/test_package.py")
        self.invoke()
        self.assertEqual(self.state()["status"], "PASS")

    def test_zero_tests_is_error_and_all_skipped_is_not_pass(self):
        self.write("test_empty.py", "value = 1\n")
        self.select("test_empty.py")
        self.invoke()
        self.assertEqual(self.state()["status"], "ERROR")
        self.write(
            "test_empty.py",
            PASSING.replace(
                "class Example", '@unittest.skip("fixture")\nclass Example'
            ),
        )
        self.invoke()
        self.assertEqual(self.state()["status"], "SKIP")

    def test_invalid_selection_does_not_fall_back_to_discovery(self):
        for name in ("missing.py", "../outside.py", "tests", "/tmp/test.py"):
            with self.subTest(name=name):
                self.select(name)
                self.assertIn("ERROR", self.invoke()[1])
                self.assertFalse((self.home / "logs/state.json").exists())

    @unittest.skipIf(os.name == "nt", "Requires symlink privileges")
    def test_selected_symlink_is_rejected(self):
        target = self.write("test_real.py", PASSING)
        (self.root / "test_link.py").symlink_to(target)
        self.select("test_link.py")
        self.assertIn("ERROR", self.invoke()[1])

    def test_missing_dependency_is_error(self):
        self.write("test_import.py", "import missing_fixture_dependency\n")
        self.select("test_import.py")
        self.invoke()
        self.assertEqual(self.state()["status"], "ERROR")
        self.assertIn(
            "ModuleNotFoundError", (self.home / "logs/latest.log").read_text()
        )

    def test_inputs_modified_during_test_do_not_record_pass(self):
        self.write(
            "test_modify.py",
            PASSING.replace(
                "self.assertEqual(2 + 2, 4)",
                'from pathlib import Path\n        Path("app.py").write_text("changed")',
            ),
        )
        self.select("test_modify.py")
        self.invoke()
        self.assertEqual(self.state()["status"], "ERROR")
        self.assertIn("Inputs changed", (self.home / "logs/latest.log").read_text())

    def test_subagent_payload_does_not_run(self):
        self.write("test_selected.py", FAILING)
        self.select("test_selected.py")
        self.assertEqual(self.invoke(agentId="child")[0], {})
        self.assertFalse((self.home / "logs").exists())

    def test_timeout_is_not_a_pass(self):
        spec = importlib.util.spec_from_file_location(
            "selected_test_hook", SOURCE / "run.py"
        )
        hook = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(hook)
        with patch.object(hook, "TEST_TIMEOUT", 0):
            result, text = hook.execute(["test_selected.py"])
        self.assertEqual(result["status"], "TIMEOUT")
        self.assertIn("exceeded", text)

    def test_force_runs_on_clean_and_unchanged_inputs(self):
        self.write("test_selected.py", PASSING)
        self.select("test_selected.py")
        self.commit()
        self.assertIn("SKIP", self.invoke()[1])
        self.assertIn("[test-run RUN]", self.invoke(force=True)[1])
        self.assertIn("[test-run RUN]", self.invoke(force=True)[1])

    def test_reverting_dirty_contents_and_committing_are_detected(self):
        self.write("test_selected.py", PASSING)
        self.select("test_selected.py")
        self.commit()
        self.invoke()
        self.write("test_selected.py", FAILING)
        self.invoke()
        self.write("test_selected.py", PASSING)
        self.assertIn("[test-run RUN]", self.invoke()[1])
        self.assertEqual(self.state()["status"], "PASS")
        self.write("test_selected.py", FAILING)
        self.commit()
        self.assertIn("[test-run RUN]", self.invoke()[1])
        self.assertEqual(self.state()["status"], "FAIL")

    def test_space_in_test_filename(self):
        self.write("tests/test example.py", PASSING)
        self.select("tests/test example.py")
        self.invoke()
        self.assertEqual(self.state()["status"], "PASS")

    @unittest.skipIf(os.name == "nt", "POSIX process-group timeout")
    def test_timeout_stops_test_descendants(self):
        self.write(
            "test_slow.py",
            """import subprocess
import sys
import time
import unittest
class Slow(unittest.TestCase):
    def test_slow(self):
        subprocess.Popen([sys.executable, "-c",
            'import time; from pathlib import Path; time.sleep(1); Path("leaked").touch()'])
        time.sleep(10)
""",
        )
        spec = importlib.util.spec_from_file_location(
            "timeout_hook", self.home / "run.py"
        )
        hook = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(hook)
        with patch.object(hook, "TEST_TIMEOUT", 0.3):
            report, _ = hook.execute(["test_slow.py"])
        self.assertEqual(report["status"], "TIMEOUT")
        time.sleep(1)
        self.assertFalse((self.root / "leaked").exists())


if __name__ == "__main__":
    unittest.main()
