**Don't submit this as written. I'd recommend CAB reject it, or send it back, in its current form.** The certificate rotation is justified. The plan has four problems, and the first two are serious.

## Blocking issues

**1. The rollback plan doesn't work.**
- "Restore old certs" has no steps, no verification and no decision point.
- It only works until the old certs expire. Saturday is Oct 31 and expiry is about Nov 3, so you'd have about 3 days of margin. A failed rotation that gets rolled back leaves you with certs that die shortly after.
- It doesn't cover the OS update at all. You can't cleanly roll back a patched controller except by booting the previous kernel or restoring a snapshot. Package downgrades of mariadb, erlang, rabbitmq or OVS are not reliable.
- Required: a tested rollback per component, a named go/no-go checkpoint with a time (for example "if Galera isn't Synced on all nodes by T+1:30, roll back"), and a second window reserved before Nov 3.

**2. The two changes are bundled.**
- If a controller comes back unhealthy after the reboot, you can't tell whether the cause is the new certs, the new packages or the reboot.
- The cert rotation is deadline-driven. The OS update isn't. Together they put two high-risk changes into a 4-hour window.
- Recommendation: make the certs the Saturday CR. Do the patching in a separate CR, rolling one controller at a time with a soak between nodes.
- If you must keep both, make the patching an optional gated phase. It would only start if the certs are fully validated with at least 90 minutes left, and it would need its own rollback.

**3. There's no rehearsal, and nobody has done this before.**
- Nobody has rotated these certs in 3 years, so no one has current knowledge of the procedure.
- Required: run the full procedure in a lab or staging environment first, and attach the evidence to the CR.

**4. The cert inventory and CA question are unanswered.** The answers change the whole procedure.
- **Is the CA changing, or just the leaf certs?** Check the CA's own expiry too.
  - If the CA changes, every client needs the new trust bundle before any server cert is swapped. That includes all OpenStack services, compute nodes, Horizon, monitoring, load balancers and external automation.
  - If it's the same CA, the rotation is much simpler.
- **Galera:** wsrep replication and SST use the same cert and CA configuration on every node.
  - With a new CA, a rolling restart can fail because nodes can't talk to each other. You may need a full cluster stop and a bootstrap from the most advanced node. That's an API outage and a different risk profile.
  - With the same CA, a rolling restart is fine.
- **RabbitMQ:** do a rolling restart, one node at a time, and check for partitions. Every service's `oslo.messaging` connection must reconnect with verification still passing.
- **Other certs on the same age:** check libvirt/QEMU TLS, VNC proxy, HAProxy/VIP, Keystone, etcd, OVN and Ceph RGW. Anything missing from the inventory will break on Nov 3 anyway.
- **Deployment tool:** I don't know what deploys this (kolla-ansible, OSA, TripleO or something else). Rotate through that tool. Hand-editing files will be reverted on the next deploy run.

## Required additions

- **Backups, taken and verified:** all old certs and keys with ownership, permissions and SELinux contexts, plus config backups and a fresh Galera backup (mariabackup or mysqldump). Add VM or LVM snapshots if the OS update stays in scope.
- **Order of work:** trust bundle, then RabbitMQ, then Galera, then API endpoints, with validation after each step.
- **Validation checklist:**
  - `openssl s_client` against every endpoint, checking SANs, chain and expiry.
  - `rabbitmqctl cluster_status`.
  - `wsrep_local_state_comment = Synced` and `wsrep_cluster_size = 3`.
  - `openstack endpoint list` and `openstack service list`.
  - An end-to-end test: create a VM, a volume and a network.
- **Impact statement:** the data plane is unaffected, but API calls will fail during restarts. Say how long and what you'll communicate.
- **Timeline with durations,** and the checkpoints where you stop and roll back.
- **Monitoring:** a cert-expiry alert at 30/14/7 days, and an owner and calendar entry for the next rotation.
- **If the patch stays in scope:** list the packages being updated. Check specifically for mariadb, erlang, rabbitmq, OVS/OVN and the kernel, because those change behaviour. Reboot one controller at a time and wait for Galera to be Synced, RabbitMQ to be clustered and the VIPs to be healthy before the next one. Never reboot them together.

## Suggested structure
1. **Now through Thursday:** inventory, answer the CA question, rehearse in lab, take backups, and issue the new certs ahead of time.
2. **Saturday window:** cert rotation only, with checkpoints.
3. **Reserve a fallback window before Nov 3** in case the rollback is invoked.
4. **Separate CR:** OS patching and rolling reboots, scheduled after the certs have been stable for a few days.

If you tell me the deployment tool and whether the CA is changing, I can draft the revised CR with the runbook, checkpoints, rollback steps and validation checklist. I can also publish it as a page you can share with CAB.