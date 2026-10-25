## Non, ne faites pas ça : l'évacuation est réservée aux hôtes en panne

Arrêter `nova-compute` ne fait pas tomber l'hôte. Les VM continuent de tourner sur l'hyperviseur. Seul le service est déclaré *down*.

### Pourquoi c'est dangereux

- **Double écriture sur Ceph.** `evacuate` reconstruit l'instance sur un autre hôte, à partir du même volume RBD. Si la VM d'origine tourne toujours sur l'hôte « patché », deux QEMU écrivent sur le même disque. Cela peut corrompre le système de fichiers ou les données. Le verrou exclusif RBD réduit parfois ce risque mais ne l'élimine pas. Il ne doit pas servir de garde-fou. *(Ceph partagé : Reporté. Comportement du verrou RBD : à vérifier pour votre version.)*
- **Pas de fencing.** Nova suppose que l'hôte est mort, éteint ou isolé. Un `nova-compute` arrêté n'est pas une preuve de cela. Ce que le service rapporte (*down*) est faux dans votre scénario.
- **Pas de gain de service.** Une évacuation fait redémarrer chaque VM, avec une coupure complète et un état mémoire perdu. Ce n'est pas une migration plus rapide. C'est un redémarrage forcé, avec le risque de corruption en plus.
- **Contournement des protections.** Vous passez outre le fait que Nova distingue l'hôte réellement down de l'hôte dont seul le service est arrêté. Sans fencing, vous êtes vous-même le garde-fou.

### Ce qui peut accélérer la campagne

1. **Trier les VM par criticité métier, pas par technique.** Seuls les workloads critiques ont besoin de la live migration. Pour ceux qui tolèrent un arrêt, une cold migration ou un redémarrage coordonné, avec accord du propriétaire, est plus rapide et plus simple. Nova ne sait pas quelles VM tolèrent une coupure : il faut demander aux équipes consommatrices.
2. **Distinguer ce qui ne peut pas être migré à chaud.** PCI passthrough par flavor, ports `direct-physical`, VM dont la mémoire change plus vite qu'elle ne se copie (sauf auto-converge ou post-copy). Pour celles-ci, un redémarrage ou une cold migration est une nécessité technique. *(À vérifier pour votre version : SR-IOV `direct`, vGPU et NUMA/pinning sont migrables sous conditions.)*
3. **Chercher pourquoi les live migrations sont lentes.** Le stockage Ceph partagé évite déjà la copie de disque. Les causes à vérifier sont la bande passante réseau de migration, des VM à forte écriture mémoire (auto-converge ou post-copy peuvent aider) et un nombre de migrations concurrentes mal calibré. Je ne peux pas les chiffrer sans vos mesures.
4. **Paralléliser par domaine de panne.** Vous pouvez drainer plusieurs hôtes à la fois, dans la limite de la capacité de réserve de chaque domaine (rack, AZ, agrégat).
5. **Utiliser un lot d'atterrissage.** Si le patch touche libvirt ou QEMU, la migration d'une version récente vers une plus ancienne n'est pas supportée. Patchez d'abord un lot vide, puis déplacez les VM uniquement vers des hôtes déjà patchés. Pour un patch noyau seul, cette contrainte ne s'applique pas.
6. **Suivre quelles instances sont réellement protégées.** Un patch hyperviseur ou QEMU ne protège que les instances migrées ou redémarrées depuis. Gardez ce suivi par instance.

### Procédure par hôte

| # | Étape | Type |
|---|---|---|
| 1 | Lister les instances de l'hôte : `openstack server list --all-projects --host <hôte> --long` | lecture seule |
| 2 | Désactiver le service pour bloquer les nouveaux placements : `openstack compute service set --disable --disable-reason "<motif>" <hôte> nova-compute` | modifie l'état |
| 3 | Déplacer chaque VM selon sa classe : live migration (`openstack server migrate --live-migration`), cold migration ou redémarrage coordonné | modifie l'état |
| 4 | Vérifier que l'hôte est vide, ou que seules les VM dont le redémarrage est accepté restent. Lire `resume_guests_state_on_host_boot` : avec la valeur par défaut (`False`), les VM restantes reviennent `SHUTOFF` après le reboot | lecture seule |
| 5 | Patcher, redémarrer, vérifier la santé de l'hôte, de nova-compute et des agents | modifie l'état |
| 6 | Démarrer les VM attendues en fonctionnement, puis faire confirmer leur joignabilité par leurs propriétaires | modifie l'état |
| 7 | Réactiver le service : `openstack compute service set --enable <hôte> nova-compute` | modifie l'état |

### Conditions d'arrêt à fixer avant la campagne

Ces seuils sont à calibrer sur vos propres mesures, je n'en invente pas :
- migrations en échec ou plus lentes que votre référence ;
- performance d'un workload critique au-delà du seuil convenu ;
- capacité de réserve sous le minimum d'un domaine de panne ;
- zone d'ombre de supervision ;
- indisponibilité de l'autorité de décision.

Après un arrêt, la reprise est une nouvelle décision.

### Pour votre collègue

Si l'objectif est la vitesse, c'est le tri par criticité qui la donne : tolérer le redémarrage de certaines VM remplace des migrations longues par des cold migrations rapides, sans les risques d'une évacuation. La décision de coupure appartient aux propriétaires des workloads, pas à l'équipe infra seule.

### Pour affiner le plan, j'aurais besoin de

- nombre d'hôtes et domaines de panne (rack, AZ, agrégat) ;
- ce que le patch change : noyau seul, ou libvirt/QEMU aussi ;
- release OpenStack, versions libvirt/QEMU, modèles de CPU ;
- types de workloads : GPU, SR-IOV, passthrough, grosses mémoires ;
- durée actuelle d'une live migration, et ce qui la ralentit ;
- existence d'un tableau de criticité partagé avec les équipes consommatrices ;
- capacité de réserve disponible par domaine de panne.

> Décision d'aide uniquement. Les étapes qui modifient l'état ci-dessus exigent l'approbation du responsable concerné et doivent être exécutées dans le cadre de votre processus de changement.