# Configuration

`[Addition]` — everything in this file is distilled from the OzarLand
repository `kolla-ansible-deployment-patterns` at commit `dee2c60` (pages
`configuration/inventory-globals-overrides-and-secrets-layout.md`,
`configuration/tls-on-internal-and-external-endpoints.md`,
`configuration/local-registry-and-offline-deployment.md`,
`configuration/cpu-pinning-hugepages-and-numa-on-computes.md`,
`configuration/sriov-neutron-ports-and-nova-pci-alias.md`). The book does not
name Kolla-Ansible. Everything here is Kolla-Ansible 2026.1; other versions
change variables, defaults and option names. Lab runs were on Docker (with
Podman, replace `docker`; not tested). Untagged technical text is
unverified.

Secrets (rule 11): `passwords.yml`, the files under `certificates/`, keyrings
under `config/` and `clouds.yaml` hold secrets. Name keys only
(`database_password`, `docker_registry_password`); never ask for, quote or
reproduce a value, and never paste decrypted content into a review.

Rotating secrets is in host-and-database-operations.md, *Rotating secrets in
passwords.yml*; command choice and restart scope in commands-and-changes.md.

## Contents

- Configuration layout: inventory, globals.yml, overrides, passwords.yml
- TLS on internal and external endpoints
- Local registry and offline deployment
- CPU pinning, huge pages and NUMA
- SR-IOV

---

## Configuration layout: inventory, globals.yml, overrides, passwords.yml

**What Kolla-Ansible reads.** `--configdir` (or `KOLLA_CONFIG_PATH`; default
`/etc/kolla`). It passes `<configdir>/globals.yml` and
`<configdir>/passwords.yml` to Ansible as **extra variables**, then every
`.yml`, `.yaml`, `.json` of `<configdir>/globals.d/`, sorted by name.
`node_custom_config` (default `<configdir>/config`) holds the per-service
overrides. `-i` can be given several times (common and per-environment
inventories).

**Where a value lives, and who wins.**

| Value | Place | Precedence note |
|---|---|---|
| Common to the environment | `globals.yml` | Extra variables: beat inventory `group_vars`/`host_vars` |
| One topic reviewed alone | `globals.d/<nn>-<topic>.yml` | Loaded after `globals.yml`, wins over it: keep each variable in one file |
| Per group of hosts | inventory `group_vars/<group>.yml` | Loses to `globals.yml` |
| Per host | inventory `host_vars/<host>.yml` | Loses to `globals.yml` |
| Option of a service's config file | `config/<service>/...` override | Merged into the generated file |
| Secrets | `passwords.yml`, `certificates/`, keyrings | Never in clear in git |

So a value that must differ between hosts must **not** be in `globals.yml`:
there it silently applies to every host. This precedence rule is the most
common cause of a value that "does not apply".

**Override locations.** `config/<file>`, `config/<service>/<file>`,
`config/<service>/<hostname>/<file>`, and `config/global.conf` for every
service. `<hostname>` is the **inventory name** (`inventory_hostname`), not
the machine's hostname: on an all-in-one the inventory name is `localhost`.
For `nova.conf`, the 2026.1 `nova-cell` role merges, later wins:
`config/global.conf`, `config/nova.conf`, `config/nova/<service>.conf`,
`config/nova/<inventory_hostname>/nova.conf`,
`config/nova/<inventory_hostname>/<service>.conf`. There is no per-group
directory: per-group values go through inventory variables used as Jinja in
the override (overrides are rendered as templates before merging). INI files
of oslo.config services are merged section by section; non-INI files are
**replaced whole**, so a full copy must be kept current across upgrades. The
exact locations vary by role; the role's config task is the reference.

[LAB-VALIDATED: KA-CFG-01] Precedence and override locations. Lab: 2026.1,
Kolla-Ansible 22.2.0, all-in-one, Docker; same variable in `globals.yml` and
`globals.d/30-debug.yml`: `globals.d` won; in `globals.yml` and
`host_vars/<host>.yml`: `globals.yml` won; only in `host_vars`: applied;
`config/nova/<inventory-name>/nova.conf` and `config/nova/nova-compute.conf`
applied; `config/nova/<machine-hostname>/nova.conf` **ignored without any
message**. Not run: multinode inventory with `group_vars`, a second
environment, the full `nova-cell` merge order, non-INI overrides,
`config/global.conf`, several `-i`.

