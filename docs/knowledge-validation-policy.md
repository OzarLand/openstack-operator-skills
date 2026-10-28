# Knowledge validation policy

This repository gives operational advice for production OpenStack. A procedure
can read well, pass every linter, and still fail on a real platform. This
policy defines what this repository may call *validated*, what counts as
evidence, and how unverified knowledge is kept visible as unverified.

The current state of validation is in
[validation-coverage.md](validation-coverage.md) (generated from
[`validation/inventory.yaml`](../validation/inventory.yaml)).

## Contents

1. Principles
2. Statuses
3. What is in scope, and what is not
4. Acceptable evidence
5. Recording a validation
6. How skills show validation status
7. Revalidation
8. Contributing knowledge and evidence
9. Review and approval
10. Automated checks, and what they do not prove
11. Repository-wide validation claims

## 1. Principles

- **Execution, not reading.** Knowledge is validated only when the procedure
  or behaviour was executed and the observed result matched the expected
  result, on a real platform. Reading documentation, an existing runbook, an
  upstream commit or an AI-generated explanation is not validation. Neither is
  finding the same procedure in another project, or reviewing it carefully.
- **Validation is per claim.** A skill can contain a lab-validated diagnostic,
  a documented-but-untested alternative and a proposal awaiting a test. Each
  carries its own status. A skill is never "validated" as a whole while it
  contains unverified operational instructions.
- **A test validates what it tested.** A lab run on OpenStack 2026.1 with
  Kolla-Ansible and ML2/OVS validates that combination, for the steps actually
  run. It says nothing about OVN, another release, another deployment tool or
  production scale. The environment and the unobserved steps are recorded.
- **No fabricated evidence.** No invented dates, outputs, environments or
  results. A missing value is written `unknown` or `not provided`. A status is
  never raised without new evidence.
- **Production and lab stay distinct.** Both are real evidence; they answer
  different questions. Lab validation shows the procedure works as written on
  a representative platform; production validation shows it held up under
  real load, data and constraints.

## 2. Statuses

| Status | Meaning | Minimum evidence |
|---|---|---|
| `PRODUCTION-VALIDATED` | Executed and verified in a real production environment. | A documented execution with environment (release, deployment method, backends), date or period, what was run, what was observed, and who can vouch for it. Sanitized. |
| `LAB-VALIDATED` | Executed and verified in a representative laboratory environment. | A documented lab execution: environment, date, steps run, observed result, and the steps **not** run. |
| `DOCUMENTED-UNVERIFIED` | Comes from documentation, source code, a book, a runbook or another trusted source; no evidence of a successful execution is available. | A source reference. |
| `PROPOSED-UNVERIFIED` | A proposal, hypothesis, adaptation or new procedure written for this repository, not yet executed anywhere. | None, beyond a clear statement of what it proposes. |
| `NEEDS-REVALIDATION` | Previously validated, but something that matters changed (procedure text, release, dependency, backend, upstream behaviour). The old evidence is kept and marked stale. | The old evidence plus the reason it may no longer hold. |

A *representative laboratory* runs real OpenStack services with the same
deployment method, release and backends the claim is about, with enough
nodes to exercise the behaviour (for example, a three-node RabbitMQ or Galera
cluster for a partition or quorum procedure). A single-node lab is
representative for single-node behaviour only. Nested virtualization, small
scale and synthetic load are recorded as limitations, not hidden.

Who executed a lab run is recorded. A run by an automated agent on a real lab
is a lab execution; whether a human operator independently checked it is
recorded separately (`independent_human_check`), because it strengthens the
evidence without changing the status.

## 3. What is in scope, and what is not

The **declared knowledge scope** for technical validation is every item that
an operator could act on or that materially changes an operational decision,
in every published skill (`skills/*/SKILL.md` and `skills/*/references/*.md`):

- diagnostic procedures and the meaning given to their output;
- remediation, recovery and maintenance procedures;
- statements about how OpenStack, its dependencies or Kolla-Ansible behave
  (defaults, failure behaviour, what a command restarts or deletes);
- configuration facts used to decide something.

These items must have an entry in the inventory and a status tag in the skill
text (section 6).

