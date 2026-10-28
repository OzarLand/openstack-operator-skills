# Procedure block template (for a skill's reference file)

Use this shape for each symptom or procedure added to a `references/` file.
Keep it short: the skill must reason from it, not read a manual. Rules:
[knowledge-validation-policy.md](../knowledge-validation-policy.md), section 6.

```markdown
## <Symptom as the operator sees it>

[<STATUS>: <ID>] <scope of the evidence: release, deployment method, backends;
the important steps that were not run>. [Addition] (or [Book: Ch. N])

**Recognize.** Exact states, fields and messages that identify it.

**Read-only checks.**
- `command` (where it runs) — what each result means.

**Tell the causes apart.**
| Observation | Points to |
|---|---|

**Fix options** (least invasive first).
1. <Cause>: what to do. *State-changing* | *Destructive*: what is affected or
   lost, preconditions, undo. If this step has its own evidence, give it its
   own tag: [DOCUMENTED-UNVERIFIED: <ID>].

**Verify.** What every layer must show afterwards.

**Do not.** The tempting move that makes it worse.
```

Then add one inventory entry per tag in `validation/inventory.yaml`
(template: [validation-record.yaml](validation-record.yaml)) and run
`python3 tools/validate_knowledge.py --write`.