**What a host actually got.** Kolla-Ansible does not report an override
directory it did not use. After a change:
1. *State-changing* (files): `kolla-ansible genconfig -i <inventory>
   --configdir <env> [--tags <service>]` writes the new files on the hosts
   without restarting containers; a host or container restart then applies
   them unannounced, so `reconfigure` (or revert and `genconfig` again) soon
   after.
2. Read-only: on the host, read the generated file
   `/etc/kolla/<service>/<file>` (for example
   `/etc/kolla/nova-compute/nova.conf`).
3. Read-only: `kolla-ansible validate-config ...`; reports under
   `/var/log/kolla/config-validate` when issues are found. It ended with
   `failed=0` yet wrote one `.err` per Nova service with `ERROR:` lines for
   Kolla-Ansible's own unchanged configuration (`service_user/region_name is
   not part of the sample config`, `privsep_entrypoint/helper_command is not
   part of the sample config`): run it before the change too, and read only
   new lines.
4. *State-changing*: `kolla-ansible reconfigure ...` regenerates and
   restarts the containers whose configuration changed, one service after
   the other. Undo: revert the git change and run it again.

[LAB-VALIDATED: KA-CFG-02] Steps 1-4 with `-i`, `--configdir` and
`--vault-password-file`, `failed=0` each; after `genconfig` the running
`nova_compute` kept its old file, `reconfigure` recreated it with the new one.
Lab: 2026.1, Kolla-Ansible 22.2.0, all-in-one, Docker. Not run: multinode,
other services than Nova.

**Keeping it in git without secrets.** One layout from the source: one
repository, one directory per environment, each a complete `--configdir`
plus its `inventory/` (`hosts`, `group_vars/`, `host_vars/`), so every
command names `-i` and `--configdir` and `diff -r` shows what differs
between environments. Secret material: `passwords.yml` (every service
password, SSH keys, keys from `kolla-genpwd`); `certificates/`
(`kolla_certificates_dir`); backend credentials among overrides (Ceph
keyrings); `clouds.yaml` and `admin-openrc*.sh` from `post-deploy`. Losing
`passwords.yml` means losing every service password of the platform: back it
up like the database.
- Encrypt with Ansible Vault and commit the encrypted file; Kolla-Ansible
  passes `--ask-vault-pass`, `--vault-password-file`, `--vault-id` to Ansible.
  Keep the vault password file outside the repository. Before every commit,
  `head -1 passwords.yml` must read `$ANSIBLE_VAULT;...`, or use a pre-commit
  hook that refuses an unencrypted file.
- `kolla-genpwd` has no vault option: run it on a decrypted copy in a private
  directory (`umask 077`, `mktemp -d`), `ansible-vault encrypt ... --output
  <env>/passwords.yml`, then `shred -u` the copy.
- A `.gitignore` safety net: `environments/*/passwords.yml.*`,
  `environments/*/certificates/`, `environments/*/clouds.yaml`,
  `environments/*/admin-openrc*.sh`, `*.keyring`, `.vault-pass*`.

[LAB-VALIDATED: KA-CFG-03] Vault-encrypted `passwords.yml` (`kolla-genpwd
-p`, `ansible-vault encrypt`, `shred`; file starts `$ANSIBLE_VAULT;1.1;AES256`),
the `.gitignore` (`passwords.yml.old`, `clouds.yaml`, `admin-openrc.sh`, a
`.keyring` ignored; encrypted `passwords.yml` and `globals.yml` tracked), runs
with `--vault-password-file`. Lab: 2026.1, Kolla-Ansible 22.2.0, all-in-one.
Not run: HashiCorp Vault, `kolla-mergepwd`, a second environment.

**Not run.** [DOCUMENTED-UNVERIFIED: KA-CFG-04]
- *State-changing*: on an upgrade, `kolla-mergepwd --old ... --new ...
  --final ...` (on decrypted copies outside the repository, then re-encrypt)
  writes the final file; keep the old one, as a password changed by mistake
  breaks its services at the next `reconfigure` or `upgrade`. It keeps old
  unused entries unless `--clean`. Example files are under
  `<venv>/share/kolla-ansible/etc_examples/kolla/` (pip 22.2.0) or
  `.../etc/kolla/` (operating guide): use the one installed.
- HashiCorp Vault: `kolla-writepwd` to store, `kolla-readpwd` to recreate
  `passwords.yml` before a run.
- `--passwords <file>`: the 2026.1 source checks the file given but still
  passes `<configdir>/passwords.yml` to Ansible; keep the file at that path.
- To see which keys changed, `git diff` with a `textconv` driver set to
  `ansible-vault view`, locally only.

---

## TLS on internal and external endpoints

Not run on a lab: all of this section is from the Kolla-Ansible 2026.1 TLS
and ACME guides and the `loadbalancer` role code.

**What each switch encrypts.** Kolla-Ansible terminates TLS in HAProxy on the
VIPs. [DOCUMENTED-UNVERIFIED: KA-CFG-05]

| `globals.yml` switch | Encrypts | Certificate on the deploy host |
|---|---|---|
| `kolla_enable_tls_external` | clients to external VIP | `kolla_external_fqdn_cert`: `/etc/kolla/certificates/haproxy.pem` (cert, chain and key in one file) |
| `kolla_enable_tls_internal` | services and internal clients to internal VIP | `kolla_internal_fqdn_cert`: `/etc/kolla/certificates/haproxy-internal.pem` |
| `kolla_enable_tls_backend` | HAProxy to API containers (Barbican, Cinder, Glance, Heat, Horizon, Ironic, Keystone, Neutron, Nova, Placement) | first found of `<host>/<service>-cert.pem`, `<host>-cert.pem`, `<service>-cert.pem`, `kolla_tls_backend_cert` (default `backend-cert.pem`/`backend-key.pem`); valid for the address HAProxy uses for each host |

- Only one of internal or external enabled: the two VIP addresses must
  differ. A single VIP: TLS only through the internal variables.
- `kolla_internal_fqdn`/`kolla_external_fqdn` default to the VIP addresses:
  without DNS names the certificates need the VIPs as IP SANs; keep the VIP
  addresses in them even with names.
- Private CA: `kolla_copy_ca_into_containers: "yes"`, the CA under
  `/etc/kolla/certificates/ca/`, `openstack_cacert` (Ubuntu/Debian images
  `/etc/ssl/certs/ca-certificates.crt`; Rocky `/etc/pki/tls/certs/ca-bundle.crt`),
  `kolla_admin_openrc_cacert`. `kolla_haproxy_ssl_settings` defaults to
  `modern`, which refuses older TLS clients (`intermediate` exists).
- **What you may not expect: internal TLS turns on database TLS.**
  `database_enable_tls_internal` follows `kolla_enable_tls_internal` when
  `enable_proxysql` is true, which defaults to `enable_mariadb`. Then the
  `loadbalancer` role needs `proxysql-cert.pem` and `proxysql-key.pem` (and
  `proxysql-ca.pem`, a copy of the intermediate, if one signed it). The
  prechecks test only the HAProxy files: a missing ProxySQL file passes
  `prechecks` and fails `reconfigure` in the `loadbalancer` role. Every
  service's DB connection gets `?ssl_ca=<openstack_cacert>`, so the CA
  settings become mandatory. `kolla-ansible certificates` generates the
  ProxySQL files too, which is why a lab using it hides the gap. Backend TLS
  likewise drives `database_enable_tls_backend`.
- **What Kolla-Ansible does not do:** renew or watch certificates (except
  Let's Encrypt, `enable_letsencrypt`, renewed every 12 hours by its own
  container; needs a reachable ACME server, an internal one for internal
  certs, and HAProxy's socket then runs with admin access). The generated
  test CA is not for production. With `kolla_externally_managed_cert: true`
  it no longer copies the files: the other tool must place them on every host.

**Enabling TLS on a running platform.** [DOCUMENTED-UNVERIFIED: KA-CFG-06]
1. Read-only, on the deploy host: `openssl x509 -in
   /etc/kolla/certificates/haproxy-internal.pem -noout -subject -enddate -ext
   subjectAltName`; `openssl verify -CAfile
   /etc/kolla/certificates/ca/<your-ca>.crt <cert>` (add `-untrusted
   <intermediate>.crt` with an intermediate); the same `x509` on
   `proxysql-cert.pem`; `kolla-ansible prechecks -i <inventory>`.
2. *State-changing*: `kolla-ansible reconfigure -i <inventory>`, **without
   `--tags`** (endpoints and CA settings concern every service). It rewrites
   HAProxy, every service that calls another, and the Keystone catalogue
   (`http://` to `https://`); with ProxySQL every DB connection moves to TLS.
   Every API container restarts; API calls fail during the run. The internal
   VIP serves only HTTPS once the `loadbalancer` play has run, before the
   services are reconfigured. Clients that do not trust the CA fail
   afterwards; endpoint URLs stored elsewhere (tenant Heat stacks, external
   tooling, monitoring) must be updated. Running instances are not affected.
   Maintenance window, after a configuration backup and a MariaDB backup.
   Undo: switches back, the same full `reconfigure`.
