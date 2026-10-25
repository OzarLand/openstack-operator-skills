**Yes. Don't run `evacuate` for all 40 yet.** The blocker is not evacuation speed. Nobody has shown that cmp-0417 is dead. A down `nova-compute` only means Nova has stopped hearing from it. If the host is still running and isolated from the control plane, evacuating starts a second copy of each VM, and both copies can write to the same Ceph disks. For customer databases, that means corruption. Ceph being shared storage does not prevent this by itself. Treat that as an assumption to verify for your backend, not a guarantee.

I can't run commands in this session, so everything below is from what you've told me. Nothing is confirmed.

## Situation
- **Capability lost:** compute service on cmp-0417 (and the VMs on it being reachable).
- **Still working:** unknown. Need to check whether the VMs are actually running and whether other computes are up.
- **Business impact:** ~40 VMs, including customer databases. Criticality per VM is unknown to me.
- **What changed:** not stated. Something happened at 03:12. Ask what.
- **Timeline:** down since 03:12. Actions already taken since then are unknown.

## Evidence
| # | Class | Statement | Source |
|---|---|---|---|
| 1 | Observed | `nova-compute` on cmp-0417 shows `down` since 03:12 | your report of the service list |
| 2 | Reported | About 40 VMs unreachable, including customer DBs | on-call |
| 3 | Assumption | Instance disks are on Ceph RBD, not local ephemeral storage | your statement |
| 4 | Gap | Whether the host is powered on, and whether the VMs are still running | not checked |
| 5 | Gap | Whether other computes or the message bus are affected | not checked |

## Hypotheses
| Hypothesis | Supports | Would disprove | Discriminating check |
|---|---|---|---|
| A. Host is dead (power/hardware failure) | Service down, VMs unreachable | Power state on, VMs still answering on their network | Out-of-band power status (iDRAC/iLO/IPMI) |
| B. Host is alive but isolated (network, NIC, or mgmt path) | Unreachable from control plane | Host reachable through another path, or powered off | Out-of-band power status; reach host via mgmt network; check switch port |
| C. Host is fine, `nova-compute` crashed or can't reach RabbitMQ | Service down, host up | Host down or VMs unreachable | `nova-compute` log and process on host |
| D. Control-plane problem (RabbitMQ partition, etc.) affecting many computes | Other computes also down or flapping | Only cmp-0417 affected | `openstack compute service list` for all hosts; RabbitMQ cluster status on each node |

Hypothesis A is the only one where evacuation is safe. B is the dangerous one, and it looks the same from the API.

## Next diagnostics (read-only)
1. `openstack compute service list --host cmp-0417` and the same for all `nova-compute` services. Shows whether this is one host (A, B, C) or many (D). Expected: only cmp-0417 down → A/B/C; many down → D, stop here.
2. Out-of-band power status for cmp-0417. Expected: **off** → A. **On** → B or C, and evacuation is not allowed yet.
3. `openstack server list --host cmp-0417 --long` and note each VM's status. Expected: ACTIVE means the hypervisor still believes they're running.
4. Ceph watcher check per instance disk, for example `rbd status <pool>/<instance-uuid>_disk` (verify pool and naming in your deployment). Expected: a watcher from cmp-0417's IP means the VM is probably still running there → **do not evacuate that VM**.
5. If the host is reachable at all: `nova-compute` log and `systemctl status` on the host, for the 03:12 event.

## Protect decision
Is state getting worse? Not shown. Check whether the number of instances in ERROR or stuck in transitional states is growing. If it isn't, there is no reason to rush: a few more minutes of checks cost little compared with a corrupted database.

## Corrective options (not yet authorized)
**Option 1, if power is confirmed off (hypothesis A):**
- Prerequisites: out-of-band confirmation recorded; watcher check shows no live client; target capacity in Placement; each VM's owner has agreed the order.
- Steps: force the service down (`openstack compute service set --down cmp-0417 nova-compute`); evacuate in batches ordered by business criticality (customer DBs first only if their owners say so); verify each VM is ACTIVE, reachable, and its disk is consistent.
- Stop conditions: any VM still shows a watcher from cmp-0417; any target fails to boot; capacity runs out.
- Recovery: none for data already written on the new host. Keep cmp-0417 disabled and forced down when it returns. Do not bring it back until `nova-compute` has cleaned up the evacuated copies (see P3 in the failure patterns).
- Approver: the incident owner with authority over the customer SLA, plus each DB owner for their VMs.

**Option 2, if the host is alive (B or C):**
- Do not evacuate. Restore the host's management or network path, or restart `nova-compute` after reading its log. The VMs may never have stopped. Evacuating a running host is the two-copies case.
- Approver: the on-call and the platform owner.

**Option 3, if many computes are down (D):** Not a host problem. Stop and treat it as a control-plane incident (RabbitMQ partition handling in particular). Evacuating would move load onto a broken control plane.

## Verification before declaring recovery
- Each evacuated VM: ACTIVE on the new host, its service answers, the DB starts and passes its own consistency check.
- Capacity left on the remaining computes.
- No watcher on the old host for each moved disk.

## Gaps and open questions
- Is cmp-0417 powered on? (Blocks everything.)
- Are other computes down? (Decides whether this is a host or the control plane.)
- Are instance disks really on Ceph RBD, and not local ephemeral? (Without shared storage, evacuation of disks may not work at all.)
- What happened at 03:12, and what has been done since? (Restarts or host reboots can change the picture.)
- Who has authority to approve evacuation for these customers?

## Follow-up
- Containment: confirm power state, then fence and evacuate only the VMs whose owners have agreed.
- Structural: find what happened at 03:12, and whether `service_down_time` and fencing automation should exist for this host class.

What I'd tell on-call right now: **don't evacuate until power state and the Ceph watcher check are done.** Those two checks take minutes. Both answers decide whether evacuation is safe.

Decision support only. State-changing steps above require approval by the accountable owner and should be executed under your change process.