---
name: to-spec
description: "Turn an agreed PRD or conversation into local feature specs using the project template or a compact built-in structure."
disable-model-invocation: true
---

Synthesize agreed requirements into feature specs; this is not a new product
interview or an implementation task. Follow the agent roles in `AGENTS.md`.
Use the requested PRD and confirmed conversation decisions as inputs.
If no input path is supplied, use `docs/prd.md` when present, otherwise the
confirmed conversation. Ask for clarification when sources conflict or the
requested feature boundary is ambiguous.

## Process

1. Read `docs/spec-template.md` before drafting. If it is absent, use the compact
   structure below and report that fallback in the handoff. The project template
   takes precedence when present; preserve its section names and numbering.
   An unreadable project
   template is an error to report, not a reason to silently switch templates.
   Read existing specs, relevant code, glossary entries, and ADRs to distinguish
   existing behavior from proposed changes.

2. Map the requested scope to feature-level documents. For a whole PRD, account
   for every in-scope feature; avoid splitting shared behavior into duplicate
   requirements. Use the user's output paths, otherwise follow the existing
   spec location, falling back to `docs/<feature-name>-spec.md`. Read an existing
   target before updating it and preserve unrelated decisions.

3. Identify how each requirement can be checked through observable behavior.
   Prefer existing public test seams and the highest boundary that meaningfully
   exercises the feature. Confirm new or changed test seams with the user;
   retain already-confirmed ones. Keep a proposed seam explicitly unconfirmed
   until accepted, rather than inventing an API or architecture to fill the spec.

4. Write using the template rules below. Synthesize only agreed behavior;
   mark missing decisions as `TBD` beside the affected requirement or design
   note. State what needs deciding instead of writing a fictional expected
   result. A document with unresolved behavioral or test-seam decisions is a
   draft, not ready for implementation.

5. Check that every in-scope requirement has a verifiable scenario or an explicit
   blocking `TBD`, that exclusions remain excluded, and that technical proposals
   are distinguishable from approved decisions. Save the local documents and
   report their paths, coverage, and unresolved decisions. Publication to an
   issue tracker requires an explicit user request and configured tracker
   instructions; never automatically apply a readiness label.

## Template rules

If the project template is absent, start with `# [Feature Name] — Spec` and use
`## 1. Purpose`, `## 2. User Flow (Optional)`,
`## 3. Requirements & Scenarios`, and `## 4. Design Notes (Optional)`.
Purpose and Requirements & Scenarios are required; omit optional sections when
unneeded, keeping the remaining section numbers. Apply the rules below.

- **Purpose:** Explain this feature in one or two sentences and link its source
  PRD when available. Reference product goals and exclusions rather than copying
  them; put feature-specific boundaries here when needed.
- **User Flow (Optional):** Include only when a multi-step user experience needs
  explanation. Omit the section when it adds nothing.
- **Requirements & Scenarios:** Use `### Requirement:` and `#### Scenario:`
  headings with **Given**, **When**, and **Then** bullets. Each agreed requirement
  needs at least one observable scenario. Cover relevant normal, boundary, and
  failure behavior without inventing policies or padding a user-story list.
  Expected outcomes must be specific enough to test, not merely "works correctly."
- **Design Notes (Optional):** Include only meaningful Architecture, Data Model,
  Interfaces, or Technical Decisions. Record agreed public test seams and
  relevant test prior art alongside the interface or decision they verify;
  a separate Testing Decisions section is unnecessary. Prefer contracts and
  reasons over implementation file inventories. A short prototype excerpt may
  be retained when it expresses a decision more precisely than prose.

Write in the input documents' language unless the user requests another.
The product PRD and template remain unchanged unless their revision is requested.
