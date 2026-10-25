## Short answer: not yet

Don't run the runbook yet. `reset` on rabbit-03 is the only destructive step, and you haven't established that rabbit-03 simply left the cluster. A partition looks the same in the alert, and in that case a reset can wipe queues that services are still using.

You've shown me one view: `cluster_status` from rabbit-01 only. Everything else below is a hypothesis.

## Situation
- **Capability at risk:** messaging for the control plane (RPC and notifications). I don't know yet whether it's affecting anything.
- **Still working:** running instances normally keep running. rabbit-01 and rabbit-02 are a 2-of-3 majority, so the cluster is probably serving, but that is unconfirmed.
- **Unknown:** business impact, what changed recently, when it started, and whether anyone has already restarted anything. Please tell me these.

## Evidence
| Class | Statement |
|---|---|
| Observed | rabbit-01's `cluster_status` lists running nodes rabbit-01 and rabbit-02, and not rabbit-03. |
| Gap | `cluster_status` from rabbit-02 and rabbit-03. |
| Gap | Whether rabbit-03's process is up, and what its log says. |
| Gap | Partition-handling setting, metadata store (Mnesia or Khepri), queue type (classic or quorum), and RabbitMQ version. |
| Gap | Whether services are connected to rabbit-03 or are failing over. |

## Hypotheses
| Hypothesis | Would disprove | Check (read-only) |
|---|---|---|
| A. rabbit-03 is down or stopped (crash, host, OOM, maintenance) | Its process is running and it sees the others | Host and process state, plus its log |
| B. Network partition: rabbit-03 is alive and thinks it's the majority or a separate side | rabbit-03's own `cluster_status` shows the same two nodes as running | `cluster_status` from **each** node, looking for a `partitions` entry |
| C. rabbit-03 is up but stuck, or has a resource alarm (memory or disk) | No alarms in `rabbitmqctl status` | `rabbitmqctl status` on rabbit-03 |

## Next diagnostics (all read-only)
1. Run `rabbitmqctl cluster_status` on rabbit-02 and on rabbit-03. If rabbit-03 is alive and reports its own cluster view, that points to a partition.
2. Run `rabbitmqctl status` on rabbit-03, or check the process and host. Look for an alarm and the reason it stopped.
3. Read the RabbitMQ log on rabbit-03 and the other nodes around the time the alert fired. Look for `net_tick_timeout`, partition detected, or crash messages.
4. Run `rabbitmqctl list_queues name messages consumers` on a healthy node. See whether queues have messages but no consumers.
5. Check which broker the services (nova-conductor, neutron agents) are connected to. This shows whether anything is still attached to rabbit-03.
6. Before any change, save the cluster status output and the queue listing as evidence.

## Protect decision
I can't tell yet whether state is getting worse. Check whether queues are growing without consumers and whether instances are piling up in BUILD or ERROR. Compare the counts now and a few minutes later. If it is degrading, stopping API intake is an option, with the cost of no new provisioning. That decision belongs to whoever owns platform availability. If nothing is degrading, keep collecting evidence.

## Corrective options (not authorized)
- **If B (partition): stop, don't reset anything, and escalate.** Establish which side the services use first. Decide whether to stop the APIs, and get an owner's approval before touching any node.
- **If A or C (node left, majority intact): the runbook sequence is reasonable.** It's still state-changing, so do it deliberately:
  - **Prerequisites:** the diagnostics above are done, the evidence is saved, and rabbit-01 and rabbit-02 are confirmed healthy and serving.
  - **Blast radius:** the reset discards rabbit-03's local data. Queue replicas and classic mirrors held only there are lost. Clients connected to rabbit-03 will reconnect, and a rejoin can cause a burst of reconnects. Check the behaviour for your RabbitMQ version.
  - **Alternative:** if rabbit-03 merely stopped, try a plain `start_app` or restart first. That may rejoin it without wiping anything. Do this only once you've confirmed it stopped cleanly. It is the less destructive path.
  - **Stop condition:** abort if rabbit-01 or rabbit-02 shows an alarm or starts losing consumers.
  - **Recovery:** after a reset there is no way back for the data on that node.
  - **Approver:** the RabbitMQ or platform owner.
- Run one step at a time and verify each before the next.

## Verification before declaring recovery
- `cluster_status` shows all three nodes running, with no partitions and no alarms, when run from every node.
- Queues are recreated or healthy, with consumers connected.
- Nova, Neutron and Cinder services and agents are all reporting up.
- A test VM is created, reached and deleted.

## Open questions
1. What do `cluster_status` on rabbit-02 and rabbit-03 say?
2. Is the rabbit-03 process or host up? What's in its log?
3. Which RabbitMQ version, metadata store and queue type do you run, and what is the partition-handling setting?
4. What changed recently, and has anyone already restarted anything?
5. Is any workload visibly affected?

If you paste the outputs of items 1 to 3, I can tell you which branch you're on.

> Decision support only. State-changing steps above require approval by the accountable owner and should be executed under your change process.