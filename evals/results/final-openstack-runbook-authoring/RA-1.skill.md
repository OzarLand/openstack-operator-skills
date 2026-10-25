I can't write files in this session (the Write tool is disabled), so I can't publish the runbook as a page. I'm giving it inline instead.

---

# Control plane messaging recovery (VM creation failing; RabbitMQ RPC and Galera unhealthy)

**Status:** Draft, not yet validated by anyone other than the author.
**Owner:** TODO (name a role). **Last validation:** never. **Review by:** TODO.

## Purpose and scope
Restore VM creation by returning RabbitMQ and Galera to a trusted state, while protecting running workloads.

**Use when:**
- New VM creation fails and existing VMs still run normally.
- RPC between services looks broken.
- Galera is unhealthy at the same time.

**Does NOT cover:**
- One RabbitMQ node missing while the rest form a majority with no partition. That needs a lighter rejoin procedure (TODO: write it).
- Only Galera or only RabbitMQ unhealthy.
- Compute hosts down, network agent loss, storage faults.
- Existing VMs also failing. Stop and escalate.

## Context
- **Stopping the APIs is controlled degradation.** It suspends new provisioning so clients stop writing into an unstable bus and database. Running VMs should keep running (TODO: confirm for your storage and network backends).
- **Purging queues discards in-flight messages.** The messages were presumed stale, and nobody recorded what was lost. Treat the purge as destructive.
- **Verify with a real VM.** A running process is not a healthy service.
- **The incident acted first and found the cause later.** This runbook puts the partition check first.

## Who may run it
- **Section 1** is read-only (TODO: confirm which roles may run it).
- **Sections 2–4** change state. They need a named approver who can accept a provisioning outage (TODO: name the role).
- **RabbitMQ and MariaDB steps** go to platform specialists (TODO: confirm).

## Preconditions and evidence
- Shell access to all RabbitMQ and Galera nodes and to HAProxy (TODO: how, from where).
- OpenStack admin CLI credentials.
- **Before any change, save:**
  - `cluster_status` from every RabbitMQ node.
  - Galera status from every node.
  - Queue depths and consumer counts.
  - Service logs with timestamps.
  
  Restarts erase most of this.
- Ask what changed recently, especially on the control-node network.

## Decision point
Run each check on **every** node. The commands are examples to verify for your versions and deployment tool.

| Check (read-only) | If you see | Go to |
|---|---|---|
| `rabbitmqctl cluster_status` on each node | Nodes disagree on members, or a partition is listed. This was the root cause last time. | Section 1, then continue with approval |
| same | Nodes agree but consumers are missing or queues pile up | Section 1, then **stop and escalate** (not covered by the incident) |
| same | One node absent, the rest are a majority, no partition | Out of scope: lighter rejoin |
| `wsrep_cluster_size` and `wsrep_cluster_status` on each Galera node | Size below expected, or not `Primary` | Section 1, then Section 3 only once the state is understood |
| same | Expected size and `Primary` everywhere | Galera is probably not the cause. Don't restart MariaDB without a reason (TODO: was the restart needed last time?) |

## Procedure

### Section 1: Assess (all read-only)
| # | Action | Why | Expected | If different |
|---|---|---|---|---|
| 1.1 | Create a test VM and watch it fail. Spot-check existing VMs. | Separates provisioning failure from data-plane failure. | Create fails; existing VMs reachable. | Existing VMs failing: stop and escalate. |
| 1.2 | Capture RabbitMQ cluster status on every node and compare. | A partition and a missing node raise the same alert. | Evidence saved; partition present or absent. | Unreachable node: treat as no majority and escalate. |
| 1.3 | Record queue depths and consumer counts. | Baseline for the purge and recovery. | Numbers saved. | — |
| 1.4 | Capture Galera size and status on every node. | Decides whether the database needs action. | Expected size, `Primary`. | Any non-Primary node: get a specialist before Section 3. |
| 1.5 | Record which compute services and agents are up. | Baseline for 4.1. | List saved. | Hosts down for other reasons are a separate problem. |
| 1.6 | Ask what changed recently. | A partition has a trigger. | Answer recorded. | TODO: record the trigger from the incident. |

> **Approval gate before Section 2.** The named approver accepts that:
> - VM creation is suspended until recovery finishes.
> - Queued messages will be lost.
> - RabbitMQ will restart.
>
> Record who approved and when. In a partition, first establish which side the services use and decide with the incident leader whether the purge is acceptable.

