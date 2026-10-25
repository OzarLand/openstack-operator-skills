I'm assuming OpenStack, going by the node name. The commands below are Nova ones, and the same logic applies to other hypervisors.

## Plan

### Today: preflight
1. **Inventory the node.** Run `openstack server list --host cmp-12 --all-projects -c ID -c Name -c Status -c Flavor`. Tag each VM as normal, GPU, or database.
2. **Check capacity elsewhere.** The other computes need free RAM and vCPU for about 20 VMs plus headroom. The two GPU VMs need a host with the same GPU model free, or you accept downtime for them. Also check that the database VM's destination has its full RAM free, not just allocation-ratio room.
3. **Look for blockers:**
   - Local ephemeral disks mean block migration, which is slower.
   - Anti-affinity groups, host aggregates and AZ pins can reject destinations.
   - Config drives, CPU model mismatches between hosts, and anything attached to cmp-12-local storage can also block a migration.
4. **Notify the owners.** Tell the GPU and DB owners the maintenance window and what will happen to their VMs. Agree downtime up front for the GPU VMs.

### Tomorrow: drain
1. **Stop new scheduling:** `openstack compute service set --disable --disable-reason "DIMM swap" cmp-12 nova-compute`.
2. **Live-migrate the ~17 normal VMs.** Run them in batches of 3–4, not all at once, because each migration competes for the network. Check each one reaches ACTIVE on the new host before the next batch.
3. **GPU VMs (2).** Libvirt can't live-migrate PCI passthrough devices, so there are two options:
   - **Cold migrate**, which means a clean guest shutdown, `openstack server migrate`, and a start on a host with a free matching GPU. The VM is down only for the stop and start.
   - **Stop them and leave them on cmp-12.** Use this if no matching GPU is free elsewhere. They come back after the DIMM swap, and the downtime is the full hour.
   
   Ask the owners to checkpoint jobs before the shutdown.
4. **In-memory DB.** A live migration can fail to converge because the guest dirties memory faster than it copies. Choose one:
   - **Best:** fail over at the application level. Promote a replica or standby, then shut the VM down cleanly. This is zero-risk for data.
   - **Otherwise:** live-migrate with auto-converge or post-copy enabled (`live_migration_permit_auto_converge` / `live_migration_permit_post_copy`), during a low-traffic moment. Post-copy carries some risk. If the source fails mid-migration, the VM is lost.
   - **Fallback:** a clean shutdown with a snapshot or dump first. That's an hour of downtime plus a warm-up reload afterward.
   
   Take a fresh backup before touching it in any case.
5. **Confirm it's empty.** `openstack server list --host cmp-12 --all-projects` should return nothing. Then check `virsh list --all` on the host.

### Power off and DIMM swap
- Stop nova-compute, shut the host down, and let the technician work.
- After boot, check that the full RAM count shows (`free -g`, `dmidecode -t memory`) and run a quick memtest or the vendor diagnostics.

### After
1. Re-enable the service with `openstack compute service set --enable cmp-12 nova-compute`.
2. Start any VMs left on cmp-12 (the GPU ones, if you didn't move them).
3. Check that the passthrough GPUs are visible and bound to vfio.
4. Optionally migrate the DB or GPU VMs back to their original placement.

### Rollback and risk notes
- If a live migration fails, the VM stays on the source and keeps running, so you can retry or switch method.
- The main risk is the DB VM. Decide the method with its owner before tomorrow, not during the window.
- Allow roughly 1–2 hours for the drain. Don't start it right before the technician arrives.

If you're not on OpenStack, tell me the platform (Proxmox, VMware, oVirt and so on) and I'll translate the commands. I can also turn this into a shareable runbook page with the exact commands for your VM list.