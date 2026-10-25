# Host maintenance mechanics

Summarized from [Book: Ch. 20] (technical note and Fig. 20.1), [Book: Ch. 10]
and [Book: Ch. 15]. Behaviour depends on release, hypervisor and storage;
verify against the Nova documentation on live migration, cold migration and
evacuation for the running release.

## Contents

- Operations compared
- Live migration prerequisites and constraints
- Instances that cannot or should not be live-migrated
- Patched binaries
- Example commands

## Operations compared

| Operation | Instance state | Use for | Key condition |
|---|---|---|---|
| Disable compute service | unchanged | stop new placements on the host | normally the first step of planned maintenance |
| Live migration | keeps running | critical workloads that must stay up | compatible destination with CPU, memory, disk; shared storage or block migration |
| Block live migration | keeps running | local instance disks | copies disks across the network: extra network and storage load |
| Cold migration (`openstack server migrate`) | stopped, moved, started | workloads that tolerate downtime, or cannot live-migrate | downtime agreed |
| Restart in place | stopped and started on same host after reboot | workloads that tolerate host reboot downtime | owner agreement |
| Evacuation | rebuilt elsewhere | **failed hosts only** | host fenced (powered off / isolated) first; never for planned maintenance |

## Live migration prerequisites and constraints

- Destination has sufficient CPU, memory and disk.
- Shared storage for instance disks, or block migration.
- Destination CPU model compatible with the source.
- Migration from newer libvirt/QEMU to older is **not** supported: after some
  hosts are patched, instances can move onto them but not back. Patching order
  decides where instances can go.

## Instances that cannot or should not be live-migrated

- PCI passthrough or SR-IOV direct ports.
- vGPU on versions without mediated-device migration support.
- Memory-intensive workloads whose pages change faster than they can be copied,
  unless auto-converge or post-copy is enabled.

For the three cases above, restart (or cold migration) is a technical
necessity rather than a business choice.

Separate case, release-dependent [Book: Ch. 15]: instances with a NUMA
topology / pinned CPUs live-migrate NUMA-aware from Train (Nova 20.0.0); only
on earlier releases were such migrations refused (Stein, unless a workaround
was enabled) or able to produce overlapping pinning. Check the running
release before classifying them.

## Patched binaries

A patch to the hypervisor or QEMU protects only instances that have been
migrated or restarted since it was applied; an instance still running on the
old binary is not patched [Book: Ch. 17, Ch. 20].

## Example commands

`[Addition]` — illustrative OpenStack client forms; check flags for the client
version in use. All but the first two are state-changing.

| Purpose | Command | Type |
|---|---|---|
| Instances on a host | `openstack server list --all-projects --host <host>` | read-only |
| Service state | `openstack compute service list --service nova-compute` | read-only |
| Disable host | `openstack compute service set --disable --disable-reason "<reason>" <host> nova-compute` | state-changing |
| Live migrate | `openstack server migrate --live-migration [--host <dest>] [--block-migration] <server>` | state-changing |
| Cold migrate | `openstack server migrate <server>` then confirm the resize when verified | state-changing |
| Re-enable host | `openstack compute service set --enable <host> nova-compute` | state-changing |
