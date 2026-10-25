---
name: openstack-control-assessment
description: Assesses how much control an organization actually has over its OpenStack platform, capability by capability - business consequence chain, dependency walk, control level from Unknown to Sustainable with evidence and confidence, single-expert and recovery gaps - and turns findings into act-now, plan, monitor or accept decisions, measures and, when control is already lost, a restoration plan. Use when someone inherits or audits an OpenStack platform, prepares a periodic control review, faces a key engineer leaving or a team change, or says the platform feels out of control - even if they only ask where to start with an unfamiliar or fragile OpenStack cloud.
license: Apache-2.0
metadata:
  source: "OpenStack, the Day After Tomorrow (Soufian Zaouam), v1.2 - Ch. 2, 5, 6, 7, 12, App. B, App. D"
  version: "0.1.0"
---

# OpenStack control assessment

Establish, with evidence, where the organization stands so that decisions can
be made — not to produce a maturity score. The book's question: *do you still
control your OpenStack platform?* Control means the organization can
understand, decide, intervene, recover and evolve without depending on
individuals, undocumented assumptions or uncontrolled complexity
[Book: Intro, Ch. 2].

Read [references/evidence-and-safety.md](references/evidence-and-safety.md)
before the first response; its rules are mandatory. Principles:
[references/operating-principles.md](references/operating-principles.md).

## When to use

Pick the mode that matches the request:

| Mode | Trigger | Main reference |
|---|---|---|
| Baseline assessment | inherited platform, audit, "where do we stand?" | [references/control-spectrum.md](references/control-spectrum.md) |
| Periodic control review | monthly/quarterly review, before a lifecycle event | [references/review-and-measures.md](references/review-and-measures.md) |
| Organizational change review | engineer leaving, team shrinking, reorganization, vendor exit | [references/review-and-measures.md](references/review-and-measures.md) |
| Restoration plan | "control is already lost", chronic instability, defensive habits | [references/restoration-playbook.md](references/restoration-playbook.md) |

Not for: a single incident (`openstack-incident-analysis`) or choosing between
options once gaps are known (`openstack-operational-decisions`).

## Workflow

```
Control assessment:
- [ ] 1. Purpose, mode and scope (which business capabilities matter most)
- [ ] 2. Consequence chain for each critical capability
- [ ] 3. Dependency walk of one real user journey
- [ ] 4. Control level per capability, with evidence and confidence
- [ ] 5. Confidence tests to propose
- [ ] 6. Gaps where low control meets high consequence
- [ ] 7. Each finding -> act now / plan / monitor / consciously accept
- [ ] 8. Measures with owners and trends
- [ ] 9. (If control is lost) restoration sequence, guardrails, exit criteria
```

### 1. Purpose, mode and scope

Start from what the business depends on, not the component list
[Book: Ch. 5]. Ask which business capabilities rely on the platform and how
critical each is; a complex component behind a non-critical capability may
matter less than a simple dependency behind a critical one. If criticality is
unknown, that is the first finding.

### 2. Consequence chain

For each critical capability, trace [Book: Ch. 5]:

**Business capability → OpenStack capability → Platform service → Technical
dependency → Team → Expertise → Recovery capability**

Assess capabilities (can workloads be scheduled, created, migrated, resized,
recovered? can tenant connectivity be understood and restored? can volumes be
operated and recovered? can auth failures be diagnosed safely?), using the
component inventory only as evidence [Book: Ch. 5].

### 3. Dependency walk

Walk one representative journey (usually VM creation) through every
dependency; at each step ask where the signal is, who owns it, how a failure
is detected and recovered, and which business capability is affected. Gaps
usually appear at team boundaries [Book: Ch. 5].

### 4. Control level

Rate each capability on the spectrum **Unknown → Visible → Understood →
Controlled → Recoverable → Sustainable** using the criteria in
[references/control-spectrum.md](references/control-spectrum.md). Rules:

- A level needs evidence; "we think so" means the level is not established
  [Book: App. B].
