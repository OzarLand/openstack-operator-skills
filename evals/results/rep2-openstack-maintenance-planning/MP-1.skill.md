**Short version:** the deadline is fixed, so the real question is whether 8 hosts of free capacity can carry a rolling campaign at the required pace. They can, but only just, and only if you stop treating capacity and criticality as unknowns. Treat unknown criticality as "don't restart without asking", live-migrate by default, and collect criticality from tenants in parallel. I've labelled what you told me as **Reported** and my own working numbers as **Assumption**.

## 1. Requirement vs. strategy
- **Fixed (Reported):** kernel + QEMU fix on all 300 hosts in 3 weeks.
- **Clarify with Security:** does "done" mean hosts patched, or every instance running the new QEMU? It has to mean the latter. A QEMU fix only protects instances that were migrated or restarted after it was installed, and the kernel needs a reboot anyway. So every instance has to move or restart.
- **Flexible:** how each instance gets moved.

## 2. Capacity check (the binding constraint)
Free capacity is conserved in a rolling campaign. A patched host comes back empty and becomes the next landing spot. So 8 spare hosts caps how many hosts you can drain **at once**, not the total.

- **Assumption:** about 100 hosts per AZ, and spare capacity of about 2.7 hosts per AZ if it's spread evenly. You haven't told me the real split, and the AZ with the least spare sets the pace.
- Rule: hosts drained at once in an AZ ≤ spare in that AZ − reserve.
- At 2 per AZ, 6 hosts are in flight and about 2 hosts of reserve remain.
- Required pace: 300 hosts ÷ ~12–15 working days (after a 3-day buffer) is **20–25 hosts/day**.
  - With 6 in flight, a full cycle (drain, patch, reboot, verify) must finish in about 2–2.5 hours.
  - With 3 in flight (1 per AZ), it would need about 1 hour. That is unrealistic.
- The cycle time is unknown, so measure it in the pilot. If it doesn't fit, you need more capacity, tenant-agreed restarts to shorten drains, or a documented exception. Don't compress safety.

Things that can make the "8 hosts" figure misleading, each a gap to close:
- Is it empty hosts, or a few percent smeared across all hosts? If smeared, you must consolidate first, which costs extra migrations.
- Does it respect fragmentation (flavor sizes, NUMA, CPU model, aggregates)?
- Does it also have to cover a host failure mid-campaign? If so, your usable figure is lower.
- Is it per AZ or one pool?
- New tenant instances will land on freshly patched empty hosts and eat the spare. Alarm on free capacity per AZ.

## 3. Workload classes
Nova sees instances, not business impact. You need two independent inputs.

**Business criticality (gap):** only the tenants know it.
- Send the criticality table now, with a reply deadline of about day 3. Columns: workload, criticality, acceptable downtime, recovery expectation, blackout periods, owner, agreed strategy.
- An empty cell is **not** "low". Silent tenants default to "live-migrate, never restart".
- Offer a carrot: tenants who agree to a restart window help you go faster.

**Technical migratability (read-only, you can do this now):**

| Class | How to identify | Strategy |
|---|---|---|
| Normal, migratable | default | Live migration (block migration if local disks, which adds network and storage load) |
| SR-IOV `direct` port | Port `vnic_type=direct` | Live migration is supported since Train: the NIC is unplugged and re-plugged, so the guest briefly loses that interface. Verify for your release and NIC. Ask the owner whether that interruption is acceptable. |
| SR-IOV `direct-physical`, flavor PCI passthrough | `direct-physical` ports, flavor `pci_passthrough:alias` | Not live-migratable. Cold migration or coordinated restart with the owner's agreement, which needs downtime. |
| Large-memory or write-heavy | Flavor size, dirty rate | Needs auto-converge or post-copy, otherwise cold migration or restart. |
| vGPU / pinned NUMA | Flavor extra specs | Conditional: vGPU needs a recent libvirt, QEMU and kernel, and pinned/NUMA instances need Train or later. Verify for your release. |
| Can't be touched before the deadline | Owner says so | Exception: owner, compensating control, review date |

SR-IOV has a second constraint: the destination needs a free VF on the same physnet. SR-IOV-capable hosts may be a smaller pool than your 8 spare, and they can become the real bottleneck. Check this early.

