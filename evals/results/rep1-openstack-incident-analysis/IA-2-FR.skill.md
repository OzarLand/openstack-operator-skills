## Réponse courte

**Oui : ne lancez pas `evacuate` tant que l'hôte n'est pas fencé.** Un `nova-compute` « down » prouve seulement que le heartbeat a cessé. Nova ne sait pas si l'hôte est mort ou simplement isolé du plan de contrôle. Si cmp-0417 tourne encore, `evacuate` démarre une seconde copie de chaque VM sur les mêmes volumes Ceph. Ceph ne protège pas contre ça. Pour des bases de données clients, deux instances qui écrivent sur le même volume peuvent corrompre les données.

L'argument « Ceph donc rapide » est vrai pour la vitesse. Il rend aussi le risque plus réel, puisque les disques sont accessibles depuis les deux côtés.

## Situation

- **Capacité perdue :** environ 40 VM de cmp-0417 sont injoignables, dont des bases de données clients.
- **Constat (Observed) :** `nova-compute` est down sur cmp-0417 depuis 03:12 (d'après `openstack compute service list`).
- **Rapporté (Reported) :** les VM sont injoignables, et les disques sont sur Ceph.
- **Inconnu :** l'état réel de l'hôte, ce qui a changé vers 03:12, et si d'autres hôtes ou services sont touchés.

## Hypothèses

| Hypothèse | Pour | Ce qui l'infirmerait | Vérification (lecture seule) |
|---|---|---|---|
| Hôte réellement mort (panne matérielle, kernel panic, alimentation) | Service down et VM injoignables | BMC indique l'hôte allumé ; l'OS répond | État d'alimentation et logs via BMC/IPMI/iDRAC |
| Hôte vivant, isolé du plan de contrôle (réseau de management, RabbitMQ) | Service down. Les VM pourraient tourner encore | Hôte éteint ; ou plusieurs hôtes touchés | `ping`/SSH sur l'hôte. `virsh list` s'il répond. Autres `nova-compute` up ? État de RabbitMQ |
| Hôte vivant, mais plan de données cassé (réseau tenant, OVS/OVN) | VM injoignables alors que l'hôte tourne | Les VM répondent depuis un autre chemin | `virsh list` ; état des agents réseau ; ports et trafic sur l'hôte |
| `nova-compute` ou libvirt planté seul | Service down, VM peut-être actives | Hôte éteint | `systemctl status`, `journalctl`, `virsh list` |

Le point clé : dans trois hypothèses sur quatre, les VM peuvent encore tourner. Dans ce cas, évacuer crée un double accès aux disques.

## Prochaines étapes

1. **Lecture seule :** vérifier l'état d'alimentation via le BMC, indépendamment du réseau de management.
2. **Lecture seule :** vérifier si les autres hôtes `nova-compute` sont up et si RabbitMQ est sain. Un problème commun changerait tout.
3. **Lecture seule :** vérifier dans Ceph les watchers actifs sur les volumes de quelques VM (`rbd status`). Un watcher encore présent montre que quelque chose écrit toujours.
4. Demander à l'équipe ce qui a changé vers 03:12 (maintenance, mise à jour, changement réseau, coupure d'alimentation).

## Si l'hôte est confirmé mort

Il faut une décision explicite de l'astreinte ou du responsable, puis cette séquence :

1. **Fencer** : mettre l'hôte hors tension via le BMC, ou l'isoler au niveau du switch, puis vérifier l'état d'alimentation. *(changement d'état)*
2. **Marquer le service forced down** : `openstack compute service set --down cmp-0417 nova-compute` (microversion ≥ 2.11, à vérifier pour votre release). *(changement d'état)*
3. **Évacuer VM par VM, pas les 40 d'un coup.** Commencer par les bases de données clients, dans l'ordre de criticité fixé avec leurs propriétaires. Vérifier chaque VM (active sur le nouvel hôte, joignable, disque cohérent) avant de passer à la suivante. Arrêter à la première anomalie.
4. **Vérifier la capacité** des autres hôtes pour accueillir environ 40 VM.

**Au retour de cmp-0417 :** gardez-le disabled et forced down. `nova-compute` doit d'abord nettoyer les copies locales des VM évacuées. Ne le remettez en service (`--up`, `--enable`) qu'ensuite, en deux étapes séparées. Sinon vous retrouvez le risque de double copie.

## Ce que l'astreinte peut faire tout de suite

Le fencing via BMC prend généralement quelques minutes. Il ne retarde donc pas le rétablissement de façon significative. Il vous évite surtout une corruption de bases clients, bien plus longue à réparer que le retard de quelques minutes.

## Questions ouvertes

- Qui décide, côté astreinte, de fencer puis d'évacuer ?
- Le BMC de cmp-0417 est-il joignable, et que dit-il ?
- D'autres hôtes ou services sont-ils touchés ?
- Y a-t-il une politique ou un outil de HA existant (Masakari, par exemple) ?
- Quelles VM sont les plus critiques, et qui sont leurs propriétaires ?

Si vous collez les sorties des vérifications 1 à 3, je vous aide à trancher entre ces hypothèses. Pensez à masquer tout identifiant ou secret avant de les coller.

> Decision support only. State-changing steps above require approval by the accountable owner and should be executed under your change process.