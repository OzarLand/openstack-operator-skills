**No, not as described.** Stopping `nova-compute` doesn't stop the guests, so evacuating from it can start the same VM on a second host while the first copy is still running.

**Why it's dangerous**

- **Stopping nova-compute leaves the VMs running.** The qemu/libvirt processes keep running on the host. Nova only sees the host as "down" because its heartbeat stopped. That's a control-plane signal, not proof the guests are dead.
- **Shared Ceph storage makes it worse, not safer.** Both copies can write to the same RBD images, which corrupts filesystems. Ceph's exclusive lock won't reliably save you here, because nothing in the default flow blocklists the original client.
- **The safety check is weaker than it looks.** Nova refuses to evacuate while the service is up, but "down" only means the heartbeat stopped. A network partition or a hung nova-compute produces the same signal while the guests keep running.
- **Restarting nova-compute on the old host isn't a reliable fix.** Nova will destroy guests it finds have been evacuated, but only when that service starts again. During patching, the host is often rebooted first, so that cleanup may never get a chance to run.
- **Evacuation is a crash.** Guests lose memory state and get no graceful shutdown. That's acceptable for a failed host, but for planned work it means avoidable application-level recovery on every VM.

**Why it's slow, and what to change instead**

Before choosing a method, measure where the time goes. In most campaigns the real cause is one of these:

1. **Migrations run one at a time per source host.** The default `max_concurrent_live_migrations` is 1. Raising it, and draining several hosts in parallel with the spare capacity you already sized, usually gives the biggest speedup for the least risk.
2. **Migrations don't converge.** VMs with a high memory dirty rate keep migrating without finishing. Check the migration logs for that. Auto-converge or post-copy (`live_migration_permit_auto_converge`, `live_migration_permit_post_copy`) can help, but post-copy has its own failure modes, so test it first.
3. **Bandwidth is capped.** Check the migration network. With shared storage, a live migration only moves RAM, so disk copy shouldn't be the bottleneck.
4. **Some VMs can't live-migrate.** For those, a graceful stop followed by cold migration is fast on shared storage, because no disk copy is needed. Use that for non-migratable or low-value workloads.

**If you really want evacuation for some hosts**, do it only as a fenced procedure:

1. Power off the hypervisor, or otherwise cut its power and network, and confirm that from outside the host, not from nova.
2. Force the service down with `openstack compute service set --down <host> nova-compute`.
3. Evacuate the guests.
4. Never bring the old host back onto the network with its guests still defined.

This procedure is for failed hosts. For planned patching it's slower in practice than parallel live migration, because you lose the graceful handoff and still have to handle each VM's recovery.

If you tell me the migration timings you're seeing, the `max_concurrent_live_migrations` setting, and whether any VMs are pinned, SR-IOV or vGPU, I can help work out which of these is the real bottleneck.