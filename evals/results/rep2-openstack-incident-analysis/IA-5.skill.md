## Turn 1

**User:**

Production OpenStack: since about 10 minutes nobody can create VMs, new instances stay in BUILD. Existing VMs look fine. Where do I start?

**Assistant:**

## Situation
- **Capability lost:** VM provisioning. New instances stay in BUILD.
- **Still working:** existing VMs look fine (reported). That fits a control-plane problem and doesn't point to the data plane.
- **Business impact:** unknown. Who is blocked, and is anything critical waiting on new VMs?
- **Timeline:** about 10 minutes (reported).
- **What changed:** unknown. This is the most valuable question. Ask about deployments, config changes, certificate or Fernet rotation, a RabbitMQ or DB restart, network changes, and maintenance in the last hour.

I can't inspect your system from here. Everything below is a hypothesis until you paste output.

## Hypotheses
| Hypothesis | Would disprove it | Check |
|---|---|---|
| RabbitMQ is degraded: partition, alarm, or consumers gone | Healthy cluster, with consumers present on the conductor, scheduler and compute queues | Step 3 |
| Galera has lost quorum or is non-Primary | All nodes Primary at the expected cluster size | Step 4 |
| Nova services are down or not reporting, such as the scheduler, conductor or computes | All services `up` | Step 1 |
| Neutron port binding or `network-vif-plugged` is not completing (BUILD until the VIF timeout) | Ports bound and active, with agents alive | Step 5 |
| Placement, Keystone, memcached, or an expired certificate | Certificates valid, token validation fast | Step 6 |
| Hosts not mapped to a cell, or no valid host | The fault message names something else | Step 2 |

## Next diagnostics (all read-only, in this order)
1. **Service liveness**
   - Run `openstack compute service list` and `openstack network agent list`.
   - A scheduler, conductor, or many computes showing `down` points at the bus or DB.
2. **What the instances say**
   - Run `openstack server list --all-projects --status BUILD`, then `openstack server show <id>` on one.
   - Note its `host`, `fault`, and request ID.
   - If `host` is empty, the build never left the scheduler or conductor. If `host` is set, the compute side or networking is the likely area.
   - Search the logs for that `req-...` ID across services.
3. **RabbitMQ**
   - Run `rabbitmqctl cluster_status` **on each node**, because each side of a partition reports a different view.
   - Run `rabbitmqctl list_vhosts`, then `list_queues -p <vhost> name messages_ready messages_unacknowledged consumers` for each OpenStack vhost.
   - Without `-p`, an empty result is not evidence.
   - Look for partitions, memory or disk alarms, and queues with messages but zero consumers.
4. **Galera**
   - Run `SHOW GLOBAL STATUS LIKE 'wsrep_%'` on every node.
   - Check `wsrep_cluster_size`, `wsrep_cluster_status` (must be `Primary`) and `wsrep_flow_control_paused`.
5. **Neutron**
   - Check the port status and binding host for the stuck instance.
   - Check the agent or OVN controller on its compute host.
6. **Quick sweeps**
   - Check certificate expiry on API, bus and DB endpoints, and memcached health.
   - Check LB backend health and the time of any recent Fernet or cert rotation.

## Protect decision
Check whether the state is getting worse. Compare the BUILD and ERROR count now and again in a few minutes, plus the RabbitMQ queue depth over time.

If the bus or DB is unstable and instances keep piling up, you risk orphaned allocations and records that disagree between Nova, Placement and Neutron. In that case the documented option is **controlled degradation**:
- Withdraw the API endpoints at the load balancer, then recover the bus and DB, verify, and reopen.
- **Cost:** all API operations are unavailable, including delete and other self-service. Existing VMs keep running.
- **Caveat:** conductors, schedulers and agents keep running, and a bus restart causes a reconnect storm.
- **Decision owner:** I don't know who has authority here. Who is it?

If the checks show something narrow, such as one dead service, you may not need this.

## Do NOT do yet
- Don't restart RabbitMQ, Galera or Nova services without a hypothesis.
- Don't reset RabbitMQ nodes before you know whether it's a node loss or a partition.
- Don't bootstrap Galera without identifying the most advanced node (seqno / `safe_to_bootstrap`).
- Don't purge queues, since that discards in-flight operations. It needs a named owner's decision.
- Don't mass-delete or reset-state the BUILD instances yet. That destroys evidence, and the right handling depends on the cause.

## Verification before declaring recovery
- Galera at full size and Primary.
- RabbitMQ whole, with consumers connected.
- All compute services and agents reporting `up`.
- A test VM created, reached, and deleted. Process health alone isn't enough.

