# Writers contractuels — intégration A1/A2

**Statut :** proposition d'interface candidate, non gelée et non approuvée
pour la production. Aucun writer A1/A2 de production n'appelle encore ce
parcours. Le writer est candidat à un nouvel audit A5.

## Pourquoi un parcours commun

`validate_contract` garantit la forme JSON et la chronologie, mais il ne peut
pas garantir à lui seul :

- que le document est effectivement écrit avec sa version de contrat ;
- que `period.end_time` est présent pour `paper_live` (SQLite ne distingue pas
  une colonne omise d'un `NULL`) ;
- que la connexion est réellement en mode d'intégrité référentielle et de
  contraintes `CHECK` ;
- qu'aucune ligne n'est écrite si une validation échoue ;
- que la ligne relue correspond au document validé.

Le module commun est
`src/polymarket_lab/storage/contract_writer.py`. Il compose le registre de
schémas approuvés, le validateur système, la validation chronologique et la
transaction SQLite.

## Contrats approuvés intrinsèques

Le parcours normal ne reçoit **ni schéma, ni validateur, ni booléen
d'activation**. À chaque appel, il :

1. relit le registre privé et le fichier de contrat ;
2. vérifie le SHA-256 et la version `const` ;
3. gèle profondément le schéma ;
4. construit `SystemSchemaValidator` à partir de ce schéma ;
5. vérifie de nouveau l'approbation juste avant l'insertion.

Le registre public `APPROVED_CONTRACTS` est une vue en lecture seule
(`MappingProxyType`). Les entrées `ApprovedContract` sont gelées. Le writer
consulte une donnée privée, pas cette vue publique : réassigner
`APPROVED_CONTRACTS` ne change pas l'approbation utilisée.

Le schéma et `validator.schema` sont des vues profondément gelées : une
mutation ordinaire du premier ou d'un sous-objet lève `TypeError`. Le writer
ne conserve pas ces objets entre deux écritures ; une mutation en mémoire ne
peut donc pas modifier le contrat d'une écriture ultérieure.

### Validateur système

`src/polymarket_lab/validation/schema_validator.py` implémente le
sous-ensemble JSON Schema utilisé par `experiment` et `fee_schedule`. Il
refuse à la construction tout mot-clé d'assertion non supporté
(`UnsupportedSchemaError`) au lieu de l'ignorer. Il couvre notamment :
`$ref` locales, `type`, `properties`, `required`, `additionalProperties`,
`allOf`, `anyOf`, `oneOf`, `if/then/else`, `const`, `enum`, `pattern`,
`minLength`, `maxLength`, `minimum`, `maximum`, `items`, `uniqueItems`.

`multipleOf` est **explicitement refusé** à la construction : la sémantique
décimale divergeait de `jsonschema` sur les flottants (A5-C2-01). Aucun schéma
approuvé ne l'utilise. Les `$ref` doivent être locales, pointer vers un schéma
objet valide et ne pas former de cycle ; ces conditions sont vérifiées à la
construction.

Ce validateur est un **candidat interne**, pas une décision de production
approuvée. Voir « Dépendance de validation en production ».

## Interface normale

```python
from polymarket_lab.storage import write_experiment, write_fee_schedule

write_experiment(connection, document)      # -> experiment_id
write_fee_schedule(connection, document)    # -> fee_schedule_id
```

Il n'existe aucun paramètre `spec`, `validator`, `schema`,
`allow_test_specs` ou `force`. Un appel avec ces paramètres lève `TypeError`.

## Parcours de test explicite

Les schémas personnalisés ne passent **jamais** par le writer normal. Ils
utilisent un module distinct et des fonctions nommées :

```python
from polymarket_lab.storage.contract_writer_testing import (
    TestContractSpec,
    write_experiment_for_tests,
)
from jsonschema import Draft202012Validator

spec = TestContractSpec("experiment", custom_schema, Draft202012Validator(custom_schema))
write_experiment_for_tests(connection, document, spec)
```

Ce module applique les mêmes contrôles de connexion, validation, transaction
et relecture, mais sans vérification d'approbation. Il n'est pas exporté par
`polymarket_lab.storage` et aucun writer A1/A2 ne doit l'importer.

**Limite explicite :** un nom de module ou une fonction « for_tests » n'est pas
une frontière de sécurité contre du code Python arbitraire exécuté dans le
même processus. L'objectif est d'empêcher un contournement accidentel et de
rendre le parcours normal vérifiable.

## Connexion SQLite exigée

Le writer **refuse** avant validation :

- un objet qui n'est pas exactement `sqlite3.Connection` (les sous-classes sont
  refusées) ;
- un `row_factory` différent de `None` ou `sqlite3.Row` : un callable
  arbitraire pourrait falsifier la lecture des pragmas ;
- `PRAGMA foreign_keys != 1` ;
- `PRAGMA recursive_triggers != 1` ;
- `PRAGMA ignore_check_constraints != 0` ;
- `isolation_level` non `None` ;
- une transaction déjà ouverte.

