No, nothing I'd give you is tested. I haven't run any of it, on any system. I have no access to your cloud in this session, and I haven't stood up a 2026.1 ML2/OVN lab to try anything. What I'd give you is general knowledge of how Neutron/OVN binding failures usually go, not a verified procedure. I also can't confirm that 2026.1 behaves the way older releases do.

**Read-only checks that are safe to run before changing anything**

These only read state, and I'd expect them to be harmless. Check each command against `--help` on your release first.

1. **Is the OVN agent on the two bad computes alive?**
   `openstack network agent list --host <compute>` should show `OVN Controller agent` (and metadata agent) as alive. A dead or missing agent is the most common cause of binding failures with ML2/OVN, because the mechanism driver only binds ports on hosts with a live agent.
2. **Do the chassis exist in the southbound DB?**
   `ovn-sbctl list chassis` (or `ovn-sbctl show`). Check that the two hosts appear, with the hostnames Neutron expects.
3. **Do the bridge mappings match?**
   On the good and bad computes, compare `ovs-vsctl get open . external_ids:ovn-bridge-mappings`. A missing physnet mapping gives exactly "Binding failed" for provider or flat networks.
4. **What does the Neutron log say?**
   Grep neutron-server for the failed port ID. The ML2 driver usually logs why it rejected each candidate host, for example "no agent", "segment not supported", or "physnet not found".
5. **Is nova-compute healthy on those hosts?**
   Check `openstack compute service list` for state and version skew.
6. **Local OVS/OVN connection.**
   On the compute, check `ovs-vsctl get open . external_ids:ovn-remote` and that `ovn-controller` is running and connected.

**What I'd hold off on**

I'd avoid restarting services, deleting chassis records, or re-registering agents until the logs point to a cause. Those steps can disrupt running instances, and I can't tell you they're safe on your deployment.

If you paste the neutron-server log lines for a failed port and the agent list output, I can narrow it down. I'd still call anything I suggest a hypothesis until you've tried it on a non-production host or a lab.