# Implementer Stop: offline secret scanning

Registered in `.github/hooks/secret-scan.json` on `subagentStop`, alongside
the separate Ruff hook. Its `--implementer-only` option runs the scan only when
the event's `agentName` is `implementer`. Other subagents silently return `{}`
without scanning. It does not run at main-agent completion, including when
`implementer` is selected as the main agent. The agent profile has no duplicate
registration. The same repository-hook-capable CLI and workspace trust
requirements as [format-lint](../format-lint/README.md) apply; restart the CLI
after changing hook registrations. No global trust settings are changed.

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
  unmerged files, binary/non-UTF-8 input, exceeded limits, or timeout).

The decision is always `{}` (never `block`). On `FAIL`/`ERROR`, a warning is
prepended to the response when the payload carries one, and printed to stderr.
Infrastructure errors (bad input, Git failure) print `[secret-scan ERROR]` and
use a fixed warning.

Limits: 1,000 paths, 2 MiB per snapshot, 20 MiB total, 60 seconds for the
scanner process. UTF-8 (optionally BOM) text only; archives and encoded values
are not decoded. The scan checks the contents read at startup; it does not
recheck for edits made while scanning. Detectors have false positives and negatives, so a pass is not
proof that no secrets exist. This is developer feedback, not a security boundary;
CLI hooks can fail open or be disabled.

## Manual check

```sh
printf '{"cwd":"%s"}' "$PWD" | python3 .github/hooks/secret-scan/run.py
```
