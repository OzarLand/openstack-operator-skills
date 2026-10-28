# Instance networking

Instances that are `ACTIVE` but have no address, no metadata, no path from
outside, a port that will not bind, a security group that does nothing, a
compute whose data plane is down, a tunnel MTU that drops large packets, a
router frozen on a dead L3 agent, and what restarting the Open vSwitch agent
does. Everything in this file is an [Addition] to the book, distilled from
OzarLand `openstack-vm-runbooks` (`networking/`) at commit `babdd8c07971`.

Validation tags follow rule 12 of evidence-and-safety.md: untagged text is
unverified. Lab evidence is OpenStack 2026.1, Kolla-Ansible 22.2.0, ML2/OVS
(VXLAN), Docker, Ubuntu 24.04, CirrOS test instances unless a tag says
otherwise. Nothing here was run on OVN, another release or another deployment
tool. Kolla-Ansible 2026.1 runs containers as systemd units
(`kolla-<container>-container.service`): use `systemctl`, not `docker restart`.

## Contents

- No IP address
- No metadata
- Unreachable from outside
- Port binding failed
- Security group rules not applied
- ovs-vswitchd down
- Tunnel MTU mismatch
- Router on a dead L3 agent
- Restarting the OVS agent

---

## No IP address

No DHCP agent is alive to add the new port to dnsmasq, so the instance's DHCP
request is never answered. Instances created earlier keep their lease.

**Recognize.** New instance `ACTIVE`, running, no fault, no answer on its fixed
or floating IP. Earlier instances work. The console shows the DHCP client asking
and no `leased` / `bound` line (CirrOS printed `soliciting a DHCP lease`;
wording depends on the image). Nova has nothing to find. The `qdhcp-` namespace
and its dnsmasq (with Kolla-Ansible's default `neutron_agents_wrappers`, the
containers `neutron_dhcp_agent_dnsmasq_qdhcp-<network-id>` and
`..._haproxy_qdhcp-<network-id>`) can stay `Up` while the agent is down: dnsmasq
only answers ports the agent wrote to its hosts file.

[LAB-VALIDATED: VM-NET-01] Recognition and the read-only checks below, cause 1.
Lab: 2026.1, Kolla-Ansible 22.2.0, ML2/OVS VXLAN, multinode (3 DHCP agents) and
all-in-one (1 agent); test instance `ACTIVE` in 13-15 s with no address. Not
run: the checks for causes 2 to 4, OVN (no DHCP agent there), cloud-init images.

**Read-only checks.**
- `openstack server show <server-id> -c status -c OS-EXT-STS:power_state -c fault -c addresses`
- `openstack console log show <server-id> | grep -iE 'dhcp|lease|bound'`
- `openstack network agent list --agent-type dhcp` (`Alive` `XXX` or `False`);
  `openstack network agent list --network <network>`;
  `openstack port list --network <network> --device-owner network:dhcp -c ID -c "Fixed IP Addresses" -c Status`
- On the network node: `ip netns list | grep qdhcp-<network-id>`; Kolla-Ansible:
  `docker ps -a --filter name=neutron_dhcp_agent --format '{{.Names}} {{.Status}}'`,
  `/var/log/kolla/neutron/neutron-dhcp-agent.log`,
  `systemctl status kolla-neutron_dhcp_agent-container.service`. Any:
  `journalctl -u neutron-dhcp-agent`.

**Tell the causes apart.**
| Observation | Points to |
|---|---|
| No DHCP agent alive at all; every new instance on every DHCP network | 1. every DHCP agent down |
| Some agents alive, but the network's agents (`--network`) dead or none | 2. network has no live agent; only that network |
| Network's agent alive, no dnsmasq for `<network-id>` or errors for it in the agent log | 3. dnsmasq of the network not running |
| `openstack subnet show <subnet> -c enable_dhcp` is `False` | 4. subnet does not use DHCP; not an agent fault |

**Fix options.**
1. Causes 1 and 2. *State-changing*: Kolla-Ansible, on each network node:
   `systemctl start kolla-neutron_dhcp_agent-container.service`; Any:
   `systemctl start neutron-dhcp-agent`. With several agents and all down,
   Neutron may reschedule networks: their `qdhcp-` namespaces can move to
   another host (observed: controller-2 to controller-3). Undo: stop the unit
   (reproduces the outage). Then read the log and unit status for why it stopped.
2. Instances created during the outage. *State-changing*:
   `openstack server reboot <server-id>`; the owner loses the guest for the
   boot, nothing on disk; tell the owner first. CirrOS had not retried 90 s
   after the agent came back and got its lease at the next boot.
   [LAB-VALIDATED: VM-NET-02] Fix options 1 and 2. Lab: 2026.1, Kolla-Ansible
   22.2.0, ML2/OVS; running instances lost 0 requests during 180 s and 7.5 min
   outages and the restart; agent alive 23 s after the start (all-in-one). Not
   run: an outage longer than the lease (`dhcp_lease_duration`, 86400 s by
   default), DHCP agent HA (`enable_neutron_agent_ha`), the `Any:` commands.
