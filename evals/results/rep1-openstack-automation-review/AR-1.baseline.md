**Don't ship this as is.** The biggest risk is that it can cause the outage it's meant to prevent, and it will do it unattended at 3am.

## Critical

1. **No fencing, so you risk split-brain.** `state == 'down'` only means nova-compute missed heartbeats. The host and its VMs may still be running, for example after a network partition, a hung agent or a RabbitMQ problem. Evacuating then starts a second copy of each VM. With Ceph or other shared storage, two writers on one disk means corruption. You need to power the host off (IPMI/BMC) and confirm it's off before evacuating, then mark it `forced_down`. Nova's own docs require this.

2. **No blast-radius limit.** If the DB, RabbitMQ or the controllers' network has a bad minute, every compute node looks down at once. This script would then try to evacuate the whole cloud and disable every service. Add a hard cap, such as aborting if more than 1–2 hosts or more than 10% of hosts are down, and paging a human instead.

3. **No debounce.** At a one-minute cadence, a single missed heartbeat window triggers evacuation. Require the host to be down for several consecutive checks (5+ minutes), with state kept between runs, and ideally confirm it with an out-of-band check such as a BMC ping or power state.

4. **Local-disk instances lose data.** Without shared storage, evacuate rebuilds from the image, so ephemeral disk contents are gone. Filter to boot-from-volume or shared-storage instances, or accept that loss deliberately and skip the rest for a human to handle.

## Serious

5. **Order is wrong.** Disable the service first so nothing is scheduled to the host during the process. Disabling only after the loop means a mid-loop exception skips it entirely.

6. **No error handling.** One failed `evacuate_server` (409 for a wrong state, a timeout, a bad token) raises and aborts the run. The host stays `enabled`, so the next run retries every server, including ones already mid-evacuation. Wrap each call in try/except and log it.

7. **No locking.** Evacuation is async and can take longer than a minute, so runs will overlap. If cron runs on several controllers, they'll all fire at once. Use `flock -n`, or run on one controller only.

8. **All servers are treated alike.** Skip SHUTOFF, ERROR and BUILD instances and anything already migrating. Evacuating many at once can also overload the destination hosts, so rate-limit it.

## Minor

- Materialize the generators with `list(...)` before mutating.
- Pass `disabled_reason='auto-evacuated <timestamp>'` to `disable_service`. This also marks the host for humans and makes the `status == 'enabled'` check act as a "handled" flag.
- Log every decision, and send an alert on any action. Silent automation that moves VMs is worse than none.
- Use a dedicated service account with only the policy rights it needs, not full admin credentials in a `clouds.yaml` on the controller. Also set `timeout` on the connection.

## Better option

This is the problem OpenStack **Masakari** (instance HA) solves. It has host and process monitors, fencing hooks, thresholds and recovery methods. Pacemaker/pacemaker-remote with STONITH is the other common approach. If you stay with a script, it should at least do this:

```
flock -n → list down+enabled hosts
→ if count > cap: alert, exit
→ require down for N consecutive checks (persisted state)
→ fence via BMC, verify powered off
→ nova service-force-down / disable with reason
→ evacuate eligible servers (try/except each, rate-limited)
→ alert with the summary
```

I can write that version if you give me your storage setup (Ceph or local), whether you have BMC access from the controllers, and the fleet size to base the cap on.