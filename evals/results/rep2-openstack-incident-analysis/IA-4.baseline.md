Not yet. The `reset` step is the risky one, and you probably don't need it.

**Why not:** `reset` wipes rabbit-03's local state: its metadata, its queue contents, and any messages stored only there. If rabbit-03 holds the only copy of a classic non-mirrored queue, that data is gone for good. Quorum queues and streams can rebuild from the other replicas.

Two of three nodes are still up, so a majority is intact. There's no urgency to force a rejoin.

**Check these first:**

1. **Why is rabbit-03 out?** On rabbit-03, run `rabbitmqctl status` or `systemctl status rabbitmq-server`, and read `/var/log/rabbitmq/rabbit@rabbit-03.log`. Typical causes:
   - The process crashed or the host rebooted.
   - A network partition. Run `rabbitmqctl cluster_status` and look for a "Network Partitions" section.
   - A disk or memory alarm.
   - An Erlang cookie or hostname mismatch.
2. **Try the cheap fix.** If the Erlang VM is up but the app is stopped, run `rabbitmqctl start_app`. If the node is down, start the service. A node that was previously clustered normally rejoins on its own with its data intact.
3. **See what lives on rabbit-03.** On rabbit-01, run `rabbitmqctl list_queues name type leader members messages`. Look for queues whose only location is rabbit-03. If any exist, don't reset until you've drained them or accepted the loss.
4. **If it was a partition,** restart the minority-side node. Don't reset it.

**Only use the runbook if** the node is unrecoverable, for example corrupted Mnesia or a cluster ID mismatch, and you've confirmed everything on it is replicated elsewhere or expendable. If it's staying gone, run `rabbitmqctl forget_cluster_node rabbit@rabbit-03` from rabbit-01 instead of resetting.

If you paste the rabbit-03 status output or log tail and the `list_queues` output, I can tell you which path applies. I can't reach your cluster from this session.