## Situation
- **Capability lost:** creating new VMs. Instances sit in BUILD or go to ERROR.
- **Still works (reported):** running workloads. That fits a control-plane failure where the data plane is untouched.
- **Business impact:** unknown. I need to know who is blocked and whether any customer-critical workload depends on creating or scaling VMs right now.
- **What changed:** not stated. Please tell me about any deploy, config change, certificate or key rotation, network or switch work, or host maintenance in the last hour.
- **Timeline (reported):** about 20 minutes ago. I don't know who reported it first or what has already been tried.

## Don't restart yet
Don't restart RabbitMQ and all the nova services yet. A restart can make this worse, and with what we know it probably wouldn't fix it.

- **Galera is the stronger lead.** A node reporting `non-Primary` means it lost quorum or got partitioned. Nova conductor and API write to that database. If your conductors and APIs are connected through a node that is non-Primary, DB calls block or fail, and RPC timeouts follow. The MessagingTimeout in the logs could be a downstream symptom, not the cause.
- **A RabbitMQ partition would look the same.** A partition and a node that left the cluster raise the same alert and need opposite handling. Restarting or resetting the wrong side discards queues the services are still using.
- **A restart storm adds load.** Every agent and conductor reconnects at once, onto a database cluster that is already unhealthy.
- **A restart removes evidence.** You'd lose the state that tells us which hypothesis is right.
- **It combines changes.** Restarting everything makes it impossible to tell what fixed the problem, or what broke it further.

## Evidence
| # | Class | Statement | Source |
|---|---|---|---|
| 1 | Reported | New instances stay in BUILD, some go to ERROR | you |
| 2 | Reported | Existing VMs and customer workloads are fine | you |
| 3 | Reported | nova-conductor logs are full of oslo.messaging MessagingTimeout | you |
| 4 | Reported | One of three Galera nodes has `wsrep_cluster_status = non-Primary` | you |
| 5 | Gap | RabbitMQ cluster status and partitions, queue depth and consumers | not shown |
| 6 | Gap | Status of the other two Galera nodes, `wsrep_cluster_size`, and which node the services use | not shown |
| 7 | Gap | Recent changes, and whether anyone has already restarted anything | not shown |

## Hypotheses
| Hypothesis | Supports | Would disprove | Discriminating check |
|---|---|---|---|
| **H1: Galera lost quorum or is partitioned, and DB calls are blocking, which shows up as RPC timeouts** | #4, and existing VMs being fine | The other two nodes are Primary with size 2, and the services' DB endpoint points at them and responds | `wsrep_cluster_status`, `wsrep_cluster_size` and `wsrep_local_state_comment` on all 3 nodes. Check which node HAProxy or the DB VIP routes to. |
| **H2: RabbitMQ is partitioned or has an alarm (memory or disk), so replies are lost** | #3 | `cluster_status` agrees on every node with no partitions or alarms, and queues have consumers | `rabbitmqctl cluster_status` on each node, `rabbitmqctl list_queues name messages consumers` |
| **H3: A common cause hits both**, such as a network event between control nodes, a switch or MTU change, or a time or cert problem | Two shared components failing together | Galera and RabbitMQ events are unrelated in time | Compare timestamps in the Galera logs, the RabbitMQ logs and the kernel and network logs |
| **H4: Only the one non-Primary node is sick**, and the cluster itself is fine, so MessagingTimeout is separate | #4 alone | Timeouts correlate with DB errors in the logs | `wsrep_cluster_status` on the other two nodes. Check whether the conductor's DB errors name the sick node. |

## Next diagnostics (all read-only)
1. **On each Galera node:** `SHOW STATUS LIKE 'wsrep_%';` and look at `wsrep_cluster_status`, `wsrep_cluster_size`, `wsrep_local_state_comment`, `wsrep_cluster_conf_id`, `wsrep_last_committed`. This is the most valuable check. If two nodes are Primary with size 2, quorum is intact and the problem is narrower. If none is Primary, the database is down for writes.
2. **Check what the services actually connect to:** HAProxy or VIP backend status for the DB, and the `connection =` in nova.conf. This tells us whether the sick node is being used.
3. **On each RabbitMQ node:** `rabbitmqctl cluster_status` and `rabbitmqctl list_queues name messages consumers`. Run it from every node, because each side of a partition reports a different view. Also note the partition-handling setting.
4. **Follow one failed request.** Take a `req-...` ID from a failed build and follow it through nova-api, conductor, scheduler and compute. The first error in the chain matters more than the timeout at the end.
5. **Compare Galera and RabbitMQ logs** for the first error timestamp (about 20 minutes ago) and for anything in the kernel and network logs at that time.
6. **Count instances in BUILD or ERROR now and again in 5 minutes** (`openstack server list --all-projects --status BUILD`). This answers the protect question below.

