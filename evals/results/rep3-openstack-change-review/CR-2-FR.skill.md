## Résumé

**Verdict : pas prêt tel quel.** Une étape (le « ménage ») échoue à la porte « Recovery » et peut casser l'authentification de toute la plateforme d'un coup. Sans cette étape, le plan devient « prêt avec conditions ». Le reste est simple, mais il manque quelques précautions.

**Profondeur de la revue :** moyenne. L'opération est routinière et réversible si on garde les anciennes clés. Mais Keystone est une dépendance de tous les services, et vos clés n'ont jamais été tournées, donc la procédure n'a jamais été testée chez vous.

**Les 3 risques principaux :**
1. Supprimer toutes les clés sauf la nouvelle primaire invalide tous les jetons en cours de validité.
2. Les trois nœuds peuvent avoir des jeux de clés différents. Vous ne l'avez pas vérifié (*unknown*).
3. Un redémarrage simultané des 3 Keystone coupe l'authentification. Il est probablement inutile.

## 1. Ce qui ne va pas dans le plan

**Étape 2 : supprimer toutes les clés sauf la nouvelle primaire. À ne pas faire.**
- Vos clés n'ont jamais été tournées. Vous avez donc probablement `0` (staged) et `1` (primaire). *Hypothèse : à confirmer avec `ls -l /etc/keystone/fernet-keys/`.*
- Après `fernet_rotate`, vous aurez :
  - `0` : nouvelle clé staged ;
  - `1` : ancienne primaire, devenue secondaire ;
  - `2` : nouvelle primaire.
- Supprimer `0` et `1` rend illisibles tous les jetons émis avec l'ancienne primaire. Les utilisateurs et les sessions Horizon sont éjectés, et les opérations longues qui réutilisent un jeton échouent. Les services se ré-authentifient seuls, avec des erreurs 401 transitoires.
- Les clés secondaires servent justement à valider les jetons encore valides. `max_active_keys` (3 par défaut, *à vérifier pour votre release*) élague déjà automatiquement les plus anciennes aux rotations suivantes. Le « ménage » manuel n'apporte rien.
- Si vous voulez vraiment nettoyer un jour, attendez que le plus vieux jeton émis avec l'ancienne clé soit expiré. Cela veut dire plus que `[token] expiration`: ajoutez la fenêtre `allow_expired_window` et la durée de vie des jetons de vos outils longs.

**Étape 3 : rsync et redémarrage.**
- **Redémarrage probablement inutile.** Keystone relit le dépôt de clés. *À vérifier pour votre release et votre déploiement.* S'il faut redémarrer, faites-le un nœud à la fois derrière le load balancer, en vérifiant la santé entre chaque.
- **Pas de rsync aveugle.**
  - Gardez le propriétaire `keystone` et les permissions `0600`/`0700`.
  - Évitez `--delete`, ou faites un `--dry-run` avant.
  - Vérifiez que votre outil de déploiement (Kolla-Ansible, Puppet, etc.) ne réécrit pas ce répertoire. Sinon il annule votre travail ou désynchronise les nœuds.
- **Ne touchez pas à `credential-keys/`.** C'est un autre dépôt de clés, avec d'autres règles.

## 2. Plan corrigé

| # | Étape | Type |
|---|---|---|
| 0 | Comparer les clés des 3 nœuds : `sha256sum /etc/keystone/fernet-keys/*` sur chacun, avec les noms de fichiers. Elles doivent être identiques. Si elles diffèrent, arrêtez-vous : la plateforme a déjà un problème latent. | read-only |
| 1 | Sauvegarder le répertoire sur les 3 nœuds (`tar` en conservant propriétaire et permissions), puis tester la lecture de la sauvegarde. | read-only (écriture dans un répertoire à part) |
| 2 | Relever les paramètres : `[token] expiration`, `allow_expired_window`, `[fernet_tokens] max_active_keys`, et l'éventuel gestionnaire de config des clés. | read-only |
| 3 | Test de base avant : émettre un jeton sur chaque nœud, en direct sans passer par le LB, et le valider sur les deux autres. | read-only |
| 4 | `keystone-manage fernet_rotate` sur keystone-1 (avec `--keystone-user` / `--keystone-group` si besoin). | state-changing |
| 5 | Distribuer le répertoire vers keystone-2 et keystone-3 immédiatement, avec propriétaire et permissions conservés. | state-changing |
| 6 | Vérifier les checksums identiques sur les 3 nœuds. | read-only |
| 7 | Refaire le test croisé de l'étape 3, dans les deux sens, y compris la validation d'un jeton émis avant la rotation. | read-only |
| 8 | Contrôle de bout en bout : par exemple une création de VM ou de volume, un `openstack token issue` depuis un client, et un appel Nova/Glance/Neutron. | read-only |
| 9 | Ne rien supprimer. Garder la sauvegarde jusqu'à la fin de la période d'observation. | – |

