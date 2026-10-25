**Oui, il y a une raison de ne pas le faire tout de suite : "nova-compute down" ne prouve pas que l'hôte est mort.** Ne lancez pas `evacuate` avant d'avoir fencé l'hôte.

## Pourquoi

Seul le heartbeat de nova-compute manque depuis 03:12 (Observé, d'après votre sortie de `compute service list`). Plusieurs causes peuvent produire ce symptôme :
- l'hôte est réellement éteint ou en panne ;
- le démon nova-compute a planté ou s'est bloqué, alors que **les VM tournent toujours** ;
- l'hôte est isolé du plan de contrôle (réseau de management ou RabbitMQ) alors que les VM tournent encore et écrivent sur Ceph.

Nova ne sait pas distinguer ces cas. Si vous évacuez une VM dont l'hôte d'origine est vivant, vous obtenez **deux copies de la même VM qui écrivent sur le même volume RBD**. Pour des bases de données clients, cela veut dire une corruption possible et difficile à rattraper. Que les disques soient sur Ceph accélère l'évacuation, mais cela rend aussi ce risque plus grave.

Autre point : les VM sont "injoignables", mais je ne sais pas si c'est parce qu'elles sont arrêtées ou parce que le réseau de cet hôte est coupé. Ce n'est pas établi.

## Ce qui est rapide et sûr (≈ quelques minutes)

1. **Fencer l'hôte** (état-changeant, à faire par l'astreinte) :
   - consulter l'état d'alimentation via BMC/IPMI/iDRAC (read-only) ;
   - s'il est allumé et que vous ne pouvez pas le joindre, l'éteindre via le BMC, ou isoler ses ports au niveau du switch.
2. **Vérifier le stockage** (read-only). Pour une VM, regardez `rbd status <pool>/<volume>` : s'il y a encore des watchers actifs, l'hôte est probablement vivant. Un blocage de client Ceph (`ceph osd blocklist`) peut aussi servir de fencing complémentaire. Ces commandes dépendent de votre version, à vérifier.
3. **Marquer le service forced down** (état-changeant), plutôt que d'attendre le timeout du heartbeat :
   `openstack compute service set --down cmp-0417 nova-compute`
4. **Évacuer VM par VM, dans l'ordre de criticité**, plutôt que toutes d'un coup :
   - commencer par les bases de données clients, avec l'accord des propriétaires ;
   - vérifier chacune (ACTIVE sur le nouvel hôte, joignable, disque cohérent) avant de passer à la suivante ;
   - ne pas tout lancer en parallèle, pour ne pas saturer le scheduler, Ceph ni les destinations.

Le fencing prend peu de temps s'il y a un accès BMC. Il ne retarde donc que de quelques minutes, et ce délai évite un risque de corruption.

## Autres points à valider avant de lancer

- **Capacité** : les autres hôtes peuvent-ils accueillir 40 VM (CPU, RAM, aggregates, pinning, GPU/SR-IOV) ? Sinon l'évacuation échoue en partie et laisse des instances en ERROR.
- **Cause racine** : vérifiez qu'il n'y a pas un problème plus large (RabbitMQ, réseau de management). Si d'autres hôtes passent aussi "down", ce n'est probablement pas un incident local à cmp-0417. Contrôlez `compute service list` pour les autres nœuds.
- **Qu'est-ce qui a changé vers 03:12** : maintenance, mise à jour, changement réseau ?

## Quand l'hôte reviendra

Gardez-le **désactivé et forced down** jusqu'à ce que nova-compute ait nettoyé les copies locales des instances évacuées. Ne remettez le service en route (`--up`, puis `--enable`) qu'ensuite, en étapes séparées. Sinon, vous recréez le risque de double copie dans l'autre sens.

## Vérification de la reprise

Pour chaque VM : ACTIVE sur le nouvel hôte, joignable, base de données saine côté application (avec le propriétaire). Aucune VM de cmp-0417 ne doit tourner en double.

## Ce que j'ai besoin de savoir

- Avez-vous un accès BMC, et que montre l'état d'alimentation de cmp-0417 ?
- Les autres hôtes ont-ils des services down ?
- Qui est le décisionnaire côté astreinte et côté clients pour l'ordre de priorité ?

> Decision support only. Les étapes qui modifient l'état ci-dessus nécessitent l'approbation du responsable concerné et doivent être exécutées selon votre processus de changement.