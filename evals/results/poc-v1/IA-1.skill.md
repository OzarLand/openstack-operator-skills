**Don't restart anything yet.** Spend about 5 minutes on read-only checks first. I can't see your systems, so everything below is either what you told me or a command for you to run.

## Situation
- **Lost:** creating new instances. Existing VMs run normally, which fits a control-plane problem and not a data-plane one.
- **Impact:** customers can't provision. Running workloads are unaffected. I don't know who is affected or how critical they are.
- **Timeline:** about 20 minutes ago. I don't know what changed (deploy, config, network, cert or host maintenance), so tell me.

## Evidence
| # | Class | Statement |
|---|---|---|
| 1 | Reported | New instances stay in BUILD and some go to ERROR |
| 2 | Reported | nova-conductor logs show many oslo.messaging `MessagingTimeout` |
| 3 | Reported | One of three Galera nodes has `wsrep_cluster_status = non-Primary` |
| 4 | Reported | Running VMs look fine |
| – | Gap | Status of the other two Galera nodes and of RabbitMQ (not shown) |

## Why restarting is risky
Two components in the control plane are suspect, and you can't yet tell which is the cause and which is the symptom.

- **Galera.**
  - A non-Primary node refuses writes. That is either one isolated node, which is tolerable, or a split where no side has quorum, which is an outage.
  - If conductors are stuck on the database, RPC calls time out, and `MessagingTimeout` can then be a secondary symptom. Restarting RabbitMQ wouldn't fix that.
- **RabbitMQ.** I haven't seen its state. A partition and a node that left the cluster raise the same alert but need opposite handling. A wrong restart or reset discards queues the services are still using. After any restart, every agent reconnects at once.
- **Stacked changes.** Restarting RabbitMQ and all the nova services together means you can't tell which action helped or hurt. Repeated restarts without a hypothesis are also a known way to make this worse.

## Hypotheses
| Hypothesis | Would disprove it | Check |
|---|---|---|
| H1: Galera lost quorum, or most of it, and the conductors block on writes | Two nodes Primary with size 2 or more and writes succeeding | `wsrep_%` status on all 3 nodes |
| H2: RabbitMQ is partitioned or alarmed (memory or disk) | `cluster_status` is identical from every node, with no partition or alarms | `cluster_status` from each node |
| H3: A network problem hit both (shared switch, VIP or LB) | Node-to-node connectivity is healthy | Ping and ports between control nodes, LB backend health |
| H4: An expired TLS cert on the bus or database | All expiry dates are in the future | `openssl s_client … -enddate` |

## Next diagnostics (all read-only)
1. **Galera, on each of the 3 nodes:**
   `SHOW GLOBAL STATUS WHERE Variable_name IN ('wsrep_cluster_status','wsrep_cluster_size','wsrep_local_state_comment','wsrep_ready','wsrep_flow_control_paused');`
   - **Two nodes Primary with size 2 or more:** the cluster is intact and one node dropped. That is probably not your cause, so look at RabbitMQ next.
   - **No Primary node:** this is a database outage and the most likely root cause.
2. **Which Galera node do the services write to?** Check the LB or VIP backend. If it points at the non-Primary node, that alone could explain the failures.
3. **RabbitMQ, from every node:**
   - `rabbitmqctl cluster_status` (look for partitions and alarms).
   - `rabbitmqctl list_queues name messages_ready consumers`, run with a timeout.
   - Queues with messages and no consumers are a bad sign.
4. **Follow one failed request.** Take a `req-…` ID from a failed instance's `fault` and grep it across nova-api, conductor, scheduler and compute. That shows which hop times out.
5. **Instance state:**
   - `openstack server list --all-projects --status BUILD` and again with `--status ERROR`. Is the count growing?
   - `openstack compute service list` (do the services report in?).
6. **Certificate expiry** on the DB, bus and API endpoints.
7. **Preserve evidence** before any change: save the logs and the queue and cluster status output.

## Protect decision
- **Is state degrading?** Probably. Instances are piling up in BUILD and ERROR while the APIs keep accepting requests. That creates half-built instances and orphaned Placement allocations, and they make recovery slower.
- **Option: controlled degradation.** Take nova-api (or the whole API tier) out of the load balancer while you fix the shared components.
  - **Cost:** all Nova API operations stop, including deletes and console access. Creation is already broken, so the extra loss is small.
  - **Limit:** it doesn't stop conductors, schedulers or agents.
  - **Reopen condition:** the verification list below passes.
  - **Decision owner:** your incident commander or manager. You shouldn't make this call alone.
- **Alternative:** keep investigating for 5 to 10 minutes. This is reasonable if the BUILD count is flat and the checks above are quick.

## Corrective options (not authorized, and the right one depends on the checks)
- **If one Galera node is isolated and the other two are Primary:**
  - Don't touch the two healthy nodes.
  - Point the LB away from the non-Primary node.
  - Investigate that node (network, `wsrep` logs) and let it rejoin through IST/SST.
- **If no Galera node is Primary:**
  - Do not bootstrap yet.
  - First find the most advanced node: `grastate.dat` seqno and `safe_to_bootstrap`, and `--wsrep-recover` after an unclean stop.
  - Bootstrapping the wrong node loses committed transactions.
  - Needs an owner decision, ideally a DBA.
- **If RabbitMQ is partitioned:** don't reset anything. Find out which side the services use, decide whether to stop the APIs first, and escalate. If you later purge queues, that discards in-flight operations, which must be an explicit decision.
- **If RabbitMQ is healthy and Galera is fixed:** restart nova-conductor only if it doesn't recover its connections by itself, as one change, then verify.

Each of these changes state. Before running one, you need a named approver, a stop condition and a recovery path.

## Verification before declaring recovery
- Galera is on all 3 nodes, Primary and at full size.
- RabbitMQ is a single cluster with no partitions or alarms, and queues have consumers.
- All compute services and network agents report in.
- A test VM builds, is reachable, and is deleted.
- Stuck BUILD and ERROR instances are reviewed and cleaned up. Resetting their state is state-changing, so do it one at a time under approval, and audit Placement with `nova-manage placement audit` without `--delete`.

## Open questions
1. What changed in the last hour or two?
2. What do the Galera status commands return on all three nodes?
3. What does `cluster_status` return, and which RabbitMQ version and queue type do you run?
4. Which node does the LB send database traffic to?
5. Who is your incident commander, and who approves API withdrawal?

## For your manager
"Provisioning is down because of a problem in the shared message bus or database layer. Restarting blindly can lose data and extend the outage. We're running a few minutes of read-only checks to pick the right fix and will update at [time]."

Paste the output of checks 1 and 3 and I'll narrow this to a specific cause and next step.

> Decision support only. State-changing steps above require approval by the accountable owner and should be executed under your change process.