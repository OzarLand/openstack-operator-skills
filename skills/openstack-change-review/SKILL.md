---
name: openstack-change-review
description: Reviews a planned change to a production OpenStack platform for readiness - objective, starting state, blast radius, decision gates, prerequisites, rollback or recovery feasibility, stop conditions, verification, decision rights - and produces a verdict plus a minimum change decision record. Use when someone asks to review, approve or sanity-check an OpenStack change, upgrade step, configuration change, certificate or Fernet key rotation, network or database intervention, CAB or change request, or rollback plan - even if they only want a quick sanity check before running something in production.
license: Apache-2.0
metadata:
  source: "OpenStack, the Day After Tomorrow (Soufian Zaouam), v1.2 - Ch. 1, 9, 13, 14, 17, 19, App. A, App. C"
  version: "0.1.0"
---

# OpenStack change review

Decide whether a proposed change is ready to execute, and if not, what must
become true first. The book's test: before changing a mission-critical
OpenStack platform, understand enough to know what you are risking, how you
will detect failure and how you will recover if you are wrong [Book: Ch. 9].

Read [references/evidence-and-safety.md](references/evidence-and-safety.md)
before the first response; its rules are mandatory. Principles:
[references/operating-principles.md](references/operating-principles.md).

## When to use

- Reviewing a change plan, change request or runbook for a production change.
- Checking an upgrade step, a rotation (TLS, Fernet), a config or network change,
  a database intervention, or a rollback plan.
- Preparing the decision record for a significant change.

Not for: choosing *between* strategic options such as upgrade vs backport
(`openstack-operational-decisions`), building a host patching campaign
(`openstack-maintenance-planning`), reviewing automation code
(`openstack-automation-review`), or a change during a live incident
(`openstack-incident-analysis`).

## Proportionality

A routine, reversible, well-rehearsed operation needs a short review. The
review grows with blast radius, irreversibility, uncertainty and business
criticality [Book: Ch. 9, App. C]. Say which depth you chose and why.

## Workflow

```
Change review:
- [ ] 1. Objective: the problem the change solves, in business/operational terms
- [ ] 2. Starting state: is it known and trusted? Is the platform stable now?
- [ ] 3. Scope and blast radius: services, dependencies, failure domains, consumers
- [ ] 4. Decision gates (any failure = not ready)
- [ ] 5. Prerequisites and readiness
- [ ] 6. Recovery: rollback / roll-forward path, known-good state, point of no return
- [ ] 7. Execution boundaries and stop conditions
- [ ] 8. Verification designed before execution
- [ ] 9. Decision rights and communication
- [ ] 10. Verdict and decision record
```

### 1. Objective

Translate the request back into the problem it solves — "upgrade this",
"change this network" is not a diagnosis [Book: Ch. 9]. Answer the four
questions for any proposed change [Book: Ch. 1]: what capability does it
create or protect; what existing capability could it affect; what operational
burden does it add; what will be required to operate it after the delivery
team has moved on. If the objective is unclear, stop here and ask.

### 2. Starting state

What state does the change start from, and what evidence shows it is trusted
(not just "green")? [Book: Ch. 1, Ch. 9]. If the platform is currently
unstable or under incident, adding change stacks uncertainty — recommend
stabilizing first, unless the change *is* the stabilization (e.g. a platform
so far behind that waiting is the larger risk) [Book: Ch. 7, Ch. 9]. Flag other
changes scheduled in the same window: do not stack uncertainty [Book: Ch. 9].

### 3. Scope and blast radius

OpenStack changes cross service boundaries: a change "local to Nova" can
reach Placement, Neutron, the bus, the database, hypervisors and consumers'
workflows; a TLS change touches control-plane services and agents on every
compute node [Book: Ch. 1, Ch. 9]. List what is touched, the failure domain,
the workloads and consumers affected, and what a failure would reach. Cost is
blast radius, uncertainty, recoverability, dependencies, criticality and
available capacity — not the number of commands [Book: Ch. 1].

### 4. Decision gates

Before weighing anything else, check the gates [Book: App. A, Ch. 18]. Any
missing gate means "not ready — improve the condition first":

| Gate | Question |
|---|---|
| Business impact | Is the impact, including the failure case, acceptable to the accountable owner? |
| Recovery | Is there a credible path back to a trusted state (or forward), proportionate to the consequence? |
| Evidence | Is there enough technical evidence that the change does what is claimed (tested where it can be)? |
| Owner | Does the affected capability have a defined owner? |
| Authority | Is the person approving entitled to accept this consequence? |
| Blast radius | Is it bounded (batches, scope limits, failure domain)? |
| Mandatory requirements | Does it avoid violating security or regulatory requirements? |

