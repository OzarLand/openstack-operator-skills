# Architecture implications for operations

`[Addition]` — everything in this file is added by this repository, distilled
from the OzarLand `kolla-ansible-deployment-patterns` repository at commit
`dee2c60` (`comparisons/`, `topologies/`, `networking/`, `storage/`,
`services/`, `version-notes/`), plus two lab records of the OzarLand
`openstack-vm-runbooks` repository at commit `babdd8c`. The book does not name
Kolla-Ansible. It is about what a deployment choice already made means for
the people running the platform: what fails, where to look, what maintenance
and upgrades cost. It is not a deployment guide, and no choice here is the
right architecture in general: each has conditions and trade-offs. Most source
pages are comparisons written from Kolla-Ansible 2026.1 documentation and
code; untagged technical text is unverified. Lab runs used Docker: with
Podman, replace `docker` (not tested).

## Contents

- ML2/OVS or OVN
- One or three controllers
- Network services on controllers or separate network nodes
- Docker or Podman
- Interfaces, VLANs and MTU
- Provider networks
- Storage: Cinder and Glance backends, where instance disks live, external Ceph
- Services: Octavia, Designate, monitoring, central logging
- Lab topologies and what they cannot show
- From 2025.1 to 2026.1

---

## ML2/OVS or OVN

Kolla-Ansible: `neutron_plugin_agent` (`"openvswitch"`, the default, or
`"ovn"`). Linux Bridge is gone from Neutron and Kolla-Ansible. Both keep the
`openvswitch_db` and `openvswitch_vswitchd` containers on every host: OVN
programs Open vSwitch, it does not replace it.

| | ML2/OVS | ML2/OVN |
|---|---|---|
| What can fail | An agent (L3, DHCP, metadata, OVS): its routers or DHCP stop being updated, or stop if the namespace goes | `ovn-controller` on a host, `ovn-northd`, or the NB/SB database cluster: changes stop reaching hosts; OVS keeps the flows already installed |
| State to protect | Neutron's database only; agents rebuild from it | Neutron's database **and** the OVN NB/SB databases (Raft cluster on `ovn-database`, `control` by default); `neutron-ovn-db-sync-util` resyncs NB from Neutron |
| Where routers, DHCP, metadata run | `qrouter-…`, `qdhcp-…` namespaces on `network` hosts | gateway chassis on `ovn-controller-network`; DHCP by `ovn-controller` on each host; one `ovnmeta-…` namespace per network per host |
| Router HA | off by default; `enable_neutron_agent_ha: true` | built in (gateway chassis, BFD) |
| Tenant MTU on a 1500 underlay | 1450 (VXLAN) | 1442 (Geneve, `max_header_size` 38) |
| Where to look | `openstack network agent list`, `ip netns`, `tcpdump` in the namespaces, agent logs | Kolla-Ansible: `docker exec ovn_northd ovn-nbctl show` and `ovn-sbctl show`; `ovn-trace` or `ml2ovn-trace`; `ovn-controller` logs |

OVN gaps that look like faults: an instance's security groups must allow its
DHCP traffic (ML2/OVS adds that rule itself); OVN answers tenant DNS itself,
UDP only, no EDNS; not supported: IPv6 NDP proxy, east-west fragmentation
through an OVN router, the metering agent, QoS packet-rate rules, FIP port
forwarding on VLAN/flat internal networks with distributed FIPs. Ironic bare
metal DHCP needs `neutron_ovn_dhcp_agent: "yes"`. With ML2/OVS, 2026.1 runs DHCP
and L3 subprocesses in wrapper containers (`neutron_agents_wrappers`), so an
agent restart does not take them down; OVN's metadata HAProxy too.
There is no supported migration between drivers in Kolla-Ansible: prechecks
stop with "Kolla-Ansible does not support this migration operation". Moving
is a project (tool outside Kolla-Ansible, a new region or a rebuild, and a
lower MTU for every instance), not a `globals.yml` change.
[DOCUMENTED-UNVERIFIED: KA-ARCH-01] Neither driver was deployed or compared
for the source page.

