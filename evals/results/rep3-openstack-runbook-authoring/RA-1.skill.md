I couldn't save this as a file because the Write tool is disabled in this session. The full runbook is below, so you can paste it into your wiki.

---

# Runbook: VM creation fails, existing VMs fine (RabbitMQ RPC broken, Galera unhealthy)

**Status:** Draft, not yet validated
**Owner:** TODO
**Last validation:** never
**Review by:** TODO

## Purpose
Restore VM provisioning when RabbitMQ and Galera are both unhealthy. It uses the recovery that worked last time, with approval gates on the destructive steps.

## Scope
**Covers:** new VM creation fails, existing VMs keep running and are reachable, RPC between services is broken, and Galera reports unhealthy. Root cause in the reference incident was a **RabbitMQ network partition**, found only after recovery.

**Does NOT cover (stop and escalate):**
- Existing VMs are affected, which points to the data plane, network, storage or hypervisor.
- One RabbitMQ node left the cluster, the rest are a healthy majority, and there is no partition. That needs a smaller procedure. TODO: write it.
- No Galera node is Primary. That needs a bootstrap decision. TODO: write a separate runbook.
- RabbitMQ and Galera are both healthy and creation still fails. Investigate Nova, Neutron, Glance and Cinder instead.

## Context
- **Why the APIs come out first:** it stops new requests adding half-finished state while the bus and database are reset. Running VMs are not stopped by this, but new state doesn't propagate. Verify this for your backends.
- **Purging queues discards in-flight messages.** Builds, deletes and attachments that were mid-flight won't complete. This is inferred from how purge works, not from the notes.
- **The responders didn't know it was a partition while they were recovering.** This runbook therefore adds an early check for it.
- **Approaches tried that didn't work:** none recorded. TODO: ask the responders.

## Who may run it
- **Read-only checks:** first-line operations.
- **State-changing steps (stop APIs, purge, restart RabbitMQ, restart MariaDB):** the platform team, and only after the incident leader or accountable owner approves. TODO: name the role.
- Stopping the APIs deliberately suspends provisioning. That is a business decision, not only a technical one.

## Preconditions
- **Access:** HAProxy admin, shell on the controllers, and admin credentials from the secret store. Never paste credentials into tickets.
- **Record first (TODO for this platform):**
  - the RabbitMQ partition-handling mode (`ignore`, `pause_minority` or `autoheal`)
  - the vhosts the services use (from `transport_url`)
  - the expected Galera size
- **Preserve before any change:**
  - RabbitMQ cluster status from every reachable node
  - RabbitMQ logs around the first failure
  - Galera status from each node
  - `openstack compute service list` and `openstack network agent list` output
  - the list of instances in BUILD or ERROR
- **Deployment specifics** (containers, tooling, hostnames, versions, exact commands): TODO.

## Decision point (read-only)
| Check | If you see | Go to |
|---|---|---|
| RabbitMQ cluster status on every reachable node, plus logs and partition mode | Partition listed, nodes disagree, partition events in the logs, autoheal restarts, or no majority | This procedure, with approval |
| Same | One node absent, the rest a majority, and no partition events anywhere | Out of scope (node-left procedure) |
| Galera size and Primary state on each node | No node is Primary | Stop and escalate |

The notes don't say how the partition was eventually identified. TODO: confirm with the responders what evidence showed it.

