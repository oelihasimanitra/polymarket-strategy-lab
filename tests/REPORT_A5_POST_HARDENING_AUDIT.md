# Rapport A5 — audit indépendant post-durcissement du Contract Writer

**Date :** 2026-10-27  
**Auditeur :** A5 — validation et benchmark  
**Objet :** vérifier les garanties annoncées par
`tests/REPORT_A0_WRITER_HARDENING.md` après durcissement du writer, chercher
les failles résiduelles et décider de la prochaine étape.  
**Statut :** audit en lecture seule. Aucun fichier de production, migration,
test ou rapport historique modifié. Aucun commit. Aucun gel prononcé. Aucune
base de données réelle, aucune collecte, aucune simulation, aucun accès réseau.

---

## 1. Résumé exécutif

**Verdict global : PARTIEL.** Les contrôles nominaux de connexion et de
validation sont nettement meilleurs que dans l'audit A5 précédent, et les
chiffres A0 sont reproductibles. Les garanties d'approbation ne sont toutefois
pas encore intrinsèques au writer : un schéma approuvé peut être muté après
construction, un validateur permissif exposant simplement `.schema` est accepté,
et `allow_test_specs=True` reste un chemin public permettant d'écrire un schéma
`9.9.9`.

Les résultats vérifiés :

- `672 passed` sur la suite complète ;
- `672 tests collected` ;
- `672 passed` avec `--runxfail` ;
- `55 passed` pour les tests P0 ;
- `261 passed` pour les contrôles contrats/parité ciblés ;
- `47 passed` pour migrations 0007 + validateur + writer ;
- `2 passed` pour le manifeste des migrations ;
- `23 passed` pour la politique de connexion SQLite ;
- `git diff --check` : exit 0, avertissements CRLF uniquement ;
- `git ls-files schemas/migrations` : aucun fichier suivi.

L'audit indépendant principal contient **68 assertions : 66 vraies, 2 fausses**.
Parmi les assertions vraies, six **confirment des contournements** et sont
classées comme anomalies, pas comme des PASS de garantie :

- `allow_test_specs=True` accepte un schéma `9.9.9` ;
- un validateur permissif avec `.schema` officiel est accepté et persiste un
  document invalide ;
- une mutation de schéma après approbation permet d'écrire `9.9.9` ;
- une mutation du registre en mémoire contourne l'approbation ;
- `PRAGMA ignore_check_constraints=ON` contourne un CHECK SQL ;
- un `row_factory` falsifié peut faire croire que les pragmas sont actifs.

Les deux assertions fausses sont :

- `ContractSpec.from_approved("inconnu", ...)` lève
  `ContractRegistryError`, pas `ContractApprovalError` ;
- une erreur `required` couvrant à la fois `schema_version` et `period` est
  entièrement classée `version`, ce qui reclasse à tort l'absence de `period`.

**Décision recommandée : A — corrections ciblées avant une intégration
expérimentale.** Le writer est proche d'un usage expérimental, mais les
garanties d'approbation et le contrat d'erreur doivent être corrigés et testés
avant que A1/A2 s'appuie dessus. Aucun gel n'est prononcé.

---

## 2. Périmètre et limites

### 2.1 Périmètre inspecté

- `src/polymarket_lab/storage/contract_writer.py` — `ContractSpec`,
  `_check_connection`, `_validate_document`, `_write`, `write_experiment`,
  `write_fee_schedule`.
- `src/polymarket_lab/validation/registry.py` — registre approuvé et SHA-256.
- `src/polymarket_lab/validation/contracts.py` — `contract_issues`,
  `validate_contract`, chronologie, `SchemaValidatorError`.
- `src/polymarket_lab/storage/connection.py` — `open_connection`,
  `transaction`, pragmas.
- `tests/integration/test_contract_writer.py` — 31 tests.
- `tests/integration/test_migration_manifest.py` — 2 tests.
- `schemas/migrations/SHA256SUMS`, migrations `0004` à `0007`.
- `WRITER_INTEGRATION.md`, `ARCHITECTURE.md`, `DECISIONS.md` (D-053),
  `tests/README.md`, rapport A0 de durcissement, rapports historiques.

### 2.2 Ce qui n'a pas été testé

- Aucun test de concurrence multi-connexions, de verrou, de timeout, de crash
  après commit ou de reprise après incident.
- Aucune base de données réelle, aucun writer A1/A2 de production.
- Aucun test d'un validateur de production alternatif à `jsonschema` : aucune
  implémentation de ce type n'existe dans le dépôt.
- Aucun test de packaging installé hors du dépôt.

### 2.3 Distinction des preuves

- **Exécuté :** commandes pytest, script d'audit indépendant, copies
  temporaires pour le manifeste, import avec `python -S`.
- **Contrôle statique :** lecture du code, `grep`, AST et inspection des
  exports.
- **Documentaire :** `WRITER_INTEGRATION.md`, A0, D-053, README.
- **Hypothèse non mesurée :** comportement sous concurrence/crash, résistance
  d'un attaquant capable d'exécuter du code dans le processus, disponibilité
  d'un validateur de production.

---

## 3. État du code réellement inspecté

### 3.1 Connexion

`_check_connection` (`contract_writer.py:183-206`) vérifie, avant la validation
du document :

