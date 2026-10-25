I reviewed the three-step runbook as you wrote it. I found no runbook file in the working directory, so I had nothing else to go on. It isn't safe to run as written.

**Verdict:** don't use it in production in this form. The main problem is that it restarts everything without first checking what the alarm actually means.

## Findings

| # | Section | Problem | Why it matters | Suggested fix |
|---|---|---|---|---|
| 1 | Scope | The runbook doesn't say which alarm it covers (memory or disk watermark, partition, node down, queue backlog) or what it doesn't cover. | A procedure that is safe for one RabbitMQ failure can be unsafe for another with a similar symptom. | Name the exact alarm and list the look-alikes it excludes. |
| 2 | Decision point (missing) | There is no read-only check before step 1. | A node that left the cluster and a partitioned cluster raise the same alert. They need opposite handling. | Add a `rabbitmqctl cluster_status` check on every node, then branch (see below). |
| 3 | Step 1 | It restarts all three nodes at once, with no order and no pause between nodes. | Restarting all three loses quorum and cluster availability. Every nova and neutron RPC call fails while that lasts. If the cluster was partitioned, restarts can also pick the wrong side and discard queues that services still use. | Restart one node at a time, and confirm it has rejoined and the cluster is healthy before touching the next. Do nothing at all if the cluster is partitioned. |
| 4 | Step 1 | It gives no rationale and doesn't consider whether the alarm is a symptom. | A memory or disk alarm, or a queue backlog, will usually come straight back after a restart. | State the cause, or add a diagnosis step first. A restart should not be the default fix. |
| 5 | Step 2 | "Restart all nova and neutron services" is not scoped. | It covers the API, scheduler, conductor, every compute agent and every neutron agent. It can leave instances stuck in BUILD or ERROR, interrupt in-flight operations and drop network agents. | Restart only the services whose RPC connections didn't recover. Check them first with `openstack compute service list` and `openstack network agent list`. Go one service group at a time, with a check after each. |
| 6 | Step 2 | It assumes services can't reconnect on their own. | Most services reconnect after a broker recovers, so a blanket restart may be unnecessary. | Make step 2 conditional on observed stale consumers or services that stay down. |
| 7 | Step 3 | "Check that the alarm cleared" only checks the monitoring signal, not the platform. | The alarm can clear while RPC is still broken. | Verify end to end: the queue and consumer state is healthy, the services show up, and a test VM can be created, reached and deleted. |
| 8 | Stop conditions | There are none. | The operator has no point at which to halt. | Stop if a node doesn't rejoin, a partition appears, quorum is lost or monitoring is blind. Escalate at that point. |
| 9 | Approval and audience | It doesn't say who may run it or who approves the disruption. | This is a control-plane outage across the whole cloud. | Name the approving role and the people who may execute it. |
| 10 | Preconditions | It doesn't list preconditions or evidence to save before restarting. | A restart destroys the evidence for the root cause. | Save `cluster_status`, the alarm details, logs and queue depths first. |
| 11 | Recovery | There is no recovery path. | If a node won't rejoin, the operator is improvising. | Document what to do if a node fails to rejoin and what is no longer recoverable. |
| 12 | Ownership | No owner, validation date or history. | Nobody is accountable for keeping it accurate. | Add all three. Mark it Draft until someone other than the author has run it. |

## Suggested restructure

**Decision point.** I haven't verified the commands below for your RabbitMQ or OpenStack release, or for your deployment tool. On containerized deployments, run them inside the containers.

| Check (read-only) | If you see | Go to |
|---|---|---|
| `rabbitmqctl cluster_status` on all three nodes | The nodes agree, one is absent and the other two are a majority, with no partition | **A: node left the cluster** |
| Same | The nodes disagree, a partition is listed, or there is no majority | **B: stop and escalate.** Don't restart anything. |
| Same | The cluster is healthy and only the alarm is present | **C: find out why the alarm is on** (memory, disk, backlog) before any restart |

**Section A:**
1. Record the evidence (read-only).
2. Rejoin or restart the one affected node (state-changing, needs approval).
3. Check that it has rejoined and that consumers have reconnected (read-only).
4. Restart a nova or neutron service only if it is still down (state-changing, one group at a time, with a check after each).
5. Run an end-to-end test VM check, then confirm the alarm cleared.

**Section B:** don't touch the nodes. Establish which side the services are using, decide with the incident lead whether to stop the APIs, and escalate before any reset.

## Open questions before I rewrite it into the full template
- Which alarm triggered the runbook? What is the symptom, and is it a memory watermark, disk or partition?
- What is the deployment (Kolla-Ansible, containers, packages), and which RabbitMQ and OpenStack releases?
- Is RabbitMQ clustered with mirrored or quorum queues? What is the HA policy?
- Who owns this runbook, and who approves control-plane disruption?
- Was the "restart everything" order learned from a real incident? If so, which approaches did you try that failed?

I haven't run anything against your platform, and the findings above come only from the text you gave me.

> Decision support only. State-changing steps above require approval by the accountable owner and should be executed under your change process.