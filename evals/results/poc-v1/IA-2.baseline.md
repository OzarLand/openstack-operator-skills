Yes, there's one thing to check first, and it's quick. Evacuate is only safe if the old host is certainly not running those VMs.

**The risk**

"nova-compute down" only means the agent has stopped reporting. It doesn't mean the host or its guests are dead. If libvirt/QEMU is still running the VMs, for example because the agent crashed, RabbitMQ was partitioned, or the management network is down, then evacuate starts a second copy of each VM on the same RBD image. Two writers on one database disk will corrupt it, and the customer databases are the worst place for that. Ceph's exclusive-lock doesn't reliably protect you here. A live old client just hands the lock over and the two keep fighting for it. It only protects you if the old client is blocklisted.

The "unreachable" VMs suggest the host is actually down, but a network problem on that host would look the same. So don't assume.

**Before evacuating (a few minutes)**

1. **Fence the host.** Power it off through the BMC (`ipmitool -H <bmc> chassis power off`, or your fencing tooling). That's the only real guarantee, and it also tells you for sure whether it was dead.
2. **If you can't reach the BMC,** check at least that the host is dead from the hypervisor side: `ping` it, SSH to it, and look at its console. Alternatively, find the watchers on the images with `rbd status <pool>/<instance-uuid>_disk`. If a live watcher on cmp-0417's IP shows up, the VM is still running there.
3. **Tell Nova the host is down:**
   ```
   openstack compute service set --down cmp-0417 nova-compute
   ```
   Depending on your release, evacuate requires the service to be down or forced down. You can also add `--disable` so nothing gets scheduled there.
4. **Optionally blocklist the old host's Ceph clients** (`ceph osd blocklist add <addr>`) as a belt-and-braces guard if you can't power it off.

**Then evacuate**

- Do the customer databases first, then the rest. Don't fire off all 40 at once. Use batches of about 5–10 and watch the scheduler and target hosts.
- Check beforehand that the target hosts have enough capacity and that `ceph -s` is healthy.
- Don't let the old host come back up unattended afterward. When nova-compute starts, it cleans up evacuated guests, which is fine. But you want to know why it died first, so reboot it deliberately.

If the BMC confirms it's powered off, or you've otherwise verified the VMs aren't running, go ahead right now. The main thing is not to evacuate while the old host might still be running its guests.