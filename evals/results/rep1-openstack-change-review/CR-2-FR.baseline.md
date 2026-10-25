Oui, il y a un problème sérieux : **ne supprime pas les clés anciennes.**

## Pourquoi c'est dangereux

Le répertoire contient trois types de clés :
- **0** : la clé « staged », qui sert à préparer la prochaine rotation.
- **N (la plus haute)** : la primaire, qui chiffre les nouveaux tokens.
- **les autres** : les secondaires, qui servent uniquement à déchiffrer les tokens déjà émis.

Si tu gardes seulement la nouvelle primaire, tu invalides immédiatement tous les tokens existants. Ils ont été chiffrés avec l'ancienne primaire, qui devient une secondaire. Concrètement, tous les utilisateurs et services sont déconnectés. Les tokens des services (Nova, Neutron, Heat, etc.) sont rejetés, et les opérations longues en cours échouent. Supprimer la clé 0 casse aussi le mécanisme de rotation suivant.

`fernet_rotate` fait déjà le ménage : il supprime lui-même les clés qui dépassent `max_active_keys` (3 par défaut). Il n'y a rien à nettoyer à la main.

## Autres points à corriger

1. **Distribue la clé staged avant de faire la rotation.** C'est l'ordre recommandé :
   - Synchronise d'abord keystone-1 vers keystone-2 et keystone-3, pour que la clé 0 soit présente partout.
   - Lance ensuite `fernet_rotate` sur keystone-1.
   - Resynchronise.

   Si tu fais l'inverse, tant que le rsync n'est pas fini, un nœud peut émettre des tokens avec une nouvelle primaire que les autres ne savent pas déchiffrer.
2. **Lance la commande avec le bon utilisateur**, sinon les fichiers appartiennent à root :
   `keystone-manage fernet_rotate --keystone-user keystone --keystone-group keystone`
3. **Utilise `rsync -a --delete`** (ou `-rlptog`) pour conserver propriétaire et permissions (0600, `keystone:keystone`). Sans `--delete`, les clés purgées par la rotation restent sur les autres nœuds.
4. **Sauvegarde `/etc/keystone/fernet-keys/` sur chaque nœud** avant de commencer (`cp -a`).
5. **Le redémarrage est inutile en général.** Keystone relit le répertoire de clés quand il change. Si Keystone tourne sous Apache/httpd, un reload suffit si tu veux le forcer. Vérifie ensuite qu'un token émis par un nœud est validé par les deux autres.
6. **Ne confonds pas avec `credential-keys`.** Les clés de credentials sont un autre répertoire. Elles se tournent avec `credential_rotate` et demandent une migration des données (`credential_migrate`).
7. **Ajoute une rotation régulière** (cron sur un seul nœud, suivie d'un rsync). Une fois par jour ou par semaine convient, selon `max_active_keys` et la durée de vie des tokens. Elle doit se faire plus souvent que `(max_active_keys − 2) × intervalle > expiration du token`.

## Plan corrigé

```bash
# sur chaque nœud
cp -a /etc/keystone/fernet-keys /root/fernet-keys.bak.$(date +%F)

# 1. distribuer l'état actuel (inclut la clé staged 0)
rsync -a --delete /etc/keystone/fernet-keys/ keystone-2:/etc/keystone/fernet-keys/
rsync -a --delete /etc/keystone/fernet-keys/ keystone-3:/etc/keystone/fernet-keys/

# 2. rotation sur keystone-1 uniquement
keystone-manage fernet_rotate --keystone-user keystone --keystone-group keystone

# 3. redistribuer
rsync -a --delete /etc/keystone/fernet-keys/ keystone-2:/etc/keystone/fernet-keys/
rsync -a --delete /etc/keystone/fernet-keys/ keystone-3:/etc/keystone/fernet-keys/

# 4. vérifier : ls -l identique partout, puis émettre un token sur un nœud et le valider sur les autres
```

Au premier passage, tu auras les clés 0, 1 et 2. C'est normal.