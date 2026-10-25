**Don't restart everything yet.** Restarting RabbitMQ and every nova service is the most disruptive option, and it probably won't fix the cause. A non-Primary Galera node is the strongest lead, and a RabbitMQ restart does nothing for it. A restart also drops in-flight RPC messages, which turns stuck BUILD instances into more ERRORs. Spend five minutes on read-only checks first.

I can't see your environment, so this is based on what you described.

**1. Check Galera on all three nodes (read-only)**
```sql
SHOW STATUS WHERE Variable_name IN ('wsrep_cluster_status','wsrep_cluster_size','wsrep_local_state_comment','wsrep_ready','wsrep_last_committed');
```
- **The other two are Primary with size 2:** the cluster still has quorum and the database is fine. One node has been partitioned off. The likely cause is HAProxy or the VIP still sending nova some connections to the bad node, which would explain why only some operations fail. Take that node out of the HAProxy backend (or set it to drain), then investigate its network, such as a switch, MTU, or firewall change or a dropped link on the Galera port (4567). Let it rejoin by itself and resync through IST/SST.
- **All three are non-Primary, or the others also report size 1:** you've lost quorum. Don't force anything yet. Compare `wsrep_last_committed`, or `seqno` in `grastate.dat`, across nodes. Only bootstrap (`pc.bootstrap=YES` or `galera_new_cluster`) from the most advanced node. Bootstrapping a stale node can lose committed writes or split-brain you.

**2. Check RabbitMQ (read-only)**
```
rabbitmqctl cluster_status        # look for partitions
rabbitmqctl list_queues name messages consumers | sort -k2 -n -r | head
```
Check whether the nova conductor, scheduler, and compute queues have consumers and whether messages are piling up. If the Galera partition came from a network event, RabbitMQ may be partitioned too. Only restart RabbitMQ if it shows a partition or dead consumers. Restart one node at a time, and expect clients to need a reconnect.

**3. Check how nova reaches the DB**
Look in nova-conductor logs for DB errors (`OperationalError`, `WSREP has not yet prepared node`, error 1047) alongside the MessagingTimeouts. If they're there, the DB is the root cause and the timeouts are a symptom: conductor can't finish the work, so the RPC call times out.

**4. Recover**
- Fix the database first.
- Then do a rolling restart of nova-conductor and nova-scheduler only if they're stuck holding dead DB connections. They are stateless, so this is low risk. Skip computes, since existing VMs are fine.
- Reset the stuck instances with `nova reset-state --active` or `openstack server set --state error`, then delete them and retry.

**Telling your manager:** "Provisioning is down because one database node dropped out of the cluster. I'm isolating it now, which is a quick fix if the other two nodes have quorum. Restarting the message bus wouldn't fix this and could make it worse."

If you paste the Galera status from all three nodes and the `rabbitmqctl cluster_status` output, I can help you work out which case you're in.