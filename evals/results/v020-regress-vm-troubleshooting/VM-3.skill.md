**Not as your first move.** `reset-state` only edits Cinder's database record. It doesn't detach anything, so it can leave you with a stale iSCSI session or a still-running guest holding the volume. For a deleted server the normal fix is smaller, and it's the one to try first.

**What I'm relying on:** the lab-validated *Stale attachment* procedure in the skill's references. Its lab was OpenStack 2026.1 on Kolla-Ansible 22.2.0, all-in-one, with Cinder LVM over iSCSI, which matches your backend. It was not run multinode or on other releases. Nothing about your cluster has been observed yet. Treat everything below as unverified until you've run the checks.

## 1. Read-only checks first

- **Volume and attachment:** run `openstack volume show <vol>`, then `openstack --os-volume-api-version 3.27 volume attachment list --volume-id <vol>`.
  - Run `volume attachment show <id>` too. Its properties include the CHAP username and password in clear text, so redact them before pasting.
- **Server really gone:** run `openstack server show <deleted-id>`. It should return "No Server found".
- **Hypervisor check (most important):** find the last host the instance ran on, then run `virsh list --all` and `virsh domblklist <instance-name>` there. On Kolla-Ansible, run them inside `nova_libvirt`.
  - In the lab, when the compute was down during the delete, the guest **kept running with the volume open**. The database showed it as deleted and Cinder showed `available`.
  - A domain that is still defined, or a leftover iSCSI session, means the volume isn't safe to hand to anyone yet.
- **Why it stuck:** check whether `cinder-api` or `cinder-volume` was down or unreachable at delete time. That is the usual cause, and the lab reproduced it as a left-behind attachment and an unreachable Cinder API.

## 2. Fix, least invasive first

**Preferred: delete the stale attachment (state-changing).**
`openstack --os-volume-api-version 3.27 volume attachment delete <attachment-id>`

- **Preconditions:** no domain on the connector's host uses the volume.
- **Effect:** it releases the volume and the iSCSI export. The data is untouched.
- **Expected result:** the volume goes to `available` in a couple of seconds.
- **Validation status:** lab-validated (VM-VOL-16), within the scope above.

**Last resort: your command.** `openstack volume set --state available --detached <vol>` is for when the volume is `in-use` with **no attachment record left**. The lab-validated form is `volume set`, not the old `cinder reset-state`, but the effect is the same.

- **Preconditions:** no attachment record, and `domblklist` shows no domain using it on any host named by past attachments.
- **Risk:** it changes the record only. If something still has it open, the new instance and the old one become two writers, and you lose data.
- **Undo:** set the status back. Corrupted data isn't recoverable without a backup.
- **Validation status:** lab-validated (VM-VOL-20).

## 3. After either fix

- The volume should be `available` with no attachments.
- On the old host, there should be no domain and no iSCSI session for it.
- Attach it to the new instance, then confirm the attachment ID Nova lists matches Cinder's, and that `domblklist` on the new host shows it.
- If the volume was bootable or has important data, take a snapshot or backup before the user attaches it. It's cheap insurance.

If you paste the `volume show` and `attachment list` output (redacted), I can tell you which branch you're on.

> Decision support only. State-changing steps above require approval by the accountable owner and should be executed under your change process.