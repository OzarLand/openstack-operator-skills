Oui, il y a une raison sérieuse d'attendre : **ne lancez pas l'évacuation tant que l'hôte n'est pas fencé.** C'est ce qui sépare un rétablissement rapide d'une corruption de données chez les clients.

## Situation
- **Capacité perdue** : environ 40 VM sur cmp-0417 injoignables, dont des bases de données clients.
- **Observé** : `nova-compute` sur cmp-0417 est « down » depuis 03:12 (d'après vous, sans sortie montrée).
- **Rapporté** : les VM sont injoignables, leurs disques sont sur Ceph.
- **Inconnu** : l'état réel de l'hôte, ce qui a changé avant 03:12, et la criticité de chaque VM.

## Pourquoi pas tout de suite
« nova-compute down » veut seulement dire que le heartbeat a disparu. Nova ne sait pas si l'hôte est mort ou simplement isolé du plan de contrôle. Plusieurs cas donnent exactement le même symptôme :
- le service `nova-compute` a planté alors que libvirt et les VM tournent toujours ;
- l'hôte est coupé de RabbitMQ ou de la base, mais les VM tournent et gardent leur accès à Ceph ;
- l'hôte est réellement éteint ou en panne.

Si les VM tournent encore et que vous évacuez, **chaque VM existera en double**. Les deux copies écrivent sur le même volume RBD. Pour des bases de données clientes, cela peut corrompre les données sans retour possible.

Le fait que le stockage soit sur Ceph rend l'évacuation rapide, mais c'est aussi ce qui rend le double accès en écriture possible. Ce risque est la raison d'être du fencing.

## Séquence recommandée
1. **Confirmer l'état de l'hôte** (read-only). Interrogez le BMC (IPMI/iDRAC/Redfish) pour connaître son état d'alimentation. Vous pouvez aussi vérifier si l'hôte répond (ping, SSH, console).
   - **Si l'hôte est vivant** : ne l'évacuez pas. Regardez d'abord pourquoi `nova-compute` est down (`systemctl status`, journaux de `nova-compute` et de libvirt, connectivité vers RabbitMQ). Si les VM tournent encore, redémarrer le service peut tout rétablir sans rien déplacer.
   - **Si l'hôte est mort ou en panne** : passez à l'étape 2.
2. **Fencer** : éteindre l'hôte via le BMC (ou l'isoler au niveau du switch), puis vérifier l'état d'alimentation. *(state-changing)*
3. **Forcer le service down** : `openstack compute service set --down cmp-0417 nova-compute`, microversion ≥ 2.11 (à vérifier pour votre version). *(state-changing)*
4. **Évacuer instance par instance, pas les 40 d'un bloc.** L'ordre se fixe avec les propriétaires : bases clients d'abord, puis le reste. Pour chacune, vérifiez qu'elle est active sur le nouvel hôte, joignable, et que les données sont cohérentes.
5. **Vérifier la capacité restante avant de lancer.** Les 40 VM doivent tenir sur les autres hôtes, sinon les évacuations échouent ou saturent le reste de la flotte.
6. **Au retour de cmp-0417** : gardez-le désactivé et forced-down. Démarrez `nova-compute`, attendez qu'il ait nettoyé les copies locales des VM évacuées, puis faites `--up` et `--enable` en deux étapes séparées. Un retour trop tôt recrée le risque de double copie.

## Vérifications avant de décider (read-only)
- État d'alimentation de cmp-0417 via le BMC.
- `openstack compute service list --service nova-compute` : est-ce le seul hôte down ? Si plusieurs sont down en même temps, la cause est plutôt RabbitMQ, la base ou le réseau, et il ne faut surtout pas évacuer en masse.
- Qu'est-ce qui s'est passé vers 03:12 : alertes matérielles, déploiement, maintenance réseau ? Les VM ont-elles été signalées par les clients à la même heure ?
- Côté Ceph : `rbd status <pool>/<image>` sur un disque de VM concerné. Si un watcher est encore présent, la VM tourne probablement toujours.

## Décision et responsabilité
L'astreinte a raison de vouloir rétablir vite, et le fencing prend quelques minutes avec un BMC qui répond. Le coût d'attendre est du temps d'indisponibilité en plus, alors que le coût d'une erreur est la perte de données clients, sans retour arrière. Si le BMC est lui aussi injoignable, c'est un blocage à escalader : le propriétaire de l'infrastructure doit décider d'une autre méthode d'isolation (switch, coupure d'alimentation par le datacenter). Ne contournez pas cette étape.

Il me manque : l'état BMC, la liste des services compute down, la capacité libre sur les autres hôtes, et qui décide de l'évacuation.

> Decision support only. State-changing steps above require approval by the accountable owner and should be executed under your change process.