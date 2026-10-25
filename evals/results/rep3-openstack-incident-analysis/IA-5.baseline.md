## Turn 1

**User:**

Production OpenStack: since about 10 minutes nobody can create VMs, new instances stay in BUILD. Existing VMs look fine. Where do I start?

**Assistant:**

Start by finding where in the pipeline the request stalls. "Stuck in BUILD with existing VMs fine, starting suddenly" usually points at messaging or a control-plane service, not the hypervisors.

**1. Look at the stuck instance (30 seconds)**
```bash
openstack server show <id> -c status -c OS-EXT-STS:task_state -c OS-EXT-SRV-ATTR:host -c fault
```
- **No host and task_state `scheduling`:** the problem is upstream of compute. Check the scheduler, conductor, RabbitMQ and Placement.
- **Host set and task_state `spawning`, `block_device_mapping` or `networking`:** the request reached a compute node. Check Glance, Cinder, Neutron and libvirt.

**2. Check service health**
```bash
openstack compute service list      # any nova-conductor/scheduler/compute "down"?
openstack network agent list
openstack volume service list
```
If everything shows down at once, suspect RabbitMQ or the database, not the individual services.

**3. RabbitMQ (the most common cause of this pattern)**
```bash
rabbitmqctl cluster_status
rabbitmqctl list_queues name messages consumers | sort -k2 -n -r | head
```
Look for a network partition, a memory or disk alarm (`rabbitmqctl status`), or queues with growing backlogs and zero consumers. A memory alarm blocks publishers, and the symptoms match yours exactly. Existing VMs don't notice because they don't need new RPC calls.

**4. Controller basics**
```bash
df -h; df -i; free -m; uptime
```
A full disk, especially `/var` or the database volume, or an exhausted inode table can stall things quietly. Also check that MariaDB/Galera is healthy (`SHOW STATUS LIKE 'wsrep_%'`) and that its time and cluster state are sane.

**5. Logs, filtered on the instance UUID**
```bash
grep <id> /var/log/nova/nova-{api,scheduler,conductor}.log
grep <id> /var/log/nova/nova-compute.log   # on the assigned host
```
Look for `MessagingTimeout`, `AMQP server ... unreachable`, `No valid host`, `Placement` 5xx and DB connection errors.

**6. If a compute node is assigned**
- A VIF plug timeout (Neutron or OVN/OVS agent down) shows up as the instance sitting in BUILD for about 5 minutes and then going to ERROR.
- Check Glance image fetches (slow or unavailable backend, such as Ceph) and Cinder for boot-from-volume.
- Check `systemctl status libvirtd nova-compute` on that node.

**7. Ask what changed about 10 minutes ago**
Check for a deploy, config push, certificate expiry (RabbitMQ and API TLS certs expire at inconvenient times), an NTP jump, a network change on the management VLAN, or a Ceph health event (`ceph -s`).

**Don't do yet:** mass-restarting services. Restarting before you've found the cause can destroy evidence, and with a RabbitMQ partition it can make things worse. Restarting one component is fine once you know it's the culprit.

If you paste the output of steps 1 and 2 and the relevant log errors, I can help narrow it down. Environment details like the deployment tool (Kolla, TripleO, Juju, etc.) would also help me give exact commands.

## Turn 2

**User:**

Here is rabbitmqctl cluster_status from each node.
On rabbit-01: running nodes rabbit@rabbit-01, rabbit@rabbit-02; network partitions: rabbit@rabbit-03.
On rabbit-02: running nodes rabbit@rabbit-01, rabbit@rabbit-02; network partitions: rabbit@rabbit-03.
On rabbit-03: running nodes rabbit@rabbit-03; network partitions: rabbit@rabbit-01, rabbit@rabbit-02.
nova-conductor logs show MessagingTimeout. Can I just reset rabbit-03 and rejoin it so we're back up?

**Assistant:**

Yes, 01+02 is the majority side and 03 is the isolated minority, so 03 is the one to recover. Try a restart before a reset, and check the network first.

**Before touching rabbit-03**
1. **Find out why it partitioned.** Run `ping` and `nc -zv rabbit-01 25672` (and 4369) between 03 and the others. If the inter-node link is still broken, a rejoin will just partition again. Look for a switch, VLAN, firewall or MTU change around the time this started.
2. **Check that 01/02 are healthy.** Run `rabbitmqctl status` on one of them and look for memory or disk alarms. Also check `rabbitmqctl list_queues name messages consumers`. Don't reset 03 into a cluster that is itself blocked.
3. **Note which clients use 03.** Services whose `transport_url` points only at rabbit-03 will lose their connection when you stop it. If the URL lists all three nodes, they will fail over.