**Upgrades.** ML2/OVS: agent containers are recreated; with router HA,
`neutron_l3_agent_failover_delay` spaces L3 agent restarts (guide: `40 + 3n`
seconds for `n` routers as a start, better measured). ML2/OVN: `site.yml`
applies the `ovn-controller` role before `ovn-db`; the OVN databases are a
second set of stateful services to check before and after, next to MariaDB
and RabbitMQ; a 2026.1 upgrade adds `ovn_sb_db_relay` containers unless
`enable_ovn_sb_db_relay: "no"`. Both: recreating the OVS containers can cut
traffic briefly (2 s on one ML2/OVS lab: KA-ARCH-29). No OVN upgrade is
recorded. [DOCUMENTED-UNVERIFIED: KA-ARCH-02]

## One or three controllers

| Event | One controller | Three controllers |
|---|---|---|
| Controller lost | No API, no create, delete, migrate or attach; running instances keep running with their network | VIP moves, two members keep quorum, APIs answer through HAProxy |
| MariaDB/RabbitMQ restart (reconfigure, upgrade) | DB or bus down meanwhile | `serial: "33%"`: one member at a time |
| Other API containers recreated | API down meanwhile | all hosts of the play at once by default (`kolla_serial` unset): a short gap can still be seen |
| Two controllers lost | — | quorum lost, MariaDB and RabbitMQ stop on the survivor; manual recovery: `kolla-ansible mariadb-recovery` (see host-and-database-operations.md) |
| Bad change, corruption, accidental delete | down / lost | on all three within seconds: restore from backup |
| Replace a controller | rebuild and restore | one at a time, keeping quorum, after moving its DHCP networks and L3 routers |

Two controllers give no HA: losing one stops the other (quorum). Three
controllers add failure modes to watch: Galera size and state, RabbitMQ
partitions, which host holds the VIP, a VIP held by two hosts (split brain if
VRRP is blocked), a backend silently out of HAProxy;
`keepalived_virtual_router_id` (default `51`) must be unique on the L2 segment.
Glance with a non-shared `file` backend runs one `glance_api` only: a single
point of failure even with three controllers. Replication is not a backup
(`kolla-ansible mariadb-backup`). Ask: are the three really independent
(power, switches, racks)? [DOCUMENTED-UNVERIFIED: KA-ARCH-03] Neither layout
was failed over or upgraded for the source page; five or more controllers,
stretched clusters and external load balancers are not covered.

## Network services on controllers or separate network nodes

The `network` group holds the ML2/OVS L3, DHCP and metadata agents or the OVN
gateway chassis, and — in the 2026.1 multinode sample — HAProxy and keepalived
(`[loadbalancer:children]` = `network`). The source pages disagree on where
the VIP lives in that sample: the comparison page says `network`, the
interfaces page attributes the internal VIP to `control`. Unresolved; read
your own inventory (`[loadbalancer]`).

| Event | On controllers | Dedicated network nodes (≥ 2) |
|---|---|---|
| Controller lost | its routers fail over **and** its control services go at once | only control services; routing unaffected |
| Network node lost | — | routers fail over to the others; control plane unaffected |
| Control-plane `reconfigure`/`upgrade` | API and data-plane containers restart on the same hosts at the same time | can be sequenced, but the operating guide calls `--limit` "not recommended" (bug 2054348): test on a lab |
| Kernel or OVS fault on a gateway host | can take a controller down | stays on a network node |
| Heavy SNAT | competes with DB, RabbitMQ, APIs | isolated |

ML2/OVS failover needs `enable_neutron_agent_ha: true` and two or more
`network` hosts; OVN schedules gateways across all `network` hosts by priority.
With DVR (`neutron_compute_dvr_mode: dvr`) or `neutron_ovn_distributed_fip`,
FIP traffic leaves from the compute; SNAT without FIP still uses the network
group. East-west tunnel traffic is compute to compute in both layouts. Moving
later: add network hosts, move routers and DHCP networks (or let OVN
reschedule), remove the old ones; with the sample inventory this also moves
the VIPs. [DOCUMENTED-UNVERIFIED: KA-ARCH-04] Not built on a lab; no failover
times measured.