- que l'objet est un `sqlite3.Connection` ;
- `connection.in_transaction` est faux ;
- `connection.isolation_level is None` ;
- `PRAGMA foreign_keys == 1` ;
- `PRAGMA recursive_triggers == 1`.

Il lit les pragmas sans les modifier. Le writer appelle `_check_connection`
avant `_validate_document` (`contract_writer.py:420-431`). Une transaction
appelante est refusée avant toute validation, sans rollback de celle-ci.

### 3.2 Registre et `ContractSpec`

`registry.py:46-59` contient deux entrées approuvées :

| Contrat | Version | SHA-256 vérifié |
|---|---|---|
| `experiment` | `1.2.0` | `6d20ab72…e93fe85` |
| `fee_schedule` | `1.2.0` | `92bd9a17…e9918` |

Les hashes calculés sur les fichiers actuels correspondent au registre. Le
manifeste des migrations contient les hashes actuels de `0004` à `0007`.

`ContractSpec.__post_init__` (`contract_writer.py:125-158`) :

- valide `name`, `schema`, `validator.iter_errors` et la présence de
  `properties.schema_version.const` ;
- en mode `approved=True`, recharge le registre et compare le schéma fourni au
  schéma officiel ;
- compare `validator.schema` au schéma fourni.

`ContractSpec.from_approved` charge le registre puis construit la spec.
`ContractSpec.for_tests` crée une spec non approuvée. `_write`
(`contract_writer.py:420-428`) refuse une spec non approuvée sauf si
`allow_test_specs=True`.

### 3.3 Validation centralisée

`contract_issues` (`validation/contracts.py:142-178`) est bien utilisé par le
writer. Il classe :

- les erreurs de schéma ;
- les erreurs de version issues du schéma ;
- la chronologie ;
- la version attendue.

Le writer ne duplique plus la séquence dans son propre code. `validate_contract`
appelle `contract_issues` (`contracts.py:181-196`).

**Écart constaté :** l'ordre réel est **schéma → version issue du schéma →
chronologie → version attendue**, alors que A0 et `WRITER_INTEGRATION.md`
annoncent **schéma → chronologie → version**. Voir C-01.

### 3.4 Tests writer présents

`tests/integration/test_contract_writer.py` contient 31 tests. Ils couvrent
notamment :

- écritures valides expérience/barème ;
- chronologies inversées/égales ;
- erreur de schéma ;
- versions `1.1.0` et `9.9.9` avec le schéma officiel ;
- version absente ;
- `paper_live` sans clé et avec `null` ;
- incohérence métier ;
- schéma falsifié à la construction ;
- `ContractSpec` mal formé ;
- exception du validateur avec cause ;
- FK OFF, FK ON avec référence absente ;
- transaction active ;
- rollback de persistance ;
- historique inchangé ;
- non-atomicité de deux appels.

Les tests ne couvrent pas : `recursive_triggers=OFF`, `isolation_level`
non nul, mutation après approbation, validateur permissif, `from_approved`
inconnu, ordre version/chronologie, `allow_test_specs` en production,
`ignore_check_constraints`, `row_factory`, concurrence ou crash.

---

## 4. Tableau des contrôles

Légende : **PASS** = vérifié conforme ; **FAIL** = anomalie confirmée ;
**PARTIAL** = preuve incomplète ou garantie non intrinsèque ; **NOT TESTED** =
non exécuté.

### Audit A — sécurité de la connexion

| ID | Contrôle | Méthode | Résultat | Remarque / action |
|---|---|---|---|---|
| A-01 | FK OFF refusé avant validation | test indépendant | **PASS** | `ContractConnectionError`, aucune ligne, pragma inchangé |
| A-02 | `recursive_triggers=OFF` refusé | test indépendant | **PASS** | `ContractConnectionError`, aucune ligne |
| A-03 | `isolation_level` non `None` refusé | test indépendant | **PASS** | `ContractConnectionError`, aucune ligne |
| A-04 | Transaction déjà ouverte refusée sans rollback appelant | test indépendant + suite | **PASS** | marqueur et transaction conservés |
| A-05 | Pragmas de l'appelant non modifiés | test indépendant | **PASS** | FK/RT/isolation identiques après écriture |
| A-06 | Référence inexistante rejetée par SQLite | suite + indépendant | **PASS** | `ContractSQLiteError`, `foreign_key_check` vide |
| A-07 | Erreur de configuration sans écriture partielle | indépendant | **PASS** | count inchangé |
| A-08 | `open_connection` configure FK/RT/isolation | suite + inspection | **PASS** | `test_connection_policy.py` 23/23 |
| A-09 | Alternative `PRAGMA ignore_check_constraints=ON` | test indépendant | **FAIL** | le writer ne vérifie pas ce pragma ; CHECK SQL contourné |
| A-10 | Alternative `row_factory` falsifiant les pragmas | test indépendant | **PARTIAL** | contournement possible avec une connexion malveillante ; risque théorique |
| A-11 | Course entre `_check_connection` et `BEGIN` | non exécuté | **NOT TESTED** | concurrence non couverte |
| A-12 | Sous-classe `sqlite3.Connection` malveillante | non exécuté | **NOT TESTED** | frontière de confiance du processus |

**Détail A-09 :** avec le même document, `presentation_currency="USD"` et
`presentation_conversion` absent :

- `ignore_check_constraints=OFF` → `ContractSQLiteError: CHECK constraint
  failed` ;
- `ignore_check_constraints=ON` → ligne acceptée et persistée.

