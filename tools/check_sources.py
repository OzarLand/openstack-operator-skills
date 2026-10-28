#!/usr/bin/env python3
"""Report drift between the inventory and the OzarLand source pages it cites.

Given local checkouts of the source repositories, reads the front matter
`status:` of every page cited in validation/inventory.yaml and reports:

- pages that no longer exist (moved, renamed or deleted);
- pages without a readable `status:`;
- LAB-VALIDATED items citing a page whose status is `draft`, and whether the
  skill text discloses it next to the tag (docs/knowledge-validation-policy.md,
  section 4).

It reads the source repositories only; it changes nothing. It is not part of
CI because it needs the checkouts. Run it before a release or after the
source repositories change:

    python3 tools/check_sources.py --repo openstack-vm-runbooks=../openstack-vm-runbooks \\
        --repo kolla-ansible-deployment-patterns=../kolla-ansible-deployment-patterns [--ref origin/main]

Without --repo, each source repository is looked for next to this one, under
its own name. With --ref, pages are read at that git ref instead of the
working tree. Exit code 1 when a page is missing or a draft is undisclosed.
"""

import argparse
import re
import subprocess
import sys
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover
    print("PyYAML is required: pip install pyyaml", file=sys.stderr)
    sys.exit(2)

ROOT = Path(__file__).resolve().parent.parent
INVENTORY = ROOT / "validation" / "inventory.yaml"
SKILLS = ROOT / "skills"
STATUS_RE = re.compile(r"\A---\n.*?^status:\s*['\"]?([\w-]+)", re.DOTALL | re.MULTILINE)


def read_page(checkout, path, ref):
    """Return the page text, or None when it does not exist."""
    if ref:
        result = subprocess.run(["git", "-C", str(checkout), "show", f"{ref}:{path}"],
                                capture_output=True, text=True, check=False)
        return result.stdout if result.returncode == 0 else None
    file = checkout / path
    return file.read_text(encoding="utf-8") if file.is_file() else None


def tag_paragraphs(item_id, skill_texts):
    """Paragraphs of any skill file that carry the item's LAB-VALIDATED tag."""
    tag = f"[LAB-VALIDATED: {item_id}]"
    return [p for text in skill_texts for p in re.split(r"\n\s*\n", text) if tag in p]


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--repo", action="append", default=[], metavar="NAME=PATH",
                        help="local checkout of a source repository (repeatable)")
    parser.add_argument("--ref", help="git ref to read pages at, e.g. origin/main (default: working tree)")
    args = parser.parse_args()

    inventory = yaml.safe_load(INVENTORY.read_text(encoding="utf-8"))
    checkouts = {name: ROOT.parent / name for name in inventory.get("source_repos", {})}
    for entry in args.repo:
        name, _, path = entry.partition("=")
        checkouts[name] = Path(path).expanduser().resolve()
    for name, path in checkouts.items():
        if not path.is_dir():
            print(f"error: no checkout of {name} at {path} (use --repo {name}=PATH)", file=sys.stderr)
            return 2

    skill_texts = [f.read_text(encoding="utf-8") for f in sorted(SKILLS.rglob("*.md"))]
    statuses = {}
    missing, unreadable, disclosed, undisclosed = [], [], [], []
    for item in inventory["items"]:
        for source in item.get("sources", []):
            if "repo" not in source:
                continue
            key = (source["repo"], source["path"])
            if key not in statuses:
                text = read_page(checkouts[source["repo"]], source["path"], args.ref)
                match = STATUS_RE.search(text) if text is not None else None
                statuses[key] = None if text is None else (match.group(1) if match else "")
            status = statuses[key]
            where = f"{item['id']}: {source['repo']} {source['path']}"
            if status is None:
                missing.append(where)
            elif status == "":
                unreadable.append(where)
            elif status == "draft" and item["status"] == "LAB-VALIDATED":
                paragraphs = tag_paragraphs(item["id"], skill_texts)
                ok = paragraphs and all("draft" in p.lower() for p in paragraphs)
                (disclosed if ok else undisclosed).append(where)

    for title, rows in (("Missing source pages", missing), ("Source pages without a status", unreadable),
                        ("LAB-VALIDATED on a draft page, not disclosed in the skill text", undisclosed)):
        if rows:
            print(f"{title} ({len(rows)}):")
            for row in sorted(set(rows)):
                print(f"  {row}")
    counts = {}
    for status in statuses.values():
        counts[status or "missing or none"] = counts.get(status or "missing or none", 0) + 1
    summary = ", ".join(f"{k} {v}" for k, v in sorted(counts.items()))
    print(f"{len(statuses)} source pages read ({summary}); {len(disclosed)} LAB-VALIDATED citations of draft "
          f"pages disclosed, {len(undisclosed)} undisclosed, {len(missing)} missing pages")
    return 1 if missing or undisclosed else 0


if __name__ == "__main__":
    sys.exit(main())
