**Short answer: yes, there is a reason not to, and it is the main risk here.** Don't run `evacuate` for all 40 VMs yet. Nova marking `nova-compute` down means only that the control plane stopped hearing from the host. It doesn't mean the host is dead. If cmp-0417 is still running the VMs, evacuating them starts a second copy of each on another host, and both copies can write to the same Ceph images. For customer databases, that means corruption. Shared storage makes evacuation possible; it doesn't make it safe.

I haven't run anything. This session has no access to your cloud, so everything below is from what you've told me.

## Situation
- **Capability lost:** the VMs on cmp-0417 are unreachable. Whether that's a dead host or a host cut off from the control plane is unknown.
- **Still working:** unknown. Are the other computes up? Is RabbitMQ healthy? Those answers decide whether this is one host or a control-plane problem.
- **Business impact:** customer databases, about 40 VMs. Criticality per VM is unknown.
- **Timeline:** down since 03:12. What time it is now, and what's been done since (restarts, power actions, network changes), is not stated.

## Evidence
| # | Class | Statement | Source |
|---|---|---|---|
| 1 | Reported | nova-compute on cmp-0417 is down since 03:12 | on-call |
| 2 | Reported | ~40 VMs unreachable, including customer databases | on-call |
| 3 | Reported | Instance disks are on Ceph | on-call, not verified in nova.conf |
| 4 | Assumption | The host is dead, so evacuation is safe | none. Not shown |
| 5 | Gap | Power state, whether the VMs are still running, Ceph watchers, other computes' status, bus health | not checked |

## Why the "Ceph makes it quick" argument doesn't hold
- Ceph lets a new host attach the image. It does not stop the old host from writing to it.
- If cmp-0417 is isolated rather than dead (switch problem, RabbitMQ partition, agent failure), its QEMU processes may still hold the disks open and keep writing.
- Evacuation doesn't wait for that. Two writers on one database image corrupt it, and the damage shows up later, often after the "recovered" message.

## Hypotheses
| Hypothesis | Supports | Would disprove | Discriminating check (read-only) |
|---|---|---|---|
| A. Host is dead (power/hardware) | Heartbeat gone, unreachable | BMC shows power on, or the host answers on its management or data network | BMC power status; ping/SSH from a jump host |
| B. Host is alive but isolated from the control plane (network, bus, agent) | Other VMs on it still answer | VMs unreachable from the network too | Can you reach the host's data IPs? Are its VMs' services answering? |
| C. Control-plane or bus problem affecting many computes | Other computes also reporting down, or RabbitMQ alarms | Only cmp-0417 is down | `openstack compute service list` for all hosts; RabbitMQ cluster status on each node |
| D. Storage fault on the host or Ceph | Disk/OSD errors, slow requests | Ceph healthy, host healthy | `ceph -s`; `rbd status <pool>/<instance-disk>` shows watchers. A watcher from cmp-0417 means it still has the image open |

## Next diagnostics (all read-only)
1. Power state via BMC (`ipmitool -H <bmc> power status` or Redfish). Expected: "off" under A, "on" under B/C/D.
2. `openstack compute service list` for every host, plus `openstack server list --host cmp-0417 --long` for VM state. If several hosts are down, it's C, not one host.
3. RabbitMQ `cluster_status` and alarms, from each node. A partition means don't touch the nodes; see P2.
4. For a few database VMs, `rbd status` on their disks. Watchers from cmp-0417 mean its QEMU is still holding them.
5. Logs on cmp-0417 from around 03:12, if it's reachable: nova-compute, libvirt, Ceph client.
6. Confirm the disk backend: `images_type = rbd` in nova.conf on cmp-0417, and check whether any VM uses local ephemeral disk. Local-disk VMs can't be evacuated at all.

## Protect decision
- Nothing in the input shows the state is getting worse, so the default is to investigate for a few minutes. Check whether other computes or instance counts in ERROR/BUILD are changing. If they are, that's a control-plane problem (P1), and the decision changes.
- **Decision owner:** not named. Someone needs to own the choice to fence and evacuate. Who is it?

## Corrective path (not authorized)
Sequence, once the hypothesis is confirmed as A (or the host is otherwise confirmed off):
1. **Fence:** confirm power off via BMC, or isolate at the switch. Prerequisite: BMC access. Verify by power state, not by the service list. Approver: whoever owns the compute fleet.
2. **Force down:** `openstack compute service set --down cmp-0417 nova-compute`. Blast radius: nova will treat all its instances as gone. Recovery: `--up` only after cleanup (P3).
3. **Evacuate in batches, by priority:** customer databases first, agreed with their owners. Small batches, verify each VM (active on new host, reachable, DB starts cleanly) before the next. Stop if placement fails or the control plane slows.
4. **Return of cmp-0417:** keep it disabled and forced down until nova-compute has cleaned up the evacuated copies. Then `--up` and `--enable` as separate steps.

If the diagnostics show B, C or D, evacuation is the wrong move. Fix the network, bus or storage, and the VMs may just come back.

## Verification before declaring recovery
- Each evacuated VM is ACTIVE on its new host, network-reachable, and its database passes a consistency check.
- No watchers from cmp-0417 remain on the images.
- All computes and agents report up, RabbitMQ and Ceph healthy.
- A test VM can be created, reached and deleted.

## Gaps and open questions
- Is cmp-0417 powered on? (closes hypothesis A vs B)
- Are other computes down too? (C)
- Current time, and what's been done since 03:12?
- Who owns the decision to fence and evacuate, and who owns each customer database?
- Confirm the Ceph backend and that no VM uses local disk.

## Follow-up
- Containment: fence, force down, evacuate by priority. Structural: why the host went silent at 03:12 (network, bus or hardware), and whether fencing can be automated. That's a job for `openstack-automation-review`, not for now.

**What to tell the on-call:** don't evacuate all 40 now. Get the BMC power state and the Ceph watcher check first, which takes minutes. If the host is confirmed off, fence and force it down, then evacuate the database VMs in batches with an owner signing off on each.

Decision support only. State-changing steps above require approval by the accountable owner and should be executed under your change process.