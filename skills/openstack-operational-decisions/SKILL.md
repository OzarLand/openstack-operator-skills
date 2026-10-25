---
name: openstack-operational-decisions
description: Structures significant OpenStack lifecycle and operational decisions with competing options - upgrade now vs progressive vs postpone, local backport vs upgrade, keep or remove technical debt or a workaround, repair vs rebuild, security exceptions, automate or not, vendor dependence - using decision gates, explicit trade-offs, an optional weighted scoring model with sensitivity analysis, decision rights, and exit conditions. Use when an engineer or manager must choose between options, justify a decision, or tell technically correct from operationally suitable on an OpenStack platform - including any 'should we...' question about upgrading, patching strategy, carrying a patch, keeping a workaround or rebuilding.
license: Apache-2.0
metadata:
  source: "OpenStack, the Day After Tomorrow (Soufian Zaouam), v1.2 - App. A, Ch. 18, 14, 15, 10, 13, 16, 17"
  version: "0.1.0"
---

# OpenStack operational decisions

Make a significant decision explicit: what is being protected, what is known,
which options survive the non-negotiable gates, what each option costs in
risk, complexity and future control, and who decides. The book's framing:
good decisions are not decisions without uncertainty; they are decisions in
which uncertainty, consequence and accountability are made visible
[Book: App. A].

Read [references/evidence-and-safety.md](references/evidence-and-safety.md)
before the first response; its rules are mandatory. Principles:
[references/operating-principles.md](references/operating-principles.md).

## When to use

- Strategic or structural choices with several credible options: upgrade
  strategy, backport vs upgrade, keep/reduce/remove debt, retain or end a
  workaround, repair vs rebuild an environment, accept a security exception,
  automate or keep manual, reduce vendor dependence, sequence an evolution
  roadmap.
- "Is this technically right *and* operationally suitable for us now?"
- Writing the justification for a decision already taken.

Not for: readiness of one concrete change (`openstack-change-review`), live
incidents (`openstack-incident-analysis`), or reviewing automation code
(`openstack-automation-review`).

## Proportionality

The structure should become lighter for routine decisions and more explicit
as consequence grows [Book: App. A]. A reversible, low-impact choice needs a
paragraph; a decision affecting the control plane, upgrade path or critical
workloads needs the full workflow.

## Workflow

```
Decision:
- [ ] 1. Situation and business objective
- [ ] 2. Evidence (with confidence) and uncertainty
- [ ] 3. Constraints
- [ ] 4. Options, including "keep as is" — and the risk of staying
- [ ] 5. Gates: reject options that fail any gate
- [ ] 6. Trade-offs per surviving option
- [ ] 7. Weighted comparison (optional) and sensitivity
- [ ] 8. Decision rights
- [ ] 9. Controlled action, owner, review trigger, exit condition
- [ ] 10. Verification of the expected benefit, and learning
```

### 1. Situation and business objective

What is happening, and what are we trying to protect, restore or improve?
[Book: App. A]. Translate requests back into the problem ("upgrade",
"automate", "rebuild" are solutions) [Book: Ch. 9].

### 2. Evidence and uncertainty

Separate what is known from what is believed, and give each piece of
evidence a confidence level: observed in production, demonstrated in a test
environment, documented but never exercised, or one expert's statement
[Book: Ch. 5]. List what remains unproven. Organizational facts — who can
recover it, who wrote the patch, whether that person is still here — are
evidence too [Book: Ch. 3, Ch. 18].

### 3. Constraints

Change capacity (people, windows, migration headroom), maintenance status of
the running series, vendor support timeline, security deadlines, team
changes [Book: Ch. 1, Ch. 14, Ch. 20].

### 4. Options

List realistic options, always including keeping the current state. For each,
state the risk of changing **and** the risk of staying [Book: App. E]. Use the
decision-type playbooks in
[references/decision-playbooks.md](references/decision-playbooks.md) for
upgrade/backport, debt, workarounds, repair vs rebuild, security exceptions,
automation and vendor dependence.

### 5. Gates

Reject, before any scoring, an option that [Book: App. A, Ch. 18]:
- has an unacceptable business impact;
- has no credible recovery path for its consequence;
- lacks sufficient technical evidence;
- has no defined owner;
- has no appropriate decision authority;
- has an unbounded blast radius;
- violates a mandatory security or regulatory requirement;
- depends on expertise the organization cannot provide or obtain.