Le writer ne vérifie pas ce pragma ; `open_connection` ne le désactive pas
explicitement non plus. C'est un chemin alternatif de contournement des
contraintes SQL, même si le mode par défaut de SQLite est OFF.

**Détail A-10 :** un `row_factory` qui renvoie `(1,)` pour les requêtes
`PRAGMA foreign_keys` et `PRAGMA recursive_triggers` permet au writer de
continuer avec une connexion où les deux pragmas sont OFF. La ligne avec
`strategy_missing` est acceptée et `foreign_key_check` montre une violation.
Ce scénario exige du code appelant malveillant, mais il montre que le contrôle
lit des valeurs contrôlées par la connexion, pas une propriété intrinsèque.

### Audit B — registre approuvé

| ID | Contrôle | Méthode | Résultat | Remarque / action |
|---|---|---|---|---|
| B-01 | Nom du contrat correspond au registre | inspection + test | **PASS** | `load_approved_schema` et vérification du nom writer |
| B-02 | Version du contrat correspond au registre | inspection + hash | **PASS** | `1.2.0` pour les deux contrats |
| B-03 | SHA-256 du fichier correspond au registre | calcul indépendant | **PASS** | les deux hashes correspondent |
| B-04 | Schéma `9.9.9` forgé refusé à la construction | suite + indépendant | **PASS** | `ContractApprovalError` |
| B-05 | Validateur construit sur un autre schéma refusé | suite + indépendant | **PASS** | comparaison `.schema` |
| B-06 | `ContractSpec` mal formé rejeté proprement | suite + indépendant | **PASS** | `ContractSpecError` pour les quatre cas testés |
| B-07 | `for_tests` refusé en mode normal | suite + indépendant | **PASS** | `ContractApprovalError`, aucune ligne |
| B-08 | `allow_test_specs=True` impossible à activer accidentellement | inspection + indépendant | **FAIL** | flag public ; un schéma `9.9.9` est accepté avec le flag |
| B-09 | Fichier de schéma modifié sans registre détecté | test indépendant avec racine temporaire | **PASS** | `ContractRegistryError` avec hash attendu/reçu |
| B-10 | Modification du registre sans contournement | test indépendant | **FAIL** | `APPROVED_CONTRACTS` est un dict public mutable ; entrée remplacée → `9.9.9` accepté |
| B-11 | Validateur permissif avec `.schema` officiel | test indépendant | **FAIL** | `iter_errors` vide accepté ; document schéma-invalide persisté |
| B-12 | Schéma approuvé immuable après construction | test indépendant | **FAIL** | mutation des deux copies de schéma → `9.9.9` accepté |
| B-13 | Erreur `from_approved` inconnu normalisée | test indépendant | **FAIL** | `ContractRegistryError` brute au lieu de `ContractApprovalError` |
| B-14 | Hash / version de l'objet en mémoire revérifiés à l'écriture | inspection | **FAIL** | vérification uniquement à la construction |

**Détail B-08 :** avec un `ContractSpec.for_tests` construit sur un schéma
`schema_version.const = "9.9.9"` et un document `9.9.9`, l'appel
`write_experiment(..., allow_test_specs=True)` écrit la ligne. Le flag est
documenté comme réservé aux tests (`WRITER_INTEGRATION.md:69-77`), mais aucun
mécanisme de production ne l'interdit : c'est un booléen d'API publique.

**Détail B-10 :** le registre est un `dict` module-level exporté. Remplacer
`APPROVED_CONTRACTS["experiment"]` par une entrée pointant vers un fichier
temporaire `9.9.9` et son hash permet à `ContractSpec.from_approved` de
construire une spec acceptée, puis d'écrire `9.9.9`. Une exécution de code
dans le processus peut toujours contourner ; il ne faut pas présenter le
registre comme un ancrage cryptographique externe.

**Détail B-11 :** un validateur factice avec
`schema = official_schema` et `iter_errors = []` passe
`ContractSpec.from_approved`. Le writer persiste alors un document avec
`code_version = ""`, qui viole `minLength: 1` du schéma mais passe les
contraintes SQL. Le contrôle d'approbation vérifie la valeur `.schema`, pas le
comportement du validateur.

**Détail B-12 :** `ContractSpec` est `frozen=True`, mais son `schema` est un
dictionnaire imbriqué et `validator.schema` peut être le même objet ou un autre
dictionnaire mutable. Après approbation, remplacer
`properties.schema_version.const` par `9.9.9` dans les deux objets, puis
écrire un document `9.9.9`, est accepté. Un second contrôle avec
`ContractSpec.from_approved` et mutation des deux copies a également accepté.
La vérification du registre n'est faite qu'à la construction.

**Détail B-13 :** `ContractSpec.from_approved("unknown_contract", validator)`
lève `ContractRegistryError` (sous-classe de `RuntimeError`) et non
`ContractApprovalError` (sous-classe de `ContractWriteError`). Un appelant qui
attrape la famille `ContractWriteError` ne verra pas cette erreur.

### Audit C — validation et erreurs

