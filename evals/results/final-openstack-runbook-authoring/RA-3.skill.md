I couldn't save a file because file writing is disabled in this session, so the runbook is below. It is marked **Draft, not yet validated**.

The expert's note covers three actions. I added the surrounding structure (decision points, stop conditions, verification, recovery) from general Galera behaviour, not from your platform. The commands are examples to verify for your MariaDB/Galera version and deployment tool. Everything your platform specifics would fill in is marked `TODO`.

---

# Galera full cluster outage: recovery

**Status:** Draft, not yet validated
**Owner:** TODO. Name a successor before Friday.
**Last validation:** never

## Purpose
Restart the Galera cluster behind the OpenStack control plane after all DB nodes are down. The goal is to lose no committed transactions and not end up with two diverging copies of the data.

## Scope
**Covers:** every node is stopped or unusable, or there is no primary component.

**Does not cover:**
- **One node down while others are Primary.** That is a normal rejoin, not a bootstrap. TODO: link a rejoin procedure.
- **Split cluster (two components).** Stop and escalate.
- **Corruption, disk loss or restore from backup.** TODO: link the backup/restore runbook.

## Why it works this way
- After a full outage no node knows which one committed last. Bootstrapping a node that is behind makes its state the truth, and transactions only the more advanced node held are lost. That is why the rule is "highest seqno".
- Bootstrap means "form a new cluster alone". Do it on exactly one node, once.
- After a clean shutdown the position is in `grastate.dat`. After a crash it is usually `seqno: -1`, so recover it with `mysqld --wsrep-recover`. Recent versions also have a `safe_to_bootstrap` flag. Verify all of this for your version.
- TODO (expert): how Galera is deployed here (Kolla containers, packages or Pacemaker), data dir, node count, arbitrator, load balancer, local config exceptions, and past outages and what went wrong.

## Who may run it
- **Read-only checks:** platform on-call.
- **Bootstrap and anything forced:** a DB-capable engineer, approved by TODO (a named role that accepts possible loss of recent transactions). A second person reads the evidence aloud before the bootstrap.

## Preconditions
- Confirm every node is actually down (Step A). Don't trust the alert alone.
- Access to all DB nodes and logs. TODO: out-of-band access if the control plane is down.
- Know how to keep clients off the DB until verification passes (TODO: load balancer/VIP behaviour).
- **Preserve evidence first.** Copy each node's DB error log and `grastate.dat`, and record the time and every command and its output. Consider a snapshot or copy of each data dir (TODO: is this feasible here?).

## Business impact
- The control plane is effectively down while the DB is down. That means no provisioning and probably no logins.
- Running instances normally keep running. Verify for your storage and network backend.
- Decide with the incident lead whether to stop the API and conductor services so they don't hammer a half-formed cluster. TODO: service list and order.

## Procedure

### A. Is this really a full outage? (read-only, every node)
| You see | Do |
|---|---|
| All nodes stopped | Go to B |
| Some running and none Primary (`wsrep_cluster_status`) | Go to B, and read those nodes' positions too |
| Any node Primary | **Stop.** This is a rejoin, not this runbook. |
| Running nodes with different cluster views | **Stop and escalate.** Possible split-brain. |
| A node unreachable | **Stop and escalate.** You can't compare positions you can't read. |

### B. Find the most advanced node (read-only, DB stopped)
1. On each node read `grastate.dat` (for example `/var/lib/mysql/grastate.dat`; TODO: real path). Note `uuid`, `seqno` and `safe_to_bootstrap`.
2. If `seqno` is `-1`, run `mysqld --wsrep-recover`, or the equivalent in the container, and read the `Recovered position: <uuid>:<seqno>` line. If it fails, read the error log before doing anything else.
3. Record this table:

| Node | uuid | seqno | safe_to_bootstrap | Notes |
|---|---|---|---|---|

4. Decide:

| Observation | Action |
|---|---|
| One clear highest seqno, same uuid everywhere | Bootstrap that node |
| Tie for highest | Any tied node is equally current. Prefer `safe_to_bootstrap: 1`. TODO: expert's preference. |
| **Different uuids** | **Stop and escalate** |
| A node's position can't be read | **Stop and escalate.** The approver decides. |
| The highest seqno is on an unreachable node | **Stop and escalate.** Waiting is usually cheaper than losing data. |