**Outside** the technical-validation scope, stated so it cannot be used to
hide unverified procedures:

| Excluded material | Why | How its quality is checked instead |
|---|---|---|
| Reasoning methods and frameworks (evidence classes, decision gates, weighted model, control spectrum, review checklists, output formats) | They structure a decision; there is nothing to execute against a platform. | Behavioural evaluations (`evals/`), reviewed by operators. |
| The book's principles and the author's positions | Recommendations, not facts. Tagged `[Book: ...]`. | Fidelity to the book (`docs/knowledge-map.md`). |
| Worked examples and illustrative values | Illustrations, not instructions. Marked as examples where they appear. | Behavioural evaluations. |
| `weighted_score.py` arithmetic | Software, not OpenStack behaviour. | Unit test `tools/test_weighted_score.py`. |

An executable command or behavioural claim does not leave the scope because
it appears inside a framework or an example. If in doubt, it is in scope.

## 4. Acceptable evidence

Acceptable, for a validated status:

- the record of a lab execution in this repository or in a source repository
  (for example an OzarLand page's `confirmed_by` entry with its *Lab
  observations* and *Validity and limits* sections, and the pull request that
  added them);
- sanitized command output, logs or timings from that execution;
- a test report, issue or pull request documenting the execution;
- a production experience documented with enough detail for a reviewer to
  understand what was run, where, when and with which result.

Not acceptable as evidence of validity:

- documentation, release notes, source code or a book, read but not executed;
- the existence of a procedure in a runbook repository, OzarLand included;
- an AI-generated explanation, however plausible;
- passing `tools/validate_skills.py`, `tools/validate_knowledge.py` or CI;
- passing behavioural evaluations (they show the assistant reasons well, not
  that a command works);
- "we have always done it this way" without a documented execution.

A production statement without enough detail (no release, no description of
what was run, no outcome) is recorded as supporting information in
`production_reports`, and does not by itself make an item
`PRODUCTION-VALIDATED`.

A lab run described in a source page's text, without a named executor
(no `confirmed_by` record, no provenance naming who ran it), is reported
evidence: the item stays unverified and the run is summarised under
`limitations`, so its findings, especially failures, still reach the
operator as warnings. When a source's `confirmed_by` record and its own text
disagree about what was run, the narrower account is used.

Never put in evidence: credentials, tokens, real hostnames or addresses,
customer or person names, unredacted logs.

## 5. Recording a validation

Each item has one entry in `validation/inventory.yaml`. A blank example is in
[templates/validation-record.yaml](templates/validation-record.yaml).

| Field | Required | Content |
|---|---|---|
| `id` | always | Unique, `<AREA>-<TOPIC>-<NN>`, e.g. `VM-NET-03`. Never reused. |
| `claim` | always | The procedure or behaviour, in one or two sentences. |
| `kind` | always | `procedure`, `diagnostic`, `behaviour` or `config-fact`. |
| `risk` | always | Highest risk of the steps covered: `read-only`, `state-changing`, `destructive`. |
| `skill`, `location` | always | Where the item lives (`skills/<skill>/<file>`). |
| `status` | always | One of the five statuses. |
| `scope` | always | Release, deployment method, network and storage backends the claim is written for (`any` only if the text truly applies to any). |
| `sources` | always | Where the knowledge comes from: repository, path and commit, upstream document, or book chapter. |
| `validation` | for `*-VALIDATED` and `NEEDS-REVALIDATION` | `environment`, `openstack_release`, `deployment`, `network_backend`, `storage_backend`, `executed_by`, `date`, `observed` (what was run and seen), `not_observed` (steps of the claim that were not run), `evidence` (links), `independent_human_check`. |
| `missing_evidence` | for unverified statuses | The test that would validate the item, and its prerequisites. |
| `limitations` | when relevant | Known limits beyond `not_observed`. |
| `production_reports` | optional | Production observations too thin to validate. |
| `revalidate_when` | for validated items | The changes that invalidate the evidence. |

If a lab run covered only part of a procedure, either split the item (the
covered part `LAB-VALIDATED`, the rest unverified) or keep one item with the
uncovered steps in `not_observed` **and** marked in the skill text. Splitting
is preferred when the uncovered part is state-changing or destructive.

