# Rolling patch plan: 300 hosts, 3 AZs, about 8 hosts of headroom

The capacity is enough, and so is the time. The risks are SR-IOV instances, how usable the free capacity really is, and the lack of any criticality data. The plan below deals with each of those.

## 1. Treat the 8 free hosts as a leapfrog buffer

- Patch the empty hosts first. They become the already-patched destinations.
- Live-migrate guests from the next batch onto them, patch the vacated hosts, then repeat.
- Live migration also gets you the QEMU fix. A running guest keeps its old QEMU process until it is restarted or migrated, so patching a host in place does nothing for the guests on it.
- Migrate only within an AZ. Cross-AZ moves break AZ semantics and Cinder placement. With roughly 100 hosts and 2–3 free hosts per AZ, run **batches of 2 hosts per AZ at a time**. That leaves about 1 host of slack per AZ for failed migrations and node failures.
- Set the scheduler to prefer patched hosts (a weigher or an aggregate). New instances then land on patched hosts and your unpatched backlog shrinks.

## 2. Check the "8 hosts free" number first

This is the most common way a plan like this fails.

- Is the free capacity spread evenly across the 3 AZs?
- Is it in the right aggregates? Free space on general-purpose hosts doesn't help if the VMs are pinned, hugepage-backed, NUMA-sensitive, GPU or SR-IOV.
- Is it fragmented? Eight hosts at 90% full is not the same as 8 empty hosts.
- If an AZ or aggregate is short, your options are:
  - delete or shelve dead instances;
  - ask tenants to clean up;
  - borrow or add a few hosts temporarily;
  - patch that aggregate last and slowly.

## 3. Handle SR-IOV as its own cohort

- Whether these can be live-migrated depends on your Nova, libvirt and neutron versions and your NIC setup. Older releases can't do it at all. Newer ones can, using detach/reattach or a failover bond. **Test on one non-production VM before you plan around it.**
- If live migration isn't supported, these instances need downtime (cold migrate or a tenant-coordinated reboot), so they need notice and windows.
- Capacity for them is limited by free VFs on the same physnet on the destination, not just CPU and RAM. Count VFs per host and per AZ.
- Find them with Neutron ports where `binding:vnic_type` is `direct` or `direct-physical`, plus flavors that carry a PCI passthrough alias.

## 4. Unknown criticality: don't try to guess it

Assume everything is critical and choose the method by risk instead.

- **Live-migratable instances** (most of them) are safe to move without asking anyone.
- **Instances that can't be live-migrated** (SR-IOV, passthrough, local-only state, dirty-page rates that never converge) get tenant notice. Send it **this week**, with a hard deadline, for example "migrate or reboot yourself in this window, or we do it on date X."
- Pull what you can from the API and group by project to build the notification list:
  - project owner and flavor
  - uptime
  - volume-backed or ephemeral
  - server groups (anti-affinity matters for the order of moves)
  - SR-IOV ports
- Offer opt-in windows and a "do not touch before X" request. Record the exceptions and escalate them early, not in week 3.

## 5. Timeline (today is Oct 25, so the deadline is about Nov 15)

| When | What |
|---|---|
| Days 1–3 | Inventory: capacity per AZ and aggregate, SR-IOV list, live-migration test. Send tenant notices. Write the automation. |
| Days 4–6 | Pilot on 2 hosts in one AZ. Soak 24–48h. Fix whatever breaks. |
| Weeks 2–2.5 | Roll through AZ1, then AZ2 and AZ3, in parallel if the pilot was clean. Do one batch per AZ at a time. |
| Last 4–5 days | Stragglers: SR-IOV, non-migratable, opted-out. Forced action on the announced date. |

Rough math is about 4 batches of 2 hosts per AZ per day, so about 12 working days. That leaves slack, but not much if migrations are slow.

## 6. Per-host automation (stop on first failure)

1. Disable the compute service.
2. Live-migrate all instances off, then verify the host is empty.
3. Patch the kernel and QEMU/libvirt, then reboot.
4. Verify kernel and QEMU versions, `nova-compute` up, network agents up, and a test VM boots.
5. Enable the service and move to the next host.

- Cap concurrent migrations per host. Use a dedicated migration network if you have one.
- Enable auto-converge or post-copy for busy guests.
- Have a rollback ready: keep the old kernel in the boot menu and keep the old packages available.

## 7. Questions to answer before you start

- Which release are you running, and does it live-migrate SR-IOV ports?
- Is storage shared (Ceph) or local? Local storage makes every migration much slower.
- How many SR-IOV instances are there, and on which physnets?
- Are the 8 free hosts spread across AZs and aggregates in a usable way?
- Do any tenants have contractual SLAs or change-freeze periods before mid-November?

If you can give me the SR-IOV count and the per-AZ free capacity, I can turn this into a day-by-day schedule. I can also publish it as a shareable page for the team if you'd like.