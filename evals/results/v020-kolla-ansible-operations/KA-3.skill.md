## Verdict

**No, the plan is not tested, and two parts need changing before tomorrow.** It follows the documented replacement procedure only partly. The skill's reference material marks that procedure `DOCUMENTED-UNVERIFIED`: it comes from the Kolla-Ansible 2026.1 guide and code and hasn't been run on a lab. I've assumed you run three controllers with Docker. I haven't seen your inventory or versions.

## Problems with the plan as written

**1. `forget_cluster_node` with a reused name is contradicted by the references.**
- The clustering error page says to reset the replacement node instead of forgetting a name you will reuse. That is `stop_app`, then `force_reset` or `reset`, then `start_app`.
- The controller-replacement page runs `forget_cluster_node` even for a same-name replacement.
- The two pages disagree, and neither variant was run on a lab (open point, KA-OPS-08).
- Forgetting is destructive and can't be undone. A queue whose only replica was on ctl02 is lost.
- Settle this with your owner before you run it. I would not run `forget_cluster_node` just because it is in your plan.

**2. `--limit ctl02` is too narrow for `bootstrap-servers` and `deploy` (KA-OPS-09).**
- The guide requires all controllers in the limit, because RabbitMQ needs `/etc/hosts` entries for all of them.
- The documented sequence is `kolla-ansible bootstrap-servers --limit control`, then `pull --limit ctl02`, then `deploy --limit control`.
- `bootstrap-servers` on the healthy controllers can upgrade or restart Docker, and every container with it. Run it in a maintenance window. Consider Docker `live-restore` or pinning the exact Docker package version.
- With the same name, only the new node joins. With a new name, MariaDB and RabbitMQ would restart one by one on the healthy controllers.

## Steps your plan leaves out

All of these are `DOCUMENTED-UNVERIFIED` (KA-OPS-07 to KA-OPS-11).

1. **Before anything (read-only).** Don't start unless both survivors are healthy.
   - MariaDB should show `wsrep_cluster_size` 2, `Primary` and `Synced`.
   - `rabbitmqctl cluster_status` should show two running and ctl02 stopped.
   - Run `openstack network agent list --host ctl02`.
2. **Network agents.** On ML2/OVS without L3 HA, move routers and DHCP networks off ctl02's dead agents and disable those agents. OVN reschedules gateways itself.
3. **Delete ctl02's stale records before the new host registers (destructive).** Because the name is reused, delete its old network agents and compute services before the `deploy` step. This is not optional.
4. **Grow quorum queues and streams after the deploy.** A joining node isn't added to existing quorum queues or streams, and the 2026.1 role doesn't reconcile them. Run `rabbitmq-queues grow rabbit@ctl02 all`. Add stream replicas with `rabbitmq-streams add_replica`.
5. **Verify.**
   - Galera size is 3 and RabbitMQ shows three running nodes.
   - `check_if_node_is_quorum_critical` is clean on each node.
   - `list_queues name type members` shows three members.
   - Every agent is alive.
   - A test instance boots and is reachable.

## What to expect

- ctl02's MariaDB joins by full state transfer. It is slow and loads the donor node.
- Fernet keys are pushed from a healthy controller.
- While you run on two controllers, one more failure loses quorum. Avoid other changes until the work is finished.
- Use the same Kolla-Ansible version that deployed the platform. A newer one would deploy newer images to ctl02.
- The new hardware needs the same interface names, MTU and SSH access from the deploy host. It must also reach the VIP and your registry.

## Gaps I need from you

- Kolla-Ansible and OpenStack versions, and Docker or Podman.
- Whether you have exactly three controllers.
- OVS or OVN, and whether L3 HA is on.
- Whether ctl02 also ran Ceph monitors, etcd or Ironic. The documented procedure doesn't cover Ceph monitors, cells or Podman.
- The RabbitMQ queue type (quorum or classic) and whether it uses Khepri. `force_reset` doesn't exist with Khepri.
- Whether you have a recent MariaDB backup. I'd take one before you start.

Decision support only. State-changing steps above require approval by the accountable owner and should be executed under your change process.