## 6. How skills show validation status

Skills must be uploadable on their own, so the status travels inside the
skill text as a tag next to the procedure or claim:

```text
[LAB-VALIDATED: VM-NET-03]
[DOCUMENTED-UNVERIFIED: KA-OPS-04]
```

Conventions:

- A tag applies to the procedure or claim it follows or heads; a heading tag
  applies to the whole subsection unless a step carries its own tag.
- A `LAB-VALIDATED` tag is followed, in the same paragraph or bullet, by its
  scope ("lab: 2026.1, Kolla-Ansible, ML2/OVS") and the important steps not
  run, so the assistant can say what the evidence covers.
- Untagged technical text in a reference file that carries tags is
  unverified. The shared safety rules (rule 12) tell the assistant to present
  the status when it recommends a procedure and never to present an
  unverified procedure as tested.
- Provenance tags stay as they are: `[Book: Ch. N]` for the book,
  `[Addition]` for everything else. Provenance says where a statement comes
  from; the validation tag says whether it was executed.

## 7. Revalidation

Set `NEEDS-REVALIDATION` (keeping the old evidence) when:

- the procedure text changes in a way that affects what is executed;
- the claim is extended to a release, deployment method or backend that the
  evidence did not cover (or split the item instead);
- an upstream change touches the behaviour (release notes, deprecations,
  default changes, RabbitMQ or MariaDB major versions, microversion
  behaviour);
- someone reports that it failed (issue *Validation evidence or failure*);
- the source page it was taken from is corrected after a failed run.

Each validated item lists its own `revalidate_when`. Anyone can request a
revalidation with the issue template; a maintainer sets the status.

## 8. Contributing knowledge and evidence

New or changed operational knowledge comes with, where applicable:

1. the problem or behaviour;
2. the procedure and its prerequisites;
3. the environment it was tested in (release, deployment method, network and
   storage backends, topology, versions of RabbitMQ, MariaDB, libvirt);
4. the test steps;
5. the observed results (sanitized);
6. known limitations and the steps not tested;
7. risks and side effects;
8. links to supporting evidence.

Knowledge without a test is welcome: it enters as `DOCUMENTED-UNVERIFIED`
(from a source) or `PROPOSED-UNVERIFIED` (new), with `missing_evidence`
saying what test would validate it. Evidence for an existing item, or a
report that it failed, goes through the
[*Validation evidence or failure*](https://github.com/soufian-zaouam/openstack-operator-skills/issues/new?template=validation-evidence.yml)
issue form. See also [CONTRIBUTING.md](../CONTRIBUTING.md).

## 9. Review and approval

The repository has one maintainer role. A maintainer may set a validated
status only after reading the evidence and checking that:

- the evidence describes an execution, not a reading;
- the environment is representative for the claim as written;
- `observed` matches what the skill text claims, and `not_observed` is
  reflected in the skill text;
- nothing confidential is exposed.

A maintainer cannot validate their own unrecorded experience: it has to be
written down to the same standard as anyone else's. When the person who ran
the test is also the maintainer approving it, `independent_human_check`
stays `false` until someone else reproduces it.

## 10. Automated checks, and what they do not prove

`python3 tools/validate_knowledge.py` (run in CI) checks repository
consistency only:

- every inventory entry is well formed, uses an approved status, and has the
  fields its status requires (evidence for validated items, missing evidence
  for unverified ones);
- every tag in a skill points to an existing entry with the same status, and
  every entry is tagged at its declared location;
- the coverage figures in `README.md` and `docs/validation-coverage.md` match
  the inventory;
- no skill or top-level document claims repository-wide validation while
  any item in scope is not validated.

**A green CI run says the bookkeeping is consistent. It never says an
OpenStack procedure works.**

## 11. Repository-wide validation claims

The README may state that the operational knowledge base is validated only
when every inventory item is `PRODUCTION-VALIDATED` or `LAB-VALIDATED`, and it
must then say which releases, deployment methods and backends the evidence
covers. Until then it states that the knowledge base is undergoing
validation and links the coverage report. The validator enforces both
directions.