3. Cause 3: read the agent log for that network; restarting the agent makes it
   start dnsmasq again. Cause 4: enable DHCP on the subnet or address the
   instance another way (config drive, image).
   [DOCUMENTED-UNVERIFIED: VM-NET-03]

**Verify.** `openstack network agent list --agent-type dhcp` and `--network
<network>` alive; a test instance (`openstack server create ... dhcp-test`)
shows a lease in its console log and answers; delete it.

## No metadata

The first-boot request to `169.254.169.254` goes to a haproxy in the network's
`qdhcp-` namespace (Kolla-Ansible sets `force_metadata = true` for the DHCP
agent), then to the Neutron metadata agent, then to Nova's metadata API. With
every metadata agent down it goes nowhere; the image waits, then boots without
its instance ID, SSH key and user data, and stays that way after the outage.

**Recognize.** `ACTIVE`, has its address, no fault; SSH with the key fails,
user data did not run, default hostname. Earlier instances unaffected. CirrOS
console: `failed 1/20: up ... request failed` ... `failed 20/20: up ... request
failed`, `failed to read iid from metadata`; it waited about 3 minutes. With
cloud-init the data source is reported as not found (not observed on the lab).
Instances booted with a config drive do not use this path (Kolla-Ansible does
not force one).

[LAB-VALIDATED: VM-NET-04] Recognition and read-only checks below, cause 1.
Lab: 2026.1, Kolla-Ansible 22.2.0, ML2/OVS VXLAN, multinode (3 agents) and
all-in-one (1 agent), CirrOS, no config drive. Not run: causes 2 and 3,
cloud-init images, config drive, OVN (different metadata agent).

**Read-only checks.**
- `openstack server show <server-id> -c status -c addresses -c fault`
- `openstack console log show <server-id> | grep -iE 'metadata|169.254|iid|datasource'`
- `openstack network agent list --agent-type metadata`
- Kolla-Ansible, network node:
  `docker ps -a --filter name=neutron_metadata_agent --format '{{.Names}} {{.Status}}'`,
  `systemctl status kolla-neutron_metadata_agent-container.service`,
  `/var/log/kolla/neutron/neutron-metadata-agent.log`; controllers:
  `docker ps -a --filter name=nova_metadata ...` and the Nova metadata log under
  `/var/log/kolla/nova/`. Any: `journalctl -u neutron-metadata-agent`.

**Tell the causes apart.**
| Observation | Points to |
|---|---|
| No metadata agent alive | 1. every metadata agent down |
| Agents alive, their log shows errors calling Nova; `nova_metadata` down or failing | 2. Nova metadata API not answering |
| Network has no live DHCP agent (instance usually has no address either) | 3. see *No IP address* |

**Fix options.**
1. Cause 1. *State-changing*: Kolla-Ansible, each network node:
   `systemctl start kolla-neutron_metadata_agent-container.service`; Any:
   `systemctl start neutron-metadata-agent`. New instances get metadata again;
   instances already booted are not repaired. Undo: stop the unit.
2. Instances created during the outage. *State-changing*:
   `openstack server reboot <server-id>` (guest down for the boot, nothing lost
   on disk). Whether it is enough depends on the image: CirrOS reads the
   metadata at every boot; cloud-init images not tested.
   [LAB-VALIDATED: VM-NET-05] Fix options 1 and 2. Lab: 2026.1, Kolla-Ansible
   22.2.0, ML2/OVS, all-in-one, CirrOS 0.6.3: agent alive within 12 s of the
   start, running instances lost 0 of 1179 requests during a 5 min outage and
   the restart, the reboot restored key and instance ID. Not run: cloud-init
   images, config drive, the `Any:` commands; running instances were not
   measured on the multinode run.
3. Still missing after a reboot. *Destructive*:
   `openstack server rebuild --image <image> <server-id>` replaces the root
   disk with a fresh copy of the image: everything written since boot is lost;
   attached volumes kept. Only on instances created during the outage, after
   the owner confirmed nothing on the root disk matters, or after
   `openstack server image create <server-id>`. No undo without that snapshot.
   [LAB-VALIDATED: VM-NET-06] Lab: 2026.1, Kolla-Ansible 22.2.0, ML2/OVS,
   all-in-one, on a disposable CirrOS test instance; metadata came back. Not
   run: cloud-init images, instances with attached volumes, the snapshot step.
4. Cause 2: fix the Nova metadata API (containers, configuration, the shared
   secret with the metadata agent), then re-read the agent log.
   [DOCUMENTED-UNVERIFIED: VM-NET-07]

**Verify.** Agents alive; a test instance created with `--key-name <key>`
shows its instance ID in the console log, and SSH with the key works; delete it.

## Unreachable from outside

Address and metadata are fine, a neighbour in the tenant network reaches the
instance, nothing from outside does: `ssh: connect to host <floating-ip> port
22: Connection timed out` (a client on the external segment may see `No route
to host` when no router holds the floating IP). Usually one instance or
project; every floating IP failing at once points at a shared cause (check
*Router on a dead L3 agent* first on ML2/OVS, then the external network).

[LAB-VALIDATED: VM-NET-08] Recognition, quick checks and the ML2/OVS namespace
checks; Neutron's cause-3 refusals. Lab: 2026.1, Kolla-Ansible 22.2.0,
all-in-one, ML2/OVS with the L3 agent, legacy router, CirrOS. Not run: the
OVN check, DVR, L3 HA routers.

