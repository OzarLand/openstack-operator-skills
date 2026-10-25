# Contributing

Contributions from people who operate OpenStack are welcome. The most useful
ones come from production experience.

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

## Ground rules

1. **Separate sources.** Tag statements from the book `[Book: Ch. N]`. Tag
   anything else `[Addition]`. Do not attribute new ideas to the book.
2. **No universal rules for contextual decisions.** Give options with the
   conditions under which each applies.
3. **Safety rules are not optional.** Read-only first; state-changing steps
   carry prerequisites, blast radius, verification, stop conditions, recovery
   and an approver; no claimed outcomes; no invented facts. See
   `shared/evidence-and-safety.md`.
4. **Keep `SKILL.md` lean** (well under 500 lines). Put detail in
   `references/`, linked directly from `SKILL.md` (one level deep). Reference
   files over 100 lines start with a `## Contents` section.
5. **Edit shared text in `shared/` only**, then run `python3 tools/sync_shared.py`.
6. **Portable frontmatter only**: `name`, `description`, `license`, `metadata`.
   Descriptions are third person, under 1024 characters, no angle brackets,
   and say both what the skill does and when to use it.
7. **No vendor promotion**, no customer or employer details in scenarios.

## Before opening a pull request

```bash
python3 tools/sync_shared.py
python3 tools/validate_skills.py         # must report 0 errors
python3 tools/test_weighted_score.py
ruff check .                             # configuration in ruff.toml
```

If you change a skill's behaviour, run its scenarios when you can:

```bash
python3 tools/run_behavioral.py --skill <name> --modes skill baseline
```

This needs an authenticated `claude` CLI and costs API usage. Include the
summary (scores, triggered or not, critical errors) in the PR description, and
say which model you used. Do not claim results you did not run.

## Proposing a new skill

Open an issue first describing the operational problem, the evidence that it
is distinct from existing skills, and three scenarios. The design rationale in
`docs/design.md` explains why the current set is what it is.

## Licence

By contributing you agree that your contribution is licensed under the
Apache License 2.0 of this repository.
