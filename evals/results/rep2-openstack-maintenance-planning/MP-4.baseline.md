## Turn 1

**User:**

I need to patch 40 compute hosts (kernel + QEMU) this week, 2 availability zones. How should I plan it?

**Assistant:**

# Patch plan: 40 compute hosts, 2 AZs, kernel + QEMU

I'm assuming OpenStack/Nova with live migration. Tell me if that's wrong and I'll adjust.

## Core principles
1. **Do kernel and QEMU in one cycle per host.** A new QEMU only applies to VMs started or migrated after the update, and the kernel needs a reboot anyway. So the cycle is drain, patch both, reboot, verify, re-enable. This touches each VM once.
2. **Never work on both AZs at the same time.** One AZ always stays fully untouched, so a bad patch can't take out your redundancy.
3. **Size waves by spare capacity, not by a fixed number.** The usual limit is 10–15% of an AZ in flight at once. With 20 hosts per AZ, that's 2–3 hosts.

## Suggested schedule

| Day | Work |
|---|---|
| **Mon** | Pre-flight checks. Canary: 2 hosts in AZ-A, one of them a busy host. Soak overnight. |
| **Tue** | AZ-A: the remaining 18 hosts in waves of 3. Pause between waves for health checks. |
| **Wed** | Soak day. Watch AZ-A for kernel or QEMU regressions (guest crashes, migration failures, network or storage oddities). Fix the runbook if it needs it. |
| **Thu** | AZ-B: 2 canary hosts, then waves of 3 for the remaining 18. |
| **Fri** | Buffer for stragglers and failed hosts, plus the final audit. Don't schedule new work. |

## Pre-flight (Mon)
- **Capacity:** confirm each AZ can lose a full wave and still run at less than about 80% utilisation. If it can't, shrink the waves.
- **Hard-to-move VMs:** find anything that can't live-migrate. That means pinned CPUs/NUMA, SR-IOV or GPU passthrough, local-disk instances without block migration, and very large or write-heavy VMs. Agree on a plan for each with its owner (cold migrate, scheduled downtime, or patch last).
- **Anti-affinity groups:** make sure the drain doesn't have to violate them, and check where the group members sit.
- **Test the drain on one host first.** Confirm that live migration works between your kernel/QEMU versions, old to new and back.
- **Backups and rollback:** the old kernel stays in GRUB as a fallback, the old QEMU package is cached locally, and a snapshot or backup of critical VMs exists.
- **Silence alerts** for the hosts being worked on, and tell tenants about the window.

## Per-host runbook
1. Disable the Nova service with a reason (`openstack compute service set --disable --disable-reason "patching" <host> nova-compute`).
2. Live-migrate everything off. Check that the host is empty and that nothing is stuck in migrating or error.
3. Patch the kernel and QEMU/libvirt, then reboot.
4. Verify:
   - the running kernel and QEMU versions match the target
   - nova-compute, libvirt and the network agent are up
   - storage, networking and the hypervisor show as healthy
5. Re-enable the host. Put a test VM on it, or let the scheduler fill it, and confirm a live-migration round trip works.
6. Only then start the next host in the wave.

## Gates between waves
Don't start the next wave unless all of these are true:
- every host in the last wave is back and enabled
- no VMs are in error
- there are no new alerts
- capacity is still above your threshold

If a host fails twice, set it aside, leave it disabled, and continue. Friday is for those hosts.

## Automation
Script the runbook above, for example with Ansible using `serial: 3` and `max_fail_percentage: 0`. Add a pause or manual approval between waves. Doing 40 hosts by hand invites mistakes.

## Questions that would change the plan
- Are there VMs that can't live-migrate, and how many?
- How full are the AZs right now?
- Are there change-freeze or tenant-notice requirements?
- Is the kernel patch urgent (an actively exploited CVE)? If so, compress the schedule, but still keep the canary and the one-AZ-at-a-time rule.

If you'd like, I can turn this into a shareable page or write the Ansible playbook.

## Turn 2

**User:**

