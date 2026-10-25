I couldn't save this as a file because the Write tool is disabled in this session, so the full runbook is below. It is a **draft that nobody other than the author has validated yet**.

# VM creation fails, existing VMs OK: RabbitMQ RPC broken and Galera unhealthy

**Status:** Draft, not yet validated. **Owner:** TODO. **Last validation:** never.

## Purpose and scope
- **Covers:** new VM creation fails while running VMs are fine, RabbitMQ RPC is broken, and Galera is unhealthy.
- **Root cause in the originating incident:** a RabbitMQ network partition.
- **Does not cover:**
  - Running VMs also failing. That is the data plane, so this is the wrong runbook.
  - A single RabbitMQ node that left a healthy majority with no partition events. That needs a lighter, node-level procedure (TODO: write or link it).
  - Galera with no Primary component. The notes don't cover bootstrap, so escalate.
  - VM creation failures when RabbitMQ and Galera are healthy, such as scheduler, quota or capacity problems.

## Context
- Running VMs survive because the hypervisor doesn't need RPC. Creating a VM needs the API, conductor, scheduler and compute path over RabbitMQ, plus the database. The failure therefore shows up only on new operations.
- The APIs are stopped first so no new requests arrive while queues are purged and brokers and the database restart.
- Purging queues discards in-flight messages, so it is the point of no return.
- **Caveat:** this is the sequence that worked once. The partition was recognised only afterwards. Whether the purge was needed, or a restart alone would have done, is unknown.

## Who may run it
- Section A (read-only) can be run by on-call.
- Section B (state-changing) needs the platform team and explicit approval from TODO: named approver.

## Preconditions
- Access to the RabbitMQ and Galera nodes, HAProxy admin, and admin OpenStack credentials.
- Preserve evidence **before** any restart:
  - RabbitMQ `cluster_status` from every node, and the logs showing partition events.
  - Galera status from every node.
  - `openstack compute service list` and `openstack network agent list` output.
- Notify stakeholders that new VM operations will be unavailable (TODO: channel).

## Decision points
| Check (read-only) | If you see | Go to |
|---|---|---|
| RabbitMQ `cluster_status` on every node, plus logs and partition-handling mode | Nodes disagree, a partition is listed, partition events in the logs, no majority, or an absent node of unknown cause | Section B, with approval |
| same | All nodes agree, one node absent, the rest a majority, no partition events | Out of scope: node-level procedure |
| Galera size and Primary status | Primary component exists | Continue; check again after RabbitMQ |
| same | No Primary on any node | **Stop and escalate** |

## Section A: Confirm and preserve (read-only)
1. Confirm a test VM create fails and an existing VM still responds.
2. Record the baseline of compute services and network agents. Many down at once points to messaging.
3. Capture RabbitMQ cluster status and logs on all nodes.
4. Capture Galera size and Primary status on all nodes.
5. Take the decision table and the evidence to the approver, and get approval in writing.

## Section B: Recovery (state-changing, approval required)
Do one action per step, and run the check before moving on.

| # | Action | Type | Expected result / if different |
|---|---|---|---|
| B1 | Stop the APIs and pull the backends from HAProxy | state-changing | No traffic reaches the APIs. If traffic still arrives, don't continue. |
| B2 | Purge the RabbitMQ queues (TODO: command and scope) | state-changing | Queues are empty. If errors, stop and escalate. |
| B3 | Restart the RabbitMQ cluster (TODO: order and method) | state-changing | One cluster, no partition. If a node won't rejoin, stop and don't reset it. |
| B4 | Check cluster status on every node, and check consumers | read-only | Same membership everywhere and consumers reconnected. If there are no consumers, ask whether services needed a restart (TODO). |
| B5 | Check Galera size and Primary | read-only | If it is not Primary, stop. |
| B6 | Restart MariaDB (TODO: nodes, order, method) | state-changing | The node rejoins and syncs. If not, stop and **do not bootstrap**. |
| B7 | Re-check Galera size and Primary on every node | read-only | Full size and Primary. |
| B8 | Check compute services and network agents are up | read-only | Matches the A2 baseline. |
| B9 | Run the end-to-end test (see Verification) **before** reopening the APIs | test | Passes. |
| B10 | Reopen the APIs in HAProxy | state-changing | Real calls succeed. If errors return, pull the APIs again and escalate. |

The notes don't say why MariaDB was restarted after RabbitMQ, or whether that order matters (TODO).

## Stop and escalate
- **Stop if:**
  - Any expected result doesn't occur.
  - A node won't rejoin, or a partition recurs.
  - Galera has no Primary.
  - You can't see logs or monitoring.
  - No approver is available.
  - Running VMs are affected.
- **Collect before escalating:** the preserved evidence, the step reached, and the last failing output.
- **Escalate to:** TODO.

## Do NOT do without escalation
- Don't purge or restart anything without approval.
- Don't reset or remove a RabbitMQ node. A wrong reset discards queues that services are still using.
- Don't bootstrap Galera or force a primary.
- Don't reopen the APIs before the test passes.
- Don't restart before capturing evidence.
- Don't edit database rows to "fix" stuck VMs.

## Verification
- Create a test VM, confirm it reaches ACTIVE, ping it, delete it, and confirm it is gone.
- Test parameters (project, network, flavor, image) are TODO.
- Also confirm Galera is Primary at full size, RabbitMQ agrees across nodes with consumers present, and compute services and network agents are up.

## Recovery
- If the procedure fails part-way, keep the APIs out of rotation, keep the evidence, and escalate. Don't repeat purge and restart in a loop.
- VMs that were mid-operation during the purge may be left in BUILD or ERROR. Find them afterwards (TODO: standard query) and handle them one at a time, with approval.

## History
| Date | Change |
|---|---|
| 2026-10-25 | Draft created from incident notes. |

---

## Author notes
- **Source:** your single paragraph of incident notes.
- **Inferred, not in the notes:**
  - The reasons behind each step.
  - The decision table.
  - The "preserve evidence first" precondition.
  - The Do NOT list.
  - The recovery notes about stuck VMs.
  - I gave no commands because the notes contain none. Any you add must be checked against your RabbitMQ, MariaDB/Galera and OpenStack releases and your deployment (containers or host).
- **TODOs for the people who handled the incident:**
  - Exact purge and restart commands and their order.
  - How the partition was recognised at the time.
  - Whether services needed restarting to reconnect.
  - Expected Galera size and consumer counts.
  - Test VM parameters.
  - Approver, owner and escalation contacts.
- **Validation plan:** someone other than the author runs it in non-production with a deliberately induced RabbitMQ partition. They should be observed but not helped. Correct the document from their questions, then record the date and validator. TODO: who, where, when.

> Decision support only. State-changing steps above require approval by the accountable owner and should be executed under your change process.

If you want a copy in the repo, say so once Write is available and I'll save it as `runbook-rabbitmq-partition-vm-create-failure.md`.