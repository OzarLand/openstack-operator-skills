**Don't restart RabbitMQ and the nova services yet. Fix Galera first.** The non-Primary node is the likeliest root cause. A restart could make things worse.

**Why Galera is the suspect**
- Existing VMs keep running because they don't need the control plane.
- Creating a VM needs DB writes: instance create, scheduling, claims and conductor updates.
- If Galera lost quorum, or a node is split off, conductor calls and DB transactions can hang or time out. That produces MessagingTimeout in nova-conductor, which is often a symptom and not a RabbitMQ fault.
- A non-Primary node is normal when it is partitioned from the majority. It's more worrying if it's the node your services' DB connection (HAProxy or VIP) is pointed at.

**Check these first (read-only, about 2 minutes)**
1. On each Galera node, run: `SHOW STATUS LIKE 'wsrep_cluster_%'; SHOW STATUS LIKE 'wsrep_local_state_comment'; SHOW STATUS LIKE 'wsrep_ready';`
   - If the other two nodes show `Primary`, `cluster_size = 2` and `Synced`, you still have quorum. The bad node is just out of the cluster.
   - If **no** node is Primary, you've lost quorum. That's the serious case.
2. Check whether HAProxy or your VIP is still sending DB traffic to the non-Primary node. It should be marked down. If it isn't, that explains the timeouts, and pulling that node from the backend pool may fix things fast.
3. Run `rabbitmqctl cluster_status` and `rabbitmqctl list_queues name messages consumers | sort -k2 -n -r | head`. Look for network partitions, and for queues with a growing backlog and 0 consumers.
4. Look at `journalctl` on the bad Galera node. You're looking for a network blip, an OOM kill, or a full disk.

**If quorum is intact (2 of 3 Primary)**
- Take the bad node out of HAProxy.
- Let it rejoin by restarting just that mariadb/galera service. It should resync with IST or SST.
- Then see whether conductor recovers by itself. It usually does, once the DB answers.

**If no node is Primary**
- Do **not** bootstrap blindly. Find the node with the highest `seqno` in `grastate.dat`, or use `wsrep_recover`, and bootstrap from that one only. Bootstrapping from the wrong node can lose committed transactions.
- Then bring the others in one at a time.

**Why not the restart-everything plan**
- Restarting RabbitMQ drops queues and in-flight RPC. Any instance stuck in BUILD will likely end up in ERROR and need cleanup.
- If the DB is still broken, the services will just time out again, so you'd get a second outage without a fix.
- It also destroys the evidence you need for the postmortem.

**Reasonable fallbacks**
- If RabbitMQ turns out to have a partition or stuck queues after the DB is healthy, restart or rejoin only the affected node.
- Then restart nova-conductor and nova-scheduler, but only after the DB is healthy.

**For your manager**: "The likely cause is a database cluster node that dropped out of quorum. We're verifying and recovering it now. A blanket restart would risk making this worse." Once the DB is healthy, expect provisioning to return within minutes.

If you paste the output of the wsrep status commands and `rabbitmqctl cluster_status`, I can tell you which branch you're in.