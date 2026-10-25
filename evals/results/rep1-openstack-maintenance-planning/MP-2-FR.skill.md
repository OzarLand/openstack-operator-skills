**Non. Je déconseille cette approche, et elle ne doit pas être utilisée pour de la maintenance planifiée.** L'evacuate sert uniquement à récupérer les instances d'un hôte en panne. Les hypothèses ci‑dessous (Ceph partagé, hôtes sains) sont des suppositions de ma part, pas des faits que vous m'avez montrés.

## Pourquoi c'est dangereux

1. **Nova-compute arrêté ne veut pas dire VM arrêtées.** Sur un hôte sain, libvirt/QEMU continue de faire tourner les instances. Vous obtenez un hôte « down » aux yeux de Nova alors que les VM tournent encore dessus.
2. **Double exécution des instances sur Ceph.** `evacuate` reconstruit l'instance sur un autre hôte à partir des mêmes volumes RBD. Si l'original tourne encore, deux VM écrivent sur le même disque. Il y a un risque de corruption de données et de conflits réseau (même IP et même MAC). Le verrou exclusif RBD n'est pas une protection suffisante à lui seul.
3. **Le prérequis d'une évacuation, c'est le fencing.** L'hôte doit être éteint ou isolé avant, par exemple par IPMI power off ou STONITH. Dans votre procédure, « attendre qu'il apparaisse down » ne prouve rien : Nova voit seulement l'absence de heartbeat.
4. **Ce n'est pas plus rapide pour les workloads qui comptent.** L'evacuate redémarre les VM, donc il y a coupure et reboot de l'OS invité pour chacune. Le gain de vitesse vient de la suppression du travail de migration, pas d'une meilleure méthode. Pour des workloads critiques, vous remplacez du lent par des pannes.
5. **Le patch n'est pas forcément appliqué.** Une instance n'est protégée par un patch QEMU/hyperviseur que si elle a été migrée ou redémarrée depuis. Une instance qui tourne encore sur l'ancien binaire n'est pas patchée.

## Alternatives, selon vos contraintes

La vraie question est de savoir quelles VM ont besoin de rester en ligne. C'est aux équipes consommatrices de le dire, pas à l'équipe infra. Ensuite, on choisit une stratégie par classe de workload :

| Classe | Stratégie | Condition |
|---|---|---|
| Critique, migrable | Live migration | Capacité disponible dans le domaine de défaillance |
| Tolère un redémarrage (accord du propriétaire) | Cold migration (`openstack server migrate`) ou redémarrage coordonné | Fenêtre convenue. Cold migrate est rapide avec Ceph, il n'y a pas de copie de disque. |
| Non live‑migrable (PCI passthrough, `direct-physical`, mémoire très active) | Cold migration ou redémarrage | Coupure acceptée par le propriétaire |
| Intouchable avant l'échéance | Exception documentée | Propriétaire, contrôles compensatoires, date de revue |

**Pour accélérer les live migrations**, ces pistes sont à vérifier pour votre release :
- Activer `live_migration_permit_auto_converge` (ou le post‑copy) pour les VM dont la mémoire change vite.
- Augmenter la concurrence de migrations selon vos propres mesures, en surveillant le réseau et Ceph.
- Dédier un réseau à la migration.
- Migrer plusieurs hôtes en parallèle, un par domaine de défaillance (rack ou AZ) selon la capacité.

**Procédure par hôte :**
1. Désactiver le service (`openstack compute service set --disable --disable-reason "<motif>" <host> nova-compute`). Cette étape modifie l'état.
2. Migrer les instances selon leur classe, en vérifiant chaque déplacement.
3. Vérifier que l'hôte est vide, ou que seules les instances acceptées pour redémarrage restent.
4. Patcher et redémarrer.
5. Redémarrer les instances prévues. Par défaut, `resume_guests_state_on_host_boot=False`, donc elles reviennent `SHUTOFF`. À vérifier dans votre config.
6. Réactiver le service.

**Ordre de patch.** Si le patch change libvirt/QEMU, la migration d'une version plus récente vers une plus ancienne n'est pas supportée. Un premier lot vidé sert alors de zone d'atterrissage, et les instances ne vont que vers des hôtes déjà patchés. Pour un patch noyau seul, cette contrainte ne s'applique pas.

## Pour avancer, il me manque

- Le nombre d'hôtes, les domaines de défaillance (racks, AZ) et la capacité libre par domaine.
- Les versions OpenStack, libvirt et QEMU.
- Les workloads spéciaux (GPU, SR-IOV, PCI passthrough, grosse mémoire) et le tableau de criticité côté équipes consommatrices.
- Ce qui rend les live migrations lentes : mémoire très active, réseau saturé, concurrence limitée ?
- L'échéance du patch et sa nature (noyau seul, ou libvirt/QEMU).

Avec ces éléments, je peux produire le plan complet : capacité par domaine, séquençage, bornes d'arrêt et critères de fin.

> Aide à la décision uniquement. Les étapes qui modifient l'état ci‑dessus (désactivation, migrations, redémarrages) demandent l'approbation du responsable concerné et doivent être exécutées dans votre processus de changement.