## Docker or Podman

`kolla_container_engine` (`"docker"` default, or `"podman"`). Same images,
roles, `/etc/kolla/<container>/` files, `kolla_logs` volume. 2026.1 writes one
systemd unit per container, `kolla-<container>-container.service`, which
restarts it (depends on `docker.service` with Docker, `network-online.target`
with Podman).

| | Docker | Podman |
|---|---|---|
| Engine restart | `systemctl restart docker` restarts **every container of the host** (unless `live-restore`, which the bootstrap guide warns about) | no daemon; a package upgrade does not by itself restart containers (distribution-dependent, not tested) |
| Volumes | `/var/lib/docker/volumes/<volume>/_data` | `/var/lib/containers/storage/volumes/<volume>/_data` |
| Runbook commands | `docker ps/logs/exec` | `podman ps/logs/exec`: translate every Docker runbook |
| Registry settings | `daemon.json`, written by `bootstrap-servers` | Podman's own configuration (not checked) |

A container removed with `docker rm -f` comes back through its unit (seen on
a lab: KA-ARCH-23). [DOCUMENTED-UNVERIFIED: KA-ARCH-05] Not run on a lab for the
source page.

**Changing engine.** *Destructive*: the guide's `migrate-container-engine`
redeploys everything with the new engine; all instances of the cloud must be
stopped (no rolling migration), volumes are migrated and the old engine's
packages are removed with all their resources and data. Preconditions: full
outage window, database and `/etc/kolla` backups, a lab run first; follow the
guide of your release (the source gives no commands on purpose). Undo: the
same migration the other way. [DOCUMENTED-UNVERIFIED: KA-ARCH-06]

## Interfaces, VLANs and MTU

Every interface variable except `neutron_external_interface` defaults to
`network_interface` and must carry an IP: `api_interface` (APIs, internal VIP,
DB, MQ), `tunnel_interface`, `kolla_external_vip_interface`,
`dns_interface`; `migration_interface` and `octavia_network_interface` default
to `api_interface`. `neutron_external_interface` has **no IP**: it is plugged
into `br-ex`, and plugging the interface carrying the host's management
address cuts the host off. Kolla-Ansible does not create VLAN or bond
interfaces (netplan, NetworkManager, systemd-networkd do); per-host names go
in `host_vars`/`group_vars`.

MTU: Kolla-Ansible 2026.1 templates set neither `global_physnet_mtu` nor
`path_mtu`, so Neutron assumes 1500. Tenant MTU = underlay − 20 (IPv4) −
overhead (VXLAN 30, Geneve 38): 1500 → 1450 / 1442; 9000 → 8950 / 8942. The
pages disagree on the Geneve 38: Neutron's default (comparison page) or set
by Kolla-Ansible (interfaces page); unresolved, the value is the same. On a
1442 underlay (the nested lab) VXLAN networks get 1392. Raising MTU: every
switch, bond and VLAN sub-interface first; then overrides
(`/etc/kolla/config/neutron.conf` `[DEFAULT] global_physnet_mtu`,
`neutron/ml2_conf.ini` `[ml2] path_mtu`); **existing networks keep their
MTU** until their `mtu` attribute is updated. A single 1500-byte hop breaks
large packets silently: the classic overlay symptom (see the tunnel MTU
mismatch in `openstack-vm-troubleshooting`).

Read-only: `ip -d link show <interface>` (MTU, VLAN ID);
`openstack network show <network-id> -c mtu -c provider:network_type`.
[DOCUMENTED-UNVERIFIED: KA-ARCH-07] Not applied on a platform.

## Provider networks

`enable_neutron_provider_networks: true` creates `br-ex` on computes too
(`computes_need_external_bridge`, also set by DVR and OVN distributed FIPs).
Operational consequences:

- Every compute that may host such an instance needs the physical network and
  its VLANs; an instance landing on a compute without the VLAN boots without
  network. Check the switch side first.
