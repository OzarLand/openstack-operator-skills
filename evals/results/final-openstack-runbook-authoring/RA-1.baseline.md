I couldn't save or publish the runbook, because file writing is disabled in this session. Here it is as Markdown to paste into your wiki.

The commands are typical examples I added. Your notes gave the steps but not the commands, so check hostnames, HAProxy backend names, service names and any container wrappers against your environment.

---

# Runbook: VM creation fails while existing VMs keep running

**Symptoms**
- New VM creation fails, but existing VMs are fine.
- RabbitMQ RPC is broken.
- Galera is unhealthy.

**Likely signs**
- Instances stay in `BUILD` or go to `ERROR` with `MessagingTimeout` in the nova or neutron logs.
- `rabbitmqctl cluster_status` shows a partition, or queues have no consumers.
- `wsrep_cluster_size` is wrong, or the cluster is not `Primary`.

**Order matters:** stop the APIs, fix RabbitMQ, fix MariaDB, verify, then reopen.

## Procedure

1. **Stop new API traffic.** Pull the API backends out of HAProxy, then stop the API services (nova, neutron, cinder, glance and others that use RPC).
   ```
   echo "disable server <backend>/<server>" | socat stdio /var/run/haproxy.sock
   systemctl stop nova-api neutron-server cinder-api glance-api
   ```
2. **Purge RabbitMQ queues and restart the cluster.** This clears stale RPC messages and rebuilds one healthy cluster.
   ```
   rabbitmqctl list_queues name messages consumers
   rabbitmqctl purge_queue <queue>        # repeat per affected queue
   systemctl restart rabbitmq-server      # all nodes, one at a time; confirm they rejoin
   ```
3. **Restart MariaDB**, one node at a time. Wait for each node to show `Synced` before restarting the next.
   If no node will form a cluster, bootstrap from the node with `safe_to_bootstrap: 1` in `grastate.dat`, then rejoin the others. This bootstrap step is my addition, not from your notes.
4. **Verify Galera.**
   ```
   mysql -e "SHOW STATUS LIKE 'wsrep_cluster_size'"
   mysql -e "SHOW STATUS LIKE 'wsrep_cluster_status'"
   mysql -e "SHOW STATUS LIKE 'wsrep_local_state_comment'"
   ```
   Healthy means the cluster size equals the node count, the status is `Primary` and the state is `Synced`.
5. **Verify RabbitMQ.**
   ```
   rabbitmqctl cluster_status
   rabbitmqctl list_queues name messages consumers
   ```
   Healthy means all nodes are running, no partitions are listed, and queues have consumers and almost no backlog.
6. **Verify compute services and agents.** Restart any that stay down.
   ```
   openstack compute service list
   openstack network agent list
   openstack volume service list
   ```
   Every row should be enabled and up.
7. **Smoke-test before reopening.** Start the APIs while they are still out of HAProxy, or test against a node directly.
   ```
   openstack server create --flavor <f> --image <i> --network <n> recovery-test
   openstack server show recovery-test -c status    # wait for ACTIVE
   ping -c 3 <vm-ip>
   openstack server delete recovery-test
   ```
   If the test fails, go back to step 2 and check the logs. Don't reopen.
8. **Reopen the APIs.**
   ```
   echo "enable server <backend>/<server>" | socat stdio /var/run/haproxy.sock
   ```
   Watch error rates and a few real VM creations for several minutes.

## Root cause (this incident)
A RabbitMQ network partition. It broke RPC messaging, which stopped VM creation, and Galera went unhealthy at the same time.

## Follow-ups
- Record what triggered the partition (network event, host, time). The notes name the cause but not the trigger.
- Review RabbitMQ `cluster_partition_handling` (for example `pause_minority` or `autoheal`). This is my suggestion, not from the notes.
- Alert on RabbitMQ partitions, consumer count and Galera cluster size.
- Fill in the real hostnames, backend names and service list so the commands can be pasted as they are.

---

If file writing is enabled again, I can publish this as a shareable page.