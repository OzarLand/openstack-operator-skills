# Review: "RabbitMQ alarm" runbook

**Verdict: don't run it as written.** It is a command list with no decision point. Its first step restarts every RabbitMQ node at once, which is the move the platform's own guidance says to avoid when the alarm could be a partition.

I only have the three steps you typed. I haven't seen the full document, the alarm definition, the deployment tool or the RabbitMQ config. Anything not stated is marked as a gap below.

## Findings

| # | Section | Problem | Why it matters | Suggested fix |
|---|---|---|---|---|
| 1 | Scope and decision point | One alarm is treated as one situation. A node that left the cluster, a partition, and a loss of majority all raise the same alert and need different handling. | A partition needs "do not touch the nodes, find out which side the services use, escalate before any reset". A blanket restart can discard the queues services are still using. | Add a read-only decision table before step 1 (draft below). |
| 2 | Step 1 | It restarts all three nodes with no order, no gap between nodes and no health check between them. | Restarting a three-node cluster all at once removes the majority and drops every RPC connection. Nova, Neutron, Cinder and Heat all lose messaging. A cluster that was degraded can become fully down. | Check the cluster first. Restart only the affected node, one node at a time, and check each node before touching the next. Restarting all three is a separate, approved escalation. |
| 3 | Step 1 | It doesn't check which partition-handling mode is configured (`ignore`, `pause_minority` or `autoheal`). | The mode changes what the alarm means. Under `pause_minority`, a paused node may not answer `cluster_status`. Under `autoheal`, nodes may already have been restarted and lost state. | Read the mode and the logs first (read-only). Mark this as "verify for your release". |
| 4 | Step 2 | It restarts all nova and neutron services, with no scope, order or reason. | Many services restarting at once reconnect to RabbitMQ at the same moment and put a load spike on it. It also restarts nova-compute and the neutron agents on every host, which interrupts API, scheduling and networking control. | Say why it is needed, which services and which hosts. Check first whether services reconnect on their own. Restart only the services that stay stuck, in small batches, with a stop condition. |
| 5 | Step 2 | It is a bulk restart with no approver, no blast-radius statement and no stop condition. | It is a platform-wide, state-changing action. It needs a named approver and a stated impact. | Add the approver role, the affected capabilities and the stop conditions. |
| 6 | Step 3 | "Check that the alarm cleared" verifies the monitor, not the capability. | An alarm can clear while queues are empty or consumers are missing. It can also stay red after the service has recovered. | Verify end to end: service lists show up, then create, reach and delete a test VM and a test port. Add queue and consumer checks in every vhost the services use. |
| 7 | Preconditions | There are none. | No evidence is preserved before restarting, so root cause is lost, and the alarm will return. | Capture `cluster_status`, the logs, the queue backlog and the service list before any change. |
| 8 | Stop and must-not-do | There is no stop, escalation or must-not-do section. | Operators have no point at which to stop. | Add them (draft below). Examples: no `reset`, `forget_cluster_node` or queue purge without escalation. |
| 9 | Recovery | There is no recovery path and no point of no return. | If step 1 leaves the cluster down, the runbook doesn't say what to do next. | Add a recovery section. The details are a gap: see TODOs. |
| 10 | Ownership | There is no owner, validation date or history. | You can't tell whether it was ever exercised. | Mark it **Draft, not yet validated** until someone other than the author has run it. |
| 11 | Context | The runbook doesn't say why restarting is the answer. | A new operator can't tell whether "restart everything" is a deliberate workaround for a known bug or a habit. | Record the history, including what was tried and didn't work. |

## Revised draft

**Status: Draft, not yet validated.** Owner and review date are TODOs.

**Scope**
- Covers: the RabbitMQ alarm on a three-node cluster.
- Does not cover: partition or no-majority situations (go to Section B), or any reset, `forget_cluster_node` or queue purge.

**Who may run it:** first-line staff for the read-only checks. Any state-changing step needs approval from the platform owner (named role: TODO).

**Preconditions**
- Preserve evidence: `rabbitmqctl cluster_status` from every reachable node, the RabbitMQ logs, the queue backlog and consumer counts in every vhost from `transport_url`, and `openstack compute service list` and `openstack network agent list`.
- Know the partition-handling mode in `rabbitmq.conf`. Verify for your release.
- Commands may need to run inside containers on a containerized deployment (such as Kolla).

**Decision point (all read-only)**

| Check | If you see | Go to |
|---|---|---|
| `cluster_status` on every reachable node, plus logs and partition mode | All reachable nodes agree, one node is absent, the rest are a majority, and no partition events are in the logs | Section A |
| Same | Nodes disagree, a partition is listed or in the logs, no majority remains, the absent node can't be queried, or `autoheal` restarted nodes | Section B: stop and escalate |

**Section A: one node left the cluster**

| # | Action | Type | Expected result | If different |
|---|---|---|---|---|
| 1 | Confirm the other two nodes are healthy and form a majority | read-only | Both agree | Go to Section B |
| 2 | Restart `rabbitmq-server` on the **affected node only** (approval needed) | state-changing | The node rejoins | Do not restart another node. Collect logs and escalate. |
| 3 | Check `cluster_status` and the queues and consumers on all nodes | read-only | Three nodes, consumers reconnected | Wait for reconnect. Escalate if it doesn't recover. |
| 4 | Check whether nova and neutron services have reconnected (service and agent lists) | read-only | All up | Go to step 5 |
| 5 | Restart only the services that stay down, in small batches, checking after each batch (approval needed) | state-changing | Services return | Stop on a new alarm, a new failure, or an API error rate above the agreed level (TODO: set it). |
| 6 | End-to-end check: create, reach and delete a test VM and a test port | state-changing (test resources) | All succeed | Escalate |
| 7 | Confirm the alarm cleared and stays clear (the wait time is a TODO) | read-only | Cleared | Escalate |

**Section B: partition, no majority, or unknown cause.** Don't touch the nodes yet. Establish which side the services are talking to. Decide with the incident lead whether to stop the APIs. Escalate before any restart or reset.

**Stop and escalate if:** the alarm persists after step 2, a second node is affected, monitoring goes blind, or compute or the APIs degrade.
**Collect before escalating:** the evidence listed under Preconditions.
**Escalate to:** TODO.

**Do not, without escalation:** restart all three nodes together, run `reset`, `forget_cluster_node` or a queue purge, or bulk-restart services on every host.

**Recovery and point of no return:** TODO, to be confirmed with the platform owner. A node reset wipes that node's data, so list the queues and quorum-queue replicas it hosts first.

## Author notes

- **Sources:** only your three-line summary. Section A's structure comes from the decision-point guidance in the skill. Commands are illustrative and must be verified for your release and deployment tool.
- **Gaps (TODO, owner to confirm):**
  - what raises the alarm and what clears it;
  - the partition mode;
  - the deployment tool;
  - the service list and the batch size;
  - the approver and escalation contact;
  - the wait time before declaring the alarm cleared;
  - why the original runbook says to restart everything, and the history of the alarm.
- **Validation plan:** someone who didn't write it runs it, observed and not helped, in a non-production environment or during real maintenance. Correct the document from their questions.

Decision support only. State-changing steps above require approval by the accountable owner and should be executed under your change process.

If you paste the full runbook (secrets redacted), the alarm definition and the `rabbitmq.conf` partition setting, I can replace the TODOs.