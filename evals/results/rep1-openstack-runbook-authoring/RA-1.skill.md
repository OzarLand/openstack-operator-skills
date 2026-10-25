I couldn't save a file because the Write tool is disabled in this session, so the runbook is below. It's a draft built only from your notes. I left out commands, hostnames and timings that the notes didn't give, and marked them TODO.

---

# Runbook: VM creation fails, existing VMs fine (RabbitMQ partition, Galera unhealthy)

**Status:** Draft, not yet validated. **Owner:** TODO. **Last validated:** never.

## Purpose and scope
- **Purpose:** restore VM provisioning when RabbitMQ RPC is broken and Galera is unhealthy, while protecting running VMs and platform state.
- **Covers:** new VM creation fails, existing VMs keep working, RPC is broken, and both RabbitMQ and Galera are unhealthy. The root cause in the incident was a RabbitMQ network partition. It was found only after recovery.
- **Does not cover:**
  - One node that left an otherwise healthy RabbitMQ cluster (no partition). That needs a node-level rejoin, not a purge. TODO: write that runbook.
  - Galera unhealthy with RabbitMQ healthy. TODO: separate runbook.
  - Running VMs that are down or unreachable. Never evacuate from this runbook.

## Context
- Running VMs were unaffected because the control plane and data plane fail separately. Pulling the APIs is deliberate degradation: it suspends new provisioning to protect state. Verify this for your backends.
- **Hypothesis, not established:** the partition caused the Galera problem, or both share a network cause. The notes don't say. TODO: ask the responders.
- This runbook runs the partition check first. In the incident the partition was identified last.

## Who may run it
- **Read-only checks:** first-line operations.
- **State-changing steps:** the platform team, each approved by TODO: a named role who accepts the loss of provisioning and the loss of in-flight messages.

## Preconditions
- **Access:** HAProxy, the RabbitMQ and Galera nodes, and an admin credential from the secret store. Never paste credentials into tickets.
- **Monitoring:** if you are blind, that is a stop condition.
- **Evidence to save before any change:**
  - RabbitMQ logs from every node, including partition and autoheal events.
  - `cluster_status` from every reachable node.
  - Galera status from every node, and the MariaDB error logs.
  - The time of the first failure.
  - A list of instances stuck in BUILD or ERROR.
- **Platform facts to fill in:** RabbitMQ partition-handling mode (`ignore`, `pause_minority` or `autoheal`), the vhosts in `transport_url`, node counts, and the deployment tool. TODO: platform owner.

## Decision points (all read-only, on every node)
| Check | You see | Go to |
|---|---|---|
| RabbitMQ status, logs, partition mode | Nodes disagree, a partition is listed, or partition/autoheal events appear in the logs | **Procedure** (this incident) |
| same | One node absent, the rest agree and form a majority, no partition events | Out of scope. Don't purge. |
| same | No majority, or an absent node's cause is unknown | Procedure, and escalate immediately |
| Galera size and Primary state | Smaller than expected, or any node non-Primary | Record it and continue |
| same | No node is Primary | **Stop. Don't restart MariaDB. Escalate.** |

