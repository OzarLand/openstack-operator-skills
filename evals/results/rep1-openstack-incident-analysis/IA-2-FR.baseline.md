**Oui, une raison sérieuse : ne lancez pas l'évacuation avant d'avoir confirmé que cmp-0417 ne fait plus tourner ces VM.**

`nova-compute down` veut seulement dire que le heartbeat du service s'est arrêté. Cela peut venir de l'agent planté, de RabbitMQ ou du réseau de management, sans que l'hôte soit mort. Les VM peuvent donc tourner encore sur cmp-0417 et être injoignables à cause d'un problème réseau ou du plan de données.

Si vous évacuez dans ce cas, chaque VM sera recréée ailleurs sur les mêmes volumes RBD pendant que l'ancienne instance continue d'écrire. Les deux écrivent alors sur le même disque (split-brain). Sur des bases de données clients, cela peut corrompre les données de façon irrécupérable, bien pire qu'une heure d'indisponibilité. Le verrou exclusif RBD est coopératif et ne vous protège pas de façon fiable ici.

**À faire, en quelques minutes :**
1. **Vérifier l'état réel de l'hôte.** Regardez l'alimentation via le BMC (`ipmitool chassis power status`) et la console, et testez ping/SSH sur l'IP de management. Si possible, lancez `virsh list` sur l'hôte.
2. **Fencer l'hôte.** Éteignez-le via le BMC (`ipmitool chassis power off`) et vérifiez qu'il est bien éteint. Si l'hôte est déjà éteint ou en kernel panic, c'est acquis.
3. **Marquer le service down.** Lancez `openstack compute service set --down cmp-0417 nova-compute` (ou `nova service-force-down`) pour que l'état soit cohérent.
4. **Évacuer par lots, bases de données d'abord.** Utilisez `openstack server evacuate <vm>`, ou `--host` pour cibler. Avant de lancer, vérifiez la capacité restante (vCPU et RAM sur les autres hyperviseurs), car 40 VM d'un coup peuvent saturer le scheduler ou des hôtes. Contrôlez aussi `ceph -s` : si Ceph est dégradé, le gain de temps annoncé n'existe plus.
5. **Prévenir les clients.** Les VM redémarrent à froid, donc les bases feront une crash-recovery. Cela reste normal et bien moins grave qu'une corruption.

**Après coup :** ne rallumez cmp-0417 qu'une fois toutes les évacuations terminées. Au redémarrage, nova-compute nettoie les domaines libvirt des instances évacuées. Vérifiez qu'aucune VM évacuée ne tourne encore localement avant de remettre l'hôte en service.

Si le BMC confirme que l'hôte est éteint ou mort, vous pouvez évacuer tout de suite, en lots. Sinon, il faut d'abord le fencer.