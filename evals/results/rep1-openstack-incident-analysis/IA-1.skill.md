**Don't restart anything yet.** Spend about 5 to 10 minutes on read-only checks first. The restart could make this worse, and it would destroy the evidence you need to find the cause.

## Situation
- **Lost:** VM provisioning. New instances stay in BUILD or go to ERROR.
- **Still working:** running workloads (reported). That fits a control-plane problem and not a data-plane one.
- **Unknown:** business impact beyond provisioning, what changed ~20 minutes ago, and who can authorize a disruptive action.

## Evidence
| Class | Statement |
|---|---|
| Reported | Onset about 20 minutes ago. Instances are in BUILD, some in ERROR. |
| Reported | nova-conductor logs are full of `MessagingTimeout`. |
| Reported | One of three Galera nodes has `wsrep_cluster_status = non-Primary`. |
| Gap | RabbitMQ state, the other two Galera nodes, and what changed. |

## Why a blind restart is risky
- **Two shared components may be involved, and the Galera state is unclear.** A non-Primary node usually means it lost contact with the others. If the other two are still Primary, you have quorum and the database may be fine. If the network split three ways, or two nodes are non-Primary, writes are blocked. These cases need opposite handling.
- **A network event could be the shared root cause.** One partition could explain both the bus timeouts and the Galera split. Restarting RabbitMQ would not fix that, and it would also drop in-flight state.
- **A RabbitMQ partition is not the same as a node that left the cluster.** Resetting or restarting nodes on the wrong side discards queues the services are still using.
- **Restarting all the Nova services at once makes every agent and conductor reconnect together.** That reconnect storm can overload a bus that is already struggling.
- **A bounced Galera node can force a full-cluster bootstrap.** Bootstrapping the wrong node loses committed transactions.
- **While the API keeps accepting builds, state keeps degrading.** Half-built instances and orphaned Placement allocations make recovery slower.

## Hypotheses
| Hypothesis | Discriminating check |
|---|---|
| Network event or partition hits both the bus and Galera | Compare `rabbitmqctl cluster_status` and `wsrep_*` on each node. Look for the same timestamp in the logs. |
| RabbitMQ partitioned, or queues without consumers | `cluster_status` from each node, plus partition and alarm events. |
| Galera lost quorum, or the LB is sending writes to the non-Primary node | `wsrep_cluster_size` and `wsrep_cluster_status` on all 3 nodes. Check which backend the LB uses. |
| Memory or disk alarm on RabbitMQ is blocking publishers | The alarms section of `cluster_status`, and `df` and memory on the bus nodes. |
| Expired certificate on the bus or database | Certificate expiry checks. |

## Read-only diagnostics, in order
Please redact `transport_url` and DB connection strings before pasting anything.
1. **Galera, on each of the 3 nodes:** `SHOW GLOBAL STATUS LIKE 'wsrep_%';`. I need `cluster_size`, `cluster_status`, `local_state_comment` and `flow_control_paused`.
2. **RabbitMQ, from each node:** `rabbitmqctl cluster_status`. I need members, partitions and alarms.
3. **Per-vhost queues:** `rabbitmqctl list_vhosts`, then `list_queues -p <vhost> name messages_ready messages_unacknowledged consumers`. Without `-p`, only the default vhost is listed. Few queues there does not mean the queues are gone.
4. **Services:** `openstack compute service list` and `openstack network agent list`.
5. **Trend:** `openstack server list --all-projects --status BUILD` now and again in 3 to 5 minutes. This tells us whether the state is degrading.
6. **What changed:** deployments, config changes, network or switch work, certificate rotation, or host maintenance in the hour before onset. Pull the timestamp of the first `MessagingTimeout` and the first Galera state change.
7. **One failed request:** the `req-...` ID of an ERROR instance, followed through the nova-api, conductor, scheduler and compute logs.

## Protect decision
Check first whether instances are piling up in BUILD and ERROR. If they are, the option is **controlled degradation**:
- Withdraw the nova, neutron and cinder API endpoints from the load balancer so no new state is created while you recover the shared components.
- **Cost:** all API operations stop, including customers' reads and deletes. Running VMs are unaffected.
- **Cautions:** conductors, schedulers and agents keep running. Expect a reconnect storm when the bus comes back.
- **Reopen condition:** the verification checks below pass.
- **Decision owner:** I don't know who this is for you. Please tell me. Your manager's pressure for speed is a reason to get this authority clear now.

If the count is stable and impact is limited, keep investigating. A few more minutes of evidence is cheaper than a wrong restart.

## Corrective options (not yet authorized)
I'd decide these only after the diagnostics, as one planned sequence with its verification defined up front:
- **Galera is Primary on 2 of 3:** fix the LB backend or rejoin the third node. Do not bootstrap.
- **Galera has no Primary at all:** stop the API first. Then find the most advanced node (`grastate.dat` seqno and `safe_to_bootstrap`, or `--wsrep-recover`) before any bootstrap. Require a named owner.
- **RabbitMQ partition:** stop the API first. Establish which side the services use. Escalate before any node reset. Purging queues loses in-flight operations, and the owner must accept that.
- **RabbitMQ healthy, only some services are stuck:** restart the affected services one at a time, with a hypothesis for each.

## Verification before declaring recovery
- Galera at full size on all nodes and Primary.
- RabbitMQ whole, queues recreated, consumers connected.
- All compute services and network agents reporting up.
- **A test VM created, reached and deleted.** Process health alone is not enough.
- Then clean up BUILD and ERROR leftovers, and run `nova-manage placement audit` without `--delete`.

## Gaps
What changed in the last hour. The RabbitMQ and Galera outputs. The LB write-backend configuration. Whether your control plane runs in containers. Who owns the stop decision.

Paste the outputs from steps 1 to 3 and the change history and I'll narrow this to a recommendation.

> Decision support only. State-changing steps above require approval by the accountable owner and should be executed under your change process.