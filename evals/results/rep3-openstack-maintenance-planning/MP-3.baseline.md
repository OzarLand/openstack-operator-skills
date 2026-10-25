I'm assuming OpenStack, going by "compute node" and "cmp-12". If it's something else, the steps map across but the commands won't.

## Before tomorrow

1. **Check capacity.** The other hosts need room for ~20 VMs, with enough free RAM for the database. Check that two hosts have free GPUs of the same model and the same PCI alias or flavor.
2. **Sort the VMs into three groups.** Run `openstack server list --host cmp-12 --all-projects -c ID -c Name -c Flavor -c Status`. Then flag the two GPU VMs and the database VM by flavor extra specs.
3. **Find the owners** of the GPU VMs and the database, and agree a window with them.
4. **Confirm the migration basics.** Check shared or block-migration support, matching CPU models (`cpu_mode` or a CPU model baseline), and that the network and security groups exist on the destination hosts.
5. **Test with one VM.** Live-migrate one low-risk VM off and back tonight, so you find problems today rather than tomorrow.

## Drain order tomorrow

1. **Stop new VMs landing there:** `openstack compute service set --disable --disable-reason "DIMM replacement" cmp-12 nova-compute`.
2. **Live-migrate the ~17 ordinary VMs**, 2–3 at a time: `openstack server migrate --live-migration --host <target> <vm>`. Check each one for connectivity before starting the next.
3. **The in-memory database.** Live migration of a big, write-heavy memory footprint often fails to converge. In order of preference:
   - **Fail over at the application level.** Promote a replica elsewhere and then stop the VM. This is the safest and shortest outage.
   - **Live-migrate with `auto_converge` and/or `permit_post_copy` enabled** in `nova.conf` on the node, during the quietest period. Raise `live_migration_downtime` if needed. Post-copy carries some risk if the network drops mid-migration.
   - **Take a short, planned outage:** stop the database cleanly, flush to disk, cold-migrate it or leave it down for the hour, and tell its users.
4. **The two GPU VMs.** KVM can't live-migrate PCI passthrough devices, so you have two options:
   - **Cold migrate to a host with a free matching GPU.** Use `openstack server migrate` (no live flag), which stops the VM and restarts it there. Expect a few minutes of downtime, and the data on the GPU is lost.
   - **Shut them down cleanly and start them again on cmp-12 after the repair.** This takes about an hour of downtime. Use it if there's no spare GPU capacity.

   In both cases, tell the owners to checkpoint or finish any running jobs first.
5. **Confirm cmp-12 is empty:** `openstack server list --host cmp-12 --all-projects` should return nothing. Then stop the node or let the technician power it off.

## After the repair

1. Run the memory test and check that the node sees the full RAM.
2. Re-enable the service: `openstack compute service set --enable cmp-12 nova-compute`.
3. Move back the GPU VMs, and the database if you want it back there. Use the scheduler or `--host` for placement, and check that the GPUs are visible in the guest (`nvidia-smi`).

## Risks to watch

- A live migration that never finishes. Set a timeout (`live_migration_completion_timeout`) and abort with `openstack server migration abort` if it stalls.
- A cold-migrated GPU VM failing to schedule because of a missing PCI alias. The pre-checks in step 1 catch this.
- Any VM on local ephemeral storage. It needs block migration, which is slow for large disks.

If you tell me your platform and storage (Ceph or local), and whether the database has a replica, I can make this more specific. I can also turn it into a checklist or runbook page for the technician and the VM owners.