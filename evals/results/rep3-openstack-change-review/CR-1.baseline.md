**I wouldn't submit this as written.** The scope is fine, but the plan bundles two risky changes and has no real rollback. A CAB reviewer will likely send it back.

## Main problems

**1. Rollback.**
- "Restore old certs" only covers the certificate half of the change. Nothing covers the OS update or reboot.
- The old certs expire in 9 days. A rollback after Saturday leaves you with a short, hard deadline and nothing in reserve.
- If the new certs come from a different CA, every client needs the new trust bundle (computes, agents, HAProxy, monitoring, automation). "Restore" then means reverting that too.
- Galera and RabbitMQ rollbacks are not a file copy. They need restarts, and a mixed-cert cluster can fail to re-join.

**2. Two changes at once.** If something breaks after the reboots, you can't tell whether the cause is the certs or the patch, and you have 4 hours to find out. I'd do the certs in this window, because they have the deadline. I'd move the OS update and reboot to its own window, unless the security update is itself urgent. If both must go in, do certs first, soak and verify, then patch.

**3. Calendar margin.** Today is Sunday 25 Oct, so Saturday is 31 Oct. If "9 days" is exact, expiry is around 3 Nov. That leaves about 3 days if the window slips or fails. Please confirm the exact `notAfter` dates. Also confirm the CA certificates, which may expire on a different date.

**4. First rotation in 3 years, so the unknowns are untested.**
- Check that the SANs, key usage (client and server auth for mutual TLS), key sizes and CA chain are right. Check for anything that pins a cert or fingerprint.
- Rehearse the whole procedure in a lab or staging environment.
- Stage the trust bundle days earlier. A bundle with the old and new CA is non-disruptive. That shrinks the window work to swapping the certs.

**5. Controller reboots.**
- The CR should say rolling, one node at a time, and wait for Galera to show synced (`wsrep_cluster_size=3`) and RabbitMQ to be healthy before the next. Rebooting two at once breaks quorum.
- State what lives on the controllers: L3/DHCP agents, Ceph mons, and so on. VMs on computes should keep running, but API and control-plane impact needs to be stated.
- Rebooting all three also forces RabbitMQ client reconnects, which can storm.

## What to add to the CR

- **Pre-checks.**
  - Galera backup and RabbitMQ definitions export.
  - Backup of the current certs, keys and configs, with checksums.
  - Baseline of cluster health.
  - Confirmation that the new certs are issued and validated (`openssl verify`, SAN check) before the window.
- **A timed runbook** with go/no-go checkpoints. For example: 
  - T+0: backups. 
  - T+30: Galera. 
  - T+90: RabbitMQ. 
  - T+150: API endpoints. 
  - T+200: end-to-end test. 
  
  Set a hard rollback cutoff, such as "if not healthy by T+X, revert".
- **Component-level rollback**, in reverse order of change, with the exact commands. Say who decides, and test it in the rehearsal.
- **Verification.**
  - Per-endpoint `openssl s_client` checks.
  - Cluster status.
  - Create and delete a VM, volume and network.
  - Check that compute services report up.
  - Check that monitoring and automation still connect.
- **Roles and comms**: change lead, the person doing the rollback, a stakeholder notice, and a post-change check.
- **Follow-up**: expiry monitoring and alerting (30/14/7 days) and a documented rotation procedure, so this doesn't become another surprise.

## Missing information

- Which CA signs the certs (internal or external), and is the CA itself near expiry?
- How is the deployment managed (kolla-ansible, TripleO, OSA, manual)? Many of these have a built-in cert rotation path, and the rollback should use it.
- Is there a staging environment?
- Is the OS update urgent, such as a CVE with a deadline, or routine?

If you send me those answers, I can turn this into a revised, CAB-ready change request. I'd write it as a shareable page. It would have a split-change recommendation, a timed runbook, a risk table and a rollback plan per component.