- Attach a confidence to each piece of evidence. The book compares pairs
  (observed in production beats documented-but-never-exercised; demonstrated
  beats untested; independently reproduced beats one expert's statement) and
  says the exact scale matters less than making confidence visible
  [Book: Ch. 5]; a single ordering is in the reference as an `[Addition]`.
- Treat maturity as a profile, not a grade: report per capability and per
  capability area (visibility, stability, organization, governance), never one
  combined score [Book: Ch. 2, Ch. 6].
- Recoverable requires recovery demonstrated **by someone other than the
  procedure's author** within a time the business accepts [Book: Ch. 5].

### 5. Confidence tests

Familiar systems feel understood. Propose tests rather than accept
self-assessment [Book: Ch. 5, Ch. 12]: rehearse "a user cannot create a VM —
who receives it, what evidence is collected, who investigates Placement or
Neutron, who may restrict an API, who talks to the consumer?" and see whether
answers depend on who is available [Book: Ch. 1]; ask someone who did not
design the platform to explain a critical dependency; have an engineer walk through a
recovery without performing it; ask an owner what happens if the primary
expert is unavailable next week; have a new engineer execute a real procedure
alone while observed [Book: Ch. 11].

### 6. Gaps

Concentrate where low control intersects high consequence [Book: Ch. 2].
Look specifically for [Book: Ch. 5, Ch. 3]: unclear ownership; recovery that
depends on one person; poorly observed critical dependencies; changes that
cannot be reversed; drift from upstream and local patches; overloaded teams;
control debt (knowledge held by one person, undocumented and essential to
recovery); vendor-only knowledge [Book: Ch. 2, Ch. 14]; visibility that only
works when things are healthy, critical signals without owners, or dependencies
visible only inside another team's monitoring [Book: Ch. 8]; and team
overload, which feeds the loop insufficient capacity → concentrated expertise →
increased dependency → more pressure → even less capacity for improvement
[Book: Ch. 12]. For an organizational change, review each critical capability
against the remaining team (who can operate, diagnose, recover, upgrade,
decide) [Book: Ch. 12].

### 7. Findings to decisions

Every significant finding gets one outcome [Book: Ch. 5]: **act now**,
**plan**, **monitor**, or **consciously accept** — with an owner, and for
accepted risks a review condition (acceptance expires) [Book: Ch. 13]. Keep
the assessment from becoming a permanent audit or control theatre: its purpose
is a credible baseline from which to act [Book: Ch. 5].

### 8. Measures

Propose a few measures per capability area with an owner and a trend, not a
target score [Book: Ch. 6]; prefer leading indicators (capabilities with one
knowledgeable engineer, recovery procedures not exercised recently) and
measures the platform can produce itself. See
[references/review-and-measures.md](references/review-and-measures.md).

### 9. Restoration (only if control is lost)

Do not start by transforming the platform. Follow Discover → Protect → Assess
→ Stabilize → Recover Knowledge → Simplify → Establish Control → Evolve, with
temporary guardrails that each have an owner and a removal condition, and an
explicit definition of "control restored" [Book: Ch. 7]. Details in
[references/restoration-playbook.md](references/restoration-playbook.md).

## Output format

The book's practical outputs [Book: Ch. 5]:

```markdown
## Scope and method
Mode · capabilities assessed · sources of evidence · what was not assessed

## Current control state
| Capability | Criticality | Level | Key evidence (confidence) | Main gap |

## Critical risks (low control x high consequence)
## Control gaps
By area: visibility · stability · organization · governance · recovery · upstream alignment
## Findings and decisions
| Finding | Outcome (act now / plan / monitor / accept) | Owner | Review condition |
## Immediate actions
## Structural problems
## Proposed confidence tests
## Measures
| Measure | Area | Owner | How produced | Trend to watch |
## Control roadmap
(Restoration mode: sequence stage, guardrails with removal conditions, "control restored" criteria)
## Gaps in this assessment
```

End with the decision-support line from
[references/evidence-and-safety.md](references/evidence-and-safety.md) if any
action is state-changing.

## Limits and safety

- The skill rates only what evidence supports; with little evidence the honest
  result is many capabilities at Unknown or Visible, and that is a useful
  finding, not a failure of the assessment.
- It never infers team composition, recovery history or ownership; it asks or
  records the gap.
- It produces no single maturity score [Book: Ch. 6].
- Organizational findings (single-expert dependency, overload) concern
  capability, not individual performance; phrase them that way.
- It does not run discovery against live systems unless tools in the session
  provide that access; otherwise it lists the read-only data to collect.

## Related skills

- `openstack-operational-decisions` — to choose how to close a significant gap.
- `openstack-runbook-authoring` — to turn recovered knowledge into tested procedures.
- `openstack-change-review` — for changes proposed during restoration.
