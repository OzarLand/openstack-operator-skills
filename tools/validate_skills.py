#!/usr/bin/env python3
"""Structural validation of the skills and evaluation scenarios.

Checks only what can be checked without running a model. Behavioural quality
is evaluated separately (see evals/README.md).

    python3 tools/validate_skills.py
"""

import json
import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover
    print("PyYAML is required: pip install pyyaml", file=sys.stderr)
    sys.exit(2)

ROOT = Path(__file__).resolve().parent.parent
SKILLS = ROOT / "skills"
SHARED = ROOT / "shared"
SCENARIOS = ROOT / "evals" / "scenarios"
# Top-level documentation whose relative links must keep resolving.
REPO_DOCS = ["README.md", "CONTRIBUTING.md", "CHANGELOG.md", "evals/README.md", "docs/*.md"]

# Keys accepted by claude.ai and the Skills API (Claude Code accepts more, but
# using only these keeps every skill portable across surfaces).
PORTABLE_KEYS = {"name", "description", "license", "compatibility", "metadata", "allowed-tools"}
# Repository policy: these skills give advice and must not pre-approve tools.
FORBIDDEN_KEYS = {"allowed-tools"}
RESERVED_WORDS = ("anthropic", "claude")
NAME_MAX = 64
DESCRIPTION_MAX = 1024
BODY_MAX_LINES = 500
TOC_THRESHOLD = 100  # reference files longer than this need a table of contents
MIN_SCENARIOS = 3

# What exists in the book (v1.2), for citation checking.
BOOK_CHAPTERS = set(range(1, 21))
BOOK_APPENDICES = set("ABCDEF")
BOOK_FIGURES = {"1.1", "4.1", "5.1", "14.1", "20.1"}
BOOK_OTHER = {"Intro", "Concl.", "How to Read", "References"}

SCENARIO_FIELDS = {
    "id": str,
    "title": str,
    "source": str,
    "prompt": str,
    "available_evidence": list,
    "missing_information": list,
    "expected_reasoning": list,
    "expected_output": list,
    "critical_errors": list,
    "criteria": list,
}

LINK_RE = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")
CITATION_RE = re.compile(r"\[Book: ([^\]]+)\]")


class Report:
    def __init__(self):
        self.errors = []
        self.warnings = []

    def error(self, where, msg):
        self.errors.append(f"ERROR   {where}: {msg}")

    def warn(self, where, msg):
        self.warnings.append(f"WARNING {where}: {msg}")


def rel(path):
    return path.relative_to(ROOT).as_posix()


def split_frontmatter(text):
    match = re.match(r"^---\n(.*?)\n---\n?(.*)$", text, re.DOTALL)
    if not match:
        return None, text
    return match.group(1), match.group(2)


def check_frontmatter(skill_dir, fm_text, report):
    where = rel(skill_dir / "SKILL.md")
    try:
        fm = yaml.safe_load(fm_text)
    except yaml.YAMLError as exc:
        report.error(where, f"invalid YAML frontmatter: {exc}")
        return
    if not isinstance(fm, dict):
        report.error(where, "frontmatter must be a mapping")
        return

    for key in sorted(set(fm) - PORTABLE_KEYS):
        report.error(where, f"non-portable frontmatter key '{key}'")
    for key in sorted(set(fm) & FORBIDDEN_KEYS):
        report.error(where, f"frontmatter key '{key}' is not allowed by repository policy")

    name = fm.get("name")
    if not isinstance(name, str) or not name.strip():
        report.error(where, "missing 'name'")
    else:
        if not re.fullmatch(r"[a-z0-9-]+", name):
            report.error(where, f"name '{name}' must use lowercase letters, digits and hyphens")
        if name.startswith("-") or name.endswith("-") or "--" in name:
            report.error(where, f"name '{name}' has leading, trailing or consecutive hyphens")
        if len(name) > NAME_MAX:
            report.error(where, f"name is {len(name)} characters (max {NAME_MAX})")
        for word in RESERVED_WORDS:
            if word in name:
                report.error(where, f"name contains reserved word '{word}'")
        if name != skill_dir.name:
            report.error(where, f"name '{name}' does not match directory '{skill_dir.name}'")

    desc = fm.get("description")
    if not isinstance(desc, str) or not desc.strip():
        report.error(where, "missing 'description'")
    else:
        if len(desc) > DESCRIPTION_MAX:
            report.error(where, f"description is {len(desc)} characters (max {DESCRIPTION_MAX})")
        if "<" in desc or ">" in desc:
            report.error(where, "description contains angle brackets")
        if re.match(r"^(I|You|We)\b", desc.strip()):
            report.error(where, "description should be written in the third person")
        if "use when" not in desc.lower():
            report.warn(where, "description does not state when to use the skill ('Use when ...')")


def check_links(path, text, skill_dir, report, allow_md_links):
    for target in LINK_RE.findall(text):
        if re.match(r"^[a-z]+://", target) or target.startswith("#") or target.startswith("mailto:"):
            continue
        if "\\" in target:
            report.error(rel(path), f"Windows-style path in link '{target}'")
        target_path = (path.parent / target.split("#")[0]).resolve()
        try:
            target_path.relative_to(skill_dir.resolve())
        except ValueError:
            report.error(rel(path), f"link '{target}' points outside the skill directory")
            continue
        if not target_path.exists():
            report.error(rel(path), f"broken link '{target}'")
        elif not allow_md_links and target_path.suffix == ".md":
            report.error(rel(path), f"nested reference '{target}' (keep references one level deep)")


