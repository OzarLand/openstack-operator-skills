## Résumé

**Verdict : pas prêt (Not ready).** Profondeur de revue : complète, parce que Keystone est un point de passage unique pour toute l'authentification et que la suppression de clés est irréversible.

**Top 3 des risques**
1. **L'étape « supprimer toutes les clés sauf la nouvelle primaire » est le point de non-retour.** Elle invalide immédiatement tous les tokens déjà émis, pour tous les services, utilisateurs, automatisations et sessions Horizon. Elle supprime aussi la possibilité de revenir en arrière.
2. **Rotation sur keystone-1 avant distribution.** Après `fernet_rotate`, keystone-1 émet avec une nouvelle clé primaire que keystone-2 et keystone-3 ne possèdent pas encore. Tout token émis par keystone-1 et présenté à un autre nœud échoue jusqu'à la fin du rsync.
3. **Un système jamais tourné n'a jamais prouvé qu'il savait le faire.** Les trois nœuds ont-ils vraiment les mêmes clés aujourd'hui ? Je ne le sais pas.

## Ce que fait vraiment `fernet_rotate` (à vérifier pour votre release)
- La clé staged (`0`) devient primaire (index le plus élevé). Une nouvelle clé staged `0` est créée. L'ancienne primaire devient secondaire (validation seule).
- `max_active_keys` (3 par défaut) fait supprimer automatiquement les plus anciennes clés. **Le ménage est donc déjà fait par la rotation elle-même.** Il n'y a rien à supprimer à la main.
- Il faut conserver les secondaires au moins une durée `token.expiration` (et la fenêtre de renouvellement autorisée, `allow_expired_window`, 48 h par défaut). Si votre expiration est de 1 h, vous pouvez garder l'ancienne primaire sans risque et la laisser sortir naturellement à la rotation suivante.

## Portée et rayon d'action
- **Observed :** rien. Je n'ai vu aucune sortie de votre plateforme.
- **Reported :** 3 nœuds Keystone, aucune rotation jusqu'ici.
- **Assumption :** `/etc/keystone/fernet-keys/` est le `key_repository` effectif, et Keystone tourne en service/httpd classique et non en conteneur (Kolla, par exemple). Si vous utilisez Kolla-Ansible ou un autre outil de déploiement, le rsync manuel peut être écrasé au prochain run.
- **Impact :** toute l'authentification de la plateforme (API, agents, Horizon, CI, applications des clients utilisant des tokens longs).

## Gates de décision
| Gate | Statut | Preuve / lacune |
|---|---|---|
| Impact métier | **unknown** | Aucun owner n'a accepté l'invalidation de tous les tokens. |
| Récupération | **fail** | Avec la suppression des clés, pas de retour arrière possible, sauf à avoir une sauvegarde des clés. |
| Preuve | **unknown** | Pas de test sur un environnement représentatif. Aucune rotation faite auparavant. |
| Owner | **unknown** | Non indiqué. |
| Autorité | **unknown** | Non indiqué. |
| Rayon d'action | **fail** | Pas de borne : tous les tokens, tous les nœuds, en une fois. |
| Exigences obligatoires | **unknown** | Politique de sécurité sur la gestion des clés non précisée. |

## Plan corrigé (proposition, tout est state-changing sauf mention)

**Avant (read-only)**
1. Comparer les clés des 3 nœuds (empreintes, sans afficher le contenu) :
   `ssh keystone-N 'cd /etc/keystone/fernet-keys && sha256sum * && ls -l'`.
   Il doit y avoir les mêmes fichiers, les mêmes hashes, propriétaire `keystone`, mode 600/700 (dossier). **Si ça diffère, arrêtez : c'est un problème préexistant à comprendre d'abord.**
2. Relever `[fernet_tokens] key_repository`, `max_active_keys`, `[token] expiration`, `allow_expired_window`, et si un outil de déploiement gère ces fichiers.
3. **Sauvegarder** le dossier des clés (archive avec permissions, stockée de façon sécurisée, ces clés sont des secrets). C'est votre seul retour arrière.
4. Test de bout en bout avant : émission de token + validation depuis chaque nœud, via le load balancer et en direct sur chaque nœud.
5. Définir une base de référence : taux de 401/403 Keystone, taux d'erreurs des API, supervision en place.

