## Résumé

**Verdict : pas prêt tel quel.** Le plan devient « prêt sous conditions » une fois l'étape 2 supprimée et les conditions ci-dessous remplies.

**Profondeur de revue :** complète. Keystone est le point d'authentification de toute la plateforme et une erreur casse tous les services d'un coup.

**Trois risques principaux :**
1. **L'étape 2 est dangereuse.** Supprimer toutes les clés sauf la primaire invalide immédiatement tous les jetons déjà émis, c'est-à-dire tous ceux signés avec l'ancienne clé primaire, qui devient secondaire après la rotation.
2. **Fenêtre d'incohérence entre nœuds.** Après `fernet_rotate` sur keystone-1 et avant le rsync, keystone-1 signe avec une clé primaire que keystone-2 et keystone-3 ne connaissent pas. Leurs validations échouent par intermittence selon le nœud que le LB choisit.
3. **Aucun retour arrière prévu.** Je n'ai vu ni sauvegarde des clés ni vérification de bout en bout dans votre plan.

## Ce qui ne va pas dans le plan

**Étape 2 : à supprimer.** La rotation fait déjà le ménage seule.
- Le répertoire contient une clé *staged* (index 0), une clé *primary* (l'index le plus élevé) et des clés *secondary*. Les secondaires ne servent qu'à valider les jetons existants.
- `fernet_rotate` promeut la staged en primaire, crée une nouvelle staged et supprime les clés au-delà de `max_active_keys`.
- Supprimer la staged ou les secondaires n'apporte rien et casse les jetons en cours.
- Conséquences : sessions Horizon coupées, automatisations et opérations longues en échec (upload d'image, volume, orchestration), pour tous les utilisateurs et services en même temps.
- Les caches memcached de keystonemiddleware peuvent retarder les échecs. Cela donne un tableau confus, avec des erreurs qui apparaissent progressivement.

**Étape 3, rsync :**
- N'utilisez pas `--delete`.
- Préservez propriétaire et droits (`-a`, utilisateur keystone, droits restrictifs, contexte SELinux si actif).
- Vérifiez ensuite par checksum que les trois nœuds ont des fichiers identiques.

**Étape 4, redémarrage :**
- Il est a priori inutile, car Keystone relit le répertoire de clés. C'est à vérifier pour votre version et votre mode de déploiement (Apache/mod_wsgi, conteneur).
- Un redémarrage simultané des trois nœuds coupe l'authentification. S'il est nécessaire, faites-le en rolling derrière le LB.

**Ce qui manque :**
- **Outil de déploiement :** s'il gère déjà les clés Fernet (le conteneur keystone-fernet de Kolla-Ansible, Puppet, Ansible…), une rotation manuelle peut entrer en conflit avec lui ou être écrasée à sa prochaine exécution. Je ne connais pas votre outil.
- **Clés de credentials :** `/etc/keystone/credential-keys` est un répertoire distinct. Ne le touchez pas.
- **Jamais tourné :** l'état actuel est inconnu. Les nœuds ont peut-être déjà des jeux de clés différents, et la rotation n'a jamais été testée ici.

## Décisions gates

| Gate | Statut | Preuve ou manque |
|---|---|---|
| Impact métier | unknown | Impact en cas d'échec et créneau non validés par le propriétaire. |
| Recovery | **fail** (plan actuel) | Pas de sauvegarde ni de retour arrière. L'étape 2 est un point de non-retour. |
| Evidence | unknown | Pas de test sur un environnement représentatif. Cohérence actuelle des clés non vérifiée. |
| Owner | unknown | Propriétaire de la capacité « authentification » non nommé. |
| Authority | unknown | Approbateur non nommé. |
| Blast radius | **fail** (plan actuel) | Tous les services et utilisateurs, instantanément. |
| Exigences obligatoires | unknown | Politique de rotation éventuelle non précisée. |

## Plan corrigé

**Avant (lecture seule) :**
1. Comparez les checksums de `/etc/keystone/fernet-keys/` sur les trois nœuds. Ils doivent être identiques.
2. Relevez `[fernet_tokens] max_active_keys` et `[token] expiration` (et `allow_expired_window` selon la version).
3. Identifiez l'outil de déploiement qui gère les clés.
4. Vérifiez qu'aucun autre changement n'est prévu dans la même fenêtre.
5. Sauvegardez le répertoire sur chaque nœud en préservant les droits (`tar -p`, copie hors nœud). Vérifiez que l'archive est lisible.

**Exécution (changement d'état) :**
1. Sortez keystone-1 du LB. Les nœuds 2 et 3 continuent de servir.
2. Sur keystone-1, lancez `keystone-manage fernet_rotate` avec l'utilisateur et le groupe keystone, comme dans votre procédure habituelle.
3. Faites un rsync sans `--delete` vers keystone-2 et keystone-3.
4. Comparez les checksums sur les trois nœuds.
5. Vérifiez la bonne émission et validation de jetons (voir ci-dessous), puis remettez keystone-1 dans le LB.
6. Ne supprimez aucune clé. Redémarrez uniquement si c'est nécessaire, en rolling.

Pendant l'étape 3, les nœuds 2 et 3 signent encore avec l'ancienne primaire. keystone-1 la garde comme secondaire, donc la validation croisée fonctionne.

## Retour arrière et point de non-retour

- **Méthode :** restaurer l'archive sur les trois nœuds. Cela n'a pas été exercé, donc à tester sur un nœud hors production si possible.
- **Point de non-retour :** la suppression de clés sans sauvegarde. Après `fernet_rotate`, le retour arrière reste possible tant que les anciens jetons n'ont pas expiré.
- **Condition pour supprimer les anciennes clés plus tard :** elles ne sont jamais supprimées à la main. Elles sortent seules lors des rotations suivantes, au-delà de `max_active_keys`. Prévoyez une durée supérieure à la durée de vie maximale des jetons.

## Conditions d'arrêt

- Les checksums divergent entre nœuds avant ou après le rsync.
- Un nœud rejette un jeton émis par un autre.
- La sauvegarde est absente ou illisible.
- Une hausse des 401 ou 5xx sur Keystone ou chez les services dépendants est visible dans votre supervision.
- L'outil de déploiement signale des conflits sur les clés.
- Le décideur n'est pas joignable.

## Vérification (à concevoir avant l'exécution)

- **Depuis chaque nœud, directement et pas via le LB :** émettre un jeton, puis le faire valider par les deux autres nœuds.
- **Jeton émis avant la rotation :** il doit rester valide après.
- **Capacité de bout en bout :** une opération réelle, par exemple créer une VM de test ou lister les ressources avec un compte de service.
- **Supervision :** pas de hausse des 401 et 5xx sur Keystone et chez les consommateurs.
- **Période d'observation :** au moins la durée de vie maximale d'un jeton plus l'expiration des caches. Les seuils sont à fixer d'après votre baseline, que je ne connais pas.

## Droits de décision

Je n'ai pas ces informations : évaluateur technique, propriétaire de la capacité, responsable et décideur. Il faut aussi nommer qui prévient les consommateurs, par exemple en cas de brève indisponibilité de l'authentification.

## Questions ouvertes

- Quel outil de déploiement gère les clés ?
- Quelle est la valeur de `max_active_keys` ?
- Quel LB, et pouvez-vous sortir un nœud proprement ?
- Quels autres changements sont prévus ce soir ?
- Où se trouve la sauvegarde et a-t-elle été restaurée au moins une fois ?

## Journal de décision (brouillon)

- **Changement :** première rotation Fernet sur 3 nœuds Keystone
- **Date :** ce soir (date exacte : unknown)
- **Propriétaire de la décision / de la capacité / évaluateur :** unknown

**Objectif :** rotation des clés qui n'ont jamais été tournées. Le risque traité (exposition d'une clé jamais renouvelée) est à préciser.

**État actuel :** non vérifié. Clés jamais tournées, cohérence entre nœuds inconnue.

**Incertitudes :** cohérence des clés, outil de déploiement, comportement au redémarrage, sauvegarde restaurable.

**Options écartées :** suppression des clés non primaires (rejet : invalide tous les jetons en cours, aucun bénéfice). Redémarrage simultané (rejet : coupe l'authentification).

**Retour arrière :** restauration de l'archive des clés sur les trois nœuds.

**Conditions d'arrêt et vérification :** voir ci-dessus.

**Suivi :** ajouter la rotation au calendrier de maintenance, la documenter dans un runbook et la rejouer sur un environnement de test.

> Decision support only. State-changing steps above require approval by the accountable owner and should be executed under your change process.

Si vous me donnez l'outil de déploiement et la valeur de `max_active_keys`, je peux rédiger le runbook exécutable.