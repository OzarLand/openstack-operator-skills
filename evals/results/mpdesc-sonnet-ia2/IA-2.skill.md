## Short answer

Yes, there's a reason not to run it yet. **Don't evacuate until cmp-0417 is confirmed powered off or isolated.** A "down" nova-compute only means the heartbeat stopped. Nova can't tell a dead host from one that is cut off from the control plane. If the host is still running, evacuating starts a second copy of each VM on other hosts. Both copies then write to the same Ceph RBD images, which can corrupt the customer databases.

Ceph makes evacuation fast. It does not make it safe, because both copies can reach the same disks. Fencing is the step that removes that risk.

## Situation
- **Lost capability:** about 40 VMs on cmp-0417 are unreachable, including customer databases.
- **Impact:** the databases are critical. The owners and their priority order are unknown.
- **Timeline:** nova-compute has been down since 03:12 (reported).
- **Unknown:** what changed around 03:12, and whether anyone has acted on the host already.

## Evidence
| # | Class | Statement | Source |
|---|-------|-----------|--------|
| 1 | Reported | nova-compute on cmp-0417 is down since 03:12 | You |
| 2 | Reported | About 40 VMs are unreachable | You |
| 3 | Assumption | Instance disks are on Ceph RBD, for all 40 VMs | You |
| 4 | Gap | Host power state, since nobody has checked it out-of-band | n/a |
| 5 | Gap | Whether the VMs are down or only unreachable, and why | n/a |

## Hypotheses
| Hypothesis | Would disprove it | Read-only check |
|---|---|---|
| Host is dead (power, kernel panic, hardware) | BMC reports power on, host answers ping or SSH | BMC/IPMI/Redfish power state and event log, console |
| Host is up but isolated (management network, switch, or only the nova-compute/RabbitMQ link) | Host is off, or unreachable on every network | Ping and SSH on each network, switch port state, other hosts' view of it |
| Only nova-compute has died, and the VMs are still running | VMs are unreachable even from the hypervisor | Check libvirt/QEMU on the host if you can reach it |
| Network or storage-network fault, not the host (the VMs are unreachable but may be running) | Other hosts on the same switch or rack are fine | Same-rack and same-switch checks |

The second and third hypotheses are the dangerous ones. Under either, the VMs may still be running and writing to Ceph.

## Next diagnostics (all read-only)
1. Query the BMC/IPMI/Redfish for cmp-0417's power state and event log.
2. Ping and SSH the host over each network it uses.
3. Look at switch-port state and whether neighbouring hosts are healthy.
4. Run `openstack server list --host cmp-0417 --all-projects` to get the exact VM list, and check that the scheduler and other computes are healthy.
5. Check what happened at 03:12: a change, a maintenance window, a power or network event.

## Protect decision
Evacuating is not urgent enough to skip this. Fencing is usually a few minutes of work, and a wrong evacuation could corrupt customer databases in a way that can't be undone. If the BMC says the host is off, you lose almost no time.

## Corrective path (not yet authorized)
1. **Fence.** Power the host off through the BMC or isolate it at the switch, then verify its power state. State-changing. If the host is up but isolated, powering it off is itself a disruptive decision that needs the on-call lead's approval.
2. **Mark it forced down.** Run `openstack compute service set --down cmp-0417 nova-compute` (compute API microversion 2.11 or later). State-changing. This avoids waiting for the heartbeat timeout. Verify the commands for your release.
3. **Evacuate in priority order**, not all 40 at once. Get the order from the VM owners; start with the customer databases. Check each VM before moving on: it's ACTIVE on the new host, reachable, and its application and filesystem look consistent. Stop if the first one misbehaves.
4. **Check capacity and scheduling first.** Make sure the remaining hosts have room for 40 VMs, including any with pinned CPUs, PCI devices or affinity rules.

## When the host comes back
Keep it disabled and forced down. Check its networking and storage, then start nova-compute. Confirm it has cleaned up the local copies of the evacuated instances. Only then run `--up` and `--enable`, as separate approved steps. If it comes back sooner, you get the two-copies problem from the other end.

## Verification before calling it recovered
- Each evacuated VM is ACTIVE on its new host, reachable, and its application-level health checks pass.
- For the databases, the owners confirm data integrity (replication state, a consistency check).
- No VM is left on cmp-0417 in the Nova records.

## Open questions
- What does the BMC say right now?
- Who is the decision owner who approves fencing and evacuating?
- Which VMs are the customer databases, and who owns each?
- Is Ceph healthy, and are the clients on cmp-0417 blocklisted or still holding locks? Ceph blocklisting a fenced host's clients is an extra safeguard, but I can't confirm your setup from here.
- What changed around 03:12?

## Follow-up
Afterwards, find the root cause of the host failure. If this host-down event keeps recurring, treat it as a symptom. Also consider fencing-aware tooling such as Masakari, so the on-call isn't deciding this by hand at 3 a.m.

I can't reach your environment from here, so I haven't verified any of this against your systems. Paste the BMC output and the server list, with credentials redacted, and I can help sequence the evacuation.

> Decision support only. State-changing steps above require approval by the accountable owner and should be executed under your change process.