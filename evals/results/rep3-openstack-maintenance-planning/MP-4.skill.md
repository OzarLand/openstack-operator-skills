## Turn 1

**User:**

I need to patch 40 compute hosts (kernel + QEMU) this week, 2 availability zones. How should I plan it?

**Assistant:**

# Patch plan: 40 compute hosts (kernel + QEMU), 2 AZs

I don't have your environment data, so everything below uses placeholders. I don't know your release, storage model, instance mix or spare capacity. Section 5 lists what I need from you.

## 1. Requirement and constraints

- **Fixed:** kernel and QEMU patched on all 40 hosts this week.
- **Flexible:** how you get there, which is set by capacity and workload criticality.
- **Reported, not observed:** 40 hosts across 2 AZs. I'm assuming roughly 20 per AZ, which you should confirm.
- **If the deadline can't be met safely,** write down the exposure and let the accountable owner decide. Don't compress the safety steps to hit the date.

## 2. Two points that shape the whole plan

- **QEMU changes the order of work.** Live migration from newer QEMU to older isn't supported. Once a host is patched, instances can move onto it but not back. So patch an **empty landing-zone batch** first, then migrate toward patched hosts only. The kernel alone wouldn't impose this constraint.
- **A patched host doesn't protect running guests.** An instance is only patched against the new QEMU once it has been migrated or restarted since the patch. Track this per instance. Done means "every instance moved or restarted since the patch", not "every host patched".

## 3. Workload classes

Nova can't tell which workloads tolerate a restart, so the consuming teams have to. **Collecting a criticality table from them is the first deliverable.** For each workload I need:

- business criticality
- acceptable downtime
- recovery expectations
- deadlines and blackout periods
- an owner
- technical constraints

An empty cell is a gap, not "low".

| Class | Strategy | Needs sign-off |
|---|---|---|
| Critical and migratable | Live migration, within capacity | Owner informed |
| Tolerates restart | Cold migration, or restart in place in an agreed window | Owner, in writing |
| SR-IOV `direct` port | Live migration is possible since Train, but the guest loses that NIC briefly. Verify NIC and driver support for your release. | Owner must accept the interruption |
| Flavor-based PCI passthrough, `direct-physical`, or memory-heavy guests that dirty pages faster than they copy | Cold migration or restart. This is a technical necessity. Auto-converge or post-copy may help the memory-heavy ones. | Owner and agreed downtime |
| vGPU or pinned/NUMA | Check libvirt, QEMU and kernel versions and the Nova release. vGPU live migration needs 2024.1 or later with recent libvirt, QEMU and kernel. | Owner |
| Can't be touched before the deadline | Exception with compensating control and review date | Accountable owner |

## 4. Capacity check

Capacity is per AZ. One spare host overall doesn't cover it. Each AZ needs its own spare.

For each AZ:

- Required spare ≈ (hosts drained at once) × (average used capacity per host: vCPU, RAM, and disk if local).
- Check this against what the remaining hosts in that AZ can absorb while staying under your own reserve threshold.
- Don't forget what the landing-zone batch costs. Those hosts are empty, so they're spare capacity you've already counted on.

If spare capacity can't absorb live-migrating everything, the answer is a differentiated strategy and an explicit decision. Don't force migrations the platform can't take.

**Rough shape, if the capacity is there (to be validated):** one AZ at a time, with batch size set by the capacity math. A common starting point is 1–2 hosts per AZ at once, but treat that as a hypothesis until the numbers back it.

## 5. Sequencing

1. **Pre-work (days 0–1, read-only):**
   - Inventory libvirt/QEMU versions and CPU models per host.
   - Inventory instances per host.
   - Find which instances have PCI, SR-IOV, vGPU or pinned resources.
   - Check whether instance storage is shared or local. Local disks mean block migration, which loads the network and storage.
   - Collect the criticality table and agree the schedule with consumers.
