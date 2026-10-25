**No, not as described.** It's risky, and it doesn't even save the downtime you'd expect.

**The main problem:** stopping `nova-compute` does not stop the guests. The QEMU processes keep running on the host. Nova only checks that the service is down, so `evacuate` will rebuild each instance on another host while the original is still running. Both copies then have the same RBD image open. Ceph's exclusive lock doesn't make that safe. You get lock ping-pong at best and filesystem corruption at worst. Evacuate assumes the source host is dead, and Nova does not fence it for you.

**Other drawbacks:**
- Every instance gets a cold start (a hard-reboot equivalent), so you take downtime on every VM. Live migration has almost none.
- Port bindings, volumes, and anything else that needs the source host cleaned up can go stale. You'd have to clean up when the host returns, because nova-compute's startup handling of evacuated instances is only a safety net.

**If you do want the evacuate path, make it safe:**
1. Power the host off, or at least hard-stop all guests, for example through IPMI/BMC. That is the fencing step.
2. Run `openstack compute service set --down <host> nova-compute` so you don't wait for the heartbeat timeout.
3. Evacuate.

That is effectively crashing every VM on purpose, so only do it for workloads that tolerate it.

**Better ways to speed up the campaign:**
- **Cold migrate instead.** With shared Ceph storage, `openstack server migrate <vm>` (stop, move, start) takes seconds to a minute per VM and is safe. It's fine for tolerant workloads.
- **Tune live migration.** The usual reasons it's slow are:
  - Busy guests that never converge. Set `live_migration_permit_auto_converge = true`, and consider `live_migration_permit_post_copy = true`.
  - Too little parallelism. Raise `max_concurrent_live_migrations` and migrate several hosts at once.
  - The wrong network. Use a dedicated migration network via `live_migration_inbound_addr`, and check the MTU.
  - The default timeouts. Review `live_migration_completion_timeout` and `live_migration_downtime*`.
- **Check whether you need to drain at all.** User-space and config patches usually don't. Only kernel, QEMU or libvirt updates require emptying the host.
- **Patch in batches.** Drain N hosts in parallel, keeping capacity headroom, instead of one host at a time.

If you tell me what's making live migration slow (guest memory size, dirty rate, network, or timeouts), I can suggest specific settings.