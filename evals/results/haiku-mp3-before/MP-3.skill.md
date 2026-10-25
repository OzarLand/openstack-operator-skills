Assuming this is OpenStack Nova, here's the plan. The critical path is the two GPU VMs and the database, so start with those.

## Today (prep, no VM moves yet)

1. **Inventory cmp-12.** List every instance with its flavor, vCPU, RAM, NUMA or hugepage settings, attached volumes, and whether it has local disk.
   - `openstack server list --all-projects --host cmp-12`
   - For each flavor, check `pci_passthrough:alias`, `hw:cpu_policy`, and `hw:mem_page_size`.
2. **Classify each VM.** Put it in one of four buckets:
   - **Live-migratable:** the bulk of the 20, no passthrough, no local-disk blocker.
   - **Cold-migrate or stop:** the two GPU VMs.
   - **Application-managed:** the in-memory DB, if it's part of a replicated cluster.
   - **Blocked:** anything with local disk, a host-pinned device, or an owner who won't accept a move.
3. **Check spare capacity.** Sum the vCPU and RAM of cmp-12's VMs and compare that with free capacity on the other hosts, keeping at least one host's worth of headroom. Check placement with `openstack resource provider list` and `openstack allocation candidate list`. Confirm the other hosts have the same NUMA and hugepage layout, or the DB won't fit.
4. **Find GPU targets.** Confirm another host has a free GPU of the same vendor and device ID, and that its PCI alias matches the flavor. If there isn't one, those VMs must be stopped for the window, and their owners need to know.
5. **Assess the DB.** Find out whether it's replicated (Galera, Patroni, or similar), what its memory dirty rate is, and whether it can fail over to a replica elsewhere. Live-migrating a large, write-heavy in-memory DB often fails to converge. Failing over to a replica is usually safer.
6. **Check the DIMM's error history.** Correctable errors suggest a degrading module, which is risky but manageable. Recent uncorrectable errors mean the host could crash mid-plan. If that's the case, move faster and be ready to evacuate after a crash (`openstack server evacuate --host <target>` on shared storage).
7. **Notify owners** with the window, expected downtime for the GPU VMs and any stopped VMs, and the rollback point.

## Window day, in order

1. **Disable scheduling to cmp-12** so nothing new lands there:
   `openstack compute service set --disable --disable-reason "DIMM replacement" cmp-12 nova-compute`
2. **Pilot one live migration** on a low-risk VM. This proves the network, storage, and timing before the important moves.
3. **Live-migrate the bulk.** Use `openstack server migrate --live-migration --host <target>` and add `--block-migration` only where there's no shared storage. Run them a few at a time and watch the migration state.
4. **Handle the GPU VMs.** Cold-migrate each to a free GPU host, or stop them if there's no target. Passthrough devices generally block live migration.
5. **Handle the DB.** Fail over to a replica if one exists, and confirm replication health first. If there's no replica, schedule a real outage with the DB owner and shut it down cleanly. Don't rely on a live migration.
6. **Stop-and-hold conditions.** Pause and reassess if any of these happen:
   - a migration stalls or fails twice
   - capacity on the targets drops
   - the DB replica lags
   - a GPU target disappears
   - the window runs past its limit
7. **Verify the host is empty:**
   - `openstack server list --host cmp-12` returns nothing
   - `virsh list --all` on the host shows no running domains
8. **Drain and power off.**
   - If the node is hyperconverged with Ceph, set `ceph osd set noout` first.
   - Stop nova-compute, then shut down cleanly (`systemctl poweroff`), or use the BMC if needed.

## After the swap

1. Power on, and check POST and the SEL log (`ipmitool sel list`) for memory errors.
2. Run a memory test if your policy calls for it.
3. Confirm nova-compute is up and that the PCI devices are back in placement.
4. Re-enable the service: `openstack compute service set --enable cmp-12 nova-compute`
5. Decide whether to move VMs back. Rebalancing is optional, but the GPU VMs need to return to a host with the right GPU if they were moved.
6. Unset `noout` if you set it, and confirm the owners' services are healthy.

## Assumptions to check

- The platform is OpenStack Nova. If it's something else (oVirt, Proxmox, plain libvirt), the steps change but the logic holds.
- Shared storage (Ceph or similar) is in use, so live migration doesn't need block migration.
- The DB's HA story is what it looks like above.

If you share the flavor list, the host list with free capacity, and the DB's replication setup, I can turn this into a runbook with exact commands and go/no-go checks for each VM.