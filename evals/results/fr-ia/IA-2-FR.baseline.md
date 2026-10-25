**Oui, une raison sérieuse : ne l'exécutez pas avant d'avoir confirmé que cmp-0417 est vraiment mort.**

`nova-compute down` veut seulement dire que l'agent ne remonte plus de heartbeat. Ça peut venir d'un service planté, d'un problème RabbitMQ ou réseau de management, alors que l'hyperviseur et les qemu tournent toujours. Les VM sont injoignables, ce qui oriente plutôt vers un hôte ou un réseau cassé, mais ça ne le prouve pas.

Si les qemu tournent encore et que vous évacuez, Nova démarre une seconde instance sur le même volume RBD. Pour des bases de données clients, deux écrivains sur le même disque peuvent corrompre les données. Le verrou exclusif RBD réduit le risque mais ne le supprime pas, et `evacuate` ne fait aucun fencing de lui-même.

**Avant de lancer, dans cet ordre :**

1. **Fencer l'hôte.** Mettez cmp-0417 hors tension via son BMC/IPMI (`ipmitool chassis power off`) et vérifiez l'état. C'est la seule preuve fiable.
2. **Marquer le service comme down** pour que Nova accepte l'évacuation :
   `openstack compute service set --down cmp-0417 nova-compute`
3. **Vérifier côté Ceph** qu'aucun client n'écrit encore sur les disques :
   `rbd status <pool>/<image>` ne doit lister aucun watcher. Sinon, `ceph osd blocklist add <addr>` sur l'adresse du client écarte l'ancien hôte.
4. **Contrôler la HA applicative des bases.** Si Galera, Patroni ou une réplication a déjà basculé sur un autre nœud, relancer l'ancien primaire par évacuation peut créer un split-brain applicatif. Vérifiez l'état du cluster avant de rallumer ces VM.
5. **Vérifier la capacité** des autres hôtes (RAM, vCPU, quotas, affinités et anti-affinités). Évacuer 40 VM d'un coup peut échouer à moitié ou saturer des hôtes.

**Pour l'exécution :**
- Évacuez par lots, en commençant par les 2 ou 3 bases de données les plus critiques, puis vérifiez qu'elles remontent proprement (fsck, recovery) avant de continuer.
- Listez les VM avec `openstack server list --host cmp-0417 --all-projects`, et lancez `nova host-evacuate` ou une boucle sur `openstack server evacuate`.
- Si la panne vient d'un simple service nova-compute planté, le fencing ne coûtera que les quelques minutes de redémarrage. C'est peu comparé à un risque de corruption chez les clients.

Si vous avez accès à la console du BMC, regardez d'abord si l'hôte répond. Si vous me dites ce que vous voyez (BMC, `rbd status`), je peux vous aider à décider.