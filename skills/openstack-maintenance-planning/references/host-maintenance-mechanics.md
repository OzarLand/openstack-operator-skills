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
| Restart in place | stopped by the host reboot; started again only if `resume_guests_state_on_host_boot` is `True` or someone starts it `[Addition]` | workloads that tolerate host reboot downtime | owner agreement; check power state after the reboot |
| Evacuation | rebuilt elsewhere | **failed hosts only** | host fenced (powered off / isolated) first; never for planned maintenance |

[LAB-VALIDATED: MP-MECH-01] Disable, block live migration of the host's
instances, verification of the empty host and re-enable: lab 2026.1,
Kolla-Ansible 22.2.0, 1 controller and 2 computes, local disks. Not run: cold
migration (see MP-MECH-07), shared-storage live migration, many instances,
production scale. On that lab each block live migration took 32 to 34 s and
pings every 0.2 s showed gaps of 1.8 to 8.6 s at the switch-over; once,
replies stopped for about five minutes without the instance restarting, cause
not found. "Keeps running" is not "no interruption": tell owners of critical
workloads. `[Addition]`

[LAB-VALIDATED: MP-MECH-02] Restart in place: with the default
`resume_guests_state_on_host_boot = False` instances came back `SHUTOFF` after
a host reboot, and running with `True` they came back running. Lab: 2026.1,
Kolla-Ansible 22.2.0 all-in-one, ML2/OVS. Not run: a reboot of one compute of a
multinode platform, OVN, Ceph-backed disks. `[Addition]`

## Live migration prerequisites and constraints

- Destination has sufficient CPU, memory and disk.
- Shared storage for instance disks, or block migration.
- Destination CPU model compatible with the source.
- Migration from newer libvirt/QEMU to older is **not** supported: after some
  hosts are patched, instances can move onto them but not back. Patching order
  decides where instances can go. [DOCUMENTED-UNVERIFIED: MP-MECH-03]

## Instances that cannot or should not be live-migrated

Migratability depends on the release, the hypervisor stack and the device.
Classify against the running release; verify each item in the Nova
"Live-migrate instances" and Neutron SR-IOV documentation for that release.

**Not live-migratable** — restart or cold migration is a technical necessity
rather than a business choice [Book: Ch. 20]:

- Flavor-based PCI passthrough (`pci_passthrough:alias`) and Neutron
  `direct-physical` ports.
- Memory-intensive workloads whose pages change faster than they can be copied,
  unless auto-converge or post-copy is enabled.

[DOCUMENTED-UNVERIFIED: MP-MECH-04] (the live-migration convergence case is
covered in more detail, with its own status, by `openstack-vm-troubleshooting`.)

**Live-migratable with conditions** `[Addition]`:

| Device | Since | Conditions and side effects |
|---|---|---|
| SR-IOV `direct` port | Train (Nova 20.0.0), libvirt driver | The port is hot-unplugged before the migration and re-plugged on the destination: the guest loses that interface briefly while the instance keeps running. Ask the owner whether the interruption is acceptable; check NIC and driver support. Indirect ports (`macvtap`, `virtio-forwarder`) migrate without that unplug. |
| vGPU (mediated devices) | 2024.1 (Caracal) | Both hosts need libvirt ≥ 8.6.0, QEMU ≥ 8.1.0 and kernel ≥ 5.18, and the same mdev type must be available on the destination. |
| NUMA topology / pinned CPUs | Train (Nova 20.0.0) | NUMA-aware since Train; earlier releases refused such migrations (Stein, unless a workaround was enabled) or could produce overlapping pinning [Book: Ch. 15]. |

[DOCUMENTED-UNVERIFIED: MP-MECH-05] From upstream release notes and
documentation; none of the three rows was executed on a lab.

Note on the source: the book lists SR-IOV direct ports among instances that
cannot be live-migrated [Book: Ch. 20]. Upstream Nova has supported it since
Train, as described above; this file follows upstream.

## Patched binaries

A patch to the hypervisor or QEMU protects only instances that have been
migrated or restarted since it was applied; an instance still running on the
old binary is not patched [Book: Ch. 17, Ch. 20].
[DOCUMENTED-UNVERIFIED: MP-MECH-06]

## Example commands

`[Addition]` — illustrative OpenStack client forms; check flags for the client
version in use. The Type column says which are state-changing.

| Purpose | Command | Type |
|---|---|---|
| Instances on a host | `openstack server list --all-projects --host <host>` | read-only |
| Status and power state after reboot | `openstack server list --all-projects --host <host> --long` | read-only |
| Guest resume setting | `crudini --get /etc/nova/nova.conf DEFAULT resume_guests_state_on_host_boot` (or read the file / container config; absent means the default, `False` — verify for your release and deployment tool) | read-only |
| Start a stopped instance | `openstack server start <server>` | state-changing |
| Service state | `openstack compute service list --service nova-compute` | read-only |
| Disable host | `openstack compute service set --disable --disable-reason "<reason>" <host> nova-compute` | state-changing |
| Live migrate | `openstack server migrate --live-migration [--host <dest>] [--block-migration] <server>` | state-changing |
| Cold migrate | `openstack server migrate <server>` then confirm the resize when verified (the confirm subcommand differs between client versions) [DOCUMENTED-UNVERIFIED: MP-MECH-07] | state-changing |
| Re-enable host | `openstack compute service set --enable <host> nova-compute` | state-changing |
