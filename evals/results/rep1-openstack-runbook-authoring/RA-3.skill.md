I can't write files in this session (the Write and Bash tools are disabled), so I couldn't publish the runbook as a page. Here it is in full, ready to paste into your wiki. It's marked **Draft, not yet validated**.

---

# Galera full outage recovery

**Status:** Draft, not yet validated
**Owner:** TODO (name a successor before Friday)
**Last validation:** never
**Review by:** TODO

Source: the departing expert's note, "find node with highest seqno, bootstrap it, start the others". Everything else below is general Galera knowledge I added to explain and safeguard that sentence. It is not taken from your platform. Commands and paths are examples to check against your MariaDB/Galera versions and deployment tool.

> **Read first:** bootstrapping the wrong node, or two nodes, silently discards committed data. The other nodes copy the bootstrapped node's data over their own. Once that has happened you can't undo it. Get approval before the bootstrap (Section B).

## Purpose
Bring Galera back when no node is serving as a Primary component, for example after a power loss, a simultaneous crash, or all nodes being stopped. The aim is no committed transactions lost, then verified end to end through OpenStack.

## Scope
**Covers:** all DB nodes are down, or every running node reports `wsrep_cluster_status` other than `Primary`.

**Does not cover:**
- **One node down while the others are Primary.** Start that node normally and let it resync. Do not bootstrap. TODO: link the single-node rejoin runbook, or confirm there isn't one.
- **A network partition** where nodes are alive but can't see each other (possible split brain). Stop and escalate.
- **Corruption, disk failure or restoring from backup.** TODO: link the backup/restore procedure.
- **RabbitMQ, Ceph and other dependencies.**

## Context: why it works this way
- **Highest seqno:** every node applies every committed transaction, tagged with a sequence number (seqno). After a full outage, only the highest-seqno node is guaranteed to hold them all.
- **Only one node is bootstrapped:** two bootstrapped nodes form two separate clusters with diverging data.
- **`safe_to_bootstrap` in `grastate.dat`:** Galera 3.19 and later refuses to bootstrap a node that wasn't the last to leave cleanly. Forcing it is a statement that a human compared positions.
- **seqno `-1`:** the node crashed before writing its position. Recover it from the storage engine (step A3).
- **OpenStack services stay stopped until the DB is verified:** they retry aggressively and may write to a node that is about to be overwritten.
- TODO, ask the expert: local exceptions (custom `wsrep_provider_options`, garbd arbitrator, SST method, load balancer behaviour) and what was tried in past outages and failed.

## Who may run it
- **Read-only sections:** trained on-call operator.
- **Sections B and C (bootstrap and start):** DB/platform specialist. TODO: name the roles.
- **Approval for the bootstrap:** TODO: named role that can accept possible data loss, plus a deputy.

## Preconditions
- You can log in to **every** DB node. If one is unreachable you can't know whether it holds the highest seqno, so stop.
- Topology is known: node names, count, arbitrator. TODO: not provided.
- Deployment tool and how it starts the DB. TODO: confirm. Kolla-Ansible, for example, has its own MariaDB recovery action; verify before using it.
- Storage and network between nodes are healthy.
- Disk space for a copy of the data directory (B2) and for SST.
- Preserve before changing anything: DB error logs from every node, copies of `grastate.dat` (and `gvwstate.dat` if present), and the time and cause of the outage as far as known.
- Credentials come from TODO: secret store. Never paste them into tickets or chat.

## Decision point
| Check (read-only, every node) | If you see | Go to |
|---|---|---|
| `SHOW STATUS LIKE 'wsrep_cluster_status'` | At least one node is `Primary` | **Stop, this isn't a full outage.** Start down nodes one at a time (Section C only). No bootstrap. |
| Same, plus network checks between nodes | All nodes down, or all running nodes non-Primary, and you've confirmed no partition | Section A |
| Same | Nodes running but unable to reach each other, or you're unsure | **Stop and escalate** (possible split brain) |
| Positions from Section A | Cluster UUIDs differ, or a node's position can't be determined | **Stop and escalate** |
| Reachability | Not all nodes reachable | **Stop and escalate.** Proceeding without all positions is the approver's call. |

