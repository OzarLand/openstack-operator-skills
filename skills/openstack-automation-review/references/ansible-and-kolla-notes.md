# Ansible and Kolla-Ansible review notes

`[Addition]` — everything in this file is added by this repository; the book
does not name any deployment or automation tool. Each item maps a book
safeguard [Book: Ch. 16] to tool mechanics. Behaviour changes between
versions: verify against the documentation of the Ansible and Kolla-Ansible
versions in use.

## Contents

- Mapping book safeguards to Ansible mechanisms
- Ansible patterns that hide risk
- Kolla-Ansible specifics
- OpenStack resource automation (scripts, SDK, CLI loops)

## Mapping book safeguards to Ansible mechanisms

| Safeguard (book) | Ansible mechanism to look for |
|---|---|
| Preview / dry run | `--check` and `--diff`; note that `command`/`shell` tasks are skipped in check mode unless written to support it, so a clean check run can hide most of a shell-heavy playbook |
| Explicit scope | `hosts:` patterns, `--limit`, inventory groups; beware `hosts: all` and empty-group behaviour |
| Bounded blast radius | `serial:` (batches), `throttle:`, `forks` |
| Stop conditions | `max_fail_percentage`, `any_errors_fatal`, explicit `assert`/`fail` tasks on health checks between batches |
| Pre/post checks | `assert` tasks on service health, API checks, `wait_for`/`uri` checks that test the capability |
| Confirmation | `pause` prompts or a separate approval step in the pipeline for destructive plays |
| Idempotency | modules over raw `shell`; `changed_when`/`creates`/`removes`; a second run reports no changes |
| Observability | callback plugins or logs recording what changed, per host, per run |

## Ansible patterns that hide risk

- `ignore_errors: true` or `failed_when: false` on tasks whose failure matters.
- Handlers that restart a shared service (RabbitMQ, Galera, nova services) on
  every host at once when a config file changes; check whether restarts are
  serialized.
- `run_once` combined with a dynamic host choice that may pick a node in a bad
  state (e.g. a non-Primary Galera node).
- Unbounded loops over `openstack server list` output that delete, migrate or
  reset resources.
- Secrets in plain variables or logged output (`no_log` missing).
- Roles pinned to moving branches; or pinned to `stable/<series>` branches
  that are renamed when the series becomes Unmaintained [Book: Ch. 14].

## Kolla-Ansible specifics

- Run `kolla-ansible prechecks` before deploy/upgrade operations.
- `deploy`, `reconfigure` and `upgrade` regenerate configuration and may
  restart containers for the targeted services; scope with `--limit` and
  `--tags` and know which containers will restart before running in production.
- Configuration overrides under `/etc/kolla/config/` are merged into generated
  service configuration; local overrides are carried divergence that must be
  reviewed at each upgrade [Book: Ch. 14].
- Image tags: pin explicit tags/versions so a re-run does not silently pull
  different images.
- `destroy` is destructive by design and protected by an explicit confirmation
  flag; it should never appear in routine automation.
- Command syntax and available subcommands differ between releases; check the
  installed version's help.

## OpenStack resource automation (scripts, SDK, CLI loops)

- Target selection: filters on project, host, status and age; refuse to act on
  an empty or unexpectedly large set (a guard such as "abort if more than N
  targets", where N comes from the platform's own baseline).
- State-changing API calls (migrate, evacuate, delete, reset state) need a dry
  run mode that prints the intended actions.
- Rate limiting and concurrency limits per failure domain.
- Evacuation logic must fence the host first [Book: Ch. 10], then mark the
  compute service forced down before evacuating, and must not return the host
  to service before `nova-compute` has cleaned up the evacuated instances.
- Migration automation should account for capacity and the libvirt/QEMU
  direction constraint after partial patching [Book: Ch. 20].
- Cleanup automation for stale records: prefer project tools
  (`nova-manage placement audit` without `--delete` to report first); direct
  DB edits require backup, one record at a time, verification [Book: Ch. 10].
