#!/usr/bin/env python3
"""Check the knowledge validation inventory against the skills, and generate
the coverage report.

These checks are about bookkeeping: that every status tag in a skill matches
an inventory entry, that validated entries carry evidence, that the published
coverage figures match the inventory, and that nothing claims more validation
than the inventory records. They never show that an OpenStack procedure works.
See docs/knowledge-validation-policy.md.

    python3 tools/validate_knowledge.py           # check (CI)
    python3 tools/validate_knowledge.py --write   # regenerate coverage in README and docs/
"""

import argparse
import datetime as dt
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover
    print("PyYAML is required: pip install pyyaml", file=sys.stderr)
    sys.exit(2)

ROOT = Path(__file__).resolve().parent.parent
INVENTORY = ROOT / "validation" / "inventory.yaml"
SKILLS = ROOT / "skills"
README = ROOT / "README.md"
COVERAGE = ROOT / "docs" / "validation-coverage.md"
POLICY = "docs/knowledge-validation-policy.md"

STATUSES = (
    "PRODUCTION-VALIDATED",
    "LAB-VALIDATED",
    "DOCUMENTED-UNVERIFIED",
    "PROPOSED-UNVERIFIED",
    "NEEDS-REVALIDATION",
)
VALIDATED = {"PRODUCTION-VALIDATED", "LAB-VALIDATED"}
UNVERIFIED = {"DOCUMENTED-UNVERIFIED", "PROPOSED-UNVERIFIED"}
KINDS = {"procedure", "diagnostic", "behaviour", "config-fact"}
RISKS = {"read-only", "state-changing", "destructive"}
ID_RE = re.compile(r"^[A-Z]{2}-[A-Z0-9]+-\d{2}$")
TAG_RE = re.compile(r"\[(" + "|".join(STATUSES) + r"): ([A-Z]{2}-[A-Z0-9]+-\d{2})\]")
# Anything that looks like a status tag, to catch typos the strict pattern would miss.
LOOSE_TAG_RE = re.compile(r"\[([A-Z]+-[A-Z]+(?:-[A-Z]+)?): ([A-Z0-9-]+)\]")
# Tags inside inline code are examples (e.g. in the safety rules), not status claims.
CODE_SPAN_RE = re.compile(r"`[^`\n]*`")
VALIDATION_FIELDS = ("environment", "openstack_release", "deployment", "network_backend", "storage_backend",
                     "executed_by", "date", "observed", "not_observed", "evidence", "independent_human_check")
# Phrases that would claim repository-wide validation. Allowed only at 100 % coverage.
FULL_CLAIM_RE = re.compile(
    r"(knowledge base|all (?:of the )?(?:procedures|skills|knowledge)|every (?:procedure|skill))"
    r"[^.\n]{0,40}\b(?:is|are|has been|have been)\s+(?:fully |entirely |completely |technically )?"
    r"(?:validated|tested|verified)\b"
    r"|\b(?:fully|entirely|completely) (?:lab[- ]|production[- ])?(?:validated|tested|verified)\b",
    re.IGNORECASE,
)
CLAIM_SCAN = ["README.md", "CONTRIBUTING.md", "docs/*.md", "skills/*/SKILL.md", "skills/*/references/*.md"]
CLAIM_SCAN_EXCLUDE = {POLICY}
UNDERGOING_MARKER = "undergoing validation"
README_START = "<!-- validation-coverage:start -->"
README_END = "<!-- validation-coverage:end -->"


def rel(path):
    return path.relative_to(ROOT).as_posix()


