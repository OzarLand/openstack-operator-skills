I couldn't save this as a file because the Write tool is disabled in this session, so the runbook is below.

It is marked **Draft, not yet validated**. The notes had no commands, hostnames or approver names, so those are TODOs, not guesses.

---

# Runbook: VM creation fails, existing VMs OK (RabbitMQ RPC broken, Galera unhealthy)

**Status:** Draft, not yet validated. **Owner:** TODO. **Last validation:** never.
**Origin:** one incident. Root cause was found afterwards: a RabbitMQ network partition.

## Purpose and scope
Restore VM provisioning when the message bus and database are both unhealthy, while keeping running VMs and platform state safe.

**Covers:** new VM creation fails, existing VMs keep running, RabbitMQ RPC is broken, Galera is unhealthy.

**Does not cover:**
- A single RabbitMQ node that left a healthy-majority cluster with no partition events. Rejoin that node instead (see the decision point).
- Galera unhealthy while RabbitMQ is healthy.
- A compute host or nova-compute down. That is an evacuation question, so fence first.
- Running VMs affected. That is a data-plane problem, so stop and escalate.

## Context
- The control plane and data plane fail separately. Running VMs stayed up while new state couldn't propagate. Verify this for your backend.
- Pulling the APIs out of HAProxy is deliberate degradation. It stops new requests landing on a half-recovered bus. It also takes every API operation offline, not just VM creation.
- Purging queues discards in-flight messages, so VMs mid-build or mid-delete can be left inconsistent. TODO: confirm with the incident team what had to be cleaned up afterwards.
- The incident order was RabbitMQ first, then MariaDB. The notes don't say why. TODO: confirm.

## Who may run it
- **Read-only checks:** first-line ops (suggested).
- **Everything state-changing:** platform engineers.
- **Approver for stopping the APIs, purging, and restarting RabbitMQ or MariaDB:** TODO, a named role with authority to accept an API outage and lost in-flight operations. Agree this before the next incident.

## Preconditions
Preserve this evidence before any change (all read-only):
- `rabbitmqctl cluster_status` from every node.
- RabbitMQ logs around the incident start, searched for partition events.
- The partition-handling mode (`ignore`, `pause_minority` or `autoheal`). Verify for your version.
- Queue and consumer counts in every vhost the services use (check `transport_url`).
- Galera size, status and state on every node.
- Service logs showing RPC timeouts.
- Instances stuck in BUILD, ERROR or deleting.
- What changed recently.

Credentials come from the secret store. Never paste them or `transport_url` into tickets.
All commands are examples to verify for your release and deployment tool, and may need to run inside containers.

## Decision point (do this first, read-only)
| Check | If you see | Go to |
|---|---|---|
| `cluster_status` on every node, plus logs and partition mode | Nodes agree, one is absent, the rest are a majority, no partition listed and none in the logs | Rejoin that node. Purge and restart are probably excessive. Escalate if unsure. |
| same | Nodes disagree, a partition is listed, or logs show partition events | **Procedure below** |
| same | The absent node can't be queried and the cause is unknown, or there is no majority | **Procedure below** |
| logs (`autoheal`) | Autoheal restarted nodes | Procedure below. The partition already healed, so verify queues and consumers and escalate before doing more. |

If you rejoin a single node and have to reset it, a reset wipes that node's data. List its queues and replicas first, record what is lost, and get approval.

## Procedure
Each state-changing step needs the named approver. Check the result of each step before the next.