- Flat networks work as deployed (`flat_networks`); VLAN provider networks need
  `[ml2_type_vlan] network_vlan_ranges = physnet1` in
  `/etc/kolla/config/neutron/ml2_conf.ini` (empty in 2026.1 unless Ironic).
- No Neutron router: the gateway is the physical router. Metadata comes from
  the DHCP namespace (ML2/OVS, `enable_isolated_metadata`, `force_metadata`) or
  the per-host OVN metadata agent. DNS: the subnet's `--dns-nameserver`, else
  `neutron_dnsmasq_dns_servers`, which defaults to public resolvers that an
  isolated network cannot reach.
- A shared provider network puts every project on one L2 segment; security
  groups are the only separation. Addresses must not overlap with the
  physical network.

[DOCUMENTED-UNVERIFIED: KA-ARCH-08] No provider network was built on the
OzarLand labs.

*State-changing*: `openstack network create --share --provider-physical-network physnet1 --provider-network-type vlan --provider-segment <vlan-id> provider-<vlan-id>`
then `openstack subnet create` with `--gateway <physical-gateway>`, an
`--allocation-pool` no other system uses, `--dns-nameserver <resolver>` (flat:
`--provider-network-type flat`, no segment). Every project can then attach.
Undo: delete subnet and network once no port uses them.
[DOCUMENTED-UNVERIFIED: KA-ARCH-09]

## Storage: Cinder and Glance backends, where instance disks live, external Ceph

**Backends** (chosen once, expensive to change):

| | LVM | Ceph RBD (external) | NFS |
|---|---|---|---|
| Besides OpenStack | VG `cinder-volumes` per storage host | a Ceph cluster, deployed and upgraded outside Kolla-Ansible | NFS servers and exports |
| Loss of the host/server | its volumes unavailable until it returns | Ceph serves replicas | its volumes unavailable |
| Several `cinder-volume` | known LVM issues (bug 1571211) | active/active with `cinder_cluster_name` | per driver |
| `cinder-backup` default driver `ceph` | set `nfs`/`s3` or disable | fits | `nfs` with `cinder_backup_share` |

Glance `file` on local disk: one `glance-api` only and no Glance rolling
upgrade. 2026.1 moved `cinder-volume`/`cinder-backup` to the `cinder` group
(controllers); LVM needs them on the VG hosts (`cinder-volume-lvm`).
[DOCUMENTED-UNVERIFIED: KA-ARCH-10] Ceph and NFS columns not applied.

Settings that do not do what they seem [LAB-VALIDATED: KA-ARCH-11]:
`enable_cinder_backend_lvm` without `enable_cinder: "yes"` (2026.1 default
`false`) deploys no Cinder and reports `failed=0`; `cinder_backup_driver:
"nfs"` without `cinder_backup_share` deploys `cinder-backup` `down` from the
start, and a backup fails with `Service not found for creating backup`;
setting `enable_cinder_backup: "no"` afterwards leaves it running and
registered `down`. LVM volumes are thin LVs in `cinder-volumes-pool`
(`max_over_subscription_ratio` 20, iSCSI via `tgtd`). Lab: 2026.1,
Kolla-Ansible 22.2.0, all-in-one, LVM; not run: Ceph, NFS, a backup to a
working target.

Removing a stray `cinder-backup` on one host, *State-changing* (existing
backups stay; no new backup until a backup service runs): Kolla-Ansible:
`sudo systemctl disable --now kolla-cinder_backup-container.service`,
`sudo docker rm -f cinder_backup`,
`sudo docker exec cinder_api cinder-manage service remove cinder-backup <host>`.
[DOCUMENTED-UNVERIFIED: KA-ARCH-12]

**Where instance disks live.**

| | Local store (default) | Nova on Ceph RBD | Boot from volume |
|---|---|---|---|
| Root disk | Kolla-Ansible: `nova_compute` volume, `/var/lib/docker/volumes/nova_compute/_data`, qcow2 over `_base` | RBD image in `vms`, `images_type = rbd` | Cinder volume via `os-brick` |
| Compute dies | disks stay on the dead host | in Ceph | on the Cinder backend |
| Live migration | copies the disks (block migration; not with config drives) | no copy | no copy |
| Capacity | per compute: one can be full while others have room | one pool | Cinder quotas |

