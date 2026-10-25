**Don't put this in cron yet.** The logic is the right idea, but as written it can turn a small outage into a large one.

## Must fix

1. **No fencing, so you risk split-brain and data corruption.**
   - `state == 'down'` only means the `nova-compute` agent stopped reporting. It does not mean the host or its VMs are dead.
   - The usual causes are a RabbitMQ blip, a hung agent, or a network partition. In all of those, the guests keep running.
   - Evacuating then starts a second copy of each VM. On shared storage such as Ceph or NFS, two writers on one disk will corrupt it. You also get duplicate IPs and MACs.
   - Power the host off first, using IPMI/BMC or your STONITH tooling. Only evacuate once the power-off is confirmed.

2. **No blast-radius limit.**
   - If the controller loses RabbitMQ or the DB, or has a network problem, every compute node looks `down` at once.
   - This script would then try to evacuate the whole cloud onto nodes that are probably fine.
   - Add a circuit breaker. For example, abort and page a human if more than 1 host, or more than 5% of hosts, are down.

3. **No grace period.**
   - Service state flips to `down` after about 60s (`service_down_time`), and cron runs every 60s.
   - A routine agent restart, package upgrade, or short hiccup on an enabled host will trigger a full evacuation.
   - Require the service to have been down for several minutes. `svc.updated_at` gives you this without a state file.

4. **Disable comes after evacuate, and any exception skips it.**
   - If one `evacuate_server` call raises (409 for a bad state, no valid host, or API timeout), the script dies.
   - The host is never disabled, the remaining hosts are never processed, and the next minute repeats everything.
   - Mark the host disabled or forced-down first, using `update_service_forced_down` and `disable_service`. Then evacuate each server inside its own `try/except`.

5. **No locking.**
   - Evacuation is asynchronous and can take longer than a minute, so runs will overlap.
   - Wrap the script in `flock -n`.
   - If the controllers are HA, run it on only one of them. Otherwise all three fire at once.

## Should fix

- **Capacity:** if the remaining nodes don't have room, evacuated VMs go to ERROR. Check free vCPU and RAM against what you are about to move.
- **Local disks:** for instances on local storage (non-shared, non-volume-backed), evacuation rebuilds from the image and the data is lost. Decide whether that is acceptable, or filter those instances out and alert instead.
- **Server states:** filter on status. Skip ERROR and in-flight task states rather than blindly evacuating everything returned.
- **Visibility:**
  - The script is silent.
  - It needs logging and an alert (Slack, PagerDuty) on every action it takes. Otherwise you wake up to a surprise rather than not waking up at all.
  - Add a `--dry-run` flag and run it that way for a while.
- **Timeouts:** the connection and API calls have none, so a hung API call can pile up processes. Set `timeout` on `flock`, or use `timeout 50 python ...`.
- **Maintenance:** operators should be able to say "I'm working on this host". Disabling the service first already skips it. A tag or file flag also works.
- **API compatibility:** check that `disable_service(svc, host, binary)` matches the signature in your openstacksdk version. It has changed between releases.

## Sketch of the safer shape

```python
import fcntl, sys, datetime as dt, logging
import openstack

MAX_DOWN, GRACE = 1, dt.timedelta(minutes=5)

lock = open('/run/lock/auto-evac.lock', 'w')
try:
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
except BlockingIOError:
    sys.exit(0)

conn = openstack.connect(cloud='prod')
now = dt.datetime.now(dt.timezone.utc)
down = [s for s in conn.compute.services(binary='nova-compute')
        if s.state == 'down' and s.status == 'enabled'
        and now - parse(s.updated_at) > GRACE]          # parse() = your timestamp parser

if len(down) > MAX_DOWN:
    alert(f'{len(down)} computes down, refusing to auto-evacuate'); sys.exit(1)

for svc in down:
    if not fence(svc.host):                              # IPMI power-off, confirmed
        alert(f'could not fence {svc.host}'); continue
    conn.compute.update_service_forced_down(svc, svc.host, 'nova-compute')
    conn.compute.disable_service(svc, svc.host, 'nova-compute',
                                 disabled_reason='auto-evacuated')
    for s in conn.compute.servers(all_projects=True, host=svc.host):
        try:
            conn.compute.evacuate_server(s)
        except Exception as e:
            alert(f'evacuate {s.id} failed: {e}')
```

`fence()` and `alert()` are yours to supply. `fence()` is the one that matters most. If you have no way to power-cycle hosts out-of-band, I'd have the cron job alert and disable the host, and keep the evacuation manual or behind a confirmation.

I can flesh this out into a full script with a dry-run mode if you tell me your fencing method and storage backend (Ceph, NFS, or local).