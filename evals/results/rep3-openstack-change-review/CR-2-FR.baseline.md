Oui, il y a un vrai problème dans l'étape « ménage », et quelques oublis autour.

## Ne supprimez pas les anciennes clés

`fernet_rotate` fait ceci :
- La clé **staged** (`0`) est promue primaire, avec l'index le plus élevé.
- L'ancienne primaire devient secondaire. Elle sert à **valider** les tokens déjà émis.
- Une nouvelle clé staged `0` est créée.

Si vous ne gardez que la nouvelle primaire :
- **Tous les tokens en cours deviennent invalides** : sessions Horizon, tokens de service (nova, neutron, etc. qui valident ou réutilisent des tokens), opérations longues. Ça se traduit par des 401 en cascade.
- Vous perdez aussi la clé **staged**. Or elle sert à ce que tous les nœuds connaissent la prochaine primaire avant sa promotion.

Le ménage est de toute façon automatique. `[fernet_tokens] max_active_keys` (3 par défaut) fait que `fernet_rotate` purge les clés en trop. Vous n'avez rien à supprimer à la main.

Si vous voulez vraiment retirer l'ancienne clé, faites-le plus tard : après une durée supérieure à `[token] expiration` (1 h par défaut), et en gardant la staged.

## Autres points à corriger

1. **Fenêtre d'incohérence.** Après la rotation sur keystone-1, ce nœud signe avec une nouvelle primaire que keystone-2 et keystone-3 n'ont pas encore. Les tokens émis par keystone-1 seront rejetés ailleurs jusqu'au rsync.
   - Retirez keystone-1 du load balancer pendant l'opération, ou enchaînez rotate et rsync immédiatement.
   - Pour la toute première rotation, vous pouvez aussi copier d'abord les clés actuelles vers les autres nœuds si vous n'êtes pas sûr qu'elles soient identiques.
2. **Vérifiez l'état de départ.** Comparez `sha256sum /etc/keystone/fernet-keys/*` sur les 3 nœuds avant de commencer. « Jamais tournées » ne garantit pas qu'elles sont identiques.
3. **Sauvegardez** le répertoire des clés sur chaque nœud : `cp -a /etc/keystone/fernet-keys /root/fernet-keys.bak-$(date +%F)`.
4. **rsync :**
   - Utilisez `-a --delete` pour préserver propriétaire et droits (`keystone:keystone`, dossier `0700`, clés `0600`) et supprimer les clés obsolètes côté destination.
   - Pour ça, il faut un transfert en root ou un `--chown`.
   - Contrôlez les checksums après coup.
5. **Redémarrage.** Keystone tourne en général sous Apache ou httpd en WSGI, donc il n'y a souvent pas de service `keystone` à redémarrer. Keystone recharge les clés depuis le disque, et un reload du serveur web suffit au besoin. Sur Kolla ou OSA, c'est le conteneur ou le service wsgi.
6. **Gestion du déploiement.** Si les clés sont gérées par kolla-ansible, OSA, Puppet ou Juju, utilisez leur mécanisme (ex. `kolla-ansible ... fernet-rotate`), sinon le prochain run écrasera vos changements.
7. **Clés de credentials.** Les clés `credential-keys` (`/etc/keystone/credential-keys`) sont un dépôt séparé. Ne les mélangez pas.
8. **Automatisation.** Prévoyez une rotation périodique (cron ou timer) avec la même synchronisation. Sinon, vous reviendrez dans le même état dans un an.

## Plan corrigé

1. Sauvegarde et vérification des checksums sur les 3 nœuds.
2. Retrait de keystone-1 du LB (ou fenêtre courte).
3. Sur keystone-1 : `keystone-manage fernet_rotate --keystone-user keystone --keystone-group keystone`.
4. `rsync -a --delete /etc/keystone/fernet-keys/ keystone-2:/etc/keystone/fernet-keys/`, puis pareil vers keystone-3.
5. Contrôle des checksums et des droits, puis reload du serveur web sur les 3 nœuds.
6. Remise en service, puis test de validation de token croisé : émettre sur un nœud, valider sur les autres.
7. Aucune suppression manuelle.

Je peux vous écrire le script (rotate, rsync, vérifs) si vous voulez.