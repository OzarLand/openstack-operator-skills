## Short answer
Not yet. Don't run `stop_app` / `reset` on rabbit-03 until you've done a few read-only checks. The alert doesn't tell you whether rabbit-03 left the cluster or the cluster is partitioned, and the runbook is only safe for the first case.

## Situation
- **Capability affected:** unknown. You haven't said whether OpenStack services are failing, only that the cluster is degraded.
- **Business impact:** unknown. What do I need to know? Whether VM operations are failing right now.
- **What changed:** unknown. Was there a network change, a restart, or maintenance on rabbit-03?

## Evidence
| # | Class | Statement | Source |
|---|---|---|---|
| 1 | Observed | `cluster_status` on **rabbit-01** lists rabbit-01 and rabbit-02 as running. rabbit-03 is not listed. | Your report |
| 2 | Unknown | What rabbit-02 and rabbit-03 each report. | Not shown |
| 3 | Unknown | Whether rabbit-03's process is up. | Not shown |
| 4 | Unknown | Which nodes the services' `transport_url` points to. | Not shown |

## Why not just follow the runbook
- **Two situations look the same.** A node that left the cluster and a partitioned cluster raise the same alert. Each needs the opposite handling.
- **A partition is a different case.** Rabbit-01's view alone can't distinguish it. If rabbit-03 is alive and still serving clients on its own side, `reset` wipes its state. That discards queues and messages that services may still be using, and it can't be undone.
- **Reset is destructive even in the simple case.** If rabbit-03 simply left, a reset plus rejoin is the right move. It is still state-changing.
- **I haven't verified the runbook against your setup.** Its steps depend on your RabbitMQ version, metadata store and queue types.

## Hypotheses
| Hypothesis | Would disprove | Check |
|---|---|---|
| A: rabbit-03 is down or stopped (host, process or Erlang crashed) | Process is running and clients are connected to it | Host and process state on rabbit-03 |
| B: Network partition, with rabbit-03 alive on its own side | rabbit-03 reports that it is stopped or can't reach anyone | `cluster_status` run on rabbit-03 itself |
| C: Node-to-node issue, such as a cookie, DNS or firewall problem | Other nodes connect to it normally | Logs on rabbit-03 and rabbit-01 |

## Next diagnostics (all read-only)
1. Run `rabbitmqctl cluster_status` on **each** of the three nodes. Compare the "running nodes" and "partitions" sections. If rabbit-03 reports itself running with rabbit-01 and rabbit-02 missing, that points to a partition.
2. On rabbit-03, check `systemctl status rabbitmq-server` (or the container state) and the tail of the RabbitMQ log. Look for `nodedown`, `partition`, `net_tick_timeout` or `inconsistent_database`. Also check for OOM kills or resource alarms.
3. Run `rabbitmq-diagnostics check_running` and `rabbitmqctl list_queues name messages consumers`. Look for queues with messages but no consumers.
4. Check how services connect: the `transport_url` in nova, neutron and similar services, and the cluster's partition-handling setting. Check the version, the metadata store (Mnesia or Khepri) and the queue type (classic or quorum), and verify them against your version's documentation.
5. Test connectivity between the nodes (ports 4369 and 25672, plus DNS), and ask whether anything changed on the network.
6. Check whether VMs are stuck. Compare the number of instances in BUILD or ERROR now and a few minutes from now.

## Protect decision
I can't tell yet whether state is degrading. Check item 6 above and the queues with no consumers. If instances are piling up in transitional states while the bus is unstable, stopping API intake is an option. It's a trade-off, and someone with the authority to decide it should make that call (the platform owner or incident lead). If impact is low, keep investigating instead.

## Corrective options (not authorized)
**If hypothesis A holds** (rabbit-03 simply left, and 01 and 02 still form a majority):
- Rejoining is reasonable, so you can follow the runbook's steps.
- Prerequisite: you've saved the logs from rabbit-03 first.
- Blast radius: the rabbit-03 node and any queue data local to it. Clients will reconnect, so watch for a reconnect storm.
- Stop if the other two nodes become unstable.
- Recovery: none for the wiped data on rabbit-03.
- Approver: the platform or messaging owner.

**If hypothesis B holds** (partition):
- Do not reset anything. Escalate to whoever owns the bus first.
- Establish which side the services are using.
- Then decide whether to stop the APIs before touching any node.

## Verification before declaring recovery
- `cluster_status` shows all three nodes running with no partitions.
- Queues are present with consumers connected.
- All compute services and agents report as up.
- A test VM is created, reached and deleted.

## Gaps
- The `cluster_status` output from rabbit-02 and rabbit-03.
- The current service impact.
- What changed recently.
- Your RabbitMQ version and queue type.

If you paste the `cluster_status` output from all three nodes, I'll tell you which case you're in.

> Decision support only. State-changing steps above require approval by the accountable owner and should be executed under your change process.