[LAB-VALIDATED: KA-ARCH-13] Local store location and format, and a
boot-from-volume root disk on Cinder LVM/iSCSI, read on a lab. Lab: 2026.1,
Kolla-Ansible all-in-one, ML2/OVS, local store and LVM; not run: Nova on Ceph
RBD, migration.

Evacuation with the local store rebuilds the root disk from its image: data
written in the instance is lost; a boot-from-volume instance keeps its disk.
[LAB-VALIDATED: KA-ARCH-14] Lab: 2026.1, Kolla-Ansible multinode (1
controller, 2 computes), ML2/OVS, local disks and a volume; not run: Ceph RBD
instance disks. A full instance store pauses the instances that write while
Nova still shows them `ACTIVE`; `df` on the Docker volume path needs `sudo`.
Monitor each compute's store, and give it its own file system, or it fills
the root file system with Docker and logs. [LAB-VALIDATED: KA-ARCH-15] Lab:
2026.1, Kolla-Ansible multinode (1 controller, 2 computes), dedicated 5 GB
store; not run: Ceph, boot from volume on a full host.

**Nova on Ceph and external Ceph.** All instance I/O crosses the storage
network: an outage stalls every instance on that compute. Images should be
`raw` (qcow2 is downloaded and converted on every new disk). By default
Nova uses the Cinder Ceph user, so that key can read and write instance
disks. Kolla-Ansible configures clients only. Where to look:

| Symptom | Look at |
|---|---|
| Deploy fails on a missing keyring in the Nova role | `/etc/kolla/config/nova/<cluster>.client.<user>.keyring` (Nova and Cinder users) |
| `cinder-volume` `rbd-1` down | `cinder-volume.log`: monitor unreachable, `permission denied`, keyring name, `ceph.conf` with leading tabs |
| Backups fail | `cinder-backup.log`: needs both Cinder and backup keyrings |
| Attach or Ceph boot fails on a compute | `nova-compute.log`, `/var/log/kolla/libvirt/libvirtd.log`: libvirt secret, route to OSDs |

Read-only: `openstack volume service list`; Kolla-Ansible:
`sudo docker exec nova_libvirt virsh secret-list` (`ceph-persistent-cinder`,
`ceph-ephemeral-nova`). [DOCUMENTED-UNVERIFIED: KA-ARCH-16] Treated as not
run: the page's record lists a read-only check without Ceph, its body says
nothing was run.

Switching backends, *State-changing* (`reconfigure --tags glance,cinder,nova`
restarts `glance_api`, Cinder, `nova_compute`/`nova_libvirt` everywhere; API
calls may fail meanwhile): existing images, volumes and disks do not move.
Undo (switches back) is safe only before anything is created on Ceph; after,
those resources cannot be opened until the switches are set again.
[DOCUMENTED-UNVERIFIED: KA-ARCH-17]

## Services: Octavia, Designate, monitoring, central logging

Kolla-Ansible-specific. Enabling any of them adds an HAProxy frontend, which
**restarts `haproxy` on every load balancer host** (backups, then the VIP
holder): a brief interruption of every API. Disabling removes neither the
containers nor the HAProxy fragments (`haproxy-config` never deletes one).

**Octavia (amphora).** Logs `/var/log/kolla/octavia/`: `PENDING_CREATE` then
`ERROR` → `octavia-worker.log` (boot, image tag `amphora`, quota of `service`,
port 9443); `ACTIVE` but `OFFLINE` or failover loops →
`octavia-health-manager.log` (no UDP 5555 heartbeats: management VLAN,
`octavia_network_interface`, which defaults to `api_interface` and is rarely
right, host firewall). The client certificate expires after **365 days**
(`octavia_certs_client_expiry`): then nothing can be created, changed or failed
over, while existing LBs keep forwarding. Read-only:
`kolla-ansible octavia-certificates -i <inventory> --check-expiry 60`;
re-running `octavia-certificates` does not renew existing files. Default
topology `SINGLE`: a failover or image rotation interrupts an LB briefly.
2026.1 template's `heartbeat_key` is the fixed `insecure`; changing it with
running LBs is untested. Jobboard (default) needs `enable_valkey`.
[DOCUMENTED-UNVERIFIED: KA-ARCH-18]