**Pourquoi l'ordre 4→5 est acceptable.** L'ancienne clé staged (`0`) existe déjà sur les nœuds 2 et 3 si les nœuds étaient synchronisés. C'est justement la clé qui devient primaire sur keystone-1. Les jetons émis par keystone-1 restent donc validables par les autres pendant la fenêtre. **Ce raisonnement n'est vrai que si l'étape 0 est vérifiée.** Sinon, une partie des 401 apparaît dès l'étape 4.

## 3. Porte de décision

| Porte | Statut | Remarque |
|---|---|---|
| Business impact | unknown | L'échec touche l'authentification de toute la plateforme. À valider par le responsable. |
| Recovery | **fail** pour le plan initial, pass possible pour le plan corrigé | Après suppression des clés, la restauration n'est possible que si la sauvegarde existe et a été testée (*unknown*). |
| Evidence | unknown | Pas testé en pré-production. Pas d'état actuel des clés montré. |
| Owner | unknown | Qui possède Keystone chez vous ? |
| Authority | unknown | Qui approuve ce soir ? |
| Blast radius | pass avec conditions | Limité par le jeu de clés conservé et le redémarrage progressif. |
| Mandatory requirements | unknown | Une politique de rotation imposée peut exister. À confirmer. |

## 4. Récupération et point de non-retour

- **Méthode.** Restaurer le répertoire sauvegardé sur les 3 nœuds. Ça fonctionne tant qu'aucune clé n'a été supprimée sans sauvegarde.
- **Point de non-retour.** Suppression des clés sans sauvegarde, ou rotations successives qui élaguent l'ancienne primaire via `max_active_keys`. Ne tournez pas une deuxième fois avant la fin de l'observation.
- **Exercé ?** Non (*unknown*). Faites au moins une restauration à blanc de la sauvegarde.

## 5. Conditions d'arrêt

- Les checksums diffèrent à l'étape 0 ou 6.
- Un jeton émis par un nœud n'est pas validé par un autre.
- Le taux de 401 (logs Keystone ou HAProxy) monte au-delà de votre référence habituelle.
- Les messages « Could not recognize Fernet token » ou « Unable to validate token » apparaissent en continu.
- Vous ne pouvez plus restaurer (sauvegarde illisible, nœud injoignable).
- Un autre changement prévu ce soir interfère. Ne cumulez pas.

## 6. Vérification et observation

- Les tests croisés des étapes 3, 7 et 8.
- Surveiller les 401 et la latence de Keystone pendant au moins la durée de vie maximale de vos jetons. Les seuils sont les vôtres : donnez-moi vos références si vous voulez que je les fixe.
- Observer aussi un moment après l'expiration des jetons émis avant la rotation.

## 7. Droits de décision

Assesseur technique, responsable de la capacité (Keystone/IAM), responsable de l'issue et décideur : **unknown**, à nommer. Qui prévient les utilisateurs en cas d'éjection de session ?

## 8. Questions ouvertes

1. Que montrent `ls -l /etc/keystone/fernet-keys/` et les checksums sur les 3 nœuds ?
2. Quelles sont vos valeurs de `expiration`, `allow_expired_window` et `max_active_keys` ?
3. Qui gère ce répertoire : Kolla-Ansible, Puppet, à la main ?
4. Keystone tourne-t-il en conteneur ou sous Apache/uwsgi ? Quelle est la méthode de redémarrage ?
5. Avez-vous un environnement de test ?
6. Y a-t-il des tâches longues ce soir (migrations, backups, pipelines CI) qui réutilisent des jetons ?

## 9. Enregistrement de décision (brouillon)

- **Changement :** première rotation Fernet Keystone, 3 nœuds. **Date :** ce soir. **Décideur / responsable capacité / assesseur :** unknown.
- **Objectif :** rotation des clés qui n'ont jamais été renouvelées (hygiène de sécurité). *À confirmer : exigence de conformité ou simple bonne pratique.*
- **État actuel :** inconnu, voir questions 1 à 3.
- **Incertitudes :** synchronisation actuelle des nœuds, paramètres de jeton, gestion par l'outil de déploiement.
- **Options :** (a) supprimer les clés sauf la primaire, **rejetée** car elle invalide les jetons en cours et supprime les secours. (b) Rotation avec conservation des clés, **retenue**.
- **Récupération :** restauration du répertoire sauvegardé sur les 3 nœuds.
- **Arrêt / vérification :** voir sections 5 et 6.
- **Suivi :** planifier la rotation périodique, avec la même procédure, dans le calendrier de maintenance. Documenter la procédure en runbook.

> Aide à la décision uniquement. Les étapes qui modifient l'état ci-dessus nécessitent l'approbation du responsable concerné et doivent être exécutées selon votre processus de changement.