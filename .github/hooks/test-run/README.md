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
(`python` on Windows) can import the project's dependencies. Each selected file
runs in a fresh process with the repository as its working directory. Package
relative imports and duplicate basenames in different directories are supported.
Tests must use `unittest.TestCase` or a `load_tests` suite; pytest-only functions
are not supported and collecting zero tests is an error.

On each Stop, the hook fingerprints the selected list, runner/interpreter,
in-scope index blob IDs, and staged/unstaged/untracked working-file contents.
Deleted paths count as changes. Clean indexed files are represented by Git blob
IDs rather than rereading the entire repository.

- First invocation with changes: run only the selected test files.
- First invocation with a clean tree: record a baseline and skip.
- Same fingerprint: skip execution, preserving the previous result, including
  failures. The existing test log is not overwritten.
- Changed fingerprint or selection: run again, even if changes were committed
  or reverted between invocations.

State is per worktree, shared by sessions. A conversation without new file
changes does not rerun tests after the first check. This is change detection,
not edit-ownership detection: existing or externally made changes can trigger it.
Reference clones, common dependency/build/cache directories and hook logs are
excluded. Non-Python source/configuration changes also invalidate the result.
No index or source changes are made by the hook itself.

The selected tests share a **60-second** limit; the hook has a **120-second**
outer limit to leave room for Git and logging. Missing files, import errors,
zero tests, invalid results and timeouts are not passes. All-skipped suites are
reported as `SKIP`. If inputs change during execution, no current pass is cached.
Failures request one continuation; a hook-forced continuation is not blocked
again. Unchanged failures stay failed without rerunning or repeatedly blocking.
There is no AI reviewer, automatic installation, commit, or background scheduler.

## Output and local state

Results appear as `[test-run PASS]`, `FAIL`, `ERROR`, `TIMEOUT`, `SKIP`, or
`CACHED` (with the previous status). Full test output and counts are stored in
`logs/latest.log`; `logs/state.json` holds the last input fingerprint and result.
Both are gitignored. Test output can contain application data; do not print
credentials in tests or upload these logs without inspection.

No selection means no test log yet. Early configuration/Git/lock errors appear
in the terminal and may have no log. A worktree-local `logs/.running` lock
prevents overlapping runs. After an interrupted process, verify no run remains
before deleting that lock.

To rerun the same selection after an external environment fix or on a clean tree,
append `--force` to the manual hook command below. This bypasses change detection,
not test failures, and does not change the selection.
In-place package changes, environment variables and external services are not
fingerprinted. This hook complements, not replaces, required CI checks.

```sh
printf '{"cwd":"%s"}' "$PWD" | python3 .github/hooks/test-run/run.py
python3 -m unittest discover -s .github/hooks/test-run -p 'test_*.py'
```

Restart Copilot after adding the hook. The repository must be trusted.
See [GitHub's hook reference](https://docs.github.com/en/copilot/reference/hooks-reference).
