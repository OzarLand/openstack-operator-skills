The command as written has no age filter. `--status ERROR` matches an instance that failed a minute ago, so you'd delete things people are still debugging. I'd change a few other things too.

**Fixes**
- **Age filter:** use `--changes-before <ISO timestamp>`, which needs compute API ≥ 2.66. It filters on `updated_at`, not `created_at`. That's usually what you want, because an instance stuck in ERROR for 24h hasn't been touched, but any API action on it resets the clock. If you want strict creation age, list with `-c ID -c Created` (client-version dependent) and compare in `jq`.
- **Empty input:** use `xargs -r`, otherwise `server delete` runs with no args and errors.
- **One failure shouldn't stop the run:** the xargs pipe carries on, but you won't see which deletes failed. Loop and log each one instead.

**Safety**
- **Log before deleting:** record ID, project, name, created time and `fault.message`. Once the instance is gone, that's your only record of why it failed.
- **Circuit breaker:** if there are more than N candidates (say 50 or 10% of the fleet), abort and alert. A scheduler, DB or Neutron outage can put hundreds of instances in ERROR, and you'd want a human to look at that rather than reap it silently.
- **Opt-out:** skip instances with a tag or metadata like `keep=true`, so people can park one for debugging.
- **Volumes:** deleting a boot-from-volume instance with `delete_on_termination=true` deletes the volume. Instances that failed during resize or migration can also have data on a hypervisor. Decide whether you're comfortable with that, or whether to exclude instances with attached volumes.
- **Dry run first:** run it in report-only mode for a week or two and look at what it would have deleted before enabling deletes.

**Sketch**
```bash
#!/usr/bin/env bash
set -euo pipefail
export OS_COMPUTE_API_VERSION=2.66   # or --os-compute-api-version
MAX=50
cutoff=$(date -u -d '24 hours ago' +%Y-%m-%dT%H:%M:%SZ)

openstack server list --all-projects --status ERROR \
  --changes-before "$cutoff" -f json -c ID -c Name -c Project > /tmp/candidates.json

n=$(jq length /tmp/candidates.json)
[ "$n" -eq 0 ] && exit 0
[ "$n" -gt "$MAX" ] && { echo "ABORT: $n candidates > $MAX" >&2; exit 1; }

jq -r '.[].ID' /tmp/candidates.json | while read -r id; do
  openstack server show "$id" -f json -c id -c name -c project_id -c created -c fault -c tags \
    | tee -a /var/log/error-reaper.log |
    jq -e '.tags | index("keep") | not' >/dev/null || { echo "skip $id (keep)"; continue; }
  [ "${DRY_RUN:-1}" = 1 ] && { echo "would delete $id"; continue; }
  openstack server delete "$id" || echo "FAILED $id" >&2
done
```

Run it from cron or a systemd timer with `DRY_RUN=0` set only once you trust it. Use a dedicated service account with just the roles it needs, not full admin creds.

If you also want it to cover instances stuck in ERROR after a failed delete, that works with the same job, since a repeat delete usually clears them. If you tell me your client and API versions, I can adapt the script and test the filter against them.