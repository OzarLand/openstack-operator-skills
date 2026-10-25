## Turn 1

**User:**

I need to patch 40 compute hosts (kernel + QEMU) this week, 2 availability zones. How should I plan it?

**Assistant:**

# Patch plan: 40 compute hosts, 2 AZs, kernel + QEMU

I'm assuming OpenStack, from the working directory name. Say so if it's something else.

## Key constraints
- **A kernel update needs a reboot.** A QEMU update only reaches running VMs when they restart or migrate. So every host has to be drained, and the VMs should move in the process.
- **Drain by live migration.** Migrating a VM from an unpatched host to a patched one is what lands it on the new QEMU. Cold-migrate or schedule downtime for anything that can't live-migrate (SR-IOV or passthrough, local-disk without block migration, pinned or huge-page oddities).

## Capacity math
- Hold at most **10–15% of hosts out at once**. For 40 hosts that's **4 per batch**, 2 per AZ, which gives about 10 batches.
- Confirm each AZ can absorb the drained hosts' load at around 80% utilisation or lower. If it can't, use smaller batches or temporarily free capacity.
- **Only one AZ at a time.** The untouched AZ is your fallback, and tenants with multi-AZ HA stay up.

## Schedule (Mon–Fri)
| Day | Work |
|---|---|
| **Mon** | Prep and canary. Patch **1 host in AZ-A** and soak it for hours. Verify the kernel version, QEMU version, a live migration *onto* it, and a fresh boot. |
| **Tue–Wed** | AZ-A: the remaining 19 hosts in batches of 3–4. |
| **Thu** | Gate. Check AZ-A health, then canary 1 host in AZ-B and continue. |
| **Thu–Fri** | AZ-B: the remaining 19 hosts. Stop starting new batches by early Friday afternoon. |
| **Fri PM** | Cleanup, final audit, and a buffer for stragglers. |

## Per-batch runbook
1. **Pre-check.** Confirm no active alarms, Ceph or storage health is OK, and the control plane is healthy. Check that no host in the batch is in a failed state and that spare capacity is sufficient.
2. **Disable** the host (`openstack compute service set --disable --disable-reason "patching"`) and put it in maintenance in monitoring.
3. **Drain.** Live-migrate all VMs off, a few at a time. Watch for stuck migrations, and set a timeout and an abort or retry policy for ones that don't converge.
4. **Patch** the kernel and QEMU/libvirt packages, then **reboot**.
5. **Validate.** Check `uname -r`, the `qemu-kvm` version, that nova-compute, libvirtd and OVS or OVN agents are up, that networking is healthy, and that the host is registered in placement.
6. **Re-enable**, then put a test VM on it (boot, ping, volume attach).
7. **Next batch.** Start it only once the previous batch is green. Rebalancing back isn't required.

## Risks to settle before Monday
- **Pets that can't move.** List the VMs that can't live-migrate and agree downtime with their owners now.
- **Rollback.** Keep the previous kernel in GRUB, pin package versions, and have a tested way to boot the old kernel. Decide in advance what failure on the canary means (stop everything).
- **Version skew.** Confirm that live migration between old and new QEMU is supported for your machine types. Don't migrate to a *older* QEMU than the source.
- **Control-plane and storage nodes.** If they're separate from these 40 hosts, they have their own plan. Don't patch them mid-batch.
- **Communications.** Send a notice to tenants with the windows per AZ, and name one person as the stop-the-line decider.
- **Automation.** Use Ansible or similar with `serial: 2` per AZ and a health-check gate, so you aren't doing 40 hosts by hand.

## Go/no-go gates
Proceed to the next batch only if:
- all migrations succeeded or are accounted for,
- there are no new alerts or error spikes (API errors, packet loss, I/O latency),
- the batch's hosts are back in service with the right versions.

If you tell me your cloud setup (OpenStack version, storage backend, how many VMs per host, and whether you use SR-IOV or local disks), I can tighten the batch sizes and draft the Ansible playbook or drain script.

## Turn 2

**User:**

More details: shared Ceph storage. Spare capacity is about 2 hosts per AZ. 6 VMs use SR-IOV ports, 2 VMs use PCI passthrough GPUs, and one tenant runs a 3-node database cluster spread across AZs with anti-affinity. Owners have agreed the GPU VMs can be restarted during a window.

**Assistant:**

