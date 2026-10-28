# Failure patterns

Patterns documented in the book, each with the signals that point to it, the
checks that discriminate it from look-alikes, and the moves that make it worse.
A pattern is a hypothesis to test, never a conclusion [Book: Ch. 9].

Validation tags (rule 12 of the safety rules) say which technical claims
were executed on a lab; the lab records and concrete commands are in
control-plane-recovery.md and in the inventory. A book field passage is
evidence of one situation, not an execution record, so it is never a
validation by itself.

## Contents

- P1 Control-plane shared infrastructure unstable (bus and/or database)
- P2 RabbitMQ node left the cluster vs cluster partitioned
- P3 Compute host unreachable or failed
- P4 Builds fail although capacity exists
- P5 Instance stuck in BUILD until VIF plugging times out
- P6 Platform-wide authentication failure
- P7 Steal time on pinned-CPU instances
- P8 The state that lies (stale records)
- P9 Recurring incident resolved but never understood

---

## P1 Control-plane shared infrastructure unstable

Source: [Book: Ch. 19] (field decision), [Book: Ch. 1], [Book: Ch. 4].

- **Signals**: users cannot create VMs while existing instances run normally;
  RPC exchanges fail or time out; database cluster unhealthy; several services
  look broken at once.
- **Discriminating checks**: Galera status on every node; RabbitMQ cluster
  status, partitions, alarms, queues with messages but no consumers; whether
  instances accumulate in BUILD/transitional states.
- **Risk while open**: an unstable control plane that keeps accepting API
  operations creates orphaned allocations, half-built instances and records
  that disagree between Nova, Placement and Neutron — each one makes recovery
  slower and less certain.
- **Option documented in the book**: stop the APIs first; recover the bus
  (in that case after purging queues, accepting loss of in-flight operations so
  the backlog was not replayed against a just-restarted database) and the
  database; verify; reopen. Verification used: Galera full size and Primary,
  RabbitMQ whole with queues recreated and consumers connected, every compute
  service and agent reporting, a test VM created, reached and deleted.
- **Cautions**: stopping APIs does not stop conductors, schedulers or agents;
  when the bus returns every agent reconnects at once; purge loses in-flight
  operations. Root cause in the book's case was a RabbitMQ network partition —
  the review must reach that far.
- **As written, unverified** [DOCUMENTED-UNVERIFIED: IA-FP-01]: the book's
  sequence (purge, restart, reopen) comes from one field case with versions
  not recorded.
- **What a lab run of this sequence changed** `[Addition]` (Kolla-Ansible
  2026.1, RabbitMQ 4.2 with Khepri; details in control-plane-recovery.md):
  with Khepri a partition can heal by itself, so check every node again before
  any reset; `force_reset` is refused and `kolla-ansible rabbitmq-reset-state`
  failed, leaving a node outside the cluster and queues without a replica on it
  [LAB-VALIDATED: IA-CP-05]; keep `placement_api` and Keystone running while the
  other APIs are stopped, and expect the verification build to need the APIs
  back [LAB-VALIDATED: IA-CP-07].
- **Dangerous moves**: repairing bus and database while APIs keep accepting
  writes; restarting components repeatedly without a hypothesis.

## P2 RabbitMQ node left vs cluster partitioned

Source: [Book: Ch. 11], [Book: Ch. 10].

| | Node left the cluster | Cluster partitioned |
|---|---|---|
| Same initial alert | yes | yes |
| Book's handling | confirm the remaining nodes still form a majority; rejoin or reset the one node; watch consumers reconnect | do not touch the nodes yet; establish which side the services talk to; decide whether to stop the APIs first; escalate before any node is reset |
| Why | | the wrong reset discards queues the services are still using |

- **Discriminating check**: cluster status from **each** node (each side of a
  partition reports a different view); partition-handling setting (RabbitMQ
  default `ignore`, often set to `pause_minority` or `autoheal` by deployment
  tools) and metadata store (Mnesia vs Khepri); partition events in the logs;
  queue type (classic vs quorum); queues checked in every vhost the services
  use `[Addition]`. With Khepri, a partition showed `Network Partitions (none)`
  on every node; the sign was nodes disagreeing on the running nodes
  [LAB-VALIDATED: IA-CP-02].
