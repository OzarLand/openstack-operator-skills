## Turn 1

**User:**

I need to patch 40 compute hosts (kernel + QEMU) this week, 2 availability zones. How should I plan it?

**Assistant:**

Here is a plan skeleton for the 40 hosts. You haven't given me your capacity, versions, storage model or workload criticality, so those are listed as gaps. I haven't invented any numbers.

## Requirement and constraints
- **Fixed:** kernel + QEMU patched on all 40 hosts this week. *(Reported)*
- **To design:** how the hosts get patched safely. The deadline stays; the execution strategy adapts to your real capacity and workloads.
- **Key fact for QEMU:** a QEMU patch protects only instances that have been migrated or restarted since the patch. Instances left running on the old binary stay unpatched. "Host patched" is not the same as "instance protected", so track this per instance.
- If the week turns out to be unachievable without disruption you haven't agreed to, tell the accountable owner what the exposure is. Don't quietly compress the safety steps.

## Scope
- **Known:** 40 hosts, 2 AZs *(Reported)*.
- **Gaps:**
  - Hosts per AZ. It may not be 20/20.
  - Current libvirt/QEMU versions and the target versions.
  - Whether the patch changes the libvirt/QEMU version or only the kernel.
  - CPU models per host.
  - Instance storage: shared (Ceph, etc.) or local. Local disks mean block migration, which loads the network and storage.
  - Hosts with PCI passthrough, SR-IOV, vGPU, pinned/NUMA or large-memory instances.
  - Aggregates or racks inside each AZ.
  - OpenStack release.

## Workload classes
Nova can't tell which workloads tolerate a restart. Collecting the criticality table from the consuming teams is the **first deliverable**. It needs business criticality, acceptable downtime, recovery expectations and deadlines or blackout periods from each team. An empty cell is a gap, not "low".

| Class | How identified | Default strategy | Downtime | Owner sign-off |
|---|---|---|---|---|
| Critical, migratable | Criticality table + no blocking device | Live migration | None to minimal | Schedule notice |
| Tolerates restart | Owner agrees in the table | Cold migration or coordinated restart | Agreed window | Yes, per workload |
| SR-IOV `direct` port | Port binding | Live migration (the guest briefly loses that interface), or cold | Brief interface loss | Yes |
| vGPU, pinned/NUMA | Flavor/port data | Live migration if the release and versions allow it (verify for your release) | None to minimal | Schedule notice |
| Not live-migratable (flavor PCI passthrough, `direct-physical`, memory-heavy without auto-converge or post-copy) | Flavor/port data | Cold migration or coordinated restart | Agreed | Yes |
| Can't be touched before the deadline | Owner decision | Exception | n/a | Yes |

## Capacity check
Capacity has to hold **per AZ**, not in total. Formulas for you to fill in:

- Hosts that can be down at once in AZ *x*: `N_down(x) ≤ spare_capacity(x) / host_capacity(x)`. This needs vCPU, RAM and disk each checked against the destination hosts' free capacity.
- Batches per AZ ≈ `hosts(x) / N_down(x)`.
- Time per batch = migration time, bounded by max concurrent migrations (from your own baselines), plus patch and reboot, plus verification.

If live-migrating everything doesn't fit, the answer is a differentiated strategy with an explicit decision. Don't force migrations the platform can't absorb. Please send current usage and free capacity per AZ.

## Sequencing
- **Landing zone** (if the patch changes libvirt/QEMU): live migration from newer to older libvirt/QEMU isn't supported. Patch one empty or near-empty batch first and move instances only toward patched hosts. For a kernel-only patch this constraint doesn't apply.
- Check CPU-model compatibility between source and destination.
- Keep **one AZ per phase**. Finish and verify AZ-A before touching AZ-B, so a bad patch never hits both AZs.
- Start with a canary batch of one or two hosts, ideally in a low-risk class. Verify it, then scale batch size up to what the capacity check allows.
- Don't stack other changes into the same window.