def load_inventory(errors):
    try:
        data = yaml.safe_load(INVENTORY.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        errors.append(f"{rel(INVENTORY)}: cannot load: {exc}")
        return None, []
    if not isinstance(data, dict) or not isinstance(data.get("items"), list):
        errors.append(f"{rel(INVENTORY)}: expected a mapping with an 'items' list")
        return None, []
    return data, data["items"]


def nonempty(value):
    if isinstance(value, str):
        return bool(value.strip())
    return value is not None and value != [] and value != {}


def check_item(item, repos, seen, errors):
    iid = item.get("id", "<no id>")
    where = f"{rel(INVENTORY)}#{iid}"
    if not isinstance(iid, str) or not ID_RE.match(iid):
        errors.append(f"{where}: id must match {ID_RE.pattern}")
    if iid in seen:
        errors.append(f"{where}: duplicate id")
    seen.add(iid)
    for field in ("claim", "kind", "risk", "skill", "location", "status", "scope", "sources"):
        if not nonempty(item.get(field)):
            errors.append(f"{where}: missing '{field}'")
    status = item.get("status")
    if status not in STATUSES:
        errors.append(f"{where}: status '{status}' is not one of {', '.join(STATUSES)}")
    if item.get("kind") not in KINDS:
        errors.append(f"{where}: kind '{item.get('kind')}' is not one of {sorted(KINDS)}")
    if item.get("risk") not in RISKS:
        errors.append(f"{where}: risk '{item.get('risk')}' is not one of {sorted(RISKS)}")

    location = item.get("location")
    skill = item.get("skill")
    if isinstance(location, str) and isinstance(skill, str):
        path = SKILLS / skill / location
        if not path.is_file():
            errors.append(f"{where}: location skills/{skill}/{location} does not exist")

    for src in item.get("sources") or []:
        if not isinstance(src, dict) or not ({"repo", "doc", "book", "note"} & set(src)):
            errors.append(f"{where}: each source needs 'repo' (+ 'path'), 'doc', 'book' or 'note'")
        elif "repo" in src:
            if src["repo"] not in repos:
                errors.append(f"{where}: unknown source repo '{src['repo']}' (declare it under source_repos)")
            if not nonempty(src.get("path")):
                errors.append(f"{where}: repo source needs a 'path'")

    validation = item.get("validation")
    if status in VALIDATED or status == "NEEDS-REVALIDATION":
        if not isinstance(validation, dict):
            errors.append(f"{where}: status {status} requires a 'validation' record")
        else:
            for field in VALIDATION_FIELDS:
                if field not in validation or (field != "independent_human_check" and not nonempty(validation[field])):
                    errors.append(f"{where}: validation.{field} is required for {status}")
            if not isinstance(validation.get("independent_human_check"), bool):
                errors.append(f"{where}: validation.independent_human_check must be true or false")
            date = str(validation.get("date", ""))
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date):
                errors.append(f"{where}: validation.date must be YYYY-MM-DD (use the source's recorded date)")
            elif dt.date.fromisoformat(date) > dt.date.today():
                errors.append(f"{where}: validation.date is in the future")
            evidence = validation.get("evidence")
            if not isinstance(evidence, list) or not evidence:
                errors.append(f"{where}: validation.evidence must be a non-empty list of references")
        if status in VALIDATED and not nonempty(item.get("revalidate_when")):
            errors.append(f"{where}: validated items need 'revalidate_when'")
        if status == "PRODUCTION-VALIDATED" and isinstance(validation, dict):
            if "production" not in str(validation.get("environment", "")).lower():
                errors.append(f"{where}: PRODUCTION-VALIDATED needs a production environment description")
    else:
        if validation:
            errors.append(f"{where}: status {status} must not carry a 'validation' record "
                          "(record partial evidence under 'limitations' or split the item)")
        if not nonempty(item.get("missing_evidence")):
            errors.append(f"{where}: unverified items need 'missing_evidence' (the test that would validate them)")


def scan_tags(errors):
    """Return {id: [(file, status), ...]} for every status tag in the skills."""
    found = defaultdict(list)
    for path in sorted(SKILLS.glob("*/**/*.md")):
        text = CODE_SPAN_RE.sub(lambda m: " " * len(m.group(0)), path.read_text(encoding="utf-8"))
        strict = {(m.start(), m.end()) for m in TAG_RE.finditer(text)}
        for m in LOOSE_TAG_RE.finditer(text):
            if (m.start(), m.end()) not in strict and re.search(r"VALID|VERIF", m.group(1)):
                errors.append(f"{rel(path)}: malformed validation tag '{m.group(0)}'")
        for m in TAG_RE.finditer(text):
            found[m.group(2)].append((rel(path), m.group(1)))
    return found


def check_tags(items, tags, errors):
    by_id = {i.get("id"): i for i in items}
    for iid, uses in sorted(tags.items()):
        item = by_id.get(iid)
        if item is None:
            errors.append(f"{uses[0][0]}: tag refers to unknown inventory id '{iid}'")
            continue
        for path, status in uses:
            if status != item.get("status"):
                errors.append(f"{path}: tag [{status}: {iid}] disagrees with inventory status {item.get('status')}")
    for item in items:
        iid = item.get("id")
        expected = f"skills/{item.get('skill')}/{item.get('location')}"
        if not any(path == expected for path, _ in tags.get(iid, [])):
            errors.append(f"{rel(INVENTORY)}#{iid}: not tagged in its location {expected}")


