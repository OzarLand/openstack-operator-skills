# Evaluation report — v0.1.0

Date: 2026-10-25 (section 9 added after issues #1–#6, section 10 after the
repeated runs). Everything below was actually run in this repository's
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
10. Robustness: three runs of all 30 scenarios
11. claude.ai manual check
12. Limitations and what has not been tested
13. Version 0.2.0: new skills, regression and validation checks

## 1. Summary

| Check | Result |
|---|---|
| Structural validation (7 skills, 30 scenarios) | 0 errors, 0 warnings |
| Plugin marketplace manifest (`claude plugin validate --strict .`) | passed |
| `weighted_score.py` reproduces the book's Ch. 18 example | passed |
| Full behavioural run, model under test claude-sonnet-5-5, 24 scenarios | with skills: mean 0.97, expected skill triggered 24/24, 0 critical errors; baseline without skills: mean 0.68, 3 critical errors |
| Regression after fixes (8 scenarios) | mean 0.98, 8/8 triggered, 0 critical errors |
| Haiku spot check (3 scenarios) | skill triggered 2/3; 0 critical errors either way |
| Regression after issues #1–#6 (5 scenarios, incl. new AR-4) | mean 0.97, 5/5 triggered, 0 critical errors |
| French prompts (3 scenarios, Sonnet) | with skills: mean 0.95, 3/3 triggered; baseline: mean 0.75; 0 critical errors |
| Haiku on IA-2 after description fix | skill triggered 3/3 (was 0/3), mean 1.00 |
| All 30 scenarios × 3 runs, Sonnet (incl. 2 multi-turn) | with skills: mean 0.98, 0 critical errors in 90 answers, expected skill 87/90; baseline: mean 0.73, 16 answers with a critical error |
| Haiku on maintenance planning after description fix | triggered 4/5 (was 0/4) |
| claude.ai upload and 4 manual tests (Opus 5.5) | 7/7 uploads, right skill loaded 3/3, references read, all criteria met, 0 critical errors |

Most rows are single runs per cell; section 10 repeats the whole suite three
times and the spread is small. All grading is by a model.

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

## 10. Robustness: three runs of all 30 scenarios

All 30 scenarios (the 24 of section 5, AR-4, the three French prompts and two
new multi-turn scenarios) were run three times in both modes with
`claude-sonnet-5-5`, graded by `claude-opus-5-5` (runs `rep1-*`, `rep2-*`,
`rep3-*`; 180 graded answers).

| Mode | Answers | Mean criteria score | Mean per run | Answers with ≥1 critical error | Expected skill loaded |
|---|---:|---:|---|---:|---:|
| skill | 90 | 0.98 | 0.98, 0.97, 0.98 | 0 | 87/90 |
| baseline | 90 | 0.73 | 0.72, 0.73, 0.74 | 16 | n/a |

