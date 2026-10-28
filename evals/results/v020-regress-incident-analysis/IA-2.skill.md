## Short answer

Yes, there's a reason to wait. **Don't evacuate until the host is fenced.** A "down" nova-compute only means the heartbeat stopped. It doesn't mean the host is off. Nova can't tell a dead host from one that is isolated from the control plane or has a hung `nova-compute` agent. If cmp-0417 is still running, evacuating starts a second copy of each VM on another host, and both copies write to the same Ceph RBD images. For the customer databases that means corruption, which is much worse than the current outage. [Book: Ch. 10, P3]

Fencing is usually quick, so this shouldn't cost you much time.

## Situation

- **Capability lost:** about 40 VMs on cmp-0417 are unreachable, including customer databases.
- **Evidence:** Observed (your output): `nova-compute` on cmp-0417 is "down" since 03:12.
- **Reported:** the VMs are unreachable, and instance disks are on Ceph.
- **Assumption:** I'm assuming that's Ceph RBD for every VM, including the databases. Boot-from-volume VMs and any with local ephemeral disks behave differently.
- **Unknown:** what changed around 03:12, whether any other hosts are affected, and what has already been tried.

## Before anyone evacuates

1. **Fence the host.** This step is `DOCUMENTED-UNVERIFIED` here and state-changing.
   - Check the power state through BMC/IPMI/Redfish, or isolate the host at the switch.
   - If the host is up but cut off from the control plane, power it off. Powering off is the fence. Don't just trust that it's dead.
   - If it's still running and the VMs are still serving some clients, decide that deliberately with the owners.
2. **Mark the service forced down** (state-changing). This is better than waiting for the heartbeat timeout:
   `openstack compute service set --down cmp-0417 nova-compute`
   This needs compute API microversion 2.11 or later. Verify it for your release.
3. **Evacuate in priority order, not all 40 at once.**
   - Start with the customer databases, in the order their owners agree on.
   - Run a first batch of 2–3 and check each one: ACTIVE on the new host, reachable, application healthy.
   - Then continue. Evacuating in batches also limits the load on the scheduler and on Ceph.
   - On microversion 2.95 or later, evacuated instances come up stopped and you must start them.
4. **Check the state of the Ceph locks before you start.** If the host is truly fenced, stale RBD watchers or locks should be gone or expire. If you see live watchers on the images, the host is not really dead.

## Read-only checks to run now

| Check | What it tells you |
|---|---|
| BMC/Redfish power state of cmp-0417 | Whether the host is really off. This is the key check. |
| Ping, SSH and console on cmp-0417 | Whether the host is up but isolated. |
| `openstack compute service list` for all hosts | Whether this is one host or a wider control-plane problem such as RabbitMQ. If many hosts show down, evacuating is the wrong move. |
| `openstack server list --host cmp-0417 --all-projects` | The real VM list, to share with owners for ordering. |
| `rbd status <pool>/<image>` on a few critical VMs | Whether anything still holds a watcher on the image. |
| Nova-compute, libvirt and kernel logs on the host, if reachable | Why it went down at 03:12. |
| Recent changes (deploys, network, kernel, hardware alerts) | The likely cause. |

## Hypotheses

- **Host crashed or powered off.** The check is BMC power state and console. This is the safe case: fence is trivial, then evacuate.
- **Host is alive but isolated from the control plane.** The check is whether the VMs answer on the data network. This is the dangerous case, and evacuation here causes split-brain.
- **nova-compute or its message-bus connection is broken, while VMs run fine.** The check is `virsh list` on the host. Restarting `nova-compute` may be enough, and no evacuation is needed.
- **Wider control-plane problem such as RabbitMQ.** The check is the compute service list for other hosts. If it's present, fix that first.

If the VMs are unreachable, the second case is less likely, but not ruled out. A network or switch fault could cause both.

## When the host comes back

Keep it disabled and forced down. On start, `nova-compute` removes the local copies of the instances that were evacuated. Confirm it has done that before you run `--up` and `--enable`, as separate approved steps. Bringing it back earlier recreates the two-copies risk from the other end. This sequence was `LAB-VALIDATED` for 2026.1, Kolla-Ansible, ML2/OVS and local disks. It was not run with Ceph, IPMI fencing or batches.

## Verification

For each evacuated VM, check that it is on the new host and ACTIVE, reachable, and has its network ports bound. For the databases, also check application-level health (replication state, consistency, client connections). After the batch, check that cmp-0417 has no RBD watchers and that the other compute services are healthy.

## Open questions for the on-call

- Who has authority to approve the fence and the evacuation?
- Which VMs matter most, and who owns the databases? Ask the owners; infrastructure can't infer this.
- Is cmp-0417 powered off or isolated? The BMC will tell you in under a minute.
- What changed around 03:12?

If you paste the BMC power state and the compute service list, I can narrow this down and draft the batch order. Please redact any credentials from the output.

> Decision support only. State-changing steps above require approval by the accountable owner and should be executed under your change process.