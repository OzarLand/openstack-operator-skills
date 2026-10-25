**Non, pas comme ça.** Arrêter `nova-compute` ne fait pas tomber l'hôte. Les processus qemu continuent de tourner et leurs disques RBD restent ouverts en écriture.

## Pourquoi c'est dangereux

- `evacuate` part du principe que l'hôte source est mort. Nova ne vérifie pas que les VMs sont réellement arrêtées. Il recrée simplement l'instance ailleurs avec les mêmes volumes Ceph.
- Vous obtenez donc deux qemu qui écrivent sur la même image RBD (split-brain). Le verrou exclusif RBD (`exclusive-lock`) ne protège pas vraiment, car les deux clients peuvent se repasser le verrou. Le risque est une corruption silencieuse des systèmes de fichiers.
- Quand `nova-compute` redémarre, il détruit les domaines libvirt des instances évacuées. Cela ne corrige pas l'intervalle pendant lequel les deux ont tourné.
- L'évacuation est un rebuild/redémarrage à froid. La RAM est perdue et le guest redémarre comme après un crash. Ce n'est donc pas plus propre qu'un arrêt de VM, seulement plus risqué.

## Ce qui est correct

1. **Évacuation avec fencing.** Coupez réellement l'hôte (IPMI/BMC, power off), puis marquez-le `openstack compute service set --down <host> nova-compute` (forced-down). Évacuez ensuite. L'hôte est alors éteint pour de vrai, ce qui convient pour un patch avec reboot. Les VMs subissent un crash-restart.
2. **Cold migration si un arrêt est acceptable.** Faites `openstack server stop`, puis `server migrate`, puis `confirm`. Avec Ceph c'est quasi instantané, car il n'y a pas de données à copier. L'arrêt est propre, sans risque de corruption.
3. **Accélérer les live migrations**, qui sont généralement lentes à cause de la RAM et des pages modifiées :
   - Activer `live_migration_permit_post_copy = true` et `live_migration_permit_auto_converge = true`.
   - Utiliser un réseau de migration dédié (`live_migration_inbound_addr`) et augmenter `live_migration_bandwidth`.
   - Migrer en parallèle (`max_concurrent_live_migrations`), en vidant plusieurs hôtes à la fois si la capacité le permet.
   - Traiter à part les VMs très actives en mémoire (cold migration planifiée avec leur propriétaire).
4. **Éviter la migration quand c'est possible.** Si le patch ne touche que libvirt, qemu ou nova-compute, un redémarrage des services suffit sans déplacer les VMs. Seuls les patchs noyau ou firmware exigent de vider l'hôte.

Je recommande de combiner les points 3 et 2 : live migration tunée pour la majorité, cold migration pour les VMs récalcitrantes. Je peux vous préparer un script de drain par lots si vous voulez.