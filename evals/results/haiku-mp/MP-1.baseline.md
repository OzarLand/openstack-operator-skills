The main constraint is spare capacity, not the three weeks. Your 8 spare hosts can act as a rotating buffer, but only if VMs can move off a host without downtime, and SR-IOV and unknown criticality are what will break that. I'd plan it in four steps.

## 1. Start with inventory, not criticality

Don't wait for the infra team to learn which VMs matter. For planning you need four facts per host and per VM:

- **AZ and free capacity** (vCPU, RAM, and whether the free space is in the same AZ)
- **Migratable or not**: SR-IOV VFs, CPU pinning, NUMA, GPU/vGPU passthrough, local disks, and any "do not migrate" flags
- **Tenant and owner**, so you know who to notify
- **Criticality tag**, if any exists in CMDB, project metadata, or tenant contacts. Treat blanks as "needs a planned window," not "critical" or "disposable."

Classify each host:

- **A. Empty or near-empty**: patch first. These are your first targets.
- **B. Live-migratable only**: fully automatable.
- **C. SR-IOV or pinned**: needs tenant coordination, cold migration, or a short planned restart.
- **D. Not evacuable** (passthrough, local state): needs a tenant-scheduled window or an exception.

Count C and D early. If they are 20% or more of the fleet, that is your schedule risk, not the 8 spare hosts.

## 2. Fix the sequencing rule

- **A kernel fix requires a host reboot**, so every VM on that host has to be moved or restarted.
- **A QEMU fix requires the QEMU process to restart**, which means a live migration to a patched host, or a restart. A running VM keeps the old QEMU until it moves.

So the rule is: **patch the spare hosts first, then use them as migration targets.** Each patched host becomes new buffer, so the pool rotates instead of being consumed. Never migrate VMs onto an unpatched host as a "temporary" move, because those VMs remain vulnerable.

## 3. Check whether the buffer math works

These numbers are assumptions. Substitute your real ones:

- ~20 VMs per host, 300 hosts, roughly 100 per AZ
- Keep about 30% headroom, so 8 spare hosts give about 5–6 hosts' worth of usable space
- That's ~2 hosts per AZ, not 8 total, because VMs can't leave their AZ

At 2 hosts per AZ, each AZ needs ~50 waves. At ~1.5 hours per wave, that's ~75 hours per AZ, which fits in 3 weeks **only if nothing fails**. One failed migration or one oversized VM can stall a whole wave.

So the plan should include **temporary capacity**, borrowed from other clusters or AZs. Buying hardware won't arrive in 3 weeks. Ask for this in week 1, not week 3.

## 4. Scope the security ask

Before committing to "all 300 in 3 weeks," get answers from security:

- **Exposure**: the threat is probably guest-to-host escape, so prioritize multi-tenant and internet-facing hosts first.
- **Mitigations**: is there a workaround, such as disabling a device model or feature, that buys time for the hard hosts? Ask for the exact CVE IDs and affected QEMU/kernel versions.
- **Exceptions**: define a documented exception path for class D hosts, with compensating controls and a date.

## Suggested timeline

- **Days 1–3**: inventory, classification, tenant notices for class C/D, capacity request, and a migration test on one live-migratable VM plus one SR-IOV VM to confirm the procedure and rollback.
- **Days 4–5**: patch the 8 spare hosts and class A hosts. Verify with a version report.
- **Days 6–15**: run class B waves per AZ, with automated cordon, evacuate, patch, reboot, verify, and uncordon. Track each host's status so security gets a live count.
- **Days 16–21**: class C windows with tenants, class D exceptions, and stragglers.

Two things would sharpen this: which virtualization stack you run (OpenStack, libvirt, something else), and whether the SR-IOV VMs can be live-migrated in that stack. If you share a host or VM export, I can calculate the per-AZ waves and the class C/D counts directly. I can also write this up as a plan document for the team.