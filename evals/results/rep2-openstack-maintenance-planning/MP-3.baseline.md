# Evacuating cmp-12: plan

I'm assuming OpenStack with KVM/libvirt, since the working directory is named `osk`. If it's something else, the shape stays the same and only the commands change.

## Today (T-1 day)

1. **Inventory the node.**
   ```
   openstack server list --all-projects --host cmp-12 --long
   openstack hypervisor show cmp-12
   ```
   Tag each VM as *live-migratable*, *GPU*, or *big DB*.
2. **Check capacity.**
   - The rest of the cluster needs room for about 17 VMs. That means vCPU, RAM and disk, plus headroom for the DB's RAM.
   - Find a destination for the GPU VMs: a host with a free, identical GPU model and the same PCI alias/flavor. If none exists, those two VMs go down for the full hour.
3. **Notify the owners** of the two GPU VMs and the DB. Agree on a downtime window and on who verifies afterwards.
4. **Check shared prerequisites.**
   - Storage type: shared (Ceph) or local disk. Local disk makes live migration slower, because it needs block migration.
   - CPU model compatibility with destination hosts.
   - Network and security group parity.
   - A recent backup or snapshot of the DB and the GPU VMs.

## Tomorrow, before the technician arrives

1. **Stop new scheduling:**
   ```
   openstack compute service set --disable --disable-reason "DIMM swap 2026-10-26" cmp-12 nova-compute
   ```
2. **Live-migrate the ~17 ordinary VMs**, 2–3 at a time:
   ```
   openstack server migrate --live-migration --host <dest> <vm>
   ```
   Watch `nova migration-list` and `openstack server list --host cmp-12` as you go.
3. **Handle the big in-memory DB.** Pick one of these, in order of preference:
   - **Application-level failover (best).** If it has a replica or cluster, promote the replica elsewhere. Then stop or migrate the original during the window. This gives near-zero downtime and no migration risk.
   - **Live migration with post-copy and auto-converge.** Set `live_migration_permit_post_copy=true` and `live_migration_permit_auto_converge=true` on the source. Run it off-peak and raise `live_migration_completion_timeout` if needed. A high dirty-page rate can stall pre-copy. Post-copy converges, but if the network fails mid-migration the VM is lost, so only use it with a fresh backup.
   - **Planned shutdown.** Do a clean DB shutdown or checkpoint, then stop the VM. Cold-migrate it, or leave it down for the hour. Reloading a large in-memory dataset can take a long time, so budget for warm-up after it starts.
4. **Handle the two GPU VMs.** PCI passthrough devices can't be live-migrated.
   - Notify the owners, then stop the VMs cleanly: `openstack server stop <vm>`.
   - Either **cold-migrate** them to a host with a free matching GPU (`openstack server migrate <vm> --host <dest>`, then confirm), or leave them stopped on cmp-12 and start them after the repair.
   - Moving them is only worth it if the owners can't tolerate an hour of downtime. Cold migration still means a restart, and any local scratch or instance disk state can be a problem.
5. **Verify the node is empty.**
   ```
   openstack server list --all-projects --host cmp-12
   virsh list --all    # on cmp-12
   ```
   It should be empty, apart from any GPU VMs you chose to leave stopped there.

## During the repair

- Power the node off cleanly with `shutdown -h now`, after nothing is running on it.
- Keep the service disabled so nothing is scheduled onto it.

## After the repair

1. Boot the node and confirm the full RAM is visible (`free -g`, `dmidecode -t memory`). Check the BMC/IPMI for memory errors (`ipmitool sel list`).
2. Confirm libvirt and nova-compute are up, and that the GPUs are still bound to `vfio-pci`.
3. Re-enable the node:
   ```
   openstack compute service set --enable cmp-12 nova-compute
   ```
4. Restart any stopped GPU VMs and have their owners verify them. Rebalance the migrated VMs back only if you need to. It isn't necessary.

## Risks to watch

- **DB live migration stalls or degrades performance.** Rehearse it, or use failover instead.
- **No spare GPU capacity.** The GPU VMs then stay down for the whole window.
- **Anti-affinity groups.** They can block the scheduler's destination choices.
- **Memory pressure on destinations.** Check headroom before you start.

If you give me the real details (storage backend, whether the DB has a replica, whether a spare GPU host exists), I can turn this into a command-by-command runbook with the actual VM names.