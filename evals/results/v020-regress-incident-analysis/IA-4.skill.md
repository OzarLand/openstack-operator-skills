## Short answer

No, not yet. Don't run the runbook as written. `reset` on rabbit-03 destroys that node's local data, and you haven't shown that rabbit-03 is actually gone from the cluster.

## Situation

- **Capability at risk:** the OpenStack message bus. The cluster is degraded but may still have quorum, with 2 of 3 nodes running.
- **What still works:** running instances should keep running. The control plane may be fine or may be stalling.
- **Unknown:** business impact, what changed recently, when the alert first fired, and whether anyone has already acted on rabbit-03.

## Evidence

| # | Class | Statement | Source |
|---|---|---|---|
| 1 | Observed | `cluster_status` on rabbit-01 lists rabbit-01 and rabbit-02 as running and omits rabbit-03. | Your message |
| 2 | Reported | The runbook says stop_app, reset, join_cluster, start_app. | Your message |
| 3 | Gap | What `cluster_status` shows on rabbit-02 and rabbit-03. | Not shown |
| 4 | Gap | Whether rabbit-03's container or host is up, and why it left. | Not shown |
| 5 | Gap | Whether any services are timing out (`MessagingTimeout`, computes flapping, builds stuck in BUILD). | Not shown |

## Why the runbook step is risky

"A node left the cluster" and "the cluster is partitioned" raise the same alert but need opposite handling. The runbook assumes the first. These are the hypotheses I'd test:

| Hypothesis | Would disprove it | Check |
|---|---|---|
| rabbit-03 is stopped or crashed (container down, host down, OOM). | rabbit-03's own `cluster_status` shows it running. | Container or unit state on rabbit-03. |
| Partition: rabbit-03 is up but cut off. On rabbit-03, `cluster_status` shows only itself, and clients may still be connected to it. | rabbit-03 can reach rabbit-01 and rabbit-02 on port 25672, and all three agree on membership. | `cluster_status` on all three nodes, plus the `net_tick_timeout` log lines. |
| rabbit-03 is stopped for a cause that is still active (memory or disk alarm, a bad deploy or config change). | Alarms are clear and there are no recent changes. | `check_local_alarms`, container logs, recent deploy history. |

Lab evidence from RabbitMQ 4.2 with Khepri and Kolla-Ansible 2026.1 (tag `LAB-VALIDATED: IA-CP-02`) points the same way:
- During a partition, `cluster_status` showed no partition entry on either side. The cut-off node kept accepting connections.
- The partition healed by itself once the network returned.
- A reset-based recovery failed in that lab. The node was left outside the cluster, and after rejoining it belonged to no quorum queue or stream. Clients and Neutron agents then failed with `PRECONDITION_FAILED` (tag `LAB-VALIDATED: IA-CP-05`).

I don't know your RabbitMQ version, whether you use Khepri or Mnesia, or whether you deploy with Kolla-Ansible. Verify those first. The lab results may not transfer to your platform.

## Next diagnostics (all read-only)

Run these on every node. With Kolla-Ansible, prefix them with `sudo docker exec rabbitmq`.

1. `rabbitmq-diagnostics cluster_status` on rabbit-01, rabbit-02 and rabbit-03. Compare the running lists and the partition lines.
2. `rabbitmq-diagnostics check_local_alarms`.
3. On rabbit-03: `systemctl status kolla-rabbitmq-container.service` (or `docker ps`), plus the last 100 log lines.
4. `rabbitmqctl list_queues name type messages consumers --silent | sort -k3 -n -r | head -20`. Look for RPC queues that are growing with 0 consumers.
5. `rabbitmqctl list_feature_flags name state --silent | grep khepri`. This tells you whether the store is Khepri or Mnesia.
6. `rabbitmqctl list_queues name type members`. Check whether rabbit-03 is still a replica of the quorum queues and streams.
7. From a control node: `openstack compute service list` and `openstack network agent list`. Are the services alive?
8. `grep -i net_tick_timeout` in the RabbitMQ logs.

Please redact any `transport_url` or password if you paste output.

## Protect decision

I can't tell yet whether the state is getting worse. Check for it:
- Compare the number of instances in BUILD or ERROR now and a few minutes from now.
- Watch queue depths over time.

If the system is healthy on two nodes and there's no growth, there's no urgency, and gathering evidence is safer than changing anything. If builds are stalling, the owner of the platform (please name who) should decide whether to withdraw the API endpoints from the load balancer while you recover the bus.

## Corrective options (not yet authorized)

Which one applies depends on the diagnostics.

- **A. rabbit-03 is simply stopped.** Start it with `sudo systemctl start kolla-rabbitmq-container.service`. This is state-changing and low risk. It should rejoin and quorum replicas should catch up (about 40 s on the lab). Streams may not regain a replica on a node that was down when they were declared. Undo is to stop the unit. Verify afterwards that it is a member of all queues.
- **B. Partition.** Repair the network and let it heal. Do not reset anything, and do not restart Nova or Neutron while the bus is partitioned.
- **C. Alarm or consumers gone.** Fix the cause. This is not a cluster membership problem.
- **D. The runbook sequence (reset and rejoin).** This is a last resort for a node that is up but cannot rejoin. It is destructive for rabbit-03's data and has no undo.
  - **Prerequisites:** options A to C ruled out, rabbit-01 and rabbit-02 confirmed healthy and in agreement, and an `export_definitions` backup taken.
  - **Blast radius:** replica loss on rabbit-03, then reconnect load, then a replica repair via `rabbitmq-queues grow rabbit@rabbit-03 all` and `rabbitmq-streams add_replica`, which adds replication load.
  - **Stop condition:** if reset times out, stop and escalate. Don't repeat it.
  - **Approver:** the owner of the message bus or the platform. Please name them.

## Verification before declaring recovery

- All three nodes list each other as running, with no alarms.
- `list_queues name type members` shows rabbit-03 in every quorum queue and stream.
- Every RPC queue has consumers and none is growing.
- All compute services and network agents report up.
- A test VM can be created, reached and deleted.

## Open questions

- What was the first signal, and what changed recently (deploy, reboot, config, network)?
- Is it Khepri or Mnesia, and which RabbitMQ version?
- Has anyone already touched rabbit-03?
- Who is the decision owner?

Paste the output of checks 1 to 6 and I'll narrow it down.

> Decision support only. State-changing steps above require approval by the accountable owner and should be executed under your change process.