**Oui, il y a une raison forte de ne pas tout évacuer maintenant : rien ne prouve que cmp-0417 soit mort.** Un `nova-compute` down signifie seulement que Nova ne reçoit plus de heartbeat. Si le processus a crashé, si le réseau de management est coupé ou si le service est bloqué, les qemu peuvent continuer à tourner sur l'hôte. Les VMs sont alors toujours actives et écrivent sur leurs disques Ceph. Évacuer les relance ailleurs : deux copies de la même VM écrivent sur le même disque. Pour des bases de données, c'est une corruption, pas une simple indisponibilité. Ceph ne protège pas contre ça, puisqu'il ne sait pas qui est légitime.

Je n'ai pas d'accès shell ici, donc je n'ai rien vérifié sur votre plateforme. Ce qui suit repose sur les faits fournis et sur la règle « fencer avant d'évacuer ».

## Situation
- **Capacité perdue** : l'hébergement des VMs sur cmp-0417 (≈40 VMs, dont des bases clients).
- **Ce qui marche** : le plan de contrôle (API, scheduler) n'est pas signalé comme dégradé. Rien n'indique une panne plus large.
- **Impact** : bases clients injoignables. Criticité par VM inconnue : il faut la liste des propriétaires.
- **Inconnu** : état réel de l'hôte, ce qui a changé vers 03:12, et l'heure actuelle (donc la durée réelle).

## Evidence
| # | Classe | Constat | Source |
|---|---|---|---|
| 1 | Reported | nova-compute cmp-0417 down depuis 03:12 | message de l'astreinte |
| 2 | Reported | ≈40 VMs injoignables, disques sur Ceph | message de l'astreinte |
| 3 | Gap | État de l'hôte (power, réseau, qemu) | non vérifié |
| 4 | Gap | Les VMs écrivent-elles encore sur Ceph ? | non vérifié |

## Hypothèses
| Hypothèse | Ce qui la soutient | Ce qui l'infirmerait | Vérification discriminante |
|---|---|---|---|
| A. Hôte réellement éteint/mort | Heartbeat absent | BMC indique « on », ou watchers Ceph présents | BMC + `rbd status` |
| B. Hôte vivant, nova-compute ou réseau de management seul en panne (les VMs tournent) | Cas courant : service crashé, agent bloqué | BMC « off » et plus de watchers | BMC + `rbd status` + ping/ssh |
| C. Partition réseau (côté Ceph ou côté contrôle) | Plusieurs hôtes concernés | Hôte joignable depuis tous les réseaux | Ping depuis un autre hôte sur chaque réseau |

## Vérifications read-only à faire avant toute évacuation
1. **BMC** : `ipmitool -I lanplus -H <bmc-cmp-0417> -U <user> chassis power status` (identifiants depuis le coffre, pas dans le chat). Résultat attendu : `off` pour A.
2. **Watchers Ceph**, pour chaque disque d'instance : `rbd status <pool>/<image>`. Si un watcher pointe sur l'IP de cmp-0417 (réseau Ceph), qemu tient encore le disque ouvert. C'est le discriminant le plus fort. Aussi `rbd lock ls <pool>/<image>`.
3. **Nova** : `openstack compute service list --service nova-compute` et `openstack server show <id> -c OS-EXT-SRV-ATTR:host -c OS-EXT-STS:vm_state` pour quelques VMs.
4. **Réseau** : ping et ssh vers cmp-0417 depuis un autre hôte, sur le management et le réseau de stockage. Si accessible : `virsh list --all` et `journalctl -u nova-compute --since "03:00"`.

## Décision de protection
La plateforme ne se dégrade pas : seul cet hôte est en cause, donc attendre quelques minutes pour vérifier ne coûte presque rien. Les instances ne sont pas à rétablir en bloc sans vérification.

## Options d'action (non autorisées)
- **Si A est confirmé (BMC off, aucun watcher)** : évacuation possible, mais par étapes.
  - Prérequis : fencer et confirmer l'arrêt. Forcer le service à `down` (`openstack compute service set --down cmp-0417 nova-compute`). Désactiver l'hôte.
  - Ordre : par criticité, en accord avec les propriétaires (bases en premier). Pas les 40 d'un coup.
  - Vérification par VM : active sur le nouvel hôte, joignable, base qui démarre et passe sa récupération de crash.
  - Sortie : ne pas remettre cmp-0417 en service tant que nova-compute n'a pas nettoyé les copies locales évacuées.
  - Recommandé avant évacuation : snapshot Ceph de chaque disque (`rbd snap create`), ce qui permet de revenir en arrière. À valider par l'owner.
  - Approbateur : responsable de l'exploitation (décision explicite).
- **Si B ou C** : ne pas évacuer. Restaurer nova-compute ou le réseau sur l'hôte vivant, ou l'isoler proprement (réseau Ceph coupé) si le fencing est impossible. Dans ce cas les VMs peuvent geler sur I/O, ce qui doit être décidé et annoncé.

## Vérification avant de déclarer le rétablissement
- Chaque VM évacuée : état actif, réseau joignable, base saine après récupération de crash.
- Nova : nouvel hôte listé, cmp-0417 désactivé et forcé down jusqu'à nettoyage.
- Ceph : watchers sur les disques uniquement côté nouvel hôte.

## Lacunes
- Résultat du BMC et des watchers : sans ces deux points, impossible de trancher entre A, B et C.
- Cause du passage down à 03:12 : sans elle, un nouvel incident est possible après évacuation.
- Liste des VMs par criticité et contacts des propriétaires.
- Présence de sauvegardes ou de réplicas des bases.

**Réponse courte** : ne lancez pas `evacuate` sur les 40 VMs maintenant. Vérifiez d'abord le BMC et les watchers Ceph. Si l'hôte est réellement éteint, évacuez par ordre de criticité, après fencing et snapshots. Sinon, rétablissez l'hôte vivant.

> Decision support only. State-changing steps above require approval by the accountable owner and should be executed under your change process.