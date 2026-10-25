# Knowledge map — *OpenStack, the Day After Tomorrow* (v1.2)

This map records what the book actually contains, so that every skill in this
repository can be traced back to it. It was produced by reading the full English
edition (front matter, Introduction, Chapters 1–20, Conclusion, Appendices A–F,
References) at commit `09b5dea` of
[soufian-zaouam/openstack-the-day-after-tomorrow](https://github.com/soufian-zaouam/openstack-the-day-after-tomorrow).
The French edition mirrors the English one chapter for chapter and was not used
as a separate source.

Citation convention used across the repository: `Ch. 9` = Chapter 9,
`App. A` = Appendix A, `Intro` = Introduction, `Concl.` = Conclusion.

## Contents

1. How the book marks its own statements
2. Main operational principles
3. Methods and decision frameworks
4. Operational scenarios and incidents (the *From the field* passages)
5. Recurring problems the book helps solve
6. Lessons convertible into reusable workflows
7. Material that should stay reference documentation
8. What the book does **not** cover
9. Source map per skill

---

## 1. How the book marks its own statements

The book distinguishes four kinds of statement (*How to Read This Book*):

| Kind | Meaning | Implication for the skills |
|---|---|---|
| **Technical note** | Verifiable OpenStack fact, with a reference. "The parts of the book most likely to age." | Usable as reference, but skills must tell the user to verify release-specific details against current docs. |
| **Principle** | An operating rule the book recommends. "A recommendation, not a fact." | Encoded as decision rules, presented as the author's recommendation, never as universal law. |
| **From the field** | A situation the author encountered, abstracted. "Evidence of what happened in one context, not proof of what will happen in yours." | Used as worked examples and evaluation scenarios, not as prescriptions. |
| Reasoning | The argument connecting the above; opinions are stated in the first person. | Positions the author flags as personal (e.g. "execution before judgement", "governance by committee is a temptation to resist") are labelled as such in the skills. |

The book is explicit that it is "one operator's experience and point of view,
not a standard or a reference manual" (README) and that where the answer
depends on the deployment or backend, it says so (Intro). The skills inherit
that posture.

## 2. Main operational principles

### 2.1 The central concept: control

- **Control** = the organization can understand, decide, intervene, recover and
  evolve the platform without depending on individuals, undocumented
  assumptions or uncontrolled complexity (Intro, Ch. 2).
- Availability is an outcome; control is a capability. A platform can be
  available and uncontrolled (Ch. 2).
- Control is relative to business consequence: concentrate effort where low
  control meets high consequence (Ch. 2).
- Control includes independence from vendors, a deployment engineer or a
  proprietary process (Ch. 2, Ch. 14).
- Control is a moving state, must be **evidenced** rather than felt, and can be
  lost without any incident (Ch. 2).
- **Control debt** vs **technical debt**: the same artefact is control debt when
  the organization loses its ability to understand/recover it (Ch. 3).

### 2.2 The four capabilities (Intro, Ch. 2, Fig. 4.1)

| Capability | Definition in the book | Failure when isolated (Ch. 2) |
|---|---|---|
| Visibility | Observe state, understand meaningful signals, including ownership and dependencies. "Useful evidence, not more data." | Information without action |
| Stability | Maintain a trusted operating state; controlled degradation, capacity, safe change, recovery. | Depends on heroes (without organization) |
| Organization | People, knowledge, skills, ownership, collaboration that survive departures. | Local optimization (without governance) |
| Governance | Make, communicate and own decisions when objectives, constraints and risks conflict. "Everyone can challenge. Someone must decide." | Bureaucracy (without evidence) |

### 2.3 Boxed principles (verbatim titles, chapter of origin)

| Principle | Source |
|---|---|
| Stay as close to upstream as practical. | Intro, Ch. 14 |
| The measure of a successful deployment is whether the platform remains operable when the deployment experts are no longer present. | Ch. 1 |
| Complexity is part of the operational risk of an OpenStack platform, and it must earn its place. | Ch. 3 |
| Assessment tells us where we are. Measurement tells us whether we are moving in the right direction. | Ch. 5 |
| The purpose of observability is to make the platform understandable enough to support the right decision at the right time. | Ch. 8 |
| Before changing a mission-critical OpenStack platform, understand enough to know what you are risking, how you will detect failure, and how you will recover if you are wrong. | Ch. 9 |
| Recovery is a feature because a platform is not operational if the organization cannot demonstrate how it returns to a trusted state. | Ch. 10 |
| Documentation is operational memory only when the organization has a deliberate way to create it, maintain it, test it, use it and retire it. | Ch. 11 |
| A team is resilient when the platform remains operable after its experts change. | Ch. 12 |
| Everyone can challenge. Someone must decide. | Ch. 13 |
| A workaround is safe only while the risk it introduces remains smaller than the risk it removes. | Ch. 15 |
| The objective is the right level of automation for the platform the organization can actually operate, which is rarely the maximum. | Ch. 16 |
| Security exposure is a control gap like any other. | Ch. 17 |
| A successful OpenStack evolution is a platform whose future can still be operated deliberately, not merely a newer one. | Ch. 18 |
| Stopping is not giving up control. In the right circumstances, it is how control is preserved. | Ch. 19 |
| Security requirements define what must be achieved. Platform capacity and business criticality determine how safely it can be achieved. | Ch. 20 |

### 2.4 Principles stated in the running text (not boxed)

- Distribute operational work by risk and required expertise, not convenience;
  "does this require platform expertise or a reliable procedure?" (Ch. 1).
- **Change capacity** is a finite resource; prioritize changes that improve the
  platform's ability to absorb future changes (Ch. 1).
- The cost of a change is blast radius, uncertainty, recoverability,
  dependencies, criticality and available capacity — not the number of
  commands (Ch. 1).
- **Trusted state** and **controlled degradation**; the control plane and data
  plane fail separately (Ch. 1, technical note).
- Ask whether an improvement made *now* reduces more risk than it introduces (Ch. 1).
- Facts / hypotheses / assumptions; try to disprove hypotheses; a symptom is not
  a diagnosis; a request is not a diagnosis (Ch. 9).
- Evidence proportional to consequence; uncertainty is a risk signal; sometimes
  the safest action is to wait (Ch. 9).
- **Do not stack uncertainty** — with the author's caveat that for platforms far
  behind on unmaintained releases, transformation can be the only
  stabilization (Ch. 7, Ch. 9).
- Verification and stop conditions are designed *before* execution; "approval
  alone does not make a decision controlled" (Ch. 9).
- State explicitly what remains unknown and why residual uncertainty is
  acceptable (Ch. 9).
- "What changed?" resolves more incidents than any single metric (Ch. 8, author's experience).
- Recovery is designed around capabilities, validated end to end; databases are
  restored as one operation at one point in time, then reconciled (Ch. 10).
- Fence before evacuating (Ch. 10, technical note and field passage).
- Repeated recovery is not stability (Ch. 9); repetition of a workaround is
  evidence (Ch. 15).
- Automate execution before judgement (Ch. 16, flagged as the author's position).
- Decision rights follow consequence and blast radius, and must be visible
  before the incident (Ch. 13).
- Risk acceptance should expire (Ch. 13); every backport, workaround, guardrail
  and security exception needs an owner and an exit condition (Ch. 7, 14, 15, 17).
- Resumption after a stop is a new decision (Ch. 19).
- The organization must remain capable of saying no (Concl.).

## 3. Methods and decision frameworks

| Method | What it is | Source |
|---|---|---|
| Control loop | Observe → Understand → Prioritize → Decide → Act → Verify → Learn; lightweight for routine, more explicit as consequence/uncertainty grow; names where it breaks. | Ch. 4 |
| Four questions for any proposed change | What capability does it create/protect; what could it affect; what operational burden does it add; what is required to operate it after delivery moves on. | Ch. 1 |
| Consequence chain for assessment | Business capability → OpenStack capability → Platform service → Technical dependency → Team → Expertise → Recovery capability. | Ch. 5 |
| User-journey walk | Follow a real transaction (e.g. VM creation) through every dependency; at each step: signal, owner, detection, recovery, business capability. | Ch. 5, Fig. 5.1 |
| Control spectrum | Unknown → Visible → Understood → Controlled → Recoverable → Sustainable, with explicit criteria per level. | Ch. 5 |
| Evidence confidence | Observed in production > documented but never exercised; demonstrated > untested; independently reproduced > single-expert statement. | Ch. 5 |
| Four outcomes of a finding | Act now / plan / monitor / consciously accept. | Ch. 5 |
| Capability measures | Per capability plus recovery, change quality, upstream alignment; measures the platform produces itself; no single score; metrics need a decision owner; leading indicators. | Ch. 6 |
| Restoration sequence | Discover → Protect → Assess → Stabilize → Recover Knowledge → Simplify → Establish Control → Evolve; first-30-days outputs; guardrails with owner and removal condition; "control restored" exit criteria. | Ch. 7 |
| Visibility questions | Why can users not create VMs, which capabilities, which shared dependencies, is it new, what changed, who owns it. | Ch. 8 |
| Repair vs rebuild criterion | Is the information in the current state valuable enough to justify preserving its uncertainty? Which option most likely returns to a trusted state with acceptable impact? | Ch. 10 |
| Documentation minimum information model | Purpose, scope, context, dependencies, action/decision, expected result, stop and escalation conditions, recovery, owner, last validation date, history. Decision points and "must not do without escalation". | Ch. 11 |
| Accountability levels | Operational / capability / platform technical accountability, distinct from business accountability. | Ch. 12 |
| Decision-rights four questions and chain | Who assesses, who owns the capability, who is accountable, who decides; Action → … → Decision authority. | Ch. 13 |
| Backport minimum record | Upstream issue, upstream change of origin, why not the full upgrade, owner, test, reconsideration trigger. Three layers: upstream / distribution / local. | Ch. 14, Fig. 14.1 |
| Upgrade readiness review | Local modifications, recovery coverage, test coverage, docs, capacity, ownership gaps, consumer readiness, monitoring readiness — plus policy changes. | Ch. 14, Ch. 17 |
| Complexity tests | Value, who operates it, how recovered, cost at next lifecycle transition; plus what changes at upgrade and what happens if unavailable. Mental models (not formulas): Business impact × Loss of control = Operational exposure; Business value + Risk reduction + Control gained − Complexity introduced. | Ch. 3, Ch. 15 |
| Debt decision table | Seven situations → keep and document / plan simplification / prioritize removal or redundancy / remove during planned event / keep temporarily with exit condition / treat as priority risk / remove. | Ch. 15 |
| Workaround record | Purpose, owner, scope, side effects, detection criteria, recovery method, exit condition. | Ch. 15 |
| Automation discipline | Execution vs judgement; semi-automation; production-software obligations; scope-proportional safeguards (preview, dry run, explicit scope, confirmation, monitoring, stop conditions). | Ch. 16 |
| Decision gates | Reject before scoring if: unacceptable business impact, no credible recovery, insufficient evidence, no owner, no authority, unbounded blast radius, violates mandatory security/regulatory requirement. | Ch. 18, App. A |
| Weighted scoring model | Six dimensions, illustrative weights 25/25/20/10/10/10, 1–5 with 5 always preferable; a conversation tool that never overrides a gate. | Ch. 18, App. A |
| Evolution as operating states | Each transition: what changes, what stays protected, what capability is created, what risk is introduced, how completion is known. Four horizons; reassessment points. | Ch. 18 |
| Field-decision grid | Context → Signal → Uncertainty → Business risk → Options → Decision → Trade-off → Outcome → Lesson. | Ch. 18–20 |
| Stop conditions catalogue | Dependency behaves differently; blast radius exceeds approved boundary; monitoring insufficient; recovery no longer credible; critical performance crosses threshold; capacity unavailable; decision authority unavailable. | Ch. 19 |
| Stop communication | What is restricted, why continuing is riskier, what remains protected, what condition allows reopening. | Ch. 19 |
| Control Decision Framework | 12 steps: Situation, Business objective, Evidence, Uncertainty, Constraints, Business impact, Options, Trade-offs, Decision rights, Controlled action, Verification, Learning. | App. A |
| Control Assessment Worksheet | 17 questions per critical capability; "we think so" means the level is not established. | App. B |
| Minimum Change Decision Record | Owners, objective, current state, evidence, uncertainty, options, trade-offs, selected/rejected, recovery, stop conditions, verification, follow-up. | App. C |
| Control Review Questions | Visibility, Stability, Organization, Governance, Evolution, Security. | App. D |
| Operating principles at a glance | Before acting / before changing / during incidents / during evolution / for the organization. | App. E |

## 4. Operational scenarios and incidents

Every *From the field* passage and both worked decisions, with the decision
pattern each one teaches. These are the only scenarios the evaluation suite
treats as "documented in the book".

| ID | Scenario | Source | Decision pattern |
|---|---|---|---|
| F1 | VM creation fails; RabbitMQ RPC unreliable and Galera affected; existing VMs fine. Team stops the APIs, restarts RabbitMQ after purging queues, restarts MariaDB, verifies (Galera full/Primary, RabbitMQ whole with consumers, agents reporting, test VM end to end), then reopens. Root cause later: RabbitMQ network partition. | Ch. 19 | Controlled degradation; stop before repair; verification before reopening; review must reach the cause. |
| F2 | Compute host failed; no proof it was dead rather than isolated; no automatic fencing. Team used out-of-band management to confirm and power off, then evacuated. | Ch. 10 | Fence before evacuate; missing heartbeat is not proof. |
| F3 | Long-lived platform with stuck BUILD/ERROR/deleting instances, orphan ports, volumes attached to deleted instances. Cleanup with project tools, then direct DB corrections. | Ch. 10 | "The state that lies"; DB surgery as high-consequence change (backup, one record at a time, verify). |
| F4 | Shared test environment with years of inconsistent state; each fix created the next problem. Evidence preserved, baseline written, environment rebuilt and validated progressively. | Ch. 10 | Repair vs rebuild; production changes the equation. |
| F5 | New engineer executed a real procedure alone, observed. Gaps: step order, implicit precautions, first signals when things diverge, why some configs are exceptions. Docs corrected from his questions. | Ch. 11 | Test documentation with a non-author. |
| F6 | Senior engineer left after an organized transfer; upgrade execution and the reasons for customizations were not transferred. Rebuilt from code, configs, git history, test upgrade, decision records. | Ch. 12 | Knowledge only shows when someone else performs the work. |
| F7 | Pinned-CPU VMs showed steal time; live migration relieved it temporarily; team kept migrating, then stopped, accepted limited steal and investigated the cause. | Ch. 15 | Workaround becoming the risk; repetition is evidence; relocate ≠ fix. |
| F8 | Mandatory OS patching of hundreds of compute hosts; not enough spare capacity to live-migrate everything; criticality unknown to infra. Consumers filled a shared criticality table; critical workloads live-migrated, others restarted on agreement. | Ch. 20 | Security target fixed, execution differentiated by criticality and capacity; collect criticality before the event. |
| W1 | Illustrative evolution decision: unmaintained series two SLURP releases behind, ~12 local patches (3 in Nova scheduling, author gone), recovery demonstrated once two years ago by the departed engineer, team 6→4, OSSA with untested backport. Options immediate / progressive / postpone; model says first action is a recovery exercise. | Ch. 18 | Gates before scoring; the score points to what to fix first. |

Also used as illustrative (non-field) examples in the text: RabbitMQ node left
the cluster vs cluster partitioned — same alert, different runbooks (Ch. 11);
the rehearsal "a user cannot create a VM — who receives it…?" (Ch. 1); the
loop example where "fix Nova" becomes "protect the trusted state while
accepting loss of provisioning" (Ch. 4).

## 5. Recurring problems the book helps solve

1. "VMs won't build" and other cross-service symptoms with misleading local explanations (Ch. 4, 5, 8, 9).
2. Pressure to fix fast during control-plane instability (Ch. 19).
3. Hosts that look dead; evacuation risk (Ch. 10).
4. Stale/orphaned database state distorting quota, capacity and investigations (Ch. 6, 10).
5. Patching and maintenance campaigns without enough spare capacity (Ch. 20).
6. Workarounds repeated until they become architecture (Ch. 15).
7. Local backports and divergence that make every upgrade harder (Ch. 14, 17).
8. Upgrades postponed until they become emergencies; SLURP misread as a full promise (Ch. 14).
9. Silent expiry: TLS certificates, Fernet key rotation (Ch. 8, 17).
10. Policy (RBAC) changes breaking users and automation after upgrade (Ch. 14, 17).
11. Automation that only its author understands, or that is delegated judgement (evacuate on heartbeat) (Ch. 16, 10).
12. Single-expert dependency, failed knowledge transfer, team shrinkage (Ch. 1, 12).
13. Unclear decision rights during incidents; disruptive actions with no authorized owner (Ch. 13).
14. Documentation theatre; runbooks without decision points (Ch. 11).
15. Platforms where control is already lost and teams want to transform immediately (Ch. 7).
16. Recovery plans that test components, not capabilities; database backups never restored (Ch. 10).

## 6. Lessons convertible into reusable workflows

| Workflow | Built from | Becomes |
|---|---|---|
| Structured incident investigation with evidence ledger, dependency walk, hypothesis elimination, stop/degrade decision and pre-defined verification | Ch. 4, 5, 8, 9, 10, 19, App. E | `openstack-incident-analysis` |
| Pre-change review with gates, blast radius, recovery path, stop conditions, verification, decision rights and a decision record | Ch. 1, 9, 13, 14, 19, App. A, App. C | `openstack-change-review` |
| Host maintenance / patching campaign planning by criticality, capacity and failure domain | Ch. 9, 10, 17, 20 | `openstack-maintenance-planning` |
| Option comparison for lifecycle and structural decisions (upgrade vs backport vs postpone, keep/remove debt, workaround, repair vs rebuild, security exception) | Ch. 13, 14, 15, 17, 18, App. A | `openstack-operational-decisions` |
| Control assessment, measurement, restoration planning, organizational-change review | Ch. 2, 5, 6, 7, 12, App. B, App. D | `openstack-control-assessment` |
| Review of automation for judgement delegation, scope, safeguards and operability | Ch. 3, 10, 16 | `openstack-automation-review` |
| Turning knowledge into runbooks with decision points, stop/escalation and validation by a non-author | Ch. 7, 10, 11, 12 | `openstack-runbook-authoring` |

## 7. Material that should stay reference documentation

These parts are valuable but are facts or definitions, not methods. They are
paraphrased into skill `references/` files where a skill needs them, with a
note that they age and must be verified against current upstream docs:

- Control plane vs data plane failure behaviour (Ch. 1 technical note, Fig. 1.1).
- What a VM creation traverses (Ch. 5 technical note, Fig. 5.1).
- Signals on shared components: Galera `wsrep_*`, RabbitMQ queues/consumers/alarms, service and agent liveness, transitional instance states, Placement vs hypervisor, TLS and Fernet expiry (Ch. 8 technical note).
- Galera quorum and bootstrap, RabbitMQ queue types, partition handling and metadata store, memcached, load balancer VIP (Ch. 10 technical note).
- Evacuation and fencing (Ch. 10 technical note).
- Stale-state tooling: `nova-manage placement audit|heal_allocations`, `nova-manage db archive_deleted_rows` (Ch. 6, 10).
- Release maintenance phases, SLURP, backport vocabulary (Ch. 14 technical notes).
- `*-status upgrade check`, Nova rolling upgrade sequence, Neutron expand/contract (Ch. 14 technical note).
- Pinned CPUs, emulator threads, NUMA live migration history (Ch. 15 technical note).
- Host maintenance operations: disable, live/block/cold migration, compatibility constraints, non-migratable instances, patched binary only after migration/restart (Ch. 20 technical note, Fig. 20.1).
- Secure default RBAC, `enforce_new_defaults`, `enforce_scope`; Fernet rotation; certificate expiry (Ch. 17).
- Glossary (App. F) and References (book's References section).

Material that is **not** turned into skills: the team-structure and onboarding
discussion of Ch. 12 (used only as inputs to assessment and runbook testing),
the measurement rhythm of Ch. 6 (folded into the assessment skill), and the
book's argument about why Day 2 is hard (Ch. 1–3), which informs the shared
principles file rather than any workflow.

## 8. What the book does not cover

Recorded so that skills do not pretend otherwise:

- **No deployment tool is named or prescribed.** The book never mentions
  Ansible, Kolla-Ansible, OpenStack-Ansible, TripleO or Puppet (searched across
  all chapters and appendices). Chapter 16 discusses automation generically.
  Any tool-specific checks in `openstack-automation-review` are additions by this
  repository and are marked as such.
- No monitoring stack, networking backend, distribution or support contract is
  prescribed (Intro, *Scope and limits*).
- No command-level troubleshooting catalogue. The author's separate
  [OpenStack Production Guide](https://github.com/soufian-zaouam/openstack-production-guide)
  (troubleshooting by symptom, RCA cases) is a companion work; it was **not**
  used as a source for this version of the skills.
- No universal thresholds (e.g. "migrate at most N VMs at a time"). The book
  insists such boundaries are context-dependent (Ch. 9, 20).

## 9. Source map per skill

| Skill | Primary sources | Secondary sources |
|---|---|---|
| openstack-incident-analysis | Ch. 4, 8, 9, 19; Ch. 1 & 5 technical notes; Ch. 10 (fencing, stale state, recovery as change) | Ch. 11 (partition vs node-left), Ch. 13, App. E |
| openstack-change-review | Ch. 9, App. A gates, App. C, Ch. 19 stop conditions | Ch. 1 (four questions, change cost), Ch. 13, Ch. 14 (upgrade readiness), Ch. 17 (policy, rotation) |
| openstack-maintenance-planning | Ch. 20 (incl. technical note, Fig. 20.1) | Ch. 9, Ch. 10 (evacuation is not maintenance), Ch. 17, Ch. 13 |
| openstack-operational-decisions | App. A, Ch. 18, Ch. 14, Ch. 15 | Ch. 10 (repair vs rebuild), Ch. 13, Ch. 16, Ch. 17, Concl. |
| openstack-control-assessment | Ch. 5, Ch. 6, Ch. 7, App. B, App. D | Ch. 2, Ch. 12, Ch. 13, Ch. 8 technical note |
| openstack-automation-review | Ch. 16 | Ch. 3, Ch. 10 (evacuation/fencing), Ch. 15 (workarounds into scripts), Ch. 14 (deployment tooling & branch renames) |
| openstack-runbook-authoring | Ch. 11 | Ch. 10 (exercises), Ch. 12 (testing by non-author, F5/F6), Ch. 7 (guardrails), Ch. 19 |

## 10. Where the skills deliberately diverge from the book

Technical statements in the book that upstream documentation contradicts.
The skills follow upstream, say so where the point appears, and list the
point here as a candidate erratum for the book.

| Book statement | Upstream behaviour | Where handled |
|---|---|---|
| Instances with SR-IOV direct ports cannot be live-migrated (Ch. 20 technical note) | Live-migratable with the libvirt driver since Train: the port is unplugged and re-plugged, so the guest loses that interface briefly. vGPU instances are live-migratable since 2024.1 with recent libvirt, QEMU and kernel. | `openstack-maintenance-planning` (SKILL.md step 3, `host-maintenance-mechanics.md`) |
