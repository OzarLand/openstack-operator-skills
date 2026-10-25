**Non, je ne recommande pas cette approche pour une campagne de patchs.** Sur Ceph partagé, `evacuate` fonctionne mécaniquement, mais c'est un outil de reprise après panne, pas de maintenance planifiée.

## Pourquoi c'est risqué

- **Les VMs continuent de tourner sur l'hôte.** Arrêter `nova-compute` n'arrête pas les processus QEMU. Après l'evacuate, la même instance peut tourner à deux endroits sur les mêmes volumes RBD. Deux écritures concurrentes peuvent corrompre les disques. Nova ne fence pas l'hôte à votre place.
- **Le redémarrage au retour de l'hôte peut aggraver le problème.** Le nettoyage des instances évacuées dépend du comportement de `nova-compute` au démarrage. Le risque se situe dans cette fenêtre, et il n'est pas maîtrisé par la procédure.
- **Ce n'est pas plus rapide au sens utile.** Avec du stockage partagé, la live migration ne copie que la RAM. L'evacuate reconstruit chaque VM : état mémoire perdu, redémarrage complet de l'OS invité. Le downtime est donc plus long, pas plus court.
- **Pas de contrôle de capacité.** Le scheduler place toutes les instances d'un coup, sans lien avec les marges par domaine de panne. Les instances à PCI passthrough, GPU ou CPU épinglés peuvent ne pas trouver de destination.
- **Stockage local éphémère.** Si certaines instances ont un disque éphémère local, l'evacuate le perd.
- **Le redémarrage de l'hôte coupe les VMs restées dessus.** Avec le défaut `resume_guests_state_on_host_boot = False`, elles reviennent `SHUTOFF`.

## Pourquoi les live migrations sont lentes

Avant de changer de stratégie, vérifiez les causes habituelles, sans rien modifier :

- `max_concurrent_live_migrations` (défaut 1) sur les hôtes sources : c'est souvent la vraie limite.
- Bande passante du réseau de migration, et `live_migration_bandwidth` si elle est fixée.
- Taux de modification de la mémoire : les VMs très actives migrent lentement. Auto-converge ou post-copy peuvent aider, à valider.
- Temps de migration réel par instance, pour avoir une référence.

## Alternatives à proposer

1. **Migrations live parallèles, par lots.** Augmentez la concurrence dans la limite de vos baselines, par hôte et par domaine de panne, avec un plafond global. Définissez les conditions d'arrêt (échecs, ralentissement au-delà de la référence, capacité sous la réserve).
2. **Arrêt propre pour les charges qui tolèrent un redémarrage.** `openstack server stop`, puis cold migrate ou reboot de l'hôte, puis `start`. Pas de double exécution, et l'arrêt est géré par Nova.
3. **Landing zone si libvirt/QEMU change.** Patcher d'abord un lot vide, et ne migrer que vers les hôtes patchés, car la migration vers une version plus ancienne n'est pas supportée.
4. **Si l'équipe veut quand même l'evacuate pour certains hôtes** : seulement après extinction physique confirmée de l'hôte (IPMI ou équivalent), vérifiée par `virsh list` en lecture seule, et avec validation du propriétaire métier. C'est alors une décision explicite, pas une optimisation.

## Ce qui me manque pour chiffrer

- Nombre d'hôtes et de VMs, découpage en domaines de panne (racks, AZ, agrégats).
- Versions de libvirt/QEMU et stratégie de patch (noyau seul ou hyperviseur aussi).
- Valeurs actuelles de `max_concurrent_live_migrations` et `live_migration_bandwidth`, et temps de migration observé.
- Types de disques : Ceph racine uniquement, ou éphémères locaux.
- Liste des charges non migrables et leurs propriétaires (classes de criticité).

Ces données permettront de calculer la capacité par domaine de panne et de dimensionner la concurrence.

> Decision support only. State-changing steps above require approval by the accountable owner and should be executed under your change process.