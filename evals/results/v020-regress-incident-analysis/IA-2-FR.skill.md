## Oui : ne lancez pas l'évacuation en masse avant d'avoir fencé l'hôte

**Raison principale.** Un `nova-compute` « down » indique seulement que le heartbeat est perdu. Il ne prouve pas que cmp-0417 est éteint. Si l'hôte est vivant mais isolé du control plane (réseau de management, bus RabbitMQ, agent bloqué), ses ~40 VM tournent peut-être encore. Une évacuation les recréerait alors ailleurs sur les **mêmes volumes Ceph**. Deux copies écriraient sur le même RBD, et sur des bases de données clients cela veut dire corruption.

Ceph ne protège pas contre ce risque. Il faut en plus que le verrou RBD soit levé (blocklist du client), et l'évacuation Nova ne vérifie pas que l'ancien hôte est mort. Les 40 VM sont déjà indisponibles, donc le fencing (quelques minutes) coûte peu à côté d'une corruption de bases clients, qui ne se rattrape pas.

### Séquence recommandée (P3, IA-FP-03 / IA-FP-04)

1. **Fencer l'hôte** (`read-only` pour la vérification, puis `state-changing` pour le power off). Contrôlez l'état d'alimentation via IPMI/iDRAC/BMC. S'il est allumé, éteignez-le, ou isolez-le au niveau du switch. Si le BMC est injoignable, il faut isoler au switch ou obtenir une confirmation physique. Dans ce cas, n'évacuez pas.
2. **Marquer le service forced down** (`state-changing`) : `openstack compute service set --down cmp-0417 nova-compute`. Cela évite d'attendre `service_down_time`. À vérifier pour votre version, il faut un microversion ≥ 2.11.
3. **Évacuer VM par VM**, pas en boucle sur les 40 :
   - Faites l'ordre de priorité avec les propriétaires : bases clients d'abord. L'infrastructure ne peut pas deviner la criticité.
   - Vérifiez après chaque évacuation : ACTIVE sur le nouvel hôte, joignable, disque cohérent. Avec le microversion ≥ 2.95, l'instance reste arrêtée et il faut la démarrer.
   - Pour les bases de données, contrôlez ensuite la cohérence applicative (récupération après crash, réplication).

### Vérifications à faire en parallèle (`read-only`)

- **Capacité** : les autres hôtes peuvent-ils absorber 40 VM, en vCPU, RAM et quotas Placement ? Sinon vous obtiendrez des ERROR en cascade.
- **Cause possible** : n'est-ce que cmp-0417 ? Regardez les autres compute, les agents Neutron, RabbitMQ et Galera. Si plusieurs services sont « down » à 03:12, c'est probablement le bus ou la base, et une évacuation de masse aggraverait la situation (P1).
- **Changements** : qu'est-ce qui a changé vers 03:12 (maintenance, mise à jour, réseau, alerte matérielle) ? Une action déjà tentée sur l'hôte ?
- **Ceph** : `rbd status` sur quelques volumes du host. La présence de watchers venant de cmp-0417 prouve que l'hôte est encore actif.

### Si l'hôte revient

Gardez-le disabled et forced down. Après le démarrage de `nova-compute`, attendez qu'il ait nettoyé les copies locales des instances évacuées. Ensuite seulement, faites `--up` puis `--enable`, en deux étapes approuvées séparément. Si vous le remettez en service trop tôt, vous retrouvez le risque de deux copies.

### Ce qui n'est pas validé

La séquence a été testée en lab sur 2026.1, Kolla-Ansible, ML2/OVS, disques locaux et sans Cinder. Le fencing IPMI ou switch, Ceph/boot from volume, le microversion 2.95 et les lots n'ont **pas** été exercés. Les verrous RBD sont une hypothèse de ma part, à vérifier pour votre version de Ceph.

### Décision à prendre

Qui, côté astreinte ou management, autorise l'évacuation ? Ce doit être une personne nommée. Je n'ai pas d'accès à votre plateforme et je n'ai rien exécuté. Donnez-moi les résultats ci-dessus (état IPMI, `compute service list`, capacité) et je vous prépare la liste ordonnée.

> Decision support only. Les étapes qui modifient l'état ci-dessus (power off, forced down, évacuation) demandent l'approbation du responsable concerné et doivent être exécutées selon votre processus de changement.