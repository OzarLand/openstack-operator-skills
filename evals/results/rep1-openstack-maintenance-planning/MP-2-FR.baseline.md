**Non, je déconseille.** `evacuate` est fait pour un hôte déjà mort, pas pour un hôte qu'on met en maintenance.

**Le problème**
- Arrêter `nova-compute` n'arrête pas les VM. Les processus QEMU continuent de tourner sur l'hôte. Nova voit seulement que le service ne donne plus de heartbeat.
- `evacuate` ne vérifie pas que les VM sont réellement arrêtées. Il suppose que l'hôte est mort et recrée chaque instance ailleurs, sur le même disque RBD.
- Vous obtenez donc deux VM actives sur le même volume Ceph. C'est un split-brain, avec un risque réel de corruption de données. Le verrou exclusif RBD n'est pas une garantie sur laquelle s'appuyer.
- Même sans corruption, une évacuation fait un redémarrage à froid de chaque VM. Vous perdez l'état mémoire et vous avez une coupure, ce que la live migration évite.
- Au redémarrage de `nova-compute`, il nettoie les instances évacuées. Entre-temps, vous avez eu des doublons.

**Si vous voulez quand même évacuer, il faut fencer l'hôte**
Coupez-le par IPMI/BMC, ou au minimum arrêtez toutes les VM, avant d'évacuer. `openstack compute service set --down` évite d'attendre le heartbeat, mais ne fence rien. À ce stade, le gain face à une migration à froid est faible.

**Meilleures pistes pour accélérer**
1. **Réglages de live migration** (nova.conf, section `[libvirt]`)
   - `live_migration_permit_post_copy = true` : bascule rapidement même avec des VM qui écrivent beaucoup en mémoire.
   - `live_migration_permit_auto_converge = true`.
   - `live_migration_bandwidth = 0` : pas de limite.
   - Un réseau dédié à la migration, via `live_migration_inbound_addr`.
2. **Parallélisme** : montez `max_concurrent_live_migrations` et videz plusieurs hôtes en même temps, par lots.
3. **Cold migrate** (`openstack server migrate`) pour les VM qui tolèrent une courte coupure. Avec Ceph partagé, il n'y a aucune copie de disque, donc c'est rapide et sans risque de split-brain.
4. **Tri des VM** : live-migrer seulement les VM critiques, et arrêter proprement ou cold-migrer les autres (dev, batch).

Si la lenteur vient de quelques VM très actives, le post-copy règle généralement le problème. Dites-moi ce qui ralentit chez vous (RAM volumineuse, taux d'écriture, bande passante) et je pourrai être plus précis.