| ID | Contrôle | Méthode | Résultat | Remarque / action |
|---|---|---|---|---|
| C-01 | Ordre annoncé schéma → chronologie → version | test indépendant | **FAIL** | ordre réel schéma → version du schéma → chronologie |
| C-02 | Version absente classée `version` | suite + indépendant | **PASS** | `ContractVersionError`, aucune ligne |
| C-03 | Version inconnue/incompatible | suite + indépendant | **PASS** | `9.9.9`/`1.1.0` refusés avec le schéma officiel |
| C-04 | Document non conforme au schéma | suite + indépendant | **PASS** | `ContractSchemaError` |
| C-05 | Chronologie invalide | suite + indépendant | **PASS** | `ContractChronologyError` |
| C-06 | Validateur qui lève une exception | suite + indépendant | **PASS** | `ContractValidatorError` avec cause `SchemaValidatorError` → `RuntimeError` |
| C-07 | Schéma/spec mal formé | suite + indépendant | **PASS** | `ContractSpecError` |
| C-08 | Erreur SQL | suite + indépendant | **PASS** | `ContractSQLiteError` |
| C-09 | Divergence document/ligne relue | suite + indépendant | **PASS** | `ContractPersistenceError`, rollback |
| C-10 | Toutes les erreurs catégorisées | inspection + tests | **PARTIAL** | B-13 brute ; C-11 reclasse l'absence de `period` |
| C-11 | Erreur masquée ou reclassée à tort | test indépendant | **FAIL** | `required` multiple : `period` absent classé `version` |
| C-12 | Cause exploitable lors de l'encapsulation | test indépendant | **PASS** | chaîne `ContractValidatorError → SchemaValidatorError → RuntimeError` |
| C-13 | Document non `Mapping` | test indépendant | **PASS** | `ContractSchemaError` avec validateur officiel |

**Détail C-01 :** un document avec `schema_version=9.9.9` et une période
inversée produit `[('version', ...)]` dans `contract_issues` et
`ContractVersionError` dans le writer. La chronologie est ignorée. A0
(`REPORT_A0_WRITER_HARDENING.md:96-104`) et `WRITER_INTEGRATION.md:93-100`
annoncent l'ordre inverse (schéma, chronologie, version). Le code de
`contract_issues` documente pourtant l'ordre réel dans sa docstring
(`contracts.py:151`). Il s'agit d'une divergence documentaire et de catégorie,
pas d'une écriture partielle.

**Détail C-11 :** un document sans `schema_version` et sans `period`
produit deux messages `required`, tous deux classés `version` :

```text
('version', "<root>: 'period' is a required property")
('version', "<root>: 'schema_version' is a required property")
```

Le writer lève donc une erreur de version, alors que l'absence de `period`
est une erreur de schéma. Les deux champs manquants sont dans le même objet
d'erreur `required` racine et `_is_version_error` classe l'objet entier
(`contracts.py:65-71`).

### Audit D — transactions et persistance

| ID | Contrôle | Méthode | Résultat | Remarque / action |
|---|---|---|---|---|
| D-01 | Refus d'une transaction appelante | suite + indépendant | **PASS** | transaction et marqueur conservés |
| D-02 | Validation échouée sans écriture | suite + indépendant | **PASS** | count inchangé |
| D-03 | Insertion SQL échouée sans écriture | suite + indépendant | **PASS** | rollback, aucune ligne |
| D-04 | Divergence après écriture → rollback | suite + indépendant | **PASS** | `ContractPersistenceError`, aucune ligne |
| D-05 | Absence d'écriture partielle | tests | **PASS** | sur les scénarios exécutés |
| D-06 | Document validé vs ligne relue | suite barème + indépendant expérience | **PASS** | comparaison de toutes les colonnes écrites |
| D-07 | Conservation de l'historique | suite | **PASS** | ligne `exp_fixture_001` inchangée |
| D-08 | Deux appels indépendants non atomiques | suite + indépendant | **PASS** | premier commit conservé, second absent |
| D-09 | Documentation de l'absence d'atomicité de groupe | documentaire | **PASS** | `WRITER_INTEGRATION.md:138-149` |
| D-10 | `contract_write_batch` non implémenté | `grep` + inspection | **PASS** | uniquement documenté, aucun code |
| D-11 | `allow_test_specs=True` hors tests | test indépendant | **FAIL** | B-08 ; écriture `9.9.9` acceptée |
| D-12 | Concurrence, crash, reprise | non exécuté | **NOT TESTED** | aucune garantie revendiquée |
| D-13 | INSERT SQL direct contournant le writer | documentaire | **PASS** | limite documentée, non empêchée |

Le test `test_two_writer_calls_are_not_one_transaction` démontre bien qu'un
barème reste commité si l'expérience suivante échoue. Aucune API de groupe
n'existe.

### Audit E — migrations et traçabilité

| ID | Contrôle | Méthode | Résultat | Remarque / action |
|---|---|---|---|---|
| E-01 | Hashes du manifeste = fichiers actuels | calcul + suite | **PASS** | `0004` à `0007` |
| E-02 | Manifeste couvre tous les `.sql` | test | **PASS** | 4/4 |
| E-03 | Test détecte un fichier modifié | copie temporaire + appel du test | **PASS** | Assertion sur hash |
| E-04 | Test détecte une migration absente du manifeste | copie temporaire | **PASS** | Couverture 4/4 |
| E-05 | Test résiste à une modification conjointe fichier + manifeste | copie temporaire | **PARTIAL** | limite attendue : les deux modifiés → test accepte ; baseline auto-référentielle |
| E-06 | Migrations suivies par Git | `git ls-files` | **PARTIAL** | 0 fichier ; aucun historique formel |
| E-07 | Non-modification historique des migrations | mtimes + inspection | **PARTIAL** | mtimes antérieurs au durcissement, mais aucune baseline Git |
| E-08 | Avertissements historiques présents | inspection | **PASS** | bannières A5-06/0007/writer, résultats d'origine conservés |