## What I need from you
1. Output of steps 1–4 (redact `transport_url`, DB connection strings and tokens).
2. What changed in the last hour or two.
3. One stuck instance's `fault` and `host`, and its request ID.
4. Business impact, and who can authorize stopping the APIs.

> Decision support only. State-changing steps above require approval by the accountable owner and should be executed under your change process.

## Turn 2

**User:**

Here is rabbitmqctl cluster_status from each node.
On rabbit-01: running nodes rabbit@rabbit-01, rabbit@rabbit-02; network partitions: rabbit@rabbit-03.
On rabbit-02: running nodes rabbit@rabbit-01, rabbit@rabbit-02; network partitions: rabbit@rabbit-03.
On rabbit-03: running nodes rabbit@rabbit-03; network partitions: rabbit@rabbit-01, rabbit@rabbit-02.
nova-conductor logs show MessagingTimeout. Can I just reset rabbit-03 and rejoin it so we're back up?

**Assistant:**

## Short answer: not yet

What you pasted is a **network partition**, not a node that left the cluster. Both alerts look the same, but they need opposite handling. Resetting a node is the right move for a node that left, and the wrong one for a partition.

## What the output shows (Observed)
- rabbit-01 and rabbit-02 see each other and list rabbit-03 as partitioned.
- rabbit-03 sees only itself and lists the other two as partitioned.
- Each side reports a different view, which is the signature of a real partition. All three nodes are up, so nothing is dead.
- The `MessagingTimeout` in nova-conductor fits with that. RPC replies are getting lost or stuck, which fits BUILD with no failures on existing VMs. This is a hypothesis that fits the facts, not a proven cause. I haven't seen which side the services connect to.

## Why `reset` on rabbit-03 is risky
- `rabbitmqctl reset` wipes that node's data. If services are connected to rabbit-03, or it hosts queues or quorum-queue replicas that are in use, you discard them.
- Services may be split across both sides right now. Each side can hold a different subset of queues and consumers. Until you know which, you can't say which side's state matters.
- It is irreversible for that node's data.
- It would also trigger a reconnect storm while the control plane is already unstable.

The decision rule is to establish which side the services use, then escalate before any node is reset.

## Read-only checks to run next
1. **Which side do services use?**
   - Check `transport_url` for conductor, scheduler, compute and neutron. Redact credentials.
   - Check whether the hosts list contains all three nodes or only some, and what the LB or VIP points at, if there is one.
   - On each node, run `rabbitmqctl list_connections -p <vhost> user peer_host`, or the equivalent in your version, to see where clients are actually connected.
2. **Queues and consumers on each side**
   - On rabbit-01/02 and on rabbit-03 separately, run `rabbitmqctl list_queues -p <vhost> name messages_ready messages_unacknowledged consumers` for every OpenStack vhost.
   - Look for queues with messages but no consumers, and whether the two sides disagree.
3. **Queue types and replica placement**
   - Run `rabbitmqctl list_queues -p <vhost> name type leader members`.
   - Quorum queues need a majority of members. Check which node holds leaders and replicas.
4. **Partition handling and metadata store**
   - Check `cluster_partition_handling` in `rabbitmq.conf`. It could be `ignore`, `pause_minority` or `autoheal`, depending on how it was deployed.
   - Check whether the cluster uses Mnesia or Khepri. This setting applies to Mnesia only.
   - This tells you whether the cluster should have healed itself and why it didn't.
5. **Cause of the partition**
   - Look in the RabbitMQ logs for partition events and their timestamps.
   - Look for a network change, switch or link problem, or a rabbit-03 host problem at that time, and check latency and packet loss between rabbit-03 and the others.
   - This is what you need to answer "what changed", and I still don't have that.
6. **Alarms**
   - Check for memory or disk alarms on any node in `cluster_status`.

## Protect decision
The control plane may be accepting API writes while RPC is failing. Check whether BUILD and ERROR instances are accumulating now compared with a few minutes ago. If they are, that is the case for **controlled degradation**:
- Withdraw the API endpoints at the LB so state stops changing while you recover the bus.
- **Cost:** no API operations at all, including delete and self-service, until reopened. Existing VMs keep running.
- **Caveat:** conductors, schedulers and agents keep running and will reconnect together when the bus returns.
- **Reopen condition:** the verification list below passes.
- **Decision owner:** I still don't have a name. Who can authorize this?

