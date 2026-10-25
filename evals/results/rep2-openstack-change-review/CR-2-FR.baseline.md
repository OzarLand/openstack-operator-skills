Oui, il y a un vrai problème, et c'est l'étape « ménage ».

## Ne supprimez pas les anciennes clés

Les clés Fernet servent à chiffrer et à déchiffrer. Si vous gardez seulement la nouvelle primaire, tous les tokens émis avec les clés précédentes deviennent invalides. Concrètement :

- Les sessions Horizon et les jobs longs qui réutilisent un token sont déconnectés ou échouent en 401.
- La coupure dure au moins la durée de vie des tokens (`[token] expiration`, 1 h par défaut, et plus si vous l'avez allongée).
- Vous perdez aussi la clé staged (index 0), dont le rôle est de permettre à tous les nœuds de valider une future clé primaire avant qu'elle soit utilisée.

Le ménage est de toute façon automatique. `fernet_rotate` supprime les clés en trop selon `[fernet_tokens] max_active_keys` (3 par défaut). Si vous n'avez jamais tourné, vous avez probablement seulement les clés `0` et `1`, donc il n'y a rien à nettoyer.

## Plan corrigé

1. **Vérifier que les 3 nœuds sont synchrones avant de commencer.**
   `sha256sum /etc/keystone/fernet-keys/*` sur chaque nœud, avec des résultats identiques. C'est ce qui rend la rotation sûre. La future primaire est l'actuelle clé staged `0`, que keystone-2 et keystone-3 ont déjà. Ils peuvent donc valider les tokens émis par keystone-1 dès la rotation.
2. **Sauvegarder** `/etc/keystone/fernet-keys/` sur chaque nœud (`cp -a` ou `tar`).
3. **Rotation sur keystone-1** :
   `keystone-manage fernet_rotate --keystone-user keystone --keystone-group keystone`
   Il en sort une nouvelle clé staged `0`, l'ancienne `0` devient la primaire (index le plus élevé), et l'ancienne primaire devient secondaire.
4. **Distribuer** sans rien supprimer :
   `rsync -a --delete /etc/keystone/fernet-keys/ keystone-2:/etc/keystone/fernet-keys/`
   (idem pour keystone-3). `--delete` est acceptable ici car keystone-1 a le jeu de clés de référence.
   Vérifiez ensuite le propriétaire `keystone:keystone`, les droits `0600` sur les fichiers et `0700` sur le répertoire.
5. **Redémarrage : normalement inutile.** Keystone relit le dépôt de clés quand il change. Un restart est inoffensif en rolling, un nœud à la fois derrière le load balancer, mais ce n'est pas nécessaire.
6. **Contrôler** :
   - Obtenez un token sur chaque nœud et validez-le sur les deux autres.
   - Rechecksummez les 3 nœuds.

## Autres points

- **Ne touchez pas à `/etc/keystone/credential-keys/`.** C'est un autre dépôt, qui chiffre les credentials stockés. Une rotation mal faite peut les rendre illisibles.
- **Mettez en place une rotation régulière** avec un cron ou un timer sur un seul nœud, suivi du sync. Sinon vous retrouverez la même situation dans un an. Avec `max_active_keys=3` et des tokens d'1 h, une rotation hebdomadaire ou mensuelle suffit.
- **Si vous déployez avec kolla-ansible, TripleO ou OpenStack-Ansible**, utilisez leur mécanisme de rotation (par exemple `kolla-ansible fernet-rotate`, ou ce qui convient à votre outil). Un rsync manuel sera écrasé au prochain déploiement.

Si vous voulez, je peux vous écrire un script avec les vérifications de checksum, la sauvegarde, la rotation et le sync.