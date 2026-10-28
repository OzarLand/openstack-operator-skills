**Not yet. Don't run it with ctl01 forced until you've checked the data.** "ctl01 is the primary" doesn't mean much for Galera, and forcing the wrong node can silently lose committed transactions.

**Why the colleague's reasoning is risky**
- Galera is multi-master. ctl01 is probably just the first host in the inventory, or the usual HAProxy/ProxySQL write target. After a power cut, the node that matters is the one with the highest committed `seqno`, meaning the last one to stop or the one with the most recent data. That can be ctl02 or ctl03.
- `-e mariadb_recover_inventory_name=ctl01` skips Kolla's `seqno` comparison and bootstraps from ctl01 whatever it holds.
- Anything newer on another node is lost. Nodes that are ahead of ctl01 will normally refuse to join, so you'd likely end up stuck as well as having lost data. (`[DOCUMENTED-UNVERIFIED: KA-OPS-20]`. This form has not been run on a lab.)
- Plain `kolla-ansible mariadb-recovery -i <inventory>` does the comparison itself. It runs `--wsrep-recover` on each node and bootstraps the highest `seqno`. That form was lab-validated (`KA-OPS-17/18`, Kolla-Ansible 22.2.0 and OpenStack 2026.1, Docker, clean stop of 3 controllers). A power cut is an unclean stop, and that case was not run (`seqno: -1`).

**What to do first (all read-only, on each MariaDB host)**
1. `sudo docker ps -a --format '{{.Names}}\t{{.Status}}' | grep -w mariadb`
2. `sudo cat /var/lib/docker/volumes/mariadb/_data/grastate.dat`. Look at `seqno` and `safe_to_bootstrap`.
3. `sudo tail -n 50 /var/log/kolla/mariadb/mariadb.log`
4. `nc -zv -w 3 <controller-api-address> 3306` from the deploy host

**How to read the result**
- Confirm the whole cluster is down. If any node is up and serving, don't run `mariadb-recovery`, because it restarts every node.
- After a hard power loss, expect `seqno: -1` and `safe_to_bootstrap: 0` on most or all nodes. That is the case the lab didn't cover. The role then finds the position from the data files and writes `Recovered position: <uuid>:<seqno>` to the log. Check that every node has such a line. A node without one gets an empty `seqno` and can be skipped or wrongly chosen.
- If a node does have `safe_to_bootstrap: 1`, it is the last one to stop. Compare it with the others.
- If the `seqno` values clearly show ctl01 is the most advanced, forcing it is fine. The default run would pick it anyway, so you gain nothing from forcing it.
- If the nodes disagree, or you can't tell which is ahead, stop and escalate. Don't force anything.

**Then, if it's cause 1 (everything down), the recovery sequence is:**
1. **State-changing:** on every node, stop the container with `sudo systemctl stop kolla-mariadb-container.service`. Systemd restarts a container stopped any other way. Then copy the data with `sudo cp -a /var/lib/docker/volumes/mariadb/_data /var/lib/mariadb-before-recovery-$(date +%F)`. This copy is your only undo, so check you have free space equal to the data size.
2. **Destructive:** `kolla-ansible mariadb-recovery -i <inventory>`, with no forced host. Transactions that only a lower-`seqno` node had are lost. Undo is only by restoring the step 1 copies.
3. **Read-only:** before and after the run, check `sudo grep 'Recovered position:' /var/log/kolla/mariadb/mariadb.log | tail -n 1` on each node. Keep the colon in the pattern. Also check which host was chosen in `/tmp/kolla_mariadb_recover_inventory_name_<shard>` on the deploy host. If the chosen host's line is missing or older than this run, stop before services write again.

**Verify:**
- `wsrep_cluster_size` equals the number of MariaDB hosts, status is `Primary`, and state is `Synced`.
- `openstack token issue` and `openstack server list --all-projects --limit 5` both work.
- A later `kolla-ansible deploy` gets past the "stopped cluster" task.
- Finally, create, reach and delete a test VM.

**Before step 2, you need:**
- A named owner who accepts the data-loss risk.
- The impact of the control-plane outage understood. Running VMs keep running, but the APIs are down until recovery finishes.
- No overlapping deploy or other changes in flight.

Nothing here has been run on your system. Please paste the `grastate.dat` and log excerpts from each node, with passwords redacted, and I can tell you which node is the right source.

Decision support only. State-changing steps above require approval by the accountable owner and should be executed under your change process.