**Read-only checks, in order** (most cases end at 2 or 3).
1. `openstack port list --server <server-id> -c ID -c "Fixed IP Addresses"`;
   `openstack port show <port-id> -c fixed_ips -c security_group_ids -c port_security_enabled`
2. `openstack security group rule list --ingress <security-group-id>`: a rule
   for the protocol (`tcp` for SSH, `icmp` for ping), port and a remote prefix
   containing the client. A remote group admits only that group's members.
   `port_security_enabled: False` rules this cause out.
3. `openstack floating ip list --port <port-id>`
4. `openstack port list --network <tenant-network-id> --device-owner network:router_interface -f value -c ID`
   (HA or distributed routers use other owners: drop the filter if empty);
   `port show <port> -c device_id` gives the router;
   `openstack router show <router-id> -c external_gateway_info -c interfaces_info -c status`
5. `openstack network show <external-network-id> -c router:external -c status`
6. Only if the API looks right, ML2/OVS: `openstack network agent list --router
   <router-id> --long` (with L3 HA use the `active` node), then as root on that
   node: `sudo ip netns exec qrouter-<router-id> ip -brief addr` (floating IP
   on the `qg-` interface) and `sudo ip netns exec qrouter-<router-id> iptables
   -t nat -S | grep -F "<floating-ip>"` (DNAT to the fixed address). Without
   root: `Operation not permitted`.

**Tell the causes apart.**
| Observation | Points to |
|---|---|
| No ingress rule for protocol, port and source | 1. security group |
| No floating IP, or on another port / fixed address | 2. floating IP |
| No router interface or no gateway; association fails with `External network <network-id> is not reachable from subnet <subnet-id>` | 3. no router path (only possible before a floating IP is associated: Neutron also refuses, HTTP 409, to remove the interface or gateway a floating IP depends on) |
| API shows path and floating IP, but no address / NAT on the node | 4. router not on its node: *Router on a dead L3 agent* |
| All checks pass; a neighbour cannot connect either | 5. guest firewall or service; owner fixes it |
| Every floating IP affected, OpenStack looks right | 6. external network or upstream routing, outside OpenStack |

**Fix options.**
1. Cause 1. *State-changing*, opens every port using the group:
   `openstack security group rule create --ingress --protocol tcp --dst-port 22 --remote-ip <client-prefix> <security-group-id>`
   (and `--protocol icmp` for ping). Narrowest prefix; never `0.0.0.0/0` for
   administration ports unless the project accepts it. Rules are stateful.
   Undo: `openstack security group rule delete <rule-id>`.
2. Cause 2. *State-changing*, takes the floating IP from any other port:
   `openstack floating ip create <external-network-id>` if none is free, then
   `openstack floating ip set --port <port-id> [--fixed-ip-address <fixed-ip>] <floating-ip-id>`.
   Undo: set it back with `floating ip set --port`.
   [LAB-VALIDATED: VM-NET-09] Fix options 1 and 2. Lab: 2026.1, Kolla-Ansible
   22.2.0, all-in-one, ML2/OVS. Not run: OVN.
3. Cause 3. *State-changing*: `openstack router set --external-gateway
   <external-network-id> <router-id>` (gives every instance of the router SNAT,
   uses an external address), `openstack router add subnet <router-id>
   <tenant-subnet-id>`, then associate as in 2. Undo: `router unset
   --external-gateway`, `router remove subnet`. Causes 4 to 6, and on ML2/OVN
   the check `docker exec ovn_northd ovn-nbctl lr-nat-list neutron-<router-id>`
   (Kolla-Ansible; Any: `ovn-nbctl lr-nat-list ...`; a `dnat_and_snat` line for
   the floating IP; a clustered database may need `--db=<nb-connection>`).
   Repairing a missing OVN NAT entry is not covered.
   [DOCUMENTED-UNVERIFIED: VM-NET-10]

**Verify.** One floating IP on the right fixed address, the ingress rule
listed; from an allowed outside address `ping -c 3 <floating-ip>` and SSH work.

## Port binding failed

No ML2 mechanism driver could bind the port on the host Nova named, so
`binding:vif_type` becomes `binding_failed` and Nova raises `PortBindingFailed`.

**Recognize.** Neutron server: `Failed to bind port <port-id> on host
<compute> for vnic_type normal using segments [...]`. Nova: `Binding failed for
port <port-id>, please check neutron logs for more information.`
- Build: `ERROR`; in `nova-compute.log` of the compute that tried
  (`Instance failed network setup after 1 attempt(s)`) and in `openstack server
  event show`. A `--network` port is deleted; a pre-created `--port` stays,
  unbound (no `binding_host_id`, `binding_vif_type` `unbound`, `DOWN`).
- Live migration: refused at once. Client: HTTP 400 `No valid host was found.
  There are not enough hosts available.`; `nova-conductor.log`: `Binding failed
  for port <port-id> and host <compute>.`; instance stays `ACTIVE` on the
  source, port keeps its `ovs` binding there.
Running instances with bound ports keep their network.

