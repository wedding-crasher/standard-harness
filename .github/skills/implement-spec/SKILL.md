---
name: implement-spec
description: "Implement the result of /to-spec and /to-tickets in code."
disable-model-invocation: true
---

You have been provided a spec. This spec should have tickets associated with it, describing how to implement the spec.

Follow the agent roles in `AGENTS.md`. This is a main-agent orchestration skill.
Use the local `architect`, `implementer`, and `reviewer` profiles as needed.
Local specs/tasks need no remote tracker; use configured tracker instructions
only when accessing or updating remote tickets.

The goal is the entire spec implemented on a single **integration branch**, with every ticket resolved the way the issue tracker closes work.

The tickets are not a list of steps. They are a **task graph** with blocking relationships between them. This means there is always a **frontier** of tickets which are ready to be grabbed.

Communication to and from subagents should be sparse. Communicate primarily through **context pointers**: to the spec, tickets, research notes, and previous commits. Don't duplicate information already available via pointers.

Run implementers concurrently only for independent contracts and disjoint edit
scopes in isolated worktrees. Otherwise work sequentially.

## Steps

1. Read the spec and tickets to understand the task graph.

2. Resolve missing context directly. Use `architect` when module boundaries,
   interfaces, task dependencies, or test seams need design. Confirm material
   decisions and public test seams with the user before implementation.

3. Prepare the integration branch and assigned workspaces under the user's
   authorization. Preserve existing changes; do not reset a mismatched worktree.
   Source commits and integration require authorization before dependent tasks
   can proceed. Publish a branch or PR only when separately authorized.

4. Assign ready tasks to `implementer`, with workspace/base, edit allowlist,
   requirements, agreed test seams, and commands. Each worker owns the TDD loop
   and returns its code and evidence. A mismatched workspace is reported to the
   main agent; workers neither reset nor merge nor dispatch other agents.

5. Audit each returned diff and run `code-review`, which dispatches one independent
   `reviewer` for both functionality and quality. Resolve blocking findings and
   required evidence gaps before the main agent integrates reviewed work with
   user authorization. There is no merger or test-writer subagent.

6. If this changes the **frontier** of available tickets, kick off more **implementer subagents** to work on the new tickets. This allows for maximum concurrency.

7. Run applicable checks on the integrated candidate and use `code-review` for
   the whole change. Assign actionable fixes to `implementer`, rerun affected
   checks, and request re-review of affected scope at the new revision. Do not
   repeat a task review if it already covered the identical full candidate.

8. Report the verified integration branch and any blockers. Update PR readiness
   or ticket status only when authorized; local tasks require no remote mutation.

9. With authorization, clean up only owned worktrees whose work is preserved and
   integrated. Retain unfinished changes and identify their locations.