## Per-host procedure
1. *Read-only:* list the host's instances and confirm each is classified and its owner informed (`openstack server list --all-projects --host <host>`).
2. *State-changing:* disable nova-compute with a reason (`openstack compute service set --disable --disable-reason "<reason>" <host> nova-compute`).
3. *State-changing:* move instances by class (live migrate, or cold migrate and confirm). Verify each: ACTIVE on the destination, reachable, performance acceptable.
4. *Read-only:* verify the host is empty, or that only agreed-restart instances remain. Record their power state. Check `resume_guests_state_on_host_boot` on the host; with the default (`False`) guests come back SHUTOFF after the reboot.
5. *State-changing:* patch and reboot. Verify the host is healthy and the compute service and agents are up.
6. *State-changing:* start the agreed-restart instances their owners expect running (`openstack server start`). The owner confirms the application is reachable.
7. Optional: validate with a test instance.
8. *State-changing:* re-enable the host (`openstack compute service set --enable <host> nova-compute`).

**Do not use `openstack server evacuate` to drain hosts, including as a speed-up.** Evacuation is for failed, fenced hosts. On a host that may still be running its instances it risks duplicate guests and data corruption.

## Boundaries and stop conditions
Set these before starting:
- Maximum hosts down at once per AZ, from the capacity check.
- Maximum concurrent migrations, from your own baselines.
- **Stop if:**
  - migrations fail, or slow beyond baseline;
  - a destination behaves unexpectedly;
  - critical-workload performance crosses the agreed threshold;
  - free capacity falls below the reserve;
  - monitoring has a blind spot;
  - the approver is unreachable.
- Resuming after a stop is a new decision.

## Decision rights and communication
Name these people before starting:
- Who approves restarts and cold migrations, workload by workload (the owners, not the infra team alone).
- Who accepts deadline exceptions.
- Who tells consumers the schedule.
- Who can call stop and who can approve resuming.

## Campaign completion criteria
- All 40 hosts patched and verified.
- Every instance either migrated or restarted since the patch, or listed as an exception with its owner.
- Every agreed-restart instance running again, or intentionally left off by its owner.
- Compute services and agents healthy, and no instance left on an unpatched binary without anyone knowing.

## Exceptions
| Workload | Reason | Compensating control | Owner | Review date |
|---|---|---|---|---|
| *(none identified yet; depends on the criticality table)* | | | | |

## Gaps and questions
1. Hosts per AZ, and spare capacity per AZ (vCPU, RAM, disk)?
2. Shared or local instance storage?
3. Release, and libvirt/QEMU versions before and after the patch?
4. Does the platform have passthrough, SR-IOV, vGPU, pinned or very large-memory instances?
5. Does a criticality table exist? If not, who can get the teams to fill it in this week?
6. Are there blackout periods this week?
7. Is the patching automated (Ansible and so on)? If so, I can review the playbook before it runs.

## Follow-up
- Keep the criticality table as a living document and use it for capacity planning.
- Add a patching scenario to capacity planning.
- If every campaign eats too much capacity, put that on the roadmap as a lifecycle problem.

If you send answers to the gaps, I can turn this into a day-by-day schedule with real batch sizes.

> Decision support only. State-changing steps above require approval by the accountable owner and should be executed under your change process.

## Turn 2

**User:**

More details: shared Ceph storage. Spare capacity is about 2 hosts per AZ. 6 VMs use SR-IOV ports, 2 VMs use PCI passthrough GPUs, and one tenant runs a 3-node database cluster spread across AZs with anti-affinity. Owners have agreed the GPU VMs can be restarted during a window.

**Assistant:**

The new details change the plan in four ways. The rest of the skeleton from my first answer still applies. Everything below from you is **Reported**, and the anything-else is flagged as a gap.

## What changes

**1. Spare of about 2 hosts per AZ: drain one host at a time per AZ.**
- Draining one host uses one host's worth of spare. Draining two at once uses all of it and leaves no reserve for a failed migration or a host failing mid-campaign.
- "About 2" needs checking against real numbers, per resource and per workload type. Free capacity may be scattered across hosts, and it may not sit on the SR-IOV or GPU hosts.
- Conclusion: **1 host per AZ at a time**, unless you can show a larger reserve.

**2. Rolling wave with a landing zone.**
- If the QEMU version changes, instances can move to patched hosts but not back.
- The efficient pattern is to patch an emptied host first. Then drain the next host *onto already-patched hosts* (target them explicitly with `--host`, or use an aggregate). Each VM then moves once, and the spare capacity travels along the AZ like a wave.
- Without this, VMs land on unpatched hosts and have to be moved a second time.