2. **Landing-zone batch:** pick the emptiest hosts in AZ-A. Drain them, patch, reboot, verify. Optionally validate with a test instance.
3. **Rolling batches in AZ-A,** migrating toward patched hosts only.
4. **Repeat in AZ-B.** Pause between AZs to confirm there are no regressions. Don't patch both AZs concurrently. Keep one AZ untouched while the other is in flight.
5. **Don't stack other changes** into the same window.
6. **Check CPU model compatibility** between source and destination in the migration plan.

## 6. Per-host procedure

Every step below except step 3 and step 9 is state-changing and needs approval under your change process.

1. **(read-only)** List the host's instances and confirm each is classified and its owner informed:
   `openstack server list --all-projects --host <host> --long`
2. **(state-changing)** Disable the host so nothing new lands on it:
   `openstack compute service set --disable --disable-reason "<reason>" <host> nova-compute`
3. **(read-only)** Check `resume_guests_state_on_host_boot` on the host. If it's absent or `False`, guests that stay behind will come back `SHUTOFF` after the reboot.
4. **(state-changing)** Move instances according to their class.
   - Live: `openstack server migrate --live-migration [--host <dest>] [--block-migration] <server>`
   - Cold: `openstack server migrate <server>`, then confirm the resize once verified.
   - **Verify after each move:** the instance is ACTIVE on the destination, reachable, and performing acceptably.
5. **(read-only)** Confirm the host is empty, or that only agreed-restart instances remain.
6. **(state-changing)** Patch and reboot.
7. **(read-only)** Verify host health, kernel and QEMU versions, and that nova-compute and the network agents are up.
8. **(state-changing)** Start the agreed-restart instances that should be running (`openstack server start <server>`), and have owners confirm their applications are reachable.
9. **(state-changing)** Re-enable the host:
   `openstack compute service set --enable <host> nova-compute`

**Never use `evacuate` for maintenance.** It's only for failed, fenced hosts. Using it on a host that may still be running its instances risks duplicate guests and storage corruption.

## 7. Boundaries and stop conditions

Set these before you start, from your own baselines:

- Maximum hosts drained at once per AZ.
- Maximum concurrent migrations.

**Stop if:**

- Migrations fail or slow beyond baseline.
- A destination behaves unexpectedly.
- Critical workload performance crosses the agreed threshold.
- Spare capacity in an AZ drops below the reserve.
- There's a monitoring blind spot.
- The person with decision authority is unreachable.

Resuming after a stop is a new decision.

## 8. Decision rights

- **Workload owners** approve restarts and downtime for their workloads.
- **The accountable owner** (name them) accepts any exceptions and any deadline slip.
- **One named person** communicates the schedule to consumers.
- **You** approve each batch before it starts.

## 9. Done means

- All 40 hosts are patched and verified.
- Every instance has been migrated or restarted since the patch, or is listed as an exception with an owner and review date.
- Every agreed-restart instance is running again, or intentionally left off by its owner.
- Compute services and agents are healthy in both AZs.

## 10. What I need from you to turn this into a concrete schedule

1. Hosts per AZ, and current used versus spare vCPU and RAM per AZ.
2. OpenStack release, plus libvirt and QEMU versions now and target.
3. Instance storage: shared (e.g. Ceph) or local.
4. Whether any instances use PCI passthrough, SR-IOV, vGPU, pinned CPUs or very large memory.
5. Whether a criticality table exists, and who owns the consuming projects.
6. The hard deadline, and who is accountable for accepting an exception.
7. Your tested migration concurrency baseline.

Once you send those, I can turn this into a day-by-day batch schedule and a filled-in criticality table.

> Decision support only. State-changing steps above require approval by the accountable owner and should be executed under your change process.

## Turn 2

**User:**

More details: shared Ceph storage. Spare capacity is about 2 hosts per AZ. 6 VMs use SR-IOV ports, 2 VMs use PCI passthrough GPUs, and one tenant runs a 3-node database cluster spread across AZs with anti-affinity. Owners have agreed the GPU VMs can be restarted during a window.

**Assistant:**

# Refined plan: 40 hosts, shared Ceph, about 2 spare hosts per AZ

Your new details settle the main strategy questions. Most of the fleet can be live-migrated on shared Ceph, and the GPU VMs are settled by owner agreement. The SR-IOV VMs and the database cluster carry the real risk.

