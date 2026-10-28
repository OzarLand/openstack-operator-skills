---
name: openstack-kolla-ansible-operations
description: Operates and troubleshoots OpenStack deployed with Kolla-Ansible - choosing between deploy, reconfigure, upgrade and the other kolla-ansible commands and narrowing them with --limit and --tags, predicting which containers restart, reading the inventory, globals.yml, /etc/kolla/config overrides and passwords.yml, diagnosing failed deploy or reconfigure runs (Ansible version, HAProxy VIP, MariaDB, RabbitMQ clustering, Keystone Fernet, image pulls, compute registration), MariaDB backup, restore and mariadb-recovery, adding, removing or replacing compute and controller nodes, rotating secrets, and the operational consequences of choices such as OVS or OVN, one or three controllers, Ceph, TLS and Docker or Podman. Use when the platform is deployed with Kolla-Ansible and the question involves a kolla-ansible command, its configuration files, a failed run, or a day-2 host or database operation. Not for other deployment tools.
license: Apache-2.0
metadata:
  source: "OzarLand kolla-ansible-deployment-patterns (lab evidence on Kolla-Ansible for OpenStack 2026.1), with the method of OpenStack, the Day After Tomorrow (Soufian Zaouam), v1.2 - Ch. 9, 14, 16"
  version: "0.2.0"
---

# Kolla-Ansible operations

Help an operator act on a Kolla-Ansible deployment without surprises: know
what a `kolla-ansible` run will regenerate and restart before it runs, read a
failed run down to the task and host that failed, and treat host and database
operations as the production changes they are. Kolla-Ansible is one
deployment method among several; nothing here applies to another tool
without checking.

Read [references/evidence-and-safety.md](references/evidence-and-safety.md)
before the first response; its rules are mandatory, in particular rule 11
(secrets: `passwords.yml`, `globals.yml` and overrides often hold them) and
rule 12 (validation status). Principles:
[references/operating-principles.md](references/operating-principles.md).

## When to use

- "Which `kolla-ansible` command do I run after changing X, and what restarts?"
- A `deploy`, `reconfigure`, `upgrade`, `prechecks`, `pull` or
  `bootstrap-servers` run failed, or hangs on a task.
- Adding, removing or replacing a compute or a controller.
- Backing up or restoring MariaDB, or recovering a fully stopped Galera
  cluster with `kolla-ansible mariadb-recovery`.
- Rotating secrets in `passwords.yml`, enabling TLS, a local registry.
- What a deployment choice (OVS or OVN, one or three controllers, network
  nodes, Ceph, Docker or Podman) means for operations.

Not for, hand over instead:

| Situation | Use |
|---|---|
| Is this change ready for production (gates, rollback, stop conditions, decision record)? | `openstack-change-review`, with this skill's facts about the command |
| A playbook or script that wraps `kolla-ansible` | `openstack-automation-review` |
| A live incident (APIs down, RabbitMQ, Galera) not caused by a run in progress | `openstack-incident-analysis` |
| One instance, volume or port misbehaves | `openstack-vm-troubleshooting` |
| Upgrade now, later or in hops? | `openstack-operational-decisions` |

## What to ask for first

1. Kolla-Ansible version (`kolla-ansible --version` or the installed
   package) and OpenStack release; Ansible version on the deploy host.
2. Topology from the inventory: how many controllers, network nodes,
   computes; which groups a host is in.
3. Container engine (Docker or Podman), network backend (ML2/OVS or OVN),
   storage backends, TLS on or off.
4. For a failed run: the exact command line, the failing task name, the host,
   and the error text — with secrets redacted.

If the platform is not deployed with Kolla-Ansible, say that this skill's
specifics do not apply, and continue with the generic skills.

## Workflow

```
Kolla-Ansible operation:
- [ ] 1. Versions, topology, engine, backends; deployment really is Kolla-Ansible
- [ ] 2. Kind of request: understand / change / failed run / host or database operation / design choice
- [ ] 3. For a change: which command, which --limit and --tags, what is regenerated and restarted
- [ ] 4. For a failed run: failing task, host, error; match it; read-only checks
- [ ] 5. Risk of each step; what is lost; undo; who approves
- [ ] 6. Checks after the run: containers, services, cluster state, one real instance
```

