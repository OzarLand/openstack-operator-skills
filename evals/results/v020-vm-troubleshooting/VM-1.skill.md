**Not yet.** The wiki steps are the right last resort, but they're unsafe to run before you know whether cmp-031 is actually dead. The reference I used is the "Stuck in deleting" section of the `openstack-vm-troubleshooting` skill. Its lab validation covered the compute-down local-delete behaviour (2026.1, Kolla-Ansible 22.2.0, all-in-one). The `--down` path and the `set --state error` fallback were not run in the lab.

## Why the wiki procedure is risky here

- **Once the compute is `down`, a delete becomes a local delete.** The API removes the record, ports, allocations and attachments, and deletes any `delete_on_termination` volumes. It does nothing on cmp-031.
- **If the host is alive but nova-compute is dead, the guest keeps running.** Its IP and volumes can then be reused, which gives duplicate IPs and two writers on one volume. When nova-compute returns, it reaps the guest.
- **`--down` hits every instance on cmp-031, not just this one.** Their deletes become local deletes too, and they become evacuable, including by any auto-evacuation you run. Use it only on a host you've confirmed is fenced.
- **Setting the state to error is a record change, not a fix.** It changes only the database. If nova-compute is still working, it can start a second delete alongside the stuck one.

## Read-only checks first

Nothing below changes state.

1. `openstack server show <id> -c status -c OS-EXT-STS:task_state -c OS-EXT-STS:power_state -c OS-EXT-SRV-ATTR:host -c locked -c fault` and `openstack server event list <id>`.
2. `openstack compute service list --service nova-compute --host cmp-031 --long`. Check the **Forced Down** column, how long it has been down, and whether other computes are down too. If several are, stop and use `openstack-incident-analysis`.
3. Is cmp-031 itself alive? Check with SSH, the BMC or the switch port. This decides everything else:
   - **Host alive, nova-compute dead:** run `sudo docker ps --filter name=nova_` and `sudo docker exec nova_libvirt virsh list --all --uuid | grep <id>`, then read `/var/log/kolla/nova/nova-compute.log` for the instance ID. If the guest is still running, it holds data and the network.
   - **Host really dead:** it needs fencing, which you confirm out of band (BMC power-off or switch port).
4. Ask whether the instance has `delete_on_termination` volumes (`openstack server show` → `volumes_attached`) and whether the customer needs that data.

## Fix options, least invasive first

1. **Bring nova-compute back (preferred if the host is alive).** Run `sudo systemctl restart kolla-nova_compute-container.service` on cmp-031. At start-up it resumes deletes left in `deleting` on that host. In the lab, the delete resumed about 9 s after start and the instance was gone about 24 s later. Running instances are not affected.
2. **Host confirmed dead and fenced, or definitely not coming back.** Use the wiki sequence in this order:
   - Snapshot any `delete_on_termination` volumes whose data matters.
   - Run `openstack --os-compute-api-version 2.11 compute service set --disable --disable-reason "<why>" --down cmp-031 nova-compute`.
   - Run `openstack server delete <id>`.
   - Only if it is still stuck, run `openstack server set --state error <id>` (undo: `--state active`), then delete again.
   - Before step 2 (`--down`), check what else runs on cmp-031 and who owns it.
   - Afterwards, if cmp-031 comes back, `--up` is refused while `done` evacuations exist. Plan to restart nova-compute deliberately, because at start-up it destroys local copies.
3. **Locked instance or other causes.** If `locked` is true, `openstack server unlock <id>` comes first.

This is destructive and has no undo. It needs a named owner, such as the on-call lead or the customer-impact owner, to approve it.

## Verification afterwards

- The instance is gone from `server list`.
- Its ports are freed, and there are no leftover attachments or allocations (check `openstack resource provider allocation show <id>`).
- No guest for that UUID remains on cmp-031 (`virsh list --all`) once it's back.
- No other instances on cmp-031 changed state.

## Gaps

I haven't seen any of your output, so everything above is conditional. Paste the `server show`, `event list` and `compute service list --long` output (redacted), and tell me whether cmp-031 is reachable. With those I can say which branch applies.

Decision support only. State-changing steps above require approval by the accountable owner and should be executed under your change process.