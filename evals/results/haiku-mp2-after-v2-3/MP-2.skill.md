**No, don't do this for patching.** Evacuation is for hosts that have already failed. Using it on a host that may still be running its VMs is how you get data corruption on shared Ceph.

**Why it's dangerous**

- **Stopping nova-compute doesn't stop the guests.** The QEMU processes keep running under libvirt. Nova just loses sight of them.
- **"Shows down" is not "is dead".** Nova marks a service down when its heartbeat stops, which can happen during a network partition, a busy host, or a hung agent while the VMs are still running and writing.
- **Evacuation rebuilds the VMs on other hosts while the originals may still run.** On shared Ceph, two writers can attach the same RBD volumes. The result is filesystem corruption that may not show up until later. Nova does not fence the old host for you. Forcing the evacuation (`--force` or forcing the service down) removes the safety check entirely.
- **It's a hard crash for every guest.** Nothing is shut down cleanly and memory state is lost. That's worse for most workloads than a live migration.

**Why it isn't actually faster**

Live migration is slow for a few specific reasons: a per-host concurrency limit, memory dirty rate, and network bandwidth. Evacuation has none of these limits, but it still needs the host fenced and every guest restarted, so the total time is often similar. The shared-Ceph setup helps you here: cold migration doesn't copy disks, so it's much faster than a block migration.

**Faster options that keep the safety properties**

1. **Raise concurrency within a failure domain.** Check `max_concurrent_live_migrations` on the source computes and the network headroom for migrations. Keep to the spare capacity you actually have per rack or AZ, not the total.
2. **Use cold migration for workloads whose owners accept a short outage.** Shared storage makes it quick. Get the owner's agreement first.
3. **Coordinated restart for workloads that tolerate it.** Shut the guest down cleanly, patch the host, then start the guest. Set `resume_guests_state_on_host_boot` deliberately, because the Nova default (`False`) leaves guests off after a reboot.
4. **Only if owners agree to a hard stop:** shut the guests down cleanly on the host, confirm none are still running (`virsh list` empty), and only then consider evacuation or cold migration. Evacuation still needs the host powered off or fenced first.

**What I'd need to be more specific**

- Host count, and how many are in each failure domain
- Your current baseline: how long migrations take now, and how many run at once
- Libvirt and QEMU versions. If the patch changes them, you'll need a landing-zone batch because migrations can't go back to an older QEMU.
- The criticality of each workload, from its owner
- Any non-migratable instances: flavor-based PCI passthrough, `direct-physical` ports, or memory-heavy VMs

I haven't inspected your environment, so the numbers above are assumptions until you check them. The steps in options 1–4 change state (disabling services, migrations, restarts) and need approval from the accountable owner under your change process.

Decision support only. State-changing steps above require approval by the accountable owner and should be executed under your change process.