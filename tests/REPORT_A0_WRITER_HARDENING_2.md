# Rapport A0 — fermeture des contournements du Contract Writer

**Date :** 2026-10-27  
**Auteur :** A0 — architecte / intégrateur  
**Objet :** corriger les anomalies confirmées par
`tests/REPORT_A5_POST_HARDENING_AUDIT.md` (verdict PARTIEL).  
**Statut :** writer **candidat** à un nouvel audit A5. **Aucun commit, aucun
gel, aucune collecte, aucune simulation, aucune base réelle, aucune
dépendance de production ajoutée.** Le writer n'est pas déclaré approuvé.

---

## 1. Résumé exécutif

Les garanties d'approbation ne dépendent plus d'objets fournis par
l'appelant. Le parcours normal :

- recharge le registre privé et le fichier de contrat à chaque écriture ;
- vérifie le SHA-256 et la version `const` ;
- gèle profondément le schéma ;
- construit lui-même un `SystemSchemaValidator` ;
- re-vérifie l'approbation juste avant l'insertion.

L'API normale est réduite à `write_experiment(connection, document)` et
`write_fee_schedule(connection, document)`. Il n'existe plus de paramètre
`spec`, `validator`, `schema`, `allow_test_specs` ou `root`. Les schémas
personnalisés passent par un module explicitement distinct,
`contract_writer_testing`.

Les contrôles SQLite refusent désormais `ignore_check_constraints=ON`, un
`row_factory` arbitraire et les sous-classes de `sqlite3.Connection`, sans
modifier les pragmas de l'appelant.

L'ordre de validation est **schéma → chronologie → version**, avec une
classification précise du `schema_version` racine. Un document sans `period`
et sans `schema_version` produit d'abord une erreur de schéma pour `period`.

Le manifeste des migrations est explicite, couvert par des tests et son
empreinte est épinglée. Il reste une baseline auto-référentielle : il ne
prouve pas l'historique Git.

La dépendance de validation de production reste **non tranchée**. Le
validateur système interne est un candidat Option B, pas une décision
approuvée. L'intégration A1/A2 en production reste bloquée.

Résultats finaux : **717 tests collectés, 717 réussis, 0 xfail, 0 échec
inattendu**.

---

## 2. Fichiers modifiés ou ajoutés

### Code

- `src/polymarket_lab/validation/registry.py` — registre privé immuable, vue
  publique en lecture seule, erreurs typées, hash/version vérifiés, schéma gelé.
- `src/polymarket_lab/validation/immutability.py` — **nouveau** ;
  `freeze_json`, `thaw_json`, `canonical_json`.
- `src/polymarket_lab/validation/schema_validator.py` — **nouveau** ;
  `SystemSchemaValidator`, sous-ensemble JSON Schema fail-closed.
- `src/polymarket_lab/validation/contracts.py` — ordre
  schéma → chronologie → version, classification du `schema_version` racine,
  support des schémas gelés.
- `src/polymarket_lab/validation/__init__.py` — exports.
- `src/polymarket_lab/storage/contract_writer.py` — approbation intrinsèque,
  API sans schéma/validateur, vérification avant insertion, contrôles de
  connexion renforcés.
- `src/polymarket_lab/storage/contract_writer_testing.py` — **nouveau** ;
  parcours de test séparé `TestContractSpec`,
  `write_experiment_for_tests`, `write_fee_schedule_for_tests`.
- `src/polymarket_lab/storage/connection.py` — `ignore_check_constraints=OFF`
  appliqué et vérifié par `open_connection`.

### Tests

- `tests/integration/test_contract_writer.py` — 51 tests.
- `tests/unit/test_system_schema_validator.py` — **nouveau**, 12 tests.
- `tests/unit/test_contract_validation.py` — 12 tests, dont l'ordre et les
  erreurs multiples.
- `tests/integration/test_migration_manifest.py` — 11 tests.
- `tests/README.md` — chiffres et limites.

### Manifeste et documentation

- `schemas/migrations/SHA256SUMS` — format explicite, périmètre et fichiers
  couverts déclarés ; hashes des migrations inchangés.
