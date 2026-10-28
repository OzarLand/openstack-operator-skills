**Short answer:** the plan is sound and close to what the Kolla-Ansible docs describe, but I haven't tested it. I have no access to your cluster, and I haven't looked at your inventory or configs. A few checks first will make it safer.

**RabbitMQ**
- Running `rabbitmqctl forget_cluster_node rabbit@ctl02` on a surviving node is the right step. It only works while ctl02 is down, which it is.
- It's required. A reinstalled node with an empty data dir and the same name will be rejected, or end up in a bad join, if the cluster still lists the old ctl02.
- You can do it now, before the hardware arrives.
- Check `rabbitmqctl cluster_status` first. It should show ctl01 and ctl03 running and ctl02 as the only down node.
- If you use quorum queues (the default in recent releases), confirm afterwards that ctl02 is gone from their member lists, for example with `rabbitmq-queues check_if_node_is_quorum_critical`. If you use classic mirrored queues, the forget handles it.

**Other services that need a check**
- **MariaDB/Galera:** the new node will do a full SST from a donor. Make sure the other two nodes are healthy and have quorum (`SHOW STATUS LIKE 'wsrep_cluster_size'` should be 2). If you only had two controllers, stop and think before going further. Take a DB backup first.
- **OVN (if you use it):** the dead member stays in the NB/SB Raft clusters. Kick it with `ovs-appctl -t /var/run/ovn/ovnnb_db.ctl cluster/kick OVN_Northbound <server-id>`, and the same for `OVN_Southbound`. Otherwise the rejoin can fail.
- **Ceph mon, etcd, OpenSearch:** if any of these are colocated on ctl02, they need the same remove-then-rejoin treatment.
- **HAProxy/keepalived:** with the same IPs, nothing changes. Check the VIP is currently held by a healthy node.

**Kolla-Ansible mechanics**
- Clear ctl02's old SSH host key from `known_hosts`, since the hardware is new.
- Run `bootstrap-servers -l ctl02`, then `prechecks -l ctl02`, then `pull -l ctl02`, then `deploy -l ctl02`.
- With `--limit`, templates need facts from the other controllers. If you hit undefined-fact errors, run `kolla-ansible gather-facts` against ctl01, ctl03 and ctl02, or include them in the limit.
- Watch the RabbitMQ and MariaDB steps closely during the deploy. Confirm ctl02 joined (`cluster_status`, `wsrep_cluster_size` back to 3) before you move on.
- Don't run a full deploy or reconfigure against the whole cluster while ctl02 is half-built.

**Afterwards:** check `openstack compute service list`, `openstack network agent list` and `openstack volume service list`. Delete any stale ctl02 entries if the services re-register under new IDs.

If you share your inventory (which services live on ctl02) and your Kolla-Ansible release, I can tighten this into an exact runbook.