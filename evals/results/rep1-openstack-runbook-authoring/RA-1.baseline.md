I couldn't publish this as a page because file writing is disabled in this session, so the runbook is below. Commands are generic examples, and items marked *verify* weren't in your notes, so adapt them to your deployment.

# Runbook: VM creation failing (RabbitMQ / Galera recovery)

**Symptoms**
- New VM creation fails, but existing VMs keep running. The data plane is fine and the control plane is broken.
- RabbitMQ RPC is broken (timeouts, `MessagingTimeout`, services not answering).
- Galera is unhealthy.

**Triage (before touching anything)**
1. Confirm existing VMs are healthy, so the impact is limited to control-plane operations.
2. Check RabbitMQ for partitions with `rabbitmqctl cluster_status`. Look for a non-empty partitions section, missing nodes, or queues with no consumers.
3. On each node, check Galera:
   - `wsrep_cluster_size` should match the expected node count.
   - `wsrep_cluster_status` should be `Primary`.
   - `wsrep_local_state_comment` should be `Synced`.
4. Announce the incident and freeze VM operations.

**Recovery**

This causes an API outage while it runs. Purging queues discards in-flight RPC messages, so operations in progress will fail and need cleanup afterwards.

1. **Stop the APIs.** Stop the OpenStack API services and pull the API backends from HAProxy so no new requests arrive.
2. **Purge the RabbitMQ queues.** *Verify* the method for your setup, for example a reset or `rabbitmqctl purge_queue` per queue.
3. **Restart the RabbitMQ cluster** (all nodes). Wait until every node is running and no partitions are reported.
4. **Restart MariaDB.** Go one node at a time. Only bootstrap from the most advanced node if the whole cluster is down. *Verify* this against your Galera procedure.
5. **Verify** using the checklist below before reopening anything.
6. **Reopen the APIs.** Start the API services and return the backends to HAProxy.

**Verification checklist**
- [ ] Galera cluster size equals the expected node count.
- [ ] Galera status is `Primary` on all nodes.
- [ ] RabbitMQ cluster has all nodes joined and no partitions.
- [ ] RabbitMQ consumers are present on the service queues (`rabbitmqctl list_queues name consumers`).
- [ ] Compute services are up (`openstack compute service list`).
- [ ] Network agents are up (`openstack network agent list`).
- [ ] Test VM: create it, ping it, delete it, all successfully.

**After recovery**
- Look for VMs stuck in BUILD, ERROR or deleting, and clean them up (*verify*).
- Notify users that the control plane is back.
- Work out what triggered the partition (network events, node load, link flaps) and record it in the postmortem.

**Root cause and prevention**

The root cause, found after the fact, was a RabbitMQ network partition. These follow-ups are my suggestions, not from your notes, so decide as a team:
- Alert on RabbitMQ partitions and on queues with zero consumers.
- Review the RabbitMQ `cluster_partition_handling` setting.
- Alert on Galera cluster size and status.

If you re-enable file writing, I can publish this as a shareable page.