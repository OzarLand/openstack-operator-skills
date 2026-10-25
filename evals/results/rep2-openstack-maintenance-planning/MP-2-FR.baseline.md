**Non, pas tel quel.** `evacuate` est fait pour un hôte mort, pas pour un hôte sain dont on a seulement arrêté `nova-compute`.

**Le risque principal : le split-brain**
- Arrêter `nova-compute` ne tue pas les VMs. Les processus qemu continuent de tourner et d'écrire sur leurs volumes RBD.
- Nova ne voit que le service « down » et en déduit que l'hôte est mort. `evacuate` recrée alors chaque VM ailleurs sur les mêmes images Ceph, alors que l'ancienne instance tourne encore.
- Vous avez deux qemu sur le même disque. Les verrous exclusifs RBD sont coopératifs, donc ils ne protègent pas de façon fiable. Le risque est une corruption silencieuse du système de fichiers.

**Ce qu'il faudrait pour que ce soit sûr**
- Un fencing réel avant l'evacuate : extinction de l'hôte par IPMI/BMC, ou au minimum arrêt de tous les guests.
- `openstack compute service set --down <hôte> nova-compute` (forced-down), pour ne pas dépendre du timer de heartbeat.

**Ce que vous obtenez au final**
- Un redémarrage à froid de chaque VM, avec perte de l'état mémoire et coupure de service.
- Ce n'est donc pas une migration plus rapide. C'est un crash suivi d'un reboot, déguisé en migration.
- Si votre contrainte est l'absence de coupure, ça ne la respecte pas.

**Alternatives plus propres**
1. **Accélérer la live migration**, le plus souvent suffisant :
   - `live_migration_permit_post_copy = true` (ou `live_migration_permit_auto_converge`) pour les VMs qui dirtyent beaucoup de mémoire ;
   - un réseau de migration dédié (`live_migration_inbound_addr`) ;
   - plus de migrations simultanées (`max_concurrent_live_migrations`) ;
   - une `live_migration_downtime` plus tolérante ;
   - plusieurs hôtes drainés en parallèle, si la capacité le permet.
2. **Migration à froid** (`openstack server migrate`) pour les VMs qui tolèrent un arrêt. Avec Ceph c'est très rapide, et c'est un arrêt propre (shutdown ACPI), donc sans risque de split-brain.
3. **Mixer les deux** :
   - live pour les VMs critiques ;
   - cold pour le reste ;
   - `openstack compute service set --disable` sur l'hôte avant de commencer.

Si votre collègue tient à l'approche evacuate, il faut au minimum ajouter le fencing par BMC, puis `--down`, puis `evacuate`. À ce stade, autant utiliser la migration à froid, plus simple et plus sûre.