### 3. Before a run: predict its blast radius

A `kolla-ansible` run regenerates configuration for the services and hosts
it targets and restarts the containers whose configuration or image changed.
Before proposing a run, state: the subcommand and why it (not another) fits
the change; the inventory; `--limit` (which hosts) and `--tags` (which
services), and what each narrowing leaves out or still touches; which
containers are expected to restart; what users notice while they do; and the
check after the run. Details, with their validation status, in
[references/commands-and-changes.md](references/commands-and-changes.md).
Configuration layout, overrides and secrets in
[references/configuration.md](references/configuration.md).

Rules that hold for every run:

- **Read the plan before the run.** Know which file changed, which service it
  feeds, and which hosts run that service.
- **Narrow, but know what narrowing skips.** `--limit` and `--tags` reduce
  what runs; some plays still reach other groups or need facts from hosts
  outside the limit. The reference says where this was observed.
- **One change at a time.** Do not combine a configuration change, an image
  update and a host operation in one run; the outcome stops being
  attributable [Book: Ch. 9].
- **Re-running is not a fix.** A run that failed once on a real error fails
  again; find the task and host first.

### 4. A failed run

Read the output from the bottom up to the first `FAILED` or `fatal:` task;
note the host, the task name and the message. Match it in
[references/deployment-errors.md](references/deployment-errors.md). The
failure is often outside Kolla-Ansible (Ansible version, name resolution, the
VIP, an OS package upgrade during the run, a registry); fix the cause, then
re-run the narrowest command that covers it.

### 5. Host and database operations

Adding, removing or replacing a host, MariaDB backup and restore, Galera
recovery and secret rotation are production changes with real blast radius:
[references/host-and-database-operations.md](references/host-and-database-operations.md).
`kolla-ansible mariadb-recovery` is made for a completely stopped Galera
cluster: it bootstraps from the node with the highest `seqno` and the others
then replace their data from it. If some nodes are still up, look at them
first, and save every node's data before any recovery; the reference has the
sequence and what was run on a lab.

### 6. After a run

Check containers (none restarting or unhealthy), the OpenStack service and
agent lists, the clusters (Galera size and state, RabbitMQ members), and one
real instance created, reached and deleted. The checks are in
[references/commands-and-changes.md](references/commands-and-changes.md),
*Checking a deployment after a change*.

### Design choices

What OVS or OVN, one or three controllers, separate network nodes, Ceph,
TLS, Docker or Podman change for day-2 operations, troubleshooting and
upgrades: [references/architecture-implications.md](references/architecture-implications.md).
Present choices with their conditions and trade-offs, never as one right
architecture.

## Output format

```markdown
## Context
Kolla-Ansible and OpenStack versions, topology, engine, backends (or what is missing)

## What the operation does
Command, --limit, --tags; files regenerated; containers expected to restart; user-visible effect

## Evidence (for a failed run)
Failing task · host · message · class (Observed / Reported / Hypothesis / Assumption)

## Steps
Numbered; each labelled read-only / state-changing / destructive, with preconditions, what is lost, undo, approver, and its validation status

## Checks after the run

## Gaps
```

End any answer containing state-changing steps with the decision-support line
from [references/evidence-and-safety.md](references/evidence-and-safety.md).

## Limits and safety

- Lab evidence in the references comes from Kolla-Ansible for OpenStack
  2026.1 (mostly 22.x, Docker, Ubuntu 24.04, ML2/OVS, small nested labs).
  Other Kolla-Ansible versions change variables, defaults and subcommands:
  check `kolla-ansible --help` and the documentation of the installed
  version.
- Never ask for, quote or reproduce `passwords.yml` content or any secret.
- `kolla-ansible destroy`, `mariadb-recovery`, removing a host and rotating
  secrets can cause outages or data loss; they require a named human owner.
- The skill does not run commands and never claims a run happened.

## Related skills

- `openstack-change-review`: readiness of the change this run implements.
- `openstack-automation-review`: automation that wraps `kolla-ansible`.
- `openstack-incident-analysis`: control-plane failures outside a run.
- `openstack-vm-troubleshooting`: instance-level symptoms after a change.
