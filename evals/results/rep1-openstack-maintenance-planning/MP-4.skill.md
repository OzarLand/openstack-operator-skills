## Turn 1

**User:**

I need to patch 40 compute hosts (kernel + QEMU) this week, 2 availability zones. How should I plan it?

**Assistant:**

## Requirement and constraints

- **Mandatory (reported):** kernel and QEMU patch on 40 compute hosts, this week. I don't know the driver (CVE, compliance date, internal policy). Please say who owns the deadline and what the exposure is if it slips. The deadline stays fixed. Only the execution strategy flexes.
- **QEMU matters most here.** A patched QEMU protects only instances that are live-migrated or restarted after the patch. Instances still running on the old binary stay vulnerable even on a patched host. Track this per instance, not per host.

## Scope

| Item | Status |
|---|---|
| Hosts | 40 (reported) |
| Failure domains | 2 AZs (reported). Host split per AZ unknown. I'll assume 20/20 only for the formulas below. |
| Gaps | Rack and power domains, aggregates, current and target libvirt/QEMU versions, CPU models per host, shared vs local instance storage, OpenStack release, instance count per host, spare capacity |

## Workload classes

Nova can't tell you which workloads tolerate a restart, so the consuming teams have to. If a criticality table doesn't exist, **building it on day 1 is the first deliverable.** It needs criticality, acceptable downtime, restart tolerance and an owner for each project or instance group.

| Class | Strategy | Owner sign-off |
|---|---|---|
| Critical and migratable | Live migration, within capacity | Window and stop conditions |
| Tolerates restart | Cold migration or coordinated restart in a window | Yes, per workload |
| SR-IOV `direct` port | Live migration only if the owner accepts a brief loss of that interface (Train or later, verify NIC and driver). Otherwise cold migrate. | Yes |
| PCI passthrough, `direct-physical`, or high-dirty-rate memory | Not live-migratable (unless auto-converge or post-copy). Cold migrate or restart. | Yes, downtime agreed |
| vGPU, pinned/NUMA | Check your release. vGPU needs 2024.1 or later with libvirt ≥ 8.6, QEMU ≥ 8.1 and kernel ≥ 5.18 on both ends. | Yes |
| Can't be touched before the deadline | Exception: owner, compensating controls, review date | Accountable owner |

## Capacity check

Capacity is per AZ, not overall. For each AZ:

- Spare capacity ≥ (hosts down at once) × (host capacity in vCPU, RAM and disk), plus your reserve.
- Example only: if each AZ can lose one host at a time, each AZ needs one host of free capacity. With 20 hosts per AZ and one at a time, that's 20 sequential cycles per AZ. The AZs can run in parallel, but don't drain both at once at the start.
- Duration per host is roughly migration time plus patch, reboot and verification. Take migration time from your own baselines, since I won't guess it.

If the numbers don't allow live-migrating everything, the answer is the differentiated strategy above plus an explicit decision. Don't force migrations the platform can't absorb.

## Sequencing

1. **Landing zone first (QEMU).** Migrating from newer QEMU to older isn't supported. Patch one or a few empty or lightly loaded hosts first, and move instances only toward patched hosts. Pick the landing-zone host(s) with CPU models compatible with the rest. The kernel alone doesn't impose this constraint, but the QEMU update does.
2. **Pilot:** patch one host in AZ-A fully, with a test instance, and check results before scaling.
3. **Rolling batches.** The size of a batch comes from the capacity check. Alternate AZs or finish one AZ before the other, and never exceed a domain's spare capacity.
4. **Rack and power domains:** don't drain hosts that share them at once, if those are relevant.
5. **Don't stack other changes** into the same window.
6. **Rough schedule** (adjust to measured cycle time): Day 1 criticality table, baselines, landing zone and pilot. Days 2–4 rolling batches. Day 5 stragglers, exceptions and verification. Keep a buffer, because things will slip.

## Per-host procedure

