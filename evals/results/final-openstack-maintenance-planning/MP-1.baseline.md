# Plan for patching 300 hosts across 3 AZs in 3 weeks

## 1. Check the capacity math first
- You have 100 hosts per AZ and about 8 free hosts in total, so roughly 2–3 per AZ. **Instances can't leave their AZ** if tenants pinned them, so spare capacity has to be counted per AZ. 8 free hosts all in one AZ would not help the other two.
- At 8 hosts per cycle, you need about 38 cycles. Three weeks is about 15 working days, so that's about 2.5 cycles a day. The limit is cycle time (drain, patch, reboot, validate, re-enable), not just spare capacity.
- Free capacity can also be fragmented. Check that the spare hosts can fit your large, pinned or hugepage flavors.

**Ways to get more throughput:**
- **Leapfrog:** patch the spare hosts first. Every patched host becomes a migration target and then spare capacity again. Instances move once, onto a host that already has the new kernel and QEMU. The fix needs a new QEMU process, so a live migration to a patched host delivers it.
- **Drain the emptiest hosts first** to get more cycles per day.
- **Handle SHUTOFF instances without migrating them.** Cold-patch hosts that hold only shutoff instances.
- **Ask security whether a livepatch or mitigation is acceptable as an interim step.** This depends on the CVE, but it can take pressure off the deadline.
- **Find more headroom.** Borrow hosts, reclaim idle or shutoff instances, and stop new scheduling onto unpatched hosts.

## 2. Don't try to learn criticality. Treat everything as critical.
You can't classify instances reliably, so choose the least disruptive method for all of them and sort by migratability instead:
- **Normal VMs:** live migrate. This is usually invisible to tenants.
- **Hard to migrate:** SR-IOV, CPU-pinned, hugepage, GPU, local-disk and very memory-heavy VMs. This is the long tail.
- **Cheap signals that still help:** server groups and anti-affinity (never take down both members of a pair at once), volume-backed versus ephemeral, tenant, and flavor.
- **Let tenants tell you.** Send notice to all project owners now with a maintenance schedule. Offer a self-service way to say "don't touch before X" or "move me first". Anyone who doesn't reply gets the default method.

## 3. SR-IOV
- Live migration of SR-IOV ports depends on your OpenStack, libvirt and NIC versions. Nova can hot-unplug the VF, migrate and re-plug it, with a short network blip, but support varies. **Test it in a lab on your exact stack before the canary.**
- Destination hosts need free VFs on the same physnet.
- For anything that fails, tell the tenant in advance and ask them to restart or rebuild it in a window they pick. Give them an early date, because this group needs the longest lead time. Put the SR-IOV hosts in their own waves rather than mixing them in.

## 4. Timeline
| When | What |
|---|---|
| Days 1–4 | Inventory per AZ: host utilization, spare capacity, SR-IOV/pinned/etc. VM counts. Lab-test the live migration paths, including SR-IOV. Write the runbook and rollback. Send tenant notice. Patch the spare hosts. |
| Days 4–6 | Canary: 1–2 hosts in one AZ. Watch migration failures, tenant tickets and host health. |
| Week 2 to early Week 3 | Production waves. One wave per AZ at a time (about 2–3 hosts each), with the AZs staggered rather than all at once. Aim for about 85–90% done by the end of week 2. |
| Final 3–4 days | Long tail and failures, and the SR-IOV and pinned hosts with tenant coordination. Keep this as buffer. |

## 5. Per-wave mechanics and gates
1. Disable scheduling on the host (`nova-compute` disabled).
2. Live migrate its instances to patched hosts.
3. Patch, reboot and verify the kernel and QEMU versions.
4. Smoke test (a boot-and-migrate-in test), then re-enable.
5. Move on only if the previous wave's migration failure rate and tenant impact were acceptable. Set explicit thresholds (for example, more than X failed migrations or any host that won't rejoin pauses the rollout).

## 6. Risks to settle now
- Whether capacity really is spread across the AZs.
- Host rollback: keep the old kernel in the bootloader, and know that the QEMU rollback is harder.
- Rate limits on migrations, such as network bandwidth and converge settings for busy VMs (auto-converge or post-copy).
- Get a written decision from security on what to do if some hosts can't be patched in time (isolate them, or accept a documented exception).

I can turn this into a runbook with a wave schedule, or a script that generates drain batches from `openstack` output, if you share the per-AZ host and instance data. Do you want either?