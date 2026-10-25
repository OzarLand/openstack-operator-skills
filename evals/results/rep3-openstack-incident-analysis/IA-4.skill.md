## Short answer: not yet

Don't run the runbook as written. `reset` wipes rabbit-03's data, and you haven't yet shown that rabbit-03 left the cluster instead of being partitioned from it. Both raise the same alert, and they need opposite handling. If it's a partition, resetting the wrong node can discard queues your services are still using. If rabbit-03 really did just drop out, the runbook is probably fine, but only after the checks below.

## Situation
- **Affected:** RabbitMQ cluster is degraded, with 2 of 3 nodes running.
- **Still working:** unknown. I haven't been told whether the OpenStack services can still send messages.
- **Business impact:** unknown. I need to know what depends on this cluster and what happens if it stays at two nodes.
- **What changed:** unknown. Was there a restart, network change, maintenance or upgrade? Has anyone already acted on rabbit-03?

## Evidence
| # | Class | Statement | Source |
|---|---|---|---|
| 1 | Observed (you reported it, I haven't seen the output) | `cluster_status` on rabbit-01 lists running nodes rabbit-01 and rabbit-02 | Your message |
| 2 | Reported | The runbook prescribes stop_app, reset, join_cluster, start_app | Your message |
| 3 | Gap | Cluster status as seen from rabbit-02 and rabbit-03. Each side of a partition reports a different view. | Not provided |
| 4 | Gap | Whether the `partitions` field is empty, plus the logs on all three nodes | Not provided |

## Hypotheses
| Hypothesis | Would disprove it | Check |
|---|---|---|
| A. rabbit-03 is down or stopped (node left) | rabbit-03 is up and its own `cluster_status` shows it running with other nodes | Run `rabbitmqctl cluster_status` on rabbit-03, and check whether the beam process is running |
| B. Network partition: rabbit-03 is up but isolated | rabbit-03 is stopped, or no partition events appear in the logs | Compare status from all three nodes. Check the `partitions` field and the log for "partition" or "net_tick" events. |
| C. Something outside RabbitMQ, such as a network, host or disk alarm, or a memory/disk watermark | Alarms are clear and connectivity is fine | Run `rabbitmqctl cluster_status` and `rabbitmq-diagnostics alarms`, and ping/telnet on the cluster ports between nodes |

## Next diagnostics (all read-only)
1. `rabbitmqctl cluster_status` on **each** of the three nodes. Compare the running nodes and the `partitions` field.
2. `rabbitmq-diagnostics alarms` and the last log lines on each node.
3. Check the partition-handling setting (`ignore`, `pause_minority` or `autoheal`) and the metadata store (Mnesia or Khepri). Verify both for your release.
4. `rabbitmqctl list_queues -p <vhost> name type members` for every vhost your services use. This shows which queues have replicas on rabbit-03, and whether they are classic or quorum queues.
5. Check whether the OpenStack services still have working consumers: `list_queues name messages consumers` for queues with messages but no consumers.
6. Check which broker each service's `transport_url` points to. Please redact credentials before pasting.

## Protect decision
I can't say yet whether the state is degrading. Check whether instances are piling up in BUILD or ERROR, and whether queue depth is growing. If it is, one option is to withdraw the API endpoints from the load balancer while you recover the bus. That makes provisioning unavailable, so the decision belongs to whoever owns the platform. Who is that? If nothing is degrading and impact is limited, gathering evidence is safer than changing anything.

## Corrective options (not yet authorized)
**If the diagnostics show hypothesis A (node left, majority intact, no partition):**
- **Prerequisites:**
  - rabbit-01 and rabbit-02 are confirmed healthy and form a majority.
  - You know which queues and quorum replicas live on rabbit-03.
  - You've decided what to do about queues whose only replica is on rabbit-03.
- **Steps (state-changing):**
  - First try plain `start_app` on rabbit-03. `reset` may not be needed at all.
  - Use `reset` only if the node can't rejoin otherwise.
  - Then `join_cluster rabbit@rabbit-01` and `start_app`.
- **Blast radius:** `reset` is irreversible for rabbit-03's data. Expect a reconnect wave as consumers move around.
- **Stop if:** the status disagrees across nodes, queues disappear, or consumers don't reconnect.
- **Verify:** the steps under "Verification" below.
- **Approver:** the RabbitMQ or platform owner. I need a name from you.

**If the diagnostics show hypothesis B (partition):** don't touch any node. Work out which side the services are connected to, decide whether to stop the APIs first, and escalate before any reset.

## Verification before declaring recovery
- All three nodes appear in `cluster_status` from every node, with no partitions or alarms.
- Queues are present with their consumers connected.
- Every `nova-compute` and Neutron agent reports in.
- A test VM can be created, reached and deleted.

## Open questions
- What did `cluster_status` show on rabbit-02 and rabbit-03?
- What is the impact on users, and who can approve disruptive steps?
- What changed recently, and has anyone already acted on rabbit-03?
- Versions, queue type and partition-handling setting?

## Follow-up
Once you're stable, find out why rabbit-03 dropped. Re-running the runbook without a cause just restores the symptom.

Paste the output of step 1 (redacted) and I can narrow this down.

> Decision support only. State-changing steps above require approval by the accountable owner and should be executed under your change process.