## Turn 1

**User:**

Production OpenStack: since about 10 minutes nobody can create VMs, new instances stay in BUILD. Existing VMs look fine. Where do I start?

**Assistant:**

## Situation
- **Capability lost:** VM provisioning. New instances sit in BUILD.
- **Still works (Reported):** existing VMs. That fits a control-plane problem, not a data-plane one.
- **Unknown, so please tell me:**
  - What changed in the last ~30 minutes (deploy, config, cert or Fernet rotation, host or network work, a restart)?
  - Who is affected and how critical they are.
  - Whether anyone has already restarted or reset anything.
  - Your release, deployment tool, and Neutron backend (OVS or OVN).
  - Whether Galera and RabbitMQ are clustered.

## Evidence so far
| # | Class | Statement | Source |
|---|---|---|---|
| 1 | Reported | Nobody can create VMs; new instances stay in BUILD | You |
| 2 | Reported | Onset about 10 minutes ago | You |
| 3 | Reported | Existing VMs look fine | You |

I have shown no telemetry or commands, so everything else is a gap.

## First thing to do: freeze the situation and compare counts
Run these now. They are read-only:
1. `openstack server list --all-projects --status BUILD` and again with `--status ERROR`. Note the count and time. Repeat in a few minutes to see whether the count is growing.
2. `openstack server show <one stuck id>` and look at `fault`, `host` and `OS-EXT-SRV-ATTR:host`. Is `host` empty, or a compute?

Where it is stuck tells you which half of the path to look at.
- **No host assigned:** the problem is before the compute. Suspect the API, conductor, scheduler, Placement, the bus or the DB.
- **Host assigned:** the problem is on or after the compute. Suspect Glance, Neutron port binding or VIF plugging, or Cinder.

## Hypotheses
| Hypothesis | Supports | Would disprove | Check (read-only) |
|---|---|---|---|
| RabbitMQ unhealthy: partition, alarm, or consumers gone | The scheduler, conductor and computes all need the bus, and running VMs don't | Queues have consumers and no backlog | `rabbitmqctl cluster_status` on each node. `rabbitmqctl list_vhosts`, then `list_queues -p <vhost> name messages_ready messages_unacknowledged consumers` for each vhost. Without `-p`, an empty list proves nothing. |
| Galera non-Primary or flow-controlled | A non-Primary node refuses even reads. The instance creation write path is dead, but running VMs are not affected. | `wsrep_cluster_status` is Primary, full size, and flow control is not paused | `SHOW GLOBAL STATUS LIKE 'wsrep_%'` on every node |
| Expired TLS cert or broken Fernet or Keystone | Sudden onset, which is typical of a cert expiry | Tokens issue fine and cert dates are in the future | `openstack token issue`, then the `openssl s_client … -enddate` checks on endpoints, the bus and the DB. Compare Fernet repository checksums across Keystone nodes. |
| memcached down | Token validation becomes slow or fails | API latency is normal | memcached availability and latency |
| Scheduler or Placement problem, or hosts unmapped to a cell | "Capacity exists but nothing lands" | The instance gets a host | Fault message. `nova-manage cell_v2 list_hosts`. `nova-manage placement audit` (**without** `--delete`). |
| Neutron or VIF plugging (BUILD until `vif_plugging_timeout`) | Instances have a host but sit in BUILD | Ports bind and `network-vif-plugged` arrives | `openstack network agent list`, port status and binding host, neutron logs |
| Glance or Cinder (image fetch or volume) | Host is assigned and the stall is in the compute log | Image download works | nova-compute log for the request ID |

Also run `openstack compute service list` and `openstack network agent list`. If everything is down at once, suspect a shared component (the bus or the DB) rather than several separate failures.

**Follow one request.** Take the `req-…` ID of a failed create and grep it across the nova-api, conductor, scheduler and compute logs. The last service that logged it is where it died.

## Protect decision
Check whether the state is degrading: is the BUILD/ERROR count rising, are queues backing up without consumers, are orphaned allocations appearing? I haven't seen any of that yet.

- **If it's stable and impact is limited:** keep gathering evidence. That is the safer choice.
- **If the shared components (bus or DB) are unstable and the APIs keep accepting writes:** consider **controlled degradation**. This means withdrawing the API endpoints from the load balancer so recovery happens on a platform whose state has stopped changing.
  - **Cost:** the API is down for everyone, including operations on existing VMs.
  - **Cautions:** it does not stop conductors, schedulers or agents. Expect a reconnect storm when the bus returns.
  - **Still needed:** a named person who has authority to make this call. Who is it?

## Do not do yet
- **No restarts** of RabbitMQ, MariaDB or the Nova services without a hypothesis. They destroy evidence and can make things worse.
- **No `rabbitmqctl reset` or `forget_cluster_node`** until you know whether it is a node loss or a partition. They need opposite handling.
- **No Galera bootstrap** until you have identified the most advanced node (seqno, `safe_to_bootstrap`, `--wsrep-recover`). The wrong node loses committed transactions.
- **No queue purge** without a decision. It discards in-flight operations.
- **No `server set --state` and no deleting stuck instances.** Hold off until you understand why they are stuck, and don't touch the database directly.
- **Don't change several things at once.** You won't be able to tell what fixed it.

