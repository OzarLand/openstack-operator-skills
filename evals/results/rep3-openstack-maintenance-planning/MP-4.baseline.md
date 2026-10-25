## Turn 1

**User:**

I need to patch 40 compute hosts (kernel + QEMU) this week, 2 availability zones. How should I plan it?

**Assistant:**

# Plan for patching 40 compute hosts (kernel + QEMU) across 2 AZs

I'm assuming OpenStack/KVM. Adjust the commands if you're on something else.

## Core principles
- **Never patch both AZs at once.** Treat each AZ as a failure domain. Finish AZ-A and let it soak before touching AZ-B.
- **Canary first.** Patch 1–2 hosts, then run a real workload on them for several hours.
- **Roll in small batches.** 40 hosts is about 20 per AZ. Do 10–15% of an AZ at a time, which is 2–3 hosts. The limit is spare capacity: you need enough headroom in the AZ to absorb the evacuated VMs.
- **QEMU and kernel both need a reboot or restart.** A new QEMU binary only applies to a VM after it restarts or migrates. A new kernel needs a host reboot. Do both in the same maintenance window per host so each host is only drained once.

## Suggested week

| Day | Work |
|---|---|
| **Mon** | Pre-checks, capacity math, staging test, and a canary (1 host in AZ-A, 1 in AZ-B). Finish by midday and let them soak. |
| **Tue** | AZ-A, batches of 2–3 hosts, about 8–10 hosts. |
| **Wed** | Finish AZ-A. Soak and review metrics. |
| **Thu** | AZ-B, same batching. |
| **Fri** | Finish AZ-B only if everything is clean. Otherwise stop. Don't finish on a Friday evening. |

Keep Friday as buffer. If something goes wrong, you'll want slack rather than a weekend rollback.

## Pre-flight checklist
1. **Capacity:** Check free vCPU and RAM per AZ. Draining N hosts must leave enough room. If an AZ runs above about 75% utilization, use smaller batches.
2. **Package and version parity:** Confirm the exact kernel and QEMU/libvirt versions in your mirror. Pin them so every host gets identical bits. Check that the new QEMU is compatible with your libvirt and Nova version, including machine types.
3. **Live migration health:** Test migrations before the window. Check for VMs with pinned CPUs, SR-IOV, passthrough GPUs, or local-disk (non-shared) storage. These often can't live-migrate, so plan cold migrations or downtime with their owners.
4. **Tenant and owner comms:** Notify teams with non-migratable or latency-sensitive VMs. Give a window per AZ.
5. **Backups and rollback:** Keep the old kernel in GRUB and the old packages in your repo. Know how to roll back a host (boot the previous kernel, downgrade QEMU).
6. **Monitoring baseline:** Record current error rates, migration success rates, and host load so you can compare afterward.

## Per-host procedure
1. Disable scheduling: `openstack compute service set --disable --disable-reason "patching" <host> nova-compute`
2. Live-migrate the VMs off (`nova host-evacuate-live`, or script it with concurrency limits and bandwidth caps). Cold-migrate whatever can't live-migrate.
3. Verify the host is empty.
4. Patch kernel and QEMU/libvirt, then reboot.
5. Check after boot:
   - `uname -r` shows the new kernel.
   - `qemu-system-x86_64 --version` shows the new QEMU.
   - `libvirtd` and `nova-compute` are up.
   - Network agents (OVS/OVN) and storage mounts are healthy.
6. Re-enable the host and let a test VM schedule on it. Run a smoke test: boot, migrate, ping, and volume attach.
7. Move to the next host once it's healthy.

Automate this with Ansible, serial 2–3 per AZ, and add a pause-and-confirm step between batches. Also add a failure threshold, such as "stop if more than 1 host fails."

## Go/no-go gates between batches
- Migration success rate is above about 99%.
- No new VM error or ERROR-state spikes.
- The patched hosts show normal load and no kernel or QEMU log errors.
- Capacity in the AZ is still above your minimum.

## Things that commonly bite
- **Mixed QEMU versions in a cluster:** Live migration from a newer to an older QEMU can fail. Migrate **old to new**, never back. Keep this in mind if you have to roll back.
- **Evacuating too fast:** Parallel migrations saturate the network and slow guests. Cap concurrency at 2–4 per source host.
- **Auto-converge and big-memory VMs:** Heavy-write VMs may not converge. Enable `live_migration_permit_auto_converge` or post-copy, or schedule these separately.
- **Hosts that don't come back after reboot:** Have IPMI/BMC access verified beforehand.
- **Forgetting the VM restart for QEMU:** Hosts that are patched but not drained keep running VMs on the old QEMU until those VMs migrate or restart. Verify with `virsh qemu-monitor-command` or by checking the process binary on running guests.

