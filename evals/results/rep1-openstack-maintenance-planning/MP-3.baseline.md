I'm assuming OpenStack with KVM/libvirt, so the commands below are Nova ones. If it's Proxmox, VMware or something else, the shape is the same and the commands change.

## Today: prep and decisions

1. **Inventory.** Run `openstack server list --host cmp-12 --all-projects -c ID -c Name -c Flavor -c Status`. Flag the 2 GPU VMs and the DB VM, and tag the owners.
2. **Capacity.** Check the other hosts have room for about 20 VMs. The DB VM needs one host with its full RAM free, plus headroom for the migration. For the GPU VMs, check whether another host has free GPUs of the same model and a matching `pci_alias`.
3. **Migration prerequisites.** Check shared storage (Ceph or NFS), or confirm block migration is acceptable. Check there are no config drives, attached local devices or CPU-model mismatches that would block live migration. Run one test live migration of a low-risk VM now.
4. **Owner notices.** Tell the GPU and DB owners now, since both have downtime or risk. Get an agreed window and a rollback contact.
5. **Maintenance window.** Silence the alerts for cmp-12 and disable any auto-evacuate or HA fencing for it. Otherwise the host going down may trigger automatic VM restarts elsewhere.

## Handling each VM class

**The ~17 ordinary VMs: live migrate.**
- Stop new placement: `openstack compute service set --disable --disable-reason "DIMM replacement" cmp-12 nova-compute`.
- Migrate in batches of 3–4, not all at once: `openstack server migrate --live-migration <vm>`. Let the scheduler choose, or pass `--host`.
- Check each VM is ACTIVE, answers on the network, and its services are healthy before the next batch.

**The in-memory DB: the risky one.** A busy, large-memory guest dirties pages faster than the migration can copy them, so it may never converge. In order of preference:
- **Replicated or clustered DB:** fail over to a replica and migrate or stop the standby copy. This is the safest option.
- **Single instance:** schedule a short controlled outage with the owner. Shut the DB down cleanly (flush or snapshot to disk), then cold-migrate the VM (`openstack server migrate <vm>`, then confirm the resize). Restart the DB and expect a warm-up period to reload memory.
- **Live migration, only if downtime is unacceptable:** enable `live_migration_permit_post_copy` and `live_migration_permit_auto_converge`, and do it in a low-traffic period. Have an abort ready: `openstack server migration abort`. Test it on a staging clone first if you can.

**The 2 GPU passthrough VMs: they can't live migrate.**
- **Option A (preferred if a free matching GPU exists elsewhere):** shut down the guest and cold-migrate it. Check it boots there and the driver sees the GPU.
- **Option B:** shut down the VM and leave it SHUTOFF on cmp-12. It keeps its GPU assignment, and you start it again after the repair. This is simpler, and the downtime is about the same as the maintenance window.
- Either way, the owners need to quiesce their jobs. Training or compute workloads should checkpoint first.

## Tomorrow, before the technician touches the host

1. Re-verify the host is disabled and the target hosts still have headroom.
2. Do the DB step first, since it's the longest and riskiest, then the GPU VMs, then batches of ordinary VMs.
3. Confirm the host is empty with `openstack server list --host cmp-12 --all-projects`. Only SHUTOFF GPU VMs under Option B should remain.
4. Shut down the node cleanly (`shutdown -h now` or via BMC). Confirm power is off before the technician starts.

## After the repair

1. Boot and check the full DIMM capacity is seen: `free -g` and `dmidecode -t memory`. Run a quick memory test if time allows.
2. Re-enable the service: `openstack compute service set --enable cmp-12 nova-compute`.
3. Start any SHUTOFF GPU VMs and confirm the GPUs are visible in the guest.
4. Migrate the VMs back only if you need to rebalance. Otherwise leave them where they are, and tell the owners.
5. Lift the alert silences, and restore HA/fencing.

## Rollback

If the hour overruns or the DIMM swap fails, nothing needs rolling back. The VMs are already running elsewhere, and cmp-12 stays disabled until it's healthy.

Tell me the platform, the shared storage type and whether the DB is replicated. I can then turn this into exact commands or a runbook checklist. I can also put it on a page for the technician and owners if you want.