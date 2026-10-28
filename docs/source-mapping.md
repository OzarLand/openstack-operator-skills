# Source mapping: OzarLand repositories to skills

This document records the assessment made for version 0.2.0: what the
existing skills, the OzarLand
[openstack-vm-runbooks](https://github.com/OzarLand/openstack-vm-runbooks)
(commit `babdd8c07971`) and
[kolla-ansible-deployment-patterns](https://github.com/OzarLand/kolla-ansible-deployment-patterns)
(commit `dee2c60b9db4`) contain, why the architecture changed, and where each
piece of operational knowledge went. Validation statuses per item are in
[validation-coverage.md](validation-coverage.md); the rules in
[knowledge-validation-policy.md](knowledge-validation-policy.md).

## Contents

1. Assessment of the existing skills (0.1.0)
2. Assessment of the VM runbooks
3. Assessment of the Kolla-Ansible patterns
4. Architecture decisions
5. Mapping: source to skill
6. What was not reused, and why
7. Defects found in the sources

## 1. Assessment of the existing skills (0.1.0)

Seven skills built from the book's method; structurally validated in CI and
behaviourally evaluated (90 answers over three runs, see
[evaluation-report.md](evaluation-report.md)).

| Skill | Strengths | Weaknesses found |
|---|---|---|
| incident-analysis | Evidence ledger, competing hypotheses, protect decision, hard rules (fence before evacuate, partition is not node loss) | Command-level recovery for RabbitMQ, Galera, HAProxy, Keystone only as book technical notes; the book's RabbitMQ purge-and-restart sequence untested on current RabbitMQ (a source page reports it failed as written with Khepri on a lab, see section 7); no route for single-instance problems |
| change-review | Gates, recovery, stop conditions, decision record | Technical notes (rotation, upgrade) without execution evidence |
| maintenance-planning | Criticality times migratability, capacity per failure domain | No measured migration behaviour (interruption at switch-over) |
| operational-decisions | Gates before scoring, sensitivity, decision rights | Method only; nothing to execute |
| control-assessment | Consequence chain, control spectrum, restoration | Method only |
| automation-review | Delegated judgement, safeguards | Kolla-Ansible notes short and untested |
| runbook-authoring | Decision points, validation by a non-author | Method only |

Across all seven: the technical claims had provenance (`[Book]` /
`[Addition]`) but **no execution status**; an operator could not tell a
tested command from a paraphrased document. The method content (gates,
frameworks, output formats) is sound and was kept unchanged.

Gaps against the operational use cases of the mission: no skill for "this
instance / volume / port is stuck" (the most frequent operator question),
and no deployment-tool knowledge (the book names none).

## 2. Assessment of the VM runbooks

72 pages (lifecycle 10, scheduling 7, migration 3, networking 9, volumes 5,
diagnostics 5, recovery 11, logs 22), each with YAML frontmatter (status,
environment, `confirmed_by`), a fixed structure (symptom, quick checks,
diagnosis, causes, resolution with ⚠️/🛑 markers, verification, validity
and limits) and, on most pages, a *Lab observations* section with sanitized
outputs and timings.

- **Evidence:** 44 pages `lab-verified`, 28 `draft`. Lab runs were executed
  by an automated agent (`agent:lab-reviewer`) on Kolla-Ansible 2026.1 labs
  and recorded with environment, date and the steps *not* run. Three
  production observations by the maintainer are recorded as "steps not re-run".
  No page is `validated` (confirmed by a second operator).
- **Quality:** strong. Precise discriminating checks, exact messages, honest
  limits. Several pages contradict themselves between `confirmed_by` and the
  body (section 7); where they do, this repository used the narrower claim.
- **Assumptions:** Kolla-Ansible container names and paths, ML2/OVS, local
  instance disks, small labs. OVN and Ceph appear as documented variants,
  rarely lab-run.

## 3. Assessment of the Kolla-Ansible patterns

39 pages (deployment errors 9, operations 7, configuration 6, services 5,
comparisons 4, networking 2, storage 2, topologies 2, version notes 2).

- **Evidence:** 9 pages `lab-verified`; several `draft` pages carry partial
  lab confirmations (often read-only steps only). Five operations pages
  (adding, removing, replacing hosts, bootstrap-servers, RabbitMQ clustering)
  have no lab evidence at all — they are among the riskiest procedures.
- **Content:** deployment errors with exact messages and causes; day-2
  operations; comparisons that state consequences rather than prescribe an
  architecture.
- **Defects:** one page's frontmatter is invalid YAML; cross-page
  disagreements (section 7).

## 4. Architecture decisions

| Decision | Why | Alternative rejected |
|---|---|---|
| Keep the seven method skills unchanged in scope | They are evaluated and sound; the gaps were knowledge and evidence, not method | Restructuring for appearance |
| **New** `openstack-vm-troubleshooting` | Single-resource problems are the most common operator request and need a symptom router, not an incident workflow; 46 VM runbook pages map to it | One skill per runbook (shallow, overlapping); stuffing them into incident-analysis (its references would triple and its triggers blur) |
| **New** `openstack-kolla-ansible-operations` | Tool-specific knowledge (what a run restarts, failed runs, host and DB operations) is distinct from change readiness and is only valid for Kolla-Ansible | Folding into automation-review (that skill reviews code, not operations) or change-review (method, not mechanics) |
| Control-plane recovery into incident-analysis (`control-plane-recovery.md`) | Those pages are incident procedures for shared components; incident-analysis already owns the decision to act | A separate control-plane skill (would overlap incident-analysis triggers) |
| Lab corrections into failure-patterns, hard rules, change notes, maintenance mechanics | Existing claims gained or lost evidence; operators must see it where they read the claim | A separate errata page nobody reads |
| Validation status as inline tags + `validation/inventory.yaml` + `tools/validate_knowledge.py` | Skills are uploaded standalone, so the status must be in the text; the inventory holds the evidence for reviewers; the validator keeps both consistent | Metadata only in frontmatter (skill-level, too coarse); a separate database (unreachable from skills) |
| Router tables and one reference file per domain | Progressive disclosure: SKILL.md stays under 250 lines; a reference is read only when its symptom matches | Long SKILL.md files |

Hand-offs: vm-troubleshooting → incident-analysis when the scope is wide or
a host may be evacuated; → kolla-ansible-operations for a configuration fix;
kolla-ansible-operations → change-review for readiness; automation-review and
change-review cite lab evidence from the two new skills by ID.

## 5. Mapping: source to skill

| Source (OzarLand) | Pages | Skill and reference | IDs |
|---|---|---|---|
| vm-runbooks `lifecycle/` (except nova_libvirt restart) | 9 | vm-troubleshooting, instance-lifecycle.md | VM-LC |
| vm-runbooks `scheduling/` | 7 | vm-troubleshooting, scheduling-and-boot.md | VM-SCH |
| vm-runbooks `networking/` | 9 | vm-troubleshooting, instance-networking.md | VM-NET |
| vm-runbooks `volumes/` | 5 | vm-troubleshooting, volumes.md | VM-VOL |
| vm-runbooks nova-compute down (2), after reboot, nova_libvirt restart, live migration, CPU steal, clock skew | 7 | vm-troubleshooting, compute-host-events.md | VM-HOST |
| vm-runbooks `logs/`, tracing a VM creation | 23 | vm-troubleshooting, logs-and-tracing.md | VM-LOG |
| vm-runbooks RabbitMQ, Galera, HAProxy/keepalived, DB connections, Keystone 401, conductor/scheduler, reopening provisioning | 7 | incident-analysis, control-plane-recovery.md | IA-CP |
| vm-runbooks fence before evacuate, no valid host, stale records, CPU steal, control plane down, VM creation traversal | 6 | incident-analysis, failure-patterns.md and dependency-map.md (evidence for existing claims) | IA-FP, IA-DEP |
| vm-runbooks moving instances off a host, after a reboot | 2 | maintenance-planning, host-maintenance-mechanics.md | MP-MECH |
| kolla `operations/` deploy-reconfigure, checking, bootstrap-servers | 3 | kolla-ansible-operations, commands-and-changes.md | KA-CMD |
| kolla `deployment-errors/` | 9 | kolla-ansible-operations, deployment-errors.md | KA-ERR |
| kolla host operations, MariaDB backup and recovery, secret rotation | 6 | kolla-ansible-operations, host-and-database-operations.md | KA-OPS |
| kolla `configuration/` (layout, TLS, registry, CPU pinning, SR-IOV) | 5 | kolla-ansible-operations, configuration.md | KA-CFG |
| kolla comparisons, topologies, networking, storage, services, version notes | 19 | kolla-ansible-operations, architecture-implications.md | KA-ARCH |
| Lab evidence reused by existing skills | — | change-review (Fernet, OVS agent, restores), automation-review (what a run restarts, stop flag, evacuation steps) | cross-references by ID |

The book-derived items of the 0.1.0 skills (CR, AR, MP, IA-DEP, IA-FP) were
inventoried too, so the coverage figures cover the old knowledge as well as
the new.

## 6. What was not reused, and why

- **Full runbook text.** Skills carry the discriminating checks, decisions,
  risk labels and verification; the source pages stay the place for complete
  procedures and are linked from every inventory entry.
- **Octavia and Heat log pages:** outside the scope of single-VM
  troubleshooting; mentioned only as pointers.
- **Deployment walk-throughs** (all-in-one lab build, topology build notes):
  used only to explain the limits of the lab evidence, not as deployment
  instructions; this is an operations repository.
- **Ambiguous source text** (for example a `nova-manage` flag combination
  whose warning is unclear): left out, with the operator pointed at
  `--help` for the installed version.

## 7. Defects found in the sources

Reported here and to the source repositories' owner so they can be fixed
upstream (`tools/check_sources.py` reports missing pages and undisclosed
draft status mechanically); each affects the narrower claim this repository uses. Rows marked
*Fixed upstream* stay for the record. "confirmed_by vs body" means the page's
frontmatter lab record and its own text disagree on what was run. Last
checked against both repositories' `main` on 2026-10-28.

| Page | Problem |
|---|---|
| vm `recovery/reopening-provisioning-after-control-plane-incident.md` | Failed as written with RabbitMQ 4.2 Khepri on a lab and was corrected (PR #137), but stays `draft` with empty `confirmed_by` |
| vm `recovery/compute-host-failure-fence-before-evacuate.md` | confirmed_by vs body: topology, boot-from-volume, microversion 2.103 vs 2.29, date |
| vm `recovery/nova-compute-down-instances-still-running.md` | confirmed_by says the local delete was observed; body says not tested |
| vm `recovery/nova-compute-down-host-alive-ssh-refused.md` | confirmed_by says AllowUsers, missing account, ping and nc were run; body says not |
| vm `lifecycle/compute-disk-full-instance-paused.md` | confirmed_by says full procedure and return to Running; body says not observed |
| vm `lifecycle/restarting-nova-libvirt-does-not-stop-instances.md` | confirmed_by vs Validity on which checks ran; topology |
| vm `networking/restarting-the-ovs-agent-does-not-cut-instances.md` | confirmed_by says the stuck-agent restart ran; Validity says not |
| vm `networking/router-stuck-on-dead-l3-agent.md` | confirmed_by says the router move ran; body says not |
| vm `networking/tunnel-mtu-mismatch-large-packets-dropped.md` | The DF ping offered as the underlay test did not detect the lowered MTU on the lab |
| vm `scheduling/instance-fails-to-boot-from-volume.md` | cinder-volume down listed as a cause of `error`; the lab showed `creating` |
| vm `diagnostics/expired-certificates-...` vs `recovery/keystone-401-...` | Disagree on whether Keystone must be restarted after fixing keys |
| vm `recovery/database-too-many-connections-...`, `volumes/extend-in-use-...`, several `logs/` pages | Lab runs in the body, empty `confirmed_by` |
| vm `logs/README.md` | *Fixed upstream* (openstack-vm-runbooks #144): listed lab-verified pages as `draft`; the index now follows each page's front matter |
| kolla `deployment-errors/pull-fails-http-response-to-https-client-insecure-registry.md` | Frontmatter is invalid YAML (unquoted colon in `title`); still fails to parse with PyYAML on `main`; reported to the owner |
| kolla `operations/replacing-a-failed-controller.md` vs `deployment-errors/rabbitmq-nodes-do-not-form-a-cluster.md` | `forget_cluster_node` when the replacement reuses the old name: one does it (step 4, for either name), the other forbids it; still open on `main`, reported to the owner |
| kolla `operations/adding-a-compute-node.md` vs `deployment-errors/nova-compute-services-failed-to-register.md` | Disagree on whether Placement errors cause the registration failure |
| kolla `operations/mariadb-backup-and-restore-with-mariabackup.md` vs the mariadb-recovery page | Joiner wait about 11 min vs about 1 min |
| kolla `services/external-ceph-for-glance-cinder-and-nova.md` | confirmed_by records a read-only check; body says nothing was run |
| kolla `version-notes/2025.1-to-2026.1.md` | Lab run mentioned, empty `confirmed_by` |
