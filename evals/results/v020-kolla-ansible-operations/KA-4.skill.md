**Don't run a blanket `kolla-genpwd` and `reconfigure` tonight. It's the wrong tool for this job.**

Your file didn't come through, so I can't triage individual values. That's fine for now, because you should assume every value in it is compromised and rotate all of them. Please don't paste the contents. If any secret has already appeared in a chat, ticket or log, treat it as exposed too.

**Why the one-shot plan fails**

`kolla-genpwd` only fills empty values, so you would have to blank the values first. Even then, a plain `reconfigure` only rewrites config files and restarts containers. It doesn't change passwords that already exist inside MariaDB, RabbitMQ, Keystone or Grafana. If you rotate everything and run `reconfigure`, the services will try new credentials that the backends don't know. Some secrets also can't be rotated this way at all. This follows the Kolla-Ansible 2026.1 rotation guide as summarised in my reference notes. I haven't tested most of it. Your version and topology are unknown to me, so check the guide for your release.

| Group | Secrets | What it costs |
|---|---|---|
| Rotate with `reconfigure` | `*_keystone_password`, most `*_database_password`, `keystone_admin_password`, `metadata_secret`, `keepalived_password`, `libvirt_sasl_password`, `*_ssh_key` (not `kolla_ssh_key`), and similar | Containers whose config changed restart |
| Manual step first, then `reconfigure` | `database_password` (MariaDB root), `nova_database_password`, `horizon_secret_key`, `grafana_admin_password`, `heat_domain_admin_password` | Nova's API may be disrupted partway through |
| Outage | `rabbitmq_password`, `rabbitmq_cluster_cookie` | Stop everything, delete the RabbitMQ containers and volumes, then `deploy`. Every API is down and in-flight messages are lost. Running VMs keep running. |
| Outside Kolla-Ansible | `kolla_ssh_key`, `docker_registry_password` | Handled separately |

The guide doesn't cover Fernet keys, TLS certificates or Ceph keyrings. These can also be exposed if they lived in the same repo, so check where they are stored.

**What I'd do instead**

1. **Revoke first (read-only, then state-changing).** Today, make the repo private and remove the file from history. Check the repo's access and clone logs for the window it was public. Then check whether the cloud's API endpoints and the MariaDB, RabbitMQ and Horizon ports are reachable from the internet. If the control plane is only reachable from inside your network, an outside attacker can't use these passwords yet. That buys you time to do the rotation properly.
2. **Take a MariaDB backup** before touching any database password.
3. **Back up the file**: `cp /etc/kolla/passwords.yml ./passwords.yml.bak`. Keep the copy out of any repo.
4. **Rotate in stages, not all at once.**
   - Stage 1: the reconfigure-group secrets. Empty them, run `kolla-genpwd -p /etc/kolla/passwords.yml`, then `kolla-ansible reconfigure`. The one lab run I have on record did this for Glance, Cinder and Heat with `--tags`, on Kolla-Ansible 22.2.0, all-in-one, without HAProxy. It was not a full multinode `reconfigure`.
   - Stage 2: the manual-step secrets, in the guide's order.
   - Stage 3: the RabbitMQ secrets, in a planned maintenance window.
5. **Check after each stage**: no containers restarting or unhealthy, `openstack compute service list` and `network agent list` healthy, Galera size and state correct, and one test instance created, reached and deleted.

**Decide before tonight**

- Is one night enough? Stage 1 is probably doable. The RabbitMQ stage is a full control-plane outage, and `database_password` plus `nova_database_password` carry real risk. If step 1 shows the control plane isn't exposed, I'd spread this over a planned window instead of rushing it.
- Who owns the change? Rotating secrets can cause an outage, so a named human owner should approve it.
- What are your Kolla-Ansible and OpenStack versions, your topology (how many controllers) and your container engine? I need these to give you exact commands.

I can write the stage-by-stage change plan with stop conditions and rollback if you give me those details. I can also check your `passwords.yml` structure if you redact the values (replace them with `<redacted>`) and send it.

Decision support only. State-changing steps above require approval by the accountable owner and should be executed under your change process.