More details: shared Ceph storage. Spare capacity is about 2 hosts per AZ. 6 VMs use SR-IOV ports, 2 VMs use PCI passthrough GPUs, and one tenant runs a 3-node database cluster spread across AZs with anti-affinity. Owners have agreed the GPU VMs can be restarted during a window.

**Assistant:**

# Revised plan

## What the new details change

- **Shared Ceph is good news.** Live migration only moves memory, and there is no block migration, so drains are fast. The Ceph cluster itself must stay healthy throughout. Check `ceph health` before every wave. Also keep migration concurrency modest so the migrations don't hurt client I/O.
- **Spare capacity of about 2 hosts per AZ means waves of 2, not 3.** A wave of 2 uses all your headroom. So you can't also tolerate an unexpected host failure mid-wave. Mitigations:
  - Go one host at a time in the first few waves, then pairs.
  - Check actual utilisation first. If an AZ is above about 85% after losing 2 hosts, go one host at a time for that AZ.
- **Two waves of 2 per day is realistic.** The cycle is about 1–1.5 hours per host including drain and verification.
- **SR-IOV VMs (6) don't live-migrate reliably.** Treat them the same way as the GPU VMs: they get a restart or cold-migrate window.
- **GPU VMs (2) are already agreed.** Cold-migrate or restart them in the window, onto a GPU host that has already been patched. Don't reboot a GPU host while the VM is still running on it.
- **The 3-node database cluster needs care.** Anti-affinity plus spread across AZs means one node per host in at least two AZs. The risk is losing quorum.
  - Never have two cluster members' hosts in flight at once. Because the AZs are patched on different days, this should hold by design, but verify where each node sits.
  - Before draining a host with a DB node, ask the tenant to confirm cluster health. Check that it's in sync.
  - Live-migrate that VM alone and check the cluster afterwards.
  - Preferably, get the tenant to confirm there are no heavy jobs in the window.
  - If there are two nodes in one AZ, patch that AZ's DB hosts at different times, with a cluster health check in between.

## Handling the non-migratable VMs
1. **List them now.** For each of the 8, record the host it's on, the owner, and whether it can tolerate a restart.
2. **Decide the method per VM:**
   - SR-IOV: either cold-migrate during the window, or stop the VM, patch its host, and start it again on the same host. The second option avoids needing a spare SR-IOV VF elsewhere.
   - GPU: cold-migrate to a patched GPU host. This needs a free GPU on the target, so check that you have one.
3. **Check targets.** Confirm that the destination has free VFs and matching physical networks for the SR-IOV VMs, and a free GPU for the GPU VMs. If the destination isn't ready, the cold migration will fail.
4. **Get the owners' windows confirmed and scheduled** before the week starts. Slot them into the AZ days, with the restart done immediately before the host's drain.

## Revised schedule

| Day | Work |
|---|---|
| **Mon** | Pre-flight. Test live migration across versions. Canary: 1 host in AZ-A, then 1 in AZ-B-free-of-DB-nodes... actually keep AZ-B untouched; use 2 canary hosts in AZ-A sequentially. |
| **Tue** | AZ-A: waves of 2 (one host at a time for the first wave), including SR-IOV/GPU hosts in AZ-A, restarts in the agreed window. About 10 hosts. |
| **Wed** | AZ-A: remaining hosts, ending with the DB-node hosts, one at a time. Soak overnight. |
| **Thu** | AZ-B: canary, then waves of 2. About 10 hosts. |
| **Fri** | AZ-B: remaining hosts. Final audit, plus stragglers. |

Because capacity limits you to 2 hosts per wave, a 20-host AZ takes about 10 cycles. That's roughly 1.5–2 working days per AZ. So the week is tighter than before, and the soak day in the middle is gone. Compensate with a gate: don't start AZ-B until AZ-A has been stable for at least 12–24 hours. If AZ-A slips, AZ-B spills into next week rather than overlapping. That is the right trade.

If the kernel fix is urgent and you can't allow that, get temporary capacity first (see below).

## Ways to add headroom
- Borrow or provision 2–4 extra compute hosts, even temporarily. This is the single biggest lever on both safety and speed.
- Ask tenants to stop dev/test VMs for the week.
- Check for overcommit headroom (CPU ratio) and where memory really is the limit.

