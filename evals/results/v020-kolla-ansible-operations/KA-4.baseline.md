The file didn't come through, and there's no `passwords.yml` in my working directory. I can't tell you which values matter for your deployment. You also don't need to filter: if the file leaked, treat every value in it as compromised and rotate all of them. `kolla-genpwd` does that in one pass anyway.

**Before tonight**

1. **Back up the old file and the current state.** Run `cp /etc/kolla/passwords.yml /root/passwords.yml.leaked`. Take a database backup too, for example with `kolla-ansible mariadb_backup`.
2. **Check what else was in the repo.** Other secrets could have been committed with it, such as `globals.yml` values, SSL certs and keys under `/etc/kolla/certificates`, SSH keys, and clouds.yaml or openrc files. Rotate those too.
3. **Purge the repo history.** Deleting the file in a new commit isn't enough. Use `git filter-repo` or BFG, force-push, and ask GitHub to clear cached views. Assume the old values were scraped regardless, because the repo was public for a day.
4. **Keep the file out of git.** Use `.gitignore`, or encrypt it with `ansible-vault`.

**Regenerating**

- `kolla-genpwd -p /etc/kolla/passwords.yml` only fills in empty values. It won't overwrite existing ones.
- To force new values, blank them first. For example, back the file up and run `sed -i -E 's/^([a-z0-9_]+):.*/\1:/' /etc/kolla/passwords.yml`. Then run `kolla-genpwd`. This also blanks `keystone_admin_password`, so the admin password changes. Check the result with `grep -c ': *$' /etc/kolla/passwords.yml`, which should print 0 afterwards.
- Alternatively, run `kolla-genpwd --passwords /etc/kolla/passwords.yml` after blanking only selected keys.

**Values that need special handling**

- **`ssh_key` and `kolla_ssh_key` (`private_key`/`public_key`).** `kolla-genpwd` regenerates the pair, but the public key must be on the target hosts for the `kolla` user. Run `kolla-ansible bootstrap-servers` first, or push the new key manually. Otherwise `reconfigure` can't reach the hosts.
- **`database_password` (MariaDB root).** Reconfigure normally handles the change, but this is where a Galera cluster can go wrong. Take the backup first, and watch the MariaDB containers during the run.
- **`rabbitmq_password`, `rabbitmq_cluster_cookie`, `rabbitmq_monitoring_password`.** Changing the Erlang cookie requires a full RabbitMQ restart, so expect a short outage across all services.
- **`keystone_admin_password`.** Update your `admin-openrc.sh` and `clouds.yaml`, and any automation that uses them.
- **`fernet_key_*` and `keystone_ssh_key`.** These get rotated, which invalidates existing tokens. All users are logged out.
- **`metadata_secret`, `nova_ssh_key`, `neutron_ssh_key` and `octavia_*` (including the Octavia certs).** Check that the new SSH keys reach the compute hosts. Octavia amphora certs may need `kolla-ansible octavia-certificates` regenerated, and existing load balancers may need a failover.
- **`memcache_secret_key`, `horizon_secret_key`, `ceph`/`cinder_rbd_secret_uuid`.** `cinder_rbd_secret_uuid` and the Ceph keyrings are tied to libvirt secrets and the Ceph cluster. If you use external Ceph, don't change the UUID or keys on the OpenStack side alone. Blank only the keys that are really yours.
- **Keys that aren't `kolla-genpwd` output.** Some are tied to external systems, such as `docker_registry_password`, external Ceph, or LDAP and Keycloak secrets. Rotate them at the source and then set them by hand.

**Running it**

```
kolla-ansible -i <inventory> prechecks
kolla-ansible -i <inventory> reconfigure
```

Reconfigure with new passwords restarts most services. Plan for downtime, not a rolling change. Afterwards, check these:

- `openstack service list`, `openstack compute service list` and `openstack network agent list` all look healthy.
- `docker ps -a` shows no restart loops.
- Existing VMs and volumes still work.
- Stored application credentials, EC2 credentials and Barbican secrets still work. The DB master key and fernet rotation can affect some of them.

If you paste the key names from `passwords.yml` with the values removed, for example `awk -F: '{print $1}' /etc/kolla/passwords.yml`, I can flag the ones that need special handling in your setup. Never paste the values.