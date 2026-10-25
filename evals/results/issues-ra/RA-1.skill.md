I couldn't save a file (the Write tool is disabled in this session), so the runbook is below. I haven't published it as a shareable page. If you want it as a page or a `.md` file, say so and I'll set it up once a file can be written.

---

# Runbook: VM creation fails, existing VMs OK (RabbitMQ RPC broken, Galera unhealthy)

**Status: Draft, not yet validated.** It was written from one incident note, and nobody other than the author has run it.
**Owner:** TODO. **Last validation:** never. **Review by:** TODO.

## Purpose
Restore a trusted messaging layer and database, and with them the ability to create VMs, after a RabbitMQ partition.

## Scope
**Covers:** new VM creation fails while existing VMs keep running, and both RabbitMQ RPC and Galera are unhealthy.

**Does not cover** (TODO: link a procedure for each):
- One RabbitMQ node that left a healthy majority with no partition.
- Only Galera unhealthy, or only RabbitMQ unhealthy. Handle that one component alone.
- No Galera Primary component at all. That is a bootstrap decision for a specialist.
- Single compute host or agent failures.

## Context
- **Reported:** existing VMs stayed up. Verify this for your storage and network backends before relying on it.
- **Reported:** the partition was identified only after recovery. The steps below were a "stabilise first" response taken without knowing the cause. Next time, check for a partition before purging anything (see Decision point).
- **Gap:** the notes don't say why Galera became unhealthy. Don't assume a MariaDB restart is always needed. TODO: ask the incident team.

## Who may run it
- **Read-only checks:** first line or the platform team.
- **State-changing steps:** a platform specialist, with prior approval from a named owner (TODO: name the role).
- **Reopening the APIs:** a separate approval, given after verification passes.

## Preconditions
- **Access:** shell on the control nodes, admin OpenStack credentials and HAProxy admin. Never paste `transport_url`, DB credentials or tokens into tickets. Write `<redacted>`.
- **Evidence to save before any change**, because the purge and restart destroy it:
  - `cluster_status` from every reachable RabbitMQ node, plus RabbitMQ logs searched for partition or node-down events.
  - The configured partition-handling mode (`ignore`, `pause_minority` or `autoheal`). Verify for your release.
  - Queue and consumer counts for every vhost the services use, not only `/`.
  - Galera size and status on every node, plus the MariaDB logs.
  - Service logs showing RPC timeouts.
  - Timestamps, and what changed beforehand (TODO: what changed before this incident?).

## Decision point
| Check (read-only) | If you see | Go to |
|---|---|---|
| RabbitMQ `cluster_status` on all nodes, logs, partition mode | Nodes agree, one node absent, the rest are a majority, no partition events | Node-left case: not this runbook. Rejoin first, and list what a reset would lose. |
| Same | Differing views, a listed partition, partition events in the logs, or autoheal restarts | **Section B** |
| Same | Unclear, or no majority | Treat as Section B |
| Galera size and `Primary` status on each node | All as expected | Do **not** restart MariaDB |
| Same | Fewer nodes than expected, or a node not Primary | Include step 8, after specialist review. If **no** node is Primary, **stop and escalate**. |

## Procedure: Section B
This is the incident order (Reported). Commands aren't in the notes. Use your deployment's commands, which may run inside containers.

