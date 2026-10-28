# Upgrade and policy readiness

Summarized from [Book: Ch. 14] and [Book: Ch. 17] technical notes. Release
policy and mechanics change; always check releases.openstack.org, the project
upgrade guides and, for a distribution, the vendor's supported path before
relying on any of this.

Validation: every technical item in this file is
[DOCUMENTED-UNVERIFIED: CR-UPG-01] (upstream release policy and upgrade
guides, read but not executed for this repository), except where another tag
says otherwise. One Kolla-Ansible all-in-one upgrade from 2025.1 to 2026.1
was run on a lab; what happened is in `openstack-kolla-ansible-operations`
(architecture-implications.md, *From 2025.1 to 2026.1*). A single all-in-one
run does not validate a multinode rolling upgrade.

## Contents

- Organizational readiness review
- Lifecycle facts to confirm
- Upstream readiness tools
- Nova rolling upgrade sequence (as documented upstream)
- Neutron expand/contract
- Policy (RBAC) changes
- Things outside OpenStack that must support the jump
- After the upgrade

## Organizational readiness review

[Book: Ch. 14] A weak result does not cancel the upgrade; it shows where
preparation is required.

| Item | Question |
|---|---|
| Local modifications | Which carried patches/backports exist, and which does the target release make unnecessary or break? |
| Recovery coverage | Has control-plane recovery (database, bus) been demonstrated recently, by someone still on the team? |
| Test coverage | Has the upgrade been executed in a representative environment, including the deployment tooling? |
| Documentation | Is the procedure written with decision points, and usable by someone other than its author? |
| Capacity | Is there migration headroom and window time for compute batches? |
| Ownership gaps | Who owns each affected service and its recovery? |
| Consumer readiness | Will APIs, policies or behaviour visible to consumers change? |
| Monitoring readiness | Will monitoring work on the new release and show the new state? |

Note from the book's worked example [Book: Ch. 18]: when recovery has not been
demonstrated by anyone still on the team, the first action may be a recovery
exercise rather than the upgrade.

## Lifecycle facts to confirm

[Book: Ch. 14]
- Maintenance status of the current and target series (Maintained /
  Unmaintained / End of Life); upstream maintains branches, it does not
  "support" releases; commercial support comes from vendors.
- SLURP: upgrades are supported between consecutive SLURP releases as well as
  adjacent ones. More than one SLURP behind means hopping through each
  intermediate SLURP release.
- When a series becomes Unmaintained its `stable/<series>` branch is replaced
  by `unmaintained/<series>` — tooling pinned to the old branch name breaks; at
  End of Life only a tag remains.

## Upstream readiness tools

[Book: Ch. 14] Read-only pre-upgrade checks returning a status code, for
example `nova-status upgrade check`, `neutron-status upgrade check`,
`cinder-status upgrade check`, `placement-status upgrade check`. Other projects
ship one too (e.g. `keystone-status`, `glance-status`, `octavia-status`): check
each deployed project `[Addition]`. They perform
release-specific checks before services are restarted with new code: run them
with the **target** release's code; run with the installed code they only
check the current release.

## Nova rolling upgrade sequence (as documented upstream)

[Book: Ch. 14]
1. Schema migrations are additive, so the schema can be synchronized before
   the window with old services running.
2. Upgrade Placement first.
3. Restart services with `[upgrade_levels]compute=auto` (RPC pinned to the
   oldest compute found), starting with nova-conductor, ending with nova-api.
4. Upgrade compute nodes in batches.
5. When all computes run new code, SIGHUP the services so the automatic pin
   advances (a static pin must be removed and services restarted).
6. Complete `nova-manage db online_data_migrations` — also a hard prerequisite
   of the **next** upgrade; skipped migrations make the next schema sync refuse
   to run.

Since 2023.1, Nova tolerates computes up to two releases older than control
services (N-2); control services refuse to start if they detect a compute
service older than that.

## Neutron expand/contract

[Book: Ch. 14] Schema changes are split into expand and contract phases; the
contract phase, although usually empty in recent releases, requires every
neutron-server to be stopped — a Neutron API outage (other APIs and the data
plane are not stopped by it). Treat it as a potential point of no return
`[Addition]`.

## Policy (RBAC) changes

[Book: Ch. 17] The secure-default RBAC goal introduced personas (project
reader, member, manager; service role; narrowed admin) and the
`enforce_new_defaults` and `enforce_scope` options, staged across the 2023 and
2024 series, with old defaults being removed. An upgrade can change which
users, automation accounts and integrations keep the permissions they rely on.
Readiness requires testing policy against real users and automation. A locally
overridden policy file is a carried divergence with the same obligations as a
backport.

## Things outside OpenStack that must support the jump

[Book: Ch. 14] SLURP is a promise about OpenStack services only. The operating
system and Python version, the deployment tool, RabbitMQ, MariaDB, the
networking backend and the storage backend must each support the same jump.

## After the upgrade

[Book: Ch. 9, Ch. 14] The upgrade is not finished when software is deployed:
observe, verify, transfer into normal operations, and re-earn stability
assumptions. Review which local modifications can now be removed.