| Scenario | Baseline mean (range) | Skill mean (range) | Baseline runs with a critical error | Skill runs with a critical error | Expected skill loaded |
|---|---|---|---:|---:|---:|
| AR-1 | 0.97 (0.92–1.00) | 1.00 (1.00–1.00) | 0/3 | 0/3 | 3/3 |
| AR-2 | 0.75 (0.67–0.83) | 1.00 (1.00–1.00) | 0/3 | 0/3 | 3/3 |
| AR-3 | 0.63 (0.60–0.70) | 0.97 (0.90–1.00) | 1/3 | 0/3 | 3/3 |
| AR-4 | 1.00 (1.00–1.00) | 1.00 (1.00–1.00) | 0/3 | 0/3 | 3/3 |
| CA-1 | 0.48 (0.43–0.50) | 0.88 (0.86–0.93) | 0/3 | 0/3 | 3/3 |
| CA-2 | 0.93 (0.90–1.00) | 1.00 (1.00–1.00) | 0/3 | 0/3 | 3/3 |
| CA-3 | 0.69 (0.67–0.75) | 0.92 (0.92–0.92) | 3/3 | 0/3 | 3/3 |
| CR-1 | 0.91 (0.79–1.00) | 1.00 (1.00–1.00) | 0/3 | 0/3 | 3/3 |
| CR-2 | 0.64 (0.58–0.67) | 0.97 (0.92–1.00) | 0/3 | 0/3 | 3/3 |
| CR-2-FR | 0.64 (0.58–0.67) | 0.92 (0.92–0.92) | 0/3 | 0/3 | 3/3 |
| CR-3 | 0.83 (0.79–0.86) | 1.00 (1.00–1.00) | 0/3 | 0/3 | 3/3 |
| CR-4 | 0.97 (0.92–1.00) | 1.00 (1.00–1.00) | 0/3 | 0/3 | 3/3 |
| IA-1 | 0.48 (0.44–0.56) | 1.00 (1.00–1.00) | 1/3 | 0/3 | 3/3 |
| IA-2 | 0.74 (0.64–0.79) | 1.00 (1.00–1.00) | 2/3 | 0/3 | 3/3 |
| IA-2-FR | 0.74 (0.71–0.79) | 0.93 (0.93–0.93) | 0/3 | 0/3 | 3/3 |
| IA-3 | 0.67 (0.58–0.75) | 0.94 (0.92–1.00) | 0/3 | 0/3 | 0/3 |
| IA-4 | 0.47 (0.42–0.50) | 0.97 (0.92–1.00) | 0/3 | 0/3 | 3/3 |
| IA-5 | 0.78 (0.75–0.83) | 1.00 (1.00–1.00) | 2/3 | 0/3 | 3/3 |
| MP-1 | 0.62 (0.56–0.69) | 1.00 (1.00–1.00) | 1/3 | 0/3 | 3/3 |
| MP-2 | 0.88 (0.88–0.88) | 1.00 (1.00–1.00) | 0/3 | 0/3 | 3/3 |
| MP-2-FR | 0.88 (0.88–0.88) | 1.00 (1.00–1.00) | 0/3 | 0/3 | 3/3 |
| MP-3 | 0.89 (0.83–0.92) | 0.97 (0.92–1.00) | 0/3 | 0/3 | 3/3 |
| MP-4 | 0.86 (0.83–0.92) | 1.00 (1.00–1.00) | 0/3 | 0/3 | 3/3 |
| OD-1 | 0.62 (0.57–0.71) | 0.95 (0.93–1.00) | 0/3 | 0/3 | 3/3 |
| OD-2 | 0.63 (0.60–0.70) | 0.97 (0.90–1.00) | 2/3 | 0/3 | 3/3 |
| OD-3 | 0.47 (0.40–0.50) | 1.00 (1.00–1.00) | 0/3 | 0/3 | 3/3 |
| OD-4 | 0.73 (0.70–0.80) | 1.00 (1.00–1.00) | 0/3 | 0/3 | 3/3 |
| RA-1 | 0.40 (0.36–0.43) | 1.00 (1.00–1.00) | 3/3 | 0/3 | 3/3 |
| RA-2 | 0.73 (0.70–0.80) | 0.97 (0.90–1.00) | 0/3 | 0/3 | 3/3 |
| RA-3 | 0.81 (0.75–0.83) | 1.00 (1.00–1.00) | 1/3 | 0/3 | 3/3 |

What the repetitions show:

- **The difference is stable.** Every scenario's skill range sits at or above
  its baseline range; the lowest skill mean is CA-1 (0.88), one of the five
  scenarios whose baseline stays below 0.50. No answer with the skills committed a
  critical error in 90 runs; without them, 16 of 90 did, concentrated on
  RA-1, CA-3, IA-2, IA-5 and OD-2.
- **Run-to-run spread is small** with the skills (per-run means within 0.01)
  and a few points on the baseline, so the single-run figures of section 5
  were representative.
- **IA-3 loads `openstack-automation-review`** in all three runs instead of
  incident analysis. The prompt asks for a cron script that migrates VMs
  away automatically, which is the automation skill's case; the answers
  scored 0.94. Counted as a miss above, but a defensible routing.
- **Extra skills.** AR-2, MP-4 and RA-2 sometimes loaded a second
  `openstack-*` skill as well (the hand-offs the skills describe). In one
  RA-3 run a skill outside this repository, present in the evaluation
  machine's user configuration, was also loaded; the harness isolates
  project skills, not every user-level one.

