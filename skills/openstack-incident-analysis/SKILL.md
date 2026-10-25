---
name: openstack-incident-analysis
description: Investigates OpenStack production incidents and alerts through evidence collection, dependency analysis, competing hypotheses, read-only diagnostics, protect-or-stop decisions and pre-defined verification, before any corrective action. Use whenever an engineer is dealing with a live, recent or recurring OpenStack problem - VMs stuck in BUILD or ERROR, failed provisioning, API errors or timeouts, RabbitMQ or Galera alerts, partitions or quorum loss, compute hosts down, evacuation, dead network agents, authentication failures, recurring symptoms such as CPU steal - including when they ask whether to restart, reset, purge, bootstrap, evacuate or follow a runbook step, even if the question sounds simple. Also use for post-incident root cause analysis.
license: Apache-2.0
metadata:
  source: "OpenStack, the Day After Tomorrow (Soufian Zaouam), v1.2 - Ch. 4, 5, 8, 9, 10, 19, App. E"
  version: "0.1.0"
---

# OpenStack incident analysis

Help an operator move from a symptom to a verified, owned decision without
making the platform harder to recover. The method follows the book's control
loop — Observe, Understand, Prioritize, Decide, Act, Verify, Learn
[Book: Ch. 4] — and its rule that in complex OpenStack environments
investigation *is* the work [Book: Ch. 9].

Read [references/evidence-and-safety.md](references/evidence-and-safety.md)
before the first response; its rules are mandatory. The book's principles are
summarized in [references/operating-principles.md](references/operating-principles.md).

## When to use

- A live incident or degradation on an OpenStack platform (any symptom).
- A post-incident analysis or RCA draft.
- A "should we evacuate / restart / purge / bootstrap?" question during an incident.

Not for: planned changes (use `openstack-change-review`), maintenance campaigns
(`openstack-maintenance-planning`), or writing the resulting procedure
(`openstack-runbook-authoring`).

## Proportionality

A single, well-understood symptom with a documented fix needs a short answer:
evidence, the check, the fix, its verification. Use the full workflow when the
cause is unclear, several services are involved, the control plane's shared
components (message bus, database, load balancer, memcached) are implicated,
or the proposed action is disruptive [Book: Ch. 4]. Never skip the safety
rules, whatever the size of the answer.

## Workflow

Copy this checklist into the response and work through it:

```
Incident analysis:
- [ ] 1. Frame: capability lost, what still works, impact, timeline, what changed
- [ ] 2. Evidence ledger: Observed / Reported / Hypothesis / Assumption
- [ ] 3. Dependency path of the affected capability
- [ ] 4. Competing hypotheses, each with a disproving check
- [ ] 5. Read-only diagnostic plan, ordered by value and safety
- [ ] 6. Protect decision: is continuing making the state worse?
- [ ] 7. Corrective options with prerequisites, blast radius, stop, recovery, owner
- [ ] 8. Verification criteria before declaring recovery / reopening
- [ ] 9. Learning: cause, containment vs structural fix, what changes
```

### 1. Frame the situation

- State the **capability** that is lost or degraded (provisioning, tenant
  connectivity, volume attach, authentication, migration), not the alarm.
- State what **still works**. The control plane and data plane fail
  separately: running instances usually keep running while the APIs, bus or
  database are degraded, but new state does not propagate [Book: Ch. 1].
  Whether existing workloads are affected changes everything downstream.
- **Business impact**: which consumers, how critical, what happens if it gets
  worse. If unknown, say so and ask; do not guess criticality [Book: Ch. 8, Ch. 20].
- **What changed** recently: deployments, config, host maintenance, certificate
  or key rotation, network changes, upgrades [Book: Ch. 8]. Ask explicitly if
  the user has not said.
- **Timeline**: first signal, who reported it, actions already taken. Actions
  already taken are part of the evidence (a restart can destroy or create symptoms).

### 2. Evidence ledger

When asking for configs or logs, ask for credentials to be redacted; if a
secret appears anyway, never repeat it in the ledger or the answer (rule 11 of
the safety rules).

Record each item with its class and source. Reported user symptoms belong in
the ledger with telemetry — they often appear first [Book: Ch. 8]. Mark
anything the user has not shown as a gap. A running process is not evidence of
a healthy service [Book: Ch. 8].

### 3. Dependency path

Walk the transaction that fails through every service and shared component it
traverses and note, at each step, the signal that would show trouble and who
owns it [Book: Ch. 5, Ch. 8]. For VM creation, networking, and the shared
components, use [references/dependency-map.md](references/dependency-map.md).
Request IDs (`req-...`) let one failed request be followed across services'
logs [Book: Ch. 8]; ask for them.