## Verification before declaring recovery
- Galera is full size and Primary.
- RabbitMQ is whole, with consumers connected on the queues.
- All compute services and network agents report up.
- A test VM is created, reached, and deleted.
- The stuck BUILD instances are dealt with separately. They will not fix themselves.

## What I need from you
Paste the output of these, with passwords and tokens redacted (including `transport_url` and DB connection strings):
1. The BUILD/ERROR counts and one `server show` with its fault.
2. `openstack compute service list` and `openstack network agent list`.
3. `rabbitmqctl cluster_status` and the Galera `wsrep_%` status.
4. The log lines for one failed `req-…` ID.
5. Answers on what changed, who is affected, and who decides on stopping the APIs.

I'll narrow the hypotheses from there.

> Decision support only. State-changing steps above require approval by the accountable owner and should be executed under your change process.

## Turn 2

**User:**

Here is rabbitmqctl cluster_status from each node.
On rabbit-01: running nodes rabbit@rabbit-01, rabbit@rabbit-02; network partitions: rabbit@rabbit-03.
On rabbit-02: running nodes rabbit@rabbit-01, rabbit@rabbit-02; network partitions: rabbit@rabbit-03.
On rabbit-03: running nodes rabbit@rabbit-03; network partitions: rabbit@rabbit-01, rabbit@rabbit-02.
nova-conductor logs show MessagingTimeout. Can I just reset rabbit-03 and rejoin it so we're back up?

**Assistant:**

**Not yet.** Don't reset rabbit-03 until you know which side the services are talking to. What you pasted is a partition, not a node that left.

## What the output shows (Observed)
- rabbit-01 and rabbit-02 see each other and list rabbit-03 as partitioned.
- rabbit-03 sees only itself and lists 01 and 02 as partitioned.
- The cluster has split into two sides: {01, 02} and {03}.
- Conductor logs show `MessagingTimeout`. That fits some services publishing to queues whose replies or consumers sit on the other side. It is still a hypothesis, not proof.

If this were a node loss, the other nodes would just show rabbit-03 as not running, and rabbit-03 would not be up and reporting its own view. Here both sides are alive and each sees the other as partitioned.

## Why reset is risky here
- `rabbitmqctl reset` wipes rabbit-03's data. That includes any queues and quorum-queue replicas it hosts, and any in-flight messages.
- If some conductors, schedulers or computes are connected to rabbit-03 and are active there, a reset discards what they are using.
- Reset is irreversible for that node's data.
- Your `transport_url` and load-balancer setup decide who is connected where. I haven't seen them.

## Read-only checks first
1. **Which side do services use?** (read-only)
   - Look at `transport_url` in nova, neutron and the other services (redact credentials). Does it list all three nodes, or a VIP?
   - On each rabbit node: `rabbitmqctl list_connections name peer_host user state` and `rabbitmqctl list_consumers -p <vhost>`.
   - A rabbit-03 with many connections or consumers is a different decision from one with almost none.
2. **Partition handling and metadata store.** Check `cluster_partition_handling` (`ignore`, `pause_minority` or `autoheal`) and whether the cluster uses Mnesia or Khepri. This tells you whether the minority side should have paused itself. Rabbit-03 appears to be running, so I'd want to know why.
3. **Queues on each side.** For each OpenStack vhost, on each node: `rabbitmqctl list_queues -p <vhost> name type leader members messages_ready messages_unacknowledged consumers`. Look for queues whose leader or members sit on rabbit-03, and for quorum queues that have lost their majority.
4. **Partition time and cause.** Look at the rabbit logs on all three nodes for the partition event and its timing, then check the network between rabbit-03 and the others (switch, link, MTU, firewall). Compare against the time of the first MessagingTimeout. A partition leaves a cause behind, such as a flapping link, a host pause or a network change, and a reset won't remove it.
5. **Is the state degrading?** Compare the BUILD/ERROR counts and queue depths now against a few minutes ago.

## Options, once the checks are in

| Option | Applies if | Cost / risk |
|---|---|---|
| **A. Keep investigating, change nothing** | Impact is limited and state is stable | The outage continues. Nothing is lost. |
| **B. Controlled degradation, then recover the bus** | Instances keep accumulating in BUILD or the DB is also affected | API outage for everyone. It does not stop conductors, schedulers or agents. |
| **C. Bring rabbit-03 back into the cluster** | Services use the {01,02} side, and rabbit-03 is shown to hold nothing needed | State-changing. The recovery steps depend on the partition handling and queue type. |

