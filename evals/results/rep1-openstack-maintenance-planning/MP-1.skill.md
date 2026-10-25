# Plan: kernel and QEMU fix on 300 compute hosts in 3 weeks

The plan fixes the requirement (all 300 hosts patched in 3 weeks) and designs the execution around what you have. That is 8 hosts of spare capacity, instances you can't tell apart, and some SR-IOV tenants. You can only fully meet the deadline if you know which workloads may be restarted, so collecting that is the first job.

## 1. Requirement and constraints

- **Fixed:** kernel and QEMU fix on all 300 hosts, due in 3 weeks (**Reported**, from Security).
- **Constraint 1:** about 8 hosts of free capacity in total (**Reported**).
- **Constraint 2:** criticality is unknown. Nova sees instances, not business processes.
- **Constraint 3:** some SR-IOV tenants.
- **Exposure to state if you slip:** the CVE details, such as whether it is exploitable from a guest. I don't have them, so ask Security. That decides how much disruption is justified.
- **Important:** the QEMU fix only protects instances that have been migrated or restarted since the patch. Patching a host leaves its running guests on the old binary. Track this per instance, not per host.

## 2. Scope and gaps

Nothing below was shown to me, so these are gaps. I'm not assuming them.

| Gap | Why it matters |
|---|---|
| Host split per AZ (about 100 each?) | Capacity is calculated per AZ. |
| Where the 8 spare hosts are | 8 hosts-worth of fragmented free space is not 8 empty hosts. It may be 2 or 3 per AZ, or 8 in one AZ. |
| Current QEMU/libvirt versions, CPU models | Newer-to-older live migration is unsupported, and CPU models limit destinations. |
| Instance storage (shared Ceph vs local) | Local disks need block migration, which loads the network and storage. |
| Release | Migratability rules depend on it (SR-IOV live migration since Train). |
| Do AZs map to aggregates or flavors? | Constrains where instances can land. |
| Any GPU, PCI passthrough, pinned or huge-memory flavors | These can't be live-migrated, or only with conditions. |

## 3. Workload classes

**Step 0 is the criticality table, and it comes first.** Send consuming teams a shared table, using the template in `references/criticality-table-template.md`. It asks for:
- criticality
- acceptable downtime
- recovery expectations
- blackout periods
- an owner
- the agreed strategy

An empty cell means a gap, not low criticality. Anything unanswered is treated conservatively. By default it is live-migrated if it can be, and it is escalated rather than restarted without agreement.

You don't have to wait for every answer before starting. Start with workloads that need no decision, such as empty hosts. Set a response deadline of about 3 to 4 working days.

| Class | How identified | Strategy | Downtime | Sign-off |
|---|---|---|---|---|
| Critical, migratable | table says critical, no blocking device | Live migration (block migration if local disk) | None to seconds | Not needed beyond notice |
| Tolerates restart | owner-agreed | Cold migration, or restart in place on the reboot | Minutes | Owner |
| SR-IOV `direct` port | port type in Neutron | Live migration if the release is Train or later and the NIC and driver support it. The guest loses that interface briefly (unplug and replug). Otherwise cold migration. | Brief NIC loss, or restart | Owner must accept the NIC interruption |
| SR-IOV `direct-physical`, flavor PCI passthrough | Neutron port type, flavor alias | Not live-migratable. Cold migration or coordinated restart. | Restart | Owner |
| Large-memory, write-heavy | flavor and metrics | Live migration only with auto-converge or post-copy. Otherwise restart. | Varies | Owner |
| Can't be touched before the deadline | owner says so | Exception, with compensating control and a review date | n/a | Security and the owner |

**SR-IOV:** *verify for your release.* Upstream Nova supports live migration of `direct` ports since Train. The book lists them as not migratable, so check the Nova and Neutron SR-IOV docs for your release and test on one host first. Treat SR-IOV tenants as a separate, early conversation.

## 4. Capacity check

Capacity is per failure domain, so one host down per AZ needs spare capacity equal to one host in *each* AZ. That does not mean one host overall.

**Formula (per AZ):** hosts you can drain at once = spare capacity in the AZ, expressed in hosts, minus a reserve for failures during the campaign.

**With your numbers:** about 8 spare hosts / 3 AZs gives about 2.7 per AZ on average. That is only a ceiling if the spare is evenly spread, which I haven't seen. If one AZ has 1 spare host and another has 5, the poorest AZ sets the pace for that AZ.

A first estimate, which **you need to confirm against real numbers:**
- Drain 1 host per AZ at a time at minimum, and 2 if the spare allows and you keep a reserve for an unplanned host failure. That means 3 to 6 hosts in flight.
- 3 weeks is about 15 working days. 300 hosts / 6 in flight = 50 rounds, so about 3.3 rounds a day. At 3 in flight it is 100 rounds, about 6.7 a day. That is a lot if each round (drain, patch, reboot, verify) takes a couple of hours and migration is slow.
- **Conclusion:** the 3-week deadline is only plausible with 2 or more hosts per AZ in flight, fast drains, and a substantial share of workloads agreed as restartable or cold-migratable. It is unlikely if everything must be live-migrated one host at a time. Confirm with real drain timings from a pilot before committing to the deadline.