## Procedure

### Section A: collect each node's position
Do this on every node while all DB processes are stopped.

| # | Action | Why | Type | Expected | If different |
|---|---|---|---|---|---|
| A1 | Confirm no DB process is running on any node | Positions read from a running node can mislead | read-only | No mysqld/mariadbd anywhere | Re-run the decision table |
| A2 | Copy out and record `grastate.dat` (usually in the data dir, e.g. `/var/lib/mysql/`; verify). Note `uuid`, `seqno`, `safe_to_bootstrap` | A clean shutdown writes the last position here | read-only | Same uuid on all nodes | Different uuids, or file missing/empty: stop and escalate |
| A3 | For any node with `seqno: -1`, recover its position, e.g. `mysqld --wsrep-recover` (run as the DB user with the node's real config; read the `Recovered position: <uuid>:<seqno>` line; verify the invocation, including inside containers) | After a crash the file has no position | state-changing, low risk (may run InnoDB crash recovery) | Same uuid as in A2 | Errors or no position: stop and escalate. Don't delete files to get past it. |
| A4 | Record a table of node, uuid, seqno and source in the incident record | The approver must be able to review the decision | read-only | No blanks | Any blank: don't continue |
| A5 | Pick the candidate: highest seqno. On a tie, any of the tied nodes is fine; prefer `safe_to_bootstrap: 1` and note why | It holds every committed transaction | read-only | One named candidate | If the gap is large or unexplained, ask the approver |

### Section B: bootstrap the candidate
**Approval gate:** the named approver has seen the A4 table and agrees with the candidate. Record their name. Before this section, stop the OpenStack services that use this DB (TODO: exact list and command). Confirm the load balancer isn't sending traffic to the DB nodes. API calls and provisioning will fail while this is in place. Running instances usually keep running, but verify that for your storage backend.

| # | Action | Why | Type | Expected | If different |
|---|---|---|---|---|---|
| B1 | Confirm all other DB nodes are still stopped | Prevents two clusters | read-only | None running | Stop them, redo Section A for them |
| B2 | On the candidate, copy the data directory aside if space allows. Recommended: do the same on every node. TODO: the original note doesn't say this, so DB owner to decide | Later steps overwrite the other nodes | state-changing (adds a copy) | Copy completes, sizes match | No space: tell the approver. Don't delete anything to make room. |
| B3 | Only if `safe_to_bootstrap` is `0` on the candidate, set it to `1` in its `grastate.dat` | Galera refuses otherwise | state-changing | One line changed on one node | Never do this on any other node |
| B4 | Start the candidate in bootstrap mode, e.g. `galera_new_cluster`, `mysqld --wsrep-new-cluster`, or the deployment tool's recovery action. TODO: confirm the local command | Forms the Primary component | **point of no return** once other nodes join | New cluster, expected UUID in the log | Start fails: don't touch other nodes; collect the log and escalate |
| B5 | On the candidate check `wsrep_cluster_size`, `wsrep_cluster_status`, `wsrep_local_state_comment`, `wsrep_ready` | Confirm health before adding nodes | read-only | Size 1, `Primary`, `Synced`, `ON` | Otherwise don't start other nodes; escalate |
| B6 | Sanity-check recent data in a few OpenStack databases. TODO: define 2–3 concrete checks | Confirms the right node was chosen | read-only | Recent data present | Data older than expected: stop before any other node starts; escalate |

### Section C: start the remaining nodes, one at a time
Joiners catch up either from a cache of recent changes (IST) or by a full copy (SST). **SST overwrites the joiner's data directory** and may slow the donor. TODO: record your SST method and its donor impact.

| # | Action | Why | Type | Expected | If different |
|---|---|---|---|---|---|
| C1 | Start the next node with the normal start (not bootstrap) | It joins the existing Primary | state-changing | Log shows it joining | If it says it's forming its own cluster, stop it and escalate |
| C2 | Wait for `Synced` and cluster size +1; watch logs on donor and joiner | Starting several at once overloads the donor | read-only | Joining, Joined, Synced. TODO: record typical time from a real run | No progress past the agreed limit (TODO: set), or SST errors: stop, don't start more nodes, escalate |
| C3 | Repeat for each remaining node | One at a time | state-changing | Cluster size reaches expected count | As above |

### Section D: verify, then restore services
| # | Action | Why | Type | Expected | If different |
|---|---|---|---|---|---|
| D1 | On every node: cluster size is the expected count, `Primary`, `Synced`, `wsrep_ready=ON`, same `wsrep_cluster_state_uuid` | Process up is not cluster healthy | read-only | All true | Any mismatch: don't restore services |
| D2 | Load balancer shows nodes healthy and routes writes as designed. TODO: how your deployment does this | Services reach the DB through it | read-only | Pool as designed | Fix before services start |
| D3 | Check the message bus is healthy, then start OpenStack services in the required order. TODO: write the order and command | Dependencies | state-changing | Services up | DB errors: stop services, return to D1 |
| D4 | Create, reach and delete a test VM; confirm the test objects are gone | Verify the capability, not the process | state-changing (test objects) | VM ACTIVE, reachable, deletes cleanly | Failure: investigate the failing service; the DB is verified |
| D5 | List instances and operations stuck in transitional states from the outage. Don't fix them by hand in the DB | In-flight work may be half done | read-only | List for owners to review | Anything needing direct DB edits: escalate |

## Stop and escalate
**Stop if:**
- any node is unreachable
- UUIDs differ
- a position can't be recovered
- the candidate's data is older than expected
- you suspect a partition or a node still serving
- a joiner forms its own cluster, or SST fails or stalls
- monitoring or logs are blind
- the approver is unavailable

Stopping is not failing. Leave the cluster as it is; restarting later is a new decision.

**Collect before escalating:**
- the A4 table
- all `grastate.dat` copies
- logs from every node
- what you ran, in order, with timestamps
- current `wsrep_*` status

**Escalate to:** TODO: DB owner, deputy and incident lead, with contact route.

## Do NOT do without escalation
- Bootstrap more than one node, or a node that isn't the highest-seqno candidate.
- Set `safe_to_bootstrap: 1` on several nodes, or on a node whose position you didn't compare.
- Start all nodes at once.
- Delete `grastate.dat`, the Galera cache, or any data directory to make a node start. This forces a full SST and discards that node's copy.
- Restore from backup before escalating.
- Hand-edit OpenStack tables to fix state.
- Start OpenStack services before D1 passes.
- Paste credentials anywhere.

## Recovery if this fails
- **Before B4 completes and nobody has joined:** stop the candidate and escalate. Data is unchanged apart from the B3 line, which can be reverted.
- **After other nodes began SST:** their old data is gone. If the candidate was wrong, data held only by overwritten nodes is lost unless it was copied in B2.
- **Candidate won't start or is corrupted:** escalate. Trying the next-highest node or restoring a backup are the approver's decisions, with the data-loss cost stated. TODO: record backup location, frequency and last tested restore.

## History
| Date | Change | Why | By |
|---|---|---|---|
| 2026-10-25 | First draft from a one-line expert note | Expert leaves Friday | Claude, for review |
| TODO | Past outages, failed attempts, local exceptions | Capture from the expert | |

## Author notes
- **Sources:** the one-line note (reported, not shown) plus general Galera knowledge. Nothing here was checked against your systems.
- **Unknown, left as TODO:**
  - node names and count, arbitrator
  - deployment tool, SST method, load balancer
  - service start order
  - backups
  - owners and approver
  - timings
  - local quirks
- **Ask the expert before Friday:**
  - What went wrong in past outages?
  - Did they ever bootstrap a node that wasn't the highest, and why?
  - What do they check that isn't written down anywhere?
- **Validation plan:** someone who didn't write this, and isn't the expert, runs it in a non-production Galera cluster while the expert observes without helping. They kill all nodes, then recover. Include a variant with one node missing and one with seqno `-1`. Fix the document from every question they raise. Until then it stays Draft. TODO: assign executor, observer and date.

> Decision support only. State-changing steps above require approval by the accountable owner and should be executed under your change process.

---

If you'd like it as a shareable page, re-enable file writing and I'll publish it. The most valuable next step is an hour with the expert, going through the TODO list before Friday.