### 4. Competing hypotheses

List at least two plausible explanations, including at least one outside the
service that raised the alarm (message bus, database, network, storage,
Placement, Keystone, certificates). For each, state what supports it, what
would **disprove** it, and the cheapest read-only check that discriminates
[Book: Ch. 9]. Do not promote a hypothesis to a cause until a check supports it
and the alternatives are weakened. Known patterns, with their discriminating
checks and dangerous moves, are in
[references/failure-patterns.md](references/failure-patterns.md).

### 5. Read-only diagnostic plan

Order checks by (information gained ÷ risk) and put the shared components
first when several services look unhealthy at once. Label every step
`read-only`. If the session cannot run commands, give the commands and ask for
the output; never present expected output as observed. Prefer making the
experiment smaller than the platform: one host, one request, one dependency
[Book: Ch. 9]. Preserve evidence (logs, DB snapshots, queue state) before
anything that would destroy it [Book: Ch. 10, App. E].

### 6. Protect decision

Ask: **is the platform's state getting worse while we investigate?** Signs: an
unstable bus or database while APIs keep accepting writes, growing queues
without consumers, instances accumulating in transitional states, orphaned
allocations appearing [Book: Ch. 19].

Whether the state is degrading is something to **check**, not assume — e.g.
compare the count of instances in BUILD or ERROR now and a few minutes later,
or queue depth over time. Do not state trends or durations the user has not
shown.

If yes, present **controlled degradation** as an option, not an order: e.g.
stop accepting API requests (withdraw endpoints from the load balancer) so
the shared components can be recovered on a platform whose state is no longer
changing [Book: Ch. 1, Ch. 19]. State its cost (which capability becomes
unavailable, for how long, who to tell), what remains protected, what
condition will allow reopening, and **who has authority** to decide it
[Book: Ch. 13, Ch. 19]. If the user has not said who that is, ask. Present a
stop as a protection decision — what is restricted, why continuing is riskier,
what stays protected, what reopens it — because a stop only works where
leadership supports the engineer who makes it; containment is an active
decision, not inactivity [Book: Ch. 19]. Note the cautions: stopping APIs does not stop
conductors, schedulers and agents; reconnect storms follow a bus restart;
restarting some Neutron agents or OVN controllers can interrupt data-plane
traffic [Book: Ch. 1, Ch. 19].

If the business impact of waiting is limited and uncertainty is high,
collecting evidence is safer than changing anything [Book: Ch. 9].

### 7. Corrective options

For each option give: what it fixes and under which hypothesis, prerequisites,
blast radius, expected result, verification, stop conditions, recovery path
(or "none — irreversible"), and the approving role [Book: Ch. 9, Ch. 19,
App. C]. Recovery is itself a change under pressure [Book: Ch. 10]. When
many workloads must be restored or moved, order them by business criticality
and ask their owners for input; the infrastructure cannot infer which
workloads matter most [Book: Ch. 20]. Apply the
hard rules below. When repairs keep creating the next problem, raise
**repair vs rebuild** explicitly (production state usually cannot be discarded;
a test environment often can) [Book: Ch. 10].

### 8. Verification

Define, before any action, the evidence that will show the capability is back
and nothing new is broken [Book: Ch. 9]. Verify the **capability end to end**,
not process health — e.g. for provisioning: cluster health of database and bus,
all compute services and agents reporting, and a test VM created, reached and
deleted [Book: Ch. 10, Ch. 19]. A fix that "worked" is unverified until this
evidence exists.

### 9. Learning

- Separate **containment** (restore service, protect the platform) from
  **structural remediation** (why it happened); do not mix them during the
  incident [Book: Ch. 7].
- The review must reach the actual cause, or the incident returns
  [Book: Ch. 19]. An incident resolved but not understood is a recurring cost
  [Book: Ch. 6].
- Name what should change: monitoring, runbook, architecture, ownership,
  decision rights — or explain why existing controls were sufficient
  [Book: Ch. 4, Ch. 10].
- If the same workaround keeps being applied, say so: repeated recovery is not
  stability [Book: Ch. 9, Ch. 15].

## Hard rules

These follow from the book (the attribution is given on each); do not relax
them without explicit, evidenced reasons from the user.

- **Fence before evacuating.** Never recommend `evacuate` on the strength of a
  missing heartbeat or a "down" service. First confirm the host is really off
  (out-of-band management power state, or switch-level isolation); otherwise two
  copies of the instance can write to the same storage [Book: Ch. 10]. Then
  mark the service forced down before evacuating, and keep the host out of
  service when it returns until `nova-compute` has cleaned up the evacuated
  instances (sequence in failure pattern P3) `[Addition]`.
