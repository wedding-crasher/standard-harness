---
name: implement
description: "Implement a piece of work based on a spec or set of tickets."
disable-model-invocation: true
---

Implement the work described by the user in the spec or tickets.

Follow the agent roles in `AGENTS.md`. This is a main-agent orchestration skill.
When delegation is useful, assign `.github/agents/implementer.agent.md` a bounded
outcome; it owns tests and implementation and returns evidence without launching
reviewers. Small work may be implemented directly by the main agent.

If the user passes a ticket reference, fetch it from the issue tracker and state its title before starting. If the reference is ambiguous, ask.

Call the Skill tool with "tdd" where possible, at pre-agreed seams.

Run typechecking regularly, single test files regularly, and the full test suite once at the end.

Once done, call the Skill tool with "code-review" to review the work.

Commit only with the user's authorization, staging only the intended changes.
Without commit authorization, return the verified working-tree changes.
