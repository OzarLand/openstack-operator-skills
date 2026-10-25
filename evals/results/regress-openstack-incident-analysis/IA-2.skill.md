**Yes, there's one blocking reason: confirm cmp-0417 is really off before evacuating anything.** Evacuate rebuilds each VM on another host and assumes the old copy is dead. Nothing you've shown me proves that.

## Situation
- **Lost:** about 40 VMs are unreachable, including customer databases.
- **Unknown:** what still works, and what changed around 03:12.
- **Observed:** nova-compute on cmp-0417 shows `down` since 03:12 (your report).
- **Assumption:** instance disks are on shared Ceph RBD.

## Why not evacuate yet
**Observed:** a `down` service means Nova missed heartbeats. **Hypothesis only:** the host and its VMs are dead. Several causes fit what you've told me:

| Cause | Old VMs still running? | Evacuate result |
|---|---|---|
| Host crashed or lost power | No | Safe |
| nova-compute crashed, or lost RabbitMQ/DB access, but libvirt/QEMU is up | **Yes** | Two copies of each VM |
| Host partitioned from the management network, but still reaching Ceph | **Yes** | Two copies |
| Host hung or in a kernel panic, may come back | Maybe | Possible split brain on recovery |

In the "still running" cases, the evacuated copy and the original both write to the same RBD images. For customer databases, that means corruption. Ceph exclusive locks and blocklisting can limit this, but don't rely on them as your fence. The VMs being unreachable doesn't rule it out: a data-plane or ToR switch problem could make them unreachable while they keep running and writing to Ceph.

## Do this first (read-only, a few minutes)
1. **Check power state out of band** (BMC/IPMI/Redfish `power status`). Is cmp-0417 actually off?
2. **If it's on, check whether it's isolated.** Can you ping or SSH to it? Look at switch port status for its management, tenant and storage links.
3. **Check Ceph for active clients.** Run `rbd status <pool>/<volume>` on a few of the affected VMs' images (find them via `openstack server show`). A live watcher from cmp-0417's IP means the VM is still running.
4. **Find out what changed around 03:12.** Look for a deploy, reboot, network change or config change, and check cmp-0417's BMC event log and the neighbouring hosts. If other hosts on the same rack or switch are affected, that points to the network, and evacuating won't help.

## If the host is alive
Fence it. Power it off through the BMC (`state-changing`). Only a human with authority should do this, because it is also a hard stop for any VMs still running. Then wait for it to be confirmed off.

## Once it's confirmed off or fenced
Evacuating is reasonable. Do it deliberately, not as a blast of 40 at once:
- **Order by criticality.** Do the customer databases first, and ask their owners about priority. Then do the rest in batches.
- **Check capacity first.** Do the other hosts have the room for roughly 40 VMs, and for any special flavors, NUMA/pinning or AZ constraints? Check the scheduler won't just push most of them to ERROR.
- **Mark the service down explicitly** if your release needs it (`openstack compute service set --down` or a forced-down flag; verify for your release).
- **Do a small batch first.** Evacuate 2–3 VMs, including one DB. Check they boot and the DB comes up cleanly (crash recovery will run on the DB), then proceed.
- **Stop if** VMs go to ERROR, Ceph or the scheduler shows strain, or any DB doesn't recover cleanly.
- **Recovery:** evacuate is not easily reversible. Keep cmp-0417 fenced until it's cleaned up, and don't power it back on with its old VMs still defined on it (clean up the stale domains first).

## Verification
Per VM: `ACTIVE` on the new host, the service reachable from the customer's side, and for DBs the application-level check from their owner. Platform: no VM running on two hosts (compare libvirt domain lists), and the old host stays fenced until investigated.

## Open questions
- Is the BMC power state known?
- What changed around 03:12?
- Who has authority to approve fencing and mass evacuation? Name them.
- Is it a single host, or are its rack-mates also affected?

> Decision support only. State-changing steps above require approval by the accountable owner and should be executed under your change process.

If you paste the BMC output and the `rbd status` results, I can help tell which case you're in.