3. Give clients the CA (`OS_CACERT` or the trust store); `kolla-ansible
   post-deploy -i <inventory>` regenerates `admin-openrc.sh` with `OS_CACERT`.

**Renewing.** [DOCUMENTED-UNVERIFIED: KA-CFG-07] Replace the file under
`/etc/kolla/certificates/`, check it with the `openssl` commands above.
- *State-changing*: HAProxy and ProxySQL certificates: `kolla-ansible
  reconfigure -i <inventory> --tags loadbalancer`. HAProxy restarts where its
  files differ, backups first then the VIP holder: API calls (and database
  connections, for ProxySQL) interrupted for a few seconds. Undo: previous
  file back, same command.
- *State-changing*: backend certificate: `reconfigure --tags <service>`
  (copied by each service's role), same short interruption for that service.
- A new CA: trust it everywhere first (new CA next to the old one in
  `certificates/ca/`, full `reconfigure`), then switch the certificate, then
  remove the old CA. This order follows from how trust works; the source
  says it was not run.

**Predictable failures.** [DOCUMENTED-UNVERIFIED: KA-CFG-08]

| Observation | Points to |
|---|---|
| Prechecks: `External haproxy certificate file is not found` / `Internal haproxy certificate file is not found` | file named by `kolla_*_fqdn_cert` missing on the deploy host |
| Deploy times out at `Wait for haproxy to listen on VIP` | HAProxy does not start: `.pem` without a key or with a mismatched key; `docker logs haproxy` |
| `reconfigure` fails in the `loadbalancer` role after enabling internal TLS | missing `proxysql-cert.pem`/`proxysql-key.pem` |
| Services log `CERTIFICATE_VERIFY_FAILED` after enabling internal TLS | CA not trusted in containers: `kolla_copy_ca_into_containers`, `openstack_cacert`, CA file under `certificates/ca/` |

Not covered by the source: RabbitMQ TLS (`rabbitmq_enable_tls`), libvirt TLS,
Octavia certificates, database certificate rotation in detail, Podman.

---

## Local registry and offline deployment

Not run on a lab: from the Kolla-Ansible 2026.1 guides and code, the `docker`
role of `ansible-collection-kolla` 2026.1 and the Distribution documentation.

**What a platform downloads, by default.** [DOCUMENTED-UNVERIFIED: KA-CFG-09]

| What | From (2026.1 default) | Used by |
|---|---|---|
| Container images | `quay.io`, namespace `openstack.kolla` (`docker_registry`, `docker_namespace`) | `pull`, `deploy` on every host |
| Kolla-Ansible | PyPI or Git | `pip install`, deploy host |
| Ansible collections | Galaxy (`requirements-core.yml`), `ansible-collection-kolla` Git (`requirements.yml`) | `kolla-ansible install-deps` |
| Docker packages | `download.docker.com` (`enable_docker_repo: true`, `docker_apt_url`, `docker_yum_url`) | `bootstrap-servers` |
| OS packages | hosts' repositories | `bootstrap-servers`, the OS |

A local registry removes only the first line; offline needs all five.
- Image reference: `<docker_registry>/<docker_namespace>/<docker_image_name_prefix><name>:<tag>`,
  `openstack_tag` default `<openstack_release>-<kolla_base_distro>-<kolla_base_distro_version>`.
  Mirror with the same namespace and tags and change only `docker_registry`.
- Private CA: `docker_registry_ca` (a path on the deploy host), copied to
  `/etc/docker/certs.d/<registry>/ca.crt` on targets. Login:
  `docker_registry_username` in `globals.yml`, `docker_registry_password` in
  `passwords.yml`; Kolla-Ansible does not manage the registry itself.
- `docker_registry_insecure` allows broken chains and plain HTTP, is
  strongly discouraged in production and disables registry authentication.
- **Does not help:** `docker_registry_mirrors` writes Docker's
  `registry-mirrors`, which works only for Docker Hub; Kolla images come from
  `quay.io`, so it is never used for them.
- A pull-through cache (Distribution `proxy.remoteurl`, one upstream) still
  needs the upstream for each first pull: not offline. Addressing a cache of
  `https://quay.io` through `docker_registry` was not tested by the source.
  Explicit copy (`docker pull`/`tag`/`push` or `skopeo`) works offline; the
  image list is what `kolla-ansible pull` fetches on a connected lab with the
  same `globals.yml`. Keep old `openstack_tag` images: they are what you roll
  back to. An upgrade needs the new release's images in the registry first.

**Changing registry settings on a running platform.** [DOCUMENTED-UNVERIFIED: KA-CFG-10]
1. Read-only, from a target host: `curl -s --cacert <registry-ca.crt>
   https://<registry>:<port>/v2/_catalog | head` and
   `.../v2/openstack.kolla/<image>/tags/list`.
2. *State-changing*: `kolla-ansible bootstrap-servers -i <inventory> --limit
   <new-or-maintenance-hosts>` writes `/etc/docker/daemon.json` and the CA,
   and **restarts Docker where the configuration changed, which restarts every
   container on that host** unless Docker's `live-restore` is enabled. On a
   running platform limit it to new hosts or a window per host. Undo: previous
   variables, run again.
3. `kolla-ansible pull -i <inventory>`: downloads images, starts nothing; run
   it before any deploy or upgrade offline, to find missing images without
   touching services.
- Offline deploy host: Kolla-Ansible from a local index or `pip download`
  wheels (same Python and platform); collections downloaded on a connected
  host (`ansible-galaxy collection download`, an archive of the
  `ansible-collection-kolla` branch), not tested by the source. Hosts: point
  `docker_apt_url`/`docker_yum_url` at a mirror or `enable_docker_repo: false`;
  point OS repositories at the mirror before `bootstrap-servers`.

**Where to look.** [DOCUMENTED-UNVERIFIED: KA-CFG-11]

| Observation | Points to |
|---|---|
| `http: server gave HTTP response to HTTPS client` | plain-HTTP registry: see deployment-errors.md, the section with that message |
| `x509: certificate signed by unknown authority` | `docker_registry_ca` unset or wrong CA; check `/etc/docker/certs.d/<registry>/ca.crt` |
| `manifest unknown` / `not found` for one image | image or tag missing: compare with `/v2/<namespace>/<image>/tags/list` |
| Hosts still reach `quay.io` | `docker_registry` not in the `globals.yml` used, or a variable overriding `docker_image_url` |
| `unauthorized`, `no basic auth credentials` | set `docker_registry_username` and the `docker_registry_password` key before `pull` |
| `bootstrap-servers` fails installing Docker | `docker_apt_url`/`docker_yum_url` or OS repos; `/var/log/apt/`, `/var/log/dnf.log` |
| Docker does not restart | malformed `daemon.json`: `journalctl -u docker` |

Not covered: Podman registry configuration, HA registry, building images,
signing and scanning.

---

## CPU pinning, huge pages and NUMA

**What Kolla-Ansible does not enable for you.** [DOCUMENTED-UNVERIFIED: KA-CFG-12]
Kolla-Ansible has no variable for any of this; it goes through the kernel
command line and `nova.conf` overrides.
1. **`NUMATopologyFilter` is not enabled.** Kolla-Ansible sets
   `[filter_scheduler] enabled_filters` only with Blazar or the fake driver;
   Nova's 2026.1 default is five filters (`ComputeFilter`,
   `ComputeCapabilitiesFilter`, `ImagePropertiesFilter`,
   `ServerGroupAntiAffinityFilter`, `ServerGroupAffinityFilter`) without it.
   The Nova guide: it "must be enabled" wherever NUMA awareness is used.
   Writing the option replaces the whole list: keep the five, add every
   filter you rely on (`PciPassthroughFilter` with SR-IOV/PCI,
   `AggregateInstanceExtraSpecsFilter`, `BlazarFilter` with `enable_blazar`,
   which the override would otherwise drop). Do not copy `available_filters`.
   There is one `enabled_filters`: merge the NUMA and SR-IOV needs into one line.