## Procedure
| # | Action | Why | Type | Expected | If different |
|---|---|---|---|---|---|
| 1 | Confirm a test create fails and running VMs still respond | Confirms a control-plane-only failure | read-only | Create fails or sticks; running VMs reachable | Running VMs affected: **stop**, wrong runbook |
| 2 | Save the evidence listed above | Restarts destroy the evidence, and the cause was found late last time | read-only | Files saved off the nodes | Tell the approver what couldn't be saved |
| 3 | Run the decision checks | Partition and node loss need different handling | read-only | Findings recorded with timestamps | Treat an unreachable node as unknown, not dead |
| 4 | Get approval to suspend provisioning | Pulling the APIs affects every API user | decision | Approval recorded (who, when) | No approver: escalate |
| 5 | Remove the APIs from HAProxy | Stops new state while the bus and DB are repaired | **state-changing** | API backends down | Traffic still arrives: look for other entry points (TODO: list them) |
| 6 | Purge the RabbitMQ queues | Clears RPC messages stuck by the partition | **state-changing, destructive** | Queues empty | Check every vhost the services use. TODO: exact scope and command |
| 7 | Restart the RabbitMQ cluster | Re-forms one consistent cluster | **state-changing** | One cluster, no partition | Nodes still disagree: **stop**, escalate. TODO: node order and method |
| 8 | Restart MariaDB | Return Galera to healthy | **state-changing** | Size equals node count, all Primary and Synced | Cluster won't re-form: **stop**. TODO: node order, bootstrap needs, and why this step was needed (not in the notes) |
| 9 | Check Galera size and Primary on every node | Verify the DB before reopening | read-only | As above | See step 8 |
| 10 | Check the RabbitMQ cluster and that consumers are attached | A running cluster with no consumers still breaks RPC | read-only | One cluster, consumers present | Missing consumers: TODO, no service restarts are recorded in the notes |
| 11 | Check compute services and agents are up | Their heartbeat travels over the bus | read-only | All up | Investigate before reopening |
| 12 | Create, ping and delete a test VM | End-to-end check before exposing the cloud | state-changing (test VM) | ACTIVE, answers ping, deleted | Failure: keep the APIs closed and escalate |
| 13 | Re-add the APIs to HAProxy | Restore service | **state-changing** | Backends up, requests succeed | Errors rise: pull them again |
| 14 | Repeat the test VM check through the normal path and watch the logs for partition events | Repeated recovery isn't stability | read-only | Clean for TODO: observation period | Recurrence: escalate |
| 15 | List instances stuck from the outage and agree their handling with the owner | Purged messages mean those requests never complete | read-only | List shared with the approver | No mass deletes or state resets without approval |

## Stop and escalate
- **Stop if:**
  - running VMs are impacted
  - there is no RabbitMQ majority, or nodes still disagree after a restart
  - Galera has no Primary component, or a node won't rejoin
  - monitoring is down, or the approver is unreachable
  - the test VM still fails
- **Collect first:** the saved evidence, plus the steps taken with timestamps.
- **Escalate to:** TODO.

## Do NOT do without escalation
- Reset or force-boot a RabbitMQ node, or forget a cluster node.
- Bootstrap Galera or force a node to be the source.
- Purge or restart before the evidence is saved and approval is given.
- Evacuate hosts or restart compute services because they show as "down" during a bus outage.
- Edit the database directly to fix stuck instances.
- Reopen the APIs before the test VM passes.

## Verification
A test VM is created, reaches ACTIVE, answers ping and is deleted, after the APIs are reopened. Galera, RabbitMQ and agent checks support this but don't replace it.

## Recovery
- If any step fails midway, keep the APIs out of HAProxy. Existing VMs keep running and provisioning stays suspended. Escalate from there.
- **Point of no return:** the queue purge (step 6). The discarded messages can't be recovered.

## History
| Date | Change | Why | By |
|---|---|---|---|
| TODO | Created from incident notes | Partition incident | TODO |

Approaches tried that didn't work: none recorded. TODO: ask the responders.

---

## Author notes
- **Source:** your one-paragraph summary. The actions, order, checks and root cause come from it. These parts are my additions: the decision table, approvals, stop conditions, do-not-do list, evidence preservation, and step 15.
- **Gaps to close with the responders:**
  - Commands and node order.
  - Why MariaDB was restarted, and whether Galera was a cause or a consequence.
  - The partition-handling mode.
  - How the stuck instances were handled.
  - The observation period.
  - Owner, approver and escalation contacts.
  - Any other ways into the APIs.
- **One thing to review:** the incident purged queues before the cause was known. The purge can't be undone, so the runbook puts evidence and approval ahead of it.
- **Validation:** TODO. Someone who wasn't in the incident should run it in non-production (simulate a partition) or during a maintenance window. They should be observed but not helped, and the runbook should be corrected from their questions. Until then it stays Draft.

> Decision support only. State-changing steps above require approval by the accountable owner and should be executed under your change process.

---

If you want this saved as a file or published as a page, tell me where. I'd also fill in the TODOs with the people who handled the incident first.