## Questions that would change the plan
- Are workloads on shared storage (Ceph) or local disk?
- How much spare capacity does each AZ have?
- Do you have any non-migratable VMs (GPU, SR-IOV, pinned)?
- Do you have a hard maintenance window, or can you roll during business hours?
- Which orchestration tool do you have (Ansible, Kolla, TripleO, etc.)?

If you give me those answers, I can turn this into a concrete batch schedule and an Ansible playbook skeleton. I can also publish it as a shareable runbook page for your team.

## Turn 2

**User:**

More details: shared Ceph storage. Spare capacity is about 2 hosts per AZ. 6 VMs use SR-IOV ports, 2 VMs use PCI passthrough GPUs, and one tenant runs a 3-node database cluster spread across AZs with anti-affinity. Owners have agreed the GPU VMs can be restarted during a window.

**Assistant:**

# Revised plan with those constraints

## What changes

**1. Capacity is the binding limit.** With about 2 hosts of spare capacity per AZ, you can drain at most 2 hosts at once. That uses all your headroom, so I'd run **1 host at a time by default, and 2 only if utilization is well below your estimate** (check actual vCPU, RAM and hugepages, not just host count). That's about 20 sequential cycles per AZ. At roughly 60–90 min per host, that's 20–30 hours of elapsed work per AZ. Plan **two days per AZ** and don't expect to compress it much. The capacity returns each time a patched host comes back, so the rolling approach is safe as long as you don't skip the "re-enable before next drain" step.

**2. Shared Ceph removes the disk-copy problem.** Live migration is fast and cheap, and evacuations are quick. Check two things:
- Are any compute hosts also Ceph OSD/MON hosts (hyperconverged)? If so, set `noout` per host and wait for `HEALTH_OK` before the next one. Never reboot two hosts that hold overlapping replicas.
- Confirm the new QEMU's librbd/Ceph client version is compatible with your cluster.

**3. SR-IOV (6 VMs) and GPU passthrough (2 VMs) can't be live-migrated** in most setups. Treat them as a separate class.

For GPU VMs, the owners have approved a restart window, so use **stop, patch host, start on the same host**. This avoids needing a free matching GPU elsewhere. Do the same for SR-IOV VMs unless you've verified your Nova/libvirt version supports live migration for them. Cold-migrating them to another host is only an option if that host has a free VF on the same physnet. Doing the stop/patch/start in place also keeps their placement stable.

For both groups:
- Find the hosts first: `openstack server list --all-projects --host <h>`, filtered by port `binding:vnic_type=direct` and by flavors with `pci_passthrough:alias`.
- Get the owners' sign-off for the SR-IOV VMs too. You have it for the GPUs, but not yet confirmed for these.
- Patch these hosts **first within each AZ day, in the agreed window**, so the downtime is predictable and not scattered through the rollout.
- After restart, verify VF/GPU attach, driver load (`lspci -k`), and that link and IOMMU settings survived the new kernel. Kernel updates can break out-of-tree GPU and NIC drivers (e.g. NVIDIA, vendor SR-IOV). **Test the new kernel on a canary host with a GPU first.**

**4. The 3-node DB cluster is a quorum risk.** Three nodes across 2 AZs means one AZ holds two members, on separate hosts because of anti-affinity.
- **Never have two of its hosts down at the same time.** Losing two of three nodes loses quorum.
- Pin those hosts into **separate batches**, and wait for the cluster to be healthy and in sync (replication caught up) before moving on.
- Ask the tenant for an agreed contact and a quick health check you can run between steps. Ideally they trigger a leader failover before their node's host is drained, so you're not migrating the primary.
- Live migration will briefly stun the VM (the final switchover). For a latency-sensitive DB, prefer migrating replicas, not the primary.
- Watch for the scheduler failing to find a host. With tight capacity and a hard anti-affinity group, evacuating a DB VM may have **no valid target**. Check that a valid destination exists before draining those hosts.

## Revised schedule

| Day | Work |
|---|---|
| **Mon** | Pre-flight. Canary: 1 plain host in AZ-A, 1 GPU host in AZ-B. Soak ~4 h. |
| **Tue** | AZ-A: SR-IOV and GPU hosts first (in the window), then plain hosts, 1 at a time. |
| **Wed** | Finish AZ-A. Include the DB hosts in separate batches. Review metrics. |
| **Thu** | AZ-B: same order. Start only if AZ-A is clean. |
| **Fri** | Finish AZ-B, or use it as buffer. Do not start new drains late in the day. |

If AZ-A takes the full two days, AZ-B will also need two. That fits Thursday and Friday but leaves **no buffer**. If a problem hits, AZ-B slips to next week. That's the right trade-off, and better than patching both AZs in parallel.

