There's no runbook file in the working directory, so I'm reviewing the three steps as you wrote them. Here's what I found.

**Main problems**

1. **Restarting all three RabbitMQ nodes at once can break the cluster.**
   - Restart one node at a time. After each restart, wait until `rabbitmqctl cluster_status` shows it has rejoined and `rabbitmqctl node_health_check` passes (or `rabbitmq-diagnostics check_running`).
   - Stopping every node together can leave the cluster unable to start. The last node to stop has to be the first to start, otherwise the others wait for it and time out. That is a full outage of the control plane.
   - If the runbook restarts the nodes in a different order each time, it should say which node to start first.

2. **Restarting every nova and neutron service is too broad and in the wrong order.**
   - It causes a wider outage than needed. Many services reconnect to RabbitMQ on their own once the broker is healthy.
   - Check first which services actually lost their connections. Look for `AMQP server unreachable` or `connection reset` in the logs, or use `rabbitmqctl list_consumers` and `list_connections`.
   - If a restart is needed, restart only the services that did not reconnect. Do it in stages, such as the control plane first and then the compute and agent services.
   - Neutron agents on compute nodes (OVS, DHCP, L3) are the riskiest to restart. Restarting them can briefly disrupt tenant networking. Say whether that is acceptable and when.

3. **"Check that the alarm cleared" is too vague.**
   - Say which alarm this is. For example, it could be a memory or disk watermark, a partition, a queue backlog, or a connection count. The right fix depends on which one.
   - If it is a memory or disk alarm, restarting only hides the cause and the alarm is likely to come back. Free the disk or memory first, or find out why it filled.
   - Give exact checks, such as `rabbitmqctl list_alarms`, `rabbitmq-diagnostics alarms`, queue depths and the monitoring system.
   - Say how long to wait before concluding the alarm has cleared. Confirm that the alarm clears in monitoring and that an instance create or delete works end to end.

**Missing pieces**

- **Diagnose before acting.** Capture `cluster_status`, `list_alarms` and `list_queues` output before touching anything. That helps with the root-cause analysis and shows whether the restart helped.
- **Network partitions.** If the alarm is a partition, you need the partition-handling steps (`pause_minority`, `autoheal`, or restarting the minority side), not a plain restart.
- **Queue types.** Check for classic mirrored versus quorum queues. Rolling restarts need mirrors or quorum members in sync before the next node goes down.
- **Rollback and escalation.** Say what to do if a node does not rejoin: who to page and how to force-boot (`rabbitmqctl force_boot`) as a last resort.
- **Prerequisites.** Name who can run this, what maintenance window or notification is needed, and how to confirm nothing critical is mid-operation, such as live migrations or long-running instance builds.

**Suggested rewrite of the flow**

1. Record the current alarm, cluster status and queue depths.
2. Work out the cause (memory, disk, partition, backlog) and fix that first if you can.
3. Restart RabbitMQ one node at a time. Verify cluster health after each node.
4. Check the nova and neutron logs for services that lost their AMQP connections. Restart only those, in stages.
5. Verify with `list_alarms`, monitoring and a test instance create or delete.
6. Document the outcome and the cause.

If you paste the runbook text, or tell me where it lives, I can mark it up against these points. If you tell me which alarm it covers, I can make the checks specific to that alarm.