### 5. Prerequisites and readiness

Check what must be true before starting: tested in a representative
environment, backups taken *and restorable*, monitoring able to see the
affected capability, capacity for the change (migration headroom, window
length, people), runbook with decision points, consumers informed, dependent
teams available. For upgrades and policy changes use
[references/upgrade-readiness.md](references/upgrade-readiness.md); for
rotations, network, database and configuration changes use
[references/change-type-notes.md](references/change-type-notes.md).

### 6. Recovery

"We have rollback" must mean a credible path and a known-good state to return
to [Book: Ch. 5]. Identify:
- the rollback or roll-forward method and whether it has been exercised;
- the **point of no return** `[Addition]` (e.g. completed schema migrations,
  a contract phase, deleted data, rotated keys already removed) and what
  recovery means after it;
- evidence to preserve before starting.

If no credible recovery exists, the change fails the recovery gate: the book's
answer is to improve the condition before going further, not to score around
it [Book: App. A, Ch. 18]. Describe what proceeding would mean so the
accountable owner understands it, but keep the verdict at not ready.

### 7. Execution boundaries and stop conditions

Define boundaries before execution — capacity limits, migration rates, scope
per batch, API restrictions [Book: Ch. 9] — and concrete stop conditions
[Book: Ch. 19]:

- an expected dependency behaves differently;
- the blast radius exceeds the approved boundary;
- monitoring is insufficient to see the effect;
- recovery is no longer credible;
- critical workload performance crosses an agreed threshold;
- required capacity is unavailable;
- the decision authority is not available.

Time already invested creates no obligation to continue; resuming after a stop
is a new decision [Book: Ch. 19].

### 8. Verification

Design verification before execution [Book: Ch. 9]: the evidence that the
objective was achieved (capability end to end, not command success), that
dependencies stayed healthy, and that nothing new broke. Define an observation
period: the new state earns trust and does not inherit the previous state's
stability assumptions [Book: Ch. 9, Ch. 14].

### 9. Decision rights and communication

Name four roles: who provides the technical assessment, who owns the affected
capability, who is accountable for the outcome, who decides [Book: Ch. 13].
Technical teams assess technical risk; authorized owners accept business risk.
Name who tells consumers what to expect (e.g. suspended resource creation)
[Book: Ch. 9].

### 10. Verdict and record

Give one verdict:

- **Ready** — gates pass, recovery credible, verification and stop conditions defined.
- **Ready with conditions** — list each condition and who confirms it.
- **Not ready** — list failed gates or missing prerequisites and what would close them.
- **Reconsider** — the objective is better served another way, or the timing is
  wrong (e.g. recovery or capacity insufficient this month). This is
  sequencing, not resistance [Book: Ch. 9].

Then fill the minimum change decision record from
[references/change-record-template.md](references/change-record-template.md),
proportional to consequence [Book: App. C]. Rejected options and their reasons
belong in the record [Book: Ch. 13].

## Output format

```markdown
## Summary
Verdict · review depth and why · top 3 risks

## Objective and four questions
## Starting state
## Scope and blast radius
## Decision gates
| Gate | Status (pass / fail / unknown) | Evidence or gap |
## Prerequisites
| Prerequisite | Status | Owner |
## Recovery
Method · exercised? · point of no return · evidence to preserve
## Execution boundaries and stop conditions
## Verification
## Decision rights
Assessor · capability owner · accountable · decision maker · consumer communication
## Gaps and questions
## Decision record (draft)
```

Mark every gate or prerequisite that depends on information not provided as
`unknown`, never `pass`. End with the decision-support line from
[references/evidence-and-safety.md](references/evidence-and-safety.md).

## Limits and safety

- The review is decision support, not an approval. It never states or implies
  that a change is authorized.
- It only knows the plan and evidence supplied; it cannot verify test results,
  backups or capacity unless shown evidence, and reports them as `unknown`.
- Release-specific mechanics in the references (upgrade checks, SLURP rules,
  RBAC defaults) are summarized from the book (v1.2, 2026) and change between
  releases and distributions; verify against current upstream or vendor docs.
- It does not set universal thresholds (batch sizes, migration rates,
  observation periods). It asks for the platform's own baselines and capacity.
- The skill must not soften a failed gate because of schedule pressure; it may
  describe what the accountable owner would be accepting.

## Related skills

- `openstack-operational-decisions` — when the real question is which option to take.
- `openstack-maintenance-planning` — when the change is a host maintenance or patching campaign.
- `openstack-runbook-authoring` — to turn the approved plan into an executable runbook.
- `openstack-automation-review` — when the change is executed by automation.
