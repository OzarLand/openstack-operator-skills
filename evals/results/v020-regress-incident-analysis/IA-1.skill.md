# Don't restart RabbitMQ and all the Nova services yet

An all-at-once restart is the move most likely to make this worse and hardest to attribute. Ten minutes of read-only checks should show whether it is needed at all.

## Why not restart yet

- **Restarts may not help.** If RabbitMQ is partitioned or blocked by an alarm, restarted Nova services reconnect and wait again. If the bus is fine and the fault is a database or consumer problem, a bus restart changes nothing.
- **A bus restart destroys evidence and loses work.** In-flight requests are lost, and every agent reconnects at once. A partition on a Khepri-based RabbitMQ may show no "Network Partitions" entry, and it can heal on its own.
- **The Galera node may be unrelated.** One node `non-Primary` with the other two `Primary` is the "one node" case and needs no bootstrap or recovery. It matters only if the other two are also non-Primary, or if your services are pointed at the bad node.
- **A common cause is possible.** One network event could have hit both the bus and Galera, and restarts won't fix that.

## Situation

| Item | Detail |
|---|---|
| Capability lost | VM provisioning |
| Still working | Running VMs (reported) |
| Unknown | Business impact, what changed in the last hour, who owns the decision to degrade or restart |

## Evidence

| # | Class | Statement |
|---|---|---|
| 1 | Reported | New instances stay in BUILD, some go to ERROR, starting about 20 minutes ago |
| 2 | Reported | nova-conductor logs are full of `oslo.messaging MessagingTimeout` |
| 3 | Reported | One of three Galera nodes shows `wsrep_cluster_status = non-Primary` |
| 4 | Reported | Running workloads are fine |
| 5 | Assumption | RabbitMQ is the bus, with 3 nodes. Not stated. |
| 6 | Assumption | Kolla-Ansible deployment. Not stated. |

None of this is Observed yet. I haven't seen any output.

## Hypotheses

| Hypothesis | Disproved if | Check |
|---|---|---|
| H1: RabbitMQ partitioned, blocked by an alarm, or a node missing | All nodes agree on membership, with no alarm and no blocked connections | `cluster_status` on every node |
| H2: Consumers gone (conductor or scheduler running but not consuming) | Queues have consumers | `list_queues name messages consumers` |
| H3: Galera is the problem: the other two nodes are also non-Primary, or services use the bad node | The other two are `Primary` and `Synced`, and the DB path points at them | Status on all three nodes, plus ProxySQL or HAProxy backend state |
| H4: Common network cause (a switch or segment event hit both) | Inter-controller connectivity is clean | Node-to-node pings and ports 5672, 25672 and 4567 |
| H5: A recent change (config, deploy, certs, host work) | Nothing changed | Ask your team and check the deploy log |

## Next diagnostics (all read-only)

Run these on every controller. On Kolla-Ansible, prefix with `sudo docker exec rabbitmq` or `sudo docker exec mariadb`.

1. **RabbitMQ**
   - `rabbitmq-diagnostics cluster_status` on each node. Nodes disagreeing on who is running means a partition.
   - `rabbitmq-diagnostics check_local_alarms`
   - `rabbitmqctl list_connections name state`, looking for `blocked`
   - `rabbitmqctl list_queues name messages consumers`, looking for `conductor` or `scheduler` queues with messages and 0 consumers
2. **Galera, on all three nodes**
   - `SHOW STATUS WHERE Variable_name IN ('wsrep_cluster_status','wsrep_cluster_size','wsrep_local_state_comment','wsrep_ready','wsrep_last_committed')`
   - Which backend ProxySQL or HAProxy is sending writes to
3. **Nova**
   - `openstack compute service list`. Computes `down` while their processes run suggests the conductor can't reach the bus.
   - `docker ps -a --filter name=nova_conductor --filter name=nova_scheduler`
4. **One failed request**
   - Pick one ERROR instance. Get its `req-…` ID and fault message (`openstack server show`) and follow it through the nova-api, conductor and scheduler logs.
5. **Network**
   - Connectivity between controllers on 5672, 25672 and 4567, plus switch or bond errors.

Please redact `transport_url`, DB connection strings and passwords before pasting anything.

## Protect decision

Check whether the state is getting worse. Count instances in BUILD and ERROR now and again in a few minutes:

```
openstack server list --all-projects --status BUILD -f value | wc -l
```

If the count is growing, or you see half-built instances and orphaned allocations, the next option is **controlled degradation**:

- Withdraw the Nova, Neutron, Cinder and Glance APIs from HAProxy, or set them to `MAINT`. Keep Placement and Keystone running.
- **Cost:** nobody can create or modify anything until it is reopened. Running VMs are unaffected.
- **Reopen condition:** the verification below passes.
- **Decision owner:** I don't know who this is. It needs your manager or the on-call incident commander to authorise it as a protection decision. Who has that authority?

If the count is stable, keep investigating. Stopping the APIs does not stop conductors, schedulers or agents.

## Corrective options (none authorised yet)

Which fix applies depends on what the diagnostics show:

| Finding | Fix | Notes |
|---|---|---|
| One Galera node down, the other two `Primary` | Fix the node, then start it through its service unit | No bootstrap and no `mariadb-recovery`. Recovery stops the healthy nodes too. |
| All Galera nodes non-Primary | Repair the network first | Bootstrap only on the node with the highest `wsrep_last_committed`. This is destructive: transactions only on the other side are lost. |
| RabbitMQ node missing | Start that node through its service unit | Quorum replicas catch up. |
| RabbitMQ alarm | Free memory or disk, or fix the consumer behind the backlog | It clears on its own once below the limit. |
| Partition | Repair the network and let it heal | Do not reset any node before re-checking all of them. |
| Consumers gone | Restart that service per controller, after reading its log | In-flight requests fail. |
| RabbitMQ reset or purge | Last resort only | On a current Kolla-Ansible with Khepri, `rabbitmq-reset-state` failed on a lab and left a node outside the cluster. Rehearse it first. |

Each state-changing step needs a named approver, a stop condition and a recovery path. Don't combine several changes in one go, or you won't be able to tell which one worked.

If you still end up restarting services, do it in order. Fix the bus and the database first. Then restart conductors and schedulers. Then restart computes and agents in batches. Don't restart anything while RabbitMQ is partitioned or blocked.

## Verification before declaring recovery

- Galera: all 3 nodes `Primary`, `Synced`, same cluster size.
- RabbitMQ: one cluster, no alarm, no queue with messages and 0 consumers.
- `openstack compute service list` and `openstack network agent list` show everything up.
- A test VM is created, reached and deleted.
- BUILD and ERROR counts are no longer growing.
- Instances left in ERROR or BUILD from the outage are listed for cleanup. Don't bulk-delete them without checking each one.

## What I need from you

1. Output of the RabbitMQ and Galera checks above.
2. What changed in the last hour or two: deploy, config, certs, network or host work, or an earlier restart.
3. Deployment type (Kolla-Ansible?), the OpenStack and RabbitMQ versions, and whether RabbitMQ uses Khepri or Mnesia.
4. Whether the BUILD and ERROR counts are growing.
5. Who can authorise stopping the APIs.

For your manager, here is the short version: "The cause isn't established yet. Restarting blind could lose in-flight work and make recovery slower. We're running a few minutes of read-only checks first and will decide on a fix from the results."

> Decision support only. State-changing steps above require approval by the accountable owner and should be executed under your change process.