## Turn 1

**User:**

Production OpenStack: since about 10 minutes nobody can create VMs, new instances stay in BUILD. Existing VMs look fine. Where do I start?

**Assistant:**

# VMs stuck in BUILD, existing VMs fine: where to start

This points at the control plane (new state isn't propagating) or at a shared dependency. It is not a data-plane problem. I can't see your platform, so everything below is a hypothesis until you run the checks and paste the output. Please redact passwords and tokens (`transport_url`, `clouds.yaml`, `OS_*`) before pasting.

## Situation
- **Capability lost:** provisioning (new instances).
- **Still works (reported):** existing VMs. That is expected, since the data plane keeps running while the control plane is degraded.
- **Unknown:**
  - What changed ~10 minutes ago: a deploy or reconfigure, a certificate or Fernet rotation, a host reboot, a network change.
  - Business impact and who owns the decision to restrict the API.
  - Deployment tool and networking backend (ML2/OVS or OVN).
  - Whether anyone has already restarted anything. Restarts are evidence too.

## Hypotheses

| Hypothesis | Cheapest read-only check |
|---|---|
| **RabbitMQ unhealthy**: partition, alarm or lost consumers. RPC casts go nowhere, so instances sit in BUILD. | `rabbitmqctl cluster_status` **on every node**, then queues per vhost with `messages_ready` and `consumers`. |
| **Galera not Primary or no quorum.** | `SHOW GLOBAL STATUS LIKE 'wsrep_%'` on each node. Look at `cluster_size` and `cluster_status`. |
| **nova-conductor or scheduler not processing**, even though the process is running. | `openstack compute service list`, plus conductor and scheduler logs for messaging timeouts. |
| **Placement or Keystone or memcached** (auth or token validation failing). | Check `openstack token issue` and the Placement API. Look for 401s in the logs. |
| **Network binding / `vif-plugged` wait** (Neutron agents or OVN). | `openstack network agent list`, the port's binding status, and the `fault` message. |
| **Expired certificate** on an endpoint, the bus or the database. | `openssl s_client ... \| openssl x509 -noout -enddate` on each endpoint. |

## Next diagnostics (all read-only)
1. **Pick one stuck instance and read its fault.** Run `openstack server show <id>` and note the host (is it empty or set?) and the `fault`. Get its `req-...` ID and grep all service logs for it.
   - **No host assigned:** the problem is upstream of the compute node (bus, conductor, scheduler, Placement, DB).
   - **Host assigned:** look at nova-compute, Glance, Cinder or Neutron on that host.
2. **Run `openstack compute service list` and `openstack network agent list`.** Look for services reported down or stale heartbeats on many hosts at once. Many at once points to the bus or the database, not the hosts.
3. **Check RabbitMQ and Galera** as in the table. These are the shared components, so check them before anything else if several services look unhealthy.
   - **Check each node separately.** With Khepri, a partition may show no "Network Partitions" entry. The sign is nodes disagreeing about who is running.
   - **List queues per vhost.** Without `-p <vhost>` you only see the default vhost `/`, and an empty list there is not evidence of anything.
4. **Check the trend.** Run `openstack server list --all-projects --status BUILD` now and again in a few minutes. If the count keeps growing, the state is degrading.
5. **Check recent changes**: your deploy tool's history and the `kolla-ansible` run log, if you use it.

## Protect decision
I don't know yet whether the state is degrading. Step 4 answers that.
- **If the BUILD count is flat and impact is limited:** keep collecting evidence. That is safer than changing anything.
- **If it grows, or the bus or database turns out to be unstable while the APIs keep accepting writes:** consider controlled degradation, meaning you withdraw the API endpoints from the load balancer. This is an option, not an order.
  - **Cost:** nobody can create, modify or delete anything until you reopen.
  - **What stays protected:** you avoid orphaned allocations, half-built instances and Nova/Placement/Neutron records that disagree.
  - **Cautions:** conductors, schedulers and agents keep running. Agents all reconnect at once after a bus restart.
  - **Reopen condition:** the verification below passes.
  - **Decision owner:** who has authority to restrict the API? Please tell me.

## Corrective options
I'm deliberately not proposing any yet. Don't restart services, reset RabbitMQ nodes, bootstrap Galera or purge queues until a check supports a cause. The specific traps:
- **RabbitMQ node left vs partition:** the alert is the same, but a `rabbitmqctl reset` handles the first and destroys queues in the second. Establish which one it is, and escalate, before resetting anything.
- **Galera:** one node down needs no bootstrap. Bootstrapping the wrong node loses committed transactions.
- **Purging queues:** this discards in-flight operations and needs an explicit decision.

## Verification before declaring recovery
- Galera: full size and Primary on every node.
- RabbitMQ: all nodes in the cluster, queues present, consumers connected.
- Every compute service and network agent reports up.
- A **test VM is created, reached and deleted**.
- The stuck BUILD instances are dealt with. They are likely to need a separate, approved cleanup, not a blanket reset-state.

## What I need from you
1. Output of steps 1–4.
2. What changed in the last hour, or whether anything was restarted.
3. Deployment tool (Kolla-Ansible?), ML2/OVS or OVN, and how many controllers.
4. Who owns the decision to restrict the API, and what the business impact is.

Decision support only. State-changing steps above require approval by the accountable owner and should be executed under your change process.

## Turn 2

**User:**

Here is rabbitmqctl cluster_status from each node.
On rabbit-01: running nodes rabbit@rabbit-01, rabbit@rabbit-02; network partitions: rabbit@rabbit-03.
On rabbit-02: running nodes rabbit@rabbit-01, rabbit@rabbit-02; network partitions: rabbit@rabbit-03.
On rabbit-03: running nodes rabbit@rabbit-03; network partitions: rabbit@rabbit-01, rabbit@rabbit-02.
nova-conductor logs show MessagingTimeout. Can I just reset rabbit-03 and rejoin it so we're back up?

**Assistant:**

**Not yet.** Don't reset rabbit-03 until you know which side your services are talking to.

## What the output shows
- **Observed:** this is a real partition, not a node that left. rabbit-01 and rabbit-02 see each other and list rabbit-03 as partitioned. rabbit-03 sees only itself and lists the other two as partitioned. The three views are consistent, so the split is symmetric: {01, 02} against {03}.
- **Observed:** nova-conductor logs MessagingTimeout. This fits the partition as a cause of the BUILD problem, but it hasn't been confirmed as the cause. Some conductors or computes may be connected to the minority side, so RPC requests and replies can't reach each other.
- **Not shown:** which node each service connects to, the partition-handling setting, the metadata store (Mnesia or Khepri), the queue types, and what changed. That last one matters most, because it is what split the network.

## Why a reset is risky here
`rabbitmqctl reset` wipes rabbit-03's data. The consequences depend on facts you haven't shown yet:
- **If services are connected to rabbit-03:** you discard queues and in-flight operations they are using.
- **If they use quorum queues:** replicas on rabbit-03 are lost and need repair afterwards (`rabbitmq-queues grow`/`shrink`).
- **If the cause is a network fault between rabbit-03 and the others:** the node can't rejoin, and resetting only leaves it outside the cluster. On a lab (RabbitMQ 4.2 with Khepri), a reset attempt failed and left a node out of the cluster.
- **If the partition heals by itself:** that can happen, so a reset would be unnecessary and destructive. Re-check every node immediately before acting.

## Next diagnostics (all read-only)
1. **Check which node the services use.**
   - Look at the (redacted) `transport_url` in nova, neutron and the other services.
   - Look at the connections each RabbitMQ node holds with `rabbitmqctl list_connections -p <vhost> peer_host user state`, or the management UI.
   - Compare against nova-compute and conductor hosts. A split between services on the two sides would explain why only new work fails.
2. **Check the partition-handling setting and the metadata store** (`rabbitmq.conf`, `cluster_status`). With `pause_minority`, rabbit-03 should have paused itself, so why it is still "running" is a question to answer first.
3. **Check the network between rabbit-03 and the other two.** Ping and check latency from both directions, look at the switch or VLAN, and look at VM or hypervisor events if the nodes are VMs. Find out what changed ~10 minutes ago.
4. **List queues per vhost on both sides** with name, type, leader, members, messages and consumers. This shows what rabbit-03 actually hosts.
5. **Look at the RabbitMQ logs** on all three nodes around the start of the incident for `partition` and `net_tick_timeout` events.

## Protect decision
The majority side {01, 02} is the likely survivor, but that is a hypothesis. It is not enough to act on until step 1 is answered. Meanwhile:
- Check whether the BUILD count is still growing. If it is, the platform is accumulating bad state, and controlled degradation (withdraw the APIs from the load balancer) is worth discussing.
- Its cost is that nobody can create, change or delete anything. Keep Keystone and Placement running.
- Escalate before touching the RabbitMQ nodes. Who is the decision owner?

## Corrective options (not authorized)
These apply only after the checks above.

**A. Fix the network and let it heal.** This is the preferred option if the network cause is found.
- Verify that cluster_status on all three nodes agrees afterwards, then restart or reconnect services if needed.
- Risk: low. Services may need reconnecting.

**B. Restart or rejoin rabbit-03 without a reset.** Consider this if the node is on the minority side and no service uses it.
- Prerequisite: no service is connected to it, and you have snapshotted the queue and connection state.
- Blast risk: the node's local queue state may be lost. Reconnects happen all at once.

**C. Reset rabbit-03 and rejoin.** This is what you proposed. It is only justified if all of the following hold:
- Services are demonstrably on the {01, 02} side.
- You have listed the queues and replicas on rabbit-03.
- The network is fixed, because otherwise the node can't rejoin.
- There is a plan for rejoining and for quorum queue repair.
- You have named an approver.
- Stop conditions: any service is found connected to rabbit-03, or the rejoin fails. If it fails, the node stays outside the cluster, so you need to be able to run on the two remaining nodes.
- Recovery: none for rabbit-03's data. It is irreversible for that node.

**D. Purge queues.** Only if the backlog would be replayed against a recovering system, as in the book's case. This discards in-flight operations, so it needs an explicit decision.

## Verification before declaring recovery
- `cluster_status` on all three nodes agrees: three running nodes, no partitions.
- Queues exist with consumers connected, in every vhost the services use.
- nova-conductor MessagingTimeout stops appearing, and compute services and agents report up.
- A test VM is created, reached and deleted.
- Stuck BUILD instances are handled with a separate, approved cleanup.

## Follow-up (after the incident)
- Find what split the network, because that is the root cause. Without it this recurs.
- Review the partition-handling setting.
- Write a runbook that treats node-left and partition as different cases.

Decision support only. State-changing steps above require approval by the accountable owner and should be executed under your change process.

Please send: (1) where the services connect, (2) the partition-handling setting and store type, (3) what changed ~10 minutes ago, (4) the network check between rabbit-03 and the others.

## Turn 3

**User:**

OK. Our platform lead approved it: we pulled the APIs from HAProxy, restarted rabbit-03 and it rejoined, cluster_status now shows all three nodes running and no partitions. Can we put the APIs back in HAProxy now?

**Assistant:**

**Not yet.** A clean `cluster_status` is necessary but isn't enough to reopen. It shows the cluster is whole. It doesn't show that the services use it again. That is **Reported**, not verified, so here is what to check first.

## Before reopening (all read-only)
1. **RabbitMQ:**
   - `cluster_status` on each node again, so you know the state is stable and not a brief heal.
   - Queues in every OpenStack vhost (`-p <vhost>`) with `messages_ready` and `consumers`. Consumers should be connected, and the backlog should be draining or empty.
   - Queue leaders and members. Check that quorum queue replicas are back on rabbit-03, or plan `rabbitmq-queues grow`.
   - No memory or disk alarms.
2. **Galera:** `cluster_size` is full and `cluster_status` is Primary on every node.
3. **Services reporting:** `openstack compute service list` and `openstack network agent list` show everything up with fresh heartbeats. Agents reconnect all at once after a bus event, so give them a moment and check again.
4. **Logs:** nova-conductor and nova-scheduler have stopped logging MessagingTimeout. Check the time of the last occurrence against the rejoin.
5. **Orphaned state from the outage:** list instances in BUILD and ERROR. Anything started during the outage may be stuck, with orphaned allocations or ports. Treat that as a separate approved cleanup (audit first, no `--delete`). Don't mass reset-state.

## Reopen in stages
Your capability check is a test VM created, reached and deleted. That needs the APIs, and in a lab run the verification build needed them back.

- **Keep Keystone and Placement reachable** throughout. They were presumably not pulled, but confirm.
- **Reopen the APIs, then run the test VM.** If you can, reopen Nova (and Neutron and Glance) first for an internal or test path, or one backend, before general traffic. If the HAProxy setup doesn't allow that, reopen all and run the test VM immediately.
- **Stop conditions:** MessagingTimeout reappears, BUILD instances accumulate, or the partition returns. Then pull the APIs again and investigate.
- Run the test VM end to end: it reaches ACTIVE, gets an IP, you reach it, then delete it and confirm the port and allocation are gone.

## Root cause is still open
A restart fixed the symptom. It didn't tell you why the cluster split, and **no cause has been established**. Without finding it, this can recur.
- **Network cause:** check what changed ~10 minutes before the first MessagingTimeout, plus switch, VLAN and VM or hypervisor events on rabbit-03.
- **Handling setting:** why rabbit-03 stayed "running" on its own side instead of pausing, if the setting is `pause_minority`.
- If it does recur, don't just keep restarting. A repeated workaround is evidence that the cause is still present.

## Please confirm
- Which of these checks you have done, with output, especially consumers per queue and the service lists.
- Who is the decision owner for reopening? Your platform lead approved the earlier step. A reopen is a separate decision, so please confirm they agree.

Decision support only. State-changing steps above require approval by the accountable owner and should be executed under your change process.