1. **Read-only:** list instances (`openstack server list --all-projects --host <host>`) and confirm each is classified and its owner informed.
2. **State-changing:** `openstack compute service set --disable --disable-reason "<reason>" <host> nova-compute`.
3. **State-changing:** move instances by class (`openstack server migrate --live-migration ...` or cold migrate). Verify each one: active on the destination, reachable, performance acceptable.
4. **Read-only:** confirm the host is empty, or that only agreed-restart instances remain. If any remain, record their power state. Check `resume_guests_state_on_host_boot`. The default is `False`, so those guests come back SHUTOFF.
5. **State-changing:** patch and reboot. Verify the kernel and QEMU versions, and that the compute service and network agents are up.
6. **State-changing:** start the agreed-restart instances (`openstack server start`). Have the owner confirm the app is reachable.
7. Optionally boot a test instance on the host.
8. **State-changing:** re-enable the host.

**Do not use `evacuate` to drain hosts for maintenance.** It is for failed, fenced hosts only. Stopping nova-compute and evacuating a running host risks duplicate instances and disk corruption.

## Boundaries and stop conditions

Set these before starting, from your own baselines:
- Max hosts down per AZ.
- Max concurrent migrations.
- **Stop if:** migrations fail or slow beyond baseline, a destination behaves unexpectedly, a critical workload crosses its performance threshold, spare capacity falls below reserve, monitoring is blind, or the decision-maker is unreachable.
- Resuming after a stop is a new decision.

## Decision rights and communication

- Workload owners approve restarts and downtime.
- A named accountable owner approves deadline exceptions.
- Someone named communicates the schedule to consumers before day 1.

## Campaign completion criteria

- All 40 hosts patched and verified.
- Every instance either migrated or restarted since the patch, or on the exception list.
- Every agreed-restart instance running again, or intentionally left off by its owner.
- No instance left on the old QEMU unnoticed. Verify per instance, not per host.

## Exceptions

| Workload | Reason | Compensating control | Owner | Review date |
|---|---|---|---|---|
| (to fill) | | | | |

## Gaps and questions

1. What is the deadline, and what drives it?
2. How many hosts are in each AZ, and how much free capacity does each have?
3. Is instance storage shared (Ceph, for example) or local? Local storage means block migration, which adds network and storage load.
4. Which release, libvirt, QEMU and CPU models are in use?
5. Are there GPU, SR-IOV, passthrough or very large-memory instances?
6. Does a criticality table exist, and who owns it?
7. Is this run by hand or by automation? If automation, I can review it with the automation-review skill.

## Follow-up

- Keep the criticality table current and feed it into capacity planning.
- Add maintenance scenarios to capacity planning.
- If every campaign eats this much capacity or time, treat it as a lifecycle issue on the platform roadmap.

Send me the answers to the gaps, especially the per-AZ capacity and the storage model, and I'll turn this into a concrete day-by-day schedule with batch sizes.

> Decision support only. State-changing steps above require approval by the accountable owner and should be executed under your change process.

## Turn 2

**User:**

More details: shared Ceph storage. Spare capacity is about 2 hosts per AZ. 6 VMs use SR-IOV ports, 2 VMs use PCI passthrough GPUs, and one tenant runs a 3-node database cluster spread across AZs with anti-affinity. Owners have agreed the GPU VMs can be restarted during a window.

**Assistant:**

Those details change the plan in three places: the concurrency limit, the DB cluster, and the special-device VMs. Where I had to assume something, I've marked it.

## Capacity and concurrency

- **Shared Ceph:** no block migration, so migrations are lighter on network and storage. Live migration is the default for everything migratable.
- **About 2 hosts of spare per AZ (reported):** take **one host out at a time per AZ**. That uses one host of spare as working room and keeps about one in reserve for an unplanned host failure mid-campaign. Taking two at a time leaves no reserve, so I'd only do that if the accountable owner explicitly accepts the risk.
- **Check "about 2" before relying on it:**
  - Is it host-equivalents across vCPU and RAM, and not fragmented?
  - Can the free capacity actually hold the VMs you'll move?
  - Do the GPU hosts and the SR-IOV VF pools have their own spare? Overall spare doesn't prove that.