2. **Pinning needs `cpu_dedicated_set`** per compute (since Train, `PCPU`
   vs `VCPU` in Placement; `vcpu_pin_set` is the old option). `PCPU` and
   `VCPU` both count in the `cores` quota.
3. **Huge pages are a host setting**: persistent pages at boot (kernel
   command line, reboot); that memory is lost to host processes and to
   non-huge-page instances even when unused. `nova_libvirt` and `nova_compute`
   bind-mount the host's `/dev`, so `/dev/hugepages` is visible inside.
Order: filter first, then hosts, then flavors; a flavor published before the
filter lands instances on hosts that cannot hold them.

**Applying it on a running platform.**
1. *State-changing*, per host, emptied of instances first (plan the moves
   with `openstack-maintenance-planning`): append `hugepagesz=2M
   hugepages=<n> transparent_hugepage=never` to `GRUB_CMDLINE_LINUX`,
   `update-grub` (Rocky: `grub2-mkconfig -o /boot/grub2/grub.cfg`), reboot,
   which stops every instance left on the host. Undo: remove, regenerate,
   reboot. Read-only after: `grep Huge /proc/meminfo`, `mount | grep huge`,
   `cat /sys/devices/system/node/node*/hugepages/hugepages-2048kB/nr_hugepages`,
   `lscpu | grep -i -E "numa|thread"`, `lscpu -e` (a core and its sibling in
   the same set).