Le writer ne modifie **aucun** pragma de l'appelant. Utiliser
`open_connection`, qui applique et vérifie `foreign_keys=ON`,
`recursive_triggers=ON`, `ignore_check_constraints=OFF`,
`isolation_level=None` et `row_factory=sqlite3.Row`.

Un `row_factory` falsifié ne peut donc pas faire croire que `foreign_keys` ou
`recursive_triggers` sont actifs : la configuration est refusée avant toute
lecture de pragma.

## Ordre de validation et d'approbation

### Avant la transaction

1. **Connexion** : type exact, `row_factory`, pragmas, `isolation_level`,
   transaction appelante.
2. **Chargement de l'approbation** : le registre et le fichier sont lus,
   SHA-256 et version vérifiés, schéma gelé, `SystemSchemaValidator` construit.
   C'est un prérequis : une erreur de registre est déjà un
   `ContractApprovalError`.
3. **Schéma JSON** : `ContractSchemaError`.
4. **Chronologie** : `ContractChronologyError`.
5. **Version** : `ContractVersionError`.
6. **Métier** : `ContractBusinessError`.
7. **Mapping document → colonnes** : `ContractBusinessError` si incomplet.

### Dans la transaction

8. **`BEGIN IMMEDIATE`** : verrou d'écriture SQLite.
9. **Approbation finale** : le registre et le fichier sont relus, le schéma
   gelé est comparé à la source officielle, le validateur système est vérifié,
   puis `ContractApprovalError` si l'un échoue.
10. **INSERT**, puis relecture et comparaison de la ligne
    (`ContractPersistenceError`).
11. **COMMIT** ; toute erreur annule la transaction et aucune ligne n'est
    conservée.

Une catégorie antérieure court-circuite les suivantes.

### Pourquoi la vérification finale est dans la transaction

La vérification finale est exécutée **après `BEGIN IMMEDIATE` et juste avant
l'INSERT**, pas avant `BEGIN`. Ce choix est volontaire :

- il réduit la fenêtre entre la dernière lecture du fichier de schéma et
  l'insertion ;
- un échec de cette vérification annule la transaction et ne laisse aucune
  ligne ;
- `BEGIN IMMEDIATE` empêche un autre écrivain SQLite concurrent d'insérer au
  même moment, mais **ne verrouille pas** le fichier de schéma ni le registre.

Limites explicites :

- un changement du fichier ou du registre entre la vérification finale et
  l'INSERT reste possible (TOCTOU) ;
- aucun verrou de fichier, aucune surveillance de modification n'est fourni ;
- aucun test de concurrence, de verrou, de crash ou de reprise n'est exécuté ;
- du code arbitraire dans le processus peut remplacer les fonctions ou les
  globals.

Aucune garantie de concurrence n'est revendiquée au-delà de ces faits.

### Classification de `schema_version`

Une erreur est classée `version` uniquement si elle concerne le
`schema_version` **racine** :

- erreur au chemin exact `schema_version` (`const`, `type`, `enum`) ;
- absence du champ racine `schema_version`.

Un `schema_version` imbriqué (par exemple
`execution_assumptions.schema_version`) est une erreur de schéma.

Si un document n'a ni `period` ni `schema_version`, l'absence de `period` est
classée `schema` et le writer lève `ContractSchemaError`. L'absence de
`schema_version` ne reclasse pas les autres champs manquants en `version`.

Si un document a une période inversée **et** une version incompatible, l'ordre
schéma → chronologie → version produit `ContractChronologyError`. Si la forme
est valide mais la version seule est mauvaise, `ContractVersionError`.

## Mapping document → colonnes

- `experiment_config_json` reçoit le document validé sérialisé en JSON
  canonique (clés triées, séparateurs compacts).
- `execution_assumptions_json`, `risk_limits_json` et
  `presentation_conversion_json` sont sérialisés de la même manière.
- `random_seed` est repris de `execution_assumptions.random_seed`.
- `custom_formula_ref` reste `NULL` : champ absent du contrat, formule
  suspendue.
- `completed_at` est optionnel ; le writer contrôle sa cohérence avec `status`.
- Les IDs et timestamps sont écrits tels quels ; aucune date n'est inventée.

## Erreurs

| Classe | Catégorie | Signification |
|---|---|---|
| `ContractSpecError` | `spec` | spécification de test mal formée |
| `ContractApprovalError` | `approval` | registre, hash, version ou approbation invalide |
| `ContractConnectionError` | `connection` | type, `row_factory`, pragmas, isolation ou transaction |
| `ContractSchemaError` | `schema` | forme JSON invalide |
| `ContractChronologyError` | `chronology` | période inversée ou bornes égales |
| `ContractVersionError` | `version` | version absente/incompatible |
| `ContractBusinessError` | `business` | contrôle métier ou mauvais writer |
| `ContractValidatorError` | `validator` | exception du validateur enveloppée |
| `ContractSQLiteError` | `sql` | contrainte, FK, trigger, doublon SQL |
| `ContractPersistenceError` | `persistence` | ligne absente ou différente |

