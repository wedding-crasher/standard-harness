# Standard Harness

## Setup

```sh
uv sync
```

Installs the hook tools (Ruff, detect-secrets) into the root `.venv`.
Restart Copilot CLI after changing agents or hooks.

### If `uv sync` fails to download packages

`uv sync` fetches wheels from `pypi.org` and `files.pythonhosted.org`. Corporate
security tools (for example Microsoft Defender Network Protection) can block the
second host while `pypi.org` still works. Diagnose with `uv sync -v`; a blocked
host shows `error sending request` / `Socket is not connected`. Then use one of:

1. **Ask IT to allow `files.pythonhosted.org`.** This is the permanent fix.
2. **Use an internal PyPI mirror:**
   `UV_DEFAULT_INDEX=<mirror-url> uv sync`
3. **Install from a local wheel folder.** On an unrestricted machine with the
   same OS and CPU, run
   `pip download ruff==0.17.0 detect-secrets==1.5.0 -d wheels`, copy `wheels/`
   to the repository root, then run
   `uv sync --no-index --find-links wheels`.
4. **TLS interception errors** (certificate failures rather than blocked
   connections): `UV_NATIVE_TLS=1 uv sync` uses the system certificate store.

Without the `.venv`, the `format-lint` and `secret-scan` hooks report `ERROR`
instead of passing; they never install dependencies themselves.

## AGENTS.md

Loaded by every agent. It defines:

- **Principles:** observable outcomes, minimum complexity with complete behavior,
  tests as feedback, evidence before completion, human control, context on demand.
- **Agent roles:** who owns what, how work is assigned and reviewed, and the
  `DONE` / `BLOCKED` / `NEEDS_HUMAN` return contract.

## Agents (`.github/agents/`)

| Agent | Role |
|---|---|
| `architect` | Module boundaries, interfaces, test seams, task decomposition |
| `implementer` | Tests and code together through TDD |
| `reviewer` | One review of functionality and code quality, separate verdicts |

The main agent coordinates and owns commits and final verification.

## Hooks (`.github/hooks/`)

| Hook | When | What |
|---|---|---|
| `format-lint` | `subagentStop`, `implementer` only | Ruff format and lint on changed Python files |
| `secret-scan` | `subagentStop`, `implementer` only | Offline detect-secrets scan of changed files |
| `test-run` | Main agent Stop | Runs the unittest files listed in `test-run/selection.local.json` on every turn |

Hooks are registered in `.github/hooks/*.json`. Each hook folder has its own
README. The two implementer checks do not run for other subagents or the main
agent.

## Skills (`.github/skills/`)

Matt Pocock's skills; `implement`, `implement-spec`, `code-review`, `to-spec`,
and `ask-matt` are adapted to the three agents above.

| Group | Skills |
|---|---|
| Workflow | `ask-matt` `grilling` `grill-me` `grill-with-docs` `to-spec` `to-tickets` `implement` `implement-spec` `code-review` `wayfinder` `chief-of-staff` `triage` |
| Engineering | `tdd` `diagnosing-bugs` `codebase-design` `domain-modeling` `improve-codebase-architecture` `prototype` `research` `pr` `setup-matt-pocock-skills` `setup-pre-commit` `setup-ts-deep-modules` `migrate-to-shoehorn` `git-guardrails-claude-code` |
| Collaboration | `handoff` `claude-handoff` `retro` `wait-what` `to-questionnaire` `loop-me` `teach` `wizard` |
| Writing | `writing-for-agents` `writing-beats` `writing-fragments` `writing-shape` `scaffold-exercises` |

## Docs (`docs/`)

- `prd-template.md`: product-level PRD (Context, Goals & Success, Features & Scope, Constraints)
- `spec-template.md`: feature spec (Purpose, optional User Flow, Requirements & Scenarios, optional Design Notes)
