# Dependency map and read-only diagnostics

Summarized from the book's technical notes [Book: Ch. 1, Ch. 5, Ch. 8, Ch. 10]
plus commands marked `[Addition]` that this repository adds as common read-only
checks. Behaviour differs by release, deployment tool (containerized services
need `docker exec`/`podman exec` or equivalent) and networking backend
(ML2/OVS vs OVN). Verify for the platform at hand before relying on any detail.

## Contents

- Control plane vs data plane
- What a VM creation traverses
- Shared components and their signals
- OpenStack-level signals
- Read-only diagnostics by layer
- Commands that are NOT read-only

## Control plane vs data plane

[Book: Ch. 1, Fig. 1.1]

| Plane | Contains | If degraded |
|---|---|---|
| Control plane | API services, schedulers, conductors, message bus, databases | No create/modify/migrate/delete; new state (ports, security-group rules, floating IPs) does not reach the data plane; an instance booting during the outage may miss metadata. |
| Data plane | Hypervisors, instance disks, network paths, and the agents running on those nodes | Running instances keep running, keep storage and keep forwarding traffic. With ML2/OVS, existing DHCP leases are still served by the DHCP agent's dnsmasq; with OVN, DHCP is answered locally on each compute. L3 HA (keepalived) and OVN gateway chassis failover are data-plane mechanisms. |

Cautions: Neutron agents and OVN controllers run **on** data-plane nodes, so
restarting some of them can briefly interrupt traffic. "Stopping the control
plane" means APIs, bus and databases — not the agents.

## What a VM creation traverses

[Book: Ch. 5, Fig. 5.1]

1. **Keystone** authenticates the request (token validation usually via
   **memcached**).
2. **Nova API** validates it and records it in the API database.
3. **Nova conductor** coordinates the build and mediates DB access for computes.
4. **Nova scheduler** selects a host using **Placement** (resource providers,
   inventory, allocation claim).
5. The conductor maps the instance to a **cell** (cells v2). A host never
   mapped with `nova-manage cell_v2 discover_hosts` fails builds with "host is
   not mapped to any cell" — "capacity exists but nothing lands on it".
6. **nova-compute** fetches the image from **Glance** (or a volume from
   **Cinder** for boot-from-volume).
7. Nova asks **Neutron** to create and **bind** the port; the mechanism driver
   and the agent or OVN controller on the compute wire it.
8. Nova waits for Neutron's `network-vif-plugged` event. An instance stuck in
   BUILD until `vif_plugging_timeout` is usually a networking problem with a
   compute symptom.
9. The hypervisor driver starts the instance.

Transport: inside Nova (API, conductor, scheduler, compute) over oslo.messaging,
normally **RabbitMQ**; to Keystone, Placement, Glance, Neutron, Cinder over
REST via the service catalogue. Agent-based Neutron talks to agents over the
bus; OVN uses its own databases. Every service has its own database. A failed
VM creation can originate in any of these, in the bus, in the database cluster,
or in network/storage beneath them.

## Shared components and their signals

[Book: Ch. 8, Ch. 10, Ch. 17]

| Component | Key signals | Failure notes |
|---|---|---|
| MariaDB Galera | `wsrep_cluster_size`; `wsrep_cluster_status` (non-Primary ⇒ node refuses queries, reads included, unless `wsrep_dirty_reads` is on); `wsrep_flow_control_paused` | Writable only with quorum. Full-outage recovery bootstraps from the most advanced node (`grastate.dat` seqno and `safe_to_bootstrap`; after unclean stop find it with `--wsrep-recover`). Wrong node ⇒ lost transactions. Usually written through one node behind the LB. |
| RabbitMQ | messages ready / unacknowledged per queue; consumers per queue; memory/disk alarms; partitions | Queue accumulating while consumers vanish = a service that stopped processing, whatever its process list says. Quorum queues need a majority of members. Partition behaviour: `cluster_partition_handling` (RabbitMQ default `ignore`; the book calls `pause_minority` the usual choice for OpenStack, and several deployment tools set it — check `rabbitmq.conf`) applies to the Mnesia metadata store, not to Khepri — check which store the cluster uses. OpenStack services may use one or several non-default vhosts (check `transport_url`) `[Addition]`. |
| memcached | availability, latency | Loss makes every API call slow or failing (token validation). |
| Load balancer / VIP | backend health, API latency and error rates | The VIP is what makes "stop the APIs" a controlled action. |
| TLS certificates | expiry dates on every endpoint, bus and DB | A common cause of complete control-plane outage on long-lived platforms. |
| Keystone Fernet keys | key repository identical on all Keystone nodes; last rotation | Bad rotation or divergent keys break authentication platform-wide at once. |

