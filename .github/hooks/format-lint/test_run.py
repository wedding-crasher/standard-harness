import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


SOURCE = Path(__file__).resolve().parent


class StopHookTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="format-lint-test-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.home = self.root / ".github/hooks/format-lint"
        self.home.mkdir(parents=True)
        for name in ("run.py", "ruff.toml"):
            shutil.copy2(SOURCE / name, self.home / name)
        self.git("init", "--quiet")
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
        environment = SOURCE.parents[2] / ".venv"
        self.assertTrue(environment.is_dir(), "Run `uv sync` in the repository root")
        (self.root / ".venv").symlink_to(environment, target_is_directory=True)

    def git(self, *args):
        return subprocess.run(
            ["git", *args], cwd=self.root, capture_output=True, check=True
        ).stdout

    def write(self, name, text):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def invoke(self, **overrides):
        payload = {
            "cwd": str(self.root),
            "sessionId": "test",
            "agentId": "implementer-1",
            "response": "DONE",
            **overrides,
        }
        process = subprocess.run(
            [sys.executable, str(self.home / "run.py")],
            input=json.dumps(payload),
            text=True,
            capture_output=True,
            cwd=self.root,
            timeout=30,
            check=True,
        )
        objects = [json.loads(line) for line in process.stdout.splitlines()]
        decisions = [item for item in objects if item.get("type") != "progress"]
        self.assertEqual(len(decisions), 1)
        self.terminal = process.stdout + process.stderr
        return decisions[0], process

    def test_result_is_stateless_and_never_blocks(self):
        self.write("bad.py", "import os\n")
        first = self.invoke()
        second = self.invoke()
        self.assertEqual(first[0], second[0])
        self.assertEqual(first[1].stdout, second[1].stdout)
        self.assertNotIn("decision", first[0])
        self.assertEqual(
            [p.name for p in self.home.iterdir() if p.name != "__pycache__"],
            ["run.py", "ruff.toml"],
        )

    def test_formatting_change_passes_with_warning_prepended(self):
        path = self.write("src/a file.py", "answer=  42\n")
        output, process = self.invoke()
        self.assertEqual(path.read_text(), "answer = 42\n")
        self.assertEqual(
            output,
            {
                "modifiedResponse": "[format/lint] Formatting changed files; "
                "rerun affected tests and refresh your report. \n\nDONE"
            },
        )
        self.assertIn("[format/lint PASS]", process.stdout)
        self.assertIn("Formatting changed files", process.stdout)
        self.assertEqual(process.stderr, "")
        self.assertEqual(self.invoke()[0], {})

    def test_failures_are_shown_with_location_and_not_auto_fixed(self):
        path = self.write("bad.py", "import os\n")
        output, process = self.invoke()
        self.assertIn("did not pass", output["modifiedResponse"])
        self.assertTrue(output["modifiedResponse"].endswith("DONE"))
        self.assertIn("[format/lint FAIL]", process.stdout)
        self.assertIn("bad.py:1:8 F401", process.stdout)
        self.assertIn("did not pass", process.stderr)
        self.assertEqual(path.read_text(), "import os\n")
        path.write_text("answer = 42\n")
        self.assertEqual(self.invoke()[0], {})
        self.assertIn("PASS", self.terminal)

    def test_failure_without_response_returns_empty_decision(self):
        self.write("bad.py", "import os\n")
        output, process = self.invoke(response=None)
        self.assertEqual(output, {})
        self.assertIn("[format/lint FAIL]", process.stdout)

    def test_clean_tree_and_excluded_files_are_skipped(self):
        for name in ("reference/example.py", "dist/output.py", "notes.md"):
            self.write(name, "not python !!!")
        output, process = self.invoke()
        self.assertEqual(output, {})
        self.assertIn("[format/lint SKIP] No changed Python files.", process.stdout)
        self.assertIn("SKIP", self.terminal)
        self.assertEqual(
            (self.root / "reference/example.py").read_text(), "not python !!!"
        )

    def test_staged_files_are_formatted_without_changing_index(self):
        path = self.write("staged.py", "answer=42\n")
        self.git("add", "staged.py")
        index = self.git("show", ":staged.py")
        self.invoke()
        self.assertEqual(path.read_text(), "answer = 42\n")
        self.assertEqual(self.git("show", ":staged.py"), index)

    def test_unstaged_and_deleted_files(self):
        changed = self.write("changed.py", "answer = 1\n")
        deleted = self.write("deleted.py", "answer = 1\n")
        self.git("add", "changed.py", "deleted.py")
        self.git(
            "-c",
            "user.name=Hook Test",
            "-c",
            "user.email=hook@example.invalid",
            "commit",
            "--quiet",
            "-m",
            "Python fixture",
        )
        changed.write_text("answer=2\n")
        deleted.unlink()
        self.invoke()
        self.assertEqual(changed.read_text(), "answer = 2\n")
        self.assertNotIn("deleted.py", self.terminal)

    def test_missing_environment_is_error_mentioning_uv_sync(self):
        self.write("example.py", "answer = 42\n")
        (self.root / ".venv").unlink()
        output, process = self.invoke()
        self.assertIn("did not pass", output["modifiedResponse"])
        self.assertIn("[format/lint ERROR]", process.stdout)
        self.assertIn("uv sync", process.stdout)

    def test_parse_error_is_not_a_pass(self):
        self.write("broken.py", "def broken(\n")
        output, process = self.invoke()
        self.assertIn("did not pass", output["modifiedResponse"])
        self.assertIn("[format/lint ERROR]", process.stdout)
        self.assertIn("ruff format failed", process.stdout)

    @unittest.skipIf(os.name == "nt", "Symlink permissions depend on Windows setup")
    def test_symlink_is_not_formatted(self):
        target = self.write("reference/original.py", "answer=42\n")
        (self.root / "linked.py").symlink_to(target)
        self.invoke()
        self.assertEqual(target.read_text(), "answer=42\n")
        self.assertIn("SKIP", self.terminal)

    def test_invalid_hook_input_has_visible_error_and_valid_output(self):
        process = subprocess.run(
            [sys.executable, str(self.home / "run.py")],
            input="{",
            text=True,
            capture_output=True,
            check=True,
        )
        self.assertIn("ERROR", process.stderr)
        self.assertEqual(json.loads(process.stdout.splitlines()[-1]), {})


if __name__ == "__main__":
    unittest.main()
