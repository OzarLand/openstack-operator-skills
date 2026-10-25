## Review: "RabbitMQ alarm" runbook

I reviewed the three steps as you gave them. There is no runbook file in the working directory, so I haven't seen the original text or any context around it. I ran no commands and inspected no system.

**Verdict: don't run it as written.** It restarts the shared message bus and then every nova and neutron service without first checking what the alarm means. It also verifies only that the alarm cleared, not that the platform works. It could turn a partial problem into a full control-plane outage.

### Findings

| # | Section | Problem | Why it matters | Suggested fix |
|---|---|---|---|---|
| 1 | Scope | "RabbitMQ alarm" is not a failure mode. It could be a resource alarm (memory or disk watermark, which blocks publishers), a node that left the cluster, or a partition. | Each case needs different handling. A restart can clear a memory alarm while hiding its cause, and it can destroy state in a partition. | Name the alarm. List look-alikes the runbook does not cover. |
| 2 | Decision points | There are no checks before step 1. | A node that left the cluster and a partitioned cluster raise the same alert and need opposite handling. If it's a partition, restarting nodes can discard queues the services are still using. | Add a read-only gate: `cluster_status` from each node, partition-handling mode, logs for partition events, and queues in every vhost the services use. If there's a partition, no majority, or an unknown cause, stop and escalate. |
| 3 | Step 1 | Restarting all three nodes means a full bus outage, not a rolling restart. | Every RPC fails during the outage. Non-durable queues and in-flight operations are lost. Nodes may block waiting for peers on boot (verify for your release). All agents then reconnect at once. | Restart one node at a time. Check the cluster is whole and consumers are back before the next node. Prefer the single affected node if the cause is known. |
| 4 | Step 1 | The cause isn't established. | A restart is a familiar fix, not a diagnosis. If the cause persists, the alarm returns. | Record the alarm type and a cause hypothesis first. If it recurs, escalate it as a problem to fix, not a routine. |
| 5 | Step 2 | Restarting all nova and neutron services is a blast radius with no stated reason. | After the bus is healthy, most services reconnect on their own. Restarting everything together adds a second reconnect storm. Restarting some neutron agents or OVN controllers can interrupt data-plane traffic for running VMs. Restarting nova-compute and the conductors in bulk disrupts in-flight builds and migrations. | Make it conditional: restart only services shown to be stuck, such as consumers with no connection. Do it per service, in batches, with a check after each. Remove blanket "restart all" or require a named approver. |
| 6 | Step 2 | There's no check on running workloads or in-progress operations. | Instances stuck in BUILD or deleting can end up with records that disagree across nova, placement and neutron. | Add a baseline before starting (instances in transitional states, service list) and compare afterwards. |
| 7 | Step 3 | "Alarm cleared" is process health, not capability. | A cleared alarm doesn't show that consumers reconnected, queues are healthy, or compute services and agents are reporting. | Verify end to end: the cluster is whole and has no partitions or alarms, queues have consumers, all compute services and agents report up, and a test VM is created, reached and deleted. |
| 8 | Missing | There are no preconditions, step types, expected results or "if different" notes. | An operator can't tell read-only steps from state-changing ones, or what to do when output differs. | Use the template: label each step, state the expected result, and say what to check first if it differs. |
| 9 | Missing | There are no stop conditions, must-not-do list or escalation path. | | See the draft below. |
| 10 | Missing | There's no recovery or point of no return. | A reset or forget-node wipes data and can't be undone. | Document the data lost and a plan to rebuild queue replicas. |
| 11 | Missing | There's no owner, validation date or history. | | Mark it "Draft, not yet validated" until someone other than the author has run it. |
| 12 | Missing | There's no protect decision. | If the platform keeps accepting API writes while the bus is unstable, orphaned allocations and half-built instances accumulate. | Add an option to withdraw the APIs from the load balancer. State its cost, who decides, and what reopens them. |

### Suggested rewrite (Draft, not yet validated)

**Owner:** TODO (confirm with platform team). **Last validation:** none.

**Scope.**
- Covers a RabbitMQ alert on the control-plane bus.
- Does not cover a partition, loss of majority, or Galera problems. Those go to Section B or escalation.

**Who may run it.**
- The platform team runs Section A.
- Restarting any service, and any reset, needs approval from TODO (name the role).

**Preconditions and evidence to preserve before starting.**
- Save `cluster_status` from each node, the alarm text, RabbitMQ logs and queue state.
- Record the count of instances in BUILD or ERROR, and the compute service and agent list.
- Check how the deployment tool runs RabbitMQ. Commands may need to run inside containers. TODO: confirm.

**Decision point (all read-only).**

| Check | If you see | Go to |
|---|---|---|
| `rabbitmqctl cluster_status` on every node, partition-handling mode, logs | All nodes agree, one node absent, the rest are a majority, no partition events | A |
| Same | Differing views, partition events, no majority, or an absent node you can't query | **B: stop and escalate** |
| `rabbitmqctl list_alarms` | A memory or disk alarm | A1 (find why the watermark was hit before restarting) |

**Section A: node left the cluster.**

| # | Action | Type | Expected result |
|---|---|---|---|
| 1 | Confirm the remaining nodes form a majority and the services' vhosts are healthy | read-only | Majority present, queues have consumers |
| 2 | Find why the node is out (logs, host resources) | read-only | A cause, or an explicit "unknown" |
| 3 | Restart or rejoin that one node, with approval | state-changing | Node rejoins, cluster whole |
| 4 | Check consumers have reconnected and the baseline is unchanged | read-only | No growth in stuck instances |
| 5 | Restart a nova or neutron service only if it's shown stuck, one service at a time, with approval | state-changing | The service reconnects. Check before moving on. |

**Section B: partition or no majority.**
- Don't touch the nodes.
- Establish which side the services use.
- The incident leader decides whether to withdraw the APIs.
- Escalate to TODO before any reset.

**Stop if:**
- The cluster views differ.
- Instances in transitional states keep growing.
- Monitoring goes blind.
- The decision owner is unreachable.

**Do not, without escalation:**
- Restart all three nodes at once.
- Run `rabbitmqctl reset` or `forget_cluster_node`.
- Purge queues. This discards in-flight operations.
- Restart all nova and neutron services in bulk.

**Verification.**
- The cluster is whole with no alarms or partitions.
- Queues have consumers.
- Every compute service and agent reports up.
- A test VM is created, reached and deleted.

**Recovery.**
- A reset wipes that node's data. List its queues and quorum replicas first.
- Plan to drop it with `forget_cluster_node` if it is removed for good, and to restore the replica count if needed. Verify the commands for your RabbitMQ release.

**History.** Record approaches that were tried and failed.

### Open questions
- What exactly does the alarm report, and what does the alert say?
- What partition-handling mode is configured, and are the queues classic or quorum?
- Which deployment tool runs RabbitMQ and the services?
- Who may approve disruptive steps, and who owns the runbook?
- Why does the current runbook restart all nova and neutron services? Was there a past incident behind it? That reason belongs in the Context section.

Validate the draft by having someone other than the author run it in non-production, or during real maintenance, with the author watching but not helping.

> Decision support only. State-changing steps above require approval by the accountable owner and should be executed under your change process.