### Section 2: Suspend provisioning and reset RabbitMQ
| # | Action | Why | Type | Expected | If different |
|---|---|---|---|---|---|
| 2.1 | Pull the API backends out of HAProxy. | Stops new requests hitting an unstable bus. | state-changing | New requests stop; running VMs unaffected. | Running VMs affected: stop. TODO: which APIs, drain or disable. |
| 2.2 | Purge the RabbitMQ queues. | Removes stale RPC messages. | **state-changing, destructive** | Queues empty. | Don't force. Escalate. TODO: which queues, and how. |
| 2.3 | Restart the RabbitMQ cluster. | Clears the partition. | state-changing | All nodes rejoin and agree. | A node won't rejoin: stop. TODO: restart order and method; any reset or forced boot? |
| 2.4 | Check cluster status on every node, then consumers. | Confirms the cluster is whole and services reconnected. | read-only | No partition; consumers present. | Missing consumers usually mean a service restart. TODO: which services needed one. |

### Section 3: Restart MariaDB
The notes say only "restarted MariaDB". Order, method and any bootstrap are unrecorded, so don't improvise.

| # | Action | Type | Expected | If different |
|---|---|---|---|---|
| 3.1 | Restart MariaDB on the Galera nodes. | state-changing | All nodes rejoin. | No Primary, or the cluster won't re-form: stop. **Do not bootstrap on your own.** TODO: order, method, grastate/bootstrap. |
| 3.2 | Check size and status on every node. | read-only | Expected size; `Primary` everywhere. | Escalate to a Galera specialist. |

### Section 4: Verify, then reopen
| # | Action | Type | Expected | If different |
|---|---|---|---|---|
| 4.1 | Check compute services and network agents. | read-only | Same as or better than the 1.5 baseline. | Fix or investigate before reopening. |
| 4.2 | Create a test VM, ping it, delete it (internal path if the APIs are still out). | state-changing (test resource) | ACTIVE, answers ping, deletes cleanly. | Don't reopen. Go back to 2.4 and 3.2, then escalate. |
| 4.3 | Return the API backends to HAProxy. | state-changing | Endpoints answer; a user-path create works. | Take the APIs out again if errors return. |
| 4.4 | Watch error rates and queue depth for TODO (how long). | read-only | Stable. | Partition recurs: escalate. Restarting again is not a fix. |

## Stop and escalate
**Stop if:**
- Existing VMs are affected.
- RabbitMQ has no majority, or a node won't rejoin.
- Galera won't come back as Primary, or a bootstrap looks necessary.
- Monitoring is blind.
- The approver is unreachable.
- The failure recurs after recovery.

**Collect before escalating:**
- Cluster status from every RabbitMQ node and Galera status from every node.
- Queue and consumer counts, and logs with timestamps.
- The steps taken, with times.
- What changed recently.

**Escalate to:** TODO (on-call platform team, RabbitMQ and Galera specialists, incident leader).

## Do NOT do without escalation
- Purge queues or restart RabbitMQ before capturing status from every node.
- Reset or force-boot a RabbitMQ node, or bootstrap Galera.
- Restart MariaDB when Galera is healthy.
- Delete or evacuate running VMs to work around this.
- Edit the database directly.
- Reopen the APIs before the test VM passes.

## Recovery if the procedure fails
- The purge (2.2) can't be undone. After it, the only way forward is to finish the RabbitMQ restart and verify.
- Until 4.3 the APIs are out. Running VMs work and new provisioning is off. That is a safe state to hold while you call specialists.
- Steps to return a failed MariaDB restart to a trusted state weren't recorded (TODO: Galera specialist).
- Resuming after a stop is a new decision for the approver.

## After the incident
- Record the partition's trigger, or state that it's unknown.
- Consider alerting on partitions directly (TODO: owner).
- Identify operations lost to the purge and clean up stuck instances and volumes.

## History
| Date | Change | Why | By |
|---|---|---|---|
| TODO | First draft from incident notes | Capture knowledge after the incident | Claude draft |

Approaches tried that didn't work: none recorded (TODO: ask the incident team).

## Author notes
- **Sources:** only your one-paragraph summary. The actions and checks come from it. All of it is reported, with no output shown proving any step worked.
- **Inferred by me:**
  - The assess section and the decision table.
  - The approval gate, stop conditions and must-not-do list.
  - Putting verification before reopening.
  - The sequence of Sections 2–4 follows your incident order.
- **Gaps (TODO):**
  - Which APIs, and how they were pulled.
  - Which queues were purged.
  - RabbitMQ restart order and method.
  - MariaDB restart method and order.
  - Services that needed a restart.
  - The partition's trigger.
  - Owners, roles and escalation contacts.
- **Open question:** was the MariaDB restart needed? The cause found later was RabbitMQ only, so Galera may have recovered by itself.
- **Validation plan:** someone who didn't write this runs it, ideally in a non-production environment with an induced partition, or during real maintenance. An observer records questions without helping, and the document is corrected from them. TODO: who, where, when.

> Decision support only. State-changing steps above require approval by the accountable owner and should be executed under your change process.

I can also turn this into an HTML page or file once file writing works, or fill the TODOs if you paste more detail from the incident.