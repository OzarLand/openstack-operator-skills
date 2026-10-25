I couldn't save or publish the runbook because file writing is disabled in this session. Here it is in full, so you can paste it into your wiki.

---

# Galera Full Outage Recovery Runbook

**Scope:** every node in the cluster is down. This is written from general Galera practice (MariaDB Galera and Percona XtraDB Cluster). I haven't checked it against your environment, so fill in the `FILL-IN` items and have your DBA review it before Friday.

| Item | Value |
|---|---|
| Flavour and version | FILL-IN |
| Nodes (hostnames and IPs) | FILL-IN |
| Arbitrator (garbd)? | FILL-IN |
| Datadir | FILL-IN (default `/var/lib/mysql`) |
| Service name | FILL-IN (`mariadb`, `mysql` or `mysqld`) |
| Error log path | FILL-IN |
| SST method | FILL-IN (mariabackup, xtrabackup-v2 or rsync) |
| Load balancer or proxy | FILL-IN |
| Escalation contacts | FILL-IN |

## Why the order matters
- Every committed transaction has a **seqno** within a cluster history identified by a **UUID**. The highest seqno has the most data.
- The bootstrapped node becomes the source of truth. The others sync from it and discard anything beyond it. **If you bootstrap a node that is behind, the transactions only the better node had are lost for good.**
- `safe_to_bootstrap: 1` in `grastate.dat` appears only on the last node to shut down cleanly. After a crash every node usually shows `0` and `seqno: -1`, so you have to work out the real position yourself.

## 0. Before you start
1. Declare an incident and tell stakeholders.
2. Find out why everything went down (power, OOM kill, network partition, disk full). If the cause is still active, fix it first.
3. Check disk space on every node.
4. Copy the error logs and each `grastate.dat` somewhere safe. They are your evidence if a decision turns out wrong.
5. If you are unsure which node is best, copy its datadir (with mysqld stopped) before step 3.

## 1. Confirm every node is down
```
systemctl status <service>
ps aux | grep -E 'mysqld|mariadbd' | grep -v grep
```
- If any node is still running and `wsrep_cluster_status = Primary`, this is **not** a full outage. Don't bootstrap. Start the down nodes normally (step 4).
- If processes are alive but all nodes report `non-Primary`, use the quorum-loss fix under Troubleshooting.

## 2. Find the most advanced node
**2a. Read `grastate.dat` on every node:**
```
cat <datadir>/grastate.dat
```
| You see | Meaning |
|---|---|
| Real `seqno` (≥ 0) | Clean shutdown. That is the node's position. |
| `seqno: -1` | Crash or unclean shutdown. Do 2b. |
| `safe_to_bootstrap: 1` | This node was last out. Strong candidate. |
| All-zero uuid or missing file | No valid state. Can't be the bootstrap node. |

**2b. For nodes with `seqno: -1`, recover the position.** This starts mysqld briefly, prints the position and exits. It does not start the cluster.
```
mariadbd --wsrep-recover --user=mysql     # older MariaDB or PXC: mysqld --wsrep-recover --user=mysql
grep 'Recovered position' <error-log>     # or check the command output or journalctl
```
Expected line: `WSREP: Recovered position: 5ee99582-bb8d-11e2-b8e3-23de375c1d30:1234`, in the form `UUID:seqno`.

**2c. Pick the winner.** Record node, UUID, seqno and `safe_to_bootstrap` for each node.
- All UUIDs must match. If they differ, **stop and escalate**, because the nodes have different histories.
- Choose the highest seqno. For a tie, any node works, so prefer the one with `safe_to_bootstrap: 1`.
- If a node's recovered position is `-1` again, its InnoDB data may be damaged. Don't pick it unless every node is like that, and if they are, escalate.
- Write the choice and the reason in the incident log.

## 3. Bootstrap the chosen node (this node only)
1. If its `safe_to_bootstrap` is `0`, Galera will refuse to bootstrap. Once step 2 is verified, override it on this node only:
   ```
   sed -i 's/^safe_to_bootstrap: 0/safe_to_bootstrap: 1/' <datadir>/grastate.dat
   ```
