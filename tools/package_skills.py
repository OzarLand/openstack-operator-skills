#!/usr/bin/env python3
"""Package each skill as a zip for upload to claude.ai or the Skills API.

Each archive contains the skill folder at its root (<name>/SKILL.md, ...).
Run the validator first; packaging refuses to run if validation fails.

    python3 tools/package_skills.py            # all skills -> dist/
    python3 tools/package_skills.py openstack-incident-analysis
"""

import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILLS = ROOT / "skills"
DIST = ROOT / "dist"
EXCLUDE = {"__pycache__", ".DS_Store"}


def main(argv):
    check = subprocess.run([sys.executable, str(ROOT / "tools" / "validate_skills.py")])
    if check.returncode != 0:
        print("validation failed; not packaging", file=sys.stderr)
        return 1
    names = argv or sorted(p.name for p in SKILLS.iterdir() if (p / "SKILL.md").exists())
    DIST.mkdir(exist_ok=True)
    for name in names:
        src = SKILLS / name
        if not (src / "SKILL.md").exists():
            print(f"unknown skill: {name}", file=sys.stderr)
            return 1
        out = DIST / f"{name}.zip"
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
            for path in sorted(src.rglob("*")):
                if path.is_file() and not EXCLUDE.intersection(path.parts):
                    zf.write(path, path.relative_to(SKILLS).as_posix())
        print(f"wrote {out.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
