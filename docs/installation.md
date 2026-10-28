# Installation

Custom skills do not sync between surfaces: install them separately in each
place you use Claude. Source: Anthropic, *Agent Skills overview* (Oct 2026).

## Claude Code

### Option A — plugin marketplace

```text
/plugin marketplace add soufian-zaouam/openstack-operator-skills
/plugin install openstack-operations@openstack-operator-skills
```

Plugin skills are namespaced, e.g. `/openstack-operations:openstack-incident-analysis`.
The manifest (`.claude-plugin/marketplace.json`) passes
`claude plugin validate --strict`, and the install above was tested end to end
from GitHub in 0.1.0 (all seven skills of that version installed; the incident skill triggered on a
test prompt).

Plugin skills live outside your project (in the plugin cache under
`~/.claude/plugins/`), so the first time a skill opens its `references/`
files Claude Code asks for permission to read them. Allow it: without the
references a skill falls back to its `SKILL.md` alone and says so. In
non-interactive runs (`claude -p`), nobody can answer the prompt, so allow
reads in advance, e.g. `claude -p --allowedTools Read "..."`. Copied skills
(Option B) inside a project do not need this.

### Option B — copy the skills

```bash
git clone https://github.com/soufian-zaouam/openstack-operator-skills
# personal, all projects:
cp -r openstack-operator-skills/skills/* ~/.claude/skills/
# or for one repository (commit them to share with the team):
mkdir -p .claude/skills && cp -r openstack-operator-skills/skills/* .claude/skills/
```

Install all nine if you can: they hand off to each other. Each one also works
alone.

## claude.ai

Requires a plan with code execution enabled. Custom skills are per user.

```bash
python3 tools/package_skills.py     # writes dist/<skill>.zip
```

Upload each zip in Settings (Capabilities / Features → Skills). Each zip
contains one skill folder with its `SKILL.md` and `references/`.

Tested on 2026-10-25 (see `docs/evaluation-report.md`, section 11): all seven
zips uploaded without error, and the right skill loaded on each test question.
claude.ai mounts the skills under `/mnt/skills/plugins/<name>/` and Claude
reads the `references/` files with shell commands (`cat`, `sed`), so code
execution must stay enabled. Long outputs such as a runbook may be delivered
as a document rather than in the chat.

## Claude API

Upload each skill directory with the Skills API (`/v1/skills`) and reference
the returned `skill_id` in the `container` parameter together with the code
execution tool. The API container has no network access; these skills do not
need it.

## Updating

- Plugin: `/plugin update openstack-operations@openstack-operator-skills`.
- Copied skills: pull the repository and copy again.
- claude.ai / API: upload the new zip or a new skill version.

## Verifying an installation

Ask Claude something only the skill would structure, for example:
"A compute host shows nova-compute down; should we evacuate its VMs now?"
With the skill active, the answer should insist on fencing the host before
any evacuation and separate observed facts from hypotheses. In Claude Code,
`/skills` (or the `/` menu) lists the installed skills.

## Security

Skills are instructions that influence what Claude does. Review the files
before installing, as you would any software. These skills contain one
optional Python script (`weighted_score.py`, arithmetic only, no network or
file writes) and no other code.