**3. Timeline arithmetic.**
- I'll assume 20 hosts per AZ because you didn't say. Please confirm.
- One host at a time means 20 sequential cycles per AZ, 40 in total. That is about 8 per working day if AZs run back to back.
- Only your measured cycle time (drain, patch, reboot, verify) shows whether that fits the week.
- If it doesn't fit, the options are below. Choosing one is a decision for the accountable owner, not for me.

| Option | Trade-off |
|---|---|
| A. One host in each AZ at the same time | Halves the elapsed time. Capacity is fine per AZ. But it adds risk to the cross-AZ database cluster, so it needs the database owner's sign-off. |
| B. Two hosts at once per AZ | Uses all the spare. I don't recommend it. |
| C. Ask for an extended deadline or a documented exception for the leftovers | Costs more exposure time. |

**4. Special workloads need their own capacity checks.** Generic spare doesn't help them:
- **SR-IOV:** free VFs on the *same physical network* on a patched, SR-IOV-capable destination.
- **GPU:** a free GPU of the same type on the destination, if you cold-migrate.
- **General:** vCPU, RAM and Ceph headroom.

## Workload classes (updated)

| Class | Count | Strategy | Notes and sign-off |
|---|---|---|---|
| GPU passthrough VMs | 2 | Planned stop → patch → start, or cold migrate if a free GPU exists on a patched host | Not live-migratable. Owners have agreed a window, so confirm that it covers the actual time. Using `openstack server stop` first is cleaner than relying on the host reboot. |
| SR-IOV `direct` ports | 6 | Live migration (supported since Train; verify for your release and NIC/driver), or cold migration/restart | The guest briefly loses that interface during the migration. **The owners must say whether that is acceptable, ideally per VM.** Run a trial migration on a non-critical SR-IOV VM first. |
| 3-node database cluster, anti-affinity across AZs | 3 | Live migration, one node at a time | See below. |
| Everything else | unknown | Live migration (shared Ceph makes it straightforward) | Criticality table still needed. Anything unclassified is treated conservatively. |

**Database cluster rules:**
- Three nodes over two AZs means one AZ holds two nodes, on different hosts because of anti-affinity.
- Never have two nodes' hosts in maintenance at once.
- Check that the cluster is healthy between each node's migration.
- Ask the owner whether the cluster tolerates the pause during a live migration (heartbeat/timeouts). If it doesn't, they may prefer a controlled, one-node-at-a-time restart.
- Anti-affinity also limits where each node can land. Confirm that enough eligible patched destinations exist.
- **Stop condition:** cluster unhealthy or lost redundancy.

## Sequencing sketch
1. **Prep (before touching anything):**
   - Collect the criticality table.
   - Run the read-only inventory below.
   - Test an SR-IOV live migration on a non-critical VM.
   - Agree the GPU window and the database procedure.
2. **Canary:** one low-risk host in the first AZ, with no special workloads. This is also your first landing zone.
3. **Special-hardware hosts early:**
   - Patch an SR-IOV-capable host that carries no SR-IOV VMs early, so the 6 VMs can move once, onto a patched host.
   - Do the same for a GPU host.
   - If no such host exists, those VMs move twice, or take a cold migration. This depends on your inventory.
4. **Then roll through the first AZ**, one host at a time, draining onto patched hosts.
5. **Review at the AZ boundary.** Check capabilities, database cluster, GPU and SR-IOV VMs. Only then start the second AZ.
6. **Last:** sweep for any instance still on the old QEMU, and handle it by migration or an agreed restart.

## Read-only inventory to run
Check the flags for your client version.
- Hosts, versions and capacity: `openstack hypervisor list --long`
- SR-IOV VMs and their hosts: `openstack port list --vnic-type direct`
- GPU flavors: `openstack flavor list --long` (look for the `pci_passthrough:alias` property)
- Anti-affinity groups: `openstack server group list`
- Per-host instances: `openstack server list --all-projects --host <host>`
- Guest resume behaviour: `resume_guests_state_on_host_boot` on a host