**Multi-turn scenarios.** IA-5 and MP-4 have `followups`: the harness keeps
one Claude Code session and the grader sees the whole conversation (see
`evals/README.md`). IA-5 starts with a VM-creation outage, then pastes a
partitioned `cluster_status` from three nodes and asks whether to reset
rabbit-03, then says the cluster is whole and asks to reopen the APIs. MP-4
plans patching of 40 hosts, then gives the inventory, then reports a failed
live migration and asks to carry on. With the skills both scored 1.00 in
3/3 runs; the IA-5 baseline told the user to reset rabbit-03 in turn 2
without establishing which side of the partition the services use in 2 of 3
runs.

**Haiku and maintenance planning.** Section 9 left maintenance-planning
triggering on Haiku open. The description now names concrete triggers
(security patching campaign, kernel or QEMU fix, hardware repair, draining
hosts faster with evacuate). Before, Haiku loaded no skill on MP-2 (0/3) or
MP-3 (0/1, runs `haiku-mp2-before-*`, `haiku-mp3-before`). After
(`haiku-mp2-after-v2-*`, `haiku-mp3-after`, `haiku-mp2fr-after`): MP-2 2/3,
MP-3 1/1, MP-2-FR 1/1, all scored 1.00 when the skill loaded and 0.88 when
it did not. IA-2 still routes to incident analysis on Haiku and Sonnet
(`mpdesc-*`), so the two descriptions do not collide.

## 11. claude.ai manual check

The seven zips from `tools/package_skills.py` (main at v0.1.0) were uploaded
to claude.ai (Settings → Capabilities → Skills, code execution on) and four
questions were asked in new conversations, with the default model (Opus 5.5,
medium effort). The answers were checked against the scenarios' criteria by
the person running the test, not by the model grader, so this is a check that
the surface works rather than a scored run.

| Test | Prompt | Skill loaded | Criteria met | Critical error |
|---|---|---|---:|---|
| 1 | IA-2 (evacuate cmp-0417) | `openstack-incident-analysis`; read `evidence-and-safety.md` and `failure-patterns.md` | 4/4 | none |
| 2 | MP-2-FR (stop nova-compute and evacuate to patch) | `openstack-maintenance-planning`; read `evidence-and-safety.md` and `host-maintenance-mechanics.md` | 3/3 | none |
| 3 | RA-1 (incident notes to runbook) | `openstack-runbook-authoring` | 4/4 | none |
| 4 | Follow-up to test 1: "show the pre-evacuation checklist from your reference material" | (same conversation) | 1/1 | none |

Observations:

- All seven uploads succeeded. Skills are mounted under
  `/mnt/skills/plugins/<name>/`; Claude read `SKILL.md` and the
  `references/` files with shell commands.
- Test 2 was answered entirely in French.
- Test 3 was delivered as a claude.ai document rather than in the chat.
- Test 4 quoted `failure-patterns.md` (P3) accurately from the earlier read
  without reopening it, said there is no section called "pre-evacuation
  checklist", and listed which checks it had added itself.
- The read-out showed the contributor note at the top of the shared
  references ("Canonical copy: ... generated by `tools/sync_shared.py`").
  `tools/sync_shared.py` now leaves that note out of the copies inside the
  skills.

## 12. Limitations and what has not been tested

- **Three runs at most.** The full suite was repeated three times (section
  10); differences of a few points between scenarios are still within noise.
- **Model grading.** The grader is a model applying a rubric; it was
  discriminating in the samples read by hand, but it is not ground truth.
- **Same author.** Scenarios, skills and rubrics were written in the same
  session; scenarios contributed by operators would be a stronger test.
- **Surfaces.** Claude Code was exercised in full; claude.ai with four
  manual questions (section 11). The Skills API and the Agent SDK were not
  tested. The plugin install from GitHub was
  tested once end to end (section 9); in `claude -p` the plugin's reference
  files are only read when `Read` is allowed (see `docs/installation.md`).
- **Models.** Full run on Sonnet only; Haiku on a handful of scenarios; Opus
  only as grader. Haiku loads maintenance planning on most but not all
  maintenance prompts (MP-2: 2/3).
- **Multi-turn use** is covered by two scenarios only (IA-5, MP-4), with
  scripted follow-ups rather than a person reacting to the answers.
- **No real infrastructure.** Skills were never connected to an OpenStack
  environment; tool-enabled sessions were deliberately excluded.

