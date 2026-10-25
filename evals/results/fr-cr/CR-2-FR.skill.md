**Oui, vous oubliez des choses, et l'étape 2 («ménage») est dangereuse. Verdict : pas prêt tel quel. Avec le plan corrigé ci-dessous, ça devient «prêt sous conditions».**

Je n'ai rien vérifié sur votre plateforme. Tout ce qui suit repose sur votre description et sur le fonctionnement standard de Keystone. Vérifiez les points propres à votre release.

## Ce qui ne va pas

**1. Supprimer toutes les clés sauf la nouvelle primaire casse l'authentification.**
- Les clés secondaires servent à valider les tokens déjà émis. Si vous les supprimez, tous les tokens en cours deviennent invalides en même temps, sur tous les services.
- Cela touche les sessions Horizon, les opérations longues (Heat, snapshots, migrations) et les tokens de service.
- Supprimer aussi la clé *staged* (index 0) casse le mécanisme de distribution progressive décrit au point 2.
- Pas de «ménage» manuel. `max_active_keys` (3 par défaut, à vérifier chez vous) supprime déjà les plus anciennes clés à chaque rotation suivante.
- Après la suppression il n'y a pas de retour arrière : c'est le point de non-retour. Gardez les anciennes clés au moins pendant `token.expiration` plus `allow_expired_window`. Vérifiez ces deux valeurs chez vous.

**2. L'ordre de distribution crée une fenêtre de panne.**
- Dès que keystone-1 a fait `fernet_rotate`, il signe avec la nouvelle clé primaire. Keystone-2 et keystone-3 ne la connaissent pas encore, donc ils rejettent ces tokens tant que le rsync n'est pas terminé.
- Avec un load balancer devant, une partie des requêtes échoue pendant ce temps.
- La procédure upstream évite ça avec la clé *staged*. Faites d'abord un `fernet_rotate` sur un nœud, distribuez le répertoire à tous les nœuds, et c'est seulement ensuite que les nouvelles clés deviennent effectives partout.
- Concrètement : avant la rotation, les trois nœuds ont déjà la même clé 0 (staged). Vous pouvez donc faire la rotation sur keystone-1, puis copier tout de suite. La fenêtre est courte mais pas nulle, donc faites-le hors pic ou sortez keystone-1 du load balancer le temps de la copie.

**3. Vous n'avez pas vérifié l'état de départ.**
- «Jamais tournées» ne dit pas que les trois nœuds ont aujourd'hui les mêmes clés. Comparez les checksums des fichiers (`sha256sum`, jamais le contenu).
- Ne supposez pas que keystone-1 est la bonne source tant que ce n'est pas vérifié.

**4. Détails d'exécution du rsync.**
- Conservez propriétaire `keystone:keystone` et permissions strictes (répertoire 0700, fichiers 0600) : `rsync -a` ou `--chown` et `--chmod`.
- Utilisez `--delete` seulement pour aligner sur la source, pas pour faire du ménage.
- Faites le transfert via un canal chiffré (ssh). Ces clés sont des secrets.
- Un redémarrage de Keystone est en général inutile : il relit le répertoire de clés. Vérifiez pour votre release avant de décider. Un redémarrage simultané des trois nœuds augmente le risque pour rien.

**5. Déploiement avec Kolla ou conteneurs.**
- Si vous utilisez Kolla-Ansible, le chemin est dans le conteneur `keystone_fernet`, et il a son propre mécanisme de rotation et de synchronisation (cron + ssh/rsync). Un rsync manuel peut se battre avec lui.
- Vérifiez ce que vous utilisez avant de lancer quoi que ce soit.

**6. Pas de sauvegarde ni de rollback prévus.**
- Sauvegardez le répertoire de clés de chaque nœud avant de commencer (archive protégée, car ce sont des secrets).
- Définissez la vérification avant d'exécuter.

## Plan corrigé

1. **Lecture seule :** sur les 3 nœuds, comparez le contenu du répertoire (liste des fichiers, checksums, propriétaire, permissions). Relevez `max_active_keys`, `token.expiration` et `allow_expired_window`. Vérifiez la synchronisation de l'heure et si Kolla gère la rotation.
2. **Sauvegarde** du répertoire de clés sur chaque nœud, stockée de façon sécurisée.
3. **État modifié :** `keystone-manage fernet_rotate` sur keystone-1 seulement (utilisateur `keystone`).
4. **État modifié :** distribution immédiate vers keystone-2 et keystone-3 avec `rsync -a`, sans `--delete` sauf si vous alignez les nœuds sur la source. Pas de suppression de clés.
5. **Vérification :** demandez un token sur chaque nœud en direct (sans passer par le load balancer) et validez-le sur chacun des deux autres nœuds, pour toutes les paires. Faites ensuite un test de bout en bout : créer une ressource simple, lister des VMs, une connexion Horizon. Surveillez les erreurs 401 dans les logs Keystone et ceux des autres services.
6. **Observation :** gardez les anciennes clés au moins une durée de vie de token plus la fenêtre d'expiration. Ne nettoyez rien à la main.
7. **Après :** mettez en place une rotation planifiée et testée (cron, ou la tâche Kolla) avec un responsable nommé. Sinon, dans un an, vous serez dans la même situation.

**Conditions d'arrêt :**
- Les checksums des trois nœuds divergent au départ.
- Le token d'un nœud n'est pas validé par un autre.
- Un pic de 401 apparaît après la rotation. Dans ce cas, restaurez la sauvegarde du répertoire sur le nœud concerné, ce qui reste possible tant que vous n'avez rien supprimé.

## Inconnu (à confirmer de votre côté)

- Responsable de la capacité Keystone et personne qui approuve le changement.
- Date de la fenêtre et autres changements prévus le même soir.
- Méthode de déploiement (Kolla, package, autre).
- Valeurs de `max_active_keys`, `token.expiration` et `allow_expired_window`.
- Existence d'un environnement de test où répéter la rotation.
- Services avec des opérations longues dans la fenêtre.

> Decision support only. State-changing steps above require approval by the accountable owner and should be executed under your change process.