## Turn 1

**User:**

Production OpenStack: since about 10 minutes nobody can create VMs, new instances stay in BUILD. Existing VMs look fine. Where do I start?

**Assistant:**

Start by finding out where the instance is stuck, then check RabbitMQ. Existing VMs keep running because they don't need the control plane. New builds depend on the message queue, scheduler and conductor, and those are the usual suspects.

**1. See how far the build got (1 minute)**
```bash
openstack server show <id> -c status -c OS-EXT-STS:task_state -c OS-EXT-SRV-ATTR:host -c fault
openstack server event list <id>
```
- **No host assigned, task_state `scheduling`:** the problem is upstream of compute. It's RabbitMQ, nova-scheduler, nova-conductor, placement, or the DB. This is the most likely case.
- **Host assigned, task_state `spawning` or `networking`:** look at nova-compute on that host, Neutron (port binding), Glance, or Cinder.

**2. Check service health**
```bash
openstack compute service list      # scheduler/conductor/compute should be "up"
openstack network agent list
openstack volume service list
```
If everything shows `down` at once, suspect RabbitMQ or the DB rather than the individual services.

**3. Check RabbitMQ (the most common cause of this pattern)**
```bash
rabbitmqctl cluster_status
rabbitmqctl list_queues name messages consumers | sort -k2 -n -r | head -20
rabbitmqctl list_alarms             # memory or disk alarms block publishers
```
Look for:
- A memory or disk alarm. The broker blocks publishers and everything hangs silently.
- Queues with growing message counts and 0 consumers (for example `scheduler`, `conductor`).
- A network partition in the cluster.
- Connection or file-descriptor exhaustion.

**4. Read the logs (last 15 minutes)**
```bash
grep -E "ERROR|Timeout|AMQP|MessagingTimeout|Connection reset" /var/log/nova/nova-scheduler.log /var/log/nova/nova-conductor.log | tail -50
```
Typical hits are `MessagingTimeout`, `AMQP server unreachable`, or `Lost connection to MySQL`.

**5. Check the other dependencies**
- **DB:** is Galera healthy? Run `SHOW STATUS LIKE 'wsrep_%'` and look for `wsrep_cluster_size`, `wsrep_ready`, and a flow-control pause. Check for locked or long-running queries.
- **Placement:** run `openstack resource provider list`. If it returns errors or is slow, the scheduler can't pick hosts.
- **Disk or inodes full** on the controllers (`df -h; df -i`), including the DB and RabbitMQ partitions.
- **Clock skew or an expired cert or token** (Keystone, or TLS between services) if the logs show auth errors.

**6. Ask what changed ~10 minutes ago**
Check for a deploy, config push, certificate rotation, controller reboot, network change, or a cron job or backup that hammered the DB or broker.

**Don't do these yet**
- Don't mass-restart services before you've looked at the logs. Restarting RabbitMQ or Galera carelessly can turn this into a bigger outage.
- Don't delete the stuck instances yet. They're evidence, and you can reset them later with `openstack server set --state error <id>`, then delete.

If you tell me the output of step 1 and the `rabbitmqctl` or `compute service list` results, I can narrow it down. If you want me to dig through logs here, point me at them. I don't have access to your cluster from this session.

## Turn 2

**User:**

Here is rabbitmqctl cluster_status from each node.
On rabbit-01: running nodes rabbit@rabbit-01, rabbit@rabbit-02; network partitions: rabbit@rabbit-03.
On rabbit-02: running nodes rabbit@rabbit-01, rabbit@rabbit-02; network partitions: rabbit@rabbit-03.
On rabbit-03: running nodes rabbit@rabbit-03; network partitions: rabbit@rabbit-01, rabbit@rabbit-02.
nova-conductor logs show MessagingTimeout. Can I just reset rabbit-03 and rejoin it so we're back up?

**Assistant:**

Probably yes, but you may not need a reset, and you should fix the network first. Here's the order I'd go in.

**What you have:** a split-brain. rabbit-01 and rabbit-02 are the majority and see each other. rabbit-03 is isolated and thinks it's running alone. That fits the MessagingTimeouts. Clients and queues on or pointing at rabbit-03 can't talk to the rest, and nova RPC calls go unanswered.

