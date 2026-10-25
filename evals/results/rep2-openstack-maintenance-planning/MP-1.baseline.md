# Plan for patching 300 hosts in 3 weeks

## 1. Capacity and throughput
- **Cadence.** With about 8 free hosts, you can drain about 6 at a time and keep 2 as margin. That is 2 per AZ, so one AZ's problem never blocks the others. 300 / 6 is about 50 wave-slots. Over 15 working days that is about 3.5 slots per day, so each host's drain, patch, reboot and validate cycle has to fit in about 2 to 3 hours.
- **Drain speed is the constraint.** Measure it in a canary before you commit to a calendar. If the average host takes more than 3 hours, you need more parallelism or more temporary capacity. Borrowing hosts, spare racks or a few cloud or lab nodes is cheaper than missing the deadline.
- **Leapfrogging.**
  1. Patch the spare hosts first.
  2. Live-migrate VMs from the next hosts onto the patched spares.
  3. Patch those emptied hosts, which become the new spares.
  4. Repeat.
- **The QEMU fix needs a migration.** A running VM keeps its old QEMU process until it restarts or moves to a host with the new binary. Draining onto patched hosts fixes both problems in one step. Don't patch hosts in place with VMs running and call it done.
- **Order within an AZ.** Start with the hosts that have the fewest VMs. That grows your patched pool fastest and leaves the heavy hosts for last, when you have the most headroom.

## 2. SR-IOV tenants (the main risk)
- Live migration of VMs with SR-IOV VFs is unsupported or fragile in many Nova and driver combinations. Check what your release and NICs actually support before assuming either way.
- Inventory the VMs with SR-IOV ports now (`port.binding:vnic_type=direct`) and map them to hosts.
- Put the SR-IOV hosts in their own track, with their own spare hosts. A target host needs the same physnet and free VFs.
- Tell those tenants about the disruption (cold migrate, or detach and reattach the port) and agree windows with them. Start this in week 1, because it is the slowest part and has the longest lead time.
- Test one SR-IOV VM end to end in the canary so you know the real downtime.

## 3. Not knowing which VMs are critical
You won't classify 10k instances by hand, so don't try. Do three things instead:
- **Treat every VM as critical by default.** That means live migration only, with no surprise stops or reboots. This is a policy that needs no per-VM knowledge.
- **Use proxies to identify the VMs that can't migrate.** Look at SR-IOV, CPU pinning, hugepages, local-disk or non-volume-backed VMs, and very large or write-heavy VMs that won't converge. Also look at server-group anti-affinity, so you never drain two hosts holding members of the same group at once.
- **Notify tenants.** Send one notice in week 0. Tell them what is happening and when, and ask them to flag critical workloads or request a window. Anything that needs downtime gets an explicit, scheduled window. Silence means live migration only.

## 4. Phases

| When | What |
|---|---|
| **Week 0 (prep)** | Inventory VMs, SR-IOV ports, local-disk VMs and server groups per host. Build and test the drain and patch runbook. Patch the spare hosts. Send the tenant notice. Fix migration settings (auto-converge, post-copy, bandwidth limits). |
| **Week 1** | Canary of 2 to 3 hosts per AZ, including 1 SR-IOV host. Measure drain time and failure rate. Then ramp non-SR-IOV waves in one AZ, then the others. |
| **Week 2** | Full cadence across all AZs, with the SR-IOV track running in parallel under its agreed windows. |
| **Week 3** | Stragglers, failed migrations, tenant exceptions and verification. Keep about 3 working days as buffer, not as planned work. |

Run one automated loop per host: disable the host in Nova, live-migrate everything off, patch, reboot, verify the kernel and QEMU versions, run a test boot, then enable the host and move on. Gate the loop on failure rate. If more than a few migrations fail or the spare pool drops below 2, it pauses automatically.

## 5. Safeguards
- Set a per-AZ cap on hosts out at once, and a global cap.
- Define rollback before wave 1: keep the old kernel in GRUB, and keep the old QEMU package available.
- Have a decision rule for VMs that won't migrate. For example, after N failed attempts, escalate to the tenant with a deadline, then force a stop/start in a stated window.
- Report daily: hosts patched, hosts remaining, failures, exceptions and spare capacity.

## Questions that change the plan
1. What are your Nova release and NIC vendor? They decide whether SR-IOV live migration works at all.
2. Is storage shared (Ceph or volume-backed) or local? Local storage makes block migration much slower.
3. Is a 3-week deadline firm for every host, or only for hosts running untrusted tenants? A risk-ranked order would help if you fall behind.
4. How many VMs are there per host, and how many are SR-IOV?

If you can answer those, I can turn this into a day-by-day schedule with wave sizes. I can also publish it as a page for the team.