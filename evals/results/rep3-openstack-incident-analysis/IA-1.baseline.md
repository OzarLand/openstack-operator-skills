**Don't restart RabbitMQ and all the nova services yet.** Spend about 5 minutes diagnosing first. Existing VMs are fine, so there's no customer-facing urgency to justify a blind restart. A restart could also make this worse:

- Restarting nova services while the DB is degraded can leave instances stuck in half-built states and add reconnect storms.
- Restarting RabbitMQ drops in-flight RPC messages. Anything mid-build is lost, and you could cause a bigger incident if the real fault is the DB.
- It destroys evidence you'll want for the postmortem.

**Likely story:** the MessagingTimeouts may be a symptom, not the cause. A Galera node in `non-Primary` rejects queries ("WSREP has not yet prepared node for application use"). If HAProxy or the service DB connection strings still route to that node, conductor and scheduler calls hang or fail, and RPC replies time out. Boot is the heaviest DB and RPC path, which fits "builds fail, running VMs fine." A RabbitMQ partition is the other candidate, so check both.

**1. Galera (most suspicious, check first)**
On each DB node:
```
mysql -e "SHOW STATUS LIKE 'wsrep_%'" | egrep 'cluster_status|cluster_size|cluster_state_uuid|local_state_comment|ready|connected'
```
- **The other two nodes should show `Primary`, `cluster_size = 2`.** If so, you still have quorum. The fix is to get traffic off the bad node, not to touch the healthy ones.
- **Check HAProxy.** Make sure the non-Primary node is marked down (it should fail the clustercheck). If it's still in rotation, take it out. That may fix provisioning on its own.
- **If all three nodes are non-Primary,** the cluster has lost quorum, and you need a controlled recovery. Pick the node with the highest `seqno` (`grastate.dat`) and bootstrap from it. Do **not** bootstrap the wrong node, because that can lose committed writes. Stop and loop in your DBA first.
- **Then find out why it dropped:** network partition between DB nodes, a node that crashed or OOM'd, or an SST/IST in progress. Check `journalctl -u mariadb` (or the container logs) and `dmesg`.

**2. RabbitMQ**
```
rabbitmqctl cluster_status        # look for "partitions" and all 3 nodes running
rabbitmqctl list_queues name messages consumers | sort -k2 -nr | head -20
rabbitmqctl list_connections | wc -l
```
- **Partition or dead node:** resolve that specifically. Restart only the minority or bad node, not the whole cluster.
- **Queues with many messages and 0 consumers** (`conductor`, `scheduler`, `compute.*`) mean services have lost their connections.
- **File descriptor or memory alarms** also show up in `cluster_status`.

**3. Nova**
```
openstack compute service list      # any down/disabled?
```
- Look for the first error in the conductor and scheduler logs from about 20 minutes ago, not the timeouts. A `DBConnectionError` or "WSREP not ready" would confirm the Galera theory.

**Only restart after you know the cause:**
- If the DB is fixed, nova services usually reconnect on their own. If they don't, restart just `nova-conductor` and `nova-scheduler`, one at a time.
- Don't restart `nova-compute` unless it's actually unresponsive.
- Then clean up: `openstack server list --all-projects --status ERROR` and `--status BUILD`. Reset or delete the stuck ones (`openstack server set --state error`, then delete) once things are healthy.

**For your manager:** "Provisioning is down because of a Galera node that dropped out of the cluster. We're confirming quorum and routing traffic off that node. Running workloads aren't affected. ETA is typically minutes once the cause is confirmed." That's more defensible than "we restarted everything and hoped."

If you paste the output of the `wsrep_%` status from all three nodes and `rabbitmqctl cluster_status`, I can help you pin down the cause and the exact next step.