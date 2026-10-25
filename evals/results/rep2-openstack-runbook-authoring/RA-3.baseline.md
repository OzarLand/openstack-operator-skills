I couldn't publish this as a page. File writing is disabled in this session, so the runbook is below as Markdown. I haven't run any of it against your environment. I wrote it from general Galera practice (MariaDB and Percona behave the same for these steps) and your expert's one-line note.

---

# Galera full cluster outage recovery

**Use when:** every node is down, or no node reports `wsrep_cluster_status = Primary`.
Replace values in `<angle brackets>`.

## Rules that prevent data loss
1. **Bootstrap the node with the most recent data.** Every other node will copy its data from that node. Any transactions that exist only on a node with a higher seqno are lost.
2. **Bootstrap exactly one node.** Bootstrapping two nodes creates two separate clusters (split brain).
3. **Start the other nodes one at a time.** Wait for each to reach `Synced` before starting the next.
4. **Don't delete `grastate.dat` or data files** unless a step says to. Deleting `grastate.dat` forces a full state transfer (SST).
5. **Keep application traffic off the cluster** until step 6 passes.

## 1. Confirm it's a full outage
Run on every node:
```bash
systemctl status mariadb        # or mysql / mysqld
mysql -e "SHOW STATUS LIKE 'wsrep_cluster_status'; SHOW STATUS LIKE 'wsrep_cluster_size';"
```
If any node is still `Primary`, stop. This isn't a full outage. Restart the failed nodes normally and let them rejoin.

Also check that the nodes can reach each other on ports 3306, 4567, 4568 and 4444. A network partition with nodes still running is a different incident.

## 2. Stop everything and keep evidence
```bash
systemctl stop mariadb
pgrep -a 'mysqld|mariadbd'      # expect no output
mkdir -p /root/galera-recovery-$(date +%F)
cp -a /var/lib/mysql/grastate.dat /var/lib/mysql/gvwstate.dat /root/galera-recovery-$(date +%F)/ 2>/dev/null
cp /var/log/mysql/error.log /root/galera-recovery-$(date +%F)/ 2>/dev/null   # path varies
```
If you have time and disk space, snapshot or copy the datadir on the node you'll bootstrap.

## 3. Read every node's position (the "highest seqno" step)
Run on all nodes, with mysqld stopped:
```bash
cat /var/lib/mysql/grastate.dat
```

| You see | Meaning | Action |
|---|---|---|
| `seqno: <number>` | Clean shutdown. The position is reliable. | Record uuid and seqno. |
| `seqno: -1` | The node crashed. The file doesn't hold the real position. | Run the recovery command below. |
| `safe_to_bootstrap: 1` | This node left the cluster last, cleanly. | Strong candidate, but still compare seqnos. |
| File missing or empty | Unclean state, or an earlier attempt removed it. | Run the recovery command below. |

For nodes with `seqno: -1` or no file:
```bash
sudo -u mysql mysqld --wsrep-recover     # MariaDB 10.4+: mariadbd --wsrep-recover
grep 'Recovered position' /var/log/mysql/error.log | tail -1   # or journalctl
# e.g. WSREP: Recovered position: 5ee99582-bb8d-11e2-b8e3-23de375c1d30:8204507
```
The result is `uuid:seqno`. The command doesn't join the cluster.

Write the results in a table (node, uuid, seqno) and keep it with the incident notes.

## 4. Choose the node
- All nodes must show the **same uuid**. If they differ, stop and escalate.
- Pick the **highest seqno**. If nodes tie, any of them works. Prefer `safe_to_bootstrap: 1`, then the healthiest hardware.
- **Escalate instead of continuing** if every node is at `-1` and `--wsrep-recover` gives no position, or if you suspect data corruption on the best node. A person with database authority must decide which node is the source of truth.

