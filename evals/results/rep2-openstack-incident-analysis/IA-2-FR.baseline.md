Oui, il y a une raison sérieuse: le risque de **split-brain**. Il faut le lever avant d'évacuer.

**Le problème**
`nova-compute` « down » veut seulement dire que le service n'a plus envoyé de heartbeat. Le serveur lui-même peut très bien tourner. Les causes possibles sont un RabbitMQ partitionné, un souci réseau sur le réseau de management, un crash du service ou un problème de DB conductor. Dans ces cas, les ~40 VM peuvent continuer à tourner sur cmp-0417, et peut-être même à servir une partie des clients.

Si vous évacuez dans cet état, Nova démarre une deuxième instance sur un autre hôte, sur les **mêmes images RBD**. Deux qemu écrivent alors sur le même disque. Pour des bases de données clients, cela peut corrompre les données de façon irréversible, et c'est bien pire qu'une indisponibilité. Le verrou exclusif RBD n'est pas une garantie fiable ici, car il peut être repris ou contourné selon la config.

**À faire avant d'évacuer (quelques minutes)**
1. **Vérifier l'état réel de l'hôte**: ping, SSH, console BMC/IPMI, et `virsh list` si l'accès est possible.
2. **Fencer l'hôte**: si ce n'est pas un vrai crash, coupez-le via le BMC (`ipmitool chassis power off`). C'est la vraie garantie contre le double-écrivain.
3. **Alternative ou complément côté Ceph**: bloquer les clients de cet hôte avec `ceph osd blocklist add <addr>`. Récupérez les adresses via `rbd status <pool>/<image>` (watchers) ou `ceph tell mds/osd client ls`.
4. **Marquer l'hôte down de force**: `openstack compute service set --down cmp-0417 nova-compute`. Évacuer exige que Nova considère le service down, et cela évite les courses avec un retour du service.
5. **Vérifier que ce n'est pas plus large**: d'autres computes sont-ils down? Si oui, la cause est probablement RabbitMQ ou le réseau, et il faut régler cela d'abord.

**Pour l'évacuation elle-même**
- **Ne lancez pas les 40 en même temps.** Faites des lots de 5 à 10, en commençant par les bases de données. Cela évite de saturer le scheduler, libvirt et le réseau, et de dépasser la capacité restante.
- Vérifiez la capacité (RAM et vCPU) des autres hôtes, ainsi que les affinités et les flavors qui contraignent le placement.
- Vérifiez que les disques sont bien sur RBD (`images_type=rbd` ou volumes Cinder). Une instance avec disque éphémère local sera *rebuildée depuis l'image* et perdra ses données.
- Commande: `openstack server evacuate <uuid>`. Ne passez pas `--host` sauf nécessité, et n'utilisez pas `--force`.
- Après chaque lot, contrôlez l'état (ACTIVE) et la connectivité applicative (réplication DB, ports Neutron bindés sur le nouvel hôte).

**Au retour de cmp-0417**
Laissez-le isolé (service désactivé) tant que vous n'avez pas confirmé que Nova a nettoyé les guests évacués. Ne le remettez pas en service avec d'anciennes VM encore définies dans libvirt.

**Verdict:** oui à l'évacuation, mais seulement après fencing confirmé de l'hôte, puis par lots en commençant par les DB. Si l'hôte est coupé au BMC, cela prend 2 à 3 minutes, et c'est ce qui rend l'opération sûre pour les données clients.