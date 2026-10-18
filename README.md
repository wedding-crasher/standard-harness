### Standard Harness

Shared development principles and agent roles live in [AGENTS.md](AGENTS.md).
See [the source comparison](docs/research/agent-instruction-philosophies.md) for
the public projects consulted and the practices deliberately not imported.

Matt Pocock skills live in `.github/skills/`. The local orchestration skills
(`implement`, `implement-spec`, and `code-review`), the `to-spec` writer,
and the `ask-matt` router
are adapted to three agents:

| Agent | Responsibility |
|---|---|
| `architect` | Module boundaries, interfaces, test seams, and task decomposition |
| `implementer` | Tests and implementation together through TDD |
| `reviewer` | One independent review of both functionality and code quality |

The main agent coordinates work, user decisions, integration, and final
verification. See [AGENTS.md](AGENTS.md) for ownership, handoffs, and review
evidence. Models use runtime defaults.
There is no separate test writer or second reviewer.

`to-spec` turns an agreed PRD or conversation into local feature documents using
[`docs/spec-template.md`](docs/spec-template.md), or a compact structure described
inside the skill if the project template is absent. Requirements and Given/When/Then
scenarios are central; User Flow and Design Notes are optional. Unresolved
decisions remain explicit draft blockers rather than invented requirements.
Issue publication is opt-in, not a prerequisite.

Sources under `reference/` remain unmodified and are not installed as plugins:

- `ai-native-harness`: scoped specialist roles and evidence-based handoffs.
- `mattpocock-skills`: the original skills; local copies retain the MIT license.
- `superpowers`: `obra/superpowers`, cloned at
  `bb92a77741419a4ab5f06e711a283343f1ada0c3` (v7.0.0), consulted for
  single-reviewer task checks and verification before completion.

Updating a reference clone does not update `.github/skills/` or the local agents.
Preserve the local adaptations when importing future upstream changes.

### Setup

Hook tools are pinned in `pyproject.toml` and installed with
[uv](https://docs.astral.sh/uv/) into one shared root `.venv`. Run `uv sync` in
the repository root once; the hooks never install packages.

### Python format/lint hook

The Implementer's scoped `Stop` runs Ruff formatting and linting on changed
Python files each time, keeping no state or logs. Results and failure locations
appear in the terminal; on failure or formatting changes a warning is also
prepended to the response. No other agent or lifecycle event runs it.
See [scope and statuses](.github/hooks/format-lint/README.md).

### Offline secret scanning hook

The same Implementer-only `Stop` also runs pinned `detect-secrets` on changed
text files of all types, including staged index contents and unstaged/untracked
worktree files. It detects potential API keys, tokens and private keys offline;
the terminal shows locations and detector types, never secret values or snippets.
Reference clones, virtual environments and dependencies are excluded. See
[scope, limitations, and tests](.github/hooks/secret-scan/README.md).

### Selected tests on main-agent Stop

Edit `.github/hooks/test-run/selection.local.json` to list the unittest files to run.
The main-agent `agentStop` hook runs only that list when code/index contents or
the selection change; unchanged inputs reuse the previous result, including
failures. An empty list disables it. Results live in
`.github/hooks/test-run/logs/latest.log`. See [usage and limits](.github/hooks/test-run/README.md).
