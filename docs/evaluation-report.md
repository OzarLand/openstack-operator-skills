# Evaluation report — v0.1.0

Date: 2026-10-25 (section 9 added after issues #1–#6). Everything below was actually run in this repository's
development session; raw outputs and grades are under `evals/results/`.

## Contents

1. Summary
2. Structural checks
3. Behavioural method
4. Proof of concept (incident analysis) and what changed
5. Full run: all skills, with skill vs baseline
6. Independent fidelity audit and fixes
7. Regression run after fixes
8. Cross-model spot check (Haiku)
9. Regression after issues #1–#6
10. Limitations and what has not been tested

## 1. Summary

| Check | Result |
|---|---|
| Structural validation (7 skills, 28 scenarios) | 0 errors, 0 warnings |
| Plugin marketplace manifest (`claude plugin validate --strict .`) | passed |
| `weighted_score.py` reproduces the book's Ch. 18 example | passed |
| Full behavioural run, model under test claude-sonnet-5-5, 24 scenarios | with skills: mean 0.97, expected skill triggered 24/24, 0 critical errors; baseline without skills: mean 0.68, 3 critical errors |
| Regression after fixes (8 scenarios) | mean 0.98, 8/8 triggered, 0 critical errors |
| Haiku spot check (3 scenarios) | skill triggered 2/3; 0 critical errors either way |
| Regression after issues #1–#6 (5 scenarios, incl. new AR-4) | mean 0.97, 5/5 triggered, 0 critical errors |
| French prompts (3 scenarios, Sonnet) | with skills: mean 0.95, 3/3 triggered; baseline: mean 0.75; 0 critical errors |
| Haiku on IA-2 after description fix | skill triggered 3/3 (was 0/3), mean 1.00 |

These are single runs per cell, graded by a model. They show a consistent
direction, not precise effect sizes.

## 2. Structural checks

`python3 tools/validate_skills.py` (also run in CI) — see `evals/README.md` for
the list of checks. Output at release:

```
7 skills checked: 0 errors, 0 warnings
```

The validator was also checked against injected faults (upper-case name with a
reserved word, name/directory mismatch, citation to a non-existent chapter,
drifted shared copy): all four were reported as errors.

## 3. Behavioural method

- Harness: `tools/run_behavioral.py` with Claude Code CLI 2.1.310 (`claude -p`).
- **Skill mode:** all seven skills installed in a temporary project's
  `.claude/skills/`; Claude Code decides whether to load a skill, so triggering
  is tested. Tools restricted to `Skill Read Glob Grep`; no MCP servers. The
  environment also had unrelated plugin skills installed (e.g. generic
  incident-response and debugging skills), so the OpenStack skills competed
  with them for triggering.
- **Baseline mode:** same prompt, `--disable-slash-commands` (no skills).
- **Model under test:** CLI default, recorded as `claude-sonnet-5-5`; the
  Haiku spot check used `claude-haiku-5-5`.
- **Grader:** separate `claude -p` instance with `claude-opus-5-5`, no skills,
  `evals/grader-prompt.md`, structured JSON output. Criterion pass = 1,
  partial = 0.5, fail = 0; critical errors reported separately.

## 4. Proof of concept (incident analysis) and what changed

`openstack-incident-analysis` was built and tested first (runs `poc-v1`,
`poc-v2`).

| Scenario | Mode | Model | Skill(s) invoked | Criteria score | Critical errors committed |
|---|---|---|---|---:|---|
| IA-1 | baseline | claude-sonnet-5-5 | — | 0.44 | declares a root cause as established fact from the current evidence |
| IA-1 | skill | claude-sonnet-5-5 | openstack-incident-analysis | 1.00 | none |
| IA-2 | baseline | claude-sonnet-5-5 | — | 0.57 | approves evacuating before the host is confirmed powered off or isolated |
| IA-2 | skill | claude-sonnet-5-5 | openstack-incident-analysis | 0.93 | none |
| IA-3 | baseline | claude-sonnet-5-5 | — | 0.58 | none |
| IA-3 | skill | claude-sonnet-5-5 | — | 0.75 | none |
| IA-3 | skill | claude-sonnet-5-5 | openstack-incident-analysis | 1.00 | none |
| IA-4 | baseline | claude-sonnet-5-5 | — | 0.58 | none |
| IA-4 | skill | claude-sonnet-5-5 | — | 1.00 | none |
| IA-4 | skill | claude-sonnet-5-5 | openstack-incident-analysis | 1.00 | none |

| Mode | Runs | Mean criteria score | Runs with ≥1 critical error | Expected skill triggered |
|---|---:|---:|---:|---:|
| skill | 6 | 0.95 | 0 | 4/6 |
| baseline | 4 | 0.54 | 2 | n/a |

Findings and changes:
- In v1, the skill **did not trigger** on IA-3 (automating live migrations for
  CPU steal) and IA-4 (RabbitMQ alert + runbook). Anthropic's skill-creator
  guidance notes that Claude tends to under-trigger skills; descriptions of all
  skills were rewritten to list concrete triggers and to apply "even if the
  question sounds simple". In v2 both triggered and scored 1.00.
- The grader flagged an unflagged assumption about outage duration and a claim
  that state was "probably" degrading: the skill now requires checking trends
  rather than assuming them.
- Evacuation ordering lacked owner input: added a rule to order restoration by
  business criticality with owners' input.
- IA-4 shows the noise level: in v1 the skill did not trigger, so "skill" and
  "baseline" were effectively the same condition, yet they scored 1.00 and 0.58.

## 5. Full run: all skills, with skill vs baseline

Runs `final-<skill>`, executed with the skills as committed in `661f51d`.

| Scenario | Mode | Model | Skill(s) invoked | Criteria score | Critical errors committed |
|---|---|---|---|---:|---|
| AR-1 | baseline | claude-sonnet-5-5 | — | 1.00 | none |
| AR-1 | skill | claude-sonnet-5-5 | openstack-automation-review | 1.00 | none |
| AR-2 | baseline | claude-sonnet-5-5 | — | 0.75 | none |
| AR-2 | skill | claude-sonnet-5-5 | openstack-automation-review | 1.00 | none |
| AR-3 | baseline | claude-sonnet-5-5 | — | 0.50 | none |
| AR-3 | skill | claude-sonnet-5-5 | openstack-automation-review | 0.80 | none |
| CA-1 | baseline | claude-sonnet-5-5 | — | 0.50 | none |
| CA-1 | skill | claude-sonnet-5-5 | openstack-control-assessment | 1.00 | none |
| CA-2 | baseline | claude-sonnet-5-5 | — | 0.90 | none |
| CA-2 | skill | claude-sonnet-5-5 | openstack-control-assessment | 0.90 | none |
| CA-3 | baseline | claude-sonnet-5-5 | — | 0.67 | gives a single numeric score as the answer |
| CA-3 | skill | claude-sonnet-5-5 | openstack-control-assessment | 0.92 | none |
| CR-1 | baseline | claude-sonnet-5-5 | — | 0.79 | none |
| CR-1 | skill | claude-sonnet-5-5 | openstack-change-review | 1.00 | none |
| CR-2 | baseline | claude-sonnet-5-5 | — | 0.67 | none |
| CR-2 | skill | claude-sonnet-5-5 | openstack-change-review | 1.00 | none |
| CR-3 | baseline | claude-sonnet-5-5 | — | 0.93 | none |
| CR-3 | skill | claude-sonnet-5-5 | openstack-change-review | 1.00 | none |
| CR-4 | baseline | claude-sonnet-5-5 | — | 0.92 | none |
| CR-4 | skill | claude-sonnet-5-5 | openstack-change-review | 1.00 | none |
| IA-1 | baseline | claude-sonnet-5-5 | — | 0.44 | none |
| IA-1 | skill | claude-sonnet-5-5 | openstack-incident-analysis | 1.00 | none |
| IA-2 | baseline | claude-sonnet-5-5 | — | 0.71 | none |
| IA-2 | skill | claude-sonnet-5-5 | openstack-incident-analysis | 0.93 | none |
| IA-3 | baseline | claude-sonnet-5-5 | — | 0.50 | none |
| IA-3 | skill | claude-sonnet-5-5 | openstack-automation-review, openstack-incident-analysis | 0.92 | none |
| IA-4 | baseline | claude-sonnet-5-5 | — | 0.42 | none |
| IA-4 | skill | claude-sonnet-5-5 | openstack-incident-analysis | 1.00 | none |
| MP-1 | baseline | claude-sonnet-5-5 | — | 0.62 | none |
| MP-1 | skill | claude-sonnet-5-5 | openstack-maintenance-planning | 1.00 | none |
| MP-2 | baseline | claude-sonnet-5-5 | — | 0.88 | none |
| MP-2 | skill | claude-sonnet-5-5 | openstack-maintenance-planning | 1.00 | none |
| MP-3 | baseline | claude-sonnet-5-5 | — | 0.92 | none |
| MP-3 | skill | claude-sonnet-5-5 | openstack-maintenance-planning | 1.00 | none |
| OD-1 | baseline | claude-sonnet-5-5 | — | 0.71 | none |
| OD-1 | skill | claude-sonnet-5-5 | openstack-operational-decisions | 0.93 | none |
| OD-2 | baseline | claude-sonnet-5-5 | — | 0.40 | approves the backport without owner, test or exit condition |
| OD-2 | skill | claude-sonnet-5-5 | openstack-operational-decisions | 0.90 | none |
| OD-3 | baseline | claude-sonnet-5-5 | — | 0.60 | none |
| OD-3 | skill | claude-sonnet-5-5 | openstack-operational-decisions | 1.00 | none |
| OD-4 | baseline | claude-sonnet-5-5 | — | 0.70 | none |
| OD-4 | skill | claude-sonnet-5-5 | openstack-operational-decisions | 0.90 | none |
| RA-1 | baseline | claude-sonnet-5-5 | — | 0.29 | turns the incident sequence into an unconditional procedure (always purge and restart) |
| RA-1 | skill | claude-sonnet-5-5 | openstack-runbook-authoring | 1.00 | none |
| RA-2 | baseline | claude-sonnet-5-5 | — | 0.70 | none |
| RA-2 | skill | claude-sonnet-5-5 | openstack-runbook-authoring | 1.00 | none |
| RA-3 | baseline | claude-sonnet-5-5 | — | 0.83 | none |
| RA-3 | skill | claude-sonnet-5-5 | openstack-runbook-authoring | 1.00 | none |

| Mode | Runs | Mean criteria score | Runs with ≥1 critical error | Expected skill triggered |
|---|---:|---:|---:|---:|
| skill | 24 | 0.97 | 0 | 24/24 |
| baseline | 24 | 0.68 | 3 | n/a |

Observations:
- The baseline's critical errors were exactly the failure modes the book warns
  about: asserting a single numeric maturity score (CA-3), approving a local
  backport without owner, test or exit condition (OD-2), and turning one
  incident's recovery sequence into an unconditional runbook — "always purge
  and restart" (RA-1). In the POC, the baseline also asserted a root cause as
  fact (IA-1) and approved evacuation without fencing (IA-2).
- On some scenarios the base model was already strong (AR-1 1.00, CA-2 0.90,
  CR-3 0.93, MP-3 0.92); the skills add most where the book's method differs
  from generic good practice: controlled degradation and verification before
  reopening (IA-1), decision points in runbooks (RA-1), differentiated patching
  by criticality and failure domain (MP-1), restraint when control is lost
  (CA-1), lifecycle discipline for backports (OD-2).
- Remaining partial scores (skill mode) were about not naming a specific
  approver, not asking whether the vendor already ships a fix, treating
  deletion of tenant resources as "mostly execution", and not stating the
  workaround risk test explicitly. Each led to a small edit (section 7).

## 6. Independent fidelity audit and fixes

An independent agent read the whole book and all skill files, looking for
misattributions, untagged additions, technical errors, context turned into
absolute rules, and missing lessons. It found **no technical errors and no
state-changing command labelled read-only**. Fixed as a result:

| Finding | Fix |
|---|---|
| "One corrective action at a time" contradicted the book's own Ch. 19 sequence | Rule rewritten: keep outcomes attributable; multi-step recoveries are one planned sequence with verification defined up front |
| Change review let an owner override a failed recovery gate; the book does not | Verdict stays "not ready"; improve the condition first |
| Single evidence-confidence ordering attributed to Ch. 5 | Marked as an addition; the book gives pairwise comparisons |
| "Verify is the step most often skipped" attributed to Ch. 4 | Replaced with the book's statement: the loop loses its last two steps |
| Control-debt definition dropped "undocumented" and made categories exclusive | Restored the book's wording |
| Pinned/NUMA instances listed as needing restart | Scoped to releases before Train |
| Landing-zone patch strategy, point of no return, several verification lists presented under book citations | Tagged `[Addition]`; landing zone scoped to libvirt/QEMU-changing patches |
| Neutron contract phase called a control-plane outage | Corrected to a Neutron API outage |
| RabbitMQ runbook branch could route a resolved `pause_minority` partition to "reset the node" | Added partition-mode and log checks, and an "absent node cannot be queried" branch to escalation |
| `*-status upgrade check` usage ambiguous | States they must run with the target release's code |
| "Delay can be right once" | Restored the book's affordability condition |
| Missing: cultural precondition for stopping (Ch. 19), target operating state and horizons (Ch. 18), overload feedback loop (Ch. 12), visibility designed for failure (Ch. 8), handover rehearsal (Ch. 1) | Added to incident analysis, operational decisions and control assessment |

## 7. Regression run after fixes

Runs `regress-<skill>`, skill mode, on the scenarios most affected by the edits.

| Scenario | Mode | Model | Skill(s) invoked | Criteria score | Critical errors committed |
|---|---|---|---|---:|---|
| AR-3 | skill | claude-sonnet-5-5 | openstack-automation-review | 1.00 | none |
| CR-1 | skill | claude-sonnet-5-5 | openstack-change-review | 1.00 | none |
| CR-3 | skill | claude-sonnet-5-5 | openstack-change-review | 0.93 | none |
| IA-1 | skill | claude-sonnet-5-5 | openstack-incident-analysis | 1.00 | none |
| IA-2 | skill | claude-sonnet-5-5 | openstack-incident-analysis | 0.93 | none |
| MP-1 | skill | claude-sonnet-5-5 | openstack-maintenance-planning | 1.00 | none |
| OD-2 | skill | claude-sonnet-5-5 | openstack-operational-decisions | 1.00 | none |
| RA-1 | skill | claude-sonnet-5-5 | openstack-runbook-authoring | 1.00 | none |

| Mode | Runs | Mean criteria score | Runs with ≥1 critical error | Expected skill triggered |
|---|---:|---:|---:|---:|
| skill | 8 | 0.98 | 0 | 8/8 |

## 8. Cross-model spot check (Haiku)

Runs `haiku-*`, model under test `claude-haiku-5-5`.

| Scenario | Mode | Model | Skill(s) invoked | Criteria score | Critical errors committed |
|---|---|---|---|---:|---|
| AR-1 | baseline | claude-haiku-5-5 | — | 1.00 | none |
| AR-1 | skill | claude-haiku-5-5 | openstack-automation-review | 1.00 | none |
| IA-2 | baseline | claude-haiku-5-5 | — | 0.79 | none |
| IA-2 | skill | claude-haiku-5-5 | — | 0.71 | none |
| MP-1 | baseline | claude-haiku-5-5 | — | 0.56 | none |
| MP-1 | skill | claude-haiku-5-5 | openstack-maintenance-planning | 1.00 | none |

| Mode | Runs | Mean criteria score | Runs with ≥1 critical error | Expected skill triggered |
|---|---:|---:|---:|---:|
| skill | 3 | 0.90 | 0 | 2/3 |
| baseline | 3 | 0.78 | 0 | n/a |

With Haiku the incident skill **did not trigger** on IA-2 (evacuation); the
answer avoided the critical error but scored below the baseline run. Triggering
on smaller models is a known weakness to work on (section 10).

## 9. Regression after issues #1–#6

Issues #1–#6 (community review) changed maintenance planning (SR-IOV and vGPU
live-migration classes, restart check after reboot), the RabbitMQ guidance
(vhosts, default partition handling, reset caveats), the shared safety rules
(rule 11, secrets), incident analysis (forced-down step, safe return of an
evacuated host) and `weighted_score.py` (input validation, ties). Scenario
AR-4 (a playbook containing a credential) was added for rule 11. Runs
`issue4-ar4`, `issue5-ia2`, `issues-*`:

| Scenario | Mode | Model | Skill(s) invoked | Criteria score | Critical errors committed |
|---|---|---|---|---:|---|
| AR-4 | baseline | claude-sonnet-5-5 | — | 1.00 | none |
| AR-4 | skill | claude-sonnet-5-5 | openstack-automation-review | 1.00 | none |
| IA-2 | skill | claude-sonnet-5-5 | openstack-incident-analysis | 0.86 | none |
| IA-4 | skill | claude-sonnet-5-5 | openstack-incident-analysis | 1.00 | none |
| MP-1 | skill | claude-sonnet-5-5 | openstack-maintenance-planning | 1.00 | none |
| RA-1 | skill | claude-sonnet-5-5 | openstack-runbook-authoring | 1.00 | none |

| Mode | Runs | Mean criteria score | Runs with ≥1 critical error | Expected skill triggered |
|---|---:|---:|---:|---:|
| skill | 5 | 0.97 | 0 | 5/5 |
| baseline | 1 | 1.00 | 0 | n/a |

The AR-4 baseline also redacted the credential, so the scenario guards against
regression rather than showing a difference.

**Plugin install from GitHub.** In an empty Claude Code configuration,
`claude plugin marketplace add soufian-zaouam/openstack-operator-skills` then
`claude plugin install openstack-operations@openstack-operator-skills`
installed all seven skills. An evacuation prompt (similar to IA-2) triggered
`openstack-operations:openstack-incident-analysis`. In `claude -p` without
permissions, reading the skill's `references/` from the plugin cache was
denied and the answer said so; with `--allowedTools Read` the references were
read. Not graded; a check that installation works, not a scored run.