| # | Action | Why | Type | Expected | If different |
|---|---|---|---|---|---|
| 1 | Save the evidence listed above | The purge and restart destroy it | read-only | Copies stored off-node | Note which node was unreachable and continue |
| 2 | Work out which RabbitMQ side the services use and whether any node is paused | A wrong reset discards queues still in use | read-only | Clear map of nodes and sides | Unknown: escalate before step 4 |
| 3 | **Approval gate:** the named owner accepts that provisioning stops and queues are purged | Deliberately pausing provisioning protects the platform | decision | Approver and time recorded | No approver: **stop** |
| 4 | Pull the APIs from HAProxy and stop them (TODO: which services?) | Stops new requests adding broken state | state-changing | No API traffic, VMs still running | Running VMs affected: stop and escalate |
| 5 | Purge RabbitMQ queues (TODO: which vhosts, and by what method?) | Clear stale state left by the partition | **state-changing, destructive** | Queues empty | Error: don't force it, escalate |
| 6 | Restart the RabbitMQ cluster (TODO: node order, how nodes rejoin) | Rebuild one consistent cluster | state-changing | Identical `cluster_status` everywhere, no partition | Nodes disagree: **stop** |
| 7 | Check RabbitMQ cluster status and consumers | Services must reconnect | read-only | Nodes agree, consumers present | No consumers: do services need a restart? (TODO: notes are silent) |
| 8 | Restart MariaDB, only if Galera was unhealthy (TODO: node order, rolling or not) | Restore full Galera membership | state-changing | Expected size, Primary, synced | A node won't rejoin, or no Primary: **stop and escalate** |
| 9 | Check compute services and network agents are up | They report over RPC | read-only | All up, state fresh | Some down: check their RabbitMQ connectivity first. Don't evacuate or fence on this alone. |
| 10 | Run the Verification below (TODO: how was the test run while the APIs were out of HAProxy?) | Prove the capability before taking user traffic | creates one test VM | Create, ping and delete all succeed | See Verification |
| 11 | Reopen the APIs in HAProxy (needs approval) | Restore service | state-changing | Normal requests succeed | Errors return: pull the APIs again |

## Stop and escalate
**Stop if:**
- RabbitMQ has no majority, or the nodes still disagree after step 6.
- Galera has no Primary, or nodes won't rejoin.
- Running VMs are affected.
- Monitoring is blind, or no approver is available.
- The failure comes back after recovery. Repeated recovery is not stability.

**Collect first:** the saved evidence, your exact steps with timestamps, and the current state of every RabbitMQ and Galera node.
**Escalate to:** TODO.

## Do not do without escalation
- Don't purge queues or restart RabbitMQ before checking for a partition and getting approval.
- Don't restart all MariaDB nodes at once, or bootstrap Galera (TODO: confirm site policy).
- Don't evacuate or fence hosts because services look "down" while messaging is broken.
- Don't reopen the APIs before the end-to-end test passes.
- Don't put secrets in tickets.

## Verification
1. RabbitMQ nodes agree, there is no partition and consumers are present.
2. Galera has the expected size, is Primary and is synced on every node.
3. Compute services and agents are up.
4. Create a test VM, confirm it reaches ACTIVE, ping it, delete it, and confirm its resources are released.
5. After reopening the APIs, watch error rates for a set period (TODO: how long?).

## Recovery
- **If a step fails:** keep the APIs out of HAProxy and escalate. That keeps provisioning off while running VMs stay up.
- **Point of no return:** step 5, the queue purge. Lost in-flight messages can't be restored. Instances stuck in BUILD or ERROR from interrupted requests may need cleanup (TODO: how was this handled?).
- **Approaches that failed:** none are recorded. TODO: ask the responders.

## Follow-up
- **Root cause (Reported):** a RabbitMQ network partition. TODO: what caused the partition, and is it fixed?
- **Candidate actions** (suggestions only, not decisions): alert on RabbitMQ partitions and on Galera size and status, and review the partition-handling mode against your network design.

## History
| Date | Change | Why | By |
|---|---|---|---|
| TODO | Draft created from incident notes | Capture knowledge | TODO |

---

## Author notes
- **Sources:** one paragraph of incident notes, with everything in it taken as reported. No outputs were shown, so I haven't claimed the sequence is proven to work.
- **Inferred, not in your notes:** the decision point, the evidence-preservation step, the approval gates, the stop and do-not lists, and the recovery section. I added these because purging queues and restarting RabbitMQ and MariaDB are destructive, and the incident took those steps before the partition was identified.
- **Decision for the owner:** I gated the incident's purge-and-restart order behind a partition check and approval. If the team wants it as a first-line fast path instead, that call is theirs to make.
- **Gaps (TODO):**
  - **Responders can close:** exact commands, node order, vhost scope, the list of stopped services, whether services needed restarting, and how the test VM was created with the APIs out of HAProxy.
  - **Database owner can close:** why Galera was unhealthy.
  - **Network team can close:** the partition's cause.
  - **Management can close:** the named owner, approver and escalation contact.
- **Validation plan:** a platform engineer who didn't write it runs a tabletop first. They then run it in a non-production environment, or during real maintenance, observed but not helped. Correct the document from their questions, then update the status line. TODO: who, where and when.

> Decision support only. State-changing steps above require approval by the accountable owner and should be executed under your change process.