- `schemas/migrations/README.md` — limites de la baseline.
- `WRITER_INTEGRATION.md` — interface, approbation, ordre, erreurs, options
  A/B.
- `ARCHITECTURE.md` — parcours writer.
- `DECISIONS.md` — D-053 marquée partiellement remplacée, nouvelle D-054.
- `contracts/README.md` — registre et validateur système.
- `contracts/CONTRACT_FREEZE_PROPOSAL.md` — statistiques datées.
- `tests/REPORT_A0_WRITER_HARDENING.md` — bannière historique.
- `tests/REPORT_A0_WRITER_HARDENING_2.md` — présent rapport.

**Non modifiés :** migrations `0004` à `0007`, rapports A5, index ou
historique Git, fichiers de dépendances de production.

---

## 3. Anomalies traitées et classification

### 3.1 Approbation et contrats

| Réf. | Anomalie | Traitement | Classification |
|---|---|---|---|
| B-08 | `allow_test_specs=True` accepte un schéma `9.9.9` | Paramètre supprimé de l'API normale ; parcours de test séparé | **CORRIGÉE ET TESTÉE** |
| B-10 | `APPROVED_CONTRACTS` public mutable | `MappingProxyType` et entrées gelées ; le writer lit une donnée privée | **CORRIGÉE ET TESTÉE** |
| B-11 | Validateur permissif avec `.schema` officiel | Aucun validateur appelant n'est accepté ; validateur construit par le système | **CORRIGÉE ET TESTÉE** |
| B-12 | Mutation de `spec.schema` / `validator.schema` après construction | Gel profond, objets immuables, rechargement à chaque écriture | **CORRIGÉE ET TESTÉE** |
| B-13 | `from_approved` laisse fuir `ContractRegistryError` | Normalisation en `ContractApprovalError`, cause conservée | **CORRIGÉE ET TESTÉE** |
| B-14 | Hash/version vérifiés uniquement à la construction | Vérification du registre et du fichier avant insertion | **CORRIGÉE ET TESTÉE** |
| D-11 | `allow_test_specs=True` hors tests | Même correction que B-08 | **CORRIGÉE ET TESTÉE** |

### 3.2 Connexion SQLite

| Réf. | Anomalie | Traitement | Classification |
|---|---|---|---|
| A-09 | `ignore_check_constraints=ON` contourne un CHECK | Pragma vérifié à `0` avant validation et écriture ; `open_connection` le force à `OFF` | **CORRIGÉE ET TESTÉE** |
| A-10 | `row_factory` falsifié | `row_factory` limité à `None` ou `sqlite3.Row` ; configuration refusée avant lecture | **CORRIGÉE ET TESTÉE** |
| A-11 | Course entre contrôle et `BEGIN` | Non exécuté | **NON VÉRIFIABLE** |
| A-12 | Sous-classe malveillante de `sqlite3.Connection` | Type exact exigé ; sous-classe refusée | **CORRIGÉE ET TESTÉE** |

### 3.3 Validation et erreurs

| Réf. | Anomalie | Traitement | Classification |
|---|---|---|---|
| C-01 | Ordre réel schéma → version → chronologie | Ordre schéma → chronologie → version | **CORRIGÉE ET TESTÉE** |
| C-10 | Toutes les erreurs catégorisées | Erreurs de registre normalisées ; causes conservées | **CORRIGÉE ET TESTÉE** |
| C-11 | `required` multiple reclasse `period` en version | Seul le `schema_version` racine est classé version | **CORRIGÉE ET TESTÉE** |

### 3.4 Manifeste et dépendance

| Réf. | Anomalie | Traitement | Classification |
|---|---|---|---|
| E-05 | Baseline auto-référentielle | Format/périmètre/couverture explicites, empreinte du manifeste épinglée, tests de modification | **CORRIGÉE MAIS PARTIELLEMENT TESTÉE** |
| E-06/E-07 | Historique Git absent | Aucun historique créé ; limite documentée | **NON VÉRIFIABLE** |
| F-03/F-06 | Aucun validateur alternatif concret | `SystemSchemaValidator` interne fail-closed | **CORRIGÉE ET TESTÉE** |
| F-04/F-05 | `jsonschema` absent des dépendances de production | Options A/B documentées ; aucune dépendance ajoutée ; intégration bloquée | **NON CORRIGÉE** (décision propriétaire) |