def coverage_tables(items):
    total = len(items)
    counts = Counter(i.get("status") for i in items)
    validated = sum(counts[s] for s in VALIDATED)
    pct = (100.0 * validated / total) if total else 0.0
    lines = [
        "| Status | Items | Share |",
        "|---|---:|---:|",
    ]
    for status in STATUSES:
        share = (100.0 * counts[status] / total) if total else 0.0
        lines.append(f"| `{status}` | {counts[status]} | {share:.0f} % |")
    lines.append(f"| **Total in scope** | **{total}** | |")
    summary = (f"{validated} of {total} items in scope ({pct:.0f} %) are validated: "
               f"{counts['PRODUCTION-VALIDATED']} in production, {counts['LAB-VALIDATED']} in a lab. "
               f"{total - validated} are not validated yet.")
    per_skill = defaultdict(Counter)
    for i in items:
        per_skill[i.get("skill")][i.get("status")] += 1
    skill_lines = ["| Skill | Production | Lab | Documented, unverified | Proposed, unverified | Needs revalidation |",
                   "|---|---:|---:|---:|---:|---:|"]
    for skill in sorted(per_skill):
        c = per_skill[skill]
        skill_lines.append(f"| `{skill}` | " + " | ".join(str(c[s]) for s in STATUSES) + " |")
    return "\n".join(lines), summary, "\n".join(skill_lines), validated == total and total > 0


def skill_status_table(items):
    """One row per skill directory, including skills with no inventory items."""
    by_skill = defaultdict(list)
    for i in items:
        by_skill[i.get("skill")].append(i)
    lines = ["| Skill | Validation status | Environment | Software version | Evidence | Known limitations |",
             "|---|---|---|---|---|---|"]
    for skill in sorted(p.name for p in SKILLS.iterdir() if (p / "SKILL.md").exists()):
        group = by_skill.get(skill, [])
        if not group:
            lines.append(f"| `{skill}` | No inventory items: a reasoning method from the book | n/a | n/a "
                         "| Behavioural evaluation only (reasoning, not execution) | Commands quoted in its "
                         "examples are untagged, so unverified |")
            continue
        c = Counter(i.get("status") for i in group)
        validated = sum(c[s] for s in VALIDATED)
        if c["PRODUCTION-VALIDATED"]:
            status = "Partially production-validated" if validated < len(group) else "Production-validated"
        elif validated:
            status = "Partially lab-validated" if validated < len(group) else "Lab-validated"
        else:
            status = "Unvalidated"
        status += f": {validated} of {len(group)} items"
        lab = [i.get("validation") or {} for i in group if i.get("status") in VALIDATED]
        if lab:
            tools = sorted({"Kolla-Ansible" if "kolla" in str(v.get("deployment")).lower() else "other"
                            for v in lab})
            env = f"{', '.join(tools)} lab" + ("s" if len(lab) > 1 else "")
            versions = "OpenStack " + ", ".join(sorted({str(v.get("openstack_release")) for v in lab}))
            dates = sorted(str(v.get("date")) for v in lab)
            evidence = f"{len(lab)} lab records, {dates[0]} to {dates[-1]}"
            limits = []
            if not c["PRODUCTION-VALIDATED"]:
                limits.append("no production evidence")
            if not any(v.get("independent_human_check") for v in lab):
                limits.append("runs by an automated lab agent, no independent human check")
            if validated < len(group):
                limits.append(f"{len(group) - validated} items unverified")
            limitations = "; ".join(limits).capitalize()
        else:
            env = versions = "Unknown (no execution recorded)"
            evidence = "None recorded"
            limitations = f"All {len(group)} items unverified"
        cells = [f"`{skill}`", status, env, versions, f"{evidence}; [details](docs/validation-coverage.md)",
                 limitations]
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def render_readme_block(items):
    table, summary, _, _ = coverage_tables(items)
    return f"{README_START}\n{summary}\n\n{table}\n\n{skill_status_table(items)}\n{README_END}"