## Procedure
| # | Action | Why | Type | Expected | If different, check first |
|---|---|---|---|---|---|
| 1 | Confirm the symptom: VM create fails and an existing VM responds | Shows a control-plane-only failure | read-only | Create fails, existing VM OK | If existing VMs are affected, stop |
| 2 | Collect the evidence listed under Preconditions | Needed for root cause and escalation | read-only | Saved outputs with timestamps | n/a |
| 3 | Run the decision-point checks | Decides whether this runbook applies | read-only | Partition or equivalent confirmed | If unclear, escalate and don't continue |
| 4 | **Get approval** to suspend provisioning, and record the approver | Disruptive: API requests fail meanwhile | decision | Named approver in the incident log | No approver reachable: stop |
| 5 | Stop the APIs and pull them from HAProxy | No new state during recovery | state-changing | Backends out, no API traffic | Method is deployment-specific (TODO) |
| 6 | **Purge RabbitMQ queues** | Clears broken RPC state | state-changing, **destructive** | Queues empty | Record the vhosts and queues purged. The step 4 approval must cover this explicitly |
| 7 | Restart the RabbitMQ cluster | Re-forms it without the partition | state-changing | One cluster, no partition listed | Node order is TODO. If a node won't rejoin, stop. Don't reset nodes ad hoc |
| 8 | Check cluster status on every node and that consumers are connected | A running broker doesn't prove RPC works | read-only | Nodes agree, consumers present | Missing consumers may mean services need a restart (TODO: confirm) |
| 9 | Restart MariaDB | Return Galera to health | state-changing | Nodes rejoin | Node order and whether any node was bootstrapped are TODO. If no node is Primary, stop |
| 10 | Check Galera size and Primary on every node | Process up doesn't mean cluster healthy | read-only | Size equals expected, all Primary | Lower size: stop and escalate |
| 11 | Check compute services and network agents are up | They depend on the bus | read-only | All up | Check their RabbitMQ connectivity first |
| 12 | Test VM: create, ping, delete | End-to-end capability check | state-changing (test resource) | All three succeed | Don't reopen the APIs. Escalate |
| 13 | Reopen the APIs in HAProxy | Restore service | state-changing | Requests succeed | Errors: pull the APIs again and escalate |
| 14 | Triage instances in BUILD or ERROR and leftover resources | Purge may have orphaned in-flight work (inferred) | read-only first | Triaged list | Any cleanup needs owner approval. TODO: define the procedure |

## Stop and escalate
**Stop if:**
- existing VMs become affected
- no Galera node is Primary, or the size can't be restored
- RabbitMQ won't re-form
- no approver is reachable for steps 4 to 9
- monitoring can't confirm a step's result

**Collect before escalating:** the preserved evidence, the steps taken with times, and any output that differed from expected.

**Escalate to:** TODO (on-call platform lead and the RabbitMQ/Galera expert).

## Do NOT do without escalation
- Reset or force-remove a RabbitMQ node, or purge queues, before confirming partition state and recording evidence. A wrong reset discards queues the services still use.
- Bootstrap Galera or force a node to Primary without a named decision-maker.
- Reopen the APIs before the test VM passes.
- Use purge and restart as a routine fix. Repeated recovery is not stability, so find the cause.

## Verification
- **End to end:** create, ping and delete a test VM, first before reopening the APIs and then again through the public endpoint.
- **Supporting checks:** RabbitMQ is consistent with consumers connected, Galera size and Primary are correct, and compute services and agents are up.
- **Recurrence monitoring:** TODO: define the alert and time window.

## Recovery
- If steps 5 to 10 fail, keep the APIs out of rotation and escalate. The step 2 evidence is your baseline.
- **Point of no return: step 6.** Purged messages can't be restored. The restarts in steps 7 and 9 can be repeated, but they may lengthen the outage.

## Follow-up
- Find why the partition happened, such as network events, host load and timing. The notes don't record this.
- Confirm the partition-handling mode is deliberate and documented.
- Add an alert that detects a partition early.

## History
| Date | Change | Why | By |
|---|---|---|---|
| 2026-10-25 | First draft from incident notes | Capture incident knowledge | TODO |

---

## Author notes
- **Sources:** your incident notes only. The step order and verification checks come from them. The reasons for each step, the decision table, the stop conditions, the do-not-do list and step 14 are my inference, not something the responders recorded.
- **Gaps (all marked TODO):**
  - commands and hostnames
  - restart order for RabbitMQ and MariaDB
  - the expected Galera size
  - whether any service restart was needed
  - how the partition was identified
  - who approved the original actions
  - timings
  - the partition cause
  - owner and escalation contacts
- **Validation plan:** someone who didn't write it should run it, observed and not helped. Use a non-production environment for the read-only parts and a rehearsal or maintenance window for the full run. Then correct the document from their questions. Who and when are still TODO.

> Decision support only. State-changing steps above require approval by the accountable owner and should be executed under your change process.

---

The notes don't say whether purging queues was a deliberate choice or a fallback. If it was a fallback, the runbook should probably say to try a plain RabbitMQ restart first. Can you ask the responders?