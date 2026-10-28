I'd advise against deleting and recreating the network and subnet. It probably won't fix this, and it's destructive.

- **Delete is blocked or destructive.** Neutron won't delete a network while it has ports. You'd have to remove or detach every instance port first, and the new network would get new IDs, new ports and possibly new IPs. Floating IPs, routers, security-group references and anything in Terraform or Heat would break.
- **The cause is probably not the network object.** Last week's instances work and new ones don't, so the network and subnet definitions were fine until this morning. Something changed in the DHCP path, which is usually the DHCP agent, dnsmasq, or the OVS flows or ports. Recreating the network just re-runs the same broken machinery.
- **Existing instances are at risk too.** If DHCP is down, they will fail to renew their leases when those expire. This is urgent even though they look fine now.

**Triage, in order**

1. **Is the DHCP agent alive and hosting this network?**
   ```
   openstack network agent list --agent-type dhcp
   openstack network agent list --network <net-id>
   openstack port list --network <net-id> --device-owner network:dhcp
   ```
   Look for a dead agent (`XXX`), no agent hosting the network, or no DHCP port.

2. **Does the new instance's port look right?**
   ```
   openstack port show <port-id>   # status, binding:host_id, binding:vif_type, binding_failed?
   ```
   A port that is DOWN or has `binding_failed` points at the OVS agent on the compute node. Check `openstack network agent list --host <compute>` too.

3. **Check the logs** with `docker logs`, or look in `/var/log/kolla/neutron/`:
   - On the network node, check `neutron-dhcp-agent.log` for RPC or RabbitMQ errors and for dnsmasq spawn failures.
   - On the compute node, check `neutron-openvswitch-agent.log` for errors, a stuck resync, or "Agent out of sync".
   - On RabbitMQ, a partition or queue backlog would explain a "since this morning" start.

4. **Check the data path.**
   ```
   docker exec openvswitch_vswitchd ovs-vsctl show           # is the tap on br-int, with the correct tag?
   docker exec openvswitch_vswitchd ovs-ofctl dump-flows br-int | grep -i 'tp_dst=67'
   ip netns exec qdhcp-<net-id> ip a                          # on the network node; does the tap have the DHCP IP?
   ```
   Then run `tcpdump -ni any port 67 or port 68` in the qdhcp namespace and on the compute node's tap. This shows whether the DISCOVER arrives and whether an OFFER leaves.

5. **Find out what changed this morning.** Did anyone run `kolla-ansible deploy` or reconfigure, or upgrade or restart containers? Did a host reboot, a disk fill up, the clock drift, or a security-group or port-security change land? Compare `docker ps` uptimes across the nodes.

**Likely fixes, from least to most invasive**

- Restart `neutron_dhcp_agent` and `neutron_openvswitch_agent` on the affected nodes.
- Reschedule the network to a healthy agent with `openstack network agent add network --dhcp <agent-id> <net-id>`.
- Fix RabbitMQ if it is the cause.
- If the DHCP port or namespace is corrupt, remove the agent binding and re-add it. That is much less invasive than recreating the network.

If you paste the output of steps 1, 2 and the relevant log excerpts, I can narrow it down. I don't have access to your cluster from here, so I can't run these myself.