# Revised plan with your details

## What changes

**1. Spare capacity of 2 hosts per AZ means batches of 2, not 4.**
Draining 2 hosts uses all your headroom in that AZ, so run batches of **2 hosts per AZ** and never more. Ceph shared storage helps, because live migration doesn't have to copy disks. With 20 hosts per AZ that's 10 batches per AZ. Each batch is drain, patch, reboot and validate, about 1–1.5 hours when migrations go well. That's 2–3 batches per half day, so AZ-A should take Tue–Wed and AZ-B Thu–Fri. This is tight. To get slack, leapfrog: while batch N reboots, start draining batch N+1 only if that host is not part of the 2-host limit. In practice that means **at most 2 hosts out of service per AZ at any moment**, counting hosts that are still draining. Don't overlap.

If you can free more capacity (shut down dev or test VMs, or add a temporary host), do it. It's the single biggest lever on your timeline.

**2. SR-IOV VMs (6): cold-migrate or restart, don't live-migrate.**
- Live migration with SR-IOV ports is only reliable on newer OpenStack releases and with specific NIC and driver combinations. Check your release and test it on one non-critical VM first.
- If it isn't supported, treat all 6 as downtime workloads. Find their owners now and schedule restarts, or migrate them in their own sub-window.
- On the destination, make sure there are free VFs on the right physical network (`physnet`) before you drain. Otherwise the scheduler will fail the move.
- Pin down which hosts these 6 are on. If several sit on one host, patch that host as a planned-downtime item, not part of a normal batch.

**3. GPU passthrough VMs (2): restart during the agreed window.**
- Identify which hosts they're on and which hosts have free matching GPUs. Passthrough VMs can only land on hosts with the same GPU flavor and a free device.
- Simplest approach: stop both VMs at the start of their window, patch and reboot their host(s), and start them again, either on the same host or on a spare GPU host. Verify the GPU is visible in the guest (`nvidia-smi` or similar) before you call it done.
- Do this at the **canary stage** (Monday or early Tuesday). If anything is wrong with the new kernel and the GPU driver (a mismatch is common), you find out before touching the other hosts.

**4. 3-node DB cluster with anti-affinity across AZs: the main HA risk.**
- It tolerates losing one node, but not two. So the rule is: **never have two of its nodes down or in transition at the same time.** Because the AZs are patched one at a time, that mostly holds.
- Within an AZ, make sure the node isn't migrated onto a host that's next in the batch. Use the batch order (or a temporary host-aggregate or scheduler hint) to keep it away from hosts you're about to drain.
- Before the VM moves, ask the owners to confirm the cluster is healthy with all 3 members in sync. After the move, confirm it has rejoined before you continue. Make this a **go/no-go gate** for any batch that includes the node.
- Let the owners know the windows. Their node in each AZ will be live-migrated (brief pause) or restarted, whichever you choose.
- With 3 nodes across 2 AZs, two of them share an AZ. Find out which AZ that is and **patch that AZ first with extra care**, since losing that AZ's hosts takes two nodes at once if both happen to be on hosts that are down at the same time. Make sure those two are on different hosts and in different batches.

## Updated order of work

| When | What |
|---|---|
| **Before Mon** | Inventory: which hosts have the 6 SR-IOV VMs, the 2 GPU VMs, and the DB nodes. Confirm free VFs and GPUs on target hosts. Test one live migration of a normal VM onto an already-patched host if you can. Check the live migration support matrix for SR-IOV on your release. Tell owners the windows. |
| **Mon** | Canary in AZ-A: 1 non-special host. Then the **GPU host(s)** in their window. Validate kernel, QEMU, GPU in guest. |
| **Tue–Wed** | AZ-A in batches of 2. Handle SR-IOV VMs in a planned sub-window. DB gate each time. |
| **Thu** | AZ-A health gate, AZ-B canary, then continue in batches of 2. |
| **Thu–Fri** | AZ-B in batches of 2. Stop starting new batches early Friday afternoon. |
| **Fri PM** | Cleanup and audit. Keep this half day as buffer. Any remaining hosts roll to Monday if needed. |