E-05 reste partiellement corrigée par nature : un acteur qui modifie la
migration, le manifeste, le test et la constante épinglée peut produire un état
cohérent. Aucune baseline interne au dépôt ne peut prouver l'historique.

---

## 4. Choix d'architecture

### 4.1 Approbation intrinsèque

`ContractSpec` n'est plus un objet que l'appelant peut fabriquer avec un
schéma et un validateur. Son constructeur exige un jeton privé ; le seul
chemin public est `ContractSpec.from_approved(name)`. Le writer normal ne
reçoit même pas de `ContractSpec` : il appelle `from_approved` à chaque
écriture.

Le registre privé est un tuple d'`ApprovedContract` gelés. La vue publique
`APPROVED_CONTRACTS` est un `MappingProxyType`. Le writer consulte la donnée
privée, donc remplacer la vue publique ne change pas l'approbation.

Le schéma approuvé est gelé récursivement (`MappingProxyType` et tuples). Le
validateur système possède sa propre copie gelée. Une mutation ordinaire lève
`TypeError` ; une réassignation d'attribut lève `AttributeError`. Avant
l'insertion, le writer relit le registre et le fichier et compare le schéma
gelé à la source officielle.

**Limite :** du code Python arbitraire dans le même processus peut utiliser
`object.__setattr__`, monkeypatcher des globals ou remplacer des fonctions.
Aucune garantie de sécurité de processus n'est revendiquée. L'objectif est
d'empêcher les contournements accidentels et de rendre les garanties
vérifiables.

### 4.2 Validateur système

`SystemSchemaValidator` couvre le sous-ensemble utilisé par `experiment` et
`fee_schedule` : `$ref` locales, `type`, `properties`, `required`,
`additionalProperties`, `allOf`, `anyOf`, `oneOf`, `if/then/else`, `const`,
`enum`, `pattern`, `minLength`, `maxLength`, `minimum`, `maximum`, `items`,
`uniqueItems`. Tout mot-clé d'assertion non supporté est refusé à la
construction, jamais ignoré.

Ce choix est un **candidat Option B**. Il permet de fermer P0-A sans ajouter de
dépendance externe, mais il ne vaut pas approbation de production. La décision
propriétaire reste ouverte (voir §8).

### 4.3 Parcours de test séparé

`src/polymarket_lab/storage/contract_writer_testing.py` est un module distinct,
non exporté par `polymarket_lab.storage`. Ses fonctions portent
`_for_tests`. Il accepte un schéma et un validateur personnalisés et applique
les mêmes contrôles de connexion, validation, transaction et relecture, sans
vérification d'approbation.

Ce n'est pas une frontière de sécurité : son nom et sa séparation empêchent un
import accidentel par A1/A2, pas un import délibéré. L'API normale, elle, ne
peut pas recevoir de spécification de test.

### 4.4 Connexion

Le writer exige :

- `type(connection) is sqlite3.Connection` ;
- `row_factory is None` ou `sqlite3.Row` ;
- `foreign_keys=1` ;
- `recursive_triggers=1` ;
- `ignore_check_constraints=0` ;
- `isolation_level is None` ;
- `in_transaction` faux.

Il ne modifie aucun pragma. `open_connection` applique et vérifie les mêmes
propriétés.

### 4.5 Ordre et classification

L'ordre est schéma → chronologie → version. Une erreur de version ne concerne
que le `schema_version` **racine** : chemin exact `schema_version`, ou absence
du champ racine. Un `schema_version` imbriqué est une erreur de schéma.

Un document sans `period` et sans `schema_version` produit une erreur de
schéma pour `period` ; l'absence de `schema_version` ne reclasse pas les autres
champs. Un document avec période inversée et version incompatible produit une
erreur de chronologie.

### 4.6 Manifeste

