# Runbook template

Fields follow the book's minimum information model: purpose, scope, context,
dependencies, action or decision, expected result, stop and escalation
conditions, recovery, owner, last validation date, history [Book: Ch. 11].
The exact format can vary; the discipline cannot. Layout and the example
values below are this repository's `[Addition]`.

## Contents

- Template
- Decision-point example (RabbitMQ)

## Template

```markdown
# <Runbook title: operation or failure mode>

Status: Draft — not yet validated | Validated <date> by <name, not the author>
Owner: <role / name>    Last validation: <date>    Review by: <date>

## Purpose
What this procedure achieves and why it exists.

## Scope
Covers: <precise situation>
Does NOT cover: <look-alike situations and where to go instead>

## Context
Why the platform is built this way here; links to decision records; known
exceptions and why they are constraints, not mistakes.

## Who may run it
Executable by: <first line / platform team>    Disruptive steps approved by: <role>

## Preconditions and dependencies
- Starting state assumed: ...
- Must be healthy: ...
- Access needed: ...
- Evidence to preserve before starting: ...

## Decision point(s)
| Check (read-only) | If you see | Go to |
|---|---|---|

## Procedure
### Section A — <case>
| # | Action | Why | Type | Expected result | If different, check first |
|---|---|---|---|---|---|
| 1 | | | read-only | | |
| 2 | | | state-changing | | |

## Stop and escalate
Stop if: ...
Collect before escalating: ...
Escalate to: ...

## Do NOT do without escalation
- ...

## Verification
End-to-end capability check: ...

## Recovery
If the procedure fails at step N: ...
Point of no return: ...

## History
| Date | Change | Why | By |
|---|---|---|---|
Includes approaches tried that did not work.
```

## Decision-point example (RabbitMQ)

Structure from [Book: Ch. 11]; commands are illustrative `[Addition]` and must
be adapted (e.g. run inside containers on containerized deployments).

First establish the partition-handling mode (and metadata store) and search
the RabbitMQ logs for partition events: with `pause_minority`, a partition
already resolved by pausing the minority looks, from the majority side, like a
single absent node — and a paused node may not answer `cluster_status`.

| Check (read-only) | If you see | Go to |
|---|---|---|
| `rabbitmqctl cluster_status` on every reachable node, plus logs and partition-handling mode | All reachable nodes agree; one node absent; remaining nodes are a majority; no partition reported **and** no partition events in the logs | Section A — node left the cluster |
| same | Nodes report different views, a partition is listed, or logs show partition events | Section B — partition: **stop, escalate** |
| same | The absent node cannot be queried and the cause of its absence is unknown | Section B |
| same | No majority remains | Section B |

**Section A (node left):** confirm the remaining nodes form a majority; rejoin
or reset the one node (state-changing, approval per policy); watch consumers
reconnect; verify RPC-dependent capability end to end.

**Section B (partition):** do not touch the nodes yet; establish which side
the services are talking to; decide with the incident leader whether to stop
the APIs first; escalate before any node is reset — the wrong reset discards
the queues services are still using.
