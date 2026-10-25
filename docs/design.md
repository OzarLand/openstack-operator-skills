# Design — OpenStack operator skills

Status: implemented (see `docs/evaluation-report.md` for test status).
Input: `docs/knowledge-map.md`.

## 1. Goal and non-goals

**Goal.** Turn the operating method of *OpenStack, the Day After Tomorrow* into
Agent Skills that change how Claude behaves when an engineer brings it a
production OpenStack problem: investigate before acting, separate facts from
hypotheses, weigh business consequence, require recovery and verification, and
leave decisions with the humans who own them.

**Non-goals.**
- Not a command reference or troubleshooting catalogue. The book is not one
  and does not claim to be (knowledge map §8).
- Not a summary of the book. Skills contain procedures and decision rules; the
  book's argument stays in the book.
- Not an executor. No skill runs commands against infrastructure or treats its
  own output as authorization.

## 2. Evaluation of the candidate skills

| Candidate | Verdict | Reason |
|---|---|---|
| A. `openstack-operations-principles` | **Reworked** into `openstack-operational-decisions` + a shared principles file | A free-floating "philosophy" skill would trigger ambiguously, overlap every other skill and produce generic advice. The book's philosophy becomes operational through a specific tool — the Control Decision Framework, its gates and the weighted model (App. A, Ch. 18) — applied to lifecycle and structural decisions (upgrade vs backport, keep/remove debt, workarounds, repair vs rebuild, security exceptions). That is where "technically correct vs operationally suitable" is actually decided. The principles themselves live in `shared/operating-principles.md`, copied into every skill. |
| B. `openstack-incident-analysis` | **Kept** | Strongest support in the book (Ch. 4, 8, 9, 10, 19, App. E) and the highest-stakes use. Implemented first as the proof of concept. |
| C. `openstack-change-review` | **Kept** | Ch. 9, App. A gates, App. C record, Ch. 19 stop conditions form a complete review method. |
| D. `openstack-maintenance-planner` | **Kept, renamed** `openstack-maintenance-planning` | Distinct from change review: it *constructs* a plan (workload classes, capacity per failure domain, migration type, patch order) rather than evaluating one. Ch. 20 supplies a full worked case and the mechanics. Renamed for naming consistency. Upgrades stay in change review / operational decisions, not here. |
| E. `openstack-automation-review` | **Kept, re-scoped** | The book's automation chapter (Ch. 16) is generic and never names Ansible or Kolla-Ansible. The skill's decision rules come from Ch. 16, Ch. 10 (fence-before-evacuate) and Ch. 15 (workarounds becoming scripts). Ansible/Kolla-Ansible specifics (idempotency, check mode, `serial`, failure thresholds) are included as clearly labelled **additions** in a separate reference file. |
| F. `openstack-runbook-builder` | **Kept, renamed** `openstack-runbook-authoring` | Ch. 11 gives a minimum information model, decision points, "must not do", owner and validation date, and the partition-vs-node-left example. Renamed for naming consistency. |
| New: `openstack-control-assessment` | **Added** | Part II (Ch. 5–7) and Appendices B and D are the book's most distinctive method and none of the candidates covered them: consequence chain, control spectrum with criteria, evidence confidence, four outcomes, restoration sequence, review after team change. |

Rejected additional ideas: a separate *upgrade-planning* skill (upgrade
readiness is a change review with extra checks, and the upgrade-vs-backport
choice is an operational decision — splitting further would overlap), a
*security* skill (the book's own position is that security is platform work
handled with the same disciplines, Ch. 17), and a *team/organization* skill
(Ch. 12 is advisory prose with few repeatable procedures; its tests are folded
into assessment and runbook validation).

## 3. Final collection

