**Verdict: I wouldn't submit it as written.** CAB will probably bounce it, and the weak points are real risks, not paperwork gaps.

## Main problems

**1. Two high-risk changes are bundled.**
- If the control plane misbehaves after the window, you can't tell whether the certs or the patch/reboot caused it. That makes troubleshooting and rollback much harder.
- The OS update can change OpenSSL, crypto policy, Erlang or MariaDB versions. Those directly affect how RabbitMQ and Galera handle your new certs.
- Only the cert rotation has a deadline. Today is Oct 25, so Saturday is Oct 31 and expiry is about Nov 3. That leaves roughly 3 days of margin if the window slips.
- Recommendation: Saturday is certs only. Patch and reboot the controllers in a separate window as a rolling change, one controller at a time. If the patch can't wait, do it after the certs have run clean for a few days.

**2. "Restore old certs" isn't a rollback plan.**
- The old certs expire in 9 days, so this rollback only works until about Nov 3. Say so, and say what happens after that.
- The plan doesn't say where the old certs and keys are backed up or whether they have been verified. After 3 years, nobody should assume they can be recovered from the controllers.
- It doesn't say how services get restarted or reloaded with the old certs, or in what order.
- It doesn't say how you decide to roll back.
- There is no rollback at all for the patch/reboot: previous kernel in GRUB, package downgrade path, or VM snapshots of the controllers.

**3. Nobody has rotated these certs before, so there is no rehearsal and no known procedure.** I'd require a dry run in staging or a lab before CAB approval. A few things will probably catch you out:
- **Hidden consumers of the CA and certs.** Every service config that pins a CA bundle or verifies a server needs checking. That includes nova, neutron and cinder, the keystone auth CA settings, the oslo.messaging `ssl_ca_file` and the DB connection `ssl_ca` options. It also includes compute nodes, HAProxy or the load balancer, Horizon, monitoring, backup jobs and any external automation hitting the APIs.
- **Certificate contents.** Check SANs, key usage (RabbitMQ and Galera may use mutual TLS, so clientAuth and serverAuth both matter), key size and signature algorithm.
- **The CA's own expiry.** If the CA is also about 3 years old, it may be close to expiring too. If you're changing the CA, the new trust bundle has to reach everything before any leaf cert is swapped.
- **Galera needs more care than it looks.** Cert changes for the wsrep and SST/IST channels generally need a node restart. Decide the order of nodes and wait for each to rejoin and sync before moving on. Document the quorum and `safe_to_bootstrap` recovery procedure in case a node won't rejoin.
- **RabbitMQ.** Define how the new certs are picked up and how you'll confirm clients reconnect. Export definitions beforehand, and write down what happens if the cluster partitions.

**4. Missing from the CR:**
- A complete cert inventory, checked by actually probing every endpoint (`openssl s_client`) rather than working from memory.
- A minute-by-minute timeline that fits in 4 hours, with go/no-go checkpoints and a hard "abort and roll back by T+X" point.
- Pre-change backups: mariabackup or a Galera dump, RabbitMQ definitions, config directories, controller snapshots.
- Success checks: every endpoint serves the new cert, Galera `wsrep_cluster_size`=3 and Synced, `rabbitmqctl cluster_status` is healthy, and a test run of VM create, volume attach and network create passes.
- Impact statement. Running VMs should be unaffected. If the controllers also host L3/DHCP agents, say so, because that is a data-plane impact.
- Comms plan and named roles (executor, verifier, decision-maker).
- A pre-approved backup window (for example Sunday or Monday) in case Saturday fails. With a Nov 3 expiry you need this.

## Suggested structure
1. **Before the window (non-disruptive):** inventory, generate and validate new certs, back up everything, stage the new certs on disk alongside the old ones, distribute any new CA bundle, and rehearse in staging.
2. **Saturday window (certs only):** roll one controller at a time. Order the services by risk and verify after each (for example, API endpoints, then RabbitMQ, then Galera last). Keep the old certs in place until verification passes.
3. **Separate change:** patch and reboot the controllers one at a time, waiting for Galera to resync and RabbitMQ to rejoin between each, with its own rollback plan.

I can turn this into a revised CR draft (scope, risk assessment, timeline, verification checklist, rollback and backout criteria) ready to paste into your CAB template. If you'd rather have it as a shareable page, I can publish it. It would help to know your deployment tool (kolla-ansible, TripleO, OSA, manual), the cert authority, and whether the controllers also run network agents.