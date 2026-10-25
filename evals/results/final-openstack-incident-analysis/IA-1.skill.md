**Don't restart RabbitMQ and all the nova services yet.** You have two shared components that may both be unhealthy, a Galera node in non-Primary and RPC timeouts. A blind restart can make recovery harder and slower, and it won't tell you which one is the cause. Ten minutes of read-only checks will most likely get you provisioning back sooner than a restart that fails or leaves you with a mess. I can't run anything on your platform, so everything below is a request for output. Nothing has been inspected.

## Situation
- **Lost capability:** provisioning (new VMs stick in BUILD or go to ERROR).
- **Still working:** existing VMs. This is the control plane failing, not the data plane.
- **Business impact:** unknown. I'd need to know who is blocked and whether autoscaling or customer-facing flows are failing.
- **What changed:** you haven't said. Ask your team about maintenance, deploys, certificate rotations and network changes in the hour before this started.
- **Timeline:** about 20 minutes ago. You haven't said whether anyone has already restarted anything.

## Evidence
| # | Class | Statement | Source |
|---|---|---|---|
| 1 | Reported | New instances stay in BUILD, some go to ERROR | You |
| 2 | Reported | Existing VMs are fine | You |
| 3 | Reported | nova-conductor logs are full of `MessagingTimeout` | You, no excerpt shown |
| 4 | Reported | One of three Galera nodes has `wsrep_cluster_status = non-Primary` | You, not shown which node or what the other two say |
| 5 | Gap | RabbitMQ state, other Galera nodes, and which DB node HAProxy sends nova to | Not provided |

## Hypotheses
| Hypothesis | Would disprove it | Check |
|---|---|---|
| **A. RabbitMQ partition or alarm.** RPC replies are lost, so conductor times out. This is the book's P1/P2 pattern. | `cluster_status` is healthy on every node, no alarms, and consumers are attached | `rabbitmqctl cluster_status` **on each node**, `list_queues` |
| **B. Galera degraded.** A non-Primary node is still receiving nova traffic, or quorum is lost. | The other two nodes are Primary with size 2, and HAProxy excludes the bad node | `SHOW STATUS LIKE 'wsrep_%'` on all three |
| **C. A network event.** A single event partitioned both the DB and the bus. | Both components look healthy on a quiet network | Switch and interface logs, and whether the Galera node and any RabbitMQ node share a host or rack |
| **D. A non-bus cause.** For example, an expired certificate on the bus or DB, or a Placement problem. | Certificates are valid and the error is bus-specific | Certificate expiry dates, conductor logs for the request ID |

A and B may be one incident rather than competing causes. A single network partition could have caused both.

## Next diagnostics (all read-only)
1. **Galera, on all three nodes:** `SHOW STATUS WHERE Variable_name IN ('wsrep_cluster_status','wsrep_cluster_size','wsrep_local_state_comment','wsrep_ready','wsrep_last_committed');`
   - If two nodes are Primary with size 2, quorum holds. The bad node just needs to be out of the load balancer, and the DB is probably not your main problem.
   - If **no** node is Primary, you've lost quorum. That's a separate, more dangerous problem (see below).
2. **HAProxy:** is the non-Primary node still receiving nova's DB connections? Check the backend status.
3. **RabbitMQ, run from each node:** `rabbitmqctl cluster_status`, `rabbitmqctl list_alarms`, `rabbitmqctl list_queues name messages consumers | head`. Different nodes reporting different cluster members means a partition. Also tell me the version, whether you use classic or quorum queues, and the `cluster_partition_handling` setting.
4. **Pick one failed request ID** (`req-…`) and follow it from nova-api through conductor and scheduler to compute. The first service that stops responding is your lead.
5. **Compare the number of instances in BUILD/ERROR now with a few minutes ago**, to see whether state is accumulating. `openstack server list --all-projects --status BUILD`
6. **`openstack compute service list` and `openstack network agent list`:** are the computes and agents reporting?

Paste me the output of 1, 3 and 5 and I can narrow it quickly.

## Protect decision
First find out whether the situation is getting worse (check 5). If instances keep piling up in BUILD, and especially if some are ERROR with half-created ports and allocations, the platform is accumulating orphaned state. Every extra failed build makes cleanup slower later.

If so, consider **controlled degradation**: withdraw the nova (and probably neutron/cinder) API endpoints from the load balancer. That freezes state while you fix the bus and DB. It costs you all API operations, including deletes and other management actions, though running VMs are unaffected. It does not stop conductors, schedulers or agents. It needs someone with authority to take the API offline, which is probably your manager or on-call lead. You can tell them provisioning is already down, so this mostly costs the API operations that still work. Reopen only when the checks below pass.

## What I would avoid, and why
- **Restarting RabbitMQ blindly.** If the cluster is partitioned, a reset on the wrong side discards queues the services are using. Establish the partition state first and escalate before touching nodes. Every agent reconnects at once afterwards, which creates a reconnect storm.
- **Restarting all nova services at once.** If the DB is unhealthy they will fail again. You'd also lose the log evidence of what failed first, and you'd be stacking changes so you can't tell what helped.
- **Bootstrapping Galera.** If all three nodes are non-Primary, do **not** bootstrap the first one that comes up. Bootstrapping the wrong node discards committed transactions. Identify the most advanced node first (`safe_to_bootstrap`, seqno, `mysqld --wsrep-recover`), and escalate to whoever owns the database.
- **Purging queues** drops in-flight operations. It can be the right trade-off, but only as a deliberate decision, not a reflex.

## Corrective options (not yet authorized)
Which one applies depends on the results above:
- **If only one Galera node is non-Primary and the others are healthy:** remove it from HAProxy and let it rejoin or resync (IST/SST). Check that it can see its peers over the network first. State-changing but low blast radius. The DB owner approves.
- **If RabbitMQ is partitioned:** do not touch it yet. Decide on stopping the APIs, then recover the bus under the senior owner's direction. That decision depends on which side the services use.
- **If the bus is healthy and only the DB is the issue:** restart the nova services only after the DB is fixed, one service at a time, with verification between each.

Change one thing at a time and verify before the next.

## Verification before declaring recovery
- Galera shows size 3, Primary and Synced on all nodes.
- RabbitMQ cluster is whole with no alarms and consumers are attached.
- Every compute service and network agent reports as up.
- A **test VM** is created, reaches ACTIVE, is reachable, and is deleted.
- The BUILD and ERROR counts stop growing.
- Stuck instances are cleaned up (reset state or delete) only after all of the above.

## For your manager
Provisioning is down because the control-plane messaging and database layers are unhealthy. Existing customer workloads are unaffected. We're running read-only checks to decide the safe recovery path. A rushed restart risks turning a provisioning outage into data loss or a longer outage. I'd expect to be able to give an ETA after the first round of checks.

> Decision support only. State-changing steps above require approval by the accountable owner and should be executed under your change process.

Send me the Galera status from all three nodes, the RabbitMQ `cluster_status` from each node, and the BUILD/ERROR counts now and a few minutes from now.