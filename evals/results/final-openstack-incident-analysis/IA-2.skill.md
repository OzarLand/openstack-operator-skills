## Short answer

Yes, there is one reason not to run it yet: **fence the host first.** Evacuation is safe only once cmp-0417 is confirmed dead or isolated. A "down" nova-compute service doesn't prove that.

**Why this matters here:** "down" only means nova-compute has stopped sending heartbeats. Nova can't tell a dead host from one that is alive but cut off from the control plane. That could be a stuck nova-compute process, a management-network or RabbitMQ problem on that host, or a hung agent. In those cases the VMs may still be running on cmp-0417 and still holding their Ceph RBD images.

If you evacuate while the originals are alive, you get two copies of each VM writing to the same RBD volumes. Ceph doesn't stop that unless exclusive locks and blacklisting are enforced, and you shouldn't assume they are. For the customer databases, that means silent corruption, which is far worse than the current outage. Evacuation can't be undone once the second copy starts writing.

"Ceph makes evacuate quick" is true. It makes the move fast, but it also makes a double-write easy.

## What to do now (all read-only unless noted)

1. **Check power state out-of-band.** Use IPMI/iDRAC/iLO/BMC on cmp-0417, for example `ipmitool -I lanplus -H <bmc> chassis power status`. This is the main check.
   - **Powered off or hardware-dead:** the host is confirmed down. Go to step 4.
   - **Powered on:** do not evacuate yet. Go to step 2.
2. **Find out whether the VMs are still running.** Look at the console or BMC, ping the host on its management and tenant networks, or check from Ceph whether the RBD images still have watchers: `rbd status <pool>/<image>`. A live watcher means a client is still attached.
3. **If the host is alive but isolated, fence it.** Power it off through the BMC or isolate its switch ports. This is **state-changing** and needs a named approver. Before you do it, ask whether the customer databases would rather be fixed in place. If a quick fix is possible, such as restarting nova-compute, fixing a network problem or fixing a hung process, it would avoid the evacuation and the data risk altogether.
4. **Only after fencing is confirmed**, evacuate in priority order rather than all 40 at once:
   - Start with a few non-critical VMs to confirm the destination hosts, networking and Ceph access work.
   - Then do the customer databases, with their owners' input on the order. Nova can't tell which VMs matter most.
   - Check destination capacity first (`openstack hypervisor stats show`, Placement). Sending 40 VMs at the scheduler without checking can leave many in ERROR.
   - Run `openstack server evacuate`, or use `nova host-evacuate` if your client supports it, on a few at a time. Check each batch before the next.

## What I need from you (gaps)

- **Observed:** nova-compute on cmp-0417 is down since 03:12 (from your message). Nothing else has been shown to me.
- **Reported, not shown:** about 40 VMs are unreachable, and instance disks are on Ceph.
- **Unknown:**
  - the host's BMC power state
  - whether anything changed around 03:12 (a deploy, maintenance, a network change, RabbitMQ issues)
  - whether other computes are also affected, which would point at the shared bus or network rather than this host
  - the Ceph configuration (exclusive-lock and blocklisting behaviour)
  - spare capacity
  - the release and tooling

Whether other computes are affected is worth one minute to check. If several hosts show "down" together, the cause is probably RabbitMQ or the network. In that case evacuating is wrong and could make things much worse.

## Verification after evacuation

For each VM, check that it is ACTIVE on the new host, reachable, and that its application (for databases, the engine and its data) is healthy. Check that cmp-0417 no longer runs any of these VMs. Once the host is repaired, clean up the old domains before it rejoins, so they don't start again next to the evacuated copies.

If the BMC says the host is off, the delay is a few minutes. If the BMC says it's on, those minutes are what keeps the customer data safe.

> Decision support only. State-changing steps above (fencing, evacuation) require approval by the accountable owner and should be executed under your change process.