The effect of restartable workloads on capacity is large. A restartable instance doesn't need free capacity elsewhere if it stays on the host through the reboot. This is the main lever on your capacity problem.

## 5. Sequencing

1. **Pilot, 1 host per AZ in week 1.** Use hosts with non-critical or volunteer tenants. Measure drain time, migration failure rate, and SR-IOV behaviour. Then fix batch sizes from this data, not guesses.
2. **Landing zone.** Patch the emptiest hosts first, and use them as the first destinations for migrations. After the QEMU patch, instances can move onto patched hosts but not back to unpatched ones. So direct migrations only toward patched hosts, and don't migrate onto unpatched ones when avoidable.
3. **Roll as a wave.** Patched hosts re-enable and become landing space for the next batch. Free capacity then moves through the fleet instead of being used up.
4. **Per-AZ rule.** Never drain more hosts in an AZ than its spare capacity minus the reserve. Stagger the three AZs so they are never all at the same stage, and keep one AZ untouched when possible.
5. **SR-IOV hosts last in the order, but scheduled early** with the tenants, so there is time to negotiate downtime.
6. **Don't stack changes.** Keep this separate from other changes in the same window.

## 6. Per-host procedure

1. Confirm instances on the host are classified and owners informed. `openstack server list --all-projects --host <host>` (**read-only**).
2. Disable the host: `openstack compute service set --disable --disable-reason "<reason>" <host> nova-compute` (**state-changing**).
3. Move instances by class: live migrate (`openstack server migrate --live-migration`, with `--block-migration` for local disk) or cold migrate (**state-changing**). Verify each one is active on the destination, reachable and performing normally.
4. Check the host is empty, or that only agreed-restart instances remain. Record their power state. Read `resume_guests_state_on_host_boot` (**read-only**). If it is `False`, the default, those guests come back `SHUTOFF`.
5. Patch the kernel and QEMU, then reboot (**state-changing**). Verify the compute service and network agents are up.
6. Start the agreed-restart instances the owner expects running (**state-changing**), and have the owner confirm the application works.
7. Optionally boot a test instance on the host.
8. Re-enable the service (**state-changing**).

**Never use evacuation for maintenance.** It is for failed hosts only, and a host that may still be running its instances must never be evacuated.

For stopping `nova-compute` as a way to speed up draining: don't. It doesn't move anything, and it risks the evacuation pitfall above.

## 7. Boundaries and stop conditions

Set these before starting:
- Maximum hosts drained per AZ at once (from the capacity check and the pilot).
- Maximum concurrent migrations, taken from your own baseline and not a generic number.

**Stop when:**
- migrations fail or slow beyond the baseline
- a destination behaves differently than expected
- critical workload performance crosses the agreed threshold
- spare capacity in an AZ falls below the reserve
- monitoring has blind spots
- the approver is unavailable
- an unplanned host failure happens in the AZ you're working in

Resuming after a stop is a new decision.

## 8. Decision rights and communication

- **Infra team decides:** order and method, within the boundaries.
- **Workload owners decide:** whether each workload can restart or lose an SR-IOV interface.
- **Security and the accountable manager decide:** deadline exceptions, and the risk trade-off if capacity forces them.
- **Name one person** to communicate schedules to tenants, and give tenants at least one advance notice with their slot.

## 9. Completion criteria

- Every host is patched and verified.
- Every instance was migrated or restarted after the patch, or is listed as an exception with an owner.
- No instance is left on the old QEMU without being known. Check this per instance, since a patched host can still run old guests.
- Restarted instances are confirmed running, or intentionally left off by their owner.
- Compute services and agents are healthy.

## 10. Exceptions (template)

| Workload | Reason | Compensating control | Owner | Review date |
|---|---|---|---|---|
| | | | | |

## 11. Questions I need answered

1. Host count and spare capacity per AZ, and whether the spare is whole empty hosts.
2. OpenStack release, current QEMU/libvirt versions, CPU models, and storage backend.
3. How many instances use SR-IOV, which port types, and which NICs.
4. Does the kernel/QEMU CVE have guest-to-host exposure? How strict is the 3-week date for Security?
5. Who can compel tenants to answer the criticality table?
6. Typical drain time per host, from any past maintenance.

## 12. Follow-up

- Keep the criticality table current, as a shared document or instance metadata.
- Add maintenance scenarios to capacity planning. If every campaign eats this much capacity, 8 spare hosts out of 300 (about 2.7%) is a lifecycle problem for the roadmap.

> Decision support only. State-changing steps above require approval by the accountable owner and should be executed under your change process.

I can turn this into a one-page schedule or a ready-to-send criticality table for tenants. For the schedule I'd need the per-AZ numbers.