## Updated gates and automation
Between each host:
- `nova-compute` is up and the host is enabled, with test VM boot and migration working.
- Ceph is `HEALTH_OK` and no PGs are degraded.
- The AZ still has at least 1 host of free capacity.
- If a DB host was just done, the tenant confirms the cluster is healthy and in sync.
- Migration failure rate stays low. Stop after 1 failed host.

Order hosts in the playbook as: GPU/SR-IOV, then DB-VM hosts (interleaved with plain hosts), then plain hosts. Use `serial: 1` and a manual pause between each DB host.

## Questions that would sharpen this
1. Are compute hosts also Ceph OSD hosts?
2. What's actual utilization per AZ? Is the "2 spare hosts" measured in vCPU, RAM, or both, and does it count hugepages or pinned CPUs?
3. Do the SR-IOV VMs' owners accept downtime, or must those stay up?
4. Which hosts do the GPU, SR-IOV and DB VMs sit on, and are any on the same host?
5. Which OpenStack release and libvirt/QEMU versions are you moving from and to?

If you share the host list and VM placement, I can build the exact batch order, per-host checklist and an Ansible playbook skeleton. I can also publish it as a runbook page your team can use.

## Turn 3

**User:**

We're on host 5 of 40. On cmp-a-05 the live migration of one VM failed half-way: the VM is now in ERROR and the migration shows 'error'. The other VMs on that host migrated fine. Can we carry on with cmp-a-06 to stay on schedule?

**Assistant:**

**No, pause.** This is the stop condition we set (stop after 1 failed host). Staying on schedule isn't worth the risk. Fix this first, and tell me if you disagree. It will probably cost an hour or two, not a day.

## Why not continue
- **You have an unknown failure mode.** If the cause is systemic (a QEMU or libvirt version mismatch, a network or Ceph issue, or a bad migration setting), cmp-a-06 will fail the same way. It would also leave you with two hosts partly drained and your 2-host headroom gone.
- **The VM may still be in a bad state.** A half-way migration can leave a QEMU process on the source, the destination, or both. Dropping more load onto the cluster while that's unresolved makes it harder to untangle.

## Triage, in order

1. **Don't touch the VM yet.** Do not reboot it, reset-state it, or delete it. First find out where it really is.
2. **Find where the instance actually is.**
   - `openstack server show <vm>` and look at `OS-EXT-SRV-ATTR:host` and `OS-EXT-STS:task_state`.
   - On **both** cmp-a-05 and the destination, run `virsh list --all` and `ps aux | grep <instance-uuid>`.
   - **Two QEMU processes for the same instance is the dangerous case.** With RBD, that risks two writers on the same volume. Stop the extra one only after confirming which one holds the current state, and do not start both.
3. **Read the logs:** `nova-compute` on source and destination, `libvirtd`/QEMU logs (`/var/log/libvirt/qemu/<instance>.log`), and the Nova conductor log. Look at `openstack server migration list` and `openstack server migration show` for the failure.
4. **Check the common causes:**
   - Dirty-page rate too high (memory-heavy VM that never converges). Look for a timeout or "migration stalled" message.
   - QEMU or machine-type mismatch between source (old) and destination.
   - Network or MTU issue on the migration network.
   - Destination out of resources, or a CPU feature mismatch.
5. **Once you know where it is, recover.**
   - If it's running fine on the source and Nova just has stale state, run `openstack server set --state active <vm>` (or the equivalent for your release) after you confirm the guest is actually running. Clean up the failed migration record if needed.
   - If it's running on the destination, make Nova's view match.
   - If it's stopped and clean, `openstack server reboot --hard` is a reasonable fix, **but check with the owner first**, since it's an outage for that VM.
6. **Before resuming:** confirm the source host's instance directory and RBD volume locks are clean (`rbd status` / `rbd lock ls`) and that the VM is healthy, with the owner's confirmation. Leave cmp-a-05 disabled until this is resolved.

## About cmp-a-05 itself
If the other VMs migrated and the failed one is stuck, cmp-a-05 is not yet empty and has not been patched. **Don't reboot it for patching until the VM is accounted for.** Rebooting the host with a half-migrated guest could corrupt state or kill the only live copy. Once the VM is safely resolved, you can either patch cmp-a-05 and carry on, or leave it and revisit.

## Deciding how to proceed
- **If it's a one-off** (e.g. a single heavy-write VM that didn't converge): handle that VM specially (enable auto-converge or post-copy, or schedule a short stop and restart with its owner), then continue as planned.
- **If it points to a systemic issue** (QEMU/libvirt versions, network): fix that before touching more hosts. A cause common to all hosts would affect the remaining 35.
- **Who owns this VM?** If it's the DB cluster tenant's VM, tell them now and check the cluster's health before anything else.

Once you have the logs or the output of the checks above, share them and I can help work out the cause. I can also revise the schedule. For example, if you lost half a day, I'd drop the buffer on Friday and keep the one-host-at-a-time rule.
