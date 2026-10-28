# Contributing

Contributions from people who operate OpenStack are welcome. The most useful
ones come from production experience.

The quickest way in is an issue:
[unsafe or wrong advice](https://github.com/OzarLand/openstack-operator-skills/issues/new?template=unsafe-or-wrong-advice.yml)
or
[improvement or correction](https://github.com/OzarLand/openstack-operator-skills/issues/new?template=improvement.yml).
No code needed.

Advice that could cause harm before it is fixed, or a secret found in the
repository, goes privately through the [security policy](SECURITY.md).
Everyone taking part follows the OzarLand [code of conduct](CODE_OF_CONDUCT.md).

## Good contributions

- **A failing scenario.** A realistic request where a skill gave unsafe,
  wrong or unhelpful advice. Add it to `evals/scenarios/<skill>.json` with the
  expected reasoning and the critical errors to avoid, even before a fix.
- **A missing decision point** in a workflow (two situations that look alike
  but need different handling).
- **An aged technical note.** Release behaviour changes; corrections with a
  link to upstream or vendor documentation are valuable.
- **Backend or tool coverage** (OVN vs ML2/OVS, Ceph, specific deployment
  tools), kept in reference files and clearly scoped.
- **Validation evidence.** You ran a procedure from a skill on a lab or in
  production, it worked, failed or worked only partly: report it with the
  [*Validation evidence or failure*](https://github.com/OzarLand/openstack-operator-skills/issues/new?template=validation-evidence.yml)
  form. This is how items move from *unverified* to *validated*.

## Where new knowledge belongs

| You have | It goes in |
|---|---|
| A symptom of one instance, volume or port, with checks and a fix | `skills/openstack-vm-troubleshooting/references/<domain>.md` |
| A control-plane failure (RabbitMQ, Galera, HAProxy, Keystone) and its recovery | `skills/openstack-incident-analysis/references/control-plane-recovery.md` |
| A Kolla-Ansible command, configuration file, failed run or host operation | `skills/openstack-kolla-ansible-operations/references/` |
| Host maintenance mechanics | `skills/openstack-maintenance-planning/references/host-maintenance-mechanics.md` |
| A decision point or reasoning step | the relevant `SKILL.md` |
| A full runbook | upstream first, in [OzarLand openstack-vm-runbooks](https://github.com/OzarLand/openstack-vm-runbooks) or [kolla-ansible-deployment-patterns](https://github.com/OzarLand/kolla-ansible-deployment-patterns); the skill then carries the distilled checks and decisions and links the source in the inventory |

Version-specific behaviour is written with its scope ("since 2024.1", "with
Kolla-Ansible", "ML2/OVS only"), never as a universal fact. Use the
[procedure block template](docs/templates/procedure-block.md).

## Validation of operational knowledge

Read [docs/knowledge-validation-policy.md](docs/knowledge-validation-policy.md).
In short:

1. Every procedure or technical claim an operator could act on gets a status
   tag in the skill text, such as `[LAB-VALIDATED: VM-NET-04]`, and one entry
   in `validation/inventory.yaml`
   ([template](docs/templates/validation-record.yaml)).
2. A validated status needs a recorded execution: environment, release,
   deployment method, backends, date, steps run, observed result, steps not
   run. Reading documentation or a runbook is not validation.
3. If you could not test it, submit it anyway as `DOCUMENTED-UNVERIFIED` or
   `PROPOSED-UNVERIFIED`, saying in `missing_evidence` what test would
   validate it.
4. A change to a validated procedure's steps, or to its release scope, sets it
   to `NEEDS-REVALIDATION` until it is run again.
5. Never put credentials, real hostnames, addresses or customer details in
   evidence.

To report outdated or wrong instructions, use the
[unsafe or wrong advice](https://github.com/OzarLand/openstack-operator-skills/issues/new?template=unsafe-or-wrong-advice.yml)
form; to ask for a revalidation, the validation form above.

## Ground rules

1. **Separate sources.** Tag statements from the book `[Book: Ch. N]`. Tag
   anything else `[Addition]`. Do not attribute new ideas to the book.
2. **No universal rules for contextual decisions.** Give options with the
   conditions under which each applies.
3. **Validation status is required.** Status tags and inventory entries
   for every operational claim; see above.
4. **Safety rules are not optional.** Read-only first; state-changing steps
   carry prerequisites, blast radius, verification, stop conditions, recovery
   and an approver; no claimed outcomes; no invented facts. See
   `shared/evidence-and-safety.md`.
5. **Keep `SKILL.md` lean** (well under 500 lines). Put detail in
   `references/`, linked directly from `SKILL.md` (one level deep). Reference
   files over 100 lines start with a `## Contents` section.
6. **Edit shared text in `shared/` only**, then run `python3 tools/sync_shared.py`.
7. **Portable frontmatter only**: `name`, `description`, `license`, `metadata`.
   Descriptions are third person, under 1024 characters, no angle brackets,
   and say both what the skill does and when to use it.
8. **No vendor promotion**, no customer or employer details in scenarios.

## Before opening a pull request

```bash
python3 tools/sync_shared.py
python3 tools/validate_skills.py         # must report 0 errors
python3 tools/test_weighted_score.py
python3 tools/validate_knowledge.py      # inventory, tags and coverage consistent
python3 tools/test_validate_knowledge.py
ruff check .                             # configuration in ruff.toml
```

If you change a skill's behaviour, run its scenarios when you can:

```bash
python3 tools/run_behavioral.py --skill <name> --modes skill baseline
```

This needs an authenticated `claude` CLI and costs API usage. Include the
summary (scores, triggered or not, critical errors) in the PR description, and
say which model you used. Do not claim results you did not run.

Neither these checks nor behavioural evaluations validate an OpenStack
procedure; only a recorded execution does.

## Proposing a new skill

Open an issue first describing the operational problem, the evidence that it
is distinct from existing skills, and three scenarios. The design rationale in
`docs/design.md` explains why the current set is what it is.

## Licence

By contributing you agree that your contribution is licensed under the
Apache License 2.0 of this repository.
