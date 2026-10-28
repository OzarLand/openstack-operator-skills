# Changelog

## [Unreleased]

### 0.2.0 (in preparation): operational knowledge with validation status

- **New skill `openstack-vm-troubleshooting`**: one instance, volume or port —
  stuck states, scheduling and boot failures, instance networking, volumes,
  compute-host events, logs and request tracing — distilled from the OzarLand
  `openstack-vm-runbooks`.
- **New skill `openstack-kolla-ansible-operations`**: what a `kolla-ansible`
  run regenerates and restarts, failed runs, host and MariaDB operations,
  secrets, configuration and design trade-offs, from the OzarLand
  `kolla-ansible-deployment-patterns`. Kolla-Ansible only.
- **Incident analysis**: `control-plane-recovery.md` (RabbitMQ, Galera,
  HAProxy and keepalived, database connections, Keystone Fernet keys, Nova
  conductor and scheduler). The hard rule on RabbitMQ resets now says that a
  reset failed on a lab with Khepri and how the node and its queue replicas
  were recovered; controlled degradation keeps Placement and Keystone up.
- **Validation status everywhere**: knowledge validation policy, inventory of
  every actionable claim (`validation/inventory.yaml`), inline status tags,
  shared safety rule 12 (state the status and its scope), generated coverage
  report, `tools/validate_knowledge.py` in CI. The knowledge base is not fully
  validated; the README says so and the validator prevents the opposite claim.
- Existing technical notes in maintenance planning, change review and
  automation review now carry status tags and the lab findings that qualify
  them (for example live-migration interruption measured on a lab).
- Contribution workflow: validation evidence issue form, procedure and
  validation-record templates, PR checklist, `docs/source-mapping.md` with the
  assessment and the defects found in the source repositories.

- Tested on claude.ai: the seven zips upload, the right skill loads, the
  references are read (`docs/evaluation-report.md`, section 11).
- `tools/sync_shared.py` leaves the contributor note ("Canonical copy: ...")
  out of the shared references copied into each skill, so the model no longer
  reads it.

## [0.1.0] — 2026-10-25

First version.

Corrections from the first community review (issues #1–#6), included before
release:

- Maintenance planning: SR-IOV `direct` ports and vGPU are live-migratable
  under conditions (#1); check that agreed-restart instances come back after a
  reboot, including `resume_guests_state_on_host_boot` (#2).
- RabbitMQ: check every vhost, default partition handling is `ignore`, and
  what `rabbitmqctl reset` loses (#3).
- Shared safety rules: rule 11, handle secrets as secrets; scenario AR-4 (#4).
- Incident analysis: mark the failed host forced down before evacuating, and
  return it safely (#5).
- `weighted_score.py` input validation and ties, ruff in CI, link check on the
  top-level docs, wording fixes (#6).
- Incident analysis description names the evacuate-a-down-host case, so
  Haiku loads the skill on it (0/3 runs before, 3/3 after).
- Maintenance planning description names concrete triggers (patching
  campaign, hardware repair, evacuate instead of live migration), so Haiku
  loads the skill on them.

Contents:

- Seven skills: incident analysis, change review, maintenance planning,
  operational decisions, control assessment, automation review, runbook
  authoring.
- Shared operating principles and evidence/safety rules.
- Structural validator, shared-reference sync, packaging, Claude Code plugin
  marketplace manifest.
- 30 behavioural scenarios (three with French prompts, two multi-turn) and a
  `claude -p` evaluation harness; results over three runs in
  `docs/evaluation-report.md`.
- `docs/examples.md` (real answers with and without the skills), issue and
  pull request templates.
- Source: *OpenStack, the Day After Tomorrow* v1.2.
