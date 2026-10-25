**Don't restart RabbitMQ and all the nova services yet.** You have no evidence yet that RabbitMQ is the problem, and a blind restart could make recovery harder.

- **The Galera signal points at the database.** A node in `non-Primary` means it has lost quorum or been partitioned from the other two. `MessagingTimeout` in nova-conductor is only a symptom. It appears when a conductor can't finish an RPC, and a conductor stuck on a degraded DB produces it as readily as a sick bus does.
- **A RabbitMQ restart destroys evidence and adds load.** It drops in-flight operations. Every agent and service reconnects at once, and the APIs keep accepting writes against a database whose state you haven't checked.
- **The reset trap.** If RabbitMQ is partitioned, restarting or resetting the wrong side discards queues the services are still using. Whether it is partitioned is unknown.
- **Restarting everything at once means you can't tell what fixed it.** You also can't tell what you broke.

## Situation
- **Lost:** creating new instances.
- **Still working:** existing VMs. This is the usual control-plane-down, data-plane-up pattern.
- **Impact and timeline:** about 20 minutes so far (reported). Customer and business impact beyond provisioning is unknown.
- **What changed:** unknown. Please tell me about any deploy, config change, network or switch work, cert or key rotation, or host maintenance in the last hour.
- **Actions already taken:** none reported. Tell me if anyone has already restarted anything.

## Evidence
| # | Class | Statement |
|---|---|---|
| 1 | Reported | New instances sit in BUILD, some go to ERROR |
| 2 | Reported | Existing VMs and customer workloads look fine |
| 3 | Reported | nova-conductor logs are full of oslo.messaging `MessagingTimeout` |
| 4 | Reported | One of three Galera nodes has `wsrep_cluster_status = non-Primary` |

Nothing has been shown to me directly yet, and I can't reach your systems. Please paste output and redact credentials such as `transport_url` and DB connection strings.

## Hypotheses
| Hypothesis | Would disprove it | Discriminating check (read-only) |
|---|---|---|
| **H1: Galera has lost quorum or is partitioned.** Nova DB writes stall or fail, and conductors time out. Note that 1 of 3 non-Primary should leave the other two as Primary. | The other two nodes are Primary with cluster size 2 and the endpoints actually in use (HAProxy/VIP) point at them. | `SHOW STATUS LIKE 'wsrep_cluster%'` and `wsrep_local_state_comment` on all 3 nodes. Check which backend HAProxy considers healthy. Check whether nova points at the non-Primary node. |
| **H2: RabbitMQ is partitioned or unhealthy.** RPC replies are lost. | `cluster_status` agrees on every node, there are no partitions or alarms, and queues have consumers. | `rabbitmqctl cluster_status` **from each node**. Run `rabbitmqctl list_queues name messages consumers` and look for queues with messages but no consumers. Check the logs for partition events. |
| **H3: A common network problem** is hitting both the DB and the bus. This would explain the timing, and Galera dropping a node is itself consistent with it. | Inter-node latency and loss are normal, and switch and interface logs are clean. | Ping/loss between the controllers. Check kernel and switch logs around the time the Galera node dropped. |
| **H4: The problem is in Nova itself.** A conductor or scheduler is wedged, or a cell is misconfigured. | The same timeouts show up in other services (neutron, cinder). | Compare the `MessagingTimeout` pattern across services. Check `openstack compute service list` and `nova-manage cell_v2 list_cells`. |

H1 and H3 are the leading candidates because they are the only abnormal signals reported so far, but none is established yet.

## Next diagnostics (all read-only, about 5 minutes)
1. Galera status on all three nodes (see H1). Also check `wsrep_cluster_state_uuid` and `wsrep_last_committed`. Do **not** bootstrap or restart anything based on this.
2. `rabbitmqctl cluster_status` on each node, plus `rabbitmqctl list_queues` (see H2).
3. Take a count of instances in BUILD/ERROR now (`openstack server list --all-projects --status BUILD`), and again in 5 minutes. This tells you whether the state is getting worse.
4. Pick one failed instance. Get its `req-...` ID and fault message, and follow it through nova-api → conductor → scheduler → compute.
5. `openstack compute service list` and `openstack network agent list` to see who is reporting.
6. Collect logs from the failing period before any restart.

## Protect decision
This is a check, not an assumption. If the check in step 3 shows the BUILD/ERROR count is growing, the platform is accumulating half-built instances and orphaned allocations. In that case I'd suggest a **controlled degradation**:
- **Action:** withdraw the nova/neutron/cinder API endpoints from the load balancer.
- **Cost:** API reads and writes stop for everyone, existing VMs keep running, and you need to notify users.
- **Protects:** the platform state stops changing while you recover the shared components.
- **Caveat:** conductors, schedulers and agents keep running, and the bus restart will trigger a reconnect storm.
- **Reopen condition:** the verification checks below pass.
- **Decider:** your manager or incident commander should own this call. Who has that authority at your site?

If the count is flat, keep investigating. Provisioning is already down, so a few more minutes of evidence costs little.

## Corrective options (not yet authorized)
Pick one only after the diagnostics identify the cause.

- **Galera is genuinely non-Primary (H1):**
  - **First choice:** let the node rejoin and resync on its own once the network is fixed.
  - **Don't:** bootstrap it. Bootstrapping the wrong node discards committed transactions.
  - **Before any bootstrap:** identify the most advanced node (seqno / `safe_to_bootstrap` / `--wsrep-recover`).
  - **Approver:** DBA or platform lead.
  - **Recovery:** none if you pick the wrong node.
- **RabbitMQ is partitioned (H2):**
  - **First:** escalate and establish which side the services use.
  - **Then:** decide on stopping the APIs.
  - **Don't:** reset nodes before that.
  - **Purging queues:** this loses in-flight operations. It can be the right trade, but it needs an explicit decision.
  - **Approver:** platform lead.
- **Service restarts:** these are for after a confirmed cause, not a first move. Do them as one planned sequence (APIs out, bus, DB, verify, reopen), not several uncoordinated restarts.

Every one of these is state-changing and needs a named approver.

## Verification before declaring recovery
- Galera: all nodes Primary, expected cluster size, synced.
- RabbitMQ: whole cluster with no partitions, and queues have consumers.
- All compute services and network agents reporting up.
- A test VM is created, reached and deleted, and the BUILD/ERROR count stops growing.
- Clean up the instances stuck in BUILD/ERROR and any stale Placement allocations (`nova-manage placement audit` is read-only).

## For your manager
"Provisioning is down and existing workloads are unaffected. A database node has dropped out of the cluster. We're spending five minutes confirming whether the database or the message bus is the cause before restarting anything, because a wrong restart can lose data and extend the outage."

## Follow-up (after the incident)
- Treat the restart that "fixed it" as containment, not as a cause.
- Find out why the Galera node dropped, whether that was network, resources or a config change, and whether a partition is the common cause.
- Review alerting on Galera cluster status and RabbitMQ partitions.

Paste the Galera and RabbitMQ output from each node and I'll narrow this down fast.

> Decision support only. State-changing steps above require approval by the accountable owner and should be executed under your change process.