For option C, as I understand the book's guidance, the exact procedure depends on your release and whether the cluster uses Mnesia or Khepri. Whether it's a plain restart of rabbit-03 or a reset, it is state-changing. So it needs, in order:
- **Prerequisites:** the checks above done, an inventory of queues and quorum replicas hosted on rabbit-03, and a decision on what in-flight loss is acceptable.
- **Approver:** your platform lead, or whoever owns the bus. Who is that?
- **Stop conditions:** stop if consumers fail to reconnect, a queue shows no leader, or the partition recurs.
- **Recovery:** none for rabbit-03's local data once reset.
- **Verification:** `cluster_status` shows all three nodes running with no partitions, consumers are connected on the queues, all compute services and agents report up, and a test VM is created, reached and deleted.
- **After the bus comes back:** expect every agent to reconnect at once.

## Also keep in mind
- A restart or reset fixes the symptom, but the cause of the partition stays. If it recurs, repeating the reset is the recurring-workaround pattern. Find the network cause.
- Even after the bus is fixed, instances that got stuck in BUILD are a separate cleanup. Don't reset their state until you've verified what they actually are.

## What I need next
1. The `transport_url` host list (credentials redacted) and whether a load balancer or VIP sits in front of rabbit.
2. Output of `list_connections` and the queue listing from each node.
3. `cluster_partition_handling`, and the Mnesia vs Khepri answer.
4. The rabbit log lines around the partition event, and anything that changed on the network or on rabbit-03 about 10 minutes before.
5. The BUILD count now versus earlier, and who has authority to decide on stopping the APIs.

> Decision support only. State-changing steps above require approval by the accountable owner and should be executed under your change process.

## Turn 3

**User:**

OK. Our platform lead approved it: we pulled the APIs from HAProxy, restarted rabbit-03 and it rejoined, cluster_status now shows all three nodes running and no partitions. Can we put the APIs back in HAProxy now?

**Assistant:**

**Not yet.** `cluster_status` is a start, but it doesn't show the capability is back. Reopen when the checks below pass. I'm relying on your report for the restart and the rejoin, so I'm treating them as Reported, not Observed.

## Verify before reopening (all read-only except the test VM)
1. **RabbitMQ is really healthy.**
   - `cluster_status` on each node agrees: three running nodes, no partitions, no alarms (memory or disk).
   - For each OpenStack vhost, `list_queues -p <vhost> name type leader members messages_ready messages_unacknowledged consumers` shows queues present, with consumers on them. Look for queues without a leader, quorum queues missing members, and a backlog that isn't draining.
   - Check the rabbit logs for any new partition events since the restart.
2. **Galera is fine too.** `SHOW GLOBAL STATUS LIKE 'wsrep_%'` on every node: full cluster size, Primary, flow control not paused. I haven't seen any Galera output so far, so don't assume it.
3. **Services reconnected.**
   - `openstack compute service list` and `openstack network agent list` show everything up, with fresh heartbeats.
   - The conductor and scheduler logs show no new `MessagingTimeout` after the rejoin. Old ones in the log don't count; check the timestamps.
   - Reconnects can lag, so wait a few minutes and check again rather than checking once.
4. **End-to-end test, with the APIs still out of HAProxy.** Before reopening to everyone, run a test VM through a single API node or an internal path, if you can reach one:
   - create it, confirm it goes ACTIVE, reach it (ping or console), then delete it;
   - confirm the port is bound and the instance cleans up fully.

   If you can't reach the APIs without the load balancer, put back one API node first and use that as the test. Which of those you have is for your platform lead to decide.

## The stuck instances
The instances that were in BUILD before are a separate matter. Compare their count and states now against earlier.
- Some may fail to ERROR on their own, and some may stay in BUILD.
- Don't reset state or delete anything in bulk yet. Look at each one's fault first and decide who owns the cleanup.
- Once things are back, run `nova-manage placement audit` (without `--delete`) to see whether any allocations were orphaned.

## Reopening
Reopen in steps if HAProxy lets you, and watch error rates and the BUILD count as each step goes in:
1. One API backend per service.
2. Then the rest, if the test VM succeeded and nothing regressed.

**Stop conditions:** a new MessagingTimeout, a queue backlog, instances accumulating in BUILD, or a repeat partition. If any of those appear, pull the APIs again and go back to investigating.

## Tell users
Say when the APIs are back and that instances created during the outage may need to be recreated. Who tells them, and who decides the APIs reopen?

## The cause is still open
The restart is containment. It doesn't tell you why rabbit-03 partitioned. Until that's known, this can recur. Next:
- Find the network or host cause around the partition time (link flaps, a host pause, a firewall or MTU change).
- Check `cluster_partition_handling`: why wasn't the minority side paused?
- Add monitoring for partitions, consumer counts and queue depth, so you aren't first told by users.
- Write the sequence down in a runbook. If it recurs and the answer is the same restart each time, that's the recurring-workaround pattern, and I'd treat it as one.

Send me the queue listing, the service list output and the test VM result, and I'll help you confirm the verification is complete.

> Decision support only. State-changing steps above require approval by the accountable owner and should be executed under your change process.
