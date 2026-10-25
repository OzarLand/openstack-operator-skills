## Short answer: not yet

Don't follow the runbook until you've run a few read-only checks. `reset` wipes rabbit-03's data and can't be undone. Your alert looks the same whether rabbit-03 left the cluster or the cluster is partitioned, and the two cases need opposite handling.

## Situation
- **Capability affected:** the message bus is degraded, so RPC for Nova, Neutron and the other services may be affected. I don't know yet whether provisioning is actually failing.
- **Business impact, what changed, timeline:** unknown. Please tell me what changed recently (restart, network work, maintenance, upgrade) and when the alert first fired.

## Evidence
| Class | Statement | Source |
|---|---|---|
| Observed | `cluster_status` on rabbit-01 lists rabbit-01 and rabbit-02 as running, and rabbit-03 as not running. | Your report, run from rabbit-01 only |
| Gap | You haven't shown the view from rabbit-02 or rabbit-03. | – |
| Gap | You haven't shown whether the rabbit-03 process is up, or what the logs say. | – |
| Gap | Partition-handling mode, queue type and release are unknown. | – |

## Hypotheses
| Hypothesis | Would disprove it | Check (all read-only) |
|---|---|---|
| **A. rabbit-03 left or crashed** (process down, host down, OOM, disk or memory alarm). | rabbit-03 is running and sees a different cluster. | On rabbit-03, check `rabbitmqctl status`, the service state and the logs. |
| **B. Network partition.** rabbit-03 is alive and thinks it's the cluster, or sees only itself. | rabbit-03 is down, or all three nodes report the same view. | Run `cluster_status` on **each** node and compare. Look for the "Network partition detected" lines in the logs. |
| **C. rabbit-03 was removed or reset earlier.** | The cluster metadata still lists it. | Check the disk nodes list and the logs. |

## Next diagnostics (read-only)
1. Run `rabbitmqctl cluster_status` on rabbit-01, rabbit-02 and rabbit-03, and compare the partitions section on each.
2. Check rabbit-03's process and host state, its RabbitMQ logs around the time it dropped, and any alarms (disk, memory).
3. Check the partition-handling setting (`ignore`, `pause_minority` or `autoheal`) and the metadata store (Mnesia or Khepri). Verify the details for your release.
4. Run `rabbitmqctl list_queues` in every vhost the services use. Note the queue type (classic or quorum), which queues have replicas or masters on rabbit-03, and which have messages but no consumers.
5. Check whether the services are connecting to rabbit-03, for example from `transport_url` or agent logs. Redact credentials before pasting anything.
6. Check whether instances are accumulating in BUILD or ERROR, and compare the count again a few minutes later.

## Protect decision
This depends on checks 1, 4 and 6.
- **If rabbit-03 simply left and 01 and 02 are healthy:** the two remaining nodes are a majority of three, so you can keep investigating without stopping anything.
- **If it's a partition, or instances are accumulating in transitional states:** don't touch any node yet. The decision to stop API intake (controlled degradation) belongs to whoever owns the platform. Tell me who that is, and escalate before any reset.

## Corrective option (not authorized yet)
If the checks confirm A, so rabbit-03 left cleanly and 01 and 02 form a healthy majority, the runbook sequence is reasonable. Before running it:
- **Queue inventory:** list the queues and quorum-queue replicas hosted on rabbit-03. `reset` wipes that node's data.
- **If the node is gone for good:** it also needs `forget_cluster_node`, and quorum queues may need `rabbitmq-queues grow` or `shrink` to restore their replica count.
- **Blast radius:** rabbit-03's local data is lost for good, and clients connected to it will reconnect.
- **Verification:** `cluster_status` shows all three running with no partitions. Queues have consumers and the expected replica counts. Every compute service and agent reports in. A test VM can be created, reached and deleted.
- **Stop conditions:** a partition shows up, 01 or 02 is unstable, or the queues don't recover.
- **Recovery:** none for rabbit-03's local data. The cluster itself is recoverable only if you have a plan for the queue replicas.
- **Approver:** your platform owner or on-call lead.

## Follow-up
Fix the runbook so that it starts with a "node left vs partition" decision point, which it currently lacks. Record the real cause of rabbit-03's departure so the incident doesn't recur.

If you paste the output of checks 1 to 3 (with credentials redacted), I'll tell you which branch you're in.

> Decision support only. State-changing steps above require approval by the accountable owner and should be executed under your change process.