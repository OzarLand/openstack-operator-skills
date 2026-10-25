## Turn 1

**User:**

Production OpenStack: since about 10 minutes nobody can create VMs, new instances stay in BUILD. Existing VMs look fine. Where do I start?

**Assistant:**

Start with read-only checks on the shared control-plane components. I can't see your platform from this session, so everything below is a hypothesis to test, not a finding. Please paste the command output and redact credentials such as `transport_url` and DB connection strings.

## Situation
- **Lost capability:** provisioning. New instances stay in BUILD.
- **Still works:** existing VMs. This fits a control-plane problem with a healthy data plane.
- **Business impact:** unknown. I need to know who is blocked and whether anything is auto-scaling or auto-healing against the API.
- **What changed:** unknown, and it's the most valuable question. Did anything change in the last ~15 minutes before onset? Candidates are a deploy, config change, restart, certificate or Fernet rotation, host maintenance, or a network change.
- **Actions already taken:** unknown. Has anyone restarted anything? Restarts are evidence too.

## Evidence
| # | Class | Statement | Source |
|---|---|---|---|
| 1 | Reported | Nobody can create VMs for about 10 minutes | User |
| 2 | Reported | New instances stay in BUILD | User |
| 3 | Reported | Existing VMs look fine | User |
| – | Gap | Instance fault messages, service/agent state, bus and DB health, recent changes | Not shown |

## Dependency path (VM create)
Keystone (with memcached), then Nova API, which writes to the DB. Next come the conductor, the scheduler and Placement, then the cell mapping. After that, nova-compute fetches the image from Glance or the volume from Cinder. Neutron then binds the port and waits for the `network-vif-plugged` event.

Everything inside Nova travels over RabbitMQ.

BUILD means the request got past Keystone and the API. The stall is therefore further along: bus, conductor, scheduler, compute, or Neutron/VIF.

## Hypotheses
| Hypothesis | Would disprove | Cheapest check |
|---|---|---|
| H1: RabbitMQ is unhealthy (partition, alarm, queues with no consumers) | Healthy cluster, consumers present, queues draining | `rabbitmqctl cluster_status` on **each** node |
| H2: Galera has lost quorum or is non-Primary | `wsrep_cluster_status=Primary` and full size on all nodes | `SHOW GLOBAL STATUS LIKE 'wsrep_%'` on each node |
| H3: Nova services (conductor, scheduler, compute) are down or not consuming | All services report `up` and queues have consumers | `openstack compute service list` |
| H4: Networking, so VIF plugging is timing out (P5) | Ports bind and the instance fault shows no VIF error | `openstack server show` fault, `openstack network agent list`, port binding status |
| H5: Certificate expiry or memcached loss | Valid certificates, memcached healthy and fast | `openssl s_client … -enddate` on the bus, DB and API endpoints |
| H6: Scheduling or Placement or cell mapping (P4) | Fault is not "No valid host" or "not mapped to any cell" | Instance fault, `nova-manage cell_v2 list_hosts` |

Existing VMs working is expected under H1, H2, H3, H5 and most of H4. It doesn't separate them.

## Next diagnostics (all read-only)
1. `openstack server list --all-projects --status BUILD`, then `openstack server show <id>` on one instance. This gives the fault, the assigned host (or none), and a `req-…` ID.
   - **No host assigned** points to the scheduler, conductor, bus or Placement.
   - **Host assigned and stuck** points to compute, image, storage or VIF.
