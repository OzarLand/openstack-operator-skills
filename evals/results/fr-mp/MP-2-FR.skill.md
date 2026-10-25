**Non, c'est une mauvaise idée, et je ne la ferais pas passer en production.** L'évacuation sert à récupérer les instances d'un hôte tombé en panne. Elle n'est pas faite pour la maintenance planifiée, et la différence a de vraies conséquences ici.

## Pourquoi ça ne marche pas

1. **Arrêter `nova-compute` n'arrête pas les VM.** Les processus QEMU continuent de tourner sur l'hôte. Le service apparaît « down » seulement parce que ses heartbeats cessent. Nova en déduit que l'hôte est mort alors qu'il ne l'est pas. C'est le piège classique : un heartbeat manquant ne prouve pas qu'un hôte est mort, et il faut fencer avant d'évacuer.
2. **Risque de double écriture sur Ceph.** `evacuate` redémarre chaque instance ailleurs, sur le même disque RBD, alors que l'original tourne encore. Deux écrivains sur le même volume peuvent corrompre les systèmes de fichiers ou les bases de données. Le verrou exclusif RBD réduit ce risque mais ne remplace pas un fencing. Vérifiez le comportement exact pour votre release et votre configuration.
3. **Ce n'est pas une migration rapide, c'est un crash.** L'état mémoire est perdu et chaque VM redémarre à froid, donc avec une indisponibilité pour tout le monde, y compris les workloads critiques. Vous échangeriez « lent mais sans interruption » contre « rapide mais tout le monde tombe ».
4. **Il y a aussi un effet de bord au retour de l'hôte.** Au redémarrage de `nova-compute`, Nova nettoie les instances évacuées de l'hôte. Si cet ordre n'est pas maîtrisé, vous avez un risque de doublon.
5. **Aucun garde-fou de capacité.** Évacuer « tout ce qu'il héberge » d'un coup ignore la capacité de réserve par domaine de défaillance et les critères de criticité.

La seule variante défendable serait d'éteindre l'hôte via le BMC (fencing), puis d'évacuer. Mais c'est volontairement provoquer une panne franche de toutes les VM, ce qui reste un plan de reprise sur incident et pas un plan de patching.

## Ce qui règle vraiment le problème de lenteur

La lenteur vient de ce que toutes les VM reçoivent le même traitement. Le principe : la criticité métier décide de la méthode, pas la technique.

| Classe de workload | Stratégie | Condition |
|---|---|---|
| Critique et migratable | Live migration | capacité dispo dans le domaine de défaillance |
| Tolère un redémarrage (**accord du propriétaire**) | Cold migration (`openstack server migrate`) ou redémarrage coordonné | fenêtre convenue ; avec Ceph, un cold migrate est rapide |
| Non live-migratable (PCI passthrough, `direct-physical`, mémoire très volatile) | Cold migration ou redémarrage | consommateur prévenu |
| Intouchable avant l'échéance | Exception documentée | propriétaire, mesures compensatoires, date de revue |

Ce que vous cherchez, c'est la rapidité des cold migrations ou des redémarrages coordonnés pour les workloads qui les tolèrent, pas l'évacuation.

Pour accélérer la live migration elle-même, à vérifier selon votre release (lecture seule d'abord) :
- **Diagnostiquer pourquoi c'est lent.** Réseau de migration partagé avec le trafic tenant ? Bande passante limitée ? Pages mémoire modifiées plus vite qu'elles ne sont copiées ? Concurrence trop basse ?
- **Convergence** : `live_migration_permit_auto_converge` et `live_migration_permit_post_copy` pour les VM très actives.
- **Réseau dédié** à la migration, et concurrence réglée à partir de vos propres mesures.
- **Redémarrage en place** pour les VM tolérantes. Attention : avec `resume_guests_state_on_host_boot=False` (défaut), les invités reviennent `SHUTOFF` et il faut les redémarrer explicitement.

## Pour l'ordonnancement

- Si le patch touche libvirt ou QEMU, commencez par un lot vide patché comme **zone d'atterrissage**. La migration du plus récent vers le plus ancien n'est pas supportée.
- Une instance non migrée ni redémarrée après le patch **tourne toujours sur l'ancien binaire** : suivez-le instance par instance.
- Limitez le nombre d'hôtes simultanément drainés **par domaine de défaillance**.
- Définissez à l'avance les conditions d'arrêt : migrations qui échouent ou ralentissent, capacité sous la réserve, etc.

## Ce qu'il me faudrait pour aller plus loin

- Votre release OpenStack et la version de libvirt/QEMU.
- Le nombre d'hôtes, les domaines de défaillance et la marge de capacité libre.
- Ce qui est lent exactement : durée par VM, concurrence actuelle, réseau de migration.
- Si une table de criticité par projet existe. Sinon, la constituer avec les équipes consommatrices est le premier livrable.

Je peux produire un plan complet au format habituel (classes, capacité par domaine, procédure par hôte, conditions d'arrêt) si vous me donnez ces éléments.

> Decision support only. State-changing steps above require approval by the accountable owner and should be executed under your change process.