## Additional gates
Between each wave, in addition to the earlier gates:
- `ceph health` is OK, with no recovery or backfill running
- the DB cluster is healthy and in sync
- no SR-IOV or GPU VMs are left in error or stopped unexpectedly

## Next steps
1. Pull the host and VM inventory for the 8 special VMs and the 3 DB nodes (which hosts and AZs).
2. Check current utilisation per AZ to decide wave size.
3. Confirm the target GPU host and free VFs.

If you give me that inventory (or a command to get it), I'll build the host-by-host schedule and the Ansible playbook with these gates in it.

## Turn 3

**User:**

We're on host 5 of 40. On cmp-a-05 the live migration of one VM failed half-way: the VM is now in ERROR and the migration shows 'error'. The other VMs on that host migrated fine. Can we carry on with cmp-a-06 to stay on schedule?

**Assistant:**

**No, pause before cmp-a-06.** The gate we set says no VMs in error before the next host, and this case is a good example of why.

## Why it matters
- **You don't yet know where the VM is running.** After a half-finished live migration, the QEMU process can be on the source (cmp-a-05), on the destination, or on both. Nova's ERROR state doesn't tell you which. Don't reboot or patch cmp-a-05 until you know.
- **Ceph makes a double-start dangerous.** If you "fix" the VM with a hard reset or rebuild while a copy is still running elsewhere, two QEMU processes can hit the same RBD image. That risks data corruption.
- **The cause is unknown.** It might be a one-off with a specific VM, such as heavy memory writes or a stuck migration. It might also be a problem with the new QEMU/kernel combination or the network between hosts. In that case cmp-a-06 will probably fail the same way, with more VMs involved.
- **Capacity is already reduced.** cmp-a-05 can't be re-enabled until it's resolved, so it's using up one of your two spare hosts. Starting 06 would take the other, leaving nothing.

## What to do now
1. **Find where the VM is running.**
   - Run `virsh list --all` on cmp-a-05 and on the destination host. Compare with `openstack server show` (look at `OS-EXT-SRV-ATTR:host` and the migration record).
   - Check whether the guest is actually responding (ping, console, or the tenant's monitoring).
2. **Read the logs for the cause.** Check nova-compute on both hosts and the libvirt/QEMU logs for the migration error (timeout, connection reset, or a QEMU abort).
3. **Recover safely, based on step 1.**
   - **Running on the source:** abort or clean up the migration, then reset the state with `openstack server set --state active <vm>`. Verify the guest is healthy.
   - **Running on the destination:** it may just need the DB state fixed to match reality.
   - **Running nowhere:** with the instance down and Ceph healthy, a hard reboot (`openstack server reboot --hard`) usually brings it back. If a stale process or lock is left, deal with that first.
   - Tell the VM's owner either way.
4. **Check Ceph.** Run `ceph health` and look for stale locks or watchers on that VM's RBD image (`rbd status`).
5. **Finish cmp-a-05.** Once the VM is sorted out, migrate or restart whatever remains, patch, reboot, verify, and re-enable. Test with a live-migration round trip.

## Before moving on to cmp-a-06
Continue only when all of these are true:
- the failed VM is ACTIVE and verified healthy, and you know why the migration failed
- cmp-a-05 is patched and re-enabled, or intentionally parked
- you've decided whether the cause is specific to that VM or could recur

If it could recur, test it first. Take one other busy VM, live-migrate it from an unpatched host to cmp-a-05 and back, and see whether it passes. If the cause is that VM's own workload, you can continue and treat it as a special case. Ask the owner whether it can be restarted in a window, as with the SR-IOV and GPU VMs.

## On the schedule
Losing half a day is much cheaper than a corrupted VM or a failure that repeats across several hosts. If you slip, AZ-B moves out, which is what the soak gate was for. If management needs the kernel patched by Friday, the better lever is extra temporary hosts rather than skipping the check.

If you paste the migration error from the nova-compute log and the `virsh list` output from both hosts, I can help work out where the VM is and what the safe recovery step is.