**French prompts.** IA-2-FR, MP-2-FR and CR-2-FR are translations of IA-2,
MP-2 and CR-2 with the same rubrics (runs `fr-*`). All three skills triggered
and answered in French.

| Scenario | Mode | Model | Skill(s) invoked | Criteria score | Critical errors committed |
|---|---|---|---|---:|---|
| CR-2-FR | baseline | claude-sonnet-5-5 | — | 0.67 | none |
| CR-2-FR | skill | claude-sonnet-5-5 | openstack-change-review | 0.92 | none |
| IA-2-FR | baseline | claude-sonnet-5-5 | — | 0.71 | none |
| IA-2-FR | skill | claude-sonnet-5-5 | openstack-incident-analysis | 0.93 | none |
| MP-2-FR | baseline | claude-sonnet-5-5 | — | 0.88 | none |
| MP-2-FR | skill | claude-sonnet-5-5 | openstack-maintenance-planning | 1.00 | none |

**Haiku triggering on IA-2.** With the original description Haiku did not
load the incident skill on IA-2 in 3 of 3 runs (`haiku-ia2-before-*`, not
graded). The description now names the case (compute host down, `openstack
server evacuate`) and the "is it safe to run this command" question. After
the change (`haiku-ia2-after-*`, `haiku-ia2fr-after`, `haiku-mp2-after`,
`desc-*`):

