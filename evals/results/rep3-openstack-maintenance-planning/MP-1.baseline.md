# Plan for patching 300 hosts in 3 weeks

## Capacity and time budget
- 300 hosts over 3 AZs is about 100 per AZ. Free capacity is about 8 hosts in total, so roughly 2 to 3 per AZ. You'll need to confirm the real per-AZ figure, because it sets the batch size.
- Capacity comes back after each host is patched and returned to service. That makes this a rolling or "leapfrog" upgrade, so the 8 hosts are your working buffer and not a hard limit on the total.
- Run **2 hosts per AZ at a time** (6 in flight) and keep 1 to 2 hosts of reserve for failures. At about 100 hosts per AZ that is about 50 cycles per AZ. You'd need about 3 or 4 cycles a day per AZ if you only work weekdays, which is tight.
- If drain-patch-reboot-validate takes more than about 3 hours, the plan doesn't fit. Run AZs in parallel with automation and consider extending the windows beyond business hours. Measure real cycle time on the canary before committing to dates.

## Sequence
1. **Week 0 (days 1–3): prep and discovery**
   - Pull per-AZ free capacity and check that each AZ can really absorb a batch. Check aggregates, flavors and NUMA or hugepage constraints too.
   - Classify every VM:
     - Live-migratable.
     - SR-IOV, GPU, pinned or otherwise non-migratable.
     - Local-disk (no shared storage).
     - Large or write-heavy (migrations may not converge).
   - Build and test the automation: disable the host, migrate, patch, reboot, verify kernel and QEMU versions, then enable.
   - Patch **one canary host per AZ** and let it soak for 24 to 48 hours. This tests the kernel and QEMU change itself and gives you a real cycle time.
2. **Week 1: start with the hard cases**
   - Start SR-IOV and non-migratable tenant notifications **on day 1**. They have the longest lead time (see below).
   - Patch the AZ-by-AZ rolling batches for ordinary hosts in parallel.
3. **Week 2: bulk of the fleet**
   - Run at full speed. Review the burn-down daily.
4. **Week 3: stragglers and buffer**
   - Handle hosts that failed to drain, tenant exceptions and reboot failures. Don't plan to use this week for the bulk, because it is your only slack.

## Use patched hosts as targets
The QEMU fix only applies to a VM when its QEMU process restarts. Live-migrating a VM onto an already-patched host gives it the new QEMU, and the kernel reboot covers the old host. So:
- Patch the empty buffer hosts first.
- Drain the next batch onto them.
- Patch the drained hosts, which become the new buffer.

Each VM then moves once, not twice.

## SR-IOV
- Check whether your Nova, libvirt and NIC combination supports live migration with SR-IOV ports. Support depends on version and NIC. If it doesn't work, assume cold migration or stop/start, which means downtime.
- Verify the destination has free VFs on the same physical network. Plan a dedicated SR-IOV host group with its own buffer, so these tenants don't compete with everyone else.
- Send tenants a **maintenance notice with a fixed window and a self-service option** (they can move or restart on their own schedule before a deadline). Whatever they haven't moved by the deadline gets moved by you.
- Separate patching these hosts from the rest of the fleet. They are the likely schedule risk.

## Unknown criticality
You can't classify criticality reliably, so don't try to guess. Instead, make the process safe for any VM:
- **Live-migrate by default.** Most VMs see only a brief pause, so criticality barely matters for them.
- **Criticality only matters for non-migratable VMs.** For those, notify the project owner and let them choose a slot. Use project or tenant contacts, flavor, tags or metadata, and naming as hints.
- **Respect anti-affinity and server groups.** Never drain two hosts that hold members of the same group together. Check this in the batch selection.
- Publish a calendar, give tenants a notice (a week ahead is reasonable), and offer an "opt into a window or we pick one" model.
- Ask security for **risk-based ordering**: patch internet-facing, multi-tenant-dense or untrusted-workload hosts first, in case you can't finish everything.

## Guardrails
- Set concurrency caps for migrations per host and per AZ, and use auto-converge or post-migration for busy VMs.
- Make the process halt on failure: stop the pipeline if a batch has more than N failed migrations or hosts that don't come back.
- Keep the old kernel bootable for rollback, and know the QEMU rollback path.
- Track daily: hosts done, hosts in flight, buffer remaining, failed migrations and tenant exceptions.

## Questions I'd settle first
1. What is the free capacity per AZ, and is storage shared (Ceph) or local?
2. Is the SR-IOV live-migration path supported in your Nova and NIC versions?
3. How long does drain-to-return take on a typical host?
4. Can you work outside business hours?
5. Is there a hard dependency on specific hosts (GPUs, pinned CPUs, dedicated tenants)?

If it would help, I can turn this into a shareable page with a timeline and a batch schedule once you have the per-AZ numbers.