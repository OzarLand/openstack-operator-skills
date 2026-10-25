**Non, je déconseille cette approche. Elle est dangereuse.**

**Le problème**
- Arrêter `nova-compute` n'arrête pas les VMs. Les qemu/libvirt continuent de tourner sur l'hôte. Nova ne fait que cesser de les gérer, et le service apparaît « down » après `service_down_time`.
- `evacuate` part du principe que l'hôte source est mort. Nova recrée donc chaque VM sur une autre machine, sur les **mêmes volumes RBD**, pendant que l'ancienne instance tourne encore.
- Vous avez alors deux guests qui écrivent sur le même disque, ce qui peut corrompre les données. Les exclusive-locks RBD réduisent le risque mais ne le suppriment pas, car sans fencing (blocklist) rien ne garantit l'exclusion.
- Au redémarrage de `nova-compute`, il détruit les instances évacuées. Entre-temps, vous avez eu une fenêtre de split-brain.
- Même quand tout se passe bien, `evacuate` reconstruit puis redémarre la VM. C'est l'équivalent d'un crash suivi d'un boot : la mémoire est perdue et les applications ne sont pas arrêtées proprement. Ce n'est donc pas plus propre qu'un cold migrate, et c'est bien plus risqué.

**Si vous voulez quand même passer par evacuate**, il faut que l'hôte soit vraiment mort :
1. Fencing : coupez l'hôte via IPMI/BMC (power off), pas seulement le service.
2. `openstack compute service set --down <host> nova-compute` (force-down).
3. `openstack server evacuate` des VMs.

Vous acceptez alors que toutes les VMs subissent un crash.

**Meilleures options pour accélérer la campagne**
1. **Cold migrate sur Ceph partagé** : `openstack server stop` suivi de `openstack server migrate`. Il n'y a aucune copie de données, donc c'est quasi instantané, avec quelques secondes ou minutes d'arrêt par VM. C'est probablement ce que votre collègue cherche.
2. **Tuner la live migration** :
   - `live_migration_permit_auto_converge = true` et `live_migration_permit_post_copy = true`, pour que les VMs à forte écriture mémoire convergent ;
   - `live_migration_completion_timeout` et `live_migration_downtime*` ajustés ;
   - un réseau de migration dédié ;
   - pas de tunnelling ;
   - `max_concurrent_live_migrations` relevé et plusieurs hôtes vidés en parallèle.
3. **Désactiver l'hôte avant de le vider** (`openstack compute service set --disable`) pour que le scheduler n'y place plus rien.
4. **Éviter de vider l'hôte** quand le patch ne l'exige pas : un simple redémarrage de `nova-compute` ou de libvirt laisse les VMs tourner. Seuls les patchs noyau/qemu en ont besoin.
5. **Segmenter par criticité** : live migration pour les VMs sensibles, cold migrate pour les VMs qui tolèrent un arrêt.

Je peux vous aider à écrire le script de drainage (disable, migrate par lots, vérification) si vous voulez.