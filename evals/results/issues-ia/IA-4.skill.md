## Short answer: not yet

Don't run the runbook yet. `reset` wipes rabbit-03's data and can't be undone. Your evidence doesn't yet separate "rabbit-03 left the cluster" from "the cluster is partitioned". Those two situations raise the same alert but need opposite handling.

## Situation
- **Capability:** the message bus is degraded. Its effect on OpenStack operations is unknown.
- **Business impact:** unknown. I need to know whether provisioning, RPC or migrations are failing, and whether running VMs are affected.
- **What changed:** unknown. Was there a restart, deployment, network change, host maintenance or certificate rotation?
- **Timeline:** unknown. When did the alert fire, and has anyone already acted on rabbit-03?

## Evidence
| # | Class | Statement | Source |
|---|---|---|---|
| 1 | Observed (as reported) | `cluster_status` on rabbit-01 lists running nodes rabbit-01 and rabbit-02 only. | Your message |
| 2 | Reported | The runbook says stop_app, reset, join_cluster and start_app on rabbit-03. | Your message |
| 3 | Gap | `cluster_status` from rabbit-02 and rabbit-03. | Not shown |
| 4 | Gap | Whether the output has a partitions section, and what it says. | Not shown |
| 5 | Gap | Whether rabbit-03's process is actually down or isolated, and why. | Not shown |
| 6 | Gap | Queue types, replica placement and consumer counts. | Not shown |
| 7 | Assumption | The runbook was written for a clean node loss. | Not demonstrated |

## Hypotheses
| Hypothesis | Would disprove it | Check (read-only) |
|---|---|---|
| A. rabbit-03 is down or stopped (crash, OOM, host or disk problem, deliberate stop). | The rabbit-03 process is running and clients are connected to it. | `systemctl status` or the container state on rabbit-03, plus its logs and the host's OOM, disk and network state. |
| B. rabbit-03 is partitioned or isolated, and still serving clients on its own side. | rabbit-03 reports itself alone and has no client connections. | `cluster_status` on **each** node, partition entries in the logs, and `rabbitmqctl list_connections` on each node. |
| C. Something outside RabbitMQ, such as the network, a certificate or the Erlang cookie, broke rabbit-03's membership. | The inter-node ports and TLS are fine. | Test connectivity between nodes (epmd and the distribution port) and check certificate expiry. |

Under hypothesis B, running `reset` on rabbit-03 discards queues that services may still be using. That is the main danger. Rejoining one node of a partitioned cluster can also lose messages.

## Next diagnostics (all read-only)
1. `rabbitmqctl cluster_status` on **rabbit-02 and rabbit-03**, not just rabbit-01. Each side of a partition reports a different view.
2. `rabbitmq-diagnostics check_running` and `rabbitmqctl list_connections` on every node. This shows which node the services (nova, neutron and others) are connected to.
3. The partition-handling setting (`ignore`, `pause_minority` or `autoheal`) and the metadata store (Mnesia or Khepri). Verify both for your release.
4. rabbit-03's logs from before the drop, plus host state (OOM, disk, network).
5. `rabbitmqctl list_queues -p <each vhost> name type members messages consumers`, to find queues that live on rabbit-03, whether they are classic or quorum, and whether any have messages but no consumers.
6. Compare the number of instances in BUILD or ERROR now and in a few minutes. Also check whether `openstack compute service list` and `openstack network agent list` show services flapping. This tells you whether the state is getting worse.

Please redact credentials such as `transport_url` before pasting any output.

## Protect decision
I can't say yet whether the state is degrading. Two of three nodes is still a majority, so the cluster may be serving fine. If nodes 01 and 02 are healthy, services are reconnected and nothing is accumulating, continue investigating. Nothing here suggests an emergency. If instead you find a real partition with services split across sides, stop API writes first. That is a protection decision for whoever owns the control plane, and you'd need to tell them what capability goes away.

## Corrective option (not yet authorized): the runbook's rejoin
This only applies if the checks establish that rabbit-03 simply left or died, and that rabbit-01 and rabbit-02 are a healthy majority.
- **Purpose:** restore the third member.
- **Prerequisites:** the checks above, plus the list of queues and quorum replicas on rabbit-03 and a decision on whether its data matters.
- **Blast radius:** `reset` is state-changing and irreversible for that node's data. Classic queues that lived only on rabbit-03 are lost. Quorum queues may need `rabbitmq-queues grow` afterwards. Consumers will reconnect.
- **A lighter step first:** if the process merely stopped, `start_app` on rabbit-03 without `reset` may rejoin it with its data intact. I haven't verified that for your release or setup. A forced `reset` is the last resort, not the first move.
- **Stop conditions:** a partition is found, services are connected to rabbit-03, or the remaining nodes show alarms.
- **Recovery:** none for rabbit-03's local data.
- **Approver:** whoever owns the messaging platform. I don't know who that is for you, so please tell me.

## Verification before declaring recovery
- `cluster_status` shows all three nodes running and no partitions, from every node.
- Queues are present with consumers connected, and no queues are stuck.
- Every nova-compute service and Neutron agent reports as up.
- A test VM is created, reached and deleted.

## Open questions
1. Is anything currently failing for users, or is this alert-only?
2. Did anything change recently, or has anyone already touched rabbit-03?
3. What are the RabbitMQ version, deployment tool and partition-handling setting?
4. Who owns the decision to reset a node?

If you paste the output of checks 1 and 2, I can tell you which hypothesis fits.

> Decision support only. State-changing steps above require approval by the accountable owner and should be executed under your change process.