- **Partition is not node loss.** For RabbitMQ, a node that left the cluster
  and a partitioned cluster raise the same alert and need opposite handling.
  Do not recommend resetting nodes until it is established which side the
  services use; escalate first [Book: Ch. 11].
- **Galera bootstrap is the step to rehearse.** Bootstrapping the wrong node
  discards committed transactions. Require identification of the most advanced
  node (seqno, `safe_to_bootstrap`, `--wsrep-recover`) before any bootstrap
  advice [Book: Ch. 10].
- **Purging queues discards in-flight operations.** It may be the right
  trade-off (Ch. 19 did it deliberately), but state the loss and require a
  decision.
- **Direct database edits** need a backup first, one record at a time, and
  verification after [Book: Ch. 10].
- **Relocating a symptom is not fixing it.** Live-migrating away from a
  problem (e.g. steal time on pinned CPUs) is a workaround; if it recurs, the
  recurrence itself is evidence the cause is still present — stop and
  investigate [Book: Ch. 15].
- **Do not automate an unresolved workaround.** Automating it makes the
  problem happen faster and at scale; recommend finding the cause first. If a
  stop-gap is unavoidable, prefer semi-automation (detect and propose, a human
  decides) with bounded scope and an exit condition [Book: Ch. 16, Ch. 15].
  Hand automation design to `openstack-automation-review`.
- **Keep outcomes attributable.** Do not combine unrelated changes (e.g. a
  config change, an upgrade and a network change) during recovery; that makes
  results impossible to attribute [Book: Ch. 9]. A recovery that needs several
  steps in a row — as in the book's own incident: stop the APIs, recover the
  bus, restart the database, then verify [Book: Ch. 19] — should be decided as
  one planned sequence with its verification defined up front.
- **Familiar fixes are hypotheses.** "What worked last time" must be checked
  against the current evidence [Book: Ch. 9].

## Output format

Use this structure; collapse sections that do not apply rather than padding them.

```markdown
## Situation
Capability affected · what still works · business impact (or "unknown — need X") · what changed · timeline

## Evidence
| # | Class | Statement | Source |
|---|-------|-----------|--------|

## Dependency path
<affected transaction, step by step, with the signal to check at each step>

## Hypotheses
| Hypothesis | Supports | Would disprove | Discriminating check |
|------------|----------|----------------|----------------------|

## Next diagnostics (read-only)
1. <command or check> — what it tells us — expected signal for each hypothesis

## Protect decision
Is the state degrading? Options (continue investigating / controlled degradation / other), cost, what stays protected, reopen condition, decision owner.

## Corrective options (not yet authorized)
For each: purpose · prerequisites · blast radius · expected result · verification · stop conditions · recovery · approver

## Verification before declaring recovery
<end-to-end capability checks>

## Gaps and open questions
<what is unknown, why it matters, how to close it>

## Follow-up
Containment vs structural actions · what should change · owner
```

End with the decision-support line from
[references/evidence-and-safety.md](references/evidence-and-safety.md).
When the user asks for a post-incident RCA, also use the book's grid:
Context → Signal → Uncertainty → Business risk → Options → Decision →
Trade-off → Outcome → Lesson [Book: Ch. 18]. A worked example of the output is
in [references/worked-example.md](references/worked-example.md).

## Limits and safety

- The skill knows only what the user provides or what tools available in the
  session actually return. It never claims to have inspected a system.
- It does not execute or authorize production changes. Disruptive actions
  (stopping APIs, purging queues, resetting or bootstrapping cluster nodes,
  evacuating, deleting resources, editing databases) require a named human
  decision owner [Book: Ch. 13].
- Technical facts in the references are summarized from the book's technical
  notes (v1.2, 2026) plus marked additions; behaviour varies by release,
  deployment tool and backend. Ask for versions and verify against upstream or
  vendor documentation before relying on them.
- It gives no universal thresholds (timeouts, migration rates, queue depths);
  those depend on the platform's baselines [Book: Ch. 8].
- If the user is under time pressure, keep the structure but shorten it; do
  not drop the evidence classes, the protect decision or the verification.

## Related skills

- `openstack-runbook-authoring` — turn the outcome into a procedure with decision points.
- `openstack-change-review` — review the structural fix before it is applied.
- `openstack-operational-decisions` — for repair-vs-rebuild or keep-the-workaround decisions after the incident.