**Designate (BIND9).** Zone `PENDING`/`ERROR` → `designate-worker.log` (rndc,
port 953); BIND9 has no copy → `designate-mdns.log`, `/var/log/kolla/named/`;
no record for an instance → `neutron-server.log`, network `dns_domain`, port
`dns_name`; resolves on BIND9 but not outside → delegation and
`designate_ns_record` (default `ns1.example.org`), port 53 on `dns_interface`
(Kolla-Ansible does not delegate). Check each hop with `dig` (mDNS 5354, BIND9
53, resolvers). BIND9 is authoritative only. Enabling it restarts Nova
containers on every compute (notifications). [DOCUMENTED-UNVERIFIED: KA-ARCH-19]

**Monitoring.** Kolla-Ansible provides Prometheus, exporters, Alertmanager and
Grafana, but **no alert rules, no notification receiver, no dashboards**: you
bring `/etc/kolla/config/prometheus/*.rules`, a complete
`prometheus-alertmanager.yml` (a secret if it holds SMTP or webhook
credentials), `grafana/dashboards/*.json`. Alertmanager and Grafana are on the
external VIP by default. Enabling also turns on RabbitMQ's Prometheus plugin:
the next `rabbitmq` role run restarts RabbitMQ. A rule or receiver change
leaves a monitoring gap while containers restart. Where to look: Prometheus
targets page (`/api/v1/targets`), `docker logs prometheus_server` (rule that
does not parse), `docker logs prometheus_alertmanager` (SMTP/webhook).
[DOCUMENTED-UNVERIFIED: KA-ARCH-20]

**Central logging.** `/var/log/kolla/<service>/` on each host is root-only:
`sudo sh -c 'grep -h "<request-id-without-req>" /var/log/kolla/nova/*.log'`
(plain `sudo grep` with a glob fails: `No such file or directory`). With
OpenSearch, search by request ID without `req-`
(`request_id:"…" OR global_request_id:"…"`). A quiet service's last line is
shipped only when it writes the next one: the `nova-scheduler` line explaining
a `NoValidHost` arrived 2 min 25 s late; if a trail stops at a service, grep
its host. `enable_fluentd_systemd` shipped 0 journal documents (Permission
denied, nothing in `fluentd.log`). Retention: indices closed after 30 days,
deleted after 60; Kolla-Ansible does not update an existing policy. Without
HAProxy, Dashboards answered on 5601 without credentials.
[LAB-VALIDATED: KA-ARCH-21] Lab: 2026.1, Kolla-Ansible 22.2.0 all-in-one,
ML2/OVS, `enable_haproxy: "no"`, one OpenSearch node; not run: HAProxy
frontends, a three-node cluster, a retention change, Dashboards UI.

Port 9200 has no authentication (`plugins.security.disabled`): anyone on the
internal network can read and delete logs. OpenSearch on controllers competes
for disk with MariaDB and RabbitMQ; at its disk watermarks it stops writing
(health `red`, indices read-only); heap default `1g`.
[DOCUMENTED-UNVERIFIED: KA-ARCH-22]

