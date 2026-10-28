# Security policy

## What this policy covers

This repository holds Agent Skills that give operational advice for production
OpenStack, their reference files and evaluation records. Three kinds of issue
are security issues here:

1. **Unsafe advice**: a skill that, followed as written, could cause data loss,
   an outage or a security weakness without the warning, precondition or
   approval its safety rules require (`shared/evidence-and-safety.md`), for
   example a destructive step presented as safe or a lab result presented as
   proven in production.
2. **Sensitive data published by mistake**: a secret, a real hostname or
   address, or an unredacted log in a skill, an example or an evaluation
   result.
3. **A skill that mishandles secrets**: repeats a credential the user pasted,
   asks for one, or puts one in a generated runbook or record.

## How to report

Use GitHub private vulnerability reporting: "Report a vulnerability" in the
Security tab of this repository. Only you and the maintainers see the report.
If the Security tab does not offer it, message the
[OzarLand](https://github.com/OzarLand) organization owner on GitHub. There is
no e-mail contact.

Wrong or unhelpful advice that involves no sensitive data and could not cause
harm before it is fixed can go in a public issue:
[unsafe or wrong advice](https://github.com/OzarLand/openstack-operator-skills/issues/new?template=unsafe-or-wrong-advice.yml).

Say which skill and file, the prompt or situation, what the skill advised and
what could go wrong. Do not include the sensitive data itself beyond what is
needed to locate it.

## What to expect

- Acknowledgement within 5 business days.
- Sensitive data is removed promptly; if a secret was exposed, its owner is
  told so they can rotate it, and the history is rewritten if needed.
- Unsafe advice is corrected, or the procedure is downgraded in
  `validation/inventory.yaml` with a warning, until it is fixed.
- Credit to the reporter in the fix, unless they prefer to stay anonymous.

## Vulnerabilities in OpenStack itself

A vulnerability in OpenStack, Kolla-Ansible or another upstream project goes to
the [OpenStack Vulnerability Management Team](https://security.openstack.org/),
not here.