2. Bootstrap:
   ```
   galera_new_cluster                        # MariaDB (systemd)
   systemctl start mysql@bootstrap.service   # Percona XtraDB Cluster
   mysqld --wsrep-new-cluster --user=mysql & # manual, any flavour
   ```
3. Verify:
   ```
   mysql -e "SHOW STATUS WHERE Variable_name IN ('wsrep_cluster_size','wsrep_cluster_status','wsrep_local_state_comment','wsrep_ready','wsrep_cluster_state_uuid','wsrep_last_committed');"
   ```
   Expect size `1`, `Primary`, `Synced`, ready `ON`, and the UUID from step 2.

Keep applications away from the database until the other nodes have rejoined. Make sure the load balancer isn't routing writes yet.

## 4. Start the other nodes, one at a time
```
systemctl start <service>
tail -f <error-log>
mysql -e "SHOW STATUS LIKE 'wsrep_local_state_comment';"
```
- The state goes Joining → Joined → **Synced**. Wait for Synced before starting the next node.
- **IST** (incremental) is fast. **SST** (full copy) can take hours on a large dataset, and it slows the donor. Don't interrupt it.
- `wsrep_cluster_size` should rise by one after each node.
- Every node's config should list its peers, for example `wsrep_cluster_address=gcomm://node1,node2,node3`. Never leave an empty `gcomm://` as the permanent value.

## 5. Verify and hand back
1. On every node, check:
   - `wsrep_cluster_size` equals the expected N.
   - `Primary`, `Synced` and `wsrep_ready=ON`.
   - The same `wsrep_cluster_state_uuid`.
   - `wsrep_last_committed` equal or very close.
2. Do a test write on one node and read it back on another.
3. Check the error logs for new errors.
4. Re-enable the load balancer and confirm every node is healthy there.
5. Release application traffic and monitor for about 30 minutes. Watch deadlocks and `wsrep_flow_control_paused`.
6. Confirm monitoring sees all nodes again.
7. Write post-incident notes: root cause, which node was bootstrapped and its seqno, whether any transactions may have been lost, and time to recovery.

## Troubleshooting
| Symptom | Action |
|---|---|
| "It may not be safe to bootstrap the cluster from this node" | Expected when `safe_to_bootstrap: 0`. Override only on the node chosen in step 2. |
| Processes alive, all nodes `non-Primary` (quorum lost) | Compare `wsrep_last_committed` on all nodes. On the highest, run `SET GLOBAL wsrep_provider_options='pc.bootstrap=YES';`. The others reconnect. |
| SST fails or loops | Read both the donor and joiner logs. Check disk space, the SST user and credentials, the firewall (ports 4567, 4568, 4444 and 3306), and that mariabackup or xtrabackup is installed on both nodes. |
| Joiner has corrupt data | Stop it and move its datadir aside (don't delete it yet). Start it empty so it takes a full SST from a Synced node. |
| UUIDs differ between nodes | Stop. This is likely split brain or an earlier re-bootstrap. Escalate. |
| Every node is `-1` even after `--wsrep-recover` | Escalate. As a last resort, back up the datadir of the node with the healthiest InnoDB recovery and bootstrap it, accepting that some data may be lost. |

## Never
- Bootstrap more than one node. That creates split brain.
- Bootstrap a node because it started first or is the "primary". Compare seqno.
- Edit `safe_to_bootstrap` on any node except the chosen one.
- Delete `grastate.dat` or the datadir of the best node.
- Start several joiners at once.
- Send traffic to a half-recovered cluster without deciding to.

---

Before Friday, ask the DBA to:
- Fill in the table above.
- Confirm which flavour and bootstrap command you use.
- Say whether there are local quirks, such as a garbd arbitrator, custom `pc.*` settings, or a standard SST method.
- Do a dry run in staging, which is the best test of a runbook like this.

If you restore file writing, or want a different format, I can turn this into a file or a published page.