## Recovery options (not authorized, pick after the checks)
| Option | Appropriate if | Cost / risk |
|---|---|---|
| Fix the underlying network issue and let the cluster heal | The cause is a transient or fixable network problem and the handling mode heals | No data loss if it heals cleanly. Verify queue state afterwards. |
| Restart or rejoin the **minority** side (rabbit-03) | rabbit-03 is the side with no service connections and holds nothing needed | State-changing and disruptive. List its queues and replicas first. |
| Purge queues | The backlog would be replayed against components that are unstable | Loses in-flight operations. Needs a named owner's explicit decision. |
| Reset rabbit-03 | Only after checks 1 to 3 show it is idle or its data is expendable | Wipes its data, irreversible. If you remove it for good, use `forget_cluster_node` and restore quorum-queue replica counts. |

Whichever you pick, decide the whole sequence with its verification up front. Don't combine it with unrelated changes.

## Verification before declaring recovery
- `cluster_status` on every node shows all three running and no partitions.
- Queues in each OpenStack vhost exist with consumers connected, and `MessagingTimeout` stops appearing in the conductor logs.
- All compute services and network agents report `up`.
- The stuck BUILD instances are resolved or deliberately cleaned up.
- A test VM is created, reached and deleted.

## What I need
- Outputs of checks 1 to 4.
- When the partition started and what changed around then.
- The decision owner for stopping the APIs.

> Decision support only. State-changing steps above require approval by the accountable owner and should be executed under your change process.

## Turn 3

**User:**

OK. Our platform lead approved it: we pulled the APIs from HAProxy, restarted rabbit-03 and it rejoined, cluster_status now shows all three nodes running and no partitions. Can we put the APIs back in HAProxy now?

**Assistant:**

Not on that evidence alone. A clean `cluster_status` shows the bus is whole. It doesn't show that the capability is back, and the verification list we set before acting is still open. Also, the actions and the clean status are reported, not shown. Paste the output if you want me to treat it as observed.

## Gates before reopening (all read-only)
1. **Bus state**
   - Rerun `cluster_status` on all three nodes and confirm there are no partitions or alarms. Check that it is still stable a few minutes later, since a flapping link would re-partition.
   - Run `list_queues -p <vhost> name type leader members messages_ready messages_unacknowledged consumers` for every OpenStack vhost. Queues should exist, with consumers on the conductor, scheduler and compute queues. Quorum queues should have their full replica count.
   - Messages stuck ready with no consumers means a service didn't reconnect.
2. **Services reconnected**
   - `openstack compute service list` and `openstack network agent list`: every compute service and agent should show `up`.
   - Check that `MessagingTimeout` has stopped appearing in the conductor, scheduler and compute logs. Components that didn't reconnect after the restart are a common leftover.
3. **Galera**: you haven't shown it yet. Check `wsrep_cluster_size`, `Primary` status and flow control on every node.
4. **Backlog and leftovers**
   - APIs are out of rotation, but conductors and schedulers are still running. Check whether the backlog is being processed or replayed now that the bus is back, and whether the BUILD count is changing.
   - Decide per instance what to do with the stuck BUILD ones. Don't mass reset-state or delete them blindly, since some may complete and some may have orphaned Placement or Neutron records. Run `nova-manage placement audit` **without** `--delete` and review it.
5. **Root cause of the partition**
   - You restarted the node, which is containment. If the network issue or a recent change that caused the partition is still there, it can recur right after you reopen.
   - Do you know why it partitioned, such as a link, switch or host event? Also check `cluster_partition_handling` and why it didn't self-heal. If you can't answer, reopen with that risk stated and monitor.

## End-to-end test, before opening to users
Create a test VM, reach it, then delete it. Do this against a single API backend if you can reach it directly. If you can only test through the VIF, add one backend to HAProxy first and watch it, then add the rest. This is a reopen plan, and it is state-changing.

## Reopen
- Reopen in stages if HAProxy allows it: one API backend first, watch the error rate, queue depth and BUILD count, then add the others.
- **Stop and withdraw again if:** a partition reappears, consumers drop, BUILD or ERROR counts start growing, or a test VM fails.
- **Decision owner:** your platform lead approved the stop, so confirm they also own the reopen decision.
- Tell the affected users when you reopen.

## Afterwards
- Capture the logs and queue state from this incident now, before they rotate, for the review.
- Containment is done, but the cause isn't understood until you know why the partition happened and why it didn't heal. Otherwise it returns.

If you paste the outputs from gates 1 to 3, I can say whether it's safe to start the staged reopen.

> Decision support only. State-changing steps above require approval by the accountable owner and should be executed under your change process.
