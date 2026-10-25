## Turn 1

**User:**

Production OpenStack: since about 10 minutes nobody can create VMs, new instances stay in BUILD. Existing VMs look fine. Where do I start?

**Assistant:**

Existing VMs are fine and new ones sit in BUILD instead of going to ERROR. That usually means the request is being lost or stalled between the API and the compute node. It's rarely a hypervisor problem. Work through these checks in order.

**1. Check whether the instance was scheduled to a host**
```bash
openstack server show <id> -c status -c OS-EXT-STS:task_state -c OS-EXT-SRV-ATTR:host -c fault
```
- **Host is empty and task_state is `scheduling`:** the problem is the scheduler, conductor, RabbitMQ, or placement. Go to step 2.
- **Host is set and task_state is `networking`, `block_device_mapping` or `spawning`:** the problem is on the compute node or in Neutron, Cinder or Glance. Go to step 3.

**2. Check the control plane and message bus (the most likely cause)**
```bash
openstack compute service list          # are nova-scheduler / nova-conductor up?
systemctl status nova-scheduler nova-conductor     # (or docker/podman/k8s equivalent)
rabbitmqctl cluster_status
rabbitmqctl list_queues name messages consumers | sort -k2 -n -r | head
rabbitmqctl list_alarms                 # memory/disk alarms block publishers
```
- Look for a RabbitMQ memory or disk alarm, a network partition, a queue with a huge backlog, or queues with 0 consumers. A full disk on a controller is a common cause that starts suddenly.
- Check `nova-scheduler.log` and `nova-conductor.log` for `MessagingTimeout`, `AMQP server unreachable`, or DB connection errors.
- Check placement:
  ```bash
  openstack resource provider list
  ```
  It should respond and list your compute nodes. Also check the placement API logs.
- Check the database. Look for Galera/MySQL being down, read-only, out of connections, or having lost quorum. Run `SHOW STATUS LIKE 'wsrep_cluster_size'`.

**3. Check the compute side**
```bash
journalctl -u nova-compute --since "20 min ago" | grep -iE "error|timeout|trace"
```
- On the compute node, check `nova-compute.log` and the libvirt logs.
- Check whether Neutron is the blocker. Look for `Timed out waiting for network-vif-plugged`, then check `openstack network agent list` (OVS/OVN agents must be alive) and neutron-server and its DB.
- Check Glance (`openstack image list`, and whether the image store or Ceph is reachable).
- If the instance boots from a volume, check Cinder (`openstack volume service list`, and Ceph health with `ceph -s`).

**4. Find what changed about 10 minutes ago**
- Check recent deploys, config pushes, certificate expiry, NTP or time drift, a controller reboot, or a disk filling up. Run `df -h` on controllers and DB nodes.
- Check cron jobs and backups. A mysqldump or snapshot can lock tables or fill a disk.

**Once you find and fix the cause**
- Instances stuck in BUILD won't recover on their own. Delete them and recreate them, or run `nova reset-state --active <id>` followed by a delete.

If you can paste the output of step 1 and `openstack compute service list`, I can narrow it down quickly. Those two outputs usually show which of the two branches you're in.

## Turn 2

**User:**

Here is rabbitmqctl cluster_status from each node.
On rabbit-01: running nodes rabbit@rabbit-01, rabbit@rabbit-02; network partitions: rabbit@rabbit-03.
On rabbit-02: running nodes rabbit@rabbit-01, rabbit@rabbit-02; network partitions: rabbit@rabbit-03.
On rabbit-03: running nodes rabbit@rabbit-03; network partitions: rabbit@rabbit-01, rabbit@rabbit-02.
nova-conductor logs show MessagingTimeout. Can I just reset rabbit-03 and rejoin it so we're back up?

**Assistant:**

Yes, that's the standard way to heal a partition: restart or reset the minority node and let it rejoin the majority. Do it carefully, though, because a reset is destructive for that node.