**1. Restore service first, without touching the cluster**
- If a load balancer or `transport_url` sends clients to rabbit-03, take it out (HAProxy backend disabled, or remove it from `transport_url`) so everything goes to 01 and 02. This can fix the symptom in minutes and is easy to undo.
- Check the setting with `rabbitmqctl environment | grep partition_handling`. If it's `ignore`, that explains why 03 kept serving instead of pausing. Consider `pause_minority` or `autoheal` afterwards.

**2. Find out why the partition happened**
- From each node, test the link to the others: ports 4369 (epmd), 25672 (inter-node) and 5672. Also check MTU, firewall or security-group changes, the switch or hypervisor host carrying rabbit-03, and `net_ticktime` timeouts in the RabbitMQ logs.
- If you rejoin 03 while the network is still flaky, it will just partition again.

**3. Check what lives on rabbit-03 before wiping anything**
```bash
rabbitmqctl list_policies
rabbitmqctl list_queues name type policy pid slave_pids   # run on 01 and on 03
```
- With quorum queues, or classic queues with HA mirroring, the data exists on 01 and 02, so losing 03's copy is fine.
- Un-mirrored classic queues whose master was on 03 will be lost on reset. For nova RPC queues that's usually tolerable, because they are transient and clients re-declare them. It's still better to know what you're dropping.

**4. Rejoin, trying the gentlest option first**
Run these on rabbit-03 only, once the network is fixed:
```bash
rabbitmqctl stop_app
rabbitmqctl start_app      # often enough: it rejoins and discards its minority state
rabbitmqctl cluster_status # should list all 3 and no partitions
```
Do the full reset only if it won't rejoin:
```bash
rabbitmqctl stop_app
rabbitmqctl reset          # wipes this node's data only
rabbitmqctl join_cluster rabbit@rabbit-01
rabbitmqctl start_app
```
Never run `reset` on 01 or 02. Make sure nothing is pointing at 03 while you do this.

**5. Verify**
- `cluster_status` on all three nodes shows no partitions, and `list_alarms` is empty.
- Queues have consumers again.
- If the conductor still logs MessagingTimeout after the broker is healthy, restart nova-conductor and nova-scheduler. Some stale connections don't recover on their own.
- Boot a test instance. Then clean up the stuck BUILD instances with `openstack server set --state error <id>`, followed by delete and a rebuild or retry.

If `stop_app`/`start_app` doesn't clear the partition, send me the output and I'll help with the next step.

## Turn 3

**User:**

OK. Our platform lead approved it: we pulled the APIs from HAProxy, restarted rabbit-03 and it rejoined, cluster_status now shows all three nodes running and no partitions. Can we put the APIs back in HAProxy now?

**Assistant:**

Not yet. A clean `cluster_status` shows the broker is healthy, but you haven't confirmed the services are talking over it again. Run these checks first, which take a few minutes, then re-enable.

**Check before re-enabling**
1. **Broker health:**
   - `rabbitmqctl list_alarms` is empty.
   - `rabbitmqctl list_queues name messages consumers` shows consumers on the nova queues (`conductor`, `scheduler`, `compute.*`) and no big backlog.
   - `cluster_status` on all three nodes agrees, with no partitions.
2. **Services reconnected:**
   - `openstack compute service list` shows scheduler, conductor and computes `up` with fresh timestamps.
   - `openstack network agent list` and `openstack volume service list` are also up.
   - Check the conductor and scheduler logs for new MessagingTimeout errors. If they keep appearing after the rejoin, restart nova-conductor and nova-scheduler.
3. **Root cause:** do you know why rabbit-03 partitioned? If the network fault is still there, it can re-partition right after you put traffic back. At least check inter-node connectivity and the RabbitMQ logs for `net_ticktime` or `nodedown` messages.
4. **Clear the stuck instances:** set the old BUILD instances to error and delete them (`openstack server set --state error <id>`, then delete). They are leftovers from the outage.

**Re-enabling**
- Bring the APIs back one backend at a time, not all at once. Watch the logs and a test request after each.
- Start with a read-only call (`openstack server list`), then boot a test instance (`openstack server create`) and confirm it reaches ACTIVE before you add the rest.
- Keep the HAProxy change handy so you can pull the backends out again.

**Afterwards**
- Set `cluster_partition_handling` to `pause_minority` (or `autoheal`) so a minority node stops serving by itself next time.
- Add monitoring on RabbitMQ partitions and alarms, and on queue consumer counts.

If any check in step 1 or 2 looks wrong, paste the output and I'll help work out what to do.
