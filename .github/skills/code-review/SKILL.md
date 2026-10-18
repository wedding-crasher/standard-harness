---
name: code-review
description: "Review a branch, PR, or working-tree change with one independent reviewer checking both functional requirements and code quality, reporting separate verdicts."
---

Two-axis review of a committed diff or an explicit working-tree snapshot:

- **Standards**: does the code conform to this repo's documented coding standards?
- **Spec**: does the code faithfully implement the originating issue / spec?

Both axes run in **one independent reviewer session**. Dispatch
`.github/agents/reviewer.agent.md` as described under Review in `AGENTS.md`.
The main agent runs this orchestration; a reviewer reads its criteria without
dispatching another agent.

A supplied request, local spec, or ticket is sufficient. Use configured tracker
instructions only when fetching remote issues; missing tracker setup does not
block review of local requirements.

## Process

### 1. Pin the fixed point

Whatever the user said is the fixed point (a commit SHA, branch name, tag, `main`, `HEAD~5`, etc.). If they didn't specify one, ask for it.

For committed changes, resolve the fixed point and HEAD to immutable SHAs and
capture `git diff <base-sha>...<head-sha>` and
`git log <base-sha>..<head-sha> --oneline`. Supply the actual outputs, not just
commands: the reviewer has no shell.

For requested work-in-progress review, identify the agreed baseline and capture
staged, unstaged, and in-scope untracked contents as a hashed snapshot. Do not
commit merely to obtain a reviewable diff. Label the snapshot and keep it stable
during review; later changes require refreshed evidence.

Confirm the baseline exists and the selected change is nonempty before dispatch.
Report an invalid baseline or empty change without launching a reviewer.

### 2. Identify the spec source

Look for the originating spec, in this order:

1. Issue references in the commit messages (`#123`, `Closes #45`, GitLab `!67`, etc.), fetched via the workflow in the tracker doc.
2. A path the user passed as an argument.
3. A spec file under `docs/`, `specs/`, or `.scratch/` matching the branch name or feature.
4. Use a confirmed user request or acceptance criteria if no document exists.
   If no behavioral baseline is available, ask for it. If the user has none,
   the reviewer reports Functionality as `UNVERIFIED` and still reviews quality.

### 3. Identify the standards sources

Search the repo for every file that documents how code should be written. When `CODING_STANDARDS.md` or `CONTRIBUTING.md` exists, it must be on the list.

On top of whatever the repo documents, the Standards axis always carries the **smell baseline** below: a fixed set of Fowler code smells (_Refactoring_, ch.3) that applies even when a repo documents nothing. Two rules bind it:

- **The repo overrides.** A documented repo standard always wins; where it endorses something the baseline would flag, suppress the smell.
- **Always a judgement call.** Each smell is a labelled heuristic ("possible Feature Envy"), never a hard violation. Like any standard here, skip anything tooling already enforces.

Each smell reads *what it is* → *how to fix*; match it against the diff:

- **Mysterious Name**: a function, variable, or type whose name doesn't reveal what it does or holds. → rename it; if no honest name comes, the design's murky.
- **Duplicated Code**: the same logic shape appears in more than one hunk or file in the change. → extract the shared shape, call it from both.
- **Feature Envy**: a method that reaches into another object's data more than its own. → move the method onto the data it envies.
- **Data Clumps**: the same few fields or params keep travelling together (a type wanting to be born). → bundle them into one type, pass that.
- **Primitive Obsession**: a primitive or string standing in for a domain concept that deserves its own type. → give the concept its own small type.
- **Repeated Switches**: the same `switch`/`if`-cascade on the same type recurs across the change. → replace with polymorphism, or one map both sites share.
- **Shotgun Surgery**: one logical change forces scattered edits across many files in the diff. → gather what changes together into one module.
- **Divergent Change**: one file or module is edited for several unrelated reasons. → split so each module changes for one reason.
- **Speculative Generality**: abstraction, parameters, or hooks added for needs the spec doesn't have. → delete it; inline back until a real need shows.
- **Message Chains**: long `a.b().c().d()` navigation the caller shouldn't depend on. → hide the walk behind one method on the first object.
- **Middle Man**: a class or function that mostly just delegates onward. → cut it, call the real target direct.
- **Refused Bequest**: a subclass or implementer that ignores or overrides most of what it inherits. → drop the inheritance, use composition.

### 4. Dispatch one reviewer

Dispatch `reviewer` once, in a session independent of the author. Include:

- Requirements/spec, non-goals, and applicable acceptance criteria.
- Immutable base/head or working-tree snapshot, actual diff and commit list.
- Standards-source paths and this skill's smell baseline.
- Actual test commands, results, and relevant evidence paths for this candidate.
- The implementer's report, clearly identified as claims to verify.

Ask it to inspect functionality (missing, extra, or incorrect behavior) and code
quality (standards, correctness, maintainability, and test validity) together.
It returns separate verdicts with findings and limitations. It neither edits nor
executes commands nor dispatches subagents. Supply additional context when needed.
If independent dispatch is unavailable, report the review as blocked rather than
calling the author's self-review independent.

### 5. Aggregate

Present the review under `## Functionality` and `## Code quality`, retaining
separate `PASS`, `ISSUES`, or `UNVERIFIED` verdicts. Do not let one axis hide a
failure or missing evidence in the other.

Return actionable findings to the implementer. After fixes, collect fresh
evidence and request a scoped re-review of the changed candidate. State unresolved
findings and evidence gaps explicitly; a finished review is not approval to merge.

## Why two axes

A change can pass one axis and fail the other:

- Code that follows every standard but implements the wrong thing → **Standards pass, Spec fail.**
- Code that does exactly what the issue asked but breaks the project's conventions → **Spec pass, Standards fail.**

Reporting them separately stops one axis from masking the other.