## OpenStack-level signals

[Book: Ch. 6, Ch. 8]

- Liveness of every compute service and network agent as the services report it.
- Instances in BUILD, deleting or migrating longer than the operation should take.
- Difference between what Placement believes is allocated and what hypervisors run.
- Placement allocations for instances that no longer exist (`nova-manage placement audit`).
- Hosts with `nova-compute` disabled, and why.

## Read-only diagnostics by layer

Commands are examples; adapt to the deployment. All are read-only as written.

| Layer | Check | Source |
|---|---|---|
| Services | `openstack compute service list` | Book: Ch. 8 |
| Services | `openstack network agent list` | Book: Ch. 8 |
| Instance | `openstack server show <id>` (status, `fault`, host) | Addition |
| Instance | `openstack server list --all-projects --status BUILD` (also ERROR) | Addition |
| Request | search all service logs for the request id `req-<uuid>` | Book: Ch. 8 (correlation); command form is an Addition |
| Cells | `nova-manage cell_v2 list_hosts` | Addition |
| Placement | `nova-manage placement audit` (**without** `--delete`) | Book: Ch. 6, Ch. 10 |
| Placement | `openstack resource provider list` / `openstack resource provider usage show <uuid>` (needs osc-placement) | Addition |
| Galera | `SHOW GLOBAL STATUS LIKE 'wsrep_%';` on each node | Addition (signals: Book: Ch. 8) |
| RabbitMQ | `rabbitmqctl cluster_status` (members, partitions, alarms) | Addition |
| RabbitMQ | `rabbitmqctl list_vhosts`, then for each OpenStack vhost `rabbitmqctl list_queues -p <vhost> --timeout 60 name messages_ready messages_unacknowledged consumers`. Without `-p`, only the default vhost `/` is listed: on platforms that use per-service vhosts this shows few or no queues, which is **not** evidence that queues or consumers are gone. Can be slow on a degraded cluster. | Addition (signals: Book: Ch. 8) |
| RabbitMQ | `rabbitmqctl list_queues -p <vhost> name type leader members` (which queues and quorum replicas live on which node) | Addition |
| Certificates (HTTPS, AMQPS) | `openssl s_client -connect <host>:<port> -servername <name> </dev/null 2>/dev/null \| openssl x509 -noout -enddate` — `-servername` returns the right certificate behind an SNI load balancer | Addition |
| Certificates (MariaDB) | same with `-starttls mysql` (OpenSSL ≥ 1.1.1): MariaDB negotiates TLS inside its own protocol, so plain `s_client` does not work | Addition |
| Fernet | compare checksums of the key repository across Keystone nodes | Addition |
| Upgrade state | `nova-status upgrade check` (read-only; for an upgrade it must run with the *target* release's code before services restart — with installed code it only checks the current release) | Book: Ch. 14 |

## Commands that are NOT read-only

Never present these as diagnostics. Each needs the full change discipline and
a decision owner.

- `nova-manage placement audit --delete`, `nova-manage placement heal_allocations`,
  `nova-manage db archive_deleted_rows`, `nova-manage cell_v2 discover_hosts`
- `openstack server set --state ...` (reset state), `openstack server delete`,
  `nova evacuate` / `openstack server evacuate`, any migration
- `openstack compute service set --disable|--enable`
- `openstack compute service set --down|--up` (forced down; microversion ≥ 2.11)
- `rabbitmqctl reset|forget_cluster_node|stop_app|purge_queue`, restarting nodes
- Galera bootstrap (`galera_new_cluster` or equivalent), editing `grastate.dat`
- Restarting any OpenStack service, agent or OVN controller
- Any `UPDATE`/`DELETE` against a service database
