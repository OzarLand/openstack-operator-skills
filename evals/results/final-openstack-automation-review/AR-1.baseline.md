**Don't put this in cron as written.** The worst failure is a false positive, where nova reports a host down while its VMs are still running. This script turns that into a larger outage than the one it was meant to prevent.

## Blocking issues

1. **No fencing, so you risk split-brain and disk corruption.**
   - `state == 'down'` only means nova-compute missed heartbeats (about 60s by default).
   - That also happens when nova-compute crashes, when the host is partitioned from RabbitMQ or the DB, or when the host is under load. In each case the guests may still be running.
   - Evacuating then starts a second copy of each VM. On shared storage such as Ceph or NFS, two VMs writing the same disk will corrupt it.
   - Power the host off (IPMI/BMC) and confirm it is off before evacuating.

2. **One control-plane blip evacuates the whole cloud.**
   - If the controller loses RabbitMQ or DB connectivity, or the conductor stalls, every compute host looks down at once.
   - The script would then try to evacuate every VM in the cloud, onto hosts that are also marked down or are overloaded.
   - Add a circuit breaker. If more than N hosts, or more than X%, are down, do nothing and page a human.

3. **No debounce.**
   - A host that is rebooting, or just slow to heartbeat, gets evacuated after a single one-minute observation.
   - Require the host to be down across several consecutive runs (for example 5+ minutes). That needs state kept between runs, such as a file or the service's `disabled_reason` or `updated_at`.

4. **Wrong order: evacuate, then disable.**
   - While the evacuations run, the scheduler can place the evacuated VMs back on the dead host.
   - Mark the host first, with `forced_down=True` (`update_service_forced_down`) and disable it. Then evacuate.
   - If the script dies partway, the host stays `enabled`, and the next run restarts the evacuation from scratch.

5. **No error handling.**
   - Evacuation fails with a 409 for servers in states like `BUILD`, `RESIZE` or `SHELVED`.
   - It also fails when no valid host has capacity.
   - One exception aborts the loop, skips the remaining servers, and skips the disable. You would find out in the morning, if at all.

6. **No locking.** Evacuating many VMs takes longer than a minute, so cron will start overlapping runs. They will race on the same servers. Wrap the job in `flock -n`. If you install it on several controllers, run it on only one.

## Also worth fixing

- **Mutating while paginating.** `servers()` is a lazy paginated generator, and evacuation changes `host` while you iterate. Use `list(...)` first.
- **Local-disk instances.** Evacuating a VM with an ephemeral or local root disk rebuilds it from the image, so its data is lost. Decide whether you want that automatically, or only for volume-backed or shared-storage VMs.
- **Planned maintenance.** A host that is rebooting for patching and not yet disabled will be evacuated. Put a maintenance flag, such as a file or an aggregate metadata key, in the script's check.
- **No logging or alerting.** An automated evacuation should still notify someone, so you read about it over coffee instead of finding out from users. Log what happened and send a notification.
- **No timeouts, no dry-run mode.** Add both, and run the dry-run in cron for a week before enabling the real thing.
- **Check the SDK signatures.** `disable_service` and `evacuate_server` have changed across openstacksdk versions, so test against your installed one.

## Better option

Consider **OpenStack Masakari**. It is the upstream project for this: host monitors, fencing hooks, segments, and recovery methods. If you stay with the script, treat it as a small Masakari substitute and include the guardrails above.

## Sketch of the safer shape

```python
import openstack, sys, logging

MAX_DOWN = 2            # circuit breaker: absolute or % of fleet
conn = openstack.connect(cloud='prod', timeout=30)
log = logging.getLogger("autoevac")

svcs = list(conn.compute.services(binary='nova-compute'))
down = [s for s in svcs if s.state == 'down' and s.status == 'enabled']
if len(down) > MAX_DOWN:
    alert(f"{len(down)} computes down; refusing to evacuate"); sys.exit(1)

for svc in down:
    if not down_long_enough(svc.host):        # persisted state, e.g. >= 5 runs
        continue
    if in_maintenance(svc.host):
        continue
    if not fence_host(svc.host):              # IPMI power-off + verify
        alert(f"cannot fence {svc.host}"); continue

    conn.compute.disable_service(svc, svc.host, 'nova-compute',
                                 disabled_reason='autoevac')
    conn.compute.update_service_forced_down(svc, svc.host, 'nova-compute')

    for s in list(conn.compute.servers(all_projects=True, host=svc.host)):
        try:
            conn.compute.evacuate_server(s)
        except Exception as e:
            alert(f"evacuate {s.id} failed: {e}")
    alert(f"evacuated {svc.host}")
```

Run it as `* * * * * flock -n /run/autoevac.lock python3 autoevac.py`.

`fence_host`, `down_long_enough`, `in_maintenance` and `alert` are placeholders you'd need to implement.

If you tell me your storage backend (Ceph, NFS or local) and whether you have BMC access to the computes, I can tighten this further.