- **"Reset the one node" is destructive** `[Addition]`: `rabbitmqctl reset`
  wipes that node's data. Before it, list the queues and quorum-queue replicas
  hosted on the node; a node removed for good must also be dropped with
  `forget_cluster_node`, and quorum queues may need `rabbitmq-queues grow` /
  `shrink` to restore their replica count. State-changing and irreversible for
  that node's data. [DOCUMENTED-UNVERIFIED: IA-FP-02] (the replica repair
  after a rejoin was run on a lab: IA-CP-05.)

## P3 Compute host unreachable or failed

Source: [Book: Ch. 10] (field passage and technical note), [Book: Ch. 20].

- **Signals**: compute service down; instances on it unreachable.
- **Key uncertainty**: dead or merely isolated from the control plane? Nova
  cannot know.
- **Required sequence**: confirm via out-of-band management (or isolate at the
  switch), power off / fence, **then** evacuate. Nova requires the compute
  service to be reported down before evacuating, but that is not proof
  [Book: Ch. 10]. Nova steps that go with it `[Addition]` (verify commands and
  behaviour for your release):
  1. Fence the host and verify its power state.
  2. Mark the service forced down —
     `openstack compute service set --down <host> nova-compute` (compute API
     microversion ≥ 2.11), state-changing — instead of waiting for the
     heartbeat to time out (`service_down_time`). External fencing and HA tools
     (e.g. Masakari) are expected to do the same.
  3. Evacuate instance by instance, in business-priority order agreed with the
     owners; verify each instance (active on the new host, reachable, disks
     consistent). From compute API microversion 2.95 an evacuated instance
     stays stopped on its new host and must be started.
  [LAB-VALIDATED: IA-FP-03] Steps 2 and 3 and the return below: lab 2026.1,
  Kolla-Ansible 22.2.0, ML2/OVS, local instance disks, no Cinder; the host was
  powered off by construction. Not run: fencing through IPMI or the switch,
  disabling the service, shared storage, boot from volume, microversion 2.95 or
  later, evacuation in batches. A local disk was rebuilt from the image: its
  content is lost.
  [DOCUMENTED-UNVERIFIED: IA-FP-04] Step 1, fencing through out-of-band
  management or switch isolation: the book's field case, not executed.
- **When the failed host comes back** `[Addition]`: keep it disabled and
  forced down. On start, `nova-compute` destroys the local copies of the
  instances evacuated from it, provided the evacuations completed and their
  migration records exist. Check networking and storage, start `nova-compute`,
  confirm it cleaned up the evacuated instances, and only then unset forced
  down (`--up`) and re-enable (`--enable`) as separate approved steps. Bringing
  it back earlier recreates the two-copies risk from the other end.
- **Dangerous moves**: evacuating on a missing heartbeat; automation that
  evacuates without fencing. Evacuation is for failed hosts only — never for
  planned maintenance.

## P4 Builds fail although capacity exists

Source: [Book: Ch. 5].

