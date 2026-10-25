**Don't restart everything yet.** A blanket restart of RabbitMQ and all the nova services probably won't fix this, and it could make things worse.

The Galera node reporting non-Primary is the most likely root cause. Nova-conductor does all the DB access, so a DB problem shows up as conductor timeouts, and VMs that are already running don't touch the control plane. Restarting RabbitMQ also drops in-flight messages and makes every service reconnect at once. If the DB is still broken, you'll just get a stampede and more instances stuck in ERROR.

**1. Check Galera on all three nodes (about 2 minutes)**
```sql
SHOW STATUS WHERE Variable_name IN ('wsrep_cluster_status','wsrep_cluster_size',
  'wsrep_local_state_comment','wsrep_ready','wsrep_cluster_conf_id');
```
- **The other two nodes are Primary with size 2.** You still have quorum. The bad node is a minority that got partitioned.
  - Check HAProxy and confirm that node is out of the backend. If nova is still routed to it, that's your outage, so drain it now.
  - Look for a network problem between the nodes (ports 4567, 4568 and 4444) and read the node's mysqld log.
  - Once it's out of the pool, restart mariadb on that node only. It will rejoin through IST or SST.
- **No node is Primary.** The cluster has lost quorum entirely. Don't restart them all at once.
  - Find the node with the highest seqno (`galera_recovery` or `grastate.dat`).
  - Bootstrap only that node, then join the others one at a time.
  - Never bootstrap two nodes, or you'll split-brain.
- Never wipe or force `wsrep_provider_options="pc.bootstrap=1"` on a node until you know which one has the latest data.

**2. Check RabbitMQ (in parallel)**
```
rabbitmqctl cluster_status        # look for partitions and alarms (disk/memory)
rabbitmqctl list_queues name messages consumers | sort -k2 -n -r | head
```
Only touch RabbitMQ if you see a partition, a resource alarm, or queues with zero consumers. If so, restart the minority or affected node, not the whole cluster. If a network event caused the Galera split, it may have caused a RabbitMQ partition too.

**3. After the DB is healthy**
- Conductor timeouts often clear by themselves. If they don't, do a rolling restart of nova-conductor, then nova-scheduler. Restart nova-compute only if it stays unresponsive.
- Instances stuck in BUILD won't recover reliably. Use `nova reset-state --active` (or delete) and recreate them, and delete the ERROR ones.
- Test with one VM before announcing recovery.

**For your manager:** this is most likely a DB quorum or routing problem, not a messaging one. A blind restart risks turning a partial outage into a longer one. Say you'll have a diagnosis in about 5 minutes and a fix after that.

If you paste the Galera status output from all three nodes and `rabbitmqctl cluster_status`, I can tell you which branch you're in.