| Scenario | Mode | Model | Skill(s) invoked | Criteria score | Critical errors committed |
|---|---|---|---|---:|---|
| IA-2 (3 runs) | skill | claude-haiku-5-5 | openstack-incident-analysis | 1.00 each | none |
| IA-2-FR | skill | claude-haiku-5-5 | openstack-incident-analysis | 1.00 | none |
| IA-4 | skill | claude-sonnet-5-5 | openstack-incident-analysis | 1.00 | none |
| MP-2 | skill | claude-sonnet-5-5 | openstack-maintenance-planning | 1.00 | none |
| MP-2 | skill | claude-haiku-5-5 | — | 1.00 | none |

The broader description did not take MP-2 (evacuate as a drain shortcut)
away from maintenance planning. Haiku still loaded no skill on MP-2, although
its answer met every criterion: maintenance-planning triggering on Haiku
remains open.

## 10. Limitations and what has not been tested

- **One run per cell.** Differences of a few points are within noise (see IA-4
  in the POC).
- **Model grading.** The grader is a model applying a rubric; it was
  discriminating in the samples read by hand, but it is not ground truth.
- **Same author.** Scenarios, skills and rubrics were written in the same
  session; scenarios contributed by operators would be a stronger test.
- **Surfaces.** Only Claude Code was exercised. claude.ai upload, the Skills
  API and the Agent SDK were not tested. The plugin install from GitHub was
  tested once end to end (section 9); in `claude -p` the plugin's reference
  files are only read when `Read` is allowed (see `docs/installation.md`).
- **Models.** Full run on Sonnet only; Haiku on a handful of scenarios; Opus
  only as grader. Haiku still under-triggers maintenance planning (MP-2).
- **Multi-turn use** (pasting diagnostic output back, continuing an incident)
  was not tested; all scenarios are single prompts.
- **No real infrastructure.** Skills were never connected to an OpenStack
  environment; tool-enabled sessions were deliberately excluded.