**Détail E-05 :** sur une copie temporaire, modifier
`0005_p0_foundations.sql`, recalculer son hash et mettre à jour
`SHA256SUMS` fait passer `test_migration_manifest_matches_files`. C'est normal :
le manifeste prouve l'identité relative à sa propre baseline, pas l'immutabilité
ni une signature externe. Il ne faut pas le présenter comme une preuve
cryptographique d'historique.

**Détail E-06 :** `git ls-files schemas/migrations` ne retourne rien.
`SHA256SUMS` lui-même n'est pas suivi. La non-modification passée n'est donc
pas prouvée, même si les mtimes observés sont antérieurs au writer.

### Audit F — dépendance de validation

| ID | Contrôle | Méthode | Résultat | Remarque / action |
|---|---|---|---|---|
| F-01 | `jsonschema` importé par `src/` | `grep` | **PASS** | aucun import dans `src/` |
| F-02 | Writer importable sans `jsonschema` | `python -S` + import | **PASS** | import réussi, `jsonschema` absent de `sys.modules` |
| F-03 | Implémentation de validation alternative | `grep`/inspection | **FAIL** | aucun validateur concret dans `src/` |
| F-04 | Dépendances de production documentées | inspection | **PARTIAL** | `jsonschema` seulement dans `tests/requirements-test.txt` ; `requirements.txt` ne le contient pas |
| F-05 | Absence de dépendance bloque l'usage réel | analyse | **PARTIAL** | import possible, mais aucune validation de production approuvée ; `from_approved` exige un validateur |
| F-06 | Solution de remplacement déjà présente | inspection | **FAIL** | aucune |

Le writer peut être importé dans un environnement sans `jsonschema` ; il ne
peut pas valider sans qu'un appelant fournisse un objet `iter_errors` et
`.schema`. `ContractSpec.for_tests` + `allow_test_specs=True` permet d'écrire
sans validation réelle : ce n'est pas une solution de production.

**Options disponibles, sans choix à la place du propriétaire :**

1. approuver `jsonschema` en dépendance de production, avec version épinglée
   (`4.26.0` est déjà la version de test) ;
2. fournir et approuver une autre implémentation `iter_errors`, avec tests de
   conformité et intégration au registre ;
3. maintenir l'absence de dépendance et bloquer l'intégration A1/A2.

L'option 3 est l'état actuel. Aucune modification de dépendances n'a été faite.

---

## 5. Tests exécutés et résultats exacts

Toutes les commandes suivantes ont été exécutées dans l'environnement du
projet, sans réseau ni installation.

```powershell
.\.venv\Scripts\python.exe -m pytest tests -q -rxX
# 672 passed in 25.11s

.\.venv\Scripts\python.exe -m pytest tests --collect-only -q
# 672 tests collected in 0.14s

.\.venv\Scripts\python.exe -m pytest tests -q --runxfail
# 672 passed in 27.64s

.\.venv\Scripts\python.exe -m pytest tests\integration\test_p0_candidates.py -q
# 55 passed in 6.24s

.\.venv\Scripts\python.exe -m pytest `
  tests\unit\test_contracts_negative.py `
  tests\unit\test_contracts_schema_validity.py `
  tests\integration\test_contract_sql_parity.py -q
# 261 passed in 3.54s

.\.venv\Scripts\python.exe -m pytest `
  tests\integration\test_0007_contract_sql_alignment.py `
  tests\unit\test_contract_validation.py `
  tests\integration\test_contract_writer.py -q
# 47 passed in 6.52s

.\.venv\Scripts\python.exe -m pytest tests\integration\test_migration_manifest.py -q
# 2 passed in 0.02s

.\.venv\Scripts\python.exe -m pytest tests\integration\test_connection_policy.py -q
# 23 passed in 0.38s

git diff --check
# exit 0 ; avertissements CRLF uniquement

git ls-files schemas/migrations
# aucun fichier
```

### 5.1 Audit indépendant

Script temporaire : `%TEMP%\a5_post_hardening_audit.py` (non versionné, hors
dépôt). Il reconstruit une base 0.7 en mémoire avec les migrations officielles
et les fixtures, puis exécute 68 assertions.

```text
66 PASS, 2 FAIL, 68 checks
FAILED: B4 from_approved nom inconnu erreur normalisée
        ContractRegistryError: contrat non enregistré pour la production
FAILED: C2 required multiple classé version
        [('version', "... 'period' is a required property"),
         ('version', "... 'schema_version' is a required property")]
```

Ce décompte doit être lu avec précaution : les assertions `A9`, `A10`, `B7`,
`B10`, `B12` et `B13` sont des assertions de **contournement confirmé** ; elles
sont classées FAIL/PARTIAL dans le tableau ci-dessus, pas comme des PASS de
garantie.

Contrôles complémentaires exécutés hors script principal :

- `ignore_check_constraints=OFF` → `ContractSQLiteError` CHECK ;
  `ON` → ligne acceptée ; différence observée sur le même document.
- `ContractSpec.from_approved` + mutation de `spec.schema` et
  `spec.validator.schema` → écriture `9.9.9` acceptée.