`SHA256SUMS` déclare `format`, `scope` et `covered`. Le test vérifie la liste
exacte, les hashes, l'absence de doublons, l'absence de fichier `.sql` non
couvert, le fait que le manifeste n'est pas une migration et l'empreinte du
manifeste lui-même. Un `0008` ajouté sans mise à jour échoue.

---

## 5. Tests de reproduction avant/après

Les constats « avant » sont ceux de l'audit A5 indépendant. Aucun script
d'audit A5 n'a été réutilisé tel quel ; les scénarios ont été convertis en
tests de non-régression committés dans le dépôt.

| Contournement A5 | Test après |
|---|---|
| Mutation de `spec.schema` | `test_approved_schema_and_validator_schema_are_deeply_immutable` |
| Mutation de `validator.schema` | même test |
| Validateur permissif | `test_permissive_validator_is_confined_to_explicit_test_path` |
| Validateur construit sur un autre schéma | `test_approved_spec_is_built_by_the_system_without_caller_validator` |
| Registre public remplacé | `test_public_registry_mapping_is_read_only`, `test_reassigning_public_registry_alias_does_not_change_writer` |
| `9.9.9` par le parcours normal | `test_forged_version_is_rejected_by_normal_path`, `test_custom_schema_is_exercised_only_through_test_path` |
| Schéma sur disque modifié | `test_modified_schema_on_disk_without_registry_update_is_refused` |
| `allow_test_specs=True` | `test_normal_writer_accepts_no_schema_or_validator_argument`, `test_test_path_is_explicit_and_normal_path_never_accepts_test_spec` |
| `ignore_check_constraints=ON` | `test_writer_rejects_ignore_check_constraints_on` |
| `row_factory` falsifié | `test_custom_row_factory_is_refused_before_validation`, `test_falsified_row_factory_cannot_hide_foreign_keys_off` |
| Erreurs de registre brutes | `test_from_approved_normalizes_*` (inconnu, fichier absent, JSON malformé, mauvais hash, version) |
| Ordre version/chronologie | `test_chronology_takes_priority_over_version` |
| `required` multiple mal classé | `test_missing_period_is_not_reclassified_as_version` |

Sous-ensemble de reproduction exécuté :

```text
pytest tests/integration/test_contract_writer.py -q \
  -k "mutation or registry or forged or row_factory or ignore_check or normal_writer or custom_schema or permissive or from_approved"
18 passed, 33 deselected
```

---

## 6. Commandes réellement exécutées et résultats

Depuis `C:\Users\User\polymarket_strategy_lab`, avec
`.\.venv\Scripts\python.exe` :

```text
pytest tests -q -rxX
# 717 passed in 60.93s

pytest tests --collect-only -q
# 717 tests collected in 0.19s

pytest tests -q --runxfail
# 717 passed in 30.91s

pytest tests/integration/test_p0_candidates.py -q
# 55 passed in 6.52s

pytest tests/unit/test_contracts_negative.py \
  tests/unit/test_contracts_schema_validity.py \
  tests/integration/test_contract_sql_parity.py -q
# 261 passed in 3.26s

pytest tests/integration/test_0007_contract_sql_alignment.py \
  tests/unit/test_contract_validation.py \
  tests/integration/test_contract_writer.py \
  tests/unit/test_system_schema_validator.py -q
# 83 passed in 9.00s

pytest tests/integration/test_migration_manifest.py -q
# 11 passed in 0.15s

pytest tests/integration/test_contract_writer.py -q \
  -k "mutation or registry or forged or row_factory or ignore_check or normal_writer or custom_schema or permissive or from_approved"
# 18 passed, 33 deselected in 1.76s

git diff --check
# exit 0 ; avertissements CRLF uniquement

git ls-files schemas/migrations
# aucun fichier ; count=0

python -S -c "import sys; sys.path.insert(0, 'src'); import polymarket_lab.storage.contract_writer"
# import réussi ; jsonschema absent de sys.modules
```

Comparaison avec la baseline A5 : `672/672/0` → `717/717/0`. Les 45 tests
supplémentaires couvrent l'approbation intrinsèque, le parcours de test, le
validateur système, l'ordre de validation et le manifeste.