## Remaining gaps
1. Hosts per AZ (20/20?), plus the release and the libvirt/QEMU versions before and after.
2. Is the QEMU patch a version change, or a package patch within the same version? This decides whether the landing-zone constraint applies.
3. Which hosts carry the SR-IOV and GPU VMs, and which other hosts could take them (VFs, GPUs, physnet)?
4. Does the database cluster tolerate a live-migration pause?
5. Measured live-migration and host-cycle times from your own baselines, to decide concurrency and whether the schedule fits.
6. Criticality for the rest of the VMs, and any blackout periods.
7. Who approves and who can call stop.

If you send those, I can turn this into a day-by-day schedule with host order and a stop-condition list for the change record.

> Decision support only. State-changing steps above require approval by the accountable owner and should be executed under your change process.

## Turn 3

**User:**

We're on host 5 of 40. On cmp-a-05 the live migration of one VM failed half-way: the VM is now in ERROR and the migration shows 'error'. The other VMs on that host migrated fine. Can we carry on with cmp-a-06 to stay on schedule?

**Assistant:**

**No, hold at cmp-a-05 for now.** A failed live migration is one of the stop conditions we set. Continuing is a new decision for a named person to make, and it shouldn't be made just to stay on schedule. Two things are unknown, and both could get worse if you carry on.

## Why pause
- **We don't know where the VM is running.** After a mid-way failure it may be running on the source (cmp-a-05), on the destination, or have leftover state on both. The disks are on shared Ceph, so a guest running on two hosts is a data-corruption risk. Rebooting cmp-a-05 before you know could kill the only good copy.
- **We don't know the cause.** If it was VM-specific (memory churn, a device), cmp-a-06 may be fine. If it was a destination, network or platform problem, the next host's migrations could fail the same way, and this time with more VMs at risk.
- **Spare capacity is lower.** While cmp-a-05 is disabled and not back in service, you have roughly one host of spare left in AZ-A, not two. Don't spend it until you know.

## Don't do these until the state is understood
- `openstack server set --state` / `reset-state`: it hides the real state, and the VM might still be running.
- `server evacuate`: the host hasn't failed.
- Rebooting or patching cmp-a-05.
- Hard reboot, restart or delete of the VM.
- Re-running the migration blindly.

## Read-only checks (all safe to run now)
1. The VM's view:
   - `openstack server show <vm>` (host, status, power state, task state, fault).
   - `openstack server event list <vm>` / the instance actions.
2. The migration record: `openstack server migration list --server <vm>` (status, source and destination).
3. Where the guest actually exists:
   - `virsh list --all` on the **source and the destination**, and look for the domain on each.
   - Check the qemu process on both.
4. Ceph, if you have access: whether the VM's RBD images show watchers or locks from one host or two.
5. Logs for the failure window: nova-compute on both hosts, libvirt/QEMU logs, and the conductor.
6. Whether any other VM on the destination host shows problems.

## What I need from you
- Output of 1 to 3.
- The error line from the nova-compute logs. Redact any credentials first.
- Which VM it is. If it is one of the 6 SR-IOV VMs, the 2 GPU VMs or a database node, say so. A database node also means checking the cluster's health now.
- Which destination host was used.

## Resuming: conditions for a decision
Whoever holds decision rights (the change owner or incident lead) should record a decision on these:
- The VM's state is known and it is protected: running on exactly one host, or accepted as down by its owner.
- A cause, or at least a leading hypothesis, with a reason to believe it won't repeat on cmp-a-06. If it's VM-specific, that VM can be excluded from the next drain and handled on its own plan with its owner.
- cmp-a-05 is either completed under a separate plan or deliberately left out of service, and the capacity reserve is rechecked.
- The earlier stop conditions still apply to cmp-a-06, and the first migrations are watched closely.

If you decide to continue with a reduced scope, that is a legitimate option, but it needs a named approver.

## Schedule
If the hold costs you the week, that is an exposure trade-off for the accountable owner, who can choose to extend the deadline, accept parallel AZs (option A from earlier) or take a documented exception. Don't make that choice implicitly by carrying on. Send me the check outputs and I'll help work out the cause and the next step.

> Decision support only. State-changing steps above require approval by the accountable owner and should be executed under your change process.
