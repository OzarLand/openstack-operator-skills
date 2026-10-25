# Worked example (abridged)

Based on the field decision in [Book: Ch. 19]. Shows the expected shape and
tone of an early response, when the cause is not yet known. Values in angle
quotes «like this» are what the user supplied in this example.

**User:** «Users can't create VMs since about 09:10. Existing VMs look fine.
Nova logs show MessagingTimeout. One Galera node shows non-Primary.»

---

## Situation
- Capability affected: provisioning (VM creation). Still working, per report:
  existing instances. Consistent with a control-plane problem; data plane
  apparently unaffected (to confirm).
- Business impact: no new VMs; criticality of blocked consumers **unknown** —
  who depends on provisioning today?
- What changed: **not yet known** — any maintenance, network work, cert/key
  rotation or deployment since yesterday?

## Evidence
| # | Class | Statement | Source |
|---|---|---|---|
| 1 | Reported | VM creation fails since ~09:10 | user |
| 2 | Reported | existing VMs fine | user |
| 3 | Observed | `MessagingTimeout` in Nova logs | user excerpt |
| 4 | Observed | one Galera node non-Primary | user |
| 5 | Assumption | three-node Galera and RabbitMQ clusters | not stated |

## Hypotheses
| Hypothesis | Supports | Would disprove | Discriminating check |
|---|---|---|---|
| H1 RabbitMQ partition or degradation | 3 | single consistent cluster view from all nodes, consumers present | `rabbitmqctl cluster_status` on every node |
| H2 Galera quorum loss on one node causing service errors | 4 | other nodes Primary and services writing through a healthy node | `wsrep_%` on every node; which node the LB sends writes to |
| H3 Shared network fault affecting both | 3+4 together | no network events; bus and DB fail independently | network/switch events around 09:10 |

## Next diagnostics (read-only)
1. `rabbitmqctl cluster_status` on each node — partitions, alarms, membership.
2. `SHOW GLOBAL STATUS LIKE 'wsrep_%';` on each Galera node.
3. Queues with messages ready but no consumers, in every vhost the services use
   (`rabbitmqctl list_vhosts`, then `list_queues -p <vhost>`).
4. `openstack compute service list` / `openstack network agent list`.
5. Count of instances in BUILD now vs 30 minutes ago — is state accumulating?

## Protect decision
If check 5 shows instances accumulating in BUILD while the bus and database are
unhealthy, the platform's state is getting worse. Option to put to the incident
leader: withdraw the API endpoints from the load balancer (provisioning already
unavailable; running workloads unaffected per report) so bus and database can
be recovered on a static state. Reopen only after verification below. Decision
owner: «who is incident leader / who can authorize suspending the APIs?»

## Corrective options (not yet authorized)
Not proposed until H1–H3 are discriminated. Note now: if a partition is
confirmed, do **not** reset nodes before knowing which side the services use;
if a Galera bootstrap becomes necessary, identify the most advanced node first.

## Verification before reopening
Galera full size, all Primary; RabbitMQ whole, queues present, consumers
connected; all compute services and agents up; test VM created, reached,
deleted.

## Gaps
Versions, deployment tool, queue type, partition-handling setting / metadata
store, what changed, consumer criticality.

> Decision support only. State-changing steps above require approval by the
> accountable owner and should be executed under your change process.