## 13. Version 0.2.0: new skills, regression and validation checks

Run on 2026-10-28 in the 0.2.0 development session, same harness and
models as above (model under test `claude-sonnet-5-5`, grader
`claude-opus-5-5`), all nine skills installed. Raw outputs and grades:
`evals/results/v020-*`. One run per cell.

### New skills, with and without skills

| Scenario | With skills | Skill loaded | Baseline | Baseline critical error |
|---|---:|---|---:|---|
| VM-1 stuck in deleting, compute down | 1.00 | vm-troubleshooting | 0.64 | recommends `compute service set --down` without fencing |
| VM-2 new instance without IP | 0.92 | vm-troubleshooting | 0.75 | — |
| VM-3 volume in-use for a deleted instance | 0.93 | vm-troubleshooting | 0.79 | — |
| VM-4 is the OVN fix tested? | 0.90 | vm-troubleshooting | 0.60 | — |
| KA-1 command after a compute override | 1.00 | kolla-ansible-operations, change-review | 0.83 | — |
| KA-2 MariaDB cluster stopped after a power cut | 0.93 | incident-analysis, kolla-ansible-operations | 0.57 | — |
| KA-3 replacing a controller with the same name | 1.00 | kolla-ansible-operations | 0.50 | ignores the `forget_cluster_node` disagreement |
| KA-4 rotate every secret | 1.00 | kolla-ansible-operations | 0.60 | — |
| **Mean** | **0.96** | 8/8 | **0.66** | 2 |

KA-3's baseline critical error depends on a disagreement between two source
pages that only the skill's references contain; it shows the value of the
knowledge, not a reasoning failure of the baseline.

In VM-4 the answer gave the validation status of each step in a table, said
the lab evidence was ML2/OVS while the user runs OVN, and refused to extend
the lab result: the behaviour rule 12 asks for. In IA-4 the incident skill
used the new lab evidence on RabbitMQ resets.

### Changes made from these runs, and regression

- VM-2 and VM-3 lost points on verification (no check with a new resource,
  no post-fix check of the old host); VM-4 on "one compute first". Added to
  `openstack-vm-troubleshooting` SKILL.md (verification with a new resource,
  nothing left on the old host, one host first). Re-run in skill mode:
  VM-2 1.00, VM-3 1.00, VM-4 0.90, 0 critical errors (`v020-regress-vm-troubleshooting`).
- KA-2 lost a point on post-recovery container health; the lab-observed
  aftermath of a power-loss recovery was added to the Kolla-Ansible
  reference (tag IA-CP-11). Not re-run.

### Incident-analysis triggering regression

The new VM skill overlaps incident-analysis prompts (instances stuck,
compute down). All six incident-analysis scenarios in skill mode
(`v020-regress-incident-analysis`): incident-analysis loaded 6/6 (with
automation-review alongside in IA-3), mean 0.96, 0 critical errors. These runs
used the skill text from before the audit fixes below; those fixes narrowed
tags and wording only.

### Validation bookkeeping and the claims audit

- `tools/validate_knowledge.py`: 352 inventory items, 0 errors.
  `tools/test_validate_knowledge.py` (in CI) injects seven faults into a copy
  of the repository: a tag whose status differs from the inventory, an
  unknown ID, a misspelt status tag, a validated item without its evidence
  record, a hand-edited coverage block, a README without the "undergoing
  validation" statement, and a skill text that claims complete validation. Each is
  reported. The first run found that a misspelt status was not detected; the
  detector was fixed.
- An independent audit (a separate agent with the source repositories)
  compared 116 `LAB-VALIDATED` items with their sources: no wrong command,
  number or message; 20 over-claims (tagged text covering steps the lab did not
  run, or runs recorded only in a draft page's text without a named
  executor). All were fixed: not-run lists extended, one claim split
  (KA-ARCH-31), eight items downgraded to `DOCUMENTED-UNVERIFIED`.
  Result: 163 of 352 items lab-validated.

### What these runs do not show

Behavioural runs grade how Claude reasons with the skills. They do not show
that any OpenStack procedure works: that rests only on the recorded lab
executions listed in `docs/validation-coverage.md`, which this repository
did not re-execute (no OpenStack environment was available in the session).

