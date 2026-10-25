**Yes. Don't run evacuate on all 40 VMs yet.** "Down" in `compute service list` only means nova-compute stopped sending heartbeats. It doesn't tell you the VMs are dead. If the hypervisor is still running them (a broken agent, a RabbitMQ partition, a network problem on the host), evacuation starts a second copy of each VM on another host, pointing at the same Ceph disks. For customer databases that can mean two writers on one volume, which means corruption. Ceph being fast doesn't reduce that risk. Nova also doesn't fence the old host, so the evacuation itself won't stop it.

Before anything runs, establish whether the old copies are still alive. This takes a few minutes:

1. **Is the host powered off?** Check the BMC (`ipmitool -H <bmc> power status`) or the console. If it's up, go to step 4 instead.
2. **Are the guests running?** Ask the Ceph cluster which clients still hold each disk open. `rbd status <pool>/<instance-uuid>_disk` lists watchers. A watcher from cmp-0417's IP means that copy may still be running. Run this for the database VMs first.
3. **Is the host actually dead?** If it's powered off, confirm nothing could still reach the disks. Then mark it forced-down, which is the operator's explicit statement that the host is gone: `openstack compute service set --down cmp-0417 nova-compute`. Then evacuate the database VMs one at a time, verifying each before starting the next: `openstack server evacuate --host <target> <id>`. Leave the rest for after the database VMs are back.
4. **If the host is up and the VMs are running**, the problem is probably the compute agent, the network path, or RabbitMQ, not the VMs. Check `systemctl status nova-compute libvirtd`, `virsh list --all` on the host, and the OVS/neutron agent. Restarting the agent or fixing the network may bring the VMs back with no evacuation at all.

Also check these before the bulk run:
- Are all 40 Ceph-backed? Any with local ephemeral disks can't be evacuated and will lose data.
- Do the targets have capacity for the flavors, plus any server groups, affinity rules, or pinned CPUs?
- If the host comes back later, nova-compute will try to clean up evacuated guests on startup. Make sure nobody restarts it while you're still deciding who owns the disks.

The on-call lead should approve step 3 explicitly, since it's the point where a wrong assumption causes data loss. I can't check any of this from here, so the commands above are for you to run against the cloud and host.