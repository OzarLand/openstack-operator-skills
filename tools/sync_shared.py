#!/usr/bin/env python3
"""Copy the canonical files in shared/ into every skill's references/ directory.

Each skill must be uploadable on its own (claude.ai zip, Skills API), so shared
reference text is duplicated into each skill. Edit shared/*.md, then run:

    python3 tools/sync_shared.py          # write copies
    python3 tools/sync_shared.py --check  # exit 1 if any copy is missing or stale
"""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SHARED = ROOT / "shared"
SKILLS = ROOT / "skills"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="only report drift")
    args = parser.parse_args()

    shared_files = sorted(SHARED.glob("*.md"))
    if not shared_files:
        print(f"no shared files found in {SHARED}", file=sys.stderr)
        return 1

    stale = []
    for skill_dir in sorted(p for p in SKILLS.iterdir() if (p / "SKILL.md").exists()):
        refs = skill_dir / "references"
        for src in shared_files:
            dst = refs / src.name
            expected = src.read_text(encoding="utf-8")
            if dst.exists() and dst.read_text(encoding="utf-8") == expected:
                continue
            stale.append(dst.relative_to(ROOT))
            if not args.check:
                refs.mkdir(exist_ok=True)
                dst.write_text(expected, encoding="utf-8")

    if args.check:
        for path in stale:
            print(f"stale or missing: {path}")
        return 1 if stale else 0

    for path in stale:
        print(f"updated: {path}")
    if not stale:
        print("all shared copies already up to date")
    return 0


if __name__ == "__main__":
    sys.exit(main())