- `ContractSpec.from_approved("unknown", ...)` → `ContractRegistryError`.
- Doublon expérience → `ContractSQLiteError`, lignes existantes conservées.
- Trigger de statut `planned -> running` → `ContractPersistenceError`,
  aucune ligne.
- Copie temporaire de migration modifiée → test manifeste rejette ; fichier
  + manifeste modifiés ensemble → test accepte.
- `python -S` avec `src/` → import du writer réussi sans `jsonschema`.

---

## 6. Anomalies reproduites

### A5-PH-01 — Approbation contournable par mutation du schéma après construction — **Moyen**

**Scénario :** construire une spec approuvée avec le schéma officiel et son
validateur, puis muter `properties.schema_version.const` en `9.9.9` dans les
deux copies de schéma (`spec.schema` et `validator.schema`), ou dans l'objet
unique lorsqu'il est partagé par une construction directe.  
**Attendu :** l'approbation doit rester liée à l'objet approuvé ; une version
`9.9.9` doit être refusée.  
**Observé :** `ContractSpec.from_approved` ou
`ContractSpec(..., approved=True)` accepte la mutation ; un document `9.9.9`
est écrit et persisté.  
**Méthode :** script indépendant, écriture en mémoire.  
**Gravité :** moyenne. `ContractSpec` est `frozen` au niveau des attributs,
pas profondément ; le registre n'est pas revérifié à chaque écriture.  
**Action recommandée :** copie profonde/figeage du schéma, ou stockage d'un
hash et `verify_approved_schema` à chaque `write`, plus test de mutation
post-approbation.

### A5-PH-02 — Validateur permissif accepté si `.schema` est officiel — **Moyen**

**Scénario :** validateur avec `schema = official_schema` et
`iter_errors()` retournant toujours `[]`.  
**Attendu :** l'approbation doit garantir un validateur réellement construit
sur le schéma approuvé, ou refuser un validateur non vérifiable.  
**Observé :** `ContractSpec.from_approved` accepte ; un document avec
`code_version=""` (violation `minLength: 1`) est écrit.  
**Méthode :** script indépendant.  
**Gravité :** moyenne ; la vérification porte sur la valeur `.schema`, pas sur
le comportement.  
**Action recommandée :** validateur fourni par une fabrique approuvée, ou
validation exécutée dans le writer avec une implémentation approuvée ; au
minimum, documenter que le validateur est une frontière de confiance.

### A5-PH-03 — `allow_test_specs=True` est un contournement public — **Moyen**

**Scénario :** spec de test `9.9.9` + `allow_test_specs=True`.  
**Attendu :** le mode test ne doit pas être accessible depuis un writer de
production, ou doit être structurellement séparé.  
**Observé :** `write_experiment` écrit `9.9.9`.  
**Méthode :** test indépendant B-10.  
**Gravité :** moyenne ; le flag est documenté test-only mais reste un booléen
public.  
**Action recommandée :** API de test séparée (helper non exporté en
production), ou contrôle d'environnement/mode explicite, ou suppression du
flag des fonctions de production. Test de non-usage en production.

### A5-PH-04 — Registre mutable en mémoire — **Faible/Moyen**

**Scénario :** remplacer `APPROVED_CONTRACTS["experiment"]` par une entrée
pointant vers un fichier `9.9.9` et son hash.  
**Attendu :** une modification du registre ne doit pas permettre de contourner
silencieusement les contrôles d'approbation.  
**Observé :** `ContractSpec.from_approved` accepte et le writer écrit
`9.9.9`.  
**Méthode :** script indépendant B-13.  
**Gravité :** faible à moyenne ; nécessite du code dans le processus, mais le
registre est exporté et mutable.  
**Action recommandée :** mapping immuable/privé, entrées immuables, tests de
non-mutabilité ; ou documenter que la garantie ne vaut que contre une
modification accidentelle du fichier.

### A5-PH-05 — `from_approved` ne normalise pas l'erreur de registre — **Faible**

**Scénario :** nom inconnu.  
**Attendu :** erreur `spec`/`approval` de la famille `ContractWriteError`.  
**Observé :** `ContractRegistryError` brute.  
**Méthode :** test indépendant B-04.  
**Gravité :** faible ; aucune écriture, mais contrat d'erreur instable.  
**Action recommandée :** envelopper `load_approved_schema` dans
`ContractApprovalError` avec `from`.

### A5-PH-06 — Ordre réel version → chronologie différent de l'ordre annoncé — **Faible/Moyen**

**Scénario :** document avec version `9.9.9` et période égale/inversée.  
**Attendu (documentation) :** erreur de chronologie avant version.  
**Observé :** `ContractVersionError` ; `contract_issues` retourne
`[('version', ...)]` avant d'évaluer la chronologie.  
**Méthode :** test indépendant C-01.  
**Gravité :** faible pour l'intégrité, moyenne pour le contrat d'erreur.  
**Action recommandée :** choisir l'ordre officiel et aligner
`contract_issues`, A0, `WRITER_INTEGRATION.md`, tests.

### A5-PH-07 — Erreur `required` multiple classée entièrement version — **Faible**

