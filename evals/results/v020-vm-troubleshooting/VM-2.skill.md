**Don't delete and recreate the network or subnet yet.** The evidence points to the DHCP agent, not the network.

**Why**
- Instances from last week still work and new ones don't. That pattern fits "nothing is answering new DHCP requests". Old instances keep their leases, so they look healthy.
- A broken network or subnet definition would be a surprising cause. Deleting it is irreversible, so it shouldn't be the first move.
- Deleting the network is blocked while ports exist on it. Forcing past that means deleting every port, including the working instances' ports, the router interface, and any floating IP associations. You'd cause a bigger outage than the one you have.
- Recreating the network would also change its ID and its subnet and IP allocations, and the new network could break in the same way if the cause is the agent.
- The most likely cause in your setup (ML2/OVS) is that no DHCP agent is alive for that network. A second possibility is that the agent is up but its dnsmasq for that network isn't running. The least likely is `enable_dhcp=False` on the subnet.
- A DHCP agent can be down while the `qdhcp-` dnsmasq container still shows `Up`. That is why it looks fine from the outside.
- I haven't seen any of your output, so this is a hypothesis. It does match a documented lab pattern (2026.1, Kolla-Ansible, ML2/OVS). That lab did not cover the checks for causes 2–4, so treat those as untested.

**Read-only checks, in this order** (none of them change anything)
1. `openstack network agent list --agent-type dhcp`
   - If every agent shows dead, that's cause 1.
2. `openstack network agent list --network <network>`
   - If some agents are alive but none serve this network, that's cause 2.
3. `openstack subnet show <subnet> -c enable_dhcp -c allocation_pools`
4. `openstack port list --network <network> --device-owner network:dhcp -c "Fixed IP Addresses" -c Status`
5. On the network nodes:
   - `docker ps -a --filter name=neutron_dhcp_agent --format '{{.Names}} {{.Status}}'`
   - `tail /var/log/kolla/neutron/neutron-dhcp-agent.log`
   - `systemctl status kolla-neutron_dhcp_agent-container.service`
6. `openstack console log show <new-server-id> | grep -iE 'dhcp|lease|bound'`
   - You should see the DHCP request going out with no lease coming back.

Then check what changed this morning, because that is probably the root cause:
- Did anyone run a `kolla-ansible deploy` or `reconfigure`?
- Did anyone reboot a network node?
- Is a disk full, or is RabbitMQ unhealthy?
- Is the problem only on this network, or on every network?
- If it's every network, this is an incident. Switch to incident analysis, because RabbitMQ and the Neutron server would then be suspects.

**Likely fix if cause 1 or 2 is confirmed** (state-changing, needs your owner's approval)
- Start the agent on each affected network node with `systemctl start kolla-neutron_dhcp_agent-container.service`.
- Read the log first to see why it stopped. Otherwise it may stop again.
- Risk is low, and you can undo it by stopping the unit. Running instances lost no traffic in the lab, but that lab was all-in-one and multinode, not a production scale.
- With several agents all down, networks may get rescheduled to another host.

For the instances already created this morning, the lease request has already failed. Reboot them with `openstack server reboot <id>` once the agent is back, and tell the owners first. In the lab, CirrOS didn't retry on its own after the agent returned. Other images may differ, and I haven't verified cloud-init images.

If the agent log shows an error for this network specifically, paste it with passwords and credentials removed. If the agent is alive and dnsmasq is running, we'd look next at the OVS side: tags, flows, and whether the port binding is `ovs`. Rebuilding the network is a last resort, and only after a backup and an explicit decision by whoever owns that tenant.

Decision support only. State-changing steps above require approval by the accountable owner and should be executed under your change process.