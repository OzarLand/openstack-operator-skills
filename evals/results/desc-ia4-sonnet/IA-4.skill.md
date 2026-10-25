## Short answer: not yet

Running `stop_app`, `reset`, `join_cluster` and `start_app` on rabbit-03 is the right fix only if rabbit-03 simply left the cluster. A partitioned cluster raises the same alert, and there the same steps can do real damage. So far you've only shown the view from rabbit-01, and the two cases can't be told apart from there.

## Situation
- **Capability at risk:** the message bus that Nova, Neutron and the other services use for RPC.
- **Business impact, what still works, what changed, timeline:** unknown. Please tell me whether VM creation or other operations are failing, whether anything changed recently (restart, network work, upgrade), and whether anyone has already run commands on rabbit-03.

## Evidence
| Class | Statement | Source |
|---|---|---|
| Observed | `cluster_status` on rabbit-01 lists rabbit-01 and rabbit-02 as running. rabbit-03 is not in the running list. | Your report |
| Not yet seen | The view from rabbit-02 and rabbit-03, partition status, alarms, logs, queue state | Gap |

## Why `reset` is the dangerous step
`rabbitmqctl reset` wipes rabbit-03's local data. That is harmless if rabbit-03 is a stale, empty member. If the cluster is partitioned and your services are connected to rabbit-03, it throws away queues they are actively using. In that case the book's handling is to leave the nodes alone, find out which side the services use, and escalate before resetting anything. Quorum queues add a second risk, because rabbit-03 may hold replicas that need handling first.

## Hypotheses
| Hypothesis | Disproved by |
|---|---|
| A. rabbit-03 is down or its app is stopped (node left) | rabbit-03's process is running and its own `cluster_status` shows other nodes |
| B. The cluster is partitioned and rabbit-03 is running on the other side | `cluster_status` on every node showing no partitions and rabbit-03 stopped or unreachable |
| C. Network or host problem (rabbit-03 cannot be reached) | Ping, port 25672 and 4369 reachable from rabbit-01 and rabbit-02 |

## Next diagnostics (all read-only)
Please run these and paste the output with any credentials redacted.
1. `rabbitmqctl cluster_status` on **each** of the three nodes. Look for a `Network Partitions` section, and for disagreement between nodes about who is running.
2. `rabbitmqctl list_alarms` on each node, plus the partition-handling setting. This is `cluster_partition_handling` (`ignore`, `pause_minority` or `autoheal`) and the metadata store (Mnesia or Khepri). Verify for your RabbitMQ release.
3. Is the rabbit-03 process alive? Use `systemctl status` or `docker ps`, and check its log for "partition", "net_tick" or "node down" events.
4. From rabbit-01 and rabbit-02, check connectivity to rabbit-03 on ports 4369, 25672 and 5672.
5. Where services are connected. Check the `transport_url` host list in your service config, then `rabbitmqctl list_connections` on each node. Redact any password in the URL.
6. `rabbitmqctl list_queues name type messages consumers` in each vhost your services use. This shows queue types (classic or quorum), backlogs, and whether queues have messages but no consumers.

## Protect decision
I can't say yet whether state is degrading, and I haven't seen any evidence either way. You can check by comparing instances stuck in BUILD or ERROR now against a few minutes later, and by watching queue depth. If it turns out to be a partition and services are failing and creating inconsistent state, controlled degradation becomes an option. That means withdrawing the APIs from the load balancer while the bus is recovered. It would cost provisioning and API availability, and the decision belongs to whoever owns the platform. It doesn't stop conductors, schedulers or agents. Please tell me who has that authority.

## Corrective options (not authorized, pending diagnostics)
**If it's a node that left (A or C), with rabbit-01 and rabbit-02 healthy and a majority:** the runbook is reasonable once these hold.
- **Prerequisites:**
  - Step 1 shows no partition.
  - You've listed which queues and quorum replicas live on rabbit-03.
  - You've checked that rabbit-03 has no unique data the services need.
- **Blast radius:** rabbit-03's local data is lost, and clients connected to it reconnect.
- **Verification:** all three nodes in the running list, queues with consumers, all Nova and Neutron services reporting, and a test VM created, reached and deleted.
- **Stop conditions:** a partition appears, queue counts drop unexpectedly, or consumers don't reconnect.
- **Recovery:** none for rabbit-03's local data, so it's irreversible for that node.
- **Approver:** the RabbitMQ or platform owner.
- **Caveats:** if rabbit-03 is gone for good, add `forget_cluster_node`, and check whether quorum queues need `rabbitmq-queues grow` or `shrink` afterwards.

**If it's a partition (B):** don't reset anything. Establish which side the services use and escalate. Then decide on stopping the APIs and which side to keep, as one planned sequence with its verification defined first.

## Verification before declaring recovery
Full cluster membership with no partitions or alarms, queues with consumers, every compute service and agent reporting, and a test VM created, reached and deleted.

## Gaps and open questions
- The impact on users and what changed recently.
- The status as seen from rabbit-02 and rabbit-03.
- The partition-handling mode, the queue type, and your RabbitMQ release.
- Whether anyone has already acted on rabbit-03.

## Follow-up
Once it's stable, find out why rabbit-03 dropped. Resetting and rejoining is containment, and a cause that isn't understood will recur. After the incident, the runbook should add a decision point for "check for a partition first".

> Decision support only. State-changing steps above require approval by the accountable owner and should be executed under your change process.

Paste the output of steps 1–3 and I'll help you decide which branch you're on.