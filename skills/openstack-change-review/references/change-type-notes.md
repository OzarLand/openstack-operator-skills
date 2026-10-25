# Notes by change type

What to look for in common OpenStack change types. Items marked `[Addition]`
are this repository's suggestions, not the book's.

## Contents

- Certificate rotation
- Keystone Fernet key rotation
- Network changes
- Database interventions and stale-state cleanup
- Configuration changes to shared services
- Message bus changes (queue types, cluster changes)
- Changes carrying a local patch or backport

## Certificate rotation

[Book: Ch. 8, Ch. 17]
- Covers every internal and external endpoint, the message bus and the
  database cluster; agents on every compute may be affected [Book: Ch. 9].
- Expiry dates are known in advance; an expired certificate is a common cause
  of complete control-plane outage on long-lived platforms.
- A rotation that has never been rehearsed is a change with an unknown blast
  radius; the book puts rotations in the maintenance calendar and in recovery
  exercises. Recommending a rehearsal or a staged scope before production is an
  `[Addition]` that follows from that.
- Verification `[Addition]`: services reconnect over TLS, no handshake errors,
  API and RPC traffic healthy, new expiry dates visible to monitoring.

## Keystone Fernet key rotation

[Book: Ch. 17]
- Keys must be rotated correctly and kept identical on every Keystone node.
- Removing a key still needed for tokens in flight, or leaving nodes with
  different key sets, breaks authentication for the whole platform at once.
- A platform that has never rotated has never tested that it can.
- Check `[Addition]`: distribution mechanism to all nodes, order of
  operations, rollback (keeping prior keys until tokens issued with them
  expire), verification of token issue and validation from every node.

## Network changes

[Book: Ch. 1, Ch. 9, Ch. 12]
- Often affect several services at once and may sit with another team
  (fabric, firewalls); organizational boundaries must not become operational
  boundaries — name the coordinating owner.
- Neutron agents and OVN controllers run on data-plane nodes; restarting some
  of them can briefly interrupt tenant traffic, depending on version and
  configuration [Book: Ch. 1].
- Verification must include tenant connectivity end to end, not just link
  state `[Addition]`, consistent with capability-level verification
  [Book: Ch. 10].

## Database interventions and stale-state cleanup

[Book: Ch. 10]
- Direct database surgery: backup first, one record at a time, verification
  after.
- Prefer project tools where they exist: `nova-manage placement audit`
  (read-only unless `--delete`), `nova-manage placement heal_allocations`,
  `nova-manage db archive_deleted_rows`, reset state via the API.
- Database restores: all service databases at one point in time, followed by
  reconciliation against hypervisors; mixed points in time leave Nova,
  Placement, Neutron and Cinder disagreeing.
- Galera: confirm the write path (usually a single node behind the load
  balancer) and cluster health before and after.

## Configuration changes to shared services

[Book: Ch. 1, Ch. 9]
- A change to Nova, RabbitMQ, the database or memcached reaches every
  capability that depends on them; judge blast radius by dependents, not by the
  service changed.
- Roll out to a subset first where the architecture allows it `[Addition]`.
- Verify the capability (e.g. VM creation end to end), not only that the
  service restarted.

## Message bus changes (queue types, cluster changes)

[Book: Ch. 10]
- A queue's type is fixed at declaration: moving to quorum queues means
  deleting and recreating queues, in practice with the owning services stopped
  — this is a planned control-plane outage, not a config toggle.
- Quorum queues need a majority of members: size the cluster for the failures
  it must survive.
- RabbitMQ 4.0 removed classic queue mirroring.
- Partition handling (`cluster_partition_handling`) applies to the Mnesia
  metadata store, not Khepri; check which store is in use.

## Changes carrying a local patch or backport

[Book: Ch. 14, Ch. 17]
- The backport needs: the upstream issue, the upstream change it derives from,
  why the full upgrade was not chosen, an owner, how it is tested, and when it
  will be reconsidered (exit condition).
- An upstream stable backport is tested and maintained by the community; a
  local one is tested and maintained by you.
- If the strategic question (backport vs upgrade) is not settled, hand it to
  `openstack-operational-decisions` before reviewing execution.
