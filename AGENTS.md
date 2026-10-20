# Development principles

## Observable outcomes

Translate the request into behavior that can be checked. Read the existing code
and its callers before choosing a change. When alternatives materially change
behavior, compatibility, or scope, make the tradeoff explicit and get a decision.

## Minimum complexity, complete behavior

Implement the requirements in the simplest way that fully satisfies them,
including failure paths. Minimize concepts, branches, dependencies, and
indirection rather than merely minimizing lines changed. Every added layer or
configuration option must serve a current requirement.

Keep the change focused and reuse existing conventions and interfaces.
Introduce an abstraction when
it hides real complexity for its callers, not to prepare for hypothetical needs.
Keep unrelated cleanup outside the change.

## Tests as feedback

For behavior changes, work in short red-green cycles through public interfaces.
Assert observable behavior with independent expectations. Preserve useful tests
when implementation details change; a failing requirement needs a fix or an
explicit scope decision, not a weaker assertion.

## Evidence before completion

Tie completion claims to the current code and actual command results. A partial
check supports only its tested scope. Distinguish passed, failed, skipped, and
unverified work; missing tools and hook errors are gaps, not successful checks.

## Human control

Treat existing work and developer-owned choices as constraints. Make progress
within the agreed scope; surface decisions that change it. Keep failure and
recovery visible rather than substituting success-shaped defaults.

## Context on demand

Keep durable rules here and task-specific detail near the work. Maintain one
authoritative home for each rule; use a targeted pointer instead of copying it
into every agent prompt.

When editing agent instructions or skills, read
[writing for agents](.github/skills/writing-for-agents/SKILL.md). Check that each
pointer states when to follow it and that documented behavior matches the code.

Use project skills from `.github/skills/`. Repositories under `reference/` are
source material, not active plugins or instructions for this project's workflow.

# Agent roles

The main agent coordinates; three specialists live in `.github/agents/`.
Small tasks stay with the main agent.

| Role | Responsibility |
|---|---|
| `architect` | Module boundaries, interfaces, test seams, task decomposition |
| `implementer` | Tests and implementation together through TDD, one behavior at a time |
| `reviewer` | One independent review of functionality and code quality |

## Ownership

The main agent owns user decisions, assignments, integration, authorized commits,
and final verification. Workers stay inside their assignment: they leave dispatching,
shared progress, branch switching, merging, pushing, and approval to the main agent.
Role permissions do not sandbox shell commands or enforce path allowlists, so the
main agent checks each returned diff against the assigned scope. Models inherit
runtime defaults.

The implementer leaves changes uncommitted until its Stop checks (format/lint and
secret scan) finish. They report in the terminal and prepend a warning to the
response on failure or after reformatting; the main agent then reruns affected tests.

## Assignment

Give each worker one bounded goal with requirements, acceptance criteria, and
non-goals; the workspace, base, and allowed edit paths; agreed test seams; and a
completion condition. Run writers concurrently only in isolated worktrees with
disjoint scopes. Integrate reviewed work before starting its dependents.

## Review

The main agent audits the diff, then runs `.github/skills/code-review/SKILL.md`,
giving the reviewer (read/search tools only) the base and head, or for uncommitted
work a hashed snapshot of staged, unstaged, and untracked files, plus the diff and
test evidence. Findings go back to the implementer; a changed revision gets fresh
evidence and a fresh review. After integrating several tasks, run the integrated
checks and review the whole change.

The `agentStop` test hook runs the unittest files the developer lists in
`.github/hooks/test-run/selection.local.json` on every main-agent completion.
Leave that selection unchanged to get a true result; a selected-test pass does
not replace the integrated checks.

## Return contract

Return `DONE`, `BLOCKED`, or `NEEDS_HUMAN` with what was completed, commands and
exit codes, findings, limitations, and the next owner. Reviewers return separate
Functionality and Code quality verdicts (`PASS`, `ISSUES`, `UNVERIFIED`). Missing
evidence is a gap, never a pass. After three failed fixes of one issue, diagnose
within a bound and report the blocker.