- **Duration:** this assumes 20 hosts per AZ, which you haven't confirmed. Two streams (one per AZ) of 20 sequential cycles each. If the patching days are 4 (day 1 is prep and pilot) at about 8 working hours, you need a cycle time of roughly **1.5 hours or less per host** to finish. I don't know your migration times, so the pilot measures it. If the pilot shows longer cycles, your options are:
  1. Extend the working hours.
  2. Run two hosts at a time per AZ with explicit risk acceptance.
  3. Ask the deadline owner for more time, or raise an exception for the tail.

## Sequencing: leapfrog on patched hosts

1. In each AZ, drain one host onto unpatched hosts (old to old is fine) and patch it. It becomes the **empty landing zone**.
2. Drain the next host **only onto patched hosts**, patch it, and repeat. The empty patched host moves along as you go.
3. **Pick destinations explicitly** with `--host`, or restrict them with an aggregate. If you let the scheduler choose, it may land instances on unpatched hosts and you'd migrate them twice.
4. Keep instances inside their AZ.
5. New VMs created during the week may land on unpatched hosts, but they get moved when that host is drained.

## Special workloads

### Database cluster (3 nodes, anti-affinity, across AZs)

- **Risk:** with 3 nodes over 2 AZs, two nodes sit in one AZ. If your two streams run in parallel and hit two DB hosts at once, you could lose quorum.
- **Rule:** only one DB node is in motion at a time across **both** streams. Check cluster health (quorum, replication in sync) before and after each one. Never start the next until the last is verified.
- **Method:**
  - Live-migrate the DB node. It stays up, but the final switchover pauses the guest briefly, so ask the tenant about heartbeat and timeout settings.
  - The destination must be patched, in the same AZ, and must not host another cluster member (anti-affinity).
  - A cold migration or restart is a fallback only, and the tenant decides.
- **Ask the tenant:** which DB engine it is, which node is primary, and whether they want to be present or on call for their three slots.
- **Gap:** I don't know the AZ split of the three nodes or which hosts they run on. Please pull that list.

### SR-IOV (6 VMs): decision needed, not yet agreed

- **First check:** are the ports `direct` or `direct-physical`? `direct-physical` can't be live-migrated, so cold migrate or restart. `direct` can, from Train on, if the NIC and driver support it.
- **For `direct` ports:** the interface is unplugged and re-plugged during migration, so the guest loses that interface briefly (the instance keeps running). Each owner has to say yes or no to that. If no, use a cold-migration window.
- **Also check:** the destination needs free VFs on the same physical network. Make sure the landing-zone hosts have them. Bonding or failover inside the guest can hide the interruption. Ask the owners.
- **Suggestion:** do these after the pilot, one at a time, with the owner watching.

### GPU passthrough (2 VMs): restart agreed