If a gate fails because a condition is missing (e.g. untested backport, no
recovery demonstration), the first recommended action may be to create that
condition rather than to choose [Book: App. A].

### 6. Trade-offs

For each surviving option: what control it gains now, what control debt it
creates later [Book: Ch. 14]; complexity introduced and who will operate it
[Book: Ch. 3, Ch. 15]; distance from upstream; capacity consumed; effect on
the *next* transition — prefer options that leave the organization more able
to perform the next change [Book: Ch. 1, Ch. 18]. Do not stack uncertainty
[Book: Ch. 9]. For an evolution or new capability, a target architecture is
incomplete without a **target operating state**: who will monitor, support,
recover, upgrade and own it — and could the organization operate the result
without the people who built it? [Book: Ch. 18, Ch. 1]. For multi-step
roadmaps, use the book's horizons (current state, control, lifecycle, future)
as dependencies between capabilities rather than dates [Book: Ch. 18].
For workarounds, apply the book's test explicitly: a workaround is safe only
while the risk it introduces remains smaller than the risk it removes
[Book: Ch. 15].

### 7. Weighted comparison (optional)

When two or more options survive the gates and the trade-offs are not
obvious, apply the weighted model in
[references/weighted-model.md](references/weighted-model.md): six dimensions,
illustrative weights, scores 1–5 with 5 always preferable, each score justified
by evidence. Optionally compute scores and sensitivity with
`scripts/weighted_score.py` (see the reference file). The model is a
conversation tool: report which scores rest on the weakest evidence, which
single change would flip the ranking, and what action would reduce that
uncertainty first. It never overrides a gate [Book: Ch. 18, App. A].

### 8. Decision rights

Who provides the technical assessment, who owns the capability, who is
accountable for the outcome, who decides [Book: Ch. 13]. Technical teams
assess technical risk; authorized owners accept business risk. Everyone can
challenge; someone must decide. If competent people disagree, show where
(e.g. different transition-risk scores) rather than averaging it away
[Book: App. A, Concl.].

### 9. Controlled action and exit conditions

Every retained deviation — backport, workaround, debt, guardrail, security
exception — needs an owner, a reason, a review trigger and an exit condition
[Book: Ch. 7, Ch. 14, Ch. 15, Ch. 17]. Risk acceptance expires: state the
event or date that reopens the decision [Book: Ch. 13]. Without an answer to
"what would make us remove it?", retained debt becomes forgotten debt
[Book: Ch. 15].

### 10. Verification and learning

State how the organization will know the expected benefit occurred (upgrade
easier, recovery faster, onboarding simpler, incidents fewer) and when it will
check [Book: Ch. 6, Ch. 15]. Name reassessment points (after a recovery
exercise, a major release, removal of a customization) [Book: Ch. 18]. If a
planned change has to move because readiness is not there, that is the plan
becoming more accurate, not a failure [Book: Ch. 18].

## Output format

```markdown
## Decision to make
Situation · objective · decision owner (or "unknown")

## Evidence and uncertainty
| Fact / belief | Confidence | Source |

## Constraints
## Options
| Option | Risk of doing it | Risk of not doing it |
## Gates
| Option | Failed gate (if any) | What would satisfy it |
## Trade-offs (surviving options)
## Weighted comparison (if used)
Table · justification per score · sensitivity: what flips the ranking
## Recommendation
Recommended option or first action, with conditions · what is being accepted
## Decision rights
## Owner, review trigger, exit condition
## How we will know it worked
## Decision record (draft, App. C fields)
```

Present the recommendation as the analysis's conclusion for the decision
owner, not as a decision. End with the decision-support line from
[references/evidence-and-safety.md](references/evidence-and-safety.md).

## Limits and safety

- Weights and scores are illustrative and contextual; the skill never presents
  the weighted score as an objective answer or lets it override a gate.
- It does not invent the platform's release, patch count, team size or
  recovery history; missing facts become gaps or explicit assumptions.
- Lifecycle facts (maintenance status, SLURP path, vendor support) change over
  time; it tells the user to check releases.openstack.org and the vendor.
- Context-dependent decisions are not turned into rules: the same option can be
  right for a test platform and wrong for production [Book: Ch. 10].
- It does not authorize execution; follow-on changes go through
  `openstack-change-review`.

## Related skills

- `openstack-change-review` — once an option is chosen, review its execution.
- `openstack-control-assessment` — when the decision needs a baseline of what the organization actually controls.
- `openstack-automation-review` — when the option involves automation code.
