The one-liner as written won't do what you want, and a few details matter before you schedule it.

**Problems with the one-liner**
- **No age filter.** It deletes every ERROR instance, including ones that failed a minute ago while a user or Heat/Terraform is still looking at the fault.
- **Empty input.** GNU `xargs` runs the command once with no argument when the list is empty. Use `xargs -r`.
- **No way to filter by age in the CLI.** `--changes-before` filters on `updated_at`, not `created_at`, so you need to filter the output yourself.

**Which timestamp to use**
- `created_at` is the wrong choice. A VM created months ago that hit ERROR an hour ago (failed resize, failed migration, host crash) would be deleted immediately.
- `updated_at` approximates "has been in ERROR for 24h", since the state change bumps it. That's the better proxy.
- Some instances in ERROR are still running on a hypervisor, or have volumes attached. Deleting them destroys `delete_on_termination` volumes and the `fault` info people need for debugging. I'd make the cutoff longer than 24h, or at least log the fault message and project before each delete.

**Safeguards I'd add**
- Run it in dry-run mode for a week first, writing a report of what would be deleted.
- Cap deletions per run (say 50). If the count jumps, it's probably a real outage, such as a bad compute host, a Ceph problem, or an image issue. Abort and alert instead of wiping the evidence.
- Add an opt-out, such as a metadata key or tag (`keep-error=true`) that the job skips.
- Log ID, project, name, `created_at`, `updated_at` and fault to a file or syslog.
- Use a dedicated service account with only the `delete` rights it needs, rather than full admin creds.

**Sketch**
```bash
#!/usr/bin/env bash
set -euo pipefail
CUTOFF=$(date -u -d '24 hours ago' +%Y-%m-%dT%H:%M:%SZ)
MAX=50
DRY_RUN=${DRY_RUN:-1}

ids=$(openstack server list --all-projects --status ERROR -f json \
        -c ID -c Name -c Project -c Updated \
      | jq -r --arg c "$CUTOFF" '.[] | select(.Updated < $c) | .ID')

n=$(grep -c . <<<"$ids" || true)
(( n > MAX )) && { echo "refusing: $n > $MAX" >&2; exit 1; }

for id in $ids; do
  logger -t error-reaper "$(openstack server show "$id" -f value -c project_id -c fault | tr '\n' ' ') id=$id"
  [[ $DRY_RUN == 1 ]] || openstack server delete "$id"
done
```
Check the column names and timestamp format (`Updated` may not appear in `server list` output on every client version) against your client. If it doesn't, use `server show` per ID, or call the API directly with `changes-before`.

**Alternative for the capacity-report problem**
If the main issue is the reports, filter ERROR instances out of the reports. They don't consume hypervisor resources in most cases, since failed builds don't hold a placement allocation. They only count against quota. Cleaning up still makes sense for quota, but you may not need to be aggressive.

I can turn this into a tested script with a systemd timer or cron entry if you want.