**Scénario :** document sans `schema_version` et sans `period`.  
**Attendu :** `period` manquant → erreur de schéma ; version → version.  
**Observé :** les deux messages sont classés `version`.  
**Méthode :** test indépendant C-11.  
**Gravité :** faible ; refus correct, catégorie trompeuse.  
**Action recommandée :** séparer les champs manquants ou ne classer version
que l'erreur concernant uniquement `schema_version` ; test dédié.

### A5-PH-08 — `ignore_check_constraints` contourne les CHECK SQL — **Moyen**

**Scénario :** connexion avec FK/RT/isolation conformes, mais
`PRAGMA ignore_check_constraints=ON`.  
**Attendu :** le writer devrait refuser une configuration qui désactive les
contraintes, ou vérifier l'intégrité après écriture.  
**Observé :** document avec `presentation_currency="USD"` sans conversion
accepté et persisté.  
**Méthode :** test indépendant A-09.  
**Gravité :** moyenne ; mode par défaut OFF, mais non vérifié.  
**Action recommandée :** exiger `ignore_check_constraints=0` (ou ne pas
supporter ce pragma), ajouter un test ; à défaut, documenter la limite.

### A5-PH-09 — `row_factory` peut falsifier les pragmas — **Faible**

**Scénario :** `row_factory` renvoyant `(1,)` pour les PRAGMA.  
**Attendu :** contrôle indépendant de la valeur contrôlée par l'appelant.  
**Observé :** writer accepte une connexion FK/RT OFF et persiste une
référence inexistante.  
**Méthode :** test indépendant A-10.  
**Gravité :** faible ; nécessite une connexion malveillante.  
**Action recommandée :** utiliser une connexion issue d'`open_connection` ou
vérifier les pragmas via un mécanisme non influencé par `row_factory` ; sinon
documenter la frontière de confiance.

### A5-PH-10 — Manifeste auto-référentiel et migrations non suivies — **Info**

**Scénario :** modifier une migration et mettre à jour `SHA256SUMS` ensemble ;
ou modifier le manifeste.  
**Attendu :** le test du manifeste ne doit pas être présenté comme une preuve
d'historique.  
**Observé :** test rejette un fichier modifié seul ; accepte fichier +
manifeste modifiés ensemble ; `git ls-files` vide.  
**Méthode :** copie temporaire + test ; `git ls-files`.  
**Gravité :** information/limite de preuve.  
**Action recommandée :** committer migrations + manifeste dans Git et
conserver le commit de référence ; ne pas prétendre à l'immutabilité passée.

### A5-PH-11 — Aucun validateur de production approuvé — **Bloquant A1/A2**

**Scénario :** intégration réelle A1/A2 sans `jsonschema` approuvé.  
**Attendu :** un validateur de production disponible et documenté.  
**Observé :** `src/` n'a aucune implémentation ; `jsonschema` est une
dépendance de test ; `from_approved` exige un validateur fourni.  
**Méthode :** `grep`, `python -S`, inspection des requirements.  
**Gravité :** bloquante pour une validation de production.  
**Action recommandée :** décision propriétaire sur `jsonschema` ou
implémentation alternative approuvée ; tests de conformité.

### A5-PH-12 — Concurrence, crash et reprise non testés — **Info**

Aucun test de concurrence/crash. Les garanties correspondantes ne sont pas
mesurées. Ne pas les revendiquer.

---

## 7. Risques résiduels

1. **Frontière de confiance du validateur.** Le writer dépend d'un objet
   appelant pour la validation ; `.schema` est une valeur reconstructible.
   Un validateur permissif peut annuler la garantie d'approbation (B-11).
2. **Mutabilité de l'approbation.** Le schéma et le registre sont mutables en
   mémoire ; une approbation n'est pas scellée (B-10/B-12).
3. **Flag de test public.** `allow_test_specs=True` permet une écriture non
   approuvée (B-08/D-11).
4. **Contrat d'erreur incomplet.** `from_approved` inconnu fuit une erreur
   registre (B-13) ; `required` multiple reclasse `period` en version (C-11).
5. **Ordre documenté faux.** Version avant chronologie (C-01).
6. **Pragmas non couverts.** `ignore_check_constraints` (A-09), `row_factory`
   (A-10), `defer_foreign_keys`, `trusted_schema`, `busy_timeout`,
   `journal_mode` ne sont pas vérifiés par le writer.
7. **Atomicité de groupe absente.** Deux writers indépendants ne forment pas
   une transaction (D-08/D-09). `contract_write_batch` n'existe pas.
8. **Dépendance de production absente.** A1/A2 ne peuvent pas utiliser une
   validation approuvée sans décision (F-01..F-06).
9. **Aucune preuve concurrence/crash.** Pas de garantie de reprise (D-12).
10. **Manifeste auto-référentiel.** Les migrations ne sont pas suivies par Git ;
    la baseline ne prouve que l'identité courante (E-05/E-06).
11. **`INSERT` direct.** Le writer n'est pas un verrou de schéma ; un appel
    SQL direct peut le contourner (D-13).
12. **Packaging.** `registry.ROOT` dépend de la présence de `contracts/` à côté
    de `src/` ; un paquet installé séparément doit embarquer les contrats.

---

## 8. Blocages à l'intégration A1/A2

### Blocages durs

1. **Validateur de production non approuvé.** Choisir et épingler
   `jsonschema` ou une implémentation alternative. Sans cela, A1/A2 ne peut
   pas valider réellement les contrats.
