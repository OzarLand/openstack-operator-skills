## Not yet. Don't run the runbook as written.

`reset` wipes rabbit-03's data. A node missing from `cluster_status` on rabbit-01 could mean two different things, and the runbook only fits one of them.

| | rabbit-03 left the cluster | The cluster is partitioned |
|---|---|---|
| The alert | the same | the same |
| Correct handling | rejoin or reset that one node | **don't touch any node**; first work out which side the services use |
| What a wrong reset costs | little | it can discard queues the services are still using |

### Evidence so far
| Class | Statement |
|---|---|
| Observed (your report) | `cluster_status` on rabbit-01 lists running nodes rabbit-01 and rabbit-02. |
| Gap | You haven't shown the output from rabbit-02 or rabbit-03, so I don't know whether rabbit-03 sees a different cluster. |
| Gap | I don't know whether the output has a partitions section, or what the logs say. |
| Gap | I don't know what changed recently, or whether any service is failing. |

### Read-only checks to run first
1. Run `rabbitmqctl cluster_status` on **each** of rabbit-01, rabbit-02 and rabbit-03.
   - If rabbit-03 reports itself in a cluster of its own, or if any node lists non-empty `Network Partitions`, treat it as a partition.
   - If rabbit-03 is simply down or stopped, it left the cluster.
2. Check whether rabbit-03's process is up and whether the host is reachable. Also check the network between the nodes.
3. Read the logs on all three nodes for partition events, `net_tick` timeouts, and `pause_minority` or `autoheal` messages.
4. Find the partition-handling setting (`ignore`, `pause_minority` or `autoheal`) and the queue type (classic or quorum). Check the queues in every vhost your services use.
5. List the queues, and the quorum-queue replicas, that live on rabbit-03. `reset` would destroy them.
6. Check the impact: do the OpenStack services have consumers connected, and are queues growing without consumers? Are any instances stuck in BUILD or other transitional states? Compare a count now with one a few minutes later to see whether things are getting worse.
7. Ask what changed recently, such as a deploy, network work, or a restart of rabbit-03.

Please redact any `transport_url` or password before pasting output.

### If the checks show rabbit-03 simply left the cluster
A reset and rejoin is then reasonable, but it is still state-changing and irreversible for that node's data. It needs these before you run it:
- **Prerequisite:** rabbit-01 and rabbit-02 are confirmed to form a healthy majority, and the queues on rabbit-03 have been listed.
- **Blast radius:** the queues and quorum replicas hosted on rabbit-03 are lost. Clients reconnect.
- **Stop condition:** if consumers drop or the remaining nodes show instability, stop.
- **Recovery:** none for rabbit-03's local data.
- **Verification:**
  - `cluster_status` shows 3 running nodes and no partitions.
  - Queue replicas are restored (quorum queues may need `rabbitmq-queues grow`).
  - Consumers are connected.
  - All compute services and agents are reporting.
  - A test VM is created, reached and deleted.
- **Approver:** whoever owns the control plane. Please tell me who that is.

### If it is a partition
Stop and escalate before any reset. Whether to stop the API endpoints first is a separate decision for the platform owner, and it has a cost: provisioning becomes unavailable.

Paste the three `cluster_status` outputs and I'll tell you which case this is.

> Decision support only. State-changing steps above require approval by the accountable owner and should be executed under your change process.