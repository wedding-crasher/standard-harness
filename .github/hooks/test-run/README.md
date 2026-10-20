# Selected tests at main-agent Stop

Edit `selection.local.json` in this directory. It is local and gitignored; when
cloning the harness, copy `selection.example.json` to `selection.local.json`.
Paths are relative to the repository root:

```json
{
  "files": [
    "tests/test_auth.py",
    "tests/test_order.py"
  ]
}
```

These are examples, not files provided by this repository. An absent selection
or `"files": []` disables execution. Only the developer chooses the list; agents
must not add files or remove failing tests. No globs, directories, shell commands,
or automatic related-test discovery are supported.

## Execution

`.github/hooks/test-run.json` registers only `agentStop`, not `subagentStop`.
It runs at the end of a top-level agent turn, including a directly selected
custom agent. It does not run when a worker returns to its parent.

The hook uses Python's standard-library `unittest`, with no new dependencies.
Start Copilot from the project's activated Python environment so `python3`
(`python` on Windows) can import the project's dependencies. The selected files
run together in one child process with the repository as its working directory.
Package relative imports and duplicate test basenames are supported, but tests
share process state; they are not isolated from one another.
Tests must use `unittest.TestCase` or a `load_tests` suite; pytest-only functions
are not supported and collecting zero tests is an error.

On each Stop, the hook runs the selected files, even on a clean tree or when
inputs have not changed. There is no fingerprint, cached result, or execution
lock. No index or source changes are made by the hook itself.

The selected tests share a **60-second** limit; the hook has a **120-second**
outer limit to leave room for startup and logging. Missing files, import errors,
zero tests, invalid results and timeouts are not passes. All-skipped suites are
reported as `SKIP`.
Failures request one continuation; a hook-forced continuation is not blocked
again, but its selected tests still run.
There is no AI reviewer, automatic installation, commit, or background scheduler.

## Output

Results appear as `[test-run PASS]`, `FAIL`, `ERROR`, `TIMEOUT`, `SKIP`, or
`RUN`. Full test output and counts are stored in `logs/latest.log`, which is
gitignored and overwritten on each run. Test output can contain application data; do not print
credentials in tests or upload these logs without inspection.

No selection means no new test log. Early configuration errors appear in the
terminal and may have no log. Concurrent runs can overwrite each other's log.
An old `logs/state.json` or `logs/.running` from the previous implementation is
unused. This hook complements, not replaces, required CI checks.

```sh
printf '{"cwd":"%s"}' "$PWD" | python3 .github/hooks/test-run/run.py
```

Restart Copilot after adding the hook. The repository must be trusted.
See [GitHub's hook reference](https://docs.github.com/en/copilot/reference/hooks-reference).
