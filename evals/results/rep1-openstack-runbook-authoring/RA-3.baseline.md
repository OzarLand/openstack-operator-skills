I couldn't publish this as a page because I have no tool here for creating files. The runbook is below, and you can paste it into your wiki as is.

---

# Runbook: Galera full cluster outage recovery

**Use when:** every node in the cluster is down (power loss, a crash of all nodes, a bad rolling restart). If at least one node is still `Primary` and `Synced`, don't use this. Restart the failed nodes normally and let them rejoin.

**Goal:** bring the cluster back from the node with the most recent committed data, without losing transactions or creating two clusters.

**Assumptions to check against our setup (fill in):**
- Flavor and version: MariaDB Galera or Percona XtraDB Cluster (PXC). Commands differ slightly, as noted below.
- Datadir: `/var/lib/mysql` (change if different).
- Nodes: `<node1>`, `<node2>`, `<node3>`, plus an arbiter (`garbd`) if we run one.
- Load balancer or proxy: `<HAProxy / ProxySQL / MaxScale>`.

## 0. Before you touch anything
1. **Confirm it's a real full outage.** On every node, run `systemctl status mysql` (or `mariadb`) and `pgrep -a mysqld`. If any node is running, check `SHOW STATUS LIKE 'wsrep_cluster_status';` on it. It may be a network partition, not an outage, and bootstrapping then would create a split brain.
2. **Stop application traffic.** Take the DB out of the load balancer or put the apps in maintenance mode. Nothing should write while you recover.
3. **Make sure no mysqld is running anywhere.** Stop any that are, and don't leave a node half-started.
4. **Optional but recommended:** copy `grastate.dat` and the error log from each node somewhere safe before you change anything. If a datadir is suspect, take a filesystem snapshot or copy.

## 1. Find the most advanced node
On **each** node, run:
```bash
cat /var/lib/mysql/grastate.dat
```
Look at three fields:
- `uuid`: must be **identical** on all nodes. If it isn't, stop and escalate (see Escalate below).
- `seqno`: the last committed transaction.
- `safe_to_bootstrap`: `1` means this node was the last to shut down cleanly.

**Case A: a node has `safe_to_bootstrap: 1` and a real seqno.** The cluster shut down cleanly. Use that node.

**Case B: `seqno: -1` on some or all nodes.** Those nodes crashed or were killed, so the real position isn't recorded. Recover it:
```bash
sudo -u mysql mysqld --wsrep-recover --log-error=/tmp/wsrep_recover.log
grep 'Recovered position' /tmp/wsrep_recover.log
# Recovered position: <uuid>:<seqno>
```
- Use `mysqld` (or `mariadbd` on newer MariaDB), and add `--defaults-file=...` if our config isn't in the default location.
- This does not start the server. It reads InnoDB and prints a position, then exits.
- Run it on every node whose `grastate.dat` shows `-1`.

**Pick the winner:** the node with the **highest seqno**, with the same UUID everywhere. Write down the position for each node. If two nodes tie, either is safe. Prefer the one with the healthier disk and hardware.

> **Why this matters:** bootstrapping a node with a lower seqno silently discards every transaction the others committed after it. The other nodes will then get a full SST from the stale node and overwrite their newer data.

**Escalate if:**
- UUIDs differ across nodes.
- `--wsrep-recover` returns `00000000-0000-0000-0000-000000000000:-1` on every node.
- InnoDB recovery fails.

## 2. Bootstrap the winner
Run this on the **chosen node only**.

1. Mark it safe to bootstrap. Galera 3.19+ refuses to bootstrap a node without this:
   ```bash
   sed -i 's/^safe_to_bootstrap:.*/safe_to_bootstrap: 1/' /var/lib/mysql/grastate.dat
   ```
2. Start it as a new cluster, using the command for our flavor:
   - MariaDB: `galera_new_cluster`
   - PXC (systemd): `systemctl start mysql@bootstrap.service`
   - Generic: `mysqld --wsrep-new-cluster` (start it through the init system with the same flag if possible)
3. If `grastate.dat` showed `seqno: -1`, you can also pass the recovered position: `--wsrep-start-position=<uuid>:<seqno>`.
4. Watch the error log until startup completes.

**Verify before moving on:**
```sql
SHOW STATUS WHERE Variable_name IN
 ('wsrep_cluster_size','wsrep_cluster_status','wsrep_local_state_comment','wsrep_ready','wsrep_cluster_state_uuid');
```
Expected: size `1`, status `Primary`, state `Synced`, ready `ON`, and the UUID matches what you recorded. Do a quick sanity query on a few key tables.

## 3. Start the other nodes, one at a time
On each remaining node, start it **normally**. Do **not** use the bootstrap command and do **not** set `safe_to_bootstrap`.
```bash
systemctl start mysql      # or mariadb
```
- Wait for the node to reach `Synced` before you start the next one.
- A node that is only slightly behind rejoins via **IST** (incremental), which is fast.
- A node that is too far behind, or that has diverged, does a full **SST**. This wipes its datadir and copies everything from a donor, and the donor is slowed down while it runs. Don't start several joiners at once. Watch donor load.
- If a joiner has data you aren't sure about, copy its datadir first.
- Check progress in the error log and with `SHOW STATUS LIKE 'wsrep_local_state_comment';` (`Joining`, `Joined`, then `Synced`).

After each join, `wsrep_cluster_size` should go up by one. Start the arbiter (`garbd`) last, if we have one.

## 4. Verify the whole cluster
On every node, check the following:
- `wsrep_cluster_size` equals the number of nodes, and `wsrep_cluster_status` is `Primary`.
- `wsrep_local_state_comment` is `Synced`.
- The cluster state UUID matches on all nodes.
- `wsrep_local_recv_queue_avg` is near 0.
- The error logs show no repeating errors.

## 5. Restore traffic
1. Re-add the nodes to the load balancer or proxy and check that its health checks pass.
2. Bring the applications back and watch for errors.
3. Confirm writes succeed and replicate. For example, insert a row on one node and read it on another.
4. Write an incident note with the outage time, the seqno of each node, which node you bootstrapped and why, whether any node needed SST, and the cause.

## Common mistakes
| Mistake | Consequence |
|---|---|
| Bootstrapping a node with a lower seqno | Committed transactions are lost, and the newer nodes get overwritten by SST |
| Bootstrapping more than one node | Two separate clusters (split brain) with diverging data |
| Starting every node at once | Several SSTs overloading the donor, and unclear state |
| Setting `safe_to_bootstrap: 1` on all nodes | Removes the safety check that protects you |
| Skipping `--wsrep-recover` when seqno is `-1` | You can't tell which node is most advanced |
| Starting apps before the cluster is `Synced` | Errors and possible bad writes |

## Escalate if
- UUIDs don't match, or recovery fails on every node.
- A joiner repeatedly fails SST or IST.
- You suspect data loss or corruption.

---

**Notes on gaps:**
- I wrote this from general Galera knowledge, not from our environment. The service names, paths, flavor and proxy details above are my guesses.
- Before Friday, have your DB expert fill in the placeholders and review it. Ask them what they check beyond seqno, what has gone wrong in past outages, and whether we use a non-default SST method.
- If possible, rehearse it once on staging.

If you'd like this as a published page the team can open, ask me again once file creation is available. Or give me the missing details and I'll produce a final version.