**Before you touch anything**
1. **Check where the services connect.** Look at `transport_url` in `nova.conf`, `neutron.conf` and the others. If some of them point at rabbit-03, or HAProxy/VIP is still sending traffic to it, clients are talking to the isolated node. That would explain the MessagingTimeouts. Take rabbit-03 out of the HAProxy backend or the `transport_url` lists first. That may restore service on its own, without a reset.
2. **Check whether the queues are mirrored or quorum queues.** Run `rabbitmqctl list_queues name type policy` and `rabbitmqctl list_policies`. Anything that lived only on rabbit-03 (unmirrored classic queues) will be lost on reset. For OpenStack that is usually acceptable, because messages are transient and RPC is retried. Be aware of it anyway.
3. **Check the partition handling mode.** Run `rabbitmqctl environment | grep cluster_partition_handling`. If it is `ignore` (the default), this is why the partition never healed on its own. Consider `pause_minority` or `autoheal` afterwards.
4. **Check why the partition happened.** Look at the network between rabbit-03 and the other two, and at `/var/log/rabbitmq/*.log` for `net_tick_timeout`. If the cause is still present, it will partition again.

**Recovery steps**

Try the least destructive option first.

1. Restart only the app on rabbit-03. Often this is enough:
   ```bash
   rabbitmqctl stop_app
   rabbitmqctl start_app
   ```
   Restarting it should make it rejoin and discard its divergent state.

2. If it still shows a partition, do a full reset and rejoin:
   ```bash
   # on rabbit-03
   rabbitmqctl stop_app
   rabbitmqctl reset
   rabbitmqctl join_cluster rabbit@rabbit-01
   rabbitmqctl start_app
   ```
   Run it on rabbit-03 only. Never run it on 01 or 02, because that is the majority holding the good state.

3. Verify with `rabbitmqctl cluster_status` on all three nodes. All three should be running and the partitions list should be empty. Check `rabbitmqctl list_queues name messages consumers` as well.

**After it heals**
- Restart `nova-conductor`, `nova-scheduler` and `nova-compute`, and the same for the neutron agents if they log AMQP errors. Some oslo.messaging clients keep dead connections or stale reply queues after a partition, and a restart clears them.
- Create a test VM and check that it leaves BUILD.
- Delete the instances that are stuck in BUILD and recreate them, since their requests were lost.

Is the cluster mirrored or using quorum queues? And does `transport_url` list rabbit-03, or go through a VIP? Those two answers tell you whether you need the reset at all, or only need to take rabbit-03 out of the client path.

## Turn 3

**User:**

OK. Our platform lead approved it: we pulled the APIs from HAProxy, restarted rabbit-03 and it rejoined, cluster_status now shows all three nodes running and no partitions. Can we put the APIs back in HAProxy now?

**Assistant:**

Almost. Verify a few things first, because a cluster that reports healthy can still have stale clients and broken queues.

**Verify before re-adding**
1. **Cluster state on all three nodes:**
   ```bash
   rabbitmqctl cluster_status        # run on each node: 3 running, partitions empty
   rabbitmqctl list_alarms           # must be empty
   rabbitmqctl list_queues name messages consumers | sort -k2 -nr | head
   ```
   Look for queues with a large backlog, or queues with 0 consumers that should have some. Anything that lived only on rabbit-03 is gone.
2. **Restart the OpenStack services that talk to RabbitMQ.** Restart `nova-conductor`, `nova-scheduler` and `nova-compute`, plus the neutron agents and the cinder services if they logged AMQP errors. Do this before you put traffic back, because stale connections and reply queues are the usual reason things stay broken after a partition heals. Then check:
   ```bash
   openstack compute service list
   openstack network agent list
   openstack volume service list
   ```
   Everything should show `up`. Also grep the logs for any remaining `MessagingTimeout`.
3. **Run a canary VM while the APIs are still out of HAProxy.** Use one internal API node if you can reach it directly, or a test client. Check that the VM goes BUILD → ACTIVE, and that it gets a network port and an IP.

**Then re-add the APIs**
- Add them back one backend at a time, or one service at a time (nova-api first, then neutron, glance, cinder). Watch `nova-conductor` and RabbitMQ for errors between steps.
- Confirm that HAProxy health checks pass and that the client-facing API returns normal responses.
- Check that the instances stuck in BUILD are cleaned up. Delete them and recreate them, since their requests were lost.

**Afterwards**
- Set `cluster_partition_handling` to `pause_minority` (or `autoheal`) so a partition doesn't leave an isolated node accepting traffic again.
- Find out why rabbit-03 got partitioned (`net_tick_timeout` in the logs, switch or VLAN problems, a VM live-migration or host freeze). If the cause is still there, it will happen again.
- Check whether you should move to quorum queues, which tolerate this much better.

If the canary VM reaches ACTIVE and the service lists are clean, it is safe to put the APIs back.
