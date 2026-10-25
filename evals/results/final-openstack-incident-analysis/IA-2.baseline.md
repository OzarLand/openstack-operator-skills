Yes, one big reason: **confirm the host is actually dead first.** "nova-compute down" only means the agent stopped heartbeating. It doesn't mean the VMs stopped.

**The risk**
- If cmp-0417 is partitioned from the control plane but still running libvirt/QEMU, the original VMs are still alive and attached to their RBD images.
- Evacuating then starts a second copy of each VM on another host, using the same Ceph disks.
- Two writers on one database volume can corrupt it, and that's far worse than 40 minutes of extra downtime.
- Ceph's RBD exclusive-lock is not a reliable guard here, so don't count on it.

**Do this before evacuating (a few minutes)**
1. **Fence the host.** Power it off through the BMC/IPMI (`ipmitool -H <bmc> chassis power off`, or your fencing tooling), and confirm it reports off. That makes evacuation safe. If the BMC is unreachable too, that's a sign of a real outage, but it also means you can't confirm the host is down.
2. **If you can't power it off,** blocklist the host's Ceph clients so its VMs can't write:
   `ceph osd blocklist add <client-ip>` (find the IPs via `rbd status <pool>/<image>` watchers or `ceph tell mds.* client ls`).
3. **Mark the service down explicitly:**
   `openstack compute service set --down cmp-0417 nova-compute`
   Evacuate requires the service to be down, and this stops the scheduler from sending anything back to it.

**Then, how to run it**
- **Stagger it.** Evacuate the customer databases first, in small batches (5–10). Don't send all 40 at once, which can overload the scheduler, the target hosts' RAM and CPU, and Ceph with a burst of attach and boot I/O.
- **Check capacity** on the remaining hosts. Look for pinned CPUs, NUMA, hugepages, GPU or SR-IOV flavors, and anti-affinity groups. Those can fail to schedule or end up in ERROR.
- **Look for VMs with local disks** (non-Ceph ephemeral or config drives). Those will be lost or rebuilt from the image, not preserved.
- **Don't let the host rejoin on its own.** Keep nova-compute stopped on cmp-0417 until you've verified the evacuations. When it restarts, it cleans up instances that were evacuated away, but you want that to happen deliberately.
- **Afterwards,** check that each DB VM is ACTIVE, that the guest is up, and that the database recovers cleanly. Expect crash recovery, since it was an unclean shutdown.

If someone has already confirmed cmp-0417 is powered off, go ahead right now, staggered, databases first. If nobody has, fencing it is the only step to take before evacuating.