# Implementer Stop: Python formatting and linting

Only the local `implementer` profile runs this hook. Its scoped `Stop` executes
when it finishes as a subagent, or when that profile is selected directly.
This formatter is not registered on repository-wide lifecycle events.
Requires a Copilot CLI version supporting agent-scoped hooks and progress output.
Restart the CLI after changing the profile. The workspace must also be trusted:
accept the CLI's folder-trust prompt. Do this only for a repository whose agent
and hook commands you trust. Merely selecting the agent does not admit its hooks.
Folder trust is CLI application state, not a `copilot config` setting.

## Setup

From the repository root (requires [uv](https://docs.astral.sh/uv/)):

```sh
uv sync
```

This creates the shared root `.venv` with the pinned Ruff from `pyproject.toml`.
The hook uses `.venv/bin/python` (`.venv/Scripts/python.exe` on Windows),
never installs packages, and never uses the network. If `.venv` is missing the
hook reports `ERROR` and asks you to run `uv sync`.

Ruff formats, then lints without auto-fixes, using the explicit colocated
`ruff.toml` for all selected files.

## Scope

The hook selects existing `.py`/`.pyi` files from staged, unstaged, and
Git-unignored untracked changes. It excludes `reference`, Git internals,
virtual environments, dependencies, build outputs, and symlinks. Formatting
edits worktree files only; the index is never updated, staged, or committed.

Git's dirty-file list is not proof of edit ownership: use a dedicated worktree
holding only the implementer's assigned changes. Leave changes uncommitted until
the Stop hook has run.

## Results

Each run checks from scratch and writes no files. It prints a progress line and
one final decision object on stdout. Statuses:

- `PASS`: formatter and linter succeeded (the message says if files changed).
- `SKIP`: `No changed Python files.`
- `FAIL`: lint diagnostics, printed as `file:line:col code message`.
- `ERROR`: parse error, missing environment, timeout, or tool failure.

The decision is always `{}` (never `block`). On `FAIL`/`ERROR`, or when
formatting changed files, a warning is prepended to the response when the
payload carries one; `FAIL`/`ERROR` also print it to stderr. After a format
change, rerun affected tests and refresh the report.

Limits: 15 seconds per Ruff command. This is developer feedback, not a security
boundary; CLI hooks can fail open or be disabled.

## Manual check and tests

```sh
printf '{"cwd":"%s"}' "$PWD" | python3 .github/hooks/format-lint/run.py
python3 -m unittest discover -s .github/hooks/format-lint -p 'test_*.py'
```

The first command can change selected files.

References: [GitHub agent-scoped hooks](https://docs.github.com/en/copilot/reference/hooks-reference#agent-scoped-hooks),
[Ruff configuration](https://docs.astral.sh/ruff/configuration/).