- **Candidates**: host not mapped to a cell ("host is not mapped to any
  cell"); Placement inventory/allocations disagree with reality; compute service
  disabled; stale allocations occupying capacity [Book: Ch. 5, Ch. 6]; scheduler
  filter configuration `[Addition]`.
- **Discriminating checks**: `nova-manage cell_v2 list_hosts`; instance fault
  message; `nova-manage placement audit` (read-only); service list (disabled
  reason).
- [LAB-VALIDATED: IA-FP-05] Lab (2026.1, Kolla-Ansible all-in-one): unmapped
  host, a Placement `reserved` value, a disabled service and an anti-affinity
  filter reproduced and repaired. Not run: stale allocations, traits, a `down`
  service, several computes. Details: `openstack-vm-troubleshooting`.

## P5 Instance stuck in BUILD until VIF plugging times out

Source: [Book: Ch. 5].

- **Reading**: usually a networking problem wearing a compute symptom — port
  binding or the `network-vif-plugged` event did not complete.
- **Discriminating checks**: port status and binding host; network agent / OVN
  controller health on that compute; neutron-server and agent logs for the
  request id; bus health if agent-based.
- [LAB-VALIDATED: VM-LC-01] Lab (2026.1, Kolla-Ansible, ML2/OVS): fault after
  about 300 s with the agent frozen; an agent already dead at request time
  gives `binding_failed` and "Exceeded maximum number of retries" within
  seconds instead. OVN not run. Details: `openstack-vm-troubleshooting`.

## P6 Platform-wide authentication failure

Source: [Book: Ch. 17], [Book: Ch. 8], [Book: Ch. 10].

- **Candidates**: Fernet key rotation removed a key still needed, or Keystone
  nodes hold different key sets; expired TLS certificate on an endpoint, the bus
  or the database; memcached loss (slow or failing token validation).
- **Discriminating checks**: certificate expiry dates; key repository
  comparison across Keystone nodes; timing relative to recent rotations
  ("what changed").
- Fernet keys and clock: [LAB-VALIDATED: IA-CP-18], see
  control-plane-recovery.md. Diverged keys break tokens older than the
  token cache lifetime (600 s by default on Kolla-Ansible) first; fresh
  tokens keep validating meanwhile.
- Certificates and memcached: [DOCUMENTED-UNVERIFIED: IA-FP-06] (the
  certificate part was not tested on a lab: no TLS).

## P7 Steal time on pinned-CPU instances

Source: [Book: Ch. 15] (field passage and technical note).

- **Usual explanations**: host processes (kernel threads, interrupts, memory
  deduplication, daemons) running on the CPUs in `cpu_dedicated_set` because
  host isolation was not configured; the QEMU emulator thread running on the
  instance's pinned CPUs (default unless `hw:emulator_threads_policy` moves it);
  then overlapping pinning or Nova/host mismatch. NUMA-aware live migration only
  exists from Train; older behaviour could itself create overlapping pinning.
- **Dangerous move**: repeatedly live-migrating affected instances. It
  relocates the symptom; a destination configured the same way reproduces it.
  The book's team stopped migrating, accepted limited steal and investigated.
- [LAB-VALIDATED: IA-FP-07] Lab (2026.1, Kolla-Ansible, nested KVM): steal
  reproduced on a pinned CPU (0.8 % idle, 26.7 % with host processes on it);
  emulator threads moved with `hw:emulator_threads_policy=share`. Not run: host
  isolation, migration.

## P8 The state that lies

Source: [Book: Ch. 10] (field passage), [Book: Ch. 6].

- **Signals**: instances stuck in BUILD/ERROR/deleting, ports bound to nothing,
  volumes attached to deleted instances, quota and capacity views that do not
  match reality.
- **Why it matters during an incident**: every investigation starts by asking
  whether a record describes reality.
- **Tools** (all state-changing except the audit): `nova-manage placement
  audit` / `heal_allocations`, `nova-manage db archive_deleted_rows`, reset
  state via the API [LAB-VALIDATED: IA-FP-08] (lab: 2026.1, Kolla-Ansible
  all-in-one; stuck build, stuck delete, orphan port, phantom and missing
  allocations cleaned; Cinder parts not run). Direct DB surgery only with
  backup first, one record at a time, verification after
  [DOCUMENTED-UNVERIFIED: IA-FP-09].
- **Database restores**: service databases must be restored as one operation
  at one point in time and reconciled against the hypervisors; mixed points in
  time create exactly this residue. [DOCUMENTED-UNVERIFIED: IA-FP-10]

## P9 Recurring incident resolved but never understood

Source: [Book: Ch. 6], [Book: Ch. 9], [Book: Ch. 15].

- **Signals**: the same symptom and the same fix every week or month.
- **Reading**: repeated recovery is not stability; the workaround consumes
  capacity each time; its frequency, effort and side effects are inputs to a
  permanent-remediation decision (hand off to `openstack-operational-decisions`).
