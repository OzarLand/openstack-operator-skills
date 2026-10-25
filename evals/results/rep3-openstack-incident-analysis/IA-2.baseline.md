Yes, one big one. Fence the host before you evacuate. Don't run it blindly.

**The risk:** `nova-compute` being down only means the service stopped reporting. It doesn't prove the hypervisor or its guests are dead. If the host is alive, for example because of a management-network partition or a hung or crashed nova-compute agent, the VMs may still be running. Evacuating then starts a second copy of each VM on the same RBD images. Two writers on a customer database disk means filesystem and database corruption. That's much worse than the current downtime. Ceph's exclusive lock helps, but you shouldn't rely on it as your safety net.

**Before evacuating (a few minutes):**

1. **Power the node off via BMC/IPMI** (`ipmitool -H <bmc> chassis power off`, or your fencing tool). This is the only reliable check. If you can't reach the BMC either, treat that as a warning sign.
2. **Check Ceph for live clients.** For a few of the DB volumes, run `rbd status <pool>/<instance_uuid>_disk` and look for watchers from cmp-0417's IP. If watchers are present, the VMs are almost certainly still running.
3. **Mark the service down** so Nova and the operators agree: `openstack compute service set --down cmp-0417 nova-compute`. Evacuate needs the service down or forced down anyway.
4. **Check why it's down since 03:12.** If only the agent died (`systemctl status nova-compute`, journal, RabbitMQ connectivity) and the guests are fine, restarting it may fix this without evacuating. But then the VMs wouldn't be unreachable, so check the host's network too.

**Then evacuate:**

- Do the customer databases first, then the rest in batches. Don't send all 40 at once, to avoid thundering-herd load on the scheduler, Neutron and Ceph. Check that the remaining hosts have the capacity, since 40 VMs is a lot.
- Use `openstack server evacuate <uuid>` per server, or `nova host-evacuate cmp-0417`. Don't pass `--host` unless you've checked that host.
- Watch for ERROR states and Neutron port-binding failures.
- Evacuate rebuilds the instance from its shared disk. The VM goes through a hard reboot, so databases will do crash recovery. That's expected.
- After a database comes up, check it before you tell the customer it's healthy.

**Afterwards:** don't bring cmp-0417 back with VMs still defined on it. Once nova-compute starts, it cleans up the evacuated instances, but check that libvirt has no leftover domains first. Keep the node fenced until you've investigated the cause.

If you can confirm the power-off or empty watchers, go ahead and evacuate right away.