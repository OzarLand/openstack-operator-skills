## Short answer

Yes, there is a reason not to. **Don't evacuate yet. Fence the host first.** Evacuation takes a few minutes once the host is fenced.

"nova-compute down since 03:12" only means the heartbeat stopped. Nova can't tell whether the host is dead or just cut off from the control plane. If `cmp-0417` is alive but isolated, for example through a management network problem, a hung or crashed `nova-compute` agent, or a RabbitMQ issue, its VMs may still be running. In that case evacuation starts a second copy of each VM on a new host, with the same Ceph RBD disk attached. Two writers on one volume is how you corrupt a customer database. The Ceph backend makes this worse, because the evacuated VM can attach to the disk immediately. It does not make evacuation safer.

## Situation

- **Capability lost:** about 40 VMs on `cmp-0417` are unreachable, including customer databases.
- **What still works:** unknown. Nobody has said whether the VMs are down or just unreachable, or whether other hosts are healthy.
- **Business impact:** customer databases are affected. I need the owners' priority order for restoring the 40 VMs, because I can't infer it.
- **What changed:** unknown. I need to know about any deploy, network, switch, kernel or RabbitMQ change around 03:12.
- **Actions already taken:** unknown.

## Evidence

| # | Class | Statement | Source |
|---|---|---|---|
| 1 | Observed (by you) | `nova-compute` on `cmp-0417` is "down" since 03:12 | `openstack compute service list` |
| 2 | Reported | About 40 VMs are unreachable | on-call |
| 3 | Assumption | Instance disks are on Ceph RBD for all 40 VMs | you |
| 4 | Gap | Host power state and BMC status | not checked |
| 5 | Gap | Whether the VMs are still running on the host | not checked |

## Hypotheses

| Hypothesis | Disproving check (read-only) |
|---|---|
| Host is powered off or crashed (kernel panic, PSU, hardware) | BMC/IPMI/Redfish says powered on, and the host answers ping or SSH |
| Host is up but isolated, with a management or tenant network or switch fault | Host reachable via BMC console, or out-of-band path, with `virsh list` showing running guests |
| Host is up and VMs are running, but `nova-compute` is hung or crashed, or has lost RabbitMQ | A `nova-compute` log gap at 03:12, and `systemctl status`. Other computes would also show trouble if the bus is at fault |
| The VMs are unreachable for a different reason (tenant network or OVN/agent on that host) | Check whether `cmp-0417`'s network agents are down too |

If other computes are also flapping or "down", that points to RabbitMQ or the database. Evacuating then would be a bad idea for a second reason.

## Next diagnostics (all read-only)

1. BMC/IPMI/Redfish power state and event log for `cmp-0417`. This is the most valuable check.
2. `openstack compute service list` for all hosts, to see whether it's one host or many.
3. `ping` and `ssh` to `cmp-0417` on the management network. Use the BMC console if SSH fails.
4. If you can get on the host: `systemctl status nova-compute libvirtd`, `virsh list --all`, `journalctl` around 03:12, and `dmesg`.
5. `openstack network agent list` filtered to that host.
6. RabbitMQ and Galera health, if step 2 shows more than one host affected.
7. On Ceph: `rbd status <pool>/<image>` on one or two of the affected volumes. Active watchers mean something is still using the disk, so do not evacuate.

## Protect decision

The 40 VMs are already down, so each extra minute of investigation costs customer uptime. The risk of acting early is corruption of customer databases. That is much worse than waiting for the BMC check, which usually takes minutes. If the BMC says the host is off, you've lost almost nothing. If the host is alive, you've avoided an irreversible mistake.

## Corrective options (not yet authorized)

**Option A: fence, then evacuate.** Use this if the host is dead or confirmed isolated. Evacuation fixes the "host is gone" hypotheses.

1. **Fence the host** by powering it off via BMC, or isolate it at the switch port. Verify the power state afterwards. The approver is the on-call lead or incident commander. This step is state-changing, but it is what makes the later steps safe.
2. **Mark the service forced down** instead of waiting for the heartbeat timeout: `openstack compute service set --down cmp-0417 nova-compute`. This needs compute API microversion 2.11 or later. It is state-changing, so verify it for your release.
3. **Evacuate in priority order**, with the customer databases first, as agreed with their owners. Do it per instance or in small batches, not all 40 at once.
4. **Verify each instance** before moving on: ACTIVE on the new host, reachable, application healthy, and database consistent. Check the database logs for crash recovery.
5. **Stop conditions:** any evacuation error, or any sign the original host is still writing. Pause and investigate.

Before the batch, check that the other computes have capacity for about 40 VMs. Otherwise some will fail to schedule and you'll find out halfway through.

**Recovery path:** none for a duplicate-writer event. The fencing is what protects you. A failed evacuation can be retried.

**Option B: restart `nova-compute` or libvirt, or repair the network.** Use this if the VMs are running and only the agent or network is broken. It is much less disruptive, since customers' VMs never go down. The approver is the compute owner.

## When the host comes back

Keep it disabled and forced down. Starting it with the old VM definitions risks the two-copies problem again from the other side. The sequence is:

1. Check networking and storage.
2. Start `nova-compute`.
3. Confirm it cleaned up the evacuated instances.
4. Only then run `--up` and `--enable`, as separate approved steps.

## Verification before declaring recovery

- For each VM: ACTIVE on the new host, reachable, and application-level checks pass. For the databases, confirm replication or consistency.
- `cmp-0417` is still forced down and disabled until cleanup is confirmed.
- The other computes and agents are reporting normally.

## Questions I need answered

1. What does the BMC say about `cmp-0417`'s power state?
2. Is it just this host, or are other computes affected too?
3. What changed around 03:12, and has anyone already restarted or touched anything?
4. Who owns the decision to fence and evacuate, and who gives the priority order for the customer databases?
5. Which release are you on? I haven't verified the exact commands against it.

If you can't reach the BMC, the next safest option is switch-level isolation of the host. Don't skip fencing because the BMC is unreachable. Escalate to whoever can reach the hardware.

> Decision support only. State-changing steps above require approval by the accountable owner and should be executed under your change process.