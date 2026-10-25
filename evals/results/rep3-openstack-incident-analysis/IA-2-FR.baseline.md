Oui, une raison majeure : **nova-compute « down » ne veut pas dire que l'hôte est mort.** Si cmp-0417 tourne encore, les 40 VM peuvent continuer à tourner. Évacuer, c'est alors recréer les mêmes VM ailleurs, avec les mêmes disques RBD, pendant que les originaux sont encore actifs.

**Le risque : double écriture sur les volumes Ceph**
- Deux QEMU sur le même RBD sans verrou exclusif, c'est de la corruption de données. Sur des bases de données clients, c'est le pire scénario.
- Le verrou RBD (exclusive-lock) offre une protection partielle seulement. Elle dépend de la config, du blacklist et de la version, donc ne vous y fiez pas.
- « Injoignables » peut vouloir dire que le réseau de l'hôte est coupé (OVS, agent neutron, lien) alors que les VM tournent toujours. Seul nova-compute est certain d'être down.

**À faire avant d'évacuer (quelques minutes)**
1. **Vérifier l'état de l'hôte** : ping, IPMI/BMC (`ipmitool power status`), console. Est-il allumé, en kernel panic, bloqué ?
2. **Si l'hôte est vivant** : essayer de relancer `nova-compute` (`systemctl status/restart nova-compute`, logs, RabbitMQ, disque plein, etc.). C'est souvent la cause, et les VM reviennent sans rien évacuer.
3. **Si l'hôte est mort ou inaccessible, le fencer pour de bon** : coupure d'alimentation via BMC (`ipmitool chassis power off`), et pas seulement un « down » logique. Confirmez que c'est éteint.
4. **Ceph** : sur un hôte éteint, vérifiez les watchers (`rbd status pool/volume`). Si besoin, blacklistez le client (`ceph osd blocklist add <addr>`) pour qu'il ne puisse plus écrire.
5. **Marquer l'hôte** : `openstack compute service set --disable cmp-0417 nova-compute` pour que le scheduler ne l'utilise plus. Puis `openstack compute service set --down` n'est pas nécessaire : Nova le sait déjà.

**Ensuite, évacuer, mais pas les 40 d'un coup**
- Commencez par 2 ou 3 VM de test non critiques et vérifiez qu'elles démarrent et que les services répondent.
- Priorisez les bases de données clients ensuite.
- Vérifiez la capacité des autres hyperviseurs (CPU/RAM) : 40 VM d'un coup peuvent saturer le cluster ou échouer au scheduling.
- Sur des BDD, prévoyez une vérification d'intégrité au redémarrage (crash recovery), puisque l'arrêt a été brutal.

**En résumé** : l'évacuation est la bonne réponse **si et seulement si** l'hôte est confirmé éteint. Cela prend 5 minutes de vérification et évite un risque de corruption irréversible chez les clients. Si le BMC permet un power-off immédiat, c'est le chemin le plus rapide et le plus sûr.