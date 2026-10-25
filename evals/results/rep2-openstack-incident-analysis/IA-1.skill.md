**Don't restart RabbitMQ and all the nova services yet.** Running the read-only checks below takes a few minutes. A blind restart could destroy evidence and make recovery harder, and it can't fix a Galera problem. Several shared components look unhealthy at once, so one cause, probably the network, could be behind all of them.

## Situation
- **Lost capability:** provisioning. New instances stay in BUILD or go to ERROR.
- **Still working:** existing VMs, per your report. That fits a control-plane problem, not a data-plane one.
- **Business impact:** unknown. I need to know which customers or workloads are waiting on provisioning.
- **What changed:** unknown. Please tell me about any deploy, config change, network or switch work, host maintenance, certificate rotation or upgrade in the last few hours.
- **Timeline:** started about 20 minutes ago. Tell me whether anyone has already restarted anything, since that is evidence too.

## Evidence
| # | Class | Statement | Source |
|---|---|---|---|
| 1 | Reported | New VMs stuck in BUILD, some ERROR; running VMs fine | you |
| 2 | Reported | nova-conductor logs full of `MessagingTimeout` | you |
| 3 | Reported | One of three Galera nodes has `wsrep_cluster_status = non-Primary` | you |
| 4 | Gap | RabbitMQ state (partitions, alarms, queues with no consumers) | not shown |
| 5 | Gap | Which Galera node it is, and whether the other two are Primary with size 2 | not shown |
| 6 | Gap | Whether the Galera and RabbitMQ nodes share hosts or network | not shown |

## Hypotheses
| Hypothesis | Would disprove it | Check (read-only) |
|---|---|---|
| **A. Network partition or flap** hit both Galera and RabbitMQ. They are often on the same controllers. | RabbitMQ is healthy with no partition, and the Galera node left for an unrelated reason. | Compare `rabbitmqctl cluster_status` from each node. Look for partition events in the logs. Run `ping`/MTU checks between the controllers. |
| **B. RabbitMQ partitioned or broken on its own.** This causes RPC timeouts. | Queues have consumers, there are no alarms, and the cluster is whole from every node's view. | `rabbitmqctl cluster_status` on each node, `list_queues name messages consumers`, `rabbitmqctl alarms` |
| **C. Services are hitting the non-Primary Galera node** through the load balancer or VIP. It rejects queries with "WSREP has not yet prepared node for application use". | Backend health shows that node already out, and DB errors are absent from the logs. | Check HAProxy backend state for the DB. Grep the nova logs for `WSREP`/`OperationalError`. |
| **D. Galera quorum is actually lost.** This would be much worse. | The other two nodes report Primary with `wsrep_cluster_size = 2`. | `SHOW STATUS LIKE 'wsrep_cluster%'` on **each** node |
| **E. Something else:** memcached, a certificate expiry, or a single stuck conductor. | Hypotheses A–D explain everything. | Certificate dates, conductor logs by `req-id` |

## Next diagnostics (all read-only)
1. **Galera on all three nodes:** `wsrep_cluster_status`, `wsrep_cluster_size`, `wsrep_local_state_comment`, `wsrep_ready`.
   - If two nodes are Primary with size 2, quorum is fine and one node is isolated. It's lower risk, but check whether the load balancer is still sending traffic to it.
   - If none is Primary, this is a quorum-loss incident and needs a separate, careful plan.
2. **RabbitMQ from each node, not just one:** `cluster_status`, `alarms`, `list_queues name messages consumers`. Check every vhost nova uses.
3. **HAProxy or VIP:** is the non-Primary Galera node still receiving traffic? Is the RabbitMQ endpoint healthy?
4. **Network between the controllers:** `ping`, MTU, interface errors, switch logs. Look for a flap about 20 minutes ago.
5. **Is it getting worse?** Count the instances in BUILD/ERROR now and again in a few minutes. Also watch queue depth over time.
6. **One failed request:** take a `req-id` and follow it through nova-api → conductor → scheduler → compute. Redact any `transport_url` or DB credentials before pasting logs.
7. **Preserve evidence before any restart:** save the logs from RabbitMQ, Galera, HAProxy and the conductors.

## Protect decision
Your API is still accepting new builds against an unstable bus and database. Every new request can leave an orphaned allocation or a half-built instance, which makes cleanup slower later. Step 5 will show whether this is happening.

**Option: controlled degradation.** Take the nova API (or the VM-create path) out of the load balancer.
- **Cost:** nobody can provision or change instances. Existing VMs keep running.
- **What it protects:** control-plane state while you repair it.
- **Caveat:** conductors, schedulers and agents keep running, so this isn't a full freeze.
- **Reopen condition:** the verification list below passes.
- **Who decides?** You need your manager or the platform owner to say yes. This is a real tradeoff. Provisioning is already down, so a deliberate pause costs little extra and protects your data. I'd raise it now.

## Corrective options (not authorized; need a named owner)
**Restart RabbitMQ**, only if diagnostics point to a RabbitMQ fault.
- **Risk:** reconnect storm from every agent. In-flight operations are lost.
- **Partition warning:** if the cluster is partitioned and you reset the wrong side, you lose queues the services are using.
- **Check first:** which side the services talk to.
- **Stop if:** it doesn't clearly improve within a few minutes.

**Restart all nova services**
- This won't fix a bus or DB fault, and it adds more noise. It also strands instances currently in BUILD.
- Do it last, if at all, and only after the bus and DB are healthy.

**Galera**
- Don't bootstrap or force-Primary anything yet. Bootstrapping the wrong node discards committed transactions.
- If a node must be rejoined, restart its mariadb **only after** confirming the other two are Primary. It then rejoins by IST/SST.
- If no node is Primary, find the most advanced node first using `safe_to_bootstrap` and `--wsrep-recover` seqno, then escalate.

**Cleanup** of BUILD/ERROR instances and orphaned allocations comes after the platform is stable. Use `nova-manage placement audit` (read-only) first.

Avoid combining several of these fixes at once. If you do, you won't know which one worked.

## Verification before declaring recovery
- Galera: all three nodes Primary, size 3, Synced.
- RabbitMQ: whole cluster, no partitions or alarms, queues have consumers.
- `openstack compute service list` and `openstack network agent list`: all up.
- No instances still accumulating in BUILD.
- A test VM is created, reachable and deleted.
- Only then reopen the API.

## Open questions for you
1. What changed recently, and has anyone already restarted anything?
2. Are RabbitMQ and Galera on the same three controllers or on separate hosts?
3. What do Galera's status counters show on the other two nodes? Paste the RabbitMQ `cluster_status` output from each node as well.
4. Who can authorise pausing the API, and who owns the downstream customers?
5. Which OpenStack release and deployment tool are you using (Kolla, others)? Commands and behaviour vary.

## For your manager
Provisioning is down because the control-plane message bus and database are unhealthy. Running workloads are unaffected. A blind restart risks making it worse and slower to fix. We're confirming the cause now and will give an update once the first diagnostics are in.

> Decision support only. State-changing steps above require approval by the accountable owner and should be executed under your change process.

Paste the outputs from steps 1–3 and I'll narrow this down quickly.