2. Inventory group `compute-pinned` (child of `compute`) with your own
   variables in `group_vars/compute-pinned.yml` (`nova_cpu_dedicated_set`,
   `nova_cpu_shared_set`, `nova_reserved_host_memory_mb`; not Kolla
   variables). `config/nova/nova-scheduler.conf` with the full
   `enabled_filters` plus `NUMATopologyFilter`; `config/nova/nova-compute.conf`
   with `[DEFAULT] reserved_host_memory_mb` and `[compute] cpu_dedicated_set`,
   `cpu_shared_set` from those variables, wrapped in `{% if
   nova_cpu_dedicated_set is defined %} ... {% endif %}`. Without the guard
   the template fails on computes outside the group; empty defaults would
   render `cpu_dedicated_set = `. Outside the group Nova keeps 512 MB reserved.
3. *State-changing* (files): `kolla-ansible genconfig -i <inventory> --tags
   nova --limit <host>`; read-only: `sudo grep -A3 "^\[compute\]"
   /etc/kolla/nova-compute/nova.conf` on the host.
4. *State-changing*: `kolla-ansible reconfigure -i <inventory> --tags nova
   --limit control,compute-pinned` restarts `nova_compute` on the limited
   computes and `nova_scheduler`. Instances keep running. **The scheduler is
   unavailable for minutes, not seconds**: after the restart, *Refresh cell
   cache in nova scheduler* reloads it and new workers started 2 min 44 s
   later; instances created meanwhile went to `ERROR` with `MessagingTimeout`
   (re-created about 4 min later, they booted). Wait for `Starting scheduler
   node` in `nova-scheduler.log`.
