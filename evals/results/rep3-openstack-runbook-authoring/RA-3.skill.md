I couldn't save a file because the Write tool is disabled in this session, so the runbook is below. It's a **draft that hasn't been validated**. His note is the only source I had. The rest is general Galera behaviour added to explain and safeguard that one line. I wrote it without access to your systems. Commands, paths and variable names are examples to verify for your MariaDB version and deployment tool. Facts only you have are marked `TODO`.

---

# Galera full outage recovery (all nodes down)

**Status:** Draft, not yet validated. **Owner:** TODO (name someone who isn't the departing expert). **Last validation:** never.

## Purpose
Bring Galera back when no node is serving, without losing committed transactions and without creating two diverging clusters.

## Why "highest seqno, bootstrap it" is the whole procedure
- After a full outage the nodes can differ by their last few transactions.
- The **seqno** is the last transaction a node committed, in the cluster's global order. The highest seqno marks the most recent data.
- Bootstrapping forms a new cluster from that node's data. The other nodes then copy from it (IST or SST) and overwrite their own state.
- If you bootstrap a node with a lower seqno, you silently discard committed transactions that exist only on the others. This is the main risk.

## Scope
**Covers:** every node is down, or none is in Primary state.

**Does not cover** (stop and escalate):
- One node down while the others are still Primary. Restart that node and let it rejoin. No bootstrap.
- Split-brain, or nodes non-Primary while others are running.
- Suspected corruption or disk loss on several nodes.

## Context (all TODO)
- Node count and hostnames.
- Deployment tool, and whether MariaDB runs as a package or in containers.
- What sits in front of the database (HAProxy or similar).
- Which OpenStack services use the database.
- Backup location, last successful date, last restore test.
- Any node with deliberately unusual config.
- Whether a garbd arbitrator exists.

## Who may run it
- **Phases 1–2 (read-only):** the on-duty operator.
- **Phase 3 (state-changing):** a DB-capable platform engineer, **after approval by TODO: named role**. This is a database intervention with possible data loss.

## Preconditions
- Every node is confirmed stopped. Bootstrapping while another node serves creates two clusters.
- You have access to **every** node, including ones that look dead.
- You know why the cluster went down, so it won't just crash again. If you don't, escalate before bootstrapping.
- Evidence is preserved first. Copy `grastate.dat` and the MariaDB error log from every node. Record the stop order and times. If space allows, copy the chosen node's datadir. TODO: confirm paths and feasibility.

## Decision points
| Check (read-only) | If you see | Go to |
|---|---|---|
| Process, unit or container status on all nodes | Any node running and Primary | Not a full outage. **Stop.** |
| `grastate.dat` on each node | Numeric seqno on all, uuid identical | Phase 2 step 3 to confirm |
| same | `seqno: -1` on any node (unclean stop) | Recover the real seqno (Phase 2 step 3) |
| same | uuid differs between nodes | **Stop and escalate.** The nodes may have different histories. |
| Recovered seqnos | Tie for highest | Prefer the node with `safe_to_bootstrap: 1`, otherwise the one that stopped last. Record who approved the choice. |
| Any node unreachable, or its seqno unknown | You can't prove which is highest | **Stop and escalate.** Don't guess. |

## Procedure

**Phase 1: confirm the outage (all read-only)**
1. Check that MariaDB isn't running on any node. Expect all stopped. If one is running, check `wsrep_cluster_status`. If it's Primary, stop.
2. Check that the load balancer has no healthy database backend and nothing is still writing.
3. Identify the cause: disk, OOM, network, host reboot. If the cause is unknown, escalate.

**Phase 2: find the most advanced node (read-only on the cluster)**
1. Read uuid, seqno and `safe_to_bootstrap` from `grastate.dat` on each node. If the uuids differ, stop.
2. Save copies of `grastate.dat` and the error logs.
3. For any node showing `-1`, or whenever in doubt, recover the position without joining a cluster, for example `mysqld --wsrep-recover`. Read the `Recovered position: <uuid>:<seqno>` line. On containerized deployments use your tool's documented method. TODO: the expert should confirm the exact command and that it's safe on your version.
4. Fill in a table of node, uuid, seqno, `safe_to_bootstrap` and how it stopped. **A second person checks it.**
5. **Approval gate:** the approver records the chosen node and signs off on Phase 3.

**Phase 3: bootstrap and rejoin (all state-changing)**
1. On the chosen node only, if `safe_to_bootstrap` is 0, set it to 1 or use your tool's documented force option.
2. Start that node as a new cluster, for example `galera_new_cluster`. TODO: the exact method for your deployment tool. If it fails, read the log. Don't switch to another node without approval.
3. Verify (read-only):
   - `wsrep_cluster_size` = 1
   - `wsrep_cluster_status` = Primary
   - `wsrep_local_state_comment` = Synced
   - `wsrep_ready` = ON
4. Start the second node normally, with no bootstrap flag. Wait until it is Synced and the cluster size is 2.
5. Add the remaining nodes **one at a time**. Several simultaneous SSTs can overload the donor. Stop at the first failure.
6. TODO: confirm whether to restart the bootstrapped node normally afterwards, so it isn't left with "new cluster" start state.

**Phase 4: bring services back**
TODO: the order for your platform. Re-enable load-balancer backends one at a time once each node is Synced, then start dependent OpenStack services.

## Stop and escalate
Stop if any of these happens:
- A node is already running Primary.
- Any seqno is unknown, or a node is unreachable.
- The uuids differ.
- The disk is full, or InnoDB corruption messages appear.
- The chosen node won't start alone.
- The approver is unavailable.
- You can't see the status variables.

Before escalating, collect all `grastate.dat` copies, the recovered seqnos, error logs from every node, a timeline, and exactly what was already run.

**Escalate to:** TODO (a named DB owner after Friday, plus any vendor or support contact).

## Do NOT do without escalation
- Bootstrap a node because it "was last up" without comparing seqnos on every node.
- Bootstrap two nodes, or bootstrap while any node is running.
- Delete `grastate.dat`, the InnoDB logs, or the datadir to force a start. That can destroy the only copy of the newest data.
- Set `safe_to_bootstrap` on a node that wasn't chosen in Phase 2.
- Start all the remaining nodes at once.
- Restore a backup instead of recovering. That loses everything since the backup.

## Verification (end to end)
1. On every node: the expected cluster size, Primary, Synced, ready, and the same `wsrep_cluster_state_uuid`.
2. Write a test row on one node and read it on another. TODO: define a scratch database.
3. Issue a Keystone token, list servers, and create, reach and delete a test VM. TODO: define the test project, image and network.
4. Check monitoring and application errors for an agreed period. TODO: how long.

## Recovery if it fails
- **Before Phase 3 step 2:** nothing has changed except possibly `safe_to_bootstrap`. Restore your saved `grastate.dat` copy.
- **After other nodes have joined a wrongly chosen donor:** this is the **point of no return**, because they were overwritten. Stop and escalate. Recovery would rely on the pre-bootstrap datadir copies or backups, and the owner decides what to do about the lost transactions.
- **If the data looks wrong afterwards:** stop the services writing to the database, then escalate.

## Known failed approaches
TODO: ask him what has been tried before that didn't work (SST problems, timeouts, version bugs).

## History
| Date | Change | Why | By |
|---|---|---|---|
| 2026-10-25 | Draft from one-line note plus general Galera knowledge | Expert leaving Friday | Claude, unvalidated |

## Author notes
- **Inferred and unconfirmed:** the command forms, file paths, status variable names, the one-at-a-time rule, and the Phase 4 order.
- **Questions for him before Friday:**
  - What are the topology and deployment tool, and what is the exact bootstrap command in it?
  - How do the backups and the load balancer work?
  - What is the service stop/start order?
  - What went wrong in past outages?
  - What does he do "without thinking" that isn't in the note? Ask him to narrate a real or simulated outage while someone writes it down.
  - Who approves, and who owns this runbook?
- **Validation plan:** another engineer runs it on a non-production Galera cluster, or during real maintenance, with the expert watching but not helping. They stop all nodes, find the highest seqno, bootstrap, and rejoin. Inject one difficulty, such as a `-1` node or a tied seqno. Fix the runbook from every question they ask. Then record the date and executor, and repeat with a second person.

> Decision support only. State-changing steps above require approval by the accountable owner and should be executed under your change process.

---

Do you want me to publish this as a private page you can share with the team? Since Write is blocked here, I'd need to build it another way, so say if you want that.