2. `openstack compute service list` and `openstack network agent list`. Do services report `up`? A running process isn't proof of health.
3. `rabbitmqctl cluster_status` on every node, checking partitions and alarms. Then `rabbitmqctl list_vhosts` and, for each OpenStack vhost, `rabbitmqctl list_queues -p <vhost> name messages_ready messages_unacknowledged consumers`. Without `-p` you only see vhost `/`, and an empty result there proves nothing. Messages piling up with zero consumers means something stopped processing.
4. Galera `wsrep_%` status on each node: size, Primary status, and flow-control pause.
5. Grep all service logs for the `req-…` ID, and look at conductor, scheduler and nova-compute errors since the onset time.
6. Certificate expiry on the bus, DB and API endpoints. Use `-starttls mysql` for MariaDB.
7. Run the BUILD count (step 1's list) again in a few minutes, and sample queue depth twice. This tells us whether the state is degrading.

## Protect decision
I don't know yet whether the state is getting worse. Compare the BUILD count and queue depth across two samples.
- **If the count is stable or small and the shared components look healthy:** keep investigating. Changing nothing is the safer choice.
- **If the bus or DB is unstable and BUILD/ERROR instances keep piling up:** the platform keeps accepting writes that become orphaned allocations and half-built records. Then controlled degradation is an option: withdraw the API endpoints from the load balancer so the shared components can be recovered on a platform whose state is no longer changing.
  - **Cost:** nobody can use the APIs at all, including reads, until reopening.
  - **Stays protected:** existing VMs keep running. APIs are not the only writers, though: conductors, schedulers and agents keep working, and agents reconnect all at once when the bus returns.
  - **Reopen when:** Galera is Primary and full size, RabbitMQ is whole with consumers connected, all services report `up`, and a test VM passes.
  - **Decision owner:** whoever has authority over production availability. Who is that? Please name them before this is considered.

## Corrective options (not yet authorized)
I'm deliberately not proposing a fix, because no hypothesis is supported yet. Specifically, don't do any of these before the checks above:
- Don't restart RabbitMQ, Galera or Nova services. A restart destroys evidence and causes a reconnect storm.
- Don't purge queues. That discards in-flight operations.
- Don't reset or `forget` RabbitMQ nodes. A partition and a lost node raise the same alert and need opposite handling.
- Don't bootstrap Galera without identifying the most advanced node (seqno, `safe_to_bootstrap`).
- Don't reset instance states or delete the stuck instances. They hold the evidence, and the cause is probably upstream of them.

Once a check supports a cause, I'll lay out options with prerequisites, blast radius, stop conditions, recovery and approver.

## Verification before declaring recovery
- Galera is Primary at full size.
- RabbitMQ is whole, with consumers on the queues.
- All compute services and agents report `up`.
- BUILD instances have either completed or been deliberately cleaned up.
- A test VM is created, reached and deleted.

## Gaps and open questions
1. What is the instance fault message, and is a host assigned?
2. What changed before the onset?
3. Is it all projects, or specific ones, flavors, images or networks? Do boot-from-volume instances behave differently?
4. Is the deployment ML2/OVS or OVN, and how was it deployed (Kolla, other)?
5. Does anything auto-retry or auto-scale against the API?
6. Who owns the decision to withdraw the APIs?

## Follow-up
The containment/structural split can wait until we have a cause. Whatever it turns out to be, the review has to reach the actual cause, or the incident returns.

If you paste the outputs of steps 1–4, I can narrow this to one or two hypotheses quickly.

> Decision support only. State-changing steps above require approval by the accountable owner and should be executed under your change process.

## Turn 2

**User:**

Here is rabbitmqctl cluster_status from each node.
On rabbit-01: running nodes rabbit@rabbit-01, rabbit@rabbit-02; network partitions: rabbit@rabbit-03.
On rabbit-02: running nodes rabbit@rabbit-01, rabbit@rabbit-02; network partitions: rabbit@rabbit-03.
On rabbit-03: running nodes rabbit@rabbit-03; network partitions: rabbit@rabbit-01, rabbit@rabbit-02.
nova-conductor logs show MessagingTimeout. Can I just reset rabbit-03 and rejoin it so we're back up?

**Assistant:**

**No, not yet.** Your output shows a partition, not a lost node, and a reset is the wrong move until we know which side the services are using.

## What the evidence shows
| Class | Statement |
|---|---|
| Observed | `cluster_status` on all three nodes agrees on the split. rabbit-01 and rabbit-02 see each other and report rabbit-03 as partitioned. rabbit-03 is running alone and reports the other two as partitioned. |
| Observed | nova-conductor logs show MessagingTimeout. |
| Hypothesis | The partition explains the stuck BUILDs. Services connected to rabbit-03, or queues whose leader or replicas sit on it, can't complete RPC. This is consistent with the evidence but not yet shown. |
| Gap | Which node each service connects to, where the queues live, the partition-handling setting, and why the link broke. |

rabbit-03 is still running and serving whoever is connected to it. A node that left the cluster would not show this symptom, and the two cases need opposite handling.

## Why "reset and rejoin" is risky now
- `rabbitmqctl reset` wipes rabbit-03's data. It is state-changing and irreversible for that node. If compute agents or services are connected to rabbit-03, or it hosts queue leaders or quorum replicas the services still use, you lose those queues and their in-flight operations.
- The cause isn't known. If the network path between rabbit-03 and the others is still broken, a rejoin fails or the split recurs. A reset would then destroy data and change nothing.
- If `cluster_partition_handling` is `ignore`, the two sides keep diverging while this stays open. Check the setting, because the default and the deployment tool's choice differ.

## Read-only checks to run next
1. **Partition handling and metadata store:** `cluster_partition_handling` in `rabbitmq.conf`, and whether the cluster uses Mnesia or Khepri. Verify for your release.
2. **Where services connect:** the hosts in `transport_url` for the conductor, scheduler and a few computes (redact credentials). Also `rabbitmqctl list_connections -p <vhost> node user peer_host state` on each side, to count connections per node.
3. **Queue placement:** for each OpenStack vhost, `rabbitmqctl list_queues -p <vhost> name type leader members messages_ready messages_unacknowledged consumers`, run from both sides. Look for queues led from or replicated on rabbit-03, and queues with messages but zero consumers.
4. **Partition timing and cause:** the RabbitMQ logs on all three nodes for the first partition event. Then check the network between the rabbit hosts: link state, packet loss, and any firewall, switch or VM-host change near that time.
5. **Whether the state is degrading:** the BUILD count and queue depth, sampled now and again a few minutes later.

## Protect decision
The bus is now evidenced as unstable while the APIs keep accepting boot requests, so every new request can become a half-built instance or orphaned allocation. Controlled degradation is a real option: withdraw the API endpoints from the load balancer.

- **Cost:** no one can use the APIs at all until reopening.
- **Stays protected:** existing VMs keep running.
- **Caveat:** conductors, schedulers and agents keep working, and reconnect storms follow any bus change.
- **Reopen when:** the bus is whole with consumers connected and all services report `up`.
- **Decision owner:** who has authority to withdraw the APIs? I need a named person.

## Corrective options (not authorized, pending checks 1–4)
The right option depends on which side the services use.
- **Services and queues are all on the majority side (01 and 02), and rabbit-03 holds nothing the services need:** the likely path is to fix the network cause, then rejoin rabbit-03. Reset only if it won't rejoin cleanly, and only after you've listed what it hosts.
- **Many services or queues are on rabbit-03:** this needs a plan decided by the owners. Options include moving the clients to the majority side, or choosing the other side. Escalate before any reset.
- **Any option:** state the stop conditions and the recovery path before you act. For a reset the recovery path is none for that node's data. A node dropped for good also needs `forget_cluster_node`, and quorum-queue replicas may need regrowing. Each step needs the approver you name.
- **Purging queues** is a separate decision. It discards in-flight operations, so it needs an explicit sign-off.

## Verification before declaring recovery
- All three nodes report one cluster with no partitions.
- Consumers are connected on the OpenStack queues.
- The conductor's MessagingTimeout errors stop.
- All compute services and agents report `up`.
- The stuck BUILD instances are resolved or deliberately cleaned up.
- A test VM is created, reached and deleted.

## Questions for you
1. What do checks 1–3 show, especially `transport_url` and queue leaders?
2. What changed on the network or hosts around the onset time?
3. Who owns the decision to withdraw the APIs, and who approves any node reset?

Paste those outputs and I'll narrow the options. Once the bus is stable, the review still has to find why the link broke. Otherwise it will happen again.

> Decision support only. State-changing steps above require approval by the accountable owner and should be executed under your change process.

## Turn 3

**User:**

OK. Our platform lead approved it: we pulled the APIs from HAProxy, restarted rabbit-03 and it rejoined, cluster_status now shows all three nodes running and no partitions. Can we put the APIs back in HAProxy now?

**Assistant:**

**Not yet.** A clean `cluster_status` shows the cluster is whole. It doesn't show the platform can provision again, and that was the condition we set for reopening. You can check most of it with the APIs still out of HAProxy.

## What's established
| Class | Statement |
|---|---|
| Observed | `cluster_status` shows three running nodes and no partitions. |
| Reported | The platform lead approved the action, the APIs were pulled from HAProxy, and rabbit-03 was restarted (not reset). |
| Gap | Consumers, queues, services, Galera and the BUILD instances haven't been shown since the restart. |

A restarted node rejoining says nothing about whether the services reconnected. Agents often need time, or a restart, to recover their consumers after a partition.

## Checks before reopening (all read-only)
1. **Bus health:** for each OpenStack vhost, `rabbitmqctl list_queues -p <vhost> name messages_ready messages_unacknowledged consumers`. Look for queues with messages but no consumers, and for backlogs that are draining. Also check `cluster_status` for alarms, and re-run it in a few minutes to confirm the cluster stays whole.
2. **Services reporting:** `openstack compute service list` and `openstack network agent list`. Every compute and agent should be `up`, not just running as a process. Check that the conductors and schedulers log no new MessagingTimeout after the restart.
3. **Galera:** `wsrep_cluster_size`, `wsrep_cluster_status` (Primary) and flow control on each node. We never established whether the DB was involved.
4. **Stuck instances:** list the instances in BUILD and ERROR. Note that the conductor may now replay or process the backlog of old boot requests. Decide with the owners whether to leave them or clean them up. Do that deliberately, not by bulk-deleting.
5. **Placement:** `nova-manage placement audit` without `--delete`, to spot orphaned allocations from the half-built instances.
6. **End-to-end test:** create a test VM, reach it, and delete it. If your API endpoints are only reachable through the VIP, run this against a single backend directly, or reopen to a restricted audience first. Don't skip it.

## Reopening
- Once checks 1–3 are clean, reopen in stages if you can: one API backend first, watch error rates and the BUILD count, then the rest. The platform's state hasn't been changing while the APIs were out, so a controlled return is cheap.
- **Expect a surge.** Users who were blocked will retry at once, on top of agents reconnecting. Watch queue depth and the BUILD count for the first few minutes.
- **Stop conditions:** pull the APIs again if MessagingTimeouts return, consumers drop, or BUILD instances accumulate.
- **Decision owner:** your platform lead authorized the withdrawal, so confirm they also own the reopen.

## Still open
The cause isn't found. We know the partition happened but not why the link between rabbit-03 and the others broke. Check:
- the RabbitMQ logs for the first partition event;
- network changes, link errors or loss around that time;
- the `cluster_partition_handling` setting (`ignore` lets the two sides diverge, while `pause_minority` pauses the minority).

Treat the restart as containment. If the network cause is still there, it will recur. Also decide how to alert on partitions and on queues with no consumers, so you hear about it before users do.

Paste the outputs of checks 1–4 and I'll help you decide whether to reopen.

> Decision support only. State-changing steps above require approval by the accountable owner and should be executed under your change process.
