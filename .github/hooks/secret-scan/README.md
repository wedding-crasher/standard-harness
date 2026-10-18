# Implementer Stop: offline secret scanning

The local `implementer` profile runs this separate command alongside its existing
Ruff `Stop` hook. No other agent, repository-wide hook, or lifecycle event runs
it. The same agent-scoped-hook-capable CLI and workspace trust requirements apply;
restart the CLI after editing the profile. No global trust settings are changed.

## Setup

From the repository root (requires [uv](https://docs.astral.sh/uv/)):

```sh
uv sync
```

This creates the shared root `.venv` with pinned
[`detect-secrets` 1.5.0](https://github.com/Yelp/detect-secrets/tree/v1.5.0)
from `pyproject.toml`. The hook uses `.venv/bin/python`
(`.venv/Scripts/python.exe` on Windows); if it is missing the hook reports
`ERROR` and asks you to run `uv sync`. It never installs packages or uses the
network, and makes no credential-verification requests. It uses the built-in
provider, private-key, keyword and entropy detectors with no baseline, user
configuration, or plugins; inline `allowlist secret` comments cannot suppress
findings.

## Scope

- Staged/unstaged changes and Git-unignored untracked files of any extension.
- Full **worktree files** and actual **index blobs** (even if the worktree copy
  was cleaned or deleted). Findings name `worktree` or `index`; a worktree fix
  cannot clear an index finding.
- Excluded: clean committed files, history, other worktrees, `reference/`,
  `references/`, nested Git repositories, `.git`, `.venv`, `venv`, directories
  with `pyvenv.cfg`, `node_modules`, `build`, `dist`, `__pycache__`,
  `.ruff_cache`, and `.github/hooks/test-run/logs`.
- Symlinks and submodule gitlinks are not followed. Forced-staged ignored files
  are checked.
- Files are never modified, staged, or committed. Use a dedicated worktree and
  leave changes uncommitted until the Stop checks finish.

## Results

Each run scans from scratch and writes no files. It prints a progress line and
one final decision object on stdout. Statuses:

- `PASS`: all selected snapshots scanned without findings.
- `SKIP`: `No in-scope changed files.`
- `FAIL`: potential secrets, printed as `source:path:line:type`. Secret values
  and snippets are never printed; a detected value inside a filename is shown as
  `[REDACTED]`. Remove the value, use environment/secret-store references, and
  rotate real exposed credentials.
- `ERROR`: incomplete scan (missing environment or wrong version, Git failure,
  unmerged files, binary/non-UTF-8 input, exceeded limits, timeout, or files
  changing mid-scan).

The decision is always `{}` (never `block`). On `FAIL`/`ERROR`, a warning is
prepended to the response when the payload carries one, and printed to stderr.
Infrastructure errors (bad input, Git failure) print `[secret-scan ERROR]` and
use a fixed warning.

Limits: 1,000 paths, 2 MiB per snapshot, 20 MiB total, 60 seconds for the
scanner process. UTF-8 (optionally BOM) text only; archives and encoded values
are not decoded. Detectors have false positives and negatives, so a pass is not
proof that no secrets exist. This is developer feedback, not a security boundary;
CLI hooks can fail open or be disabled.

## Manual check and tests

```sh
printf '{"cwd":"%s"}' "$PWD" | python3 .github/hooks/secret-scan/run.py
python3 -m unittest discover -s .github/hooks/secret-scan -p 'test_*.py'
```

Tests use disposable Git repositories, synthetic tokens assembled at runtime
(no real credentials, nothing allowlisted), and the real scanner.
