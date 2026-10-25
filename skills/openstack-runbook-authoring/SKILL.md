---
name: openstack-runbook-authoring
description: Turns OpenStack operational knowledge - an incident outcome, an expert's procedure, notes, chat logs or an existing runbook - into a reproducible runbook with purpose and scope, preconditions, decision points where symptoms diverge, read-only versus state-changing steps with expected results, stop and escalation conditions, explicit must-not-do actions, verification, recovery, owner and a validation plan by someone other than the author. Use when someone asks to write, review, improve or standardize a runbook, SOP, procedure, playbook document or knowledge-base article for operating, troubleshooting or recovering OpenStack, or to capture knowledge before an engineer leaves.
license: Apache-2.0
metadata:
  source: "OpenStack, the Day After Tomorrow (Soufian Zaouam), v1.2 - Ch. 11, 10, 12, 1, 7, 19"
  version: "0.1.0"
---

# OpenStack runbook authoring

Produce documentation that works as operational memory: it preserves the
reasoning, not only the instructions, tells the operator where to stop, and is
proven usable by someone who did not write it [Book: Ch. 11]. A procedure that
says "restart component X" is less valuable than one that also explains why,
what state is expected, which dependencies matter, when to stop and how to
recover [Book: Ch. 11].

Read [references/evidence-and-safety.md](references/evidence-and-safety.md)
before the first response; its rules are mandatory. Principles:
[references/operating-principles.md](references/operating-principles.md).

## When to use

- Writing a new runbook from an incident, from expert notes, or from scratch.
- Reviewing or improving an existing runbook.
- Capturing knowledge before someone leaves, or after an exercise exposed gaps.

Not for: analysing a live incident (`openstack-incident-analysis`) or deciding
whether a change is ready (`openstack-change-review`).

## Workflow

```
Runbook:
- [ ] 1. Purpose, failure mode or operation, and boundaries (what it does NOT cover)
- [ ] 2. Audience: who may execute it, and what needs a specialist
- [ ] 3. Gather knowledge, including the why, history and failed attempts
- [ ] 4. Preconditions and dependencies
- [ ] 5. Decision points where similar symptoms need different handling
- [ ] 6. Steps: read-only vs state-changing, expected result, what to check first if it diverges
- [ ] 7. Stop, escalation and must-not-do
- [ ] 8. Verification of the capability
- [ ] 9. Recovery if the procedure fails
- [ ] 10. Ownership, validation plan, history
```

### 1. Purpose and boundaries

A good runbook says what it covers and where the operator must stop and
escalate; a procedure safe for one failure mode can be unsafe when symptoms
differ slightly [Book: Ch. 11]. Name the failure mode or operation precisely
and list look-alikes it does **not** cover.

### 2. Audience

Routine, well-understood, reversible actions can move toward first-line
operations; complex diagnosis and platform changes stay with specialists. Test
each section: does it require platform expertise or a reliable procedure?
[Book: Ch. 1]. Mark sections by who may execute them and who must authorize
disruptive steps [Book: Ch. 13].

### 3. Gather knowledge

Notes and chat logs often contain passwords or tokens: apply rule 11 of the
safety rules and never carry a secret into the runbook (write `<redacted>` or
point to the secret store).

Ask for, or extract from the material provided:
- the reason behind each step and each unusual configuration — otherwise a new
  operator cannot tell a mistake to correct from a constraint to respect
  [Book: Ch. 11];
- order constraints and the precautions experienced engineers apply without
  thinking [Book: Ch. 11];
- historical decisions and why exceptions exist (link decision records)
  [Book: Ch. 11, Ch. 13];
- workarounds that were tried and did not work [Book: Ch. 11].

Where the material is silent, mark the gap (`TODO: confirm with <owner>`); do
not fill it with plausible commands or values.

### 4. Preconditions and dependencies

State the starting state the procedure assumes, the dependencies that must be
healthy, required access, and evidence to preserve before starting
[Book: Ch. 10, Ch. 11].

### 5. Decision points

Documentation should include decision points, not merely commands
[Book: Ch. 11]. Where one alert can mean different situations, branch
explicitly with the discriminating check. The book's example: a RabbitMQ node
that left the cluster vs a partitioned cluster raise the same alert; the first
is "confirm majority, rejoin or reset the one node, watch consumers
reconnect"; the second is "do not touch the nodes yet, establish which side the
services use, decide whether to stop the APIs, escalate before any reset"
[Book: Ch. 11]. Even in the first case a reset wipes that node's data, so the
runbook must say what it loses and the steps that go with it `[Addition]`.
See the template in
[references/runbook-template.md](references/runbook-template.md).

### 6. Steps

For each step: what to do, why, `read-only` or `state-changing`, expected
result, and what to look at first if the result differs [Book: Ch. 11]. One
state-changing action per step, followed by its check. Commands must come from
the source material or be clearly marked as examples to verify for the
platform.

### 7. Stop, escalation and must-not-do

List concrete stop conditions (unexpected dependency behaviour, blast radius
beyond scope, monitoring blind, recovery no longer credible, decision
authority unavailable) [Book: Ch. 19], what evidence to collect before
escalating [Book: Ch. 1], whom to escalate to, and the actions operators must
**not** take without escalation, especially destructive ones [Book: Ch. 11].

### 8. Verification

Verify the capability end to end, not process state — e.g. for provisioning,
create, reach and delete a test VM [Book: Ch. 10, Ch. 9].

### 9. Recovery

How to return to a trusted state if the procedure fails half-way
[Book: Ch. 10, App. C], and the point after which that is no longer possible
(point of no return) `[Addition]`.

### 10. Ownership, validation, history

Every significant document needs an owner, a last-validation date and a
history [Book: Ch. 11]. Add a validation plan: someone who did not write it
executes it — in a non-production environment or during real maintenance —
while observed but not helped, and the document is corrected from their
questions [Book: Ch. 11, Ch. 12]. See
[references/validation-and-exercises.md](references/validation-and-exercises.md).
Until that has happened, mark the runbook **Draft — not yet validated**.

## Output format

Produce the runbook using
[references/runbook-template.md](references/runbook-template.md), followed by:

```markdown
## Author notes
- Sources used (incident, notes, existing doc) and what was inferred
- Gaps marked TODO and who can close them
- Validation plan (who, where, when)
```

When reviewing an existing runbook, output a findings table (section,
problem, why it matters, suggested fix) before any rewritten version. End with
the decision-support line from
[references/evidence-and-safety.md](references/evidence-and-safety.md) if the
runbook contains state-changing steps.

## Limits and safety

- A generated runbook is a draft until validated by a non-author; the skill
  never labels its own output as validated or approved.
- It does not invent hostnames, versions, thresholds or command output;
  missing facts become TODOs.
- Release- and tool-specific commands must be verified for the platform's
  versions and deployment tool.
- Destructive steps are always gated by a named approver and preceded by a
  stop/escalation check.
- Avoid documentation theatre: prefer one accurate, owned procedure to many
  unvalidated pages [Book: Ch. 11].

## Related skills

- `openstack-incident-analysis` — source material from an incident.
- `openstack-change-review` — to review a runbook used for a planned change.
- `openstack-control-assessment` — to find which capabilities lack tested procedures.
