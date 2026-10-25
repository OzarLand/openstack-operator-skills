I couldn't save or publish the runbook as a page, because file writing is disabled in this session. The full text is below instead. It comes from general Galera knowledge, not from your environment, so the outgoing DBA should review it before Friday.

# Galera full-outage recovery runbook

This applies only when **every** node is down. For a single failed node, restart it and let it rejoin through IST or SST.

## Environment details (fill in)
- Nodes and IPs: `[TODO]`
- Flavor and version: `[TODO]` (MariaDB Galera, Percona XtraDB Cluster or MySQL with Galera). The bootstrap command in step 5 depends on it.
- Data directory (usually `/var/lib/mysql`), service name, and error log location: `[TODO]`
- SST method, and whether there is an arbitrator (`garbd`): `[TODO]`
- Load balancer or proxy (HAProxy, ProxySQL, MaxScale) and how to drain it: `[TODO]`
- Escalation contacts: `[TODO]`

## Rules that prevent data loss
1. Bootstrap exactly one node, the one with the highest seqno. Bootstrapping a lower one silently discards transactions the others had.
2. Never bootstrap two nodes. That creates two clusters with diverging data.
3. Keep applications off the database until the cluster is healthy.
4. Start the other nodes one at a time. Wait for each to show `Synced` before starting the next.

## Procedure

**1. Confirm the outage and stop traffic**
- On every node, run `systemctl status mariadb` and `pgrep -a mysqld`. If any node is `Primary`, stop and use normal node recovery instead.
- Drain the load balancer or enable maintenance mode.
- Check for full disks and OOM kills (`df -h`, `dmesg -T | grep -i -E 'oom|killed process'`). Fix these first, or the nodes will crash again.

**2. Preserve evidence**
- On every node, copy `grastate.dat`, `gvwstate.dat` (if it exists) and the recent error log to `/root/galera-recovery-<date>/`.
- If you can, snapshot the datadir of the node you plan to bootstrap.

**3. Read each node's state with `cat /var/lib/mysql/grastate.dat`**

| You see | Meaning | Action |
|---|---|---|
| `seqno` is ≥ 0 | Clean shutdown | Record it |
| `seqno: -1` | Crash, position not saved | Do step 3a |
| `safe_to_bootstrap: 1` | Last node out | Strong candidate, but still compare seqnos |
| `uuid` differs between nodes | Different cluster histories | **Stop and escalate** |

**3a. Recover the position on nodes with `seqno: -1`** (the server must be stopped)
```
mysqld --wsrep-recover --user=mysql 2>&1 | grep -i 'Recovered position'
# MariaDB 10.4+ may be: mariadbd --wsrep-recover --user=mysql
```
The line looks like `WSREP: Recovered position: <uuid>:<seqno>`. If the output isn't shown, check the error log or journal.

**4. Choose the node to bootstrap**
- Tabulate hostname, uuid, seqno and `safe_to_bootstrap` for every node.
- Pick the highest seqno. On a tie, prefer `safe_to_bootstrap: 1`; otherwise any tied node is fine.
- Have a second person confirm the choice. This is the one irreversible decision.
- If the chosen node has `safe_to_bootstrap: 0`, which is normal after a crash, Galera will refuse to bootstrap it. Once you're sure its seqno is the highest, set it to 1: `sed -i 's/^safe_to_bootstrap: 0/safe_to_bootstrap: 1/' /var/lib/mysql/grastate.dat`

**5. Bootstrap that node only**
```
galera_new_cluster                          # MariaDB
systemctl start mysql@bootstrap.service     # Percona XtraDB Cluster
mysqld --wsrep-new-cluster --user=mysql &   # generic fallback
```
Verify with `SHOW STATUS WHERE Variable_name IN ('wsrep_cluster_size','wsrep_cluster_status','wsrep_local_state_comment','wsrep_ready');`

You should see size 1, `Primary`, `Synced` and ready `ON`. Also check that a known table has the data you expect.

**6. Start the other nodes, one at a time**
- Use a normal start (`systemctl start mariadb`), not a bootstrap.
- Watch the log to see whether it does IST (fast) or SST (a full copy from a donor). SST wipes the joiner's datadir, which is expected.
- Wait for `Synced` and for `wsrep_cluster_size` to go up before starting the next node. Don't interrupt a long SST.

**7. Verify on every node**

Every node should show the same `wsrep_cluster_size` (your node count), `Primary`, `Synced`, `wsrep_ready ON` and `wsrep_connected ON`. Also check that `wsrep_flow_control_paused` is low.

## Troubleshooting

| Symptom | Action |
|---|---|
| "It may not be safe to bootstrap from this node" | `safe_to_bootstrap` is 0. Verify the seqno, then set it to 1 (step 4). |
| All nodes `-1` and recovery returns `-1` | Retry recovery and read the logs. Compare the latest data on a busy table across nodes. Pick one only with a second person agreeing, or escalate. |
| Joiner stuck in `Joining` or SST fails | Check the donor and joiner logs, the SST credentials, the SST tooling installed, free disk, and the firewall (3306, 4567 tcp/udp, 4568, 4444). |
| Joiner forms its own size-1 cluster | `wsrep_cluster_address` is empty or unreachable. Fix the config and restart. |
| Joiner crashes with inconsistency errors | Move its datadir aside and let it rejoin through full SST. |
| Chosen node is corrupt and won't start | Delete nothing and escalate. The fallback is the next-highest seqno, which loses the transactions in between. Record that decision. |
| Different uuids | Escalate before any bootstrap. |

## After recovery
- Re-enable the nodes in the load balancer one at a time, then restore application traffic.
- Watch the logs and flow control for an hour.
- Take a fresh backup.
- Make sure the service is enabled on boot and any temporary config changes are reverted.
- Write an incident note covering the cause, the seqnos found, which node was bootstrapped and why, any data-loss window, and IST versus SST per node.
- Find out why all nodes went down. Simultaneous or automatic restarts, OOM kills and power loss are common causes.

## Questions to ask the DBA before Friday
1. Which flavor and version are we on, and what is the exact bootstrap command?
2. Is there a `garbd` arbitrator, or a node that should never be bootstrapped, such as one in a remote data center?
3. Which SST method do we use, and how long does a full SST take at our data size?
4. How is traffic routed, and how do we drain it?
5. Do we have custom `wsrep_provider_options` such as `pc.*` or `gcache.size`?
6. Has a full outage happened before, and what went wrong?
7. Does anything in our setup break the "highest seqno wins" rule, such as async replicas or backups taken from a specific node?

Steps 1–4 only read state, so you can dry-run them with him on staging before he leaves.

If you re-enable file writing, I can publish this as a shareable page for the team.