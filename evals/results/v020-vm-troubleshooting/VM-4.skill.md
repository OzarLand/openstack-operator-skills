**Short answer: no. For ML2/OVN, the OVN-specific procedure I'd give you has never been run anywhere. I haven't tested anything myself, and I can't see your environment.**

The skill I loaded for this has a validation tag on each step. This is what they say about your case.

| Part of the procedure | Status | What it rests on |
|---|---|---|
| Recognizing the failure and the read-only checks (`port show`, `network agent list --host`, grepping the neutron-server and nova logs) | Lab-validated (VM-NET-11), **ML2/OVS only** | 2026.1, Kolla-Ansible 22.2.0, 3 controllers and 2 computes. The tag says "not run: every ML2/OVN step". |
| Restarting a dead agent, or fixing a host-name mismatch on the Neutron side | Lab-validated (VM-NET-12), **ML2/OVS only** | Same lab. It does not cover `docker restart` or the `Any:` commands (the generic ones for non-Kolla deployments). |
| **ML2/OVN causes**: no OVN chassis for the host, missing bridge mapping, chassis name differing from Nova's host name | **Documented-unverified (VM-NET-14)** | From documentation and source code. There is no execution evidence. |
| The OVN fix (`openvswitch_hostname` in `host_vars`, then `kolla-ansible reconfigure --tags openvswitch,ovn-controller --limit <compute>`) | **Documented-unverified (VM-NET-14)** | The restart time of `kolla-ovn_controller` was "not measured". The skill also notes there is no automatic rebind on OVN. |
| Bridge-mapping fix (`neutron_bridge_name`, `neutron_physical_networks` and so on) | Documented-unverified (VM-NET-13) | Not executed. |

- **Your platform is ML2/OVN, so the lab evidence doesn't carry over.** Release 2026.1 matches, but the lab used ML2/OVS. I won't present the OVS results as covering OVN.
- **Production scale is untested.** The lab was small. No tag in the skill covers real load or your topology.
- **Some fixes cut the data plane.** The OVN name fix restarts `openvswitch_vswitchd`. Every instance on that compute can briefly lose network. It needs a maintenance window, or the instances moved off first.
- **I can't tell which cause you have.** You've told me nothing yet beyond "binding failed on two computes". I can't say which cause applies, or whether a fix is needed at all.

**What is safe to do now.** The read-only checks are low-risk, and they show which cause you have before anything is changed. Please run these and paste the output, with credentials redacted:

1. `openstack port show <port-id> -c binding_host_id -c binding_vif_type -c binding_vnic_type -c network_id`
2. `openstack network show <network-id> -c provider:network_type -c provider:physical_network`
3. `openstack compute service list --service nova-compute -c Host -c Status -c State`
4. `openstack network agent list --host <compute>`. On OVN this should show an OVN controller agent for each compute.
5. `sudo docker exec ovn_sb_db ovn-sbctl --no-leader-only --columns=name,hostname list Chassis`. Compare the chassis names with the host names from check 3.
6. `sudo grep <port-id> /var/log/kolla/neutron/neutron-server.log | grep -iE 'bind|refusing'`. The line should say "no OVN chassis for host", "not supporting physical network", or a dead agent.

I'd also like to know:
- Do other computes bind ports fine?
- Did anything change on those two computes recently, such as a rename, reinstall, reboot or reconfigure?
- Are the builds failing for all networks, or only some?

If the checks point to a name mismatch or a missing chassis, I'll give you the fix with its undo and stop conditions. I'll label it as untested on OVN so your change approver knows what they're signing off. If both computes were recently reconfigured, I'd also check whether the ovn-controller container is running before anything else.