## Protect decision
Whether state is degrading is something to check (diagnostic 6). It isn't established yet. The risk is real, though. If the APIs keep accepting build requests against a shaky database and bus, you can end up with orphaned Placement allocations and half-built instances. Those make recovery slower and less certain.

**Options:**
- **Keep investigating for 10–15 minutes while counting BUILD and ERROR instances.** Choose this if the count is flat or slowly rising. It costs nothing and keeps all options open.
- **Controlled degradation.** Withdraw the nova-api, and possibly the neutron, cinder and glance, endpoints from the load balancer, so no new state is created while you fix the database and bus.
  - *Cost:* the API for everything behind it becomes unavailable for customers, not only provisioning. Customers need to be told.
  - *Doesn't stop:* conductors, schedulers and agents keep running.
  - *Reopens when:* the verification below passes.
  - *Decision owner:* I don't know who that is for you. **Who has authority to take the APIs down? Your manager, or an incident commander?**

I'd lean toward the first option unless the count is climbing. Then I'd bring the stop to your manager as a protection decision rather than restarting things under pressure.

## Corrective options (not yet authorized)
The right fix depends on the diagnostics, so these are conditional.

**If H1 holds, Galera has lost quorum or is partitioned:**
- *Majority still Primary (2 of 3):* the sick node usually rejoins on its own after the network cause is fixed, or by restarting just that node's mariadb so it does a state transfer. The blast radius is that node's load, plus a possible SST or IST that loads a donor. Check that the services aren't pointed at that node first.
- *No Primary component:* **do not bootstrap yet.** Bootstrapping the wrong node discards committed transactions. First identify the most advanced node using `wsrep_last_committed`, `safe_to_bootstrap` in `grastate.dat`, or `mysqld --wsrep-recover`. This needs a named owner and a second pair of eyes.

**If H2 holds, RabbitMQ is partitioned:**
- Don't reset any node until you know which side the services use. Escalate before resetting. Whether to purge queues is a separate decision, because purging discards in-flight operations. It is sometimes the right trade, but it needs an explicit decision.

**Restarting nova services** only makes sense after the database and bus are healthy, so the services reconnect cleanly. Do it as part of one planned sequence with verification defined up front, not as the first move.

For any of these, the **approving role** is whoever owns the control plane or database (I don't know who that is for you). **Recovery path:** none for a wrong Galera bootstrap or a queue purge, so those are the steps to rehearse and review.

## Verification before declaring recovery
Process health isn't enough. All of these should hold:
- Galera: all 3 nodes `Synced`, `wsrep_cluster_size = 3`, status `Primary`.
- RabbitMQ: one cluster, no partitions or alarms, queues have consumers.
- `openstack compute service list` and `openstack network agent list` show every service and agent up.
- No new MessagingTimeout in the conductor logs.
- **A test VM is created, reached over the network, then deleted.**
- Stuck BUILD and ERROR instances are reviewed, and Placement allocations are audited with `nova-manage placement audit` (read-only).

## Gaps and open questions
1. Output of Galera status from all 3 nodes (diagnostic 1).
2. Output of RabbitMQ `cluster_status` from all nodes (diagnostic 3).
3. What changed in the last hour, and has anyone already restarted anything?
4. Who decides to take the APIs down, and what is the business impact of waiting?
5. Versions of OpenStack, Galera and RabbitMQ. Behavior is release-specific, so verify against your vendor docs.

## Follow-up
- **Containment:** restore the database and bus, then verify. Don't mix in other changes.
- **Structural:** find out why the node went non-Primary, whether that is network, load or a fencing event. The review must reach that cause or it will return. Also check monitoring: did anything alert on `wsrep_cluster_status` before users noticed?

**What to tell your manager now:** "We have a likely control-plane database issue and we're diagnosing it. Restarting everything blind risks making it worse and unrecoverable. We'll have a clear picture in about 10–15 minutes." If you paste the Galera and RabbitMQ output, I'll narrow this down immediately.

> Decision support only. State-changing steps above require approval by the accountable owner and should be executed under your change process.