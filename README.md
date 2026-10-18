# Standard Harness

## Setup

```sh
uv sync
```

Installs the hook tools (Ruff, detect-secrets) into the root `.venv`.
Restart Copilot CLI after changing agents or hooks.

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
| `format-lint` | `implementer` Stop | Ruff format and lint on changed Python files |
| `secret-scan` | `implementer` Stop | Offline detect-secrets scan of changed files |
| `test-run` | Main agent Stop | Runs the unittest files listed in `test-run/selection.local.json`, only when inputs changed |

Each hook folder has its own README.

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