| Skill | One-line responsibility | Typical trigger |
|---|---|---|
| `openstack-incident-analysis` | Investigate a live or recent incident from evidence to verified recovery decision. | "VMs stuck in BUILD", "RabbitMQ alarms", "host down", "API 503s" |
| `openstack-change-review` | Decide whether a planned change is ready: gates, blast radius, recovery, stop conditions, verification, decision record. | "review this change", "is this upgrade plan safe", "CAB request" |
| `openstack-maintenance-planning` | Build a host maintenance or patching campaign within real capacity and business criticality. | "patch all compute nodes", "drain hosts", "kernel/QEMU update" |
| `openstack-operational-decisions` | Compare options for lifecycle and structural decisions with gates, trade-offs, decision rights and expiry. | "upgrade or backport?", "keep this workaround?", "repair or rebuild?" |
| `openstack-control-assessment` | Assess how much control the organization has, by capability, and turn gaps into decisions. | "audit our platform", "we inherited this cloud", "engineer leaving" |
| `openstack-automation-review` | Review automation for delegated judgement, scope, safeguards, operability and recovery. | "review this playbook", "auto-evacuation script", "should we automate X" |
| `openstack-runbook-authoring` | Turn operational knowledge into a runbook with decision points, stop/escalation and validation. | "write a runbook", "document this procedure", "turn this incident into a procedure" |

Hand-offs between skills are explicit in each `SKILL.md` ("Related skills"),
but each skill works on its own.

## 4. Structure and progressive disclosure

```
skills/<name>/
  SKILL.md                     # < 500 lines; workflow, decision rules, output format, limits
  references/
    operating-principles.md    # copy of shared/ (kept identical by tools/sync_shared.py)
    evidence-and-safety.md     # copy of shared/
    <skill-specific>.md        # technical notes, templates, worked examples
```

- **Shared files are duplicated on purpose.** Every skill must be uploadable on
  its own (claude.ai zip upload, Skills API), and a skill cannot reference files
  outside its own directory. The canonical text lives in `shared/`;
  `tools/sync_shared.py` copies it and `tools/validate_skills.py` fails if any
  copy drifts.
- References are one level deep from `SKILL.md`; reference files over 100
  lines start with a table of contents (Anthropic best practices).
- Frontmatter uses only the portable keys (`name`, `description`, `license`,
  `metadata`) so the same directory works in Claude Code, claude.ai and the
  API. No `allowed-tools`: these skills must not pre-approve any tool.

## 5. Behavioural contract shared by all skills

Encoded in `shared/evidence-and-safety.md` and restated briefly in each skill:

1. Classify every statement as **Observed**, **Reported**, **Hypothesis** or
   **Assumption**, with the source of each observation.
2. Read-only diagnostics before any corrective action; label every proposed
   command as read-only or state-changing.
3. Business impact before any disruptive recommendation.
4. Every state-changing recommendation carries: prerequisites, blast radius,
   expected result, verification, stop conditions, recovery path, and who must
   approve it.
5. Never claim an action happened or succeeded without evidence from the user.
6. Recommendations are not authorization. Destructive or disruptive actions
   require a named human decision owner.
7. Missing information is listed as a gap with what would close it — never
   filled with invented values.
8. Context-dependent choices are presented as options with conditions, not as
   universal rules.
9. Release-specific facts are flagged for verification against current
   upstream or vendor documentation.

## 6. Source attribution convention

- `[Book: Ch. 9]` — a rule or fact taken from the book.
- `[Book: Ch. 16, author's position]` — something the author explicitly flags
  as personal opinion.
- `[Addition]` — a recommendation introduced by this repository, not found in
  the book. Additions are kept few and are marked wherever they appear.

Skills cite the book so a human can check the reasoning; Claude does not need
the book to run them.

## 7. Evaluation approach

- **Structural checks** (`tools/validate_skills.py`, run in CI): frontmatter
  validity against the spec, name = directory, description length and
  characters, body length, links resolve, references one level deep, TOC on long
  references, shared copies identical, citations point to chapters that exist,
  scenario files well-formed and ≥ 3 per skill.
- **Behavioural scenarios** (`evals/scenarios/*.json`): built from the book's
  documented situations (knowledge map §4) where possible; each defines
  available evidence, missing information, expected reasoning, expected output,
  critical errors and grading criteria.
- **Behavioural runs** require running Claude. What was actually run, how, and
  the results are recorded in `docs/evaluation-report.md`; nothing is reported
  as passed unless it was run.

## 8. Licensing note

The book is CC BY-NC-ND 4.0, which does not allow distributing adaptations.
The author holds the copyright and can license these skills differently; the
skills paraphrase and restructure the method rather than reproduce the text.
The licence chosen for this repository is a decision for the author and is
flagged in the final report before anything is published.