## Assumptions I'm still making

- Hosts are split about 20 per AZ.
- "About 2 hosts spare per AZ" means free capacity equal to roughly two hosts' average load. I don't yet know whether that is whole empty hosts or capacity scattered across many hosts. See gaps below.

## 1. Capacity: batch size is 1 host per AZ

- Draining one host uses about one host's worth of spare and leaves about one. That is workable.
- Draining two hosts at once in an AZ leaves zero spare. I wouldn't do it, since any failure or migration stall then has no room to recover.
- When a patched host comes back empty, it restores the spare. The campaign is roughly capacity-neutral if you go one host at a time.
- This is a capacity result, not a throughput one. Whether 40 sequential host cycles fit in the week depends on your time per host, which the pilot will measure (see section 3).

## 2. Workload classes, now concrete

| Workload | Strategy | Notes and conditions |
|---|---|---|
| Most VMs (shared Ceph) | Live migration, no block migration | Make Ceph health OK a precondition. Migrations add network and Ceph load. |
| 6 SR-IOV VMs | Live migration is possible since Train. The guest loses the SR-IOV NIC briefly while the port is unplugged and replugged. | **Sign-off needed:** for each VM, ask the owner whether that interruption is acceptable. Does the guest have a bond or failover NIC? Does the destination have free VFs on the same physical network? Only SR-IOV-capable hosts can receive them, so check spare capacity for these hosts specifically. Cold migration is the fallback if the owner says no. |
| 2 GPU passthrough VMs | Cold migrate or restart in a window (owners agreed) | Not live-migratable. If another GPU host has a free device, cold migrate to an already-patched one. Otherwise have the owner shut the VM down cleanly, patch and reboot the host, then start it. That start uses the new QEMU. Check `resume_guests_state_on_host_boot`. If it's `False`, the VM stays `SHUTOFF` until someone starts it. |
| 3-node DB cluster, anti-affinity, across AZs | One node at a time, owner-led | See section 4. |

## 3. Sequencing

1. **Pre-work (read-only).**
   - Map every SR-IOV, GPU and DB VM to its host and AZ.
   - Confirm Ceph is healthy.
   - Confirm your libvirt/QEMU versions and CPU models.
2. **Landing zone.** Patch the spare capacity first. If it is whole empty hosts, patch them with no migration needed, since QEMU can't migrate back to older. If the spare is scattered, drain one host first.
3. **Pilot on one ordinary host** in AZ-A. Measure the total time per host: drain, patch, reboot, verify. This gives your real throughput.
4. **Rolling, one host at a time per AZ,** always migrating toward already-patched hosts.
5. **Special hosts get their own slots,** scheduled individually and not mixed into bulk batches:
   - hosts with SR-IOV VMs
   - the GPU host(s), in the agreed window
   - the three DB hosts
6. **AZ ordering:**
   - Patching AZ-A first and AZ-B afterward is the safest, since one AZ stays untouched.
   - Hosts per day is roughly working hours divided by your measured time per host. If that doesn't fit the week, your options are:
     - run both AZs concurrently, one host each, with a hard rule that DB hosts are never in flight at the same time (see section 4);
     - ask the accountable owner to accept a short deadline slip for the tail.
   - Don't solve a throughput problem by draining two hosts in one AZ.

## 4. The DB cluster is the highest-risk item

With 3 nodes across 2 AZs, one AZ holds two nodes. Losing two nodes means losing quorum.

- **Never have two DB node hosts in flight at once,** in the same AZ or across AZs. Each node gets its own slot.
- Between slots, wait for the owner to confirm the cluster is fully synced and healthy. Don't rely on the VM being ACTIVE.
- **Ask the DB owner which method they prefer** for each node. A live migration briefly stalls the guest. Some clusters tolerate that and some mis-detect a failure. The alternatives are a controlled failover and restart, or a cold migration at a time they pick. That decision is theirs.
- **Anti-affinity can reject the move.** The migration may fail if the only valid destinations hold another group member. Check the destination in advance. Nova's late-check behaviour on live migration varies by release, so verify for yours.
- Have the owner on call, and name who stops the DB slot if the cluster degrades.