| # | Action | Type | Expected | If different |
|---|---|---|---|---|
| 1 | Collect the evidence above | read-only | Outputs saved with timestamps | A node is unreachable: treat its state as unknown and see Stop. |
| 2 | Establish which RabbitMQ side the services are connected to | read-only | You know where the live consumers are | Services are split across sides: escalate before step 5. |
| 3 | Get approval to stop the APIs | decision | Approval recorded (who, when) | No approver reachable: do not proceed. |
| 4 | Pull the API backends out of HAProxy. TODO: list which APIs. | state-changing | No new requests arrive and running VMs are unaffected | VMs affected: stop and escalate. |
| 5 | Purge RabbitMQ queues. TODO: confirm method and which vhosts. | state-changing, **destructive** | Queues empty | Can't purge cleanly: don't force it. Escalate. |
| 6 | Restart the RabbitMQ cluster. TODO: confirm node order and method. | state-changing | One cluster, no partition | Partition recurs: the network is the cause, so stop and escalate. |
| 7 | Check the RabbitMQ cluster and that consumers have reconnected | read-only | All nodes joined, consumers present | Consumers missing: services may need a restart. TODO: the notes don't say which. |
| 8 | Restart MariaDB. TODO: confirm procedure and node order. | state-changing | Node rejoins and syncs | Won't join or no Primary: **do not bootstrap**, escalate to the DB owner. |
| 9 | Check Galera size equals the expected count, every node is Primary, and nodes are Synced | read-only | As stated | Anything else: stop and escalate. |
| 10 | Check compute services and network agents are up | read-only | All up and recently updated | Down: read their logs. Don't mass-restart. |
| 11 | End-to-end verification (below). TODO: the notes don't say whether this ran before or after reopening. | state-changing (test resources) | Pass | Fail: keep the APIs out and go back to step 7. |
| 12 | Put the APIs back into HAProxy and notify users | state-changing | Requests succeed | Errors rising: pull the APIs out again and escalate. |
| 13 | Review instances stuck in BUILD, ERROR or deleting, and decide per resource with its owner | read-only, then state-changing | Nothing left without an owner decision | No bulk state resets without approval. |

## Stop and escalate
Stop if any of these happens:
- Running VMs are affected.
- Services use different RabbitMQ sides and you can't tell which holds live state.
- A node is unreachable for an unknown reason.
- Galera has no Primary component, has lost quorum, or needs a bootstrap.
- The partition recurs.
- Monitoring is blind.
- No approver is reachable.

**Collect before escalating:** the evidence list, the step you reached, and timestamps of every change.
**Escalate to:** TODO (on-call lead, DB owner, network team).

## Do NOT do without escalation
- Purge queues, or reset or forget a RabbitMQ node, before the decision point is answered.
- Bootstrap Galera or force a node to be the source of truth.
- Mass-restart computes or agents.
- Reopen the APIs before the end-to-end test passes.
- Bulk-reset instance states in the database.

## Verification
- Create a test VM and confirm it reaches ACTIVE.
- Ping it, then delete it and confirm it is gone.
- Confirm Galera size and Primary, the RabbitMQ cluster and consumers, and that compute services and agents are up.
- Watch for recurrence. TODO: define the period.

## Recovery
- **If it fails after step 4:** keep the APIs out, preserve evidence and escalate. Running VMs stay intact.
- **Point of no return:** step 5. Purged messages can't be restored. Fix each inconsistent resource individually (step 13).
- TODO: the rollback for a failed MariaDB restart isn't in the notes.

## Follow-up
The root cause was a network partition. TODO: record what triggered it, the partition mode in use, and whether an alert fires on a partition before provisioning breaks. If this recurs, treat the network as the problem, since repeated recovery isn't stability.

## History
| Date | Change |
|---|---|
| TODO | Created from incident notes |

TODO: what was tried before the purge and restart.

---

## Author notes
- **Sources:** your one-paragraph notes. The sequence, the checks and the root cause come from them.
- **My additions, not what the team did:**
  - The decision point.
  - Evidence preservation.
  - Stop conditions and the do-not-do list.
  - The "do not bootstrap Galera" rule.
  - Per-step approvals.
  - The step numbering and the "if different" guidance.
- **Gaps for the incident engineers:** exact commands, which queues and vhosts were purged, node order, which APIs were pulled, whether services needed restarts, why RabbitMQ came before MariaDB, MariaDB restart or bootstrap details, how stuck instances were cleaned up, what triggered the partition, and the owner, approver and escalation names.
- **Validation plan:** someone who didn't write it walks it in non-production (induce a partition) or during maintenance, observed but not helped, and the runbook is corrected from their questions. It stays Draft until then.

> Decision support only. State-changing steps above require approval by the accountable owner and should be executed under your change process.

I can publish this as a private shareable page if you'd like.