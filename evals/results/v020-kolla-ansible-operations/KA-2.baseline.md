**Not as stated.** The variable is valid, but "ctl01 is the primary" is the wrong reason to use it. In a Galera cluster after a full power loss, the node to bootstrap from is the one with the highest committed transaction sequence number (seqno), not the one that was "primary". Bootstrapping from a node that is behind silently discards transactions the other nodes had committed.

What I'd do:

1. **Back up first.** On every controller, copy the MariaDB volume (`/var/lib/docker/volumes/mariadb/_data`, or your equivalent) while the cluster is stopped.

2. **Check each node's position.**
   - Run `cat /var/lib/docker/volumes/mariadb/_data/grastate.dat` on each controller.
   - A real `seqno` is usable. A `seqno: -1` means an unclean shutdown, which is expected after a power cut. In that case the position has to be recovered with `mysqld --wsrep-recover`. Look for "Recovered position" in the output or the log.
   - Compare the positions across all controllers.

3. **Run the recovery without the override first.** `kolla-ansible -i <inventory> mariadb_recovery` runs `wsrep-recover` on every node and picks the highest seqno itself. Read its output to see which node it chose and confirm that matches your own check.

4. **Use `-e mariadb_recover_inventory_name=ctl01` only if you've verified ctl01 has the highest seqno.** That is the case where you need to force the choice, for example if the automatic detection fails or two nodes tie. If ctl01 is the highest, the override is fine and gives the same result. If another node is higher, the override would be a mistake.

5. **After recovery, check the cluster.** Run `SHOW STATUS LIKE 'wsrep_cluster_size'` and confirm it equals the number of controllers, then re-run `kolla-ansible deploy`.

I haven't looked at your environment, so I can't tell you which node is ahead. Post the `grastate.dat` contents or the wsrep-recover output from each controller and I'll help you read them.