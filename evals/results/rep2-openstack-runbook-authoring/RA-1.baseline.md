I couldn't publish this as a page because file writing is disabled in this session, so the runbook is below as text. I haven't saved or published it anywhere.

# Runbook: VM creation fails after a RabbitMQ partition

**Symptoms**
- New VMs fail to build, stuck in `BUILD` or going to `ERROR`. Existing VMs keep running.
- RPC between services is broken, with `MessagingTimeout` in the nova and neutron logs.
- Galera reports unhealthy.

**Confirm the cause first.** Run `rabbitmqctl cluster_status` and look for a *Network Partitions* section. That was the root cause last time.

> **Warning:** purging RabbitMQ queues discards in-flight messages. Expect VMs left in `BUILD` or `ERROR` afterwards. Get a second person to agree before doing this in production.

## Recovery steps
1. **Stop API traffic.** Pull the API nodes out of HAProxy (disable the backends or stop the API services) so no new requests create more broken state.
2. **Purge the RabbitMQ queues and restart the RabbitMQ cluster.** Bring the nodes back one at a time and confirm the cluster re-forms with no partitions. See the first item under Gaps for the exact commands.
3. **Restart MariaDB (Galera)** once RabbitMQ is healthy. If the whole cluster is down, bootstrap from the node with the highest `seqno` in `grastate.dat`.
4. **Run the verification checklist** below before reopening anything.
5. **Test end to end.** Create a VM, ping it, then delete it.
6. **Reopen the APIs** in HAProxy and watch the logs for a few minutes.

## Verification checklist
- [ ] Galera `wsrep_cluster_size` equals the expected node count. Check with `mysql -e "SHOW STATUS LIKE 'wsrep_cluster_%'"`.
- [ ] Galera `wsrep_cluster_status` is `Primary` on every node.
- [ ] `rabbitmqctl cluster_status` shows all nodes running and no partitions.
- [ ] Service queues have consumers (`rabbitmqctl list_queues name consumers`).
- [ ] Compute services are up (`openstack compute service list`).
- [ ] Network agents are alive (`openstack network agent list`).
- [ ] The test VM create, ping and delete succeeds.
- [ ] The APIs are back in HAProxy.

## After recovery
- Clean up VMs stuck in `BUILD` or `ERROR` from the outage window.
- If a service shows no consumers, restart it (for example nova-compute or the neutron agents) so it reconnects.
- Record what triggered the partition (network blip, paused node, load).

## Gaps in the notes (please fill in)
- The exact RabbitMQ purge and restart commands. The notes don't say whether you used `purge_queue`, `reset`, or cleared the mnesia directory.
- Node names and HAProxy backend names.
- The expected Galera cluster size.
- How long recovery took, and who to page.

## Prevention ideas (mine, not from the notes)
- Alert on RabbitMQ partitions and on Galera size or status changes.
- Review RabbitMQ `cluster_partition_handling` (for example `pause_minority`) and the network redundancy between control nodes.

The commands I included are generic examples, not what you ran. Once file writing is available, or if you want me to try another route, I can publish this as a shareable page.