**Undoing central logging**, *State-changing* (`enable_central_logging: "no"`
is not enough; precondition `enable_opensearch` false — OSProfiler or
CloudKitty keep it true and Fluentd keeps shipping): Kolla-Ansible:
`kolla-ansible reconfigure -i <inventory> --tags fluentd`; on each opensearch
host `sudo docker rm -f opensearch opensearch_dashboards`, then
`sudo systemctl disable --now kolla-opensearch-container.service kolla-opensearch_dashboards-container.service`,
delete the two unit files under `/etc/systemd/system/`,
`sudo systemctl daemon-reload` — after `docker rm -f` alone the units stayed
in `auto-restart`. Undo: `enable_central_logging: "yes"` and the deploy.
Removing the `opensearch` volume deletes the logs: no undo.
[LAB-VALIDATED: KA-ARCH-23] Lab: 2026.1, Kolla-Ansible 22.2.0 all-in-one,
ML2/OVS, no HAProxy; not run: the HAProxy part below, volume removal.

**Dropping the frontends** (central logging, monitoring, Designate),
*State-changing*: delete the fragment(s) under `/etc/kolla/haproxy/services.d/`
(and `external-frontend-map` blocks with `haproxy_single_external_frontend`);
`reconfigure --tags loadbalancer` sees no change, so restart `haproxy` on each
LB host, backups first, VIP holder last (`ip -br addr | grep -w "<internal-vip>"`),
one at a time, in a window: each restart interrupts the APIs and the VIP may
move. The monitoring page's undo (`docker rm -f prometheus_server
prometheus_alertmanager grafana`) omits the systemd-unit cleanup that the
logging lab found necessary: the same units may bring those containers back
(not checked); disable and remove their `kolla-<container>-container.service`
units as on the logging lab.
[DOCUMENTED-UNVERIFIED: KA-ARCH-24]

## Lab topologies and what they cannot show

The lab evidence in this skill comes from two kinds of small labs nested in
another OpenStack cloud, both 2026.1, Kolla-Ansible 22.2.0, Docker, Ubuntu
24.04, ML2/OVS, no Ceph:

- **All-in-one** (one VM, 4 vCPU, 16 GB; no HAProxy, keepalived or ProxySQL;
  no Cinder; external network on a veth pair, FIPs reachable only from the
  node). Cannot show failover, clustering, multi-compute behaviour, API gaps
  with several backends (each service had one container, so every
  recreation was an outage), or anything OVN, Podman, Ceph.
- **Three controllers + two computes** (controllers also network nodes; one
  port per network, no trunks; underlay MTU 1442; instance store on a 10 GiB
  volume per compute; deploy host on Ubuntu 22.04 with
  `prechecks_enable_host_os_checks: false` for `deployment` only). VIP failover
  and canary instances passed on each build; not tried: OVN, Podman, Cinder,
  Ceph, dedicated network nodes. Daily unattended upgrades ran mid-deploy
  (178 packages, `libc6`, `systemd`) and MariaDB never formed its cluster:
  disable them on deploy targets. [DOCUMENTED-UNVERIFIED: KA-ARCH-25] The
  page records repeated builds without a dated record; it lists five differing
  settings while its lessons say three (unresolved).

All-in-one without HAProxy on 2026.1 (relevant to any single-node platform):
also set `enable_proxysql: "no"`, or
ProxySQL takes `kolla_internal_vip_address:3306` (the node's own address),
MariaDB exits with `Bind on TCP/IP port. Got error: 98: Address already in
use`, `deploy` hangs on `Wait for first MariaDB service port liveness`, and a
`haproxy` container runs despite `enable_haproxy: "no"`. During a first
deploy, `fatal: ... Timeout when waiting for search string MariaDB` followed by
`...ignoring` is expected; read the `PLAY RECAP`. [LAB-VALIDATED: KA-ARCH-26]
Lab: 2026.1, Kolla-Ansible 22.2.0, all-in-one nested, ML2/OVS, local disk;
not run: any multinode or HAProxy setup. The pages disagree on when ProxySQL
became the default: the all-in-one page says 2026.1, the version notes say
already 2025.1 (in 2026.1 it follows `enable_mariadb`). Unresolved; either way
it is on unless set to `"no"`.

When citing a lab-validated item, name its lab: nested, small and synthetic
load are limits, not production evidence.

## From 2025.1 to 2026.1

Both are SLURP releases: one skip-level upgrade brings 2025.2 and 2026.1
changes at once. Most likely to stop it (release notes): inventory renames
`kolla-toolbox` → `kolla_toolbox` and `kolla-logs` → `kolla_logs` (plus new
Neutron groups); the Cinder group move for LVM users; Redis → Valkey
(`enable_redis: "no"`, `enable_valkey: "yes"` before); Ansible on the deploy
host (2026.1: Ansible 12–13, ansible-core 2.19–2.20, then `install-deps`);
host OS (CentOS Stream 10, Debian 13, Rocky Linux 10, Ubuntu 24.04); RabbitMQ
allowed paths (`rabbitmq_allowed_upgrades`; `rabbitmq-version-check` fails
naming the intermediate version); Linux Bridge and dropped services (Zun,
Kuryr, InfluxDB, Telegraf, Venus, VMware, `ironic-inspector`) removed first.
Changes by themselves: `clustercheck` removed and MariaDB via HAProxy
unsupported (ProxySQL); APIs under uWSGI (`glance-tls-proxy`,
`neutron-tls-proxy` gone); Horizon behind HAProxy on port 8080; ML2/OVS L3 HA
no longer sets `ha_vrrp_health_check_interval`; `om_rabbitmq_qos_prefetch_count`
50. Kolla-Ansible runs online data migrations and `nova-status upgrade check`
(stops on a code above 1) itself. [DOCUMENTED-UNVERIFIED: KA-ARCH-27]

*Destructive*: `kolla-ansible upgrade` recreates every container and runs
schema migrations; there is no downgrade (2025.1 images do not run on a 2026.1
schema). Way back after it: restore databases and `/etc/kolla`, redeploy 2025.1
images, losing everything since the backup. Precondition: a backup restored
once on a scratch host. Handled by `openstack-change-review` and
`openstack-operational-decisions`. [DOCUMENTED-UNVERIFIED: KA-ARCH-28]

**What happened on the lab.** `kolla-ansible upgrade` completed first time
(24 min, `failed=0`). Running instances never stopped (same qemu PIDs). FIPs
lost one 2 s gap when `openvswitch_vswitchd` was recreated (+10 min). Keystone
was unavailable about 10 s, Nova up to about 15 s three times, Neutron about
30 s (`neutron_server` recreated; `neutron_rpc_server`,
`neutron_periodic_worker` appeared). MariaDB and RabbitMQ restarts were not
visible to unauthenticated probes. `mariadb_clustercheck` was removed; with an
explicit `enable_proxysql: "no"` no ProxySQL was deployed; without HAProxy,
Horizon stayed on 80. MariaDB 10.11 → 11.4.13 (major: check tooling), RabbitMQ
4.0.9 → 4.2.9, Nova max microversion 2.100 → 2.103.
[LAB-VALIDATED: KA-ARCH-29] Lab: 2025.1 → 2026.1, Kolla-Ansible 20.6.0 →
22.2.0, all-in-one, ML2/OVS, local disk, no HAProxy; not run: multinode with
HAProxy, OVN, Cinder, Valkey migration, rollback.

Everything that went wrong came before `upgrade`:
- Docker settings are not part of `kolla-ansible upgrade`: a move to a
  plain-HTTP registry made `pull` fail with `http: server gave HTTP response
  to HTTPS client`. Adding it to `insecure-registries` in
  `/etc/docker/daemon.json` and `sudo systemctl reload docker` (*State-changing*)
  applied it with all 31 containers still running; `bootstrap-servers` can
  restart Docker and every container. Check with `docker info`.
- 2025.1 `bootstrap-servers` restarted Docker before writing its proxy drop-in
  (seen once): `docker info` showed no proxy until `systemctl restart docker`.
- The Mariabackup is a root-only **directory** `full-<date>-<id>/`: a check
  expecting one `.gz` matched nothing and reported no error.
- `kolla-ansible prune-images` removed none of the 30 tagged 2025.1 images;
  `docker rmi` by tag freed 7 GB (*State-changing*: removes the quickest way
  back).

[LAB-VALIDATED: KA-ARCH-30] Lab: same run; not run: `bootstrap-servers` during
the upgrade, Podman.