[LAB-VALIDATED: VM-NET-11] Recognition, quick checks and the default-level
dead-agent line, ML2/OVS. Lab: 2026.1, Kolla-Ansible 22.2.0, multinode (3
controllers, 2 computes), Neutron server without `debug`; dead agent `Alive
False` 71 s after its unit stopped; 10 bind attempts in 0.4 s. Not run: the
debug-level lines, every ML2/OVN step.

**Read-only checks.**
- `openstack port show <port-id> -c binding_host_id -c binding_vif_type -c binding_vnic_type -c network_id`
- `openstack network show <network-id> -c provider:network_type -c provider:physical_network -c segments`
- `openstack network agent list --host <compute>` (present, alive, same name)
- Kolla-Ansible: `sudo grep <port-id> /var/log/kolla/neutron/neutron-server.log | grep -iE 'bind|refusing'`,
  and the same `grep` on `/var/log/kolla/nova/nova-conductor.log` (migration)
  or `nova-compute.log` (build). Any: the same logs.

**Tell the causes apart** (server log line; debug-level ones need `debug = True`).
| Observation | Points to |
|---|---|
| `Refusing to bind port <port-id> to dead agent: ...` | 1. agent dead (stopped, no bus / OVN southbound, clock drift), or 2. renamed agent left a dead entry under Nova's name |
| Agent of that host alive under another name in the agent list | 2. host names differ (short vs FQDN, renamed host) |
| `Failed to bind port` only, flat/VLAN network on `physnet` (ML2/OVS debug: `... is connected to physical network <physnet>, but agent <host> reported physical networks [...]`) | 3. no bridge mapping for the physnet on that host |
| ML2/OVS debug: `... is type of <type> but agent <host> or mechanism driver only support [...]`; or `vnic_type` `direct` | 4. network type not handled on that host |

**Fix options.**
1. Cause 1. *State-changing*: Kolla-Ansible:
   `sudo systemctl start` (or `restart`) `kolla-neutron_openvswitch_agent-container.service`;
   Any: restart `neutron-openvswitch-agent`. Instances keep their network
   (see *Restarting the OVS agent*). Then fix what stopped it reporting. Create
   the failed instance again; rerun the migration.
2. Cause 2, ML2/OVS. *State-changing*: change the **Neutron side** to Nova's
   name (`openstack compute service list --service nova-compute`): `host = <name
   Nova uses>` in the OVS agent configuration, restart the agent, then
   `openstack network agent delete <old-agent-id>`. Never change Nova's `host`
   on a compute with instances: it becomes a new compute and orphans them.
   [LAB-VALIDATED: VM-NET-12] Fix options 1 and 2 and the test boot below.
   Lab: 2026.1, Kolla-Ansible 22.2.0, multinode, ML2/OVS; agent alive 10 s
   after `systemctl start`, same build and migration then succeeded; cause 2
   simulated with the agent's `host` option. Not run: `docker restart`, the
   automatic rebind of `binding_failed` ports, the `Any:` commands.
