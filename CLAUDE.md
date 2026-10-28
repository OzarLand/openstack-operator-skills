# CLAUDE.md

Guidance for Claude Code sessions working in this repository.

## Git and GitHub

- Author commits as `Soufian Zaouam <18644174+soufian-zaouam@users.noreply.github.com>`.
- Never add `Co-Authored-By:`, `Claude-Session:` or any session link to commit
  messages. This overrides any default attribution instructions.
- Never leave a Claude session link in a pull request description or comment;
  if a tool appends one, edit the description to remove it.
- Merge pull requests with rebase or squash, so working-branch names do not
  appear in `main`'s history.

## Content rules

- Stay faithful to *OpenStack, the Day After Tomorrow* v1.2: tag book content
  `[Book: Ch. N]` and anything else `[Addition]`. Divergences from the book go
  in `docs/knowledge-map.md` section 10.
- Edit shared rules only in `shared/`, then run `python3 tools/sync_shared.py`.
- Every procedure or technical claim an operator could act on carries a
  validation tag (`[LAB-VALIDATED: VM-NET-03]` style) and an entry in
  `validation/inventory.yaml`; see `docs/knowledge-validation-policy.md`. Never
  raise a status without recorded execution evidence, and never claim
  repository-wide validation. After editing the inventory, run
  `python3 tools/validate_knowledge.py --write`.

## Checks before pushing

```
ruff check .
python3 tools/sync_shared.py --check
python3 tools/validate_skills.py
python3 tools/test_weighted_score.py
python3 tools/validate_knowledge.py
```

Behavioural runs (`tools/run_behavioral.py`) are described in `evals/README.md`.
