## Short answer

Yes, there is one hard reason to stop. **Don't evacuate until `cmp-0417` is confirmed powered off or fenced.** "nova-compute down" only means the heartbeat stopped. It doesn't mean the host is dead.

If the host is alive but isolated (network partition, hung or crashed `nova-compute`, bad RabbitMQ connection), the 40 VMs may still be running on it. Evacuating then starts a second copy of each VM on another host, using the same Ceph RBD images. Two guests writing to one disk will corrupt it. Your customer databases are the VMs most likely to be damaged, and corruption can't be undone. Ceph doesn't prevent this on its own. Cephx and RBD exclusive locks are not a substitute for fencing, and I can't confirm they would protect you here. Please verify that for your setup.

I haven't inspected anything. Everything below is from your message or flagged as unknown.

## Situation
- **Capability lost:** about 40 VMs are unreachable, including customer databases. Customers are affected now.
- **Timeline:** `nova-compute` has been down since 03:12.
- **Not yet known:** whether the VMs are down or only unreachable. Also unknown: what changed around 03:12, whether other services on the host are affected, and whether the on-call already did anything.

## Evidence

| # | Class | Statement |
|---|---|---|
| 1 | Observed (by you) | `nova-compute` on cmp-0417 is "down" in `openstack compute service list`, since 03:12 |
| 2 | Reported | About 40 VMs are unreachable |
| 3 | Assumption | Instance disks are Ceph-backed for every affected VM (including boot disks and ephemeral) |
| 4 | Hypothesis | The host is dead (power, kernel panic, hardware) |
| 5 | Hypothesis | The host is up but cut off from the control plane (network or bond, RabbitMQ, a hung agent) |
| 6 | Hypothesis | The host is up and the VMs are running, but their tenant or data-plane network is broken |

Hypotheses 5 and 6 produce the same "down" and "unreachable" symptoms as 4, but they're the cases where evacuation causes damage.

## Next diagnostics (all read-only, about 5 minutes)
1. **Out-of-band power state.** Check BMC, IPMI or Redfish for cmp-0417, for example `ipmitool -I lanplus -H <bmc> chassis power status`. This is the main check. Also look at the BMC event log for a 03:12 event.
2. **Is the host reachable?** Ping it and SSH to it on the management network, and check the switch port and bond state. If it answers, it isn't dead.
3. **Is `nova-compute` the only thing down?** If you can SSH in, run `systemctl status nova-compute` and `virsh list`. Running VMs in `virsh` confirm hypothesis 5 or 6, and you must not evacuate.
4. **Check a few instance IPs from outside** to see whether they're totally dead or only partly unreachable.
5. **Check the other computes.** If several show as down, suspect RabbitMQ or a network problem before suspecting this host. In that case don't evacuate anything.
6. **Check Ceph for stale watchers.** `rbd status <pool>/<image>` on a few of the affected disks shows whether a client on cmp-0417 still holds them open. A live watcher means the guest is likely still running.
7. **Ask what changed around 03:12.** Look at deploys, switch work, kernel or package updates, and power or PDU events.

## Protect decision
Waiting 5–10 minutes for the BMC check doesn't make the platform state worse. It only extends an outage that has already lasted hours. Evacuating blind is the one move that can turn an outage into data loss. So start the diagnostics now, and in parallel get the fencing path ready.

## Corrective option (not yet authorized): fence, then evacuate
- **Prerequisites:**
  - The host is confirmed off via BMC, **or** you force it off via BMC (`chassis power off`), **or** you isolate its ports at the switch.
  - A named person approves. For databases that means whoever owns customer impact on call.
  - Target hosts have capacity. Check Placement, because 40 VMs landing at once can exhaust a cluster.
- **Blast radius:** the VMs on cmp-0417 only, but they restart cold. Databases will do crash recovery, and unflushed writes are lost either way.
- **Execution:**
  - Do it in small batches, not all 40 at once. Evacuate a non-critical VM first as a canary, then the rest.
  - This limits scheduler and Ceph load, and lets you catch a problem before it hits every VM.
- **Stop if:**
  - Any evacuated VM goes to ERROR.
  - The BMC shows the host powered on after you fenced it.
  - The target hosts run short of capacity.
- **Recovery:** if the original host comes back, don't let its VMs auto-resume. Disable `resume_guests_state_on_host_boot` and clean up stale domains on the source before re-enabling the node. Check this setting for your release and deployment.
- **Approver:** the incident commander or service owner, not just the on-call engineer.

## Verification before calling it recovered
- Each evacuated VM is ACTIVE on its new host, and `virsh list` on the old host (once reachable) shows no copies of it.
- Each customer database accepts connections and passes its own consistency or replication check. A VM showing ACTIVE doesn't prove the data is intact.
- Compute services report up and Placement allocations moved. Check for leftover allocations against cmp-0417.

## Gaps
- Is the disk backend Ceph for all 40 VMs, including volumes and ephemeral disks? Any local-disk VMs can't be evacuated that way.
- What is the cause of the 03:12 failure? Evacuating restores service but doesn't answer this. If it was a network or RabbitMQ fault, it can recur on other hosts.
- Which of the 40 VMs are customer databases? Prioritise those, and tell their owners they may restart with crash recovery.

## Bottom line for the on-call
Yes, evacuate, but fence first. If the BMC says the host is off, go ahead with the approved, batched evacuation. If the host is on, find out why before touching the VMs, and force it off via BMC if you decide it must be fenced. Either path should take minutes, not hours.

> Decision support only. State-changing steps above require approval by the accountable owner and should be executed under your change process.