**Exécution**
6. Ne pas lancer la rotation sur un nœud en service sans précaution. Deux options acceptables, selon votre contexte :
   - **A (plus sûre) :** copier le dossier dans un répertoire temporaire, y faire tourner les clés (en pointant `key_repository` vers ce répertoire via un fichier de config temporaire), puis distribuer le résultat sur les 3 nœuds. La nouvelle primaire n'est utilisée qu'après distribution complète.
   - **B (plus simple) :** rotation sur keystone-1, avec le LB qui n'envoie plus de trafic vers keystone-1 pendant la fenêtre, distribution immédiate, puis remise en service. Documentez la fenêtre d'erreurs si vous ne retirez pas le nœud du LB.
7. Distribuer avec `rsync -a` (ou la commande de votre outil de déploiement), en conservant propriétaire et permissions. N'utilisez `--delete` que si vous avez comparé les listes au préalable. Il n'y a rien à nettoyer à la main : `max_active_keys` s'en charge.
8. **Le redémarrage n'est en principe pas nécessaire** : Keystone relit le dépôt de clés (à vérifier pour votre release et votre cache). Si vous redémarrez, faites-le nœud par nœud derrière le LB, pas les trois ensemble.

**Vérification (capacité, pas succès de commande)**
- Mêmes empreintes sur les 3 nœuds.
- Émettre un token sur chaque nœud et le valider sur chacun des deux autres (6 combinaisons).
- Un token émis avant la rotation (conservé) reste valide.
- Un déploiement réel de bout en bout (par exemple création d'un volume ou d'une VM de test) fonctionne.
- Taux d'erreurs 401 stable pendant une période d'observation que **vous** définissez selon vos bases de référence.

**Conditions d'arrêt**
- Les empreintes diffèrent entre nœuds avant ou après.
- Un token émis sur un nœud est rejeté sur un autre.
- Hausse des 401/403 au-dessus de votre seuil.
- Le rsync échoue à mi-chemin (nœuds avec des jeux de clés différents : c'est l'état le plus dangereux).
- L'owner ou le décideur n'est pas joignable.

**Récupération**
- Tant que vous n'avez rien supprimé, le retour arrière est de restaurer l'archive sur les 3 nœuds. Après suppression des anciennes clés, il n'existe plus de retour pour les tokens concernés, sauf par la sauvegarde.

## Ce que vous avez peut-être oublié
- Les tokens en cours (voir ci-dessus), y compris les sessions Horizon, les jobs longs et les services à tokens mis en cache.
- La **sauvegarde** et le stockage sécurisé des clés.
- Une **vérification de l'identité des clés** avant de commencer.
- Le **fonctionnement de l'outil de déploiement** (Kolla, Ansible…), qui peut défaire votre rsync.
- La **récurrence** : une rotation ponctuelle ne sert à rien si elle n'est pas planifiée (cron/pipeline, avec distribution atomique). Mettez-la au calendrier de maintenance.
- La communication aux consommateurs et la désignation de qui décide.
- D'autres changements dans la même fenêtre ? Ne les empilez pas.

## Questions ouvertes
1. Quelle est la valeur de `token.expiration` et de `max_active_keys` ?
2. Keystone est-il déployé par Kolla-Ansible ou un autre outil ?
3. Les 3 nœuds ont-ils aujourd'hui des clés identiques (empreintes) ?
4. Y a-t-il un environnement de test pour répéter la rotation ?
5. Qui est l'owner de la capacité d'authentification et qui décide ?

## Décision record (brouillon)
- **Change :** rotation des clés Fernet, 3 nœuds Keystone
- **Date / owners / assesseur :** unknown
- **Objectif :** respecter la bonne pratique de rotation (clés jamais tournées). Le besoin métier précis (conformité, incident, politique) est à préciser.
- **Options rejetées :** suppression manuelle de toutes les clés non primaires (rejetée : invalidation globale, aucun retour arrière, redondante avec `max_active_keys`).
- **Récupération :** restauration de l'archive de clés tant qu'aucune suppression n'a eu lieu.
- **Suivi :** automatiser la rotation planifiée et l'ajouter à la liste des exercices de récupération.

> Decision support only. State-changing steps above require approval by the accountable owner and should be executed under your change process.