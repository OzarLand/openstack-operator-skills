# Examples: the same question, with and without the skills

Three scenarios from the evaluation, answered by `claude-sonnet-5-5` once
without the skills (baseline) and once with them. The excerpts are the
opening of each answer, shortened only where marked `[…]`. The full answers
and the grader's verdicts are linked under each example.

The baselines are not bad answers. They are what a capable generalist writes.
The difference is in what an experienced operator would insist on: the
decision point, the owner, the way back.

## Contents

- 1. "Turn our incident notes into a runbook"
- 2. "The runbook says reset rabbit-03. Should I just follow it?"
- 3. "One more security backport on an unmaintained series. Fine?"
- How these were produced

## 1. "Turn our incident notes into a runbook"

Scenario RA-1. The notes: VM creation failed, RabbitMQ RPC broken, Galera
unhealthy; the team stopped the APIs, purged the queues, restarted RabbitMQ
then MariaDB, verified, reopened. Root cause found later: a RabbitMQ network
partition.

**Without the skills** (score 0.29, one critical error):

> **Order matters:** stop the APIs, fix RabbitMQ, fix MariaDB, verify, then
> reopen.
>
> 1. **Stop new API traffic.** Pull the API backends out of HAProxy, then
>    stop the API services […]
> 2. **Purge** […]

The grader: *"the incident sequence becomes an unconditional procedure. It
has no partition vs node-loss or quorum decision points, no authorized gate
on stopping the APIs or purging queues, no statement of the in-flight loss,
no must-not-do list, and no owner, validation plan or draft status."*

**With `openstack-runbook-authoring`** (score 1.00):

> **Status:** Draft, not yet validated by anyone other than the author.
> **Owner:** TODO (name a role). **Last validation:** never.
>
> **Does NOT cover:**
> - One RabbitMQ node missing while the rest form a majority with no
>   partition. That needs a lighter rejoin procedure […]
> - Existing VMs also failing. Stop and escalate.
>
> - **Purging queues discards in-flight messages.** […] Treat the purge as
>   destructive.
> - **The incident acted first and found the cause later.** This runbook
>   puts the partition check first.
>
> **Sections 2–4** change state. They need a named approver who can accept
> a provisioning outage.

Full answers:
[baseline](../evals/results/final-openstack-runbook-authoring/RA-1.baseline.md),
[with skill](../evals/results/final-openstack-runbook-authoring/RA-1.skill.md).

## 2. "The runbook says reset rabbit-03. Should I just follow it?"

Scenario IA-4. `rabbitmqctl cluster_status` on rabbit-01 shows only rabbit-01
and rabbit-02 running. The runbook says: stop_app on rabbit-03, reset,
join_cluster, start_app.

**Without the skills** (score 0.42):

> Not yet. The runbook's `reset` is the risky step, because it wipes
> rabbit-03's local state […]
>
> - If the node is simply stopped or crashed, **start it** […]

Sensible checks, but mostly assumes the node crashed. The grader noted it
never says the same alert can mean a partition, never asks for the view from
every node, and names no escalation path for the partition case.

**With `openstack-incident-analysis`** (score 1.00):

> Not yet. […] The alert doesn't tell you whether rabbit-03 left the cluster
> or the cluster is partitioned, and the runbook is only safe for the first
> case.
>
> | Hypothesis | Would disprove | Check |
> |---|---|---|
> | A: rabbit-03 is down or stopped […] | Process is running and clients are connected to it | Host and process state on rabbit-03 |
> | B: Network partition, with rabbit-03 alive on its own side | rabbit-03 reports that it is stopped or can't reach anyone | `cluster_status` run on rabbit-03 itself |
>
> **Next diagnostics (all read-only)**
> 1. Run `rabbitmqctl cluster_status` on **each** of the three nodes […]

Full answers:
[baseline](../evals/results/final-openstack-incident-analysis/IA-4.baseline.md),
[with skill](../evals/results/final-openstack-incident-analysis/IA-4.skill.md).

## 3. "One more security backport on an unmaintained series. Fine?"

Scenario OD-2. A new OSSA hits Neutron on a series upstream no longer
maintains; the team already carries six local security backports.

**Without the skills** (score 0.40, one critical error):

> Yes, backporting is a reasonable call. A small, self-contained security
> patch is the usual way to handle an unmaintained series, and doing it for
> the seventh time doesn't change that.

The grader: *approves the backport without owner, test or exit condition.*

**With `openstack-operational-decisions`** (score 0.90):

> **Short answer:** backporting this one is a reasonable tactical move, if
> you treat it as a stopgap. Seven local security backports on an
> unmaintained series is a lifecycle problem that no single patch fixes.
>
> - **Small does not mean cheap to carry.** […] you now own the patch.
>
> **Conditions before you proceed.** Each of these is a gate […]
> 1. **Record it.** For each backport, note the upstream change, the OSSA,
>    the owner, how you tested it, and the exit condition.

Full answers:
[baseline](../evals/results/final-openstack-operational-decisions/OD-2.baseline.md),
[with skill](../evals/results/final-openstack-operational-decisions/OD-2.skill.md).

## How these were produced

Run `final-*` of the evaluation (single prompt, no tools, no access to any
infrastructure). These three were picked because they show the clearest
difference; across all 24 scenarios the mean score was 0.97 with the skills
and 0.68 without. Method, every result and the limits are in
[evaluation-report.md](evaluation-report.md).
