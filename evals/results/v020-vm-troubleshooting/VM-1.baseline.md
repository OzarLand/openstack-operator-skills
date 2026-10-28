Mostly yes, but do two checks first, because the wiki steps skip them.

**1. Find out why nova-compute is down.**
- "nova-compute is down" only means the service stopped heartbeating. It doesn't mean the host or the guest is down.
- On cmp-031, run `docker ps -a | grep nova_compute` and `docker logs --tail 200 nova_compute`. Also check `systemctl status docker` and whether the host can reach RabbitMQ.
- If the container is just wedged or crashed, run `docker restart nova_compute`. The stuck `deleting` request will usually finish properly, with the guest, ports and volume attachments all cleaned up. That is far better than a local delete.

**2. If you must force it, confirm the guest is really gone.**
- When compute is down, the API does a "local delete". It removes the DB record and asks Neutron and Cinder to clean up. It does not touch the hypervisor.
- If the libvirt guest is still running on cmp-031, you get an orphan VM that is still holding its disk and possibly a volume. On a Ceph or shared-storage backend, that is a data-safety problem if the volume is later reattached elsewhere.
- Check with `ssh cmp-031 'docker exec nova_libvirt virsh list --all'`. If the host is dead, power it off or fence it first.
- Orphans are eventually reaped when compute comes back, because `running_deleted_instance_action` defaults to `reap`. Don't rely on that for a customer instance.

**The wiki steps, in order:**
1. `openstack server set --state error <uuid>`. This also clears `task_state`, and it is safe.
2. `openstack server delete <uuid>`.
3. If that still fails, run `openstack compute service set --down cmp-031 nova-compute`. This is a forced-down flag, and it persists. Run `--up` once the host is healthy, or the scheduler and the service state will stay wrong.
4. Delete again.

**Afterwards:**
- Check that Neutron has no leftover ports (`openstack port list --device-id <uuid>`).
- Check that the Cinder volumes are `available` and not stuck `in-use` or `detaching` (`openstack volume list`). If they are stuck, use `openstack volume attachment list` and `cinder reset-state` carefully.
- Check the placement allocations. A leftover allocation for the instance UUID on the cmp-031 provider is common after a local delete. `openstack resource provider allocation show <uuid>` shows it, and `openstack resource provider allocation delete <uuid>` removes it.

I haven't run anything on your cloud, so this is general guidance based on how Nova behaves. If you paste the `nova_compute` logs from cmp-031 and the output of `openstack server show`, I can say more about why it's stuck.