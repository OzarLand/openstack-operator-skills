The idea is worth automating, but this script should not run unattended in its current form. Evacuation is the one step in an OpenStack environment that can corrupt data, and the script has no guard against doing it at the wrong time.

## Problems, most severe first

1. **Split-brain on a host that is only unreachable.** Nova sees "down" when heartbeats stop, which can also mean a controller-side network partition, a RabbitMQ problem, or a nova-compute hang. The VMs may still be running on the original host. Evacuating them starts second copies that share disks (Ceph RBD, NFS), IPs, or ports, and both copies can write. Nova's documented procedure is to confirm the host is dead or fenced (BMC/IPMI power-off), then mark it forced-down, then evacuate. The script does none of that.

2. **No circuit breaker.** If nova-api, the database, or RabbitMQ has a problem, many compute services can look down at once. The script will then evacuate the fleet. A cap on hosts per run would turn that into a page instead of a disaster.

3. **Flapping hosts trigger it.** `service_down_time` defaults to 60s, and cron runs every 60s. One late heartbeat is enough to fire. Require several consecutive "down" observations, stored in a small state file.

4. **Overlapping runs.** If one run takes longer than a minute, the next one starts and issues duplicate evacuations. Use `flock`.

5. **One exception ends the run.** A 409 on a server in REBUILD or MIGRATING raises, so `disable_service` never runs. The next minute repeats the same work. Wrap each server in its own try/except, and disable the host first so the scheduler doesn't place new VMs on it.

6. **Local-disk instances lose their data.** Evacuating an instance with ephemeral storage rebuilds it from the image on another host. Filter these out or handle them separately.

7. **Nothing is logged.** Cron output has nowhere to go, and there is no record of what was evacuated or why. Evacuation is also asynchronous, so the script should verify the result later rather than assume it worked.

8. **SDK signatures need checking.** I did not run this against a cloud. Confirm the argument order and keyword names of `disable_service` and `evacuate_server` against your pinned openstacksdk version.

## Safer version

This version defaults to dry-run, refuses mass events, logs everything, and does not handle fencing. Fencing has to be real and happen before the evacuate step.

```python
import logging
import openstack

DRY_RUN = True            # flip to False only after a staging test
MAX_HOSTS_PER_RUN = 1     # more than this usually means a control-plane problem
EVACUABLE = {"ACTIVE", "SHUTOFF", "PAUSED", "ERROR"}

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("evac")

conn = openstack.connect(cloud="prod")

down = [s for s in conn.compute.services(binary="nova-compute")
        if s.state == "down" and s.status == "enabled"]

if not down:
    raise SystemExit(0)

if len(down) > MAX_HOSTS_PER_RUN:
    log.error("%d computes down, above cap of %d; not acting: %s",
              len(down), MAX_HOSTS_PER_RUN, [s.host for s in down])
    raise SystemExit(2)

for svc in down:
    log.warning("nova-compute on %s is down", svc.host)
    if DRY_RUN:
        log.warning("dry run: would disable and evacuate %s", svc.host)
        continue

    # Before evacuating: confirm the host is fenced (BMC power-off), not just unreachable.
    conn.compute.disable_service(svc, svc.host, "nova-compute",
                                 disabled_reason="auto-evacuation")

    for server in conn.compute.servers(all_projects=True, host=svc.host):
        if server.status not in EVACUABLE:
            log.info("skipping %s in state %s", server.id, server.status)
            continue
        try:
            conn.compute.evacuate_server(server)
            log.info("evacuation requested for %s", server.id)
        except Exception:
            log.exception("evacuation failed for %s", server.id)
```

Cron line with overlap protection and a log file:

```
* * * * * flock -n /run/evac.lock python3 /opt/evac/evac.py >> /var/log/evac.log 2>&1
```

## Recommendation

- Run it in dry-run mode for a week and compare its output against the outages you actually had.
- Add the consecutive-check logic and a real fencing step before enabling evacuation.
- If the goal is hands-off recovery, consider Masakari (Instance HA). It handles fencing, evacuation, and the edge cases above, and it is designed for this problem.
- Until then, a page to on-call with the list of down hosts gets you most of the benefit and avoids the worst outcome.