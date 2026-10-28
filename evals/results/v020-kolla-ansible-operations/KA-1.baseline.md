I can't see your config or inventory from this session. `/etc/kolla` doesn't exist here, so this is based on what you've told me. The change itself is fine, but I'd change how you roll it out.

**The change**
- `reserved_host_memory_mb` belongs in the `[DEFAULT]` section. Check that your snippet sits under `[DEFAULT]`. A key under the wrong section is silently ignored, and you'd find out only when the OOM kills come back.
- 8192 is a reasonable starting point. Size it from what each host actually runs: host OS, OVS/OVN, libvirt, and the per-guest QEMU overhead that isn't in the flavor RAM. If the hosts are dense with many small guests, you may need more.
- It only affects **new** scheduling decisions. Placement will stop putting more guests on a host past that limit. It does not move or shrink guests that are already running. A host that is already over-committed will keep OOMing until you migrate guests off it.
- Check `ram_allocation_ratio` as well. If it's above 1.0, memory overcommit is probably the real cause. Reserving 8 GB won't fix that.
- The setting is only read at nova-compute startup, so the compute containers have to restart to pick it up. Kolla does that when the config file changes.

**The rollout**
I wouldn't run a full `kolla-ansible deploy` across all 40 computes tonight. Two reasons:
1. A full deploy touches every service on the 3 controllers too. It will pick up any other drift since the last deploy, such as changed globals, image tags or other overrides, and you'd be debugging those mid-run.
2. Restarting all the compute containers at once is a big blast radius for a change that only touches nova-compute.

Here's what I'd do instead:
```bash
# 1. Preview the change
kolla-ansible genconfig -i <inventory> --tags nova      # or: reconfigure --check --diff

# 2. Canary on 1-2 computes
kolla-ansible reconfigure -i <inventory> --tags nova --limit compute01,compute02

# 3. Verify
#    - docker exec nova_compute grep -r reserved_host_memory /etc/nova/
#    - openstack resource provider inventory list <rp-uuid>   # MEMORY_MB reserved = 8192

# 4. Roll the rest in batches
kolla-ansible reconfigure -i <inventory> --tags nova --limit 'compute[03:12]'  # and so on
```
- `reconfigure` with `--tags nova` is the right tool for a config-only change. It avoids pulling images and avoids touching the controllers.
- Restarting nova-compute doesn't stop running guests, since they're libvirt/QEMU processes. Still, go in batches so you can stop if something looks off.

**Before you start**
- Find the hosts that are already near their limit and live-migrate or shut off a few guests there. Otherwise the OOMs will continue after the change.
- Check that the 2026.1 release notes for Kolla-Ansible don't call for anything special if you're also changing versions in this run.

If you can paste the config file and the output of `kolla-ansible ... --check --diff` for one host, I'll review them.