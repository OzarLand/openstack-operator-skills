## Oui : ne lancez pas `evacuate` sur les 40 VM pour l'instant

**Une alerte "down" n'est pas la preuve que l'hôte est mort.** Elle prouve seulement que nova-compute ne rapporte plus de heartbeat. Nova ne peut pas savoir si cmp-0417 est éteint ou seulement isolé du plan de contrôle, par exemple à cause d'un problème réseau de management, d'un bus de messages défaillant ou d'un nova-compute planté pendant que libvirt tourne encore.

Si l'hôte tourne encore et que vous évacuez, chaque VM aura **deux copies actives sur les mêmes volumes Ceph**. Sur des bases de données clients, cela veut dire corruption de données, sans retour arrière. Que les disques soient sur Ceph rend l'évacuation rapide, mais c'est justement ce qui rend le risque d'écriture concurrente réel. Cela confirme le besoin de fencing et ne le remplace pas.

### Ce qu'il faut faire à la place (dans l'ordre)

1. **Vérifier l'état réel de l'hôte, en lecture seule.**
   - Lisez l'état d'alimentation par le BMC/IPMI/Redfish de cmp-0417.
   - Regardez si l'hôte répond au ping et en SSH, et si les VM répondent ou si leurs ports Neutron sont actifs.
   - Vérifiez dans les logs de nova-compute et de RabbitMQ pourquoi le heartbeat s'est arrêté à 03:12.
2. **Vérifier que le problème n'est pas plus large.** Les autres computes sont-ils tous "up" ? Si plusieurs services paraissent cassés en même temps, le suspect est le bus ou la base de données. Dans ce cas, évacuer en masse aggraverait l'état.
3. **Fencer l'hôte** si la VM tourne encore ou si l'état est incertain. Coupez l'alimentation via le BMC ou isolez-le au niveau du switch, puis confirmez l'état éteint.
4. **Marquer le service forced down** (*state-changing*) : `openstack compute service set --down cmp-0417 nova-compute`. Vérifiez la commande et la microversion pour votre release.
5. **Évacuer VM par VM, par ordre de criticité métier.** Commencez par les bases de données clients, avec l'accord de leurs propriétaires. Vérifiez chaque VM (ACTIVE sur le nouvel hôte, joignable, données cohérentes) avant de passer à la suivante, plutôt que de lancer les 40 d'un coup. Gardez la capacité disponible en tête : 40 VM d'un coup peuvent saturer les autres hôtes.
6. **Si l'hôte revient plus tard**, laissez-le disabled et forced down jusqu'à ce que nova-compute ait nettoyé les copies locales des VM évacuées. Ne le réactivez qu'ensuite, étape par étape.

### Si l'hôte est confirmé éteint

Le fencing est alors déjà fait. Vous pouvez passer directement aux étapes 4 et 5, et cela prend quelques minutes. Le surcoût de la vérification est donc faible face au risque.

### Ce que je ne sais pas (à me donner ou à vérifier)

- L'état BMC de cmp-0417, la sortie de `openstack compute service list` pour tous les hôtes, et les logs de nova-compute autour de 03:12 (masquez les mots de passe et les `transport_url`).
- Ce qui a changé récemment (maintenance, déploiement, réseau).
- Si l'hôte est en cellule ou en AZ avec assez de capacité pour 40 VM.
- Quels clients sont les plus critiques, et qui, côté astreinte ou direction, a l'autorité pour décider de l'évacuation. Ce n'est pas à moi de l'autoriser.

Si vous me collez ces sorties, je vous aide à trancher entre "hôte mort, on évacue" et "problème plus large, on enquête d'abord".

> Decision support only. State-changing steps above require approval by the accountable owner and should be executed under your change process.