def render_coverage(items, data):
    table, summary, skill_table, _ = coverage_tables(items)
    out = [
        "# Validation coverage",
        "",
        "Generated by `python3 tools/validate_knowledge.py --write` from",
        "[`validation/inventory.yaml`](../validation/inventory.yaml). Do not edit by hand.",
        "What the statuses mean and what counts as evidence:",
        "[knowledge-validation-policy.md](knowledge-validation-policy.md).",
        "",
        "Structural checks and CI passing are not part of these figures: they show",
        "the inventory is consistent, not that a procedure works.",
        "",
        "## Summary",
        "",
        summary,
        "",
        table,
        "",
        "## By skill",
        "",
        skill_table,
        "",
        "## Sources",
        "",
        "| Source | Revision read |",
        "|---|---|",
    ]
    for key, repo in sorted((data.get("source_repos") or {}).items()):
        out.append(f"| [{repo.get('name', key)}]({repo.get('url')}) | `{repo.get('commit')}` |")
    out += ["", "## Items", ""]
    for status in STATUSES:
        group = [i for i in items if i.get("status") == status]
        if not group:
            continue
        out += [f"### {status} ({len(group)})", "", "| ID | Risk | Claim | Scope | Evidence or missing evidence |",
                "|---|---|---|---|---|"]
        for i in sorted(group, key=lambda x: x.get("id")):
            if status in VALIDATED or status == "NEEDS-REVALIDATION":
                v = i.get("validation") or {}
                ev = f"{v.get('executed_by')}, {v.get('date')}; not observed: {v.get('not_observed')}"
            else:
                ev = i.get("missing_evidence", "")
            cells = [i.get("id"), i.get("risk"), i.get("claim"), i.get("scope"), ev]
            out.append("| " + " | ".join(" ".join(str(c).split()).replace("|", "\\|") for c in cells) + " |")
        out.append("")
    return "\n".join(out).rstrip() + "\n"


def check_claims(items, errors):
    _, _, _, complete = coverage_tables(items)
    if complete:
        return
    for pattern in CLAIM_SCAN:
        for path in sorted(ROOT.glob(pattern)):
            if rel(path) in CLAIM_SCAN_EXCLUDE:
                continue
            for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                m = FULL_CLAIM_RE.search(line)
                if m and not re.search(r"\b(not|never|no|until|only when|unless)\b", line, re.IGNORECASE):
                    errors.append(f"{rel(path)}:{n}: claims repository-wide validation ('{m.group(0)}') "
                                  "while the inventory is not fully validated")
    if UNDERGOING_MARKER not in README.read_text(encoding="utf-8").lower():
        errors.append(f"README.md: must state that the knowledge base is '{UNDERGOING_MARKER}' "
                      "while items in scope are not validated")


def sync_generated(items, data, write, errors):
    readme = README.read_text(encoding="utf-8")
    block = render_readme_block(items)
    pattern = re.compile(re.escape(README_START) + r".*?" + re.escape(README_END), re.DOTALL)
    if not pattern.search(readme):
        errors.append(f"README.md: missing coverage markers {README_START} ... {README_END}")
    else:
        new_readme = pattern.sub(lambda _: block, readme)
        if new_readme != readme:
            if write:
                README.write_text(new_readme, encoding="utf-8")
                print("updated: README.md")
            else:
                errors.append("README.md: validation coverage is stale (run tools/validate_knowledge.py --write)")
    coverage = render_coverage(items, data)
    current = COVERAGE.read_text(encoding="utf-8") if COVERAGE.exists() else ""
    if coverage != current:
        if write:
            COVERAGE.write_text(coverage, encoding="utf-8")
            print(f"updated: {rel(COVERAGE)}")
        else:
            errors.append(f"{rel(COVERAGE)}: stale or missing (run tools/validate_knowledge.py --write)")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--write", action="store_true", help="regenerate the coverage in README.md and docs/")
    args = ap.parse_args()

    errors = []
    data, items = load_inventory(errors)
    if data is not None:
        repos = data.get("source_repos") or {}
        seen = set()
        for item in items:
            check_item(item, repos, seen, errors)
        check_tags(items, scan_tags(errors), errors)
        sync_generated(items, data, args.write, errors)
        check_claims(items, errors)

    for line in errors:
        print(f"ERROR   {line}")
    counts = Counter(i.get("status") for i in items)
    print(f"\n{len(items)} inventory items ({', '.join(f'{s} {counts[s]}' for s in STATUSES)}): {len(errors)} errors")
    print("These checks cover bookkeeping only; they do not show that any procedure works.")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
