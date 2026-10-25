# Changelog

## [Unreleased]

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