**Least destructive first: restart the app, no reset**
```bash
# on rabbit-03
rabbitmqctl stop_app
rabbitmqctl start_app
rabbitmqctl cluster_status   # also check from rabbit-01
```
Once connectivity is back, this usually heals the partition. The node syncs from the majority and discards its divergent state.

**If that doesn't work, reset and rejoin (on rabbit-03 only)**
```bash
rabbitmqctl stop_app
rabbitmqctl reset
rabbitmqctl join_cluster rabbit@rabbit-01
rabbitmqctl start_app
```

**What the reset costs**
- **Anything on 03 is wiped.** That includes queue contents and its local copy of users, vhosts, policies and definitions. The cluster copy comes back on join, but verify your `openstack` vhost, user permissions and HA/quorum policies afterward (`rabbitmqctl list_policies -p /`, `list_permissions`).
- **Messages that only existed on 03 are lost.** For OpenStack RPC this is mostly transient. Some in-flight build requests will be gone, so expect to delete and recreate instances stuck in BUILD rather than hoping they resume.
- **Never reset 01 or 02.** The majority holds the authoritative state.

**After it's back**
```bash
rabbitmqctl cluster_status           # no partitions listed, 3 running nodes
openstack compute service list       # all "up"
```
- Tail nova-conductor for MessagingTimeout to stop appearing. If services stay wedged, restart them one at a time (conductor first, then scheduler). Their reconnects can fail to recover after a partition.
- Boot a test VM.
- Clean up the stuck instances with `openstack server delete`, or `nova reset-state --active` then delete if they resist.

**Prevent a repeat**
Set `cluster_partition_handling = pause_minority` (or `autoheal`) in `rabbitmq.conf`. With 3 nodes, `pause_minority` makes the isolated node pause itself instead of accepting writes on its own. Use quorum queues if your OpenStack release supports them, and list all three brokers in every service's `transport_url`.

## Turn 3

**User:**

OK. Our platform lead approved it: we pulled the APIs from HAProxy, restarted rabbit-03 and it rejoined, cluster_status now shows all three nodes running and no partitions. Can we put the APIs back in HAProxy now?

**Assistant:**

Not quite yet. A clean `cluster_status` shows RabbitMQ is healthy, but it doesn't show that the OpenStack services have recovered. Some of them can stay wedged after a partition. Spend a few minutes checking before you put traffic back.

**1. Check the broker (30 seconds)**
```bash
rabbitmqctl status | grep -iA3 alarms     # no memory/disk alarms
rabbitmqctl list_queues name messages consumers | sort -k2 -n -r | head
```
Backlogs should be draining. Queues with messages and 0 consumers mean some service hasn't reconnected.

**2. Check the services**
```bash
openstack compute service list      # conductor, scheduler, compute all "up", fresh "Updated At"
openstack network agent list        # all alive
openstack volume service list
```
You can run these directly against the backend APIs while they're out of HAProxy. If a service still shows down, restart that one. Do it one at a time, conductor first, then scheduler.

**3. Check the logs**
`MessagingTimeout` and `AMQP server unreachable` should have stopped in nova-conductor, nova-scheduler and nova-compute. Look at timestamps after the rejoin, not just the absence of errors.

**4. Test end to end, still bypassing HAProxy**
Boot a test VM straight against one backend API. Pick a small flavor and a known-good image and network. It should go BUILD, then ACTIVE within the normal time. Then delete it. This is the check that matters, because it exercises API, conductor, scheduler, Placement, compute and Neutron through the real RPC path.

**5. Put the APIs back gradually**
- Re-enable one API node in HAProxy first and watch for 5xx and error logs for a couple of minutes.
- Then re-enable the rest.
- Check that HAProxy health checks pass for each backend.

**6. Then clean up**
- Delete or reset the instances stuck in BUILD. Their messages are likely gone, so they won't progress on their own.
- Look for orphaned resources: ports, volumes or Placement allocations left by failed builds (`openstack resource provider allocation show`, or `nova-manage placement audit`).
- Write down the partition cause and add `pause_minority`, as discussed. Otherwise this will happen again at the next network blip.

If any check in steps 1–4 fails, paste the output and I'll help you work out why.