5. Verify, read-only (Placement needs `osc-placement`): `openstack resource
   provider inventory list <uuid>` shows `PCPU`; `grep -i
   "dedicated\|shared\|error" /var/log/kolla/nova/nova-compute.log` (quiet is
   normal). Flavors: `hw:cpu_policy=dedicated`, `hw:mem_page_size=large`,
   `hw:numa_nodes=1`; boot one each, then `docker exec nova_libvirt virsh
   vcpupin <domain>` and `virsh dumpxml <domain> | grep -A3 -E
   "hugepages|numatune"`.

[LAB-VALIDATED: KA-CFG-13] (source page still `draft`) Steps 1-5. Lab: 2026.1, Kolla-Ansible 22.2.0,
all-in-one VM (4 vCPUs, 1 NUMA node, no SMT, nested KVM), Docker, ML2/OVS;
512 pages of 2 MB; `cpu_dedicated_set = 2-3`, `cpu_shared_set = 1`,
`reserved_host_memory_mb = 1024`: Placement went from `VCPU 4` to `VCPU` 1,
`PCPU` 2, `MEMORY_MB` reserved 1024; `genconfig` restarted nothing; the
pinned instance on host CPU 2, the others on CPU 1; all three
`<numatune mode='strict'>`, the huge-page one `<page size='2048' unit='KiB'
nodeset='0'/>`; scheduler gap 2 min 44 s. Not run: several NUMA nodes,
sibling threads (`hw:cpu_thread_policy`), a compute outside the group (the
empty-file path), Blazar, the undo.

