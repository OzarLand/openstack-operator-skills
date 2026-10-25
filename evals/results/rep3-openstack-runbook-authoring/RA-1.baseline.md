I couldn't save or publish this as a page because file writing is disabled in this session, so the runbook is below. The commands are examples, so adapt them to your deployment and check them before the first real use.

# Runbook: VM creation failing after a RabbitMQ partition

**Symptoms**
- New VM creation fails, but existing VMs keep running.
- OpenStack RPC calls fail or time out, which points to RabbitMQ.
- Galera (MariaDB) reports unhealthy.

**Root cause last time:** a RabbitMQ network partition. Confirm it first, because it tells you this runbook applies:
```
rabbitmqctl cluster_status   # check the "Network Partitions" section
```

> **Warning:** this procedure purges RabbitMQ queues, so in-flight RPC messages are lost. Announce a control-plane maintenance window first, and expect some VMs to be stuck in `BUILD`.

## Procedure

1. **Stop API traffic.** Pull all API backends out of HAProxy (drain or disable them), then stop the API services so nothing new is written during the repair.
2. **Purge RabbitMQ queues and restart the RabbitMQ cluster.** Restart all nodes together so the partition clears. Then run `rabbitmqctl cluster_status`.
3. **Restart MariaDB.** Do this after RabbitMQ is healthy. If the whole Galera cluster is down, bootstrap from the most advanced node (check the `seqno` in `grastate.dat`) rather than starting nodes at random.
4. **Verify Galera.**
   ```
   SHOW STATUS LIKE 'wsrep_cluster_size';         -- equals your node count
   SHOW STATUS LIKE 'wsrep_cluster_status';       -- Primary
   SHOW STATUS LIKE 'wsrep_local_state_comment';  -- Synced
   ```
5. **Verify RabbitMQ.** All nodes should be in the cluster with no partitions. Check that service queues have consumers:
   ```
   rabbitmqctl cluster_status
   rabbitmqctl list_queues name consumers messages
   ```
6. **Verify OpenStack services and agents are up.** Restart any that didn't reconnect.
   ```
   openstack compute service list
   openstack network agent list
   openstack volume service list
   ```
7. **Smoke test.** Create a test VM and wait for `ACTIVE`, then ping it and delete it.
8. **Reopen the APIs.** Start the API services if you stopped them, re-enable them in HAProxy, and watch error rates for a while.

## Cleanup after recovery
- List VMs stuck in `BUILD` or `ERROR` from the outage with `openstack server list --all-projects --status BUILD`. Reset their state or delete them.
- Check for orphaned ports and volumes from failed builds.

## Follow-ups to consider
- Alert on RabbitMQ partitions and on Galera cluster size and status.
- Review RabbitMQ's `cluster_partition_handling` setting (for example `pause_minority`) and the network path between controllers.
- Note what triggered the partition each time it recurs.

The follow-ups, the cleanup section and the example commands are my additions. Your notes only covered the eight steps and the root cause.

If you re-enable file writing, I can publish this as a shareable page.