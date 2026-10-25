**Yes. Don't run evacuate on all 40 yet.** The risk isn't speed. It's that a "down" nova-compute doesn't tell you the VMs are stopped. If they're still running, evacuating starts a second copy of each VM against the same Ceph disks. For customer databases, two writers on one disk means corruption, and it can stay hidden until someone restores or fails over.

Before anything else, establish whether the VMs are actually running on cmp-0417:

1. **Check the host out-of-band.** Use iDRAC/IPMI or the console. Is the box powered off, hung, or up? Is there a kernel or hardware fault around 03:12?
2. **Check the hypervisor directly if you can reach it.** `virsh list` or `pgrep -a qemu` should show the guests. If they're running and their IPs still respond, the fault is the nova-compute agent or its messaging (RabbitMQ), not the host. Evacuating would create duplicates. Fix the agent instead.
3. **Check the Ceph watchers.** For each VM's disk, run `rbd status <pool>/<instance-uuid>_disk`. A watcher whose address is cmp-0417 means the old QEMU process is still holding the image. Watchers normally drop within about 30 seconds of a client dying, so one that has persisted for hours means the guest is alive.

If the host is genuinely dead:

4. **Fence it.** Power it off through the BMC and confirm it's off. Don't just power-cycle it, because a rebooted host could bring its guests back.
5. **Mark it down explicitly**: `openstack compute service set --down cmp-0417 nova-compute`. Only do this after fencing.
6. **Check capacity** (`openstack hypervisor list`, free vCPU/RAM and any aggregate or PCI/NUMA constraints). Forty VMs landing on a few hosts can fail partway.
7. **Confirm the disks are actually in Ceph**, not in local `/var/lib/nova/instances`. Any VM with local ephemeral disk, a local config-drive setup, or host-pinned hardware will fail to evacuate, or will come back empty.
8. **Canary first.** Evacuate one or two non-database VMs and check that they boot, get networking, and pass a health check. Then do the database VMs one at a time, with a consistency check on each before moving to the next.

When cmp-0417 comes back, don't just power it on and let it rejoin. Nova will try to clean up the guests it no longer owns, and you want to control that step, not have it happen on its own.

I haven't run anything. I don't have access to your OpenStack or Ceph from here. If you paste the output of `openstack compute service list`, `openstack server list --host cmp-0417`, and `rbd status` for one of the database disks, I can help read them.