**Yes, one important reason: "down" in Nova doesn't prove the VMs are stopped.** `nova-compute` can show down when the host is powered off, but also when the agent is hung, RabbitMQ is partitioned, or the host has lost its management network while its guests keep running. Evacuate assumes the source is dead. If qemu is still running on cmp-0417, the evacuated copy boots from the same disks, and two instances write to one customer database. Corruption like that is much worse than an outage and can take far longer to recover from.

Ceph doesn't reliably prevent this. RBD's exclusive lock may stop the second writer, but only if the feature is enabled and the lock is still held. Don't count on it, and don't break or blocklist locks to make evacuation succeed.

**Before evacuating, spend about 5 minutes on read-only checks:**

1. **Power state out-of-band:** check the BMC/iDRAC/iLO for cmp-0417. If it's powered on, it's a control-plane or network problem, not a dead host, and evacuating is the wrong fix.
2. **Is the hypervisor still running guests?** If you can reach the console or BMC, run `virsh list --all` and `systemctl status nova-compute`.
3. **Ceph watchers (the key check):** `rbd status vms/<instance-uuid>_disk` lists clients that still have each image open. If a watcher is cmp-0417's IP, that VM is alive there. Run this for a sample of the 40, especially the databases. This assumes Nova's default `vms` pool and `<uuid>_disk` naming, so adjust if your layout differs.
4. **Nova's view:** `openstack compute service show cmp-0417` and the nova-compute and RabbitMQ logs from around 03:12, to see whether the agent stopped or lost its messaging.

**Only once the host is confirmed off or isolated:**

- Force it down explicitly: `openstack compute service set --down cmp-0417 nova-compute`. This is the fencing statement Nova relies on.
- Evacuate without `--force`. Don't use `--force` on the evacuate call during an incident; it skips the safety check that exists for this exact case.
- Check capacity first. 40 VMs may not fit on the remaining hosts, so confirm the scheduler has room or pick targets.
- Go in batches. Evacuate one database, confirm it boots and the data is consistent (it may need crash recovery), then do the rest.

**When cmp-0417 comes back:** don't just start nova-compute. On startup, Nova cleans up guests it no longer owns, and if a stale copy is still running there, that cleanup can interfere with the evacuated instances. Keep the host powered off or isolated until someone has confirmed which copies are live.

So my answer for on-call: don't run evacuate for all 40 yet. Run the power and Ceph-watcher checks first, which should take minutes. If the host is confirmed dead, fence it and evacuate in batches, starting with a database. If it's still running, fix the agent or network path instead. I can't see your cluster from here, so I'm working from your description. If you paste the output of `openstack compute service show cmp-0417` and a sample `rbd status` result, I can help read them.