## 5. Bootstrap that one node
Galera refuses to bootstrap from a node with `safe_to_bootstrap: 0`. Once you've confirmed this node has the highest seqno, set the flag on this node only:
```bash
sed -i 's/^safe_to_bootstrap: 0/safe_to_bootstrap: 1/' /var/lib/mysql/grastate.dat
```
Then start it as a new cluster, using the command for your distribution:
```bash
galera_new_cluster                          # MariaDB (systemd)
systemctl start mysql@bootstrap.service     # Percona XtraDB Cluster
sudo -u mysql mysqld --wsrep-new-cluster &  # fallback
```
Don't edit `wsrep_cluster_address` in the config. These commands override it for this one start, so there's nothing to revert.

## 6. Verify the single-node cluster
```bash
mysql -e "SHOW STATUS WHERE Variable_name IN
 ('wsrep_cluster_size','wsrep_cluster_status','wsrep_local_state_comment','wsrep_ready','wsrep_connected');"
```
**Expected:** size `1`, status `Primary`, state `Synced`, ready `ON`, connected `ON`.

Run a sanity query on a known table, such as a row count or the newest timestamp. Check the error log for new `ERROR` lines. If anything is wrong, don't start the other nodes.

## 7. Start the other nodes, one at a time
```bash
systemctl start mariadb      # node 2 only
mysql -e "SHOW STATUS LIKE 'wsrep_cluster_size'; SHOW STATUS LIKE 'wsrep_local_state_comment';"
tail -f /var/log/mysql/error.log
```
- Wait for the joiner to show `Synced` and for cluster size to increase. Then start the next node.
- A node that is close behind catches up by IST (fast). A node that is far behind or has no valid state does a full SST.
- During SST one node is the donor and shows `Donor/Desynced`. This is expected, and with rsync the donor may be briefly blocked for writes.
- Large datasets can take a long time. Check the logs and disk/network activity before assuming it's stuck.
- **Don't** start all nodes in parallel, restart a joiner mid-SST, or kill a donor. That can leave several nodes needing another SST.

## 8. Confirm and restore service
- Cluster size equals the expected node count, and all nodes are `Synced`.
- Write a test row on one node and read it from the others.
- Add the nodes back to the load balancer or proxy, then re-enable application traffic.
- Check that `wsrep_flow_control_paused` is low once things settle.
- Confirm backups and monitoring are running against the recovered cluster.
- Record the timeline, the step 3 position table and the root cause. Check whether any transactions that clients saw as committed were lost.

## Troubleshooting

| Symptom | Likely cause and fix |
|---|---|
| "It may not be safe to bootstrap the cluster from this node" | `safe_to_bootstrap: 0`. Set it to 1 on the chosen node only (step 5). |
| Bootstrapped node is `non-Primary` | It was started without the bootstrap flag. Stop it and use the bootstrap command. |
| Joiner: "Failed to open gcomm backend connection" | Check `wsrep_cluster_address`, check ports 4567/4568/4444 between nodes, and confirm the bootstrapped node is running. |
| Joiner fails SST | Read both the donor and joiner logs. Common causes are missing SST credentials, no `mariabackup` or `xtrabackup` installed, a full disk, or a firewall on port 4444. |
| Joiner reports a different cluster uuid | It has a different history. The usual fix is to force SST from the healthy cluster, but first confirm the healthy cluster has the data you want. |
| 2-node setup or `garbd` arbitrator | Start the arbitrator after the bootstrapped node is up, and check that quorum can form. |

## 9. To confirm with your DB expert before Friday
The runbook can't know these, so ask him now:
- Product and version, exact service names, and the real bootstrap command.
- Hostnames, IPs, and out-of-band console access if SSH is down.
- Paths for the datadir, error log (or journald) and config files.
- SST method (`mariabackup`, `rsync`, `xtrabackup-v2`), the SST user, and where its credentials are stored.
- Whether there's a `garbd` arbitrator, and where it runs.
- Load balancer or proxy: how to drain and re-add nodes, and who owns it.
- Whether anything auto-restarts the database (systemd restart policy, orchestrator, config management) in a way that could clash with a manual bootstrap.
- Where the latest backups are, and when a restore was last tested.
- Who to escalate to, and who can approve accepting lost transactions.
- Past outages: what happened, how long recovery took, and anything surprising.

---

If you'd like it published for the team, I can do that once file writing is available. I can also tailor the commands once you tell me which Galera flavour and distro you run.