3. Cause 3. *State-changing*: add the physnet to the host's mappings
   (Kolla-Ansible: `neutron_bridge_name`, `neutron_external_interface`,
   `neutron_physical_networks`, then `kolla-ansible reconfigure -i <inventory>
   --tags openvswitch,neutron,ovn-controller --limit <compute>`; restarts that
   compute's Neutron and Open vSwitch containers; interface must carry no IP).
   Precondition: the compute's external bridge exists only with
   `computes_need_external_bridge` (provider networks, DVR or OVN distributed
   FIPs); otherwise the agent exits with `Bridge <bridge> for physical network
   <physnet> does not exist. Agent terminated!` and the whole host loses its
   agent. Undo: revert and reconfigure. Or keep the network's instances off the
   host (aggregate plus flavor or image properties). Cause 4: use a type the
   host handles. With ML2/OVS, Neutron retries `binding_failed` ports when the
   agent revives (`_rebind_on_revive_agent_types`).
   [DOCUMENTED-UNVERIFIED: VM-NET-13]
4. ML2/OVN: `Refusing to bind port ... due to no OVN chassis for host: <host>`
   or `... OVN chassis bridge mapping physical networks [...] not supporting
   physical network: <physnet>`; compare `openstack compute service list
   --service nova-compute -c Host` with Kolla-Ansible `sudo docker exec ovn_sb_db
   ovn-sbctl --no-leader-only --columns=name,hostname list Chassis`. Fix for
   names: `openvswitch_hostname: <name Nova uses>` in `host_vars`, then
   `kolla-ansible reconfigure -i <inventory> --tags openvswitch,ovn-controller
   --limit <compute>`. *State-changing, data-plane cut*: it restarts
   `openvswitch_vswitchd`, every instance on that compute can briefly lose its
   network: maintenance window or move instances first. Agent restart:
   `kolla-ovn_controller-container.service` (not measured). No automatic
   rebind on OVN. [DOCUMENTED-UNVERIFIED: VM-NET-14]

**Verify.** *State-changing* (admin): `openstack server create --image <image>
--flavor <flavor> --network <network> --availability-zone nova:<compute> --wait
<test-name>`; its port `ACTIVE`, `binding_vif_type` `ovs`; agent alive under
Nova's name; `openstack server delete --wait <test-name>`.

## Security group rules not applied

A security group is a set of **allow** rules, default deny, stateful; groups on
a port add up. `default` allows all egress and ingress **only from its own
members** (two templates with remote `PARENT`), so instances sharing `default`
reach each other on every port. `port_security_enabled: False` disables all
filtering and anti-spoofing: everything passes. Kolla-Ansible 2026.1 ML2/OVS
uses `OVSHybridIptablesFirewallDriver`: per-port chains
`neutron-openvswi-i<id>` / `-o<id>` / `-s<id>` (first 10 characters of the port
ID), unmatched traffic to `sg-fallback` (drop), written by the OVS agent.

**Recognize.** An added rule does not let traffic in, or removed / absent rules
still let it pass; the instance is up. Lab: `nc: connect to <instance-address>
port 8080 (tcp) timed out: Operation now in progress` while port 22 passed.

[LAB-VALIDATED: VM-NET-15] Quick checks, the iptables view, and the cause 6
read-only check. Lab: 2026.1, Kolla-Ansible 22.2.0, all-in-one, ML2/OVS with
the iptables hybrid driver. Not run: the native OVS driver, ML2/OVN checks.

**Read-only checks.**
- `openstack port show <port-id> -c security_group_ids -c port_security_enabled -c allowed_address_pairs`
- `openstack security group rule list <security-group-id>`: direction
  (`ingress` = to the instance), ethertype, protocol, port range, remote prefix
  or remote group.
- `openstack network agent list --host <compute>`
- Kolla-Ansible ML2/OVS, on the compute, as root (else `Permission denied (you
  must be root)`): `sudo docker exec -u root neutron_openvswitch_agent
  iptables-save | grep -i <first-10-characters-of-port-id>` (and `ip6tables-save`).
- Admin: `openstack default security group rule list`.

**Tell the causes apart.**
| Observation | Points to |
|---|---|
| Rule on a group the port does not use, or direction / ethertype / port / remote does not match | 1. rule does not match |
| `port_security_enabled` `False` | 2. port security off |
| OVS agent not alive; port chains lack the rule | 3. change did not reach the compute |
| Group allows it, still dropped | 4. guest firewall, router, floating IP, physical firewall: *Unreachable from outside* |
| Source in `allowed_address_pairs`, or another port of the instance | 5. allowed by design |
| Both ports in `default`; its ingress rule has its own ID as remote group | 6. `default` admits its members |

**Fix options.**
1. Cause 1. *State-changing*, every port using the group:
   `openstack security group rule create --ingress --ethertype IPv4 --protocol tcp --dst-port <port> --remote-ip <cidr> <security-group-id>`,
   or `openstack port set --security-group <group> <port-id>`. Undo:
   `security group rule delete <rule-id>`. Lab: applied 1 s after the command,
   blocked again within 3 s of the delete.
2. Cause 2. *State-changing*, filtering starts at once (check groups and
   allowed address pairs first, e.g. a VRRP address):
   `openstack port set --enable-port-security --security-group <group> <port-id>`.
   Undo: `port set --no-security-group --disable-port-security <port-id>`.
3. Cause 3. *State-changing*: Kolla-Ansible ML2/OVS
   `sudo systemctl start kolla-neutron_openvswitch_agent-container.service`;
   the log shows `Agent has just been revived. Doing a full sync.` (rule
   applied 18 s after the start; the stop took 61 s, exit 137).
   [LAB-VALIDATED: VM-NET-16] Fix options 1 to 3. Lab: 2026.1, Kolla-Ansible
   22.2.0, all-in-one, ML2/OVS iptables hybrid. Not run: `docker stop`/`start`,
   OVN, the native driver.
4. Cause 6. *State-changing*, the instance loses what `default` gave it:
   `openstack security group create <group>`, add its rules, `openstack port
   set --no-security-group --security-group <group> <port-id>`. Undo: `port set
   --no-security-group --security-group default <port-id>`. Or (admin) change
   the default templates for future groups. Causes 4 and 5: fix the other
   filter or the pair. ML2/OVN: ACLs on port group `pg_<group id, _ for ->`,
   check `sudo docker exec ovn_nb_db ovn-nbctl --no-leader-only acl-list
   pg_<...>` (Kolla-Ansible); cause 3 is `ovn-northd` or `ovn-controller` down.
   Native OVS driver: conntrack-invalid traffic blocked, `224.0.0.X` multicast
   always allowed. On rule removal the iptables driver deletes matching
   conntrack entries; with OVN stateful ACLs an established flow may keep
   passing. [DOCUMENTED-UNVERIFIED: VM-NET-17]

**Verify.** `nc -zv <instance-address> <port>` from an allowed and a
non-allowed host; the port's chains (ML2/OVS) or ACLs (OVN) show the rule.

## ovs-vswitchd down

ovs-vswitchd switches the instances' traffic (`br-int`, `br-tun`). Stopped or
stuck, every instance on that compute loses the network; Nova (reading libvirt)
sees nothing.

**Recognize.** All instances of one compute stop answering, other computes
fine, Nova `ACTIVE` / `Running`, that compute's OVS agent `XXX`. Not at once:
traffic kept flowing 25 s, 6 s (stopped) and 17 s (frozen) before the cut, from
kernel-cached flows; the agent still showed `:-)` 53 s after the stop, `XXX` at
65 s. Host SSH still works when management and tunnel addresses are on plain
interfaces (as on the lab). Port changes on that compute wait.

[LAB-VALIDATED: VM-NET-18] Recognition, quick checks and Diagnosis commands.
Lab: 2026.1, Kolla-Ansible 22.2.0, multinode (3 controllers, 2 computes),
ML2/OVS VXLAN, host addresses on plain interfaces. Not run: the `Any:`
commands, a real out-of-memory kill or hang, OVN, DPDK.

**Read-only checks.**
- `openstack network agent list --agent-type open-vswitch --host <compute>`;
  `openstack server list --all-projects --host <compute> --long -c ID -c Name -c Status -c "Power State"`
- Compute, Kolla-Ansible (`docker` needs `sudo`):
  `sudo docker ps -a --filter name=openvswitch --format '{{.Names}} {{.Status}}'`
  (`openvswitch_vswitchd Exited (0)` when stopped);
  `sudo docker exec openvswitch_vswitchd ovs-appctl version` (`... is not
  running`; wrap in `timeout 10` for a hang);
  `sudo docker exec openvswitch_db ovs-vsctl show` (still answers). Do not run
  `ovs-appctl -t ovs-vswitchd` from `openvswitch_db`: it fails even when healthy
  (`stale pidfile`, `cannot read pidfile`).
- Why: `systemctl status` / `sudo journalctl -u kolla-openvswitch_vswitchd-container.service --since "-1h"`,
  `sudo docker logs --tail 200 openvswitch_vswitchd`,
  `/var/log/kolla/openvswitch/ovs-vswitchd.log`,
  `sudo dmesg -T | grep -i -E 'out of memory|killed process'`.
  Any: `journalctl -u ovs-vswitchd` (`openvswitch-switch` on Ubuntu),
  `/var/log/openvswitch/ovs-vswitchd.log`.
- Agent log (a consequence, not the cause): `Failed to communicate with the
  switch`, `OVS is dead. OVSNeutronAgent will keep running and checking OVS
  status periodically.`

**Tell the causes apart.**
| Observation | Points to |
|---|---|
| `openvswitch_vswitchd` stopped or restarting; reason in journal, log, `dmesg` | 1. stopped or killed (OOM: can recur) |
| Container `Up (healthy)`, `ovs-appctl version` no answer in 10 s, `ovs-vsctl show` fine, agent silent | 2. running but stuck (lab: simulated with `kill -STOP`) |
| ovs-vswitchd answers, agent dead | not this section: *Restarting the OVS agent* |

**Fix options.**
1. Cause 1. *State-changing*, this compute only: Kolla-Ansible
   `sudo systemctl start kolla-openvswitch_vswitchd-container.service`; Any:
   `systemctl start ovs-vswitchd`. Nothing else: the agent logs `OVS is
   restarted. OVSNeutronAgent will reset bridges and recover ports.` and
   reprograms flows; instances answered 30 s and 3 s after the start. Undo:
   none needed.
2. Cause 2. *State-changing*: `sudo systemctl restart
   kolla-openvswitch_vswitchd-container.service` (Any: `systemctl restart
   ovs-vswitchd`); returned in about 1 s, instance back 2.6 s later; for a few
   seconds `ovs-appctl version` prints `cannot read pidfile ... (No such process)`.
   [LAB-VALIDATED: VM-NET-19] Fix options 1 and 2, Kolla-Ansible commands. Lab:
   2026.1, Kolla-Ansible 22.2.0, multinode, ML2/OVS; gaps 88.5 s / 81.4 s
   (stopped) and 39.7 s (frozen); other compute 0 lost. Not run: the `Any:`
   commands, recovery from a real OOM kill or real hang.
3. A host whose own address sits on an OVS bridge loses its connectivity too
   (console access needed); a real OOM kill needs its memory cause fixed before
   closing. [DOCUMENTED-UNVERIFIED: VM-NET-20]

**Verify.** Agent `:-)`; `ping -c 10 <instance-address>`; `sudo docker exec
openvswitch_vswitchd ovs-appctl version` answers; `ovs-ofctl dump-flows br-int
| head` shows flows. Lab delays depend on traffic and port count.

## Tunnel MTU mismatch

One compute's tunnel interface has a smaller MTU than Neutron assumes. Small
encapsulated packets fit, full-size ones are dropped silently; ping and
monitoring stay green.

**Recognize.** Instances of one compute answer ping and accept connections,
but SSH hangs on large output, large HTTP answers time out, TLS with a long
chain fails. Other computes fine. Nova and Neutron report nothing. Largest ICMP
payload = network MTU - 28; VXLAN over IPv4 needs tunnel MTU >= network MTU + 50.

[LAB-VALIDATED: VM-NET-21] Recognition and the checks below. Lab: 2026.1,
Kolla-Ansible 22.2.0, ML2/OVS VXLAN over IPv4, multinode (3 controllers or 1
controller, 2 computes); tunnel MTU 1442, network MTU 1392; compute-1 lowered
to 1342: DF 56 and 1214 bytes answered, 1364 bytes lost, nothing logged. Not
run: OVN (Geneve), IPv6 underlay, VLAN or flat networks, jumbo frames.

**Read-only checks.**
- `openstack network show <network> -c mtu -c provider:network_type`
- Network node: `ip netns exec qrouter-<router-id> ping -M do -s 56 -c 3
  <instance-ip>` then `-s <network-mtu-minus-28>`, to an instance on the
  suspect compute and on another one.
- Every compute: `ip link show <tunnel-interface> | grep -o 'mtu [0-9]*'`; the
  odd one out is the cause.

**Tell the causes apart.**
| Observation | Points to |
|---|---|
| One compute's tunnel interface MTU smaller than the others | 1. lowered after deployment (network change, NIC/bond, DHCP-delivered MTU) |
| Same, correct MTU everywhere; host-to-host DF ping at full tunnel size fails | 2. underlay switch or link |
| Every compute affected; `global_physnet_mtu` (default 1500) above the real MTU | 3. Neutron assumes too much |
| `tunnel_address_family: ipv6` | 4. VXLAN overhead is 70, not 50 |

More checks [DOCUMENTED-UNVERIFIED: VM-NET-22]: Kolla-Ansible
`grep -E '^\s*local_ip' /etc/kolla/neutron-openvswitch-agent/openvswitch_agent.ini`,
`docker exec openvswitch_vswitchd ovs-vsctl show | grep -A2 'type: vxlan'`,
`ip -o addr show | grep '<local-ip>'` (Kolla-Ansible `tunnel_interface`,
default `network_interface`); controller:
`grep -E '^\s*global_physnet_mtu' /etc/kolla/neutron-server/neutron.conf`,
`grep -E '^\s*path_mtu' /etc/kolla/neutron-server/ml2_conf.ini`. Underlay:
`ping -M do -s <tunnel-mtu-minus-28> -c 3 -I <local-ip> <remote-local-ip>`.
On the lab this host-to-host DF ping, run from the other host, did **not**
detect the lowered MTU of compute-1: a passing result does not rule out cause 1;
use the per-compute `ip link` comparison.

**Fix options.**
1. Cause 1. *State-changing*: `ip link set dev <tunnel-interface> mtu <mtu>`
   (value of the other computes); traffic recovers at once; a wrong value can
   cut management if it shares the interface: out-of-band console if in doubt.
   Undo: previous value. Lost at reboot or DHCP renewal: persist it (netplan:
   `mtu: <mtu>` in `/etc/netplan/<file>.yaml`), then `netplan apply`:
   *State-changing*, can briefly cut every network of the compute: console,
   maintenance window; undo: previous file, apply again. Then find who changed it.
   [LAB-VALIDATED: VM-NET-23] Lab: 2026.1, Kolla-Ansible 22.2.0, ML2/OVS,
   multinode; `ip link set` on every run, netplan persistence only on the
   1-controller, 2-compute confirmation. Not run: other network managers.
2. Cause 2: fix the switch ports or links (outside OpenStack). Cause 3, or a
   smaller MTU as the new reality. *State-changing, every tenant network*:
   Kolla-Ansible `/etc/kolla/config/neutron.conf` `[DEFAULT] global_physnet_mtu
   = <underlay-mtu>`, `kolla-ansible reconfigure -i <inventory> -t neutron`
   (Any: set it on the Neutron servers, restart `neutron-server`), then
   `openstack network set --mtu <underlay-mtu-minus-50> <network>` for each
   existing network. Instances pick it up only at DHCP renewal or reboot;
   decide with the platform owners, maintenance window. Undo: previous values,
   reconfigure. [DOCUMENTED-UNVERIFIED: VM-NET-24]

**Verify.** Same MTU on every compute; largest DF ping answers to an instance
on every compute; again after the next reboot of the compute.

## Router on a dead L3 agent

A router's `qrouter-` namespace, NAT and floating IPs are kernel state: they
stay when the L3 agent stops, so traffic flows, but the router is frozen on the
dead agent. With Kolla-Ansible's default `enable_neutron_agent_ha: false` a
router lives on one agent, and `allow_automatic_l3agent_failover` defaults to
false: nothing reschedules it.

**Recognize.** `openstack network agent list --agent-type l3` shows one agent
`XXX`; instances behind its routers still answer on their floating IPs; users
may report a new floating IP, router interface or gateway change not working.

[LAB-VALIDATED: VM-NET-25] Recognition, read-only checks, and the behaviour
that traffic continues and the router stays on the dead agent. Lab: 2026.1,
Kolla-Ansible 22.2.0, ML2/OVS VXLAN, legacy routers, multinode; 0 of 264
requests lost during a 120 s outage, container `Exited (143)`. Not run: L3 HA,
DVR, OVN (no L3 agent), loss of a whole host.

**Read-only checks.**
- `openstack network agent list --router <router> --long` (`--long` requires
  `--router`); `openstack router list --agent <dead-agent-id>` (every router to
  handle).
- Agent host: `ip netns list | grep qrouter-<router-id>`; Kolla-Ansible
  `docker ps -a --filter name=neutron_l3_agent --format '{{.Names}} {{.Status}}'`,
  `systemctl status kolla-neutron_l3_agent-container.service`,
  `/var/log/kolla/neutron/neutron-l3-agent.log` (exit 143 = SIGTERM). Any:
  `journalctl -u neutron-l3-agent`.
- Is the host alive: `ping -c 3 <agent-host>`, `ssh <agent-host> ip netns list`.

**Tell the causes apart.**
| Observation | Points to |
|---|---|
| Host answers, namespace present, agent stopped | 1. L3 agent stopped |
| Host does not answer at all | 2. host lost: its routers' traffic is likely down too |

Changes to the routers of a dead agent do not apply while it is down; this
follows from how the agent works and was not observed (the page's lab note
mentions a floating IP associated during the outage; its body says not run).
[DOCUMENTED-UNVERIFIED: VM-NET-26]

**Fix options.**
1. Cause 1. *State-changing*: Kolla-Ansible, on the agent's host,
   `systemctl start kolla-neutron_l3_agent-container.service`; Any:
   `systemctl start neutron-l3-agent`. It resyncs its routers. Undo: stop the
   unit. Then find why it stopped.
   [LAB-VALIDATED: VM-NET-27] Lab: 2026.1, Kolla-Ansible 22.2.0, ML2/OVS,
   legacy routers, multinode; 0 of 432 requests lost after the start. Not run:
   the `Any:` command.
2. Cause 2. *Destructive*: rebuilds the router elsewhere; every instance
   behind it loses traffic during the rebuild, existing connections are cut.
   Precondition: the old host is really down or its `qrouter-<router-id>`
   namespace is gone, otherwise gateway and floating IPs answer from two
   hosts. Tell the instance owners first; moving back is a second cut.
   `openstack network agent remove router --l3 <dead-agent-id> <router>`,
   `openstack network agent add router --l3 <live-agent-id> <router>`, check
   with `agent list --router <router> --long`; repeat per router. Longer term:
   L3 HA (`enable_neutron_agent_ha: true`) keeps a standby; existing routers
   are not converted by the setting alone; read upstream first.
   [DOCUMENTED-UNVERIFIED: VM-NET-28] For a host that may not be dead, see
   `openstack-incident-analysis` (fence first).

**Verify.** Agent alive and router on a live agent; a test floating IP on an
instance behind the router answers; delete it.

## Restarting the OVS agent

A planned restart of `neutron-openvswitch-agent` (configuration change, stuck
agent, Neutron reconfigure or upgrade, which restarts it on every compute). The
agent only programs flows; ovs-vswitchd carries traffic and keeps the flows.
On start the agent tags new flows with a new cookie, resyncs with
`neutron-server`, then removes only old-cookie flows (graceful restart).
This holds only with `[agent] drop_flows_on_start = False` (the default); with
`True` all flows are cleared and instances are cut until reprogrammed.

**Before.** `openstack network agent list --agent-type open-vswitch --host
<compute>`; `openstack server list --all-projects --host <compute> --long -c ID
-c Name -c Status -c "Task State"` (anything building or migrating); on the
compute, Kolla-Ansible: `docker exec openvswitch_vswitchd ovs-appctl version`
must answer, otherwise stop: see *ovs-vswitchd down*, a restart will not help.

**Restart.** *State-changing*: Kolla-Ansible
`systemctl restart kolla-neutron_openvswitch_agent-container.service`; Any:
`systemctl restart neutron-openvswitch-agent`. It takes about a minute
(`docker_graceful_timeout`, 60 s by default; about 70 s on the lab), allow for
it in automations. If the agent does not come back: `systemctl start` the same
unit. Undo: none needed. Follow with `docker logs --tail 50 -f
neutron_openvswitch_agent` or `/var/log/kolla/neutron/neutron-openvswitch-agent.log`.

[LAB-VALIDATED: VM-NET-29] Restart of a healthy agent's unit: instances on the
restarted compute lost 0 of 295 requests (one every 0.5 s: a shorter cut would
be missed), all agents reported alive at every observation, other compute
unaffected. Lab: 2026.1, Kolla-Ansible 22.2.0, ML2/OVS
VXLAN, `drop_flows_on_start` default. Not run: the `drop_flows_on_start` check,
the restart of a stuck agent, creating an instance or changing a security group
during the restart, the flow dump during the restart, the `Any:` commands, OVN,
DPDK, production scale. Also reported from production on Kolla-Ansible 2024.x
or earlier by the page owner; steps not re-run there.

[DOCUMENTED-UNVERIFIED: VM-NET-30] Check `docker exec neutron_openvswitch_agent
grep -rn drop_flows_on_start /etc/neutron/` (no output or `False` = default)
and do not restart if it is `True`. Port changes on that compute (new
instances wait for wiring, security group updates, port updates) wait until
the agent is back, about the restart's duration: not measured. A stuck or dead
agent while ovs-vswitchd answers: a restart is the usual first step, not
reproduced. Many ports make the resync longer.

**Verify.** Agent alive (allow a minute); `ping -c 10 <instance-address>`;
`docker ps --filter name=neutron_openvswitch_agent`; `docker exec
openvswitch_vswitchd ovs-ofctl dump-flows br-int | head` shows flows. To measure
a cut, run `ping -i 0.5 -D <instance-address>` across the restart.