### C. Bootstrap the chosen node
| # | Action | Type | Expected | If not |
|---|---|---|---|---|
| C1 | Second person confirms the table and the choice, and the approver says go | read-only | Chosen node recorded | Any doubt: stop |
| C2 | Re-check that no other DB node is running | read-only | All others stopped | Stop and escalate |
| C3 | Only if the node is established as the most advanced and has `safe_to_bootstrap: 0`, set it to `1` on **that node only** (verify the method for your version) | state-changing | Flag is 1 on one node | Never on a node whose position you haven't read |
| C4 | Start it as a new cluster, for example `galera_new_cluster` or your deployment tool's recovery action. **TODO: exact command. The note doesn't say.** | state-changing | Forms a one-node Primary | Read the log. Stop if it crashes or reports a different uuid. |
| C5 | Check `wsrep_cluster_size` is 1, `wsrep_cluster_status` is `Primary`, `wsrep_local_state_comment` is `Synced` | read-only | 1 / Primary / Synced | Not Primary: don't start the others |

### D. Start the others, one at a time
| # | Action | Type | Expected |
|---|---|---|---|
| D1 | Start one node normally (not bootstrap) | state-changing | Joins, and the cluster size rises by 1 |
| D2 | Wait for `Synced` (TODO: expected sync time for your DB size) | read-only | Synced |
| D3 | Repeat for each remaining node | state-changing | Size equals the node count |

If a node won't join, read its log and don't start the next one. Don't wipe its data dir without escalation.

## Stop and escalate
**Stop if:**
- A node can't be reached or read.
- The uuids differ.
- A node is unexpectedly Primary.
- The chosen node doesn't reach Primary/Synced.
- Logs show corruption, disk-full or I/O errors.
- Monitoring is blind.
- The approver is unavailable and the choice isn't clear-cut.

**Collect before escalating:** the position table, `grastate.dat` and logs from every node, exact commands and output, and what changed before the outage (power, network, upgrade, restart).

**Escalate to:** TODO. The departing expert must not be the only contact.

## Do NOT, without escalation
- Bootstrap more than one node, or bootstrap while any other node runs.
- Bootstrap a node because it came up first or because the alert named it. Compare positions.
- Force `safe_to_bootstrap: 1` on a node whose position you haven't read.
- Delete a data dir or `grastate.dat`, or force an SST, to make a node join. That can destroy the only other copy.
- Run direct DB edits before the cluster is healthy.
- Start OpenStack services against the DB before verification passes.
- Retry "to see if it works". A retry is a new decision.

## Verification (capability, not process)
1. Every node is `Primary` and `Synced`, the cluster size is correct (TODO), and writes are accepted.
2. The load balancer sends traffic to a Synced node.
3. Start the OpenStack services in the agreed order (TODO).
4. Authenticate, list resources, then create, reach and delete a test VM (TODO: test flavor/image/network).
5. Watch for DB deadlocks, instances stuck in transitional states and messaging reconnects. Triage those separately.

## Recovery if it fails
- **C4/C5 fails:** leave the others stopped, preserve the logs and escalate. Don't try another node until you understand why, because each bootstrap attempt changes state.
- **A node won't join (D):** the cluster runs on fewer nodes. Check quorum (TODO: node count and arbitrator). Escalate before wiping that node.
- **Wrong node bootstrapped:** stop writes by stopping the API services, preserve all data dirs and escalate. TODO: whether binlogs or backups can recover the lost transactions.
- **Point of no return:** once the bootstrapped node accepts writes and the others sync from it, its starting position is the truth. Anything held only by another node is gone unless you kept copies.

## History
| Date | Change | Why |
|---|---|---|
| 2026-10-25 | First draft from a one-line note | Expert leaving Friday |

Approaches tried that didn't work: TODO, ask the expert.

---

## Author notes
**Sources:**
- The expert's one-line note.
- General Galera behaviour (`grastate.dat`, `wsrep_recover`, `safe_to_bootstrap`, `galera_new_cluster`, status variable names, one-at-a-time joins).
- I invented no hostnames, paths or timings.

**Gaps, and who can close them:**

| Gap | Who |
|---|---|
| Deployment tool, real commands, paths, node count, arbitrator, load balancer | Expert, before Friday |
| Tie-break preference, local config exceptions, past failures | Expert |
| OpenStack service order, test-VM prerequisites | Platform team |
| Approver role, escalation contacts, successor owner | Management |
| Backup/restore and rejoin procedures | DB owner |

**Validation plan:**
- Have an engineer who didn't write it run it on a non-production cluster of the same version and deployment method, with the expert watching but not helping.
- Cover three cases: a clean full stop, a hard kill of all nodes (`seqno -1`), and one with an unreachable node.
- Fix the document from every question they ask.
- Do this before Friday, then record the date and executor in the header.

> Decision support only. State-changing steps above require approval by the accountable owner and should be executed under your change process.

---

**Before Friday, I'd use the expert's remaining time on two things.** Ask them to fill the TODOs, especially the exact bootstrap command and the tie-break preference. Then have them watch someone else run the procedure on a test cluster.

If you want the runbook as a file or a shareable page, I can do that in a session where writing files is enabled.