2. **Approbation non scellée.** Avant d'utiliser `ContractSpec` comme frontière
   de sécurité, rendre le schéma/validateur immuables ou revérifier le hash et
   le schéma à chaque écriture (A5-PH-01/B-12).
3. **Validateur non vérifiable.** Ne pas se contenter de `.schema` ; utiliser
   une fabrique approuvée ou un validateur dont l'implémentation est approuvée
   (A5-PH-02/B-11).
4. **Flag test accessible.** Retirer ou isoler `allow_test_specs` du chemin de
   production (A5-PH-03/B-08).
5. **Erreur `from_approved` non normalisée.** A1/A2 doit pouvoir attraper une
   erreur d'approbation stable (A5-PH-05/B-13).

### Conditions opérationnelles

- Utiliser exclusivement `open_connection` et ne jamais passer une connexion
  brute à un writer de production.
- Ne pas utiliser `INSERT` direct pour `experiments`/`fee_schedules`.
- Ne pas supposer l'atomicité de plusieurs writers ; définir une transaction
  de groupe si nécessaire.
- Ne pas utiliser `ContractSpec.for_tests` hors tests.
- Documenter l'ordre réel et les catégories d'erreur une fois corrigés.
- Ajouter des tests de non-régression pour B-08, B-10, B-11, B-12, B-13,
  A-09, A-10, C-01, C-11.
- Ne pas revendiquer de garantie concurrence/crash.

### Non-bloquant pour une intégration locale encadrée

- Seuls `experiment` et `fee_schedule` sont couverts.
- Aucun writer A1/A2 de production n'existe encore.
- Les migrations `0005`/`0006`/`0007` restent des candidats non approuvés.
- Aucune base réelle n'existe.

---

## 9. Comparaison avec le précédent audit A5

| Point | Audit A5 précédent | État post-durcissement |
|---|---|---|
| Suite | 653/653/0 | **672/672/0** |
| FK OFF | contournement accepté | **refusé avant validation** |
| RT OFF | non couvert | **refusé** (test indépendant) |
| `isolation_level` non nul | non couvert | **refusé** |
| Transaction active | signalée comme non documentée | **refusée, transaction appelante intacte, documentée** |
| Version absente | `ContractSchemaError` (1 FAIL) | **`ContractVersionError` (PASS)** |
| `9.9.9` injecté à la construction | accepté avec un schéma de test | **refusé à la construction ; encore contournable après mutation ou avec `allow_test_specs`** |
| `validate_contract` dupliqué | writer dupliquait la séquence | **centralisé dans `contract_issues`** |
| Erreurs validateur | brute | **`ContractValidatorError` avec cause** |
| `ContractSpec` mal formé | `AttributeError` | **`ContractSpecError`** |
| Registre SHA-256 | absent | **ajouté** ; mutable en mémoire |
| Manifeste migrations | absent | **ajouté** ; auto-référentiel, non suivi Git |
| Atomicité multi-écritures | non documentée | **documentée et testée non atomique** |
| `contract_write_batch` | absent | **toujours absent, documenté non implémenté** |
| Validateur de production | absent | **toujours absent** |
| Tests writer | 14 | **31** |
| Tests migration manifeste | 0 | **2** |
| Concurrence/crash | non testé | **toujours non testé** |

Le durcissement corrige les deux défauts majeurs du précédent audit (FK OFF et
`9.9.9` forgé à la construction) et la classification de la version absente.
Il introduit toutefois une garantie d'approbation qui n'est pas encore
intrinsèque : la validation dépend d'un validateur fourni et d'objets mutables.

---

## 10. Recommandation finale

**A — le writer nécessite encore des corrections ciblées avant une intégration
expérimentale A1/A2.**

Justification : les contrôles nominaux et les tests sont solides, mais les
points B-08/B-10/B-11/B-12/B-13, C-01/C-11, A-09/A-10 et F-01..F-06 empêchent
de présenter l'approbation, les catégories d'erreur et la validation de
production comme garanties complètes. Les corrections sont locales et ne
remettent pas en cause l'architecture du writer.

Ordre de priorité proposé :

1. **P0 — validation de production :** trancher `jsonschema` ou fournir un
   validateur approuvé ; sans cela, l'intégration A1/A2 reste bloquée.
2. **P0 — approbation scellée :** empêcher la mutation du schéma/registre ou
   revérifier le hash et le schéma à chaque écriture ; refuser un validateur
   non vérifiable.
3. **P1 — test-only :** séparer ou protéger `allow_test_specs`; test de
   non-usage en production.
4. **P1 — erreurs :** envelopper `from_approved` et corriger la classification
   `required` multiple ; aligner l'ordre version/chronologie avec la
   documentation.
5. **P1 — connexion :** vérifier `ignore_check_constraints` et ne pas dépendre
   d'un `row_factory` appelant ; ajouter les tests de configuration.
6. **P2 — traçabilité :** committer migrations + `SHA256SUMS` dans Git ; ne pas
   présenter le manifeste comme une preuve d'historique.
7. **P2 — tests :** ajouter les régressions B-08/B-10/B-11/B-12/B-13,
   A-09/A-10, C-01/C-11, et documenter les cas concurrence/crash non testés.

Après ces corrections, un nouvel audit A5 ciblé pourra réévaluer un passage à
une intégration expérimentale locale sous conditions. **Aucun gel, aucun
commit, aucune approbation définitive des contrats n'est prononcé dans ce
rapport.**
