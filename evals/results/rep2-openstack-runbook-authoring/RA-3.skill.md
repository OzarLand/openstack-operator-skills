I couldn't save this as a file because Write is disabled in this session, so the runbook is below. It's a **draft, not validated**. Your expert's note has only the three clauses, so everything else comes from general Galera practice and is marked **[Added]**. I haven't checked any of it against your platform. Commands are examples to verify for your MariaDB/Galera version and deployment tool. Gaps are marked TODO because I didn't want to guess hostnames, paths or tooling.

---

# Galera full cluster outage recovery (all nodes down)

**Status:** Draft, not yet validated. **Owner:** TODO (it can't be the departing expert). **Last validation:** never.

## Purpose and scope
- **Purpose:** restore the Galera cluster behind OpenStack after every node is down, without losing committed data and without creating two diverging clusters.
- **Covers:** no node is running and none holds a Primary component (power loss, all nodes stopped, cascading crash).
- **Does NOT cover** (stop and escalate):
  - One or two nodes down while others still serve. Rejoin them normally and do not bootstrap.
  - Nodes running but `non-Primary` (partition or quorum loss). TODO: separate runbook.
  - Disk failure or data corruption. That means restoring from backup.

## Context (the "why" the note omits) [Added]
- The node with the highest committed seqno has the newest data. Bootstrapping a lower node discards transactions the others committed, and those nodes then get overwritten by a full state transfer (SST).
- A normally started node tries to join an existing cluster. With none, one node must be told to form a new one, and the rest join it.
- TODO for the expert before Friday: node count, arbitrator (garbd), proxy or load balancer, deployment tool (e.g. Kolla-Ansible), datadir and log paths, backup location, past outages, and any approaches that were tried and failed.

## Who may run it
- **Executable by:** platform or DB on-call (TODO: confirm).
- **Approver for step 6/7:** TODO, a named role that can accept possible data loss and a service-wide outage.

## Preconditions
- Every node confirmed stopped (Decision point).
- Root access, or out-of-band console, on every DB node. Take credentials from the secret store and never paste them into tickets.
- **Preserve first:** error logs and `grastate.dat` from every node, the `wsrep-recover` output, and a timeline of what changed.
- Space for a copy or snapshot of each datadir.
- Know the dependents: Keystone, Nova, Neutron, Glance, Cinder and others all write to this DB.

## Decision point: is it really a full outage?
| Check (read-only) | If you see | Go to |
|---|---|---|
| Is `mysqld`/`mariadbd` running on **every** node? | None running | Procedure |
| same | Any running | **Stop.** `wsrep_cluster_status` is Primary with fewer nodes: rejoin normally, no bootstrap. `non-Primary`: escalate. |
| A node can't be reached | State unknown | **Stop.** It may be running, and bootstrapping then creates split-brain. Reach it or fence it first. |

## Procedure
| # | Action | Type | Expected | If different |
|---|---|---|---|---|
| 1 | Confirm the decision point on all nodes and open an incident record. | read-only | All down | Unreachable node: stop |
| 2 | Incident lead decides how to hold the OpenStack services that write to the DB. Suggested: stop or pause them until the DB is verified. This is deliberate degradation, which is safer than letting them flap against a half-recovered DB. [Added] | state-changing | Services held; running VMs unaffected (verify for your backend) | Escalate |
| 3 | Copy or snapshot each datadir while the DB is down. [Added] | state-changing (copies only) | Copies exist | No space: stop |
| 4 | Read each node's position (see below). This is the "find highest seqno" step. | read-only | A seqno and UUID per node | See below |
| 5 | Pick the candidate: highest seqno, with the same cluster UUID everywhere. | read-only | One winner | Tie with identical UUID and seqno: any tied node is fine, record the choice [Added]. Differing UUIDs: stop |
| 6 | Get the approver's recorded OK for the chosen node, showing every node's seqno and the expected loss. | decision | Approval with who and when | No approver: stop |
| 7 | **Bootstrap the chosen node only** (see below). | **state-changing, point of no return** | Primary, cluster size 1, `wsrep_ready=ON` | Won't start: read the log. Don't try another node without re-deciding |
| 8 | Verify that node (DB part 1 below) before adding others. | read-only | Data present, Synced | Escalate |
| 9 | Start node 2 **normally** (no bootstrap flag) and wait for Synced. It receives IST or SST from the donor, and SST overwrites the joiner's data and loads the donor. [Added] | state-changing | Size 2, Synced | Stuck joining: read logs on both nodes, don't restart the donor |
| 10 | Start the remaining nodes **one at a time**, same check. [Added] | state-changing | Size = expected | As above |
| 11 | Restore proxy/LB routing and restart OpenStack services in the order the incident lead decides (TODO: confirm the order). | state-changing | Services connect cleanly | Stop the sequence and investigate |
| 12 | End-to-end verification. | test | Passes | See Recovery |

**Finding the highest seqno** (examples, verify for your version):
1. Read `grastate.dat` in the datadir (often `/var/lib/mysql/`, TODO: confirm) for `uuid`, `seqno` and `safe_to_bootstrap`.
2. A valid `seqno` means a clean shutdown. **`seqno: -1` means a crash, so the file does not tell you the position.** [Added]
3. For `-1` nodes, run `mysqld --wsrep-recover` (or `mariadbd`), as the service user against the real datadir. It prints `Recovered position: <uuid>:<seqno>`. Keep the output. Under Kolla-Ansible it runs inside the container, so TODO: confirm how.
4. Highest wins. If any position is still unknown, or the UUIDs differ, stop and escalate.

**Bootstrap command** (examples): `galera_new_cluster`, or start with `--wsrep-new-cluster`. Kolla-Ansible has `kolla-ansible mariadb_recovery`, which automates the selection. TODO: ask the expert whether they use it, and review how it picks a node. Whoever or whatever picks the node, the step 6 approver approves it.

## Stop and escalate
Stop if:
- any node is unreachable with unknown state,
- UUIDs differ or any position is unknown,
- the highest node won't start and you're tempted to use another,
- something is already Primary before you bootstrapped,
- SST fails twice, or the donor degrades,
- the approver is unreachable.

Collect before escalating: logs, `grastate.dat` files, `wsrep-recover` output, a command log with times and names, and `SHOW STATUS LIKE 'wsrep%'` from any running node. Escalate to: TODO.

## Do NOT do without escalation
- Bootstrap while any node's state is unknown.
- Bootstrap the node you guess is latest. Use the recorded position.
- Set `safe_to_bootstrap: 1` on a node that isn't proven highest. [Added]
- Delete `grastate.dat`, `gcache` or the datadir "to make it start". That can destroy the only current copy. [Added]
- Start several nodes at once, or start a joiner with the bootstrap option.
- Restart OpenStack services before the DB is verified.
- Make direct SQL fixes to OpenStack tables.

## Verification
1. **DB, on every node:**
   - `wsrep_cluster_status=Primary`
   - `wsrep_cluster_size` equals the expected count
   - `wsrep_local_state_comment=Synced`
   - `wsrep_ready=ON`
   - the same `wsrep_cluster_state_uuid` everywhere
   - a test write replicates (TODO: define the test table)
2. **Capability:** get a token, list servers, then create, reach and delete a test VM (TODO: define project, network and image). Process health alone is not enough.
3. **Follow-up:** look for instances or volumes stuck in transitional states, and check RabbitMQ and monitoring.

## Recovery
- Before step 7 nothing has changed except the held services. Release them if you abandon the procedure.
- After step 7, if the wrong node was bootstrapped, **stop and start no more nodes**. Escalate and use the step 3 copies and logs. TODO: document the backup restore path and when it was last tested. A restore loses everything after the backup.
- **Point of no return:** step 7, and again at step 9, because SST overwrites the joiner's data.

## History
| Date | Change | Why | By |
|---|---|---|---|
| 2026-10-25 | Expanded from the 3-clause note | Expert leaving | Claude draft, unvalidated |

---

## Author notes
- **Sources:** only the expert's sentence. Everything else is general Galera knowledge. Verify `safe_to_bootstrap`, `--wsrep-recover` and IST/SST behaviour against your MariaDB/Galera release.
- **Gaps to close with the expert before Friday:**
  1. topology, tooling and paths
  2. whether `mariadb_recovery` is the normal route, and its pitfalls
  3. OpenStack service stop and start order
  4. backup and restore details
  5. named owner and approver
  6. history of past outages
  7. a partition/quorum-loss runbook
- **Validation plan:** a colleague who did not write this runs it in a non-production Galera cluster while the expert watches but does not help.
  - Cover four cases: clean shutdown, hard kill of all nodes (`seqno: -1`), a tie, and one unreachable node.
  - Fix the document from their questions, then record the date and executor.
  - Until then the status stays "Draft". Do this before Friday.

> Decision support only. State-changing steps above require approval by the accountable owner and should be executed under your change process.

---

If you want this as a shareable page for the team, I can publish it as an artifact. I can also take the TODOs as an interview checklist for the expert's last days.