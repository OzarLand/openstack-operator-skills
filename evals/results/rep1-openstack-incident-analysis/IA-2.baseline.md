Yes, one big one: don't evacuate until you've confirmed the host is actually dead, or fenced it. If you can't confirm that, you risk corrupting those customer databases.

**The risk**

`nova-compute` showing "down" only means the agent missed its heartbeats. It doesn't mean the VMs stopped. A hung or crashed agent, a management-network partition, or a RabbitMQ or DB connectivity problem can all produce it. In those cases the VMs on cmp-0417 may still be running, and some may still be serving traffic. Evacuating then starts a second copy of each VM on a new host, both attached to the same RBD image. For a database that can mean split-brain and corrupted data. Ceph's exclusive lock offers some protection, but you shouldn't rely on it for this. The "~40 unreachable" detail suggests the host is really down, but that could also be a network path problem, so verify it.

**Before running evacuate (a few minutes)**

1. **Check the BMC/IPMI power state and console** for cmp-0417. Look for a kernel panic, hang or power loss.
2. **Fence the host.** If it's not clearly powered off, power it off through the BMC. This is the step that makes evacuating safe.
3. **Mark the service forced-down** so Nova knows the host is gone:
   `openstack compute service set --down cmp-0417 nova-compute`
4. **Optionally, blocklist the old clients in Ceph.** Run `ceph osd blocklist add <addr>` for the host's client addresses. This is a second guard against the old host writing.
5. **Check capacity** on the remaining hosts for about 40 VMs. Also check which VMs aren't fully on Ceph: local ephemeral disks, or volumes on other backends. Evacuate rebuilds those from the image and the data is lost.

**While evacuating**

- **Do the customer databases first**, a few at a time, rather than all 40 at once. This eases scheduler and Ceph load and lets you catch problems early.
- **Expect crash-consistent boots**, as after a power cut. Check the databases for integrity and replication state once they're up.
- **Find out why it died at 03:12.** If the cause was a bad kernel, a network problem or a bad batch of hardware, the destination hosts may be exposed to it too.
- **Handle the host's return carefully.** Don't power cmp-0417 back on until the evacuations are finished and you know what went wrong. When nova-compute does restart, it cleans up instances that were evacuated away.

If the BMC shows the host is off or panicked, fencing takes a minute or two. After that, evacuating everything is the right call.