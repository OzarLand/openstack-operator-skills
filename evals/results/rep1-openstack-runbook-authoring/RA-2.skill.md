# Review: "RabbitMQ alarm" runbook

**Verdict: not safe to run as written.** It treats every RabbitMQ alarm as the same problem and fixes it with a full restart. That fits some failure modes and is harmful in others. I only had the three steps you pasted, so the findings below are based on those. I haven't seen the runbook's owner, context or history.

## Findings

| # | Section | Problem | Why it matters | Suggested fix |
|---|---|---|---|---|
| 1 | Scope / purpose | "RabbitMQ alarm" doesn't say which alarm (memory or disk watermark, node down, partition, queue backlog, connection count). | The same alert can mean different situations that need different handling. A fix for one can be harmful for another. | Name the exact alert(s) covered. List look-alikes it does not cover and where to go for them. |
| 2 | Decision points | There are none. | A restart cures a stuck node but can destroy evidence or data in a partition. | Add a read-only triage first (see below) and branch on it. |
| 3 | Step 1 | It restarts all three nodes with no ordering, no pause between nodes and no check after each one. | Restarting every node takes the whole message bus down at once. Nova, Neutron and Cinder RPC stops. Cluster start-up order matters, and the last node to stop may need to be the first to start. Verify this for your RabbitMQ version. | Do one node at a time, with a check after each. Use a rolling restart only if the cluster is healthy and quorum is kept, and say why. |
| 4 | Step 1 | It ignores data loss. Non-durable or classic mirrored queues, and in-flight RPC messages, are lost on restart. | In-flight operations such as builds, migrations and port bindings can hang or end in ERROR. | State what is lost and the impact on running operations. Get approval from a named owner. |
| 5 | Step 1 | The partition-handling mode (`ignore`, `pause_minority` or `autoheal`) isn't checked. | The mode changes what a partition looks like. Under `autoheal`, RabbitMQ may already have restarted nodes and lost state. | Record the mode and check the logs for partition events before touching anything. |
| 6 | Step 2 | It restarts all nova and neutron services, with no list, no order and no scope. | This is a mass restart. Compute and agent restarts across many hosts can disrupt instances' networking, trigger resyncs and put heavy load on the DB and the new broker. | Restart only services that fail to reconnect, and first check whether they reconnected by themselves. If restarts are needed, do them in batches, control plane first, with a check between batches. |
| 7 | Step 2 | It is unclear why the restart is needed. | Modern oslo.messaging clients normally reconnect. Restarting everything may be unnecessary, and it hides which services were actually broken. | Check consumer counts and service heartbeats first. Restart only services that are provably stuck. |
| 8 | Step 3 | "Check that the alarm cleared" tests the monitoring signal, not the capability. | An alarm can clear while RPC consumers are missing or queues are stuck. | Verify end to end: services show up in `openstack compute service list` and `openstack network agent list`, RabbitMQ consumers are reconnected, and a test VM can be created, reached and deleted. |
| 9 | Missing | There are no stop or escalation conditions. | The operator doesn't know when to stop or who to call. | Add concrete stop conditions, such as no majority, a partition seen, or nodes that won't rejoin. Name who to escalate to and what evidence to collect. |
| 10 | Missing | There are no preconditions and no evidence preservation. | Logs and queue state vanish after a restart, so root cause is lost. | Capture `rabbitmqctl cluster_status`, queue lists, logs and the alarm details before step 1. |
| 11 | Missing | There is no recovery path or point of no return. | If a node doesn't come back, the operator has no guidance. A forced reset or `forget_cluster_node` is irreversible for that node's data. | Document what to do when a node fails to rejoin, and put a named approver in front of any reset. |
| 12 | Missing | There are no read-only/state-changing labels, no expected results, no owner, no validation date and no history. | A new operator can't tell what is safe, or whether the document is current. | Use the template. Mark the runbook **Draft – not yet validated** until someone other than the author has run it. |
| 13 | Context | There is no "why" for the design. For example, why restart rather than rejoin a single node? | A new operator can't tell a rule from a mistake. | Record the reasoning, the history, and what was tried and didn't work. |

## Suggested structure (draft, not yet validated)

**Status:** Draft, not yet validated. **Owner:** TODO. **Last validation:** none.

**Decision point (all read-only).** Run `rabbitmqctl cluster_status` on every reachable node, check the logs for partition events, and check the partition-handling mode. The commands are illustrative: adapt them for containers if you use Kolla.

| If you see | Go to |
|---|---|
| All reachable nodes agree, one node is absent, the rest are a majority, and the logs show no partition events | **Section A**: a node left the cluster |
| Nodes disagree, a partition is listed, autoheal restarted nodes, no majority remains, or the cause of an absent node is unknown | **Section B**: **stop and escalate** |
| A resource alarm (memory or disk) with the cluster otherwise healthy | **TODO**: separate section, since the fix is to clear the cause, not restart |

**Section A (one node out).**
1. *Read-only.* Confirm the other nodes are a majority. List queues and replicas on the absent node, and record what a reset would lose.
2. *State-changing.* Try to restart and rejoin that one node only. Check that it rejoins and that consumers reconnect before going further.
3. Reset or `forget_cluster_node` only with named approval. Follow with a quorum-queue replica check.

**Section B (partition or unclear).**
Don't touch the nodes. Find out which side the services use and decide with the incident lead whether to stop the APIs. Escalate before any restart or reset.

**Reconnect check (replaces step 2).**
*Read-only.* Look for stale services and agents and for missing consumers. Restart only services that stay stuck, in small batches, with a check after each.

**Verification.**
Services and agents are up, consumers are reconnected, and a test VM can be created, reached and deleted. The alarm clearing is only a supporting signal.

**Do not, without escalation.**
Restart all three nodes at once, reset or forget a node, purge queues, or mass-restart nova and neutron.

## Gaps to close before this becomes a real runbook
- Which alarm triggers it? (TODO: monitoring owner)
- Partition-handling mode, RabbitMQ version, queue types, and whether it is containerized (TODO: platform team)
- The list of nova and neutron services and their hosts (TODO)
- Owner, escalation contact and approver (TODO)
- Whether an earlier incident produced this runbook, and any failed attempts (TODO)

**Validation plan:** someone who didn't write it runs it in a non-production environment or during real maintenance, while the author watches but doesn't help. Correct the document from their questions.

I can write this out as a full runbook in the template format, or turn it into a shareable page, if you tell me the alarm name and the details above.

> Decision support only. State-changing steps above require approval by the accountable owner and should be executed under your change process.