- They can't be live-migrated, so it's a window. Agreed means the owners have signed off, but the time, duration and contact still need setting.
- **Option A, cold-migrate to an already-patched host with the same GPU free.** This needs a spare GPU of the same alias on a patched host. Check that one exists.
- **Option B, restart in place.** Stop the VMs, patch and reboot the host, then start them (`resume_guests_state_on_host_boot` defaults to `False`, so they won't start automatically). Check the power state afterward.
- If both GPU VMs are on the same host, do them together in one window.
- **Gap:** which hosts carry the GPUs, and whether any other GPU host exists.

## Proposed schedule

This is provisional, and the pilot's measured cycle time decides the rest.

| Day | AZ-A stream | AZ-B stream |
|---|---|---|
| 1 | Criticality table, baselines, SR-IOV/GPU/DB lists, owner sign-offs. Drain and patch the landing-zone host, then pilot it with a test instance. | Same: landing-zone host. |
| 2–4 | Leapfrog, one host at a time. Special workloads in agreed slots, with DB nodes serialized across both streams. | Same, offset so DB moves never overlap. |
| 5 | Stragglers, exceptions, per-instance QEMU verification, hand-off. | Same. |

## Stop conditions to set

On top of the earlier list:
- DB cluster loses quorum or replication lags.
- A migration fails for any SR-IOV or DB VM.
- Spare capacity in an AZ drops below one host.
- The GPU or SR-IOV pool on the destination is exhausted.
- An unplanned host failure in either AZ. Pause the campaign, because that's an incident.

## Decisions needed and owners

| Decision | Owner |
|---|---|
| SR-IOV: brief interface loss vs cold migration (per VM) | Each VM's owner |
| DB cluster: move method, time slots, who is on call | DB tenant |
| GPU: restart window time | GPU owners, already agreed in principle |
| Two hosts at a time per AZ, if cycle time forces it | Accountable platform owner |
| Exceptions for anything not done by the deadline | Accountable owner |

## Questions that would let me firm this up

1. Real host count per AZ, and the DB nodes' AZ split and host names.
2. Port type for the 6 SR-IOV VMs (`direct` or `direct-physical`), NIC model, and your OpenStack release.
3. GPU host(s), and whether a second patched GPU host exists.
4. What "about 2" spare means in vCPU and RAM, and whether any hosts are fully empty now.
5. The deadline and what it's tied to.
6. A migration time baseline. Do you have one from past campaigns?

> Decision support only. State-changing steps above require approval by the accountable owner and should be executed under your change process.

## Turn 3

**User:**

We're on host 5 of 40. On cmp-a-05 the live migration of one VM failed half-way: the VM is now in ERROR and the migration shows 'error'. The other VMs on that host migrated fine. Can we carry on with cmp-a-06 to stay on schedule?

**Assistant:**

No, not yet. Hold cmp-a-06 until the failed VM is understood. A failed migration is one of the stop conditions we set before starting, and resuming after a stop is a new decision, not a default. The schedule pressure is real, but the risk is bigger than "one VM to fix".

## Situation

- **Capability affected:** live migration, which the whole campaign depends on. Also at risk: one VM in ERROR, with unknown actual state.
- **Still works (reported):** the other VMs on cmp-a-05 migrated fine.
- **Business impact:** unknown. I don't know which VM it is, who owns it, or how critical it is. Is it one of the special workloads (DB node, SR-IOV or GPU VM)?
- **What changed:** the campaign itself (cmp-a-05 drain). Nothing else is known.

## Evidence

| # | Class | Statement | Source |
|---|---|---|---|
| 1 | Reported | One migration on cmp-a-05 failed partway | You |
| 2 | Reported | The VM is in ERROR and the migration record says `error` | You |
| 3 | Reported | Other VMs on the host migrated fine | You |
| 4 | Assumption | Shared Ceph storage, from your earlier answer | You |
| 5 | Gap | Where the guest is actually running, the error message, source and destination hosts | not shown |

## Why not carry on

- **The failure is unexplained.** If the cause is something shared (the destination, the network, QEMU version mismatch between source and destination, Ceph, or an auth/RPC issue), cmp-a-06 will probably fail the same way. If the cause is specific to this VM, you need to know that before the DB node, SR-IOV or GPU VMs come up.
- **ERROR doesn't mean the guest is down.** After a half-finished live migration, the guest may be running on the source, running on the destination, or (rarely) in a bad state on both. Anything that restarts or rebuilds it before you know could cause a duplicate-writer problem on shared Ceph.
- **It uses up the pilot's value.** The pilot was meant to establish a baseline. A failure on host 5 is exactly what the stop condition is for.

## Hypotheses

| Hypothesis | Would disprove | Check |
|---|---|---|
| Guest-specific (large memory, high dirty rate, device attached) | Error mentions connection/destination, not the guest | Instance flavor, memory activity, `migration` timeout/auto-converge messages in the compute log |
| Destination-specific (patched landing-zone host: QEMU/libvirt/CPU incompatibility, no capacity, SR-IOV/VF, port binding) | Same VM fails to any destination, or other VMs reached that destination OK | Destination `nova-compute` and libvirt logs, did other VMs land there? |
| Source-side or network (libvirt connection, TLS, firewall, migration bandwidth/timeout) | Failure is repeatable only on one VM | Source logs at the failure time, migration port/network checks |
| Ceph / storage (lock, RBD) | Ceph healthy and no lock errors | `ceph health`, RBD status for that image |
| Control plane (RPC/messaging timeout) | Other operations in the same window fine | Nova-compute and conductor logs for messaging timeouts |

## Next diagnostics (all read-only)

1. Instance details: `openstack server show <vm>` (look at status, power state, host, `fault`).
2. Migration record: `openstack server migration list --server <vm>` and the migration show output.
3. Actual location: on the source and destination hosts, `virsh list --all` (is the domain running on either, both, or neither?).
4. Logs: nova-compute and libvirt/QEMU logs on both hosts around the failure time; share the request ID (`req-...`).
5. Ceph: `ceph -s` and, for the VM's root disk, whether the image is locked by a watcher.
6. Which VM is it, and who owns it? Check the criticality table.

Please redact credentials from anything you paste.

## Protect decision

- **Is the state getting worse?** I have no evidence either way. The checks above will tell you, and the key one is where the guest is running.
- **Do not take these actions yet:** `openstack server reset-state`, `server start`, `server reboot --hard`, `rebuild`, or `evacuate`. Any of them on a VM whose real location is unclear can create two copies writing to the same Ceph disk. Evacuate is never for maintenance anyway.
- **Containment is a decision:** pause the campaign (hold cmp-a-06 and the AZ-B stream) until the cause is known. Tell the campaign owner and the deadline owner that you are stopped and why. That is the protect decision, and it's yours and theirs to make, not mine.
- **Keep cmp-a-05 disabled** and don't patch or reboot it until the VM's state is clear. A reboot would kill a guest that may be running there.

## Corrective options (not yet authorized)

Which one applies depends on what the checks show.
- **Guest running on source, record stale:** reset the instance state back to ACTIVE and retry later or cold-migrate with owner agreement. This is a state-changing step that needs approval (the owner of the VM and your change authority).
- **Guest running on destination:** the DB state needs to be reconciled to match. That is a more delicate, possibly direct-database matter that needs a backup first and an expert.
- **Guest not running anywhere:** this is a recovery for the owner's workload. Ask the owner, and check the Ceph disk is intact before starting it.
- **Cause is destination/environment:** fix it first, then re-test with a non-critical VM before restarting the campaign.

For each, I'd need prerequisites, blast radius, verification and an approver defined before it's run.

## Resuming the campaign

Don't resume until all of these hold:
- The cause is identified, or the failure is shown to be isolated to that one VM.
- The VM is in a verified, owner-confirmed state.
- A single non-critical migration to the intended destination succeeds.
- The campaign owner has decided to resume. If the cause was shared, I'd also revisit the cycle time and the concurrency limits.

## Schedule impact

Don't judge it yet. If the pause is short, you can recover some time with longer days. If not, take the earlier options to the deadline owner: more hours, two hosts at a time (consuming the spare), or an exception. Tell them now rather than later, because that conversation takes time and it's better held before you're forced into a risky shortcut.

## Questions

1. Which VM is it (project, owner, criticality), and is it one of the special ones (DB, SR-IOV, GPU)?
2. What does the `fault` message and the migration record say?
3. What does `virsh list --all` show on cmp-a-05 and the destination?
4. Which host was the destination, and was it patched?
5. Is the AZ-B stream running now? If so, should it also pause until we know the cause is not shared?

> Decision support only. State-changing steps above require approval by the accountable owner and should be executed under your change process.