def check_citations(path, text, report):
    for body in CITATION_RE.findall(text):
        body = body.split(",")[0] if "author" in body else body
        for part in re.split(r";|,| and | & ", body):
            part = part.strip()
            if not part or "author" in part:
                continue
            m = re.fullmatch(r"Ch\. (\d+)", part)
            if m:
                if int(m.group(1)) not in BOOK_CHAPTERS:
                    report.error(rel(path), f"citation to non-existent chapter '{part}'")
                continue
            m = re.fullmatch(r"App\. ([A-Z])", part)
            if m:
                if m.group(1) not in BOOK_APPENDICES:
                    report.error(rel(path), f"citation to non-existent appendix '{part}'")
                continue
            m = re.fullmatch(r"Fig\. (\d+\.\d+)", part)
            if m:
                if m.group(1) not in BOOK_FIGURES:
                    report.error(rel(path), f"citation to non-existent figure '{part}'")
                continue
            if re.fullmatch(r"\d+", part):  # "Ch. 9, 10" style continuation
                if int(part) not in BOOK_CHAPTERS:
                    report.error(rel(path), f"citation to non-existent chapter '{part}'")
                continue
            if part in BOOK_OTHER or part.endswith("technical note") or part.endswith("field"):
                continue
            report.warn(rel(path), f"unrecognized citation fragment '{part}'")


def check_skill(skill_dir, shared_texts, report):
    skill_md = skill_dir / "SKILL.md"
    text = skill_md.read_text(encoding="utf-8")
    fm_text, body = split_frontmatter(text)
    if fm_text is None:
        report.error(rel(skill_md), "missing YAML frontmatter")
        return
    check_frontmatter(skill_dir, fm_text, report)

    lines = body.count("\n") + 1
    if lines >= BODY_MAX_LINES:
        report.error(rel(skill_md), f"body is {lines} lines (keep under {BODY_MAX_LINES})")

    for heading in ("## Limits and safety", "## Output format"):
        if heading.lower() not in body.lower():
            report.error(rel(skill_md), f"missing section '{heading}'")

    check_links(skill_md, body, skill_dir, report, allow_md_links=True)
    check_citations(skill_md, body, report)

    linked = {(skill_dir / t.split("#")[0]).resolve() for t in LINK_RE.findall(body)}
    refs_dir = skill_dir / "references"
    for ref in sorted(refs_dir.glob("*.md")) if refs_dir.exists() else []:
        ref_text = ref.read_text(encoding="utf-8")
        if ref.resolve() not in linked:
            report.error(rel(ref), "reference file is not linked from SKILL.md")
        check_links(ref, ref_text, skill_dir, report, allow_md_links=False)
        check_citations(ref, ref_text, report)
        if ref_text.count("\n") > TOC_THRESHOLD and "## Contents" not in "\n".join(ref_text.splitlines()[:40]):
            report.error(rel(ref), f"longer than {TOC_THRESHOLD} lines without '## Contents' near the top")

    for name, expected in shared_texts.items():
        copy = refs_dir / name
        if not copy.exists():
            report.error(rel(skill_dir), f"missing shared reference references/{name} (run tools/sync_shared.py)")
        elif copy.read_text(encoding="utf-8") != expected:
            report.error(rel(copy), "differs from shared/ (run tools/sync_shared.py)")


def check_repo_docs(report):
    for pattern in REPO_DOCS:
        for path in sorted(ROOT.glob(pattern)):
            text = path.read_text(encoding="utf-8")
            for target in LINK_RE.findall(text):
                if re.match(r"^[a-z]+://", target) or target.startswith(("#", "mailto:")):
                    continue
                target_path = (path.parent / target.split("#")[0]).resolve()
                try:
                    target_path.relative_to(ROOT)
                except ValueError:
                    report.error(rel(path), f"link '{target}' points outside the repository")
                    continue
                if not target_path.exists():
                    report.error(rel(path), f"broken link '{target}'")


def check_scenarios(skill_names, report):
    for name in skill_names:
        path = SCENARIOS / f"{name}.json"
        if not path.exists():
            report.error(rel(SCENARIOS), f"no scenario file for skill '{name}'")
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            report.error(rel(path), f"invalid JSON: {exc}")
            continue
        if data.get("skill") != name:
            report.error(rel(path), f"'skill' must be '{name}'")
        scenarios = data.get("scenarios", [])
        if len(scenarios) < MIN_SCENARIOS:
            report.error(rel(path), f"{len(scenarios)} scenarios (minimum {MIN_SCENARIOS})")
        seen = set()
        for i, sc in enumerate(scenarios):
            where = f"{rel(path)}#{sc.get('id', i)}"
            for field, typ in SCENARIO_FIELDS.items():
                value = sc.get(field)
                if not isinstance(value, typ) or not value:
                    report.error(where, f"field '{field}' missing, empty or not a {typ.__name__}")
            if sc.get("id") in seen:
                report.error(where, "duplicate scenario id")
            seen.add(sc.get("id"))
            check_citations(path, sc.get("source", ""), report)


def main():
    report = Report()
    shared_texts = {p.name: p.read_text(encoding="utf-8") for p in sorted(SHARED.glob("*.md"))}
    skill_dirs = sorted(p for p in SKILLS.iterdir() if p.is_dir())
    if not skill_dirs:
        report.error("skills/", "no skills found")
    for skill_dir in skill_dirs:
        if not (skill_dir / "SKILL.md").exists():
            report.error(rel(skill_dir), "missing SKILL.md")
            continue
        check_skill(skill_dir, shared_texts, report)
    check_scenarios([d.name for d in skill_dirs], report)
    check_repo_docs(report)

    for line in report.warnings + report.errors:
        print(line)
    print(f"\n{len(skill_dirs)} skills checked: {len(report.errors)} errors, {len(report.warnings)} warnings")
    return 1 if report.errors else 0


if __name__ == "__main__":
    sys.exit(main())
