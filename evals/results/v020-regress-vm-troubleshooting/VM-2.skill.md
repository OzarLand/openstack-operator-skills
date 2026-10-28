## Resource and scope
- **Symptom (reported):** new instances on one tenant network go `ACTIVE` but never get a DHCP lease. Cloud-init says there is no lease. This started this morning. Instances created last week still work.
- **Stack (reported):** Kolla-Ansible, ML2/OVS.
- **Scope (unknown):** I don't know yet whether this affects only this network or every DHCP network. That is the first thing to find out.

## Recommendation: don't delete and recreate the network or subnet yet
Nothing you've described points at the network or subnet objects. The pattern "old instances fine, new ones get no lease" is the signature of a DHCP agent that isn't serving the network. Existing instances keep working on their leases, and dnsmasq only answers ports the agent has written to its hosts file. Recreating the network would not fix an agent problem.

It would also be destructive:
- Every existing port, fixed IP and floating IP association on that network would be lost.
- Routers, security group associations and anything referencing the network would break.
- The working instances from last week would lose their network.
- You would destroy the evidence you need to find the real cause.

The hypothesis fits the lab-validated pattern (VM-NET-01: 2026.1, Kolla-Ansible 22.2.0, ML2/OVS). That lab did not exercise causes 2–4 below, and your release may differ. The checks below are read-only, so run them before deciding anything.

## Likely causes
| Cause | Distinguishing observation |
|---|---|
| 1. Every DHCP agent is down | No agent is alive, and every new instance on every DHCP network is affected |
| 2. This network has no live agent | Other agents are alive, but none of this network's agents are (`--network` filter), and only this network is affected |
| 3. The network's dnsmasq isn't running | The agent is alive, but there is no dnsmasq for the network ID or the agent log shows errors for it |
| 4. The subnet has `enable_dhcp=False` | It is a subnet setting, not an agent fault. Check whether someone changed it this morning |

## Next checks (all read-only)
1. `openstack network agent list --agent-type dhcp` shows whether agents are `Alive`. Dead agents show `XXX` or `False`.
2. `openstack network agent list --network <network>` shows which agents serve this network.
3. `openstack subnet show <subnet> -c enable_dhcp` rules out cause 4.
4. `openstack port list --network <network> --device-owner network:dhcp -c ID -c "Fixed IP Addresses" -c Status` shows the network's DHCP ports.
5. `openstack console log show <server-id> | grep -iE 'dhcp|lease|bound'` on a failing instance. You should see it soliciting a lease and no `bound` line.
6. On the network node (Kolla-Ansible):
   - `docker ps -a --filter name=neutron_dhcp_agent --format '{{.Names}} {{.Status}}'`
   - `systemctl status kolla-neutron_dhcp_agent-container.service`
   - `tail /var/log/kolla/neutron/neutron-dhcp-agent.log`
   - `ip netns list | grep qdhcp-<network-id>`
   
   The dnsmasq container can show `Up` while the agent is dead, so don't treat it as proof that DHCP is healthy.
7. Find out what changed this morning, such as a kolla-ansible deploy or reconfigure, a RabbitMQ restart, a node reboot or a disk-full condition. If RabbitMQ or messaging is implicated (agents flapping, `MessagingTimeout` in the logs), this is a platform issue and belongs under incident analysis.

Please redact credentials such as `transport_url` before pasting any logs.

## Fix options (not authorized, pending the checks)
- **Causes 1 and 2:** start the agent on each network node with `systemctl start kolla-neutron_dhcp_agent-container.service`.
  - *Risk:* low. In the lab, running instances lost 0 requests. If all agents were down, networks may be rescheduled to another host.
  - *Undo:* stop the unit, which reproduces the outage.
  - *Follow-up:* read the log to find out why the agent stopped, or it will happen again.
  - *Status:* [LAB-VALIDATED: VM-NET-02], 2026.1, Kolla-Ansible 22.2.0, ML2/OVS. Not run: outages longer than the lease time, DHCP agent HA.
- **Instances that failed to get a lease during the outage:** `openstack server reboot <id>`.
  - *Cost:* the guest is down for the reboot, so tell the owner first. Nothing on disk is lost.
  - *Why:* in the lab, CirrOS did not retry after the agent came back and got its lease at the next boot. Cloud-init behaviour is not tested.
  - *Status:* [LAB-VALIDATED: VM-NET-02], same scope as above.
- **Cause 3:** read the agent log for that network. Restarting the agent restarts dnsmasq. [DOCUMENTED-UNVERIFIED]
- **Cause 4:** re-enable DHCP on the subnet. [DOCUMENTED-UNVERIFIED]
- **Delete and recreate the network:** not recommended. It is irreversible and has a large blast radius. It would only be worth considering if the checks show the network's own Neutron records are corrupt, and even then it needs a named owner's approval.

## Verification
- `network agent list --agent-type dhcp` and `--network <network>` show the agents alive.
- Create a **new** test instance on the network. Its console log should show a lease and it should answer on its IP. Delete the test instance afterwards.
- Check that the previously stuck instances recover after a reboot.

## Gaps
- Whether other networks are affected.
- Your OpenStack release.
- What changed this morning.
- Whether DHCP agent HA is enabled.

Please send the output of checks 1–3, and tell your colleague to hold off until then.

> Decision support only. State-changing steps above require approval by the accountable owner and should be executed under your change process.