## 4. Sequencing
1. **Landing zone first (if QEMU changes version).** Live migration from newer to older QEMU is unsupported. Patch the spare/empty hosts first, then move instances only toward patched hosts. Never move back.
2. **Canary:** one host in one AZ. Check live migration old→new, a test instance, and the tenant-visible metrics. Then one host per AZ.
3. **Waves:** at most k hosts per AZ at once (k from §2). Stagger AZs rather than patching all three at full speed. Tenants who built for AZ redundancy are protected only if you don't break all AZs together, and a bad patch should show up in one AZ first. If the deadline forces overlap, that is a decision for the owner.
4. **SR-IOV / passthrough / restart-agreed tenants** go in agreed windows, not in the migration flow.
5. **Last ~3 days:** buffer for stragglers, failed migrations and exceptions.

Separately: keep this campaign apart from other changes in the same window.

## 5. Per-host procedure
1. Read-only: list the host's instances (`openstack server list --all-projects --host <h>`). Confirm each is classified and its owner informed.
2. State-changing: `openstack compute service set --disable --disable-reason "<reason>" <h> nova-compute`.
3. State-changing: move instances by class. Live migration is `openstack server migrate --live-migration`. Cold migration is `openstack server migrate`, then confirm the resize. Verify each instance: ACTIVE on the destination, reachable, performance acceptable.
4. Read-only: confirm the host is empty. For agreed-restart instances left behind, record their power state and read `resume_guests_state_on_host_boot`. The default is `False`, so those guests come back SHUTOFF.
5. State-changing: patch and reboot. Verify the kernel version, the QEMU/libvirt version, and that compute and network agents are up.
6. State-changing: start the agreed-restart instances and have the owners confirm the applications.
7. State-changing: `openstack compute service set --enable <h> nova-compute`.
8. Record per instance "migrated or restarted after the patch: yes or no".

**Never use `evacuate` to speed up draining.** It is for failed, fenced hosts only. On a healthy host it risks double-running instances and corrupted disks.

## 6. Stop conditions (define before starting)
- Free capacity in any AZ drops below the reserve.
- Migrations fail, or run slower than the pilot baseline.
- A destination behaves differently from expected.
- Performance of a known-critical workload crosses its agreed threshold.
- A monitoring blind spot appears.
- The decision-maker is unreachable.

After any stop, resuming is a new decision, not an automatic continuation.

## 7. Decision rights
- **Security owner:** accepts any deadline exception or exposure.
- **Workload owners:** approve restarts and downtime, and accept the SR-IOV interface interruption.
- **Platform lead:** approves concurrency, batch size and stop conditions.
- **One named person:** sends consumer communications (schedule, windows).

## 8. Gaps I need answered
1. Hosts and spare capacity per AZ, and whether the spare is empty hosts or fragments. (`openstack hypervisor list` plus per-AZ usage.)
2. Release, libvirt/QEMU versions, CPU models, and whether the fix changes the QEMU version.
3. Instance storage: shared (Ceph) or local disks?
4. How many instances use `direct`, `direct-physical`, PCI-alias flavors, vGPU or pinned CPUs, and how many SR-IOV-capable hosts exist.
5. Average instances per host, and live-migration concurrency and speed on your platform.
6. Do you have a capacity reserve for host failure during the campaign?
7. Is the 3 weeks measured in working days or calendar days, and is there a freeze or blackout period?
8. What does Security accept for instances that can't move in time?

## 9. If it doesn't fit
In order of preference:
1. Borrow or temporarily add hosts to raise k.
2. Get tenants to agree restart windows for non-critical workloads, to shorten drain times.
3. Run all three AZs concurrently, with the owner's explicit acceptance of the correlated risk.
4. Document named exceptions with compensating controls and a review date.
5. Don't push migrations beyond the stop conditions to hit the date.

## 10. Completion criteria
- Every host is patched and verified.
- Every instance was migrated or restarted after the patch, or is a listed exception.
- Every agreed-restart instance is confirmed running, or deliberately left off by its owner.
- Keep the criticality table afterwards as an input to capacity planning. If every campaign eats this much capacity, put it on the roadmap.

*Decision support only. State-changing steps above require approval by the accountable owner and should be executed under your change process.*

If you want this as a shareable page for the infra and security teams, say so and I'll publish it.