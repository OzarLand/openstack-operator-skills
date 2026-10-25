## Short answer

Yes, there is a reason not to. Don't run evacuate on a "down" service alone. First confirm the host is actually off. Evacuation is still probably the right recovery, so this is a delay of minutes, not a change of plan.

## Situation

- **Capability lost:** the VMs on cmp-0417 are unreachable, including some customer databases.
- **Unknown:** I don't know if the host is dead or only cut off from the control plane. That is the question that decides whether evacuate is safe.
- **What changed:** you haven't said, so please tell me. Candidates are maintenance, network or switch work, a RabbitMQ event or a kernel panic around 03:12.

## Why not right now

`nova-compute` down at 03:12 only means the heartbeat stopped. It could be:

- **Host dead or powered off.** Evacuate is safe.
- **Host alive but isolated from RabbitMQ or the management network, or `nova-compute` crashed.** The VMs may still be running, and some of that "unreachable" may be a data-plane or network problem, not a dead host. If you evacuate, Nova rebuilds each VM on another host from the same Ceph disks, so two copies of the same VM can write to the same RBD image. For the customer databases, that risks corruption you can't undo.

Ceph does not protect you here. Shared storage is what makes evacuate fast, and it's also what lets two copies write to the same disk. The protection is Ceph's RBD exclusive lock, but don't rely on it as your fence. It depends on your config and on the old host's client being blacklisted or timed out, which I haven't seen.

## Do this, in order

1. **Fence.** Check the power state through the BMC (IPMI or Redfish). If the host is alive but unreachable, power it off through the BMC, or isolate it at the switch. `read-only` for the check, `state-changing` for the power-off. The on-call must own the decision to power off a host that is still running.
2. **Mark the service forced down.** Use `openstack compute service set --down cmp-0417 nova-compute`, which needs compute API microversion 2.11 or later. This is `state-changing`. Verify the command for your release.
3. **Evacuate in priority order, not all 40 at once.** Start with the customer databases. Ask their owners for the order, because the infrastructure can't know which VMs matter most. Check capacity first with `openstack hypervisor stats show` or Placement, so 40 evacuations don't fail on the scheduler. Verify each VM before moving on: ACTIVE on the new host, reachable, and the database consistent. Run a few first, and stop if any fail or show an error. Expect a database that was cut off mid-write to need crash recovery.
4. **Keep the host down when it returns.** Leave it disabled and forced down until `nova-compute` has cleaned up the evacuated instances' local copies. Then bring it back with `--up` and `--enable` as two separate approved steps. If it returns early, you recreate the two-copies risk.

Evacuation is for failed hosts only. If the host turns out to be fine, the fix is to repair the connection.

## Quick read-only checks, in parallel with fencing

- BMC power state and console or SEL logs for cmp-0417.
- Can you reach the host over the management network, and is `nova-compute` or libvirt still running if you can log in?
- Check whether the VMs are alive: `rbd status` on a few disks shows whether a watcher is still attached, and the customers' own monitoring may show it too.
- Check whether other hosts also lost heartbeats around 03:12. That would point to RabbitMQ or the network, not this host. `rabbitmqctl cluster_status` is read-only.
- `openstack server list --host cmp-0417 --all-projects` for the exact list, and note the count so you can compare later.

## Gaps I need answered

- Is the BMC reachable, and what does it say?
- What happened around 03:12?
- Who has authority to approve the fence, and who talks to the customers?
- Is spare capacity enough for 40 VMs?
- Does your Ceph config enforce exclusive locks?

## Verification before declaring recovery

- Each VM is ACTIVE on its new host, reachable, and its application-level check passes. For the databases, replication or consistency is confirmed with the owners.
- Nothing is left on cmp-0417 in the Nova records.
- The root cause of the 03:12 failure is identified. Evacuation contains the incident but doesn't explain it, and if the cause is a bad switch or kernel bug, other hosts may be next.

> Decision support only. State-changing steps above require approval by the accountable owner and should be executed under your change process.

If you paste the BMC status and the 03:12 context (with any credentials redacted), I can narrow this down quickly.