Chaque exception expose `category` et `issues`.

Les erreurs de registre (`ContractNotRegisteredError`,
`ContractSchemaMissingError`, `ContractSchemaUnreadableError`,
`ContractSchemaMalformedError`, `ContractHashMismatchError`,
`ContractVersionMismatchError`, `ContractSchemaMismatchError`) sont
normalisées en `ContractApprovalError` avec leur cause d'origine. Elles ne
sont jamais confondues avec une erreur SQL ou de persistance.

## Transactions et atomicité

- Une transaction appelante active fait échouer le writer **avant** toute
  validation ; le writer ne rollback pas la transaction de l'appelant.
- Chaque appel writer ouvre et commit sa propre transaction. **Deux appels
  distincts ne forment pas une transaction commune.**
- Si A1/A2 doit écrire plusieurs documents atomiquement, il faut une
  composition explicite (savepoint/transaction de groupe) à définir avant
  usage ; elle n'est pas fournie ici.
- Une erreur SQL, d'approbation ou de persistance annule la transaction du
  writer.
- Aucun test de concurrence, de crash après commit ou de reprise après crash
  n'a été exécuté. Ces garanties ne sont pas mesurées.
- La vérification d'approbation relit le fichier juste avant l'insertion, mais
  un changement du fichier entre cette lecture et l'insertion reste possible
  (fenêtre TOCTOU). Le dépôt local est supposé non modifié pendant l'appel.

## Versions et historique

- La version provient du registre approuvé (`1.2.0` aujourd'hui), pas d'un
  `const` choisi par l'appelant.
- Le writer insère explicitement cette version ; il ne dépend pas du
  `DEFAULT 1.2.0` SQL.
- Une ligne historique `1.1.0` reste lisible ; le writer ne la met pas à jour
  et ne la remplace pas.
- Aucun remplacement global de version n'est effectué.

## `paper_live` et `end_time`

Le contrat exige `period.end_time` dans `period.required`. La valeur peut être
`null` pour `paper_live` uniquement. SQLite stocke `NULL` et ne distingue pas
une clé absente. Le writer valide le document avant de lire la clé : une clé
absente est refusée avant insertion (catégorie `schema`).

## Dépendance de validation en production

`jsonschema` reste une dépendance de test (D-018) et n'est pas importé par
`src/`. Le writer normal utilise `SystemSchemaValidator`, un sous-ensemble
interne fail-closed. Cette situation correspond à un **candidat Option B**,
pas à une décision d'architecture approuvée.

### Option A — ajouter `jsonschema` en dépendance de production

**Modifications :** ajouter une version épinglée à `requirements.txt` /
`pyproject.toml` ; construire `Draft202012Validator` dans la fabrique système ;
conserver la vérification d'approbation et le gel ; ajouter des tests
d'import en environnement propre.

**Risques :** nouvelle dépendance de production, surface de maintenance et
d'audit, comportement des versions, packaging installé hors dépôt.

**Tests nécessaires :** import sans dépendance de test, parité avec le
validateur système, versions épinglées, échec explicite si absent.

### Option B — adopter un validateur interne

**Modifications :** approuver `SystemSchemaValidator` comme moteur de
production ; étendre la couverture à tous les contrats ; ajouter une suite de
conformité et des tests différentiels avec `jsonschema` ; documenter les
mot-clés supportés et la politique fail-closed.

**Risques :** sous-ensemble incomplet, bugs de conformité, maintenance
interne, absence de suite de conformité externe. Un schéma futur utilisant un
mot-clé non supporté est refusé, pas interprété.

**Tests nécessaires :** parité sur les contrats approuvés, refus des
mot-clés inconnus, couverture de tous les exemples et cas négatifs,
non-régression lors d'une nouvelle version de contrat.

Tant que le propriétaire n'a pas choisi, **l'intégration A1/A2 en production
reste bloquée**. Aucun fichier de dépendance n'a été modifié.

## Tests

- `tests/integration/test_contract_writer.py` : 58 tests.
- `tests/unit/test_system_schema_validator.py` : 32 tests de parité, de
  fail-closed.
- `tests/unit/test_contract_validation.py` : ordre et classification.
- `tests/integration/test_migration_manifest.py` : 11 tests de manifeste.

## Limites

- Seuls `experiment` et `fee_schedule` sont couverts.
- Aucun writer A1/A2 de production n'appelle encore le module.
- Un `INSERT` SQL direct peut contourner le writer.
- Les relations métier non déclarées dans les contrats ou le SQL ne sont pas
  vérifiées.
- Aucun test sur base réelle, concurrence, crash ou reprise.
- `jsonschema` production non tranché ; Option A/B non approuvée.
- Le validateur système est un sous-ensemble, pas JSON Schema complet.
- Un code arbitraire dans le même processus peut contourner les attributs
  privés ; aucune garantie de sécurité de processus n'est revendiquée.
- Aucun gel n'est prononcé.