## Things to verify
- **Ceph:** Check it's healthy (`ceph -s`, no degraded or backfilling PGs) before each batch. Rebooting compute hosts shouldn't affect it, but a slow cluster makes migrations time out. Don't patch Ceph nodes in the same week unless they're part of this.
- **Live migration limits:** Cap concurrent migrations (e.g. 2 per source host) so you don't saturate the network. Set `live_migration_completion_timeout` and `live_migration_permit_auto_converge` for busy VMs, so memory-heavy ones converge instead of hanging.
- **Version skew:** Confirm old-to-new QEMU live migration works for your machine types, and never migrate back to a host with older QEMU. Since you migrate VMs onto patched hosts, this is automatically in the safe direction if you always send VMs to already-patched hosts first.
- **Rollback:** Previous kernel kept in GRUB. If the canary fails, stop.

## Realistic risk
The schedule fits only if migrations go smoothly. If the SR-IOV VMs or a stuck migration eat time, Friday is your buffer. If you can't free extra capacity, plan on the last few AZ-B hosts slipping to the following Monday, and tell stakeholders that now rather than on Friday.

If you give me the host inventory (which hosts have the special VMs), I can write out the exact batch order and a drain script with the gates built in.

## Turn 3

**User:**

We're on host 5 of 40. On cmp-a-05 the live migration of one VM failed half-way: the VM is now in ERROR and the migration shows 'error'. The other VMs on that host migrated fine. Can we carry on with cmp-a-06 to stay on schedule?

**Assistant:**

**Don't start cmp-a-06 yet.** Fix the ERROR VM first. With only 2 spare hosts in AZ-A, you can't afford an unresolved host plus a new drain, and a half-failed migration can leave the VM in an unclear state. Fifteen minutes of triage is cheaper than a lost VM.

## 1. Find out where the VM actually is
A failed live migration can leave the guest running on the source, running on the destination, or (rarely) running on both.

```
openstack server show <vm> -c status -c OS-EXT-SRV-ATTR:host -c OS-EXT-SRV-ATTR:hypervisor_hostname -c OS-EXT-STS:vm_state -c OS-EXT-STS:task_state
openstack server migration list --server <vm>
```
Then check libvirt on **both** hosts:
```
virsh list --all | grep <instance-name>
```
- **Running on source only:** the usual case. The VM is fine, and Nova's record is just wrong.
- **Running on destination only:** the migration finished but Nova didn't record it.
- **On both, or paused on either:** stop. Don't reset state until you know which copy is live, and make sure two copies never both write to the same Ceph RBD volume. Check `rbd status` on the volume for watchers.

## 2. Look at the cause
Check the nova-compute log on source and destination for that instance ID, and the libvirt/QEMU log (`/var/log/libvirt/qemu/<instance>.log`). Common causes: a timeout on a memory-heavy VM, a destination with no free resources, an unexpected device (SR-IOV or a config drive), or a network or Neutron port-binding failure.

This matters beyond this VM. If the cause is systemic (a destination problem, or a version/machine-type incompatibility with the newly patched hosts), the next 35 hosts will hit it too.

## 3. Recover
Once you know where it's running:
- If it's running on a host and healthy: `openstack server set --state active <vm>`. Make sure its host in Nova matches reality. If it doesn't, you may need to correct it (a DB edit or `nova-manage`), so get a second pair of eyes.
- If it's not running anywhere: `openstack server reboot --hard <vm>` or start it. With Ceph-backed disks, this should come up cleanly on a good host.
- Confirm the VM answers (ping, a login or app check), and the port is bound and the volumes are attached.

## 4. Check if this VM is special
Is it one of the SR-IOV or GPU VMs, or the DB cluster node? If it's the DB node, check cluster health and rejoin before anything else. If it's SR-IOV or GPU, that explains the failure and it should have been in the cold-migrate list.

## 5. Finish cmp-a-05
Check that nothing else is still on it (`openstack server list --host cmp-a-05 --all-projects`), then patch and reboot it as planned. The host itself isn't blocked, since the failed VM is off it or can be hard-rebooted elsewhere. It must also be validated before it counts as done.

## Is the schedule at risk?
Only if you carry on blindly. If the cause is a one-off (a busy VM that timed out), carry on once the VM is recovered, and tighten the migration timeouts or use auto-converge for heavy VMs. If it's systemic, pause and fix it, because every later failure will cost more than the delay. Use the Friday buffer and tell stakeholders now if you're behind.

If you paste the migration error from the nova-compute log and the output of the first command above, I can tell you which case it is and what to do next.
