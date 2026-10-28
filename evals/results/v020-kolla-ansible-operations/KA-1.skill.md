**Short answer: the setting is reasonable, but I wouldn't run `deploy` on all 43 hosts tonight as planned.** I also can't see your config. `/etc/kolla` doesn't exist in this session, so everything below comes from your description and the Kolla-Ansible 2026.1 references.

## 1. Does it fix the OOM kills?

It only partly does.

- `reserved_host_memory_mb` changes how the scheduler counts memory (Placement `MEMORY_MB` reserved). It doesn't touch guests already running.
- A host that is already over-packed stays that way until you move or delete instances. The reservation only stops new placements.
- If `ram_allocation_ratio` is above 1.0, the 8 GiB reserve is a small dent against that overcommit. I'm stating this from general Nova behaviour. It isn't in the Kolla references, so check your ratio.
- I haven't seen any evidence of why the kills happen. Please paste the `dmesg`/`journalctl -k` OOM lines from one or two computes. They show whether the victims are qemu processes, what else is eating host RAM (OVS, Ceph OSDs, page cache), and whether the 8 GiB is the right size.
- Also check that the option is under `[DEFAULT]` in that file. An option under the wrong section is silently ignored.

## 2. Why not `deploy` on everything

- **Pending changes ride along.** `deploy` applies everything pending in `globals.yml` and the overrides, not just your line. If the deploy host's Kolla-Ansible is newer than the platform's release, it also deploys new images without the upgrade tasks. [DOCUMENTED-UNVERIFIED: KA-CMD-02]
- **It isn't rolling.** `nova_compute` restarts on all 40 computes at once. `reconfigure` ignores `-e kolla_serial` in 2026.1. [LAB-VALIDATED: KA-CMD-09, `reconfigure` only] You'd get a heartbeat gap, a RabbitMQ and conductor reconnect storm, and any in-flight build, resize or migration on those hosts failing.
- **Instances keep running.** The restart is an outage for the control path only, not for guests. [LAB-VALIDATED: KA-CFG-13, Nova, all-in-one]
- **It needs every host reachable.** Facts are gathered for every host, even with `--limit`, so one dead compute fails the run. [LAB-VALIDATED: KA-CMD-07]

## 3. Suggested sequence

1. **Read-only baseline.** Run `kolla-ansible check`, `openstack compute service list` and `openstack resource provider list`. Record per-host `MEMORY_MB` used and reserved, and `ram_allocation_ratio`. Commit `/etc/kolla` to git so you can see what changed. Confirm `kolla-ansible --version` matches the platform release.
2. **Preview, without restarting anything.** `kolla-ansible prechecks -i <inv> --tags nova`, then `genconfig --tags nova`, then `validate-config`. Check that the diff shows only your line, and that `/etc/kolla/nova-compute/nova.conf` on a compute has `reserved_host_memory_mb = 8192`. Any extra diff is a pending change you didn't intend. [LAB-VALIDATED: KA-CMD-03, Glance only]
3. **Canary.** Run `kolla-ansible reconfigure -i <inv> --tags nova --limit <1-2 computes>`.
   - Expect `nova_compute` to restart on those hosts only. Confirm with `docker inspect -f '{{.Name}} {{.State.StartedAt}}'`.
   - Check that the compute service comes back `up` and that Placement shows `MEMORY_MB` reserved 8192.
   - Check that no host's allocated memory now exceeds total minus reserved, times the ratio. Those hosts go over-allocated; nothing is killed, but they take no new instances.
   - The Kolla docs discourage `--limit`, and bug 2054348 concerns the `register:`/`--limit` interaction, so watch for tasks that delegate outside the limit.
4. **Batches.** Roll through the rest in groups, for example 4-5 computes, then 10, then the remainder. Repeat the checks after each batch.
5. **Final checks.** Run a full post-change check, including one real instance created, reached and deleted. [LAB-VALIDATED: KA-CMD-15/16, scoped to the labs described there]

**Stop if** any compute stays down for more than a few minutes, RabbitMQ shows a partition or alarms, instance builds start failing, or the diff contains anything you didn't expect.

**Rollback** is cheap. Remove the line and re-run the same command. Running guests are unaffected. [DOCUMENTED-UNVERIFIED for this change]

## 4. Before tonight

- **Capacity:** the sum of the new reserves across 40 hosts is up to about 320 GiB less schedulable RAM. Is there headroom, or will new boots hit `No valid host`?
- **Interim fix:** the OOM kills will continue on hosts that are already over-packed. Someone needs to decide whether to migrate instances off the worst hosts, which is a separate, planned change.
- **Heterogeneous computes:** if your computes have different RAM sizes, 8 GiB everywhere may be wrong. Per-host values go in `config/nova/<inventory_hostname>/nova-compute.conf`. Note that `<inventory_hostname>` is the inventory name, not the machine's hostname, and a wrong name is ignored silently. [LAB-VALIDATED: KA-CFG-01]
- **Approver:** name the capability owner who accepts a brief control-plane blip on the computes.

**Verdict: ready with conditions.** The change is low-risk and easy to undo. The plan should become a canary followed by `reconfigure --tags nova` in batches. Send me the OOM log lines, the `kolla-ansible --version` output, the `genconfig` diff and your `ram_allocation_ratio`, and I'll tighten this up.

> Decision support only. State-changing steps above require approval by the accountable owner and should be executed under your change process.