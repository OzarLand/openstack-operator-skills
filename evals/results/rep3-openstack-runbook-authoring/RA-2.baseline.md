I couldn't find the runbook file. The working directory is empty, so I'm reviewing the three steps as you wrote them. I haven't run anything.

**Main concerns**

1. **Step 1: restart all three nodes at once.** Restarting every RabbitMQ node together takes the cluster fully down. It can also leave the nodes unable to rejoin, because the last node to stop has to be the first one back up. Restart one node at a time instead:
   - Run `rabbitmqctl cluster_status` and confirm all nodes are running before you start.
   - Restart a node, wait until it has rejoined, and confirm with `rabbitmqctl cluster_status` and `rabbitmqctl node_health_check` (or `rabbitmq-diagnostics check_running`).
   - Only then move to the next node.
   - Say which node goes first and whether to do the alarm-holding node last.

2. **There's no diagnosis step.** A RabbitMQ alarm is usually a memory high-watermark or a disk-free limit. A restart only hides those and the alarm will come back. Add these before any restart:
   - `rabbitmqctl status` to see which alarm fired, and on which node.
   - `rabbitmqctl list_queues name messages consumers` to find queues with a large backlog or no consumers.
   - `df -h` on the data partition.
   - Check whether the alarm is a symptom of stuck consumers, such as a nova-conductor or neutron agent that stopped consuming.

3. **Step 2: restart every nova and neutron service.** This is broad and disruptive.
   - Often, clients reconnect by themselves once RabbitMQ is healthy, so you may not need this step.
   - If it's needed, restart only the services that lost their connections, using the "connection refused" or "AMQP" errors in the logs to find them.
   - Do the restarts in a rolling way, controllers first and then computes in batches. Restarting all `nova-compute` and neutron agents at once can cause a flood of reconnections, which can bring the alarm straight back.
   - Spell out the exact service names and the order.

4. **Step 3: "check that the alarm cleared" is too vague.** Say how to check it:
   - `rabbitmqctl status` (or `rabbitmq-diagnostics alarms`) should show no alarms on any node.
   - Queue depths should be falling.
   - `openstack compute service list` and `openstack network agent list` should show everything up.
   - Do a smoke test, such as booting a test instance.
   - Say what to do if the alarm returns (escalate, with the data to collect).

**Missing pieces**
- Prerequisites: who may run this, the impact (API calls may fail during the restart), a maintenance window or notification, and a check that no migrations are in progress.
- Whether it applies to your deployment: on containerized deployments (kolla, TripleO) the commands differ, for example `docker restart rabbitmq`.
- A rollback or failure path if a node won't rejoin. This covers `rabbitmqctl forget_cluster_node`, `force_boot`, and mirrored or quorum queue handling.
- A timeout and an owner for each step.

**Suggested outline:** (0) diagnose and record the alarm, (1) clear the root cause (purge or fix consumers, free disk), (2) restart RabbitMQ one node at a time, verifying after each, (3) restart only the affected OpenStack services, in a rolling way, (4) verify with explicit commands, (5) escalate if the alarm returns.

If you paste the runbook text or tell me where the file is, I can review the exact wording and write a revised version.