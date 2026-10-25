**Non, ce n'est pas une bonne idée, et ce n'est pas un contournement acceptable.** L'évacuation ne sert que pour un hôte en panne. Elle ne doit jamais servir pour une maintenance planifiée.

## Pourquoi c'est dangereux

- **« down » ne veut pas dire que les VMs sont arrêtées.** Quand vous arrêtez `nova-compute`, les heartbeats cessent et le service apparaît down. Libvirt et QEMU continuent pourtant de faire tourner les instances sur l'hôte.
- **L'évacuation ne vérifie rien.** Elle suppose que l'hôte a été isolé ou éteint (fencing) et qu'il est réellement mort. Ici, personne n'a fait ce fencing.
- **Deux copies de la même VM peuvent tourner en même temps.** `evacuate` reconstruit l'instance sur un autre hôte à partir du même disque. Avec du Ceph partagé, l'ancienne VM (toujours vivante) et la nouvelle peuvent écrire sur la même image RBD. Cela peut corrompre le disque. S'y ajoutent des conflits de port, d'IP et de MAC. Ne comptez pas sur le verrou exclusif RBD comme garde-fou.
- **Ce n'est pas plus rapide pour les utilisateurs.** Une évacuation est un rebuild suivi d'un redémarrage, donc une coupure pour **toutes** les VMs, y compris les critiques. Vous gagnez du temps de campagne en reportant le coût sur les clients, sans qu'ils l'aient accepté.
- **Ça ne remplace pas la décision métier.** Seuls les propriétaires des workloads peuvent dire ce qui supporte une coupure.

## Comment accélérer sans ce risque

*(Tout ce qui suit est state-changing et demande une approbation dans votre processus de changement.)*

1. **Classer les workloads** avec les équipes consommatrices :
   - ceux qui exigent de la disponibilité ;
   - ceux qui tolèrent un redémarrage ;
   - ceux qui ne sont pas live-migrables, comme le PCI passthrough ou les workloads à mémoire très active.
2. **Utiliser la cold migration pour ceux qui tolèrent une coupure.** Avec Ceph partagé, `openstack server migrate <vm>` n'a aucune donnée disque à copier : c'est un stop, un déplacement et un start, donc très rapide. C'est probablement ce que votre collègue cherche, mais de façon contrôlée et avec l'accord des owners.
3. **Réserver la live migration aux VMs qui en ont besoin.** Si vous réduisez le nombre de VMs concernées, la campagne accélère mécaniquement.
4. **Régler la live migration** pour les cas lents :
   - auto-converge ou post-copy pour les VMs dont la mémoire change vite ;
   - le débit du réseau de migration ;
   - plusieurs migrations en parallèle, dans la limite fixée par vos propres mesures de base.
5. **Patcher plusieurs hôtes en parallèle**, mais un par domaine de défaillance (rack, AZ) à la fois. Il faut donc de la capacité libre équivalente à un hôte **dans chaque** domaine.
6. **Si le patch touche libvirt/QEMU**, patcher d'abord un lot vide qui servira de zone d'atterrissage. La migration d'un QEMU récent vers un plus ancien n'est pas supportée.
7. **Pour le redémarrage en place**, vérifiez `resume_guests_state_on_host_boot` (read-only). Avec la valeur par défaut (`False`), les VMs restent `SHUTOFF` après le reboot. Il faudra alors les redémarrer et faire confirmer par les owners que les applications répondent.

Dernier point : une VM encore en cours d'exécution sur l'ancien binaire n'est pas patchée. Il faut la migrer ou la redémarrer après le patch.

## Pour affiner

Dites-moi ce qui est lent exactement : taille mémoire des VMs, taux de pages modifiées, bande passante du réseau de migration, nombre de migrations en parallèle. Donnez-moi aussi le nombre d'hôtes et de domaines de défaillance, vos versions de release, libvirt et QEMU, et si une table de criticité existe. Je peux alors produire le plan complet avec la vérification de capacité par domaine, la séquence, les conditions d'arrêt et les décideurs.

> Decision support only. State-changing steps above require approval by the accountable owner and should be executed under your change process.