**Not run.** [DOCUMENTED-UNVERIFIED: KA-CFG-14] Undo (remove the overrides,
reconfigure again). Changing the CPU sets of a host that runs instances:
placed instances keep their CPUs, and a layout that no longer covers them was
not tested; change sets only on an empty host.

**Where to look.** [DOCUMENTED-UNVERIFIED: KA-CFG-15]

| Observation | Points to |
|---|---|
| `No valid host was found`, pinned flavor | `nova-scheduler.log`; no `PCPU` inventory anywhere: `cpu_dedicated_set` unset |
| Lands on a host, fails and is rescheduled (huge-page/NUMA flavor) | `NUMATopologyFilter` missing; `nova-compute.log` on that host says why |
| `nova_compute` restart loop after the change | invalid CPU list or CPUs absent on the host: `nova-compute.log`, `docker logs nova_compute` |
| libvirt memory error at start | `/var/log/kolla/libvirt/libvirtd.log`, `HugePages_Free` per NUMA node in sysfs |

---

## SR-IOV

Not run on a lab (needs SR-IOV hardware): from the Kolla-Ansible 2026.1
SR-IOV guide, the `neutron` and `nova-cell` roles, and the Neutron and Nova
guides.

**What `enable_neutron_sriov` does, and does not.** [DOCUMENTED-UNVERIFIED: KA-CFG-16]
- Does: adds `sriovnicswitch` to the ML2 mechanism drivers; deploys
  `neutron_sriov_agent` on the `compute` group with `physical_device_mappings`
  from `neutron_sriov_physnet_mappings` (`<physnet>: <pf-interface>`); writes
  `[pci] passthrough_whitelist` in the computes' `nova.conf`
  (`nova_pci_passthrough_whitelist`), one entry per PF **matched by interface
  name** (`devname`): a PF named differently on a host, or renamed, matches
  nothing there and ports fail to bind. Set the mapping per host in
  `host_vars` if names differ; the PF name must exist wherever the agent runs.
