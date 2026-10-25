I couldn't find a runbook file called "RabbitMQ alarm". The working directory is empty. So I'm reviewing the three steps as you wrote them, not a document.

**Main concerns**

1. **Restarting all three nodes at once can break the cluster.**
   - If the steps run together, you lose quorum. Quorum queues and classic mirrored queues can then lose messages or fail to recover.
   - Restart one node at a time. Wait until `rabbitmqctl cluster_status` shows it rejoined and `rabbitmq-diagnostics check_running` passes before starting the next.
   - Restart the nodes in the reverse of the order they stopped in. The last node to stop should be the first one back up. If it isn't, a node can sit waiting for peers that never come back.

2. **A restart may not fix the alarm.** The runbook doesn't say which alarm this is, and the cause decides the fix.
   - **Memory or disk alarm:** a restart clears it temporarily, but the alarm returns if the cause is still there (a backed-up queue, a stuck consumer, a full disk). Check `rabbitmqctl status` and `rabbitmq-diagnostics alarms` first. Then find which queues are growing with `rabbitmqctl list_queues name messages consumers`.
   - **Network partition:** this needs `cluster_status` and a decision about which side wins. A blind restart can lose data.
   - Add a diagnosis step before any restart, and record the evidence for the postmortem.

3. **Restarting every nova and neutron service is a very large blast radius.**
   - It includes nova-compute and the neutron agents on every host. That can interrupt API calls, in-flight operations like migrations and builds, and agent state.
   - OpenStack services usually reconnect to RabbitMQ on their own, so restart only the services that log connection errors or have stale connections.
   - If you do restart them, stagger them. Do the control plane first (`nova-api`, `nova-scheduler`, `nova-conductor`, `neutron-server`). Then do computes and agents in small batches, so you never drop the whole fleet at once.

4. **"Check that the alarm cleared" is too vague.**
   - Give an exact command, such as `rabbitmq-diagnostics alarms` returning nothing, plus the monitoring alert resolving.
   - Add health checks:
     - `openstack compute service list` shows all services up.
     - `openstack network agent list` shows all agents alive.
     - Queue depths are draining.
     - Consumers are attached.

**Missing pieces**
- Prerequisites: who can run this, a maintenance window or notification, and a note of the current state before you start.
- A rollback or escalation path if a node doesn't rejoin.
- The exact commands and host names for each step.
- Consider `rabbitmqctl stop_app` and `start_app`, or a rolling restart, as a lighter option than restarting the whole service.

If you share the runbook file or paste its text, I can review the actual wording and suggest an edited version. I can also draft a revised runbook with the ordering and checks above.