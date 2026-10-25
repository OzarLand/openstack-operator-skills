Don't do the blanket restart yet. Your Galera symptom is the likelier root cause, and restarting RabbitMQ and all of nova won't fix a database problem. It also adds risk: in-flight messages are lost, instances stuck mid-build end up in odd states, and everything reconnects at once.

**1. Check Galera first (about 2 minutes).** Run this on all three nodes:
```
mysql -e "SHOW STATUS WHERE Variable_name IN ('wsrep_cluster_status','wsrep_cluster_size','wsrep_local_state_comment','wsrep_ready','wsrep_cluster_conf_id')"
```
- **Two nodes Primary with size 2, one non-Primary:** the cluster still has quorum and the DB is fine. The bad node is probably still in the HAProxy backend, so nova gets "WSREP has not yet prepared node" errors on a share of its queries. Take that node out of HAProxy (or stop mariadb on it) and see whether provisioning recovers. Then investigate that node separately, for example a network partition or a hung `wsrep` state. It will usually rejoin through IST/SST once its connectivity is fixed.
- **No node Primary, or only one node up:** the cluster has lost quorum. Don't restart everything. Find the most advanced node by comparing `seqno` in `/var/lib/mysql/grastate.dat` (or run `mysqld --wsrep-recover`). Bootstrap only from that node, then rejoin the others. Bootstrapping from the wrong node loses transactions.

**2. Check RabbitMQ in parallel.** The `MessagingTimeout` errors could come from a broken DB or from a broken broker.
```
rabbitmqctl cluster_status        # look for partitions
rabbitmqctl list_alarms           # memory/disk alarms block publishers
rabbitmqctl list_queues name messages consumers | sort -k2 -nr | head
```
- Any alarm or partition is a real finding. A disk or memory alarm alone explains conductor timeouts.
- If one broker node is partitioned or bad, restart only that node, not the whole cluster.
- Many messages with 0 consumers on `conductor` or `scheduler` queues points to stuck consumers, not a dead broker.

**3. Check nova.** Look at `openstack compute service list` and the conductor logs. If the DB is healthy and RabbitMQ is clean but conductors are still wedged, restart `nova-conductor` and `nova-scheduler`, one node at a time. Don't restart them all at once.

**4. Clean up afterwards.** Instances stuck in BUILD won't recover on their own. Use `nova reset-state --active` or delete and recreate them, and check for orphaned port or volume allocations.

If you have to act before you've diagnosed anything, pulling the non-Primary node out of HAProxy is the lowest-risk single move. It's reversible and it addresses the most likely cause.

For your manager: the control plane is degraded and running workloads are unaffected. You're isolating the failing component first, because a blind restart of the messaging and compute services could turn a 20-minute provisioning outage into a longer one.

If you paste the Galera status output from all three nodes and the `rabbitmqctl cluster_status` and `list_alarms` output, I can help you work out which case you're in.