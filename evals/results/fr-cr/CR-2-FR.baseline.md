Oui, une étape est dangereuse : le « ménage ». Le reste est correct mais perfectible.

## Le problème : supprimer toutes les clés sauf la primaire

Après `fernet_rotate` sur un dépôt jamais tourné, vous avez :

| Fichier | Rôle |
|---|---|
| `0` | nouvelle clé *staged* (créée par la rotation) |
| `1` | ancienne primaire, devenue secondaire |
| `2` | nouvelle primaire (l'ancienne staged promue) |

Si vous ne gardez que `2`, vous supprimez `1`. Tous les tokens émis avant la rotation deviennent invalides, donc 401 pour tous les utilisateurs et services. Les opérations longues en cours (Heat, Nova, Cinder, etc.) peuvent échouer. Vous supprimez aussi `0`, qui sert à distribuer la prochaine clé avant sa promotion.

Gardez toutes les clés. `fernet_rotate` purge déjà les plus anciennes au-delà de `max_active_keys` (3 par défaut). Si vous voulez vraiment faire le ménage, supprimez les secondaires seulement après la durée de vie maximale des tokens (`[token] expiration`, 1 h par défaut, plus la fenêtre de renouvellement).

## Autres points

1. **Vérifiez d'abord que les 3 nœuds sont identiques.** Comparez par exemple `sha256sum /etc/keystone/fernet-keys/*` sur chacun. Des clés déjà divergentes sont une cause fréquente de 401 intermittents.
2. **Sauvegardez** `/etc/keystone/fernet-keys/` sur les 3 nœuds avant de commencer.
3. **rsync :**
   - Utilisez `-a --delete` pour que les nœuds 2 et 3 soient un miroir exact.
   - Vérifiez ensuite le propriétaire (`keystone:keystone`), le mode du répertoire (`700`) et celui des fichiers (`600`).
   - Si vous synchronisez en root, ajoutez `--chown`, ou corrigez après coup.
4. **Le redémarrage est inutile.** Keystone relit le dépôt de clés à l'exécution. Un redémarrage coupe du trafic sans rien apporter. Si vous voulez le faire, faites-le nœud par nœud derrière le load balancer.
5. **Ordre idéal :** comme la clé *staged* (`0`) est déjà présente partout, tout nœud peut valider les tokens signés par la nouvelle primaire après la synchro. Le plus sûr reste de synchroniser rapidement après la rotation. Pendant la fenêtre où seul keystone-1 a la nouvelle primaire, les tokens qu'il émet échouent sur les autres nœuds.
6. **Gestion de configuration :** si Ansible, Puppet, Kolla ou Juju gère ce répertoire, il peut écraser vos fichiers. Faites alors la rotation par ces outils.
7. **Ne touchez pas à `credential-keys/`.** C'est un dépôt distinct, avec d'autres conséquences en cas d'erreur.
8. **Après la rotation :** testez un `openstack token issue` sur chaque nœud, ou directement via chaque backend. Planifiez ensuite une rotation régulière (cron sur un seul nœud, suivi d'une synchro), car le plus gros risque aujourd'hui est que la rotation reste ponctuelle.

## Plan corrigé

```bash
# 1. Sauvegarde + comparaison des checksums sur les 3 nœuds
# 2. keystone-1 :
keystone-manage fernet_rotate --keystone-user keystone --keystone-group keystone
# 3. Synchro immédiate :
rsync -a --delete /etc/keystone/fernet-keys/ keystone-2:/etc/keystone/fernet-keys/
rsync -a --delete /etc/keystone/fernet-keys/ keystone-3:/etc/keystone/fernet-keys/
# 4. Vérifier propriétaire, droits et checksums, puis tester l'émission et la validation de tokens sur chaque nœud
# (pas de suppression de clés, pas de restart)
```