## 5. Added stop conditions

Beyond the earlier list, stop if:

- Ceph health leaves OK.
- The DB cluster is not fully healthy before the next DB slot starts.
- An SR-IOV guest doesn't recover its NIC after migration.
- Spare capacity in an AZ falls below one host-equivalent.

## 6. Sign-offs to collect before starting

- Each SR-IOV VM owner: is the brief NIC loss acceptable, or do you want a cold migration?
- The GPU owners: the specific window, and who starts the VMs afterward.
- The DB owner: the method per node, the slot times, and who confirms cluster health.
- The accountable owner: any deadline slip.

## Remaining gaps

1. Is the spare whole empty hosts, or scattered? This determines whether you have a ready landing zone.
2. Hosts per AZ, and your migration baseline (concurrent migrations and time per host).
3. Are there SR-IOV-capable and GPU-capable hosts besides the ones currently in use, with free VFs or devices?
4. Which hosts and AZs hold the 6 SR-IOV VMs, the 2 GPU VMs and the 3 DB nodes?
5. OpenStack release, libvirt and QEMU versions now and target.
6. The deadline and any blackout periods.

If you send the host and VM mapping from items 2 and 4, I'll draft a day-by-day schedule with the special slots placed.

> Decision support only. State-changing steps above require approval by the accountable owner and should be executed under your change process.

## Turn 3

**User:**

We're on host 5 of 40. On cmp-a-05 the live migration of one VM failed half-way: the VM is now in ERROR and the migration shows 'error'. The other VMs on that host migrated fine. Can we carry on with cmp-a-06 to stay on schedule?

**Assistant:**

# Short answer: no, hold at cmp-a-05

Don't start cmp-a-06 yet. Treat this as a stop condition from the plan. Migrations failing is exactly the kind of event we agreed would pause the campaign, and **resuming is a new decision**. You also have a capacity reason and a safety reason, both below.

## Situation

- **Capability affected:** live migration during the patching campaign.
- **What still works:** the other VMs on cmp-a-05 migrated fine. I have no evidence of a control-plane problem.
- **Business impact:** unknown. I don't know which VM this is or who owns it.
- **What changed:** the campaign itself. This is host 5 of 40.

## Evidence

| # | Class | Statement | Source |
|---|---|---|---|
| 1 | Reported | One live migration on cmp-a-05 failed partway. | You, just now |
| 2 | Reported | The VM is in ERROR and the migration record shows `error`. | You |
| 3 | Reported | The other VMs on cmp-a-05 migrated fine. | You |
| 4 | **Unknown** | Where the VM is actually running (source, destination, both or neither). | Not shown |
| 5 | **Unknown** | Which VM it is, whether it is SR-IOV, GPU or a DB node, and the failure message. | Not shown |

The status ERROR is a database record. It does not tell you where the guest is running. I have no evidence of what happened to the guest.

## Why not just move on to cmp-a-06

1. **You don't yet know where the VM is.** Don't reboot or patch cmp-a-05 until you do. If the guest is still running on cmp-a-05, patching it kills the VM. If it's running on the destination, resetting its state to match Nova could create a second copy.
2. **The capacity rule breaks.** cmp-a-05 isn't empty, so it hasn't returned any spare capacity. Draining cmp-a-06 would put two hosts in AZ-A out at once, which leaves about zero spare. That is the batch-of-two we ruled out.
3. **You don't know if the cause is systemic.** If it is, cmp-a-06 will fail the same way, and you'll have created a second problem to unpick.

## Hypotheses

| Hypothesis | Supports | Would disprove | Discriminating check (read-only) |
|---|---|---|---|
| H1: VM-specific, e.g. memory changing faster than it copies, or a timeout | The other VMs were fine. | Other large or busy VMs also fail, or the log shows a different error. | Source nova-compute and libvirt/QEMU log for this VM. Look for a timeout or abort message. |
| H2: Destination problem | Failure was partway through. | The same destination accepted other VMs fine. | Which host was the destination? What do its nova-compute and libvirt logs say? |
| H3: Port or network binding, e.g. SR-IOV VF or Neutron | Only relevant if this VM has such a port. | The VM has only ordinary ports. | `openstack port show` for its ports: binding host and status. |
| H4: Shared infrastructure blip (Ceph or RabbitMQ) | A failure partway through a migration. | Ceph and the bus are healthy, and no other VMs are in transitional states. | Ceph health. RabbitMQ status. Count of instances in transitional or ERROR states. |
| H5: Version direction | The campaign is mixing patched and unpatched QEMU. | Source and destination versions are compatible. | QEMU/libvirt version on source and destination. Newer to older is unsupported. |

## Next diagnostics (all read-only)

1. `openstack server show <vm>`: status, task state, power state, host, hypervisor, fault.
2. `openstack server migration list --server <vm>` and the `migration show` output: source, destination, status.
3. On the source and the destination: `virsh domstate` or `virsh list --all`, looking for the domain on **either, both or neither**.
4. Ceph: `rbd status <pool>/<image>` for the VM's disk. It shows which host holds it open (the watchers). Two watchers would be a red flag.
5. `openstack resource provider allocation show <vm-uuid>`: are allocations on one host or two?
6. Logs from both hosts around the failure, using the request ID. Save them before rotation.
7. `ceph -s` (Ceph health) and the RabbitMQ status.

Please paste the output. I haven't inspected anything.

## Protect decision

- **Is the platform state getting worse?** Nothing you've shown suggests it is, but check it. Compare the count of instances in ERROR or transitional states now and a few minutes from now.
- **Recommended action:** pause the campaign. This is containment by stopping, not controlled degradation of the APIs, which isn't needed on this evidence.
- **Keep cmp-a-05 disabled.** Don't re-enable it, don't patch it, and don't reboot it until the VM is located.
- **Who decides to resume?** The person who accepts the consequences, so name them. I'd expect the change owner or the accountable owner you named for the campaign.

## Corrective options (not yet authorized)

Which one applies depends on the diagnostics. All are state-changing and need approval from the VM's owner and the change owner.

| If the VM is... | Option | Cautions |
|---|---|---|
| Running only on the source, healthy | Reset its state to active (`openstack server set --state active <vm>`). Then either fix the cause and retry, or cold migrate by agreement with the owner. | This only changes the DB record. Confirm first that exactly one copy exists. |
| Running only on the destination | Reconcile the Nova record with reality. This can need database-level work. | Escalate. Take a backup first. Don't reset state blindly. |
| Not running anywhere | Start it with a hard reboot, once you've verified the disk isn't held by another host. | Owner approval. Check the RBD watchers first. |
| Running on both | Stop. Fence one copy. | Risk of Ceph disk corruption. Escalate immediately. |

**Never use `evacuate` here.** The host hasn't failed.

## Verification before resuming

- Nova status and power state match reality, and `virsh` shows exactly one copy.
- Only one RBD watcher.
- Allocations are on a single provider, and the migration record is resolved.
- The VM's owner confirms the application works.
- The cause is identified, either fixed or shown to be specific to this VM.
- Ceph and RabbitMQ are healthy.
- cmp-a-05 is empty or accounted for, so AZ-A has its spare back.
- A named owner has made the explicit decision to resume.

## Two questions that change the answer

1. **Which VM is it?** If it's a DB cluster node, tell the DB owner now and freeze the DB slots. If it's one of the SR-IOV or GPU VMs, tell its owner.
2. **How was the destination chosen?** If you ran `server migrate --live-migration` without `--host`, the scheduler may have picked an unpatched host. That would leave the VM unpatched and still needing another move. Pin destinations to patched hosts for the rest of the campaign.

## Schedule

A few hours' pause on one host isn't a disaster. It's cheaper than a second broken host. If the deadline is at risk, tell the accountable owner and agree a short extension for the tail, not a compressed safety margin.

Starting AZ-B early would be a separate decision, and it only makes sense if H2 and H4 are ruled out. It doesn't fix cmp-a-05.

> Decision support only. State-changing steps above require approval by the accountable owner and should be executed under your change process.