---

## 7. Risques résiduels

1. **Code arbitraire dans le processus.** Les attributs privés, globals et
   fonctions peuvent être contournés par `object.__setattr__`, monkeypatch ou
   import du module de test. Aucune frontière de sécurité de processus.
2. **Validateur interne partiel.** `SystemSchemaValidator` n'est pas JSON
   Schema complet. Un mot-clé non supporté est refusé, mais la conformité
   sémantique de chaque mot-clé supporté n'a pas été prouvée exhaustivement.
3. **Fenêtre TOCTOU.** Le fichier de schéma est revérifié juste avant
   l'insertion ; un changement entre cette lecture et l'insertion reste
   possible.
4. **Concurrence et crash non testés.** Aucun test de course, verrou,
   timeout, crash après commit ou reprise.
5. **Manifeste auto-référentiel.** Une modification coordonnée migration +
   manifeste + test + constante peut passer ; seul un commit Git de référence
   fournit une preuve d'historique.
6. **Dépendance de production non tranchée.** Option A/B en attente ; A1/A2
   bloqué.
7. **Périmètre.** Seuls `experiment` et `fee_schedule` sont couverts.
8. **INSERT direct.** Un `INSERT` SQL direct hors writer contourne le parcours.
9. **Restrictions de connexion.** Les wrappers ou sous-classes légitimes de
   `sqlite3.Connection` sont refusés ; c'est volontaire mais à revoir si un
   besoin réel apparaît.
10. **Erreur de lecture de fichier.** `ContractSchemaUnreadableError` existe
    mais n'a pas été testée sur un refus de permission réel.

---

## 8. Points non traités et décisions propriétaire

### Non traités dans cette mission

- A-11 (course entre contrôle de connexion et `BEGIN`) et D-12 (crash,
  reprise, concurrence) : **non testés**.
- Historique Git des migrations : **non créé, non modifié**.
- Writers A1/A2 réels : **non branchés**.
- Autres contrats (`market_event`, `execution`, etc.) : **hors périmètre**.
- Validation d'un packaging installé hors dépôt : **non testée**.
- Gel des contrats : **non prononcé**.

### Décisions propriétaire requises

1. **Option A ou B pour la validation de production.**
   - A : ajouter `jsonschema` avec version épinglée en dépendance de
     production, construire `Draft202012Validator` dans la fabrique système,
     tester l'import en environnement propre.
   - B : adopter `SystemSchemaValidator` comme moteur de production, étendre
     sa couverture et sa suite de conformité, documenter la maintenance.
   - Tant que ce choix n'est pas fait, l'intégration A1/A2 reste bloquée.
2. **Ajouter les migrations et `SHA256SUMS` à un commit Git de référence**
   pour transformer la baseline en preuve d'historique vérifiable.
3. **Statuer sur les restrictions de connexion** (type exact et
   `row_factory`) si un wrapper applicatif légitime doit être supporté.
4. **Autoriser ou non un audit A5 puis une intégration expérimentale** ; la
   présente mission ne l'autorise pas.

---

## 9. Recommandation pour le prochain audit A5

Auditer en priorité :

1. les six contournements confirmés, avec des scripts indépendants et non
   seulement la suite existante ;
2. la construction du validateur système et sa parité avec `jsonschema` sur
   l'ensemble des cas négatifs `experiment`/`fee_schedule` ;
3. l'absence de paramètre de schéma/validateur dans l'API normale et
   l'absence de `allow_test_specs` ;
4. la normalisation des erreurs de registre et la conservation des causes ;
5. l'ordre schéma → chronologie → version et les documents multi-erreurs ;
6. les pragmas SQLite, `row_factory`, sous-classes et absence d'écriture
   partielle ;
7. les limites du manifeste (auto-référence, empreinte épinglée, Git) ;
8. l'absence de modification des migrations, des rapports A5 et des fichiers
   de dépendances.

**Verdict attendu :** un audit indépendant, pas une approbation automatique.
Aucun gel, aucun commit, aucune intégration de production n'est autorisé par ce
rapport.