- Does not: BIOS SR-IOV/VT-d, IOMMU on the kernel command line, VFs creation
  and persistence; `PciPassthroughFilter` (add it to the one
  `enabled_filters` line, see the CPU pinning section).
- Trap 1: `flat_networks` and `network_vlan_ranges` are lists and an override
  **replaces** them. Kolla-Ansible already writes `flat_networks` from
  `neutron_physical_networks` (and VLAN ranges with Ironic). Read what is
  rendered (`sudo grep -E "^(flat_networks|network_vlan_ranges)"
  /etc/kolla/neutron-server/ml2_conf.ini`) and keep every existing physnet: a
  physnet missing from the new lists cannot host new networks (existing ones
  are not deleted).
- Trap 2: `passthrough_whitelist` is the older name of `[pci] device_spec`.
  A `device_spec` override for the PCI alias method gives two lists for one
  option; which one Nova keeps was not tested. Override
  `nova_pci_passthrough_whitelist` in `globals.yml` with the full list,
  keeping the SR-IOV entries.
- Known limits (Neutron guide): no security groups on SR-IOV ports;
  restrictions on live migration of `direct` ports. Nova PCI alias matches
  vendor and product only: no choice of NIC port.

**Host preparation.** [DOCUMENTED-UNVERIFIED: KA-CFG-17]
*State-changing*: `intel_iommu=on` on the kernel command line needs a reboot
(move instances first). *Destructive* for instances using VFs: `echo <n> |
sudo tee /sys/class/net/<pf>/device/sriov_numvfs`; on some NICs changing the
number fails with `Device or resource busy` until set to `0` first, which
removes existing VFs and cuts every instance using them. The value does not
survive a reboot: persist it (network config, udev rule or systemd unit).
Undo: remove the parameter and reboot; `echo 0`. Read-only checks:
`grep -o "intel_iommu=on" /proc/cmdline`, `cat .../sriov_numvfs`, `ip -d link
show <pf>` (one `vf N` line per VF), `lspci | grep -i "virtual function"`.

**Applying it.** [DOCUMENTED-UNVERIFIED: KA-CFG-18]
*State-changing*: `kolla-ansible reconfigure -i <inventory> --tags
neutron,nova` changes ML2 (restarts `neutron-server`), deploys the agent on
every compute, changes `nova.conf` on computes and scheduler (restarts). Running
instances keep running; Neutron and Nova API calls may fail during the
restarts. Undo: `enable_neutron_sriov: "no"`, remove the overrides,
reconfigure; the `neutron_sriov_agent` containers stay until removed by hand.
Verify read-only: `openstack network agent list --agent-type nic` (one alive
`NIC Switch agent` per compute); `sudo grep -A2 "^\[pci\]"
/etc/kolla/nova-compute/nova.conf`. Then, *State-changing* (admin, test
project): a VLAN provider network on the SR-IOV physnet, a subnet, `openstack
port create --vnic-type direct`, a server on that port; `ip -d link show <pf>`
shows its MAC and VLAN on one VF. Undo in order: delete server, port, network.

**Where to look.** [DOCUMENTED-UNVERIFIED: KA-CFG-19]

| Observation | Points to |
|---|---|
| `No valid host was found` with an SR-IOV port | `nova-scheduler.log`: `PciPassthroughFilter` missing, or no free VF on that physnet |
| Port `binding_failed` | `neutron-server.log`, agent log under `/var/log/kolla/neutron/` (`neutron-sriov-nic-agent`): physnet not mapped, agent down |
| Agent not alive | `docker logs neutron_sriov_agent`: PF name in the mapping absent on that host |
| Instance fails to start | `nova-compute.log`, `libvirtd.log`: IOMMU off, no VFs, VF in use |
| No traffic in the instance | switch port not trunking the VLAN to the PF; guest VF driver |

Not covered: OVS hardware offload, `macvtap`/`virtio-forwarder`, SR-IOV with
NUMA affinity policies, InfiniBand, live migration of SR-IOV instances.
