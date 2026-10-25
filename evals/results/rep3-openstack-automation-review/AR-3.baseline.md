The idea is sound, but I wouldn't run that one-liner as written. It has no age filter, and a few other things need guarding.

**Problems with the one-liner**
- **No age check.** `--status ERROR` alone also deletes instances that failed a minute ago, mid-incident, before anyone has looked at them.
- **`xargs` runs once with no arguments when the input is empty.** That's harmless here but noisy. Use `xargs -r`.
- **ERROR doesn't always mean a dead build.** A failed resize or migration can leave a VM that still holds a user's data in ERROR. Deleting it is irreversible.
- **A mass-ERROR event deletes the evidence.** If a bad compute host or a RabbitMQ or Nova outage produces 200 ERROR instances overnight, the job wipes the faults you need for the post-mortem.
- **Volumes and ports can be orphaned.** Boot-from-volume instances without `delete_on_termination` leave volumes behind that still eat quota.

**Age filter**
Compute API 2.66+ supports `--changes-before`, which filters on `updated_at`. For an ERROR instance that's roughly when it failed, which is the age you care about:

```bash
cutoff=$(date -u -d '24 hours ago' +%Y-%m-%dT%H:%M:%SZ)
openstack --os-compute-api-version 2.66 server list --all-projects \
  --status ERROR --changes-before "$cutoff" -f value -c ID
```

**Safer wrapper**
```bash
#!/usr/bin/env bash
set -euo pipefail
MAX=${MAX_DELETES:-50}
DRY_RUN=${DRY_RUN:-1}
cutoff=$(date -u -d '24 hours ago' +%Y-%m-%dT%H:%M:%SZ)

mapfile -t ids < <(openstack --os-compute-api-version 2.66 server list \
  --all-projects --status ERROR --changes-before "$cutoff" -f value -c ID)

echo "$(date -u +%FT%TZ) found ${#ids[@]} stale ERROR instances"
if (( ${#ids[@]} > MAX )); then
  echo "more than $MAX, refusing (possible incident)" >&2; exit 1
fi

for id in "${ids[@]}"; do
  # log the fault and owner before deleting
  openstack server show "$id" -f json -c id -c name -c project_id -c user_id -c fault -c created -c updated
  (( DRY_RUN )) || openstack server delete "$id" || echo "failed: $id" >&2
done
```

**Recommendations**
1. **Run with `DRY_RUN=1` for a week or two.** Review the logged list and fault messages before enabling deletion.
2. **Keep the circuit breaker.** Fail loudly and page someone if the count exceeds a threshold, rather than deleting everything.
3. **Ship the logs somewhere durable.** Include ID, name, project and fault. If someone asks "where did my instance go?", you can answer.
4. **Consider a longer window for instances that were once ACTIVE.** A never-booted build failure is safe to delete after 24h. A formerly running VM in ERROR deserves 7 days and a notice to the owner. You can tell them apart with `openstack server show` (check `OS-EXT-STS:task_state`, or whether it has a `launched_at`).
5. **Use a dedicated service account** with only the nova delete and list permissions, not a full admin credential.
6. **Sweep orphaned volumes and ports separately,** with the same dry-run approach.

I can turn this into a systemd timer or cron entry with logging and alerting if you'd like.