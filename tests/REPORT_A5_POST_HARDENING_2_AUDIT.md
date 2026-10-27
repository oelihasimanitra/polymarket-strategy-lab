# Rapport A5 — audit indépendant du Contract Writer candidat 2

**Date :** 2026-10-27  
**Auditeur :** A5 — validation et benchmark  
**Objet :** audit indépendant de `tests/REPORT_A0_WRITER_HARDENING_2.md`, du
writer normal, du parcours de test séparé, du registre, du validateur système
et du manifeste des migrations.  
**Statut :** audit en lecture seule. Aucun fichier de production, migration,
test ou rapport historique modifié. Aucun commit. Aucun gel. Aucune base
réelle, aucune collecte Polymarket, aucune simulation, aucun ajout de
dépendance de production.

---

## 1. Résumé exécutif

**Verdict global : PARTIEL.** Le writer normal ne reçoit plus ni schéma ni
validateur de l'appelant, le registre public est une vue en lecture seule, le
schéma est gelé profondément, et le writer recharge et revérifie l'approbation
à chaque écriture. Les 717 tests annoncés sont reproductibles, et les
contournements ordinaires confirmés par l'audit précédent ne fonctionnent plus.

Le validateur système candidat est nettement meilleur qu'un simple « validateur
maison sans oracle » : sur les schémas approuvés actuels, les comparaisons avec
`jsonschema` donnent **0 divergence sur 186 cas construits et 5 000 mutations
déterministes**. Il reste toutefois un sous-ensemble JSON Schema, avec une
divergence réelle sur `multipleOf` décimal (non utilisé par les contrats
approuvés), et une validation incomplète des cibles de `$ref` à la
construction.

Résultats vérifiés :

- `717 passed` sur la suite complète ;
- `717 tests collected` ;
- `717 passed` avec `--runxfail` ;
- `55 passed` pour les tests P0 ;
- `261 passed` pour les contrôles contrats/parité SQL ;
- `83 passed` pour migrations 0007 + validation + writer + validateur système ;
- `11 passed` pour le manifeste des migrations ;
- `18 passed` pour les tests de reproduction ciblés ;
- `23 passed` pour la politique de connexion SQLite ;
- `git diff --check` : exit 0, avertissements CRLF uniquement ;
- `git ls-files schemas/migrations` : 0 fichier suivi.

L'audit indépendant du writer et de l'approbation exécute **52 contrôles :
52 PASS, 0 FAIL**. L'audit indépendant du validateur exécute en plus :

- **186 cas** construits : 0 divergence, 26 documents valides / 160 invalides ;
- **5 000 mutations** déterministes : 0 divergence ;
- **173 cas de mots-clés** : 2 divergences, toutes sur `multipleOf` décimal.

**Recommandation finale : B — une intégration expérimentale locale est
possible sous conditions, sans gel des contrats.** La condition centrale est
que le propriétaire accepte explicitement l'option B (validateur système) pour
l'usage expérimental, ou choisisse l'option A (`jsonschema`). Le writer ne doit
pas être présenté comme approuvé pour la production, et ses limites de
concurrence, de crash et de validation JSON Schema complète restent ouvertes.

---

## 2. Périmètre exact

### 2.1 Code et documents inspectés

- `src/polymarket_lab/storage/contract_writer.py` — writer normal, connexion,
  validation, approbation finale, transaction, relecture.
- `src/polymarket_lab/storage/contract_writer_testing.py` — parcours de test
  séparé.
- `src/polymarket_lab/validation/registry.py` — registre privé, vue publique,
  hash, version, gel.
- `src/polymarket_lab/validation/schema_validator.py` — `SystemSchemaValidator`.
- `src/polymarket_lab/validation/immutability.py` — gel profond.
- `src/polymarket_lab/validation/contracts.py` — `contract_issues`, ordre,
  classification.
- `src/polymarket_lab/storage/connection.py` — `open_connection`, transaction,
  pragmas.
- `tests/integration/test_contract_writer.py` — 51 tests.
- `tests/unit/test_system_schema_validator.py` — 12 tests.
- `tests/integration/test_migration_manifest.py` — 11 tests.
- `schemas/migrations/SHA256SUMS`, migrations `0004` à `0007`.
- `WRITER_INTEGRATION.md`, `ARCHITECTURE.md`, `DECISIONS.md`, `tests/README.md`,
  rapport A0 de durcissement 2, rapports A5 antérieurs.

### 2.2 Périmètre non exécuté

- Aucun test de concurrence multi-connexions, de verrou, de timeout, de crash
  après commit ou de reprise après crash.
- Aucune base de données réelle.
- Aucun branchement A1/A2 de production ; aucune collecte ni simulation.
- Aucun test de packaging installé hors dépôt.
- Aucun test de permission réelle pour `ContractSchemaUnreadableError`.
- Aucun test exhaustif de conformité JSON Schema avec une suite externe.
- Aucune décision propriétaire sur l'option A ou B de validation de production.

### 2.3 Nature des preuves

- **Exécuté :** pytest, scripts indépendants, copies temporaires, `python -S`.
- **Statique :** lecture du code, `grep`, signatures, inspection des exports.
- **Documentaire :** A0, `WRITER_INTEGRATION.md`, D-053/D-054, README.
- **Hypothèse non mesurée :** résistance à un code arbitraire dans le même
  processus, concurrence, crash, packaging.

---

## 3. Contrôles exécutés et résultats

Légende : **PASS** = vérifié conforme ; **FAIL** = anomalie confirmée ;
**PARTIAL** = preuve incomplète ou garantie non intrinsèque ; **NOT TESTED** =
non exécuté.

### Audit A — approbation des contrats

| ID | Contrôle | Méthode | Résultat | Remarque |
|---|---|---|---|---|
| A-01 | Le writer normal ne reçoit pas de schéma arbitraire | signature + test | **PASS** | `write_experiment(connection, document)` seulement |
| A-02 | Le writer normal ne reçoit pas de validateur arbitraire | signature + test | **PASS** | `ContractSpec.from_approved(name)` sans validateur |
| A-03 | Un simple `.schema` ne suffit pas en mode normal | inspection + test | **PASS** | normal construit `SystemSchemaValidator` ; `.schema` n'est utilisé que par `TestContractSpec` |
| A-04 | Mutation ordinaire du schéma/validateur bloquée | test indépendant | **PASS** | `TypeError` sur `spec.schema` et `spec.validator.schema` |
| A-05 | Registre public non remplaçable par un appelant ordinaire | test indépendant | **PASS** | `APPROVED_CONTRACTS` est `MappingProxyType` ; alias public remplacé sans effet sur le writer |
| A-06 | Version et empreinte du contrat réellement utilisé | inspection + test | **PASS** | hash SHA-256 et version `1.2.0` relus |
| A-07 | Le schéma approuvé est celui appliqué | inspection | **PASS** | `SystemSchemaValidator` est construit depuis le schéma gelé chargé |
| A-08 | Une spec de test ne rejoint pas le parcours normal | signatures + tests | **PASS** | module séparé, non exporté ; argument positionnel refusé |
| A-09 | Chemins publics/imports sans contournement accidentel | inspection + `grep` | **PASS** | API normale réduite ; token privé et module de test restent accessibles au code arbitraire |
| A-10 | Échec d'approbation avant toute écriture | test + inspection | **PASS** | chargement initial + vérification finale avant insertion ; aucune ligne |
| A-11 | Vérification finale au plus près de l'insertion | inspection + patch de test | **PASS** | `ContractApprovalError`, cause hash, aucune ligne |
| A-12 | Résistance au code Python arbitraire | non testé | **NOT TESTED** | non revendiquée : `object.__setattr__`, monkeypatch, globals privés |
| A-13 | Parcours de test écrit un schéma `9.9.9` | test indépendant | **PASS** | comportement explicite du module `contract_writer_testing` |
| A-14 | Writer normal refuse `9.9.9` | test indépendant | **PASS** | `ContractVersionError`, aucune ligne |

**Précision importante :** la protection est une barrière contre les mutations
ordinaires et les erreurs de configuration, pas une isolation de sécurité de
processus. Un acteur qui exécute du Python arbitraire peut importer
`_APPROVED_SPEC_TOKEN`, réassigner un global privé, remplacer `registry.ROOT`
ou monkeypatcher une fonction. A0 documente cette limite ; elle n'est pas
comptée comme un FAIL du writer.

### Audit B — validateur interne

| ID | Contrôle | Méthode | Résultat | Remarque |
|---|---|---|---|---|
| B-01 | Fonctionnalités supportées identifiées | inspection | **PASS** | liste explicite dans `schema_validator.py` |
| B-02 | Fonctionnalités non supportées refusées | 11 schémas indépendants | **PASS** | `patternProperties`, `format`, `not`, `contains`, ref distante, ref absente, booléen, `items: true`, listes vides |
| B-03 | Parité sur les contrats approuvés | 186 cas + 5 000 mutations | **PASS** | 0 divergence de validité |
| B-04 | Parité sur le sous-ensemble de mots-clés | 173 cas | **PARTIAL** | 2 divergences sur `multipleOf` décimal |
| B-05 | Schémas mal formés / `$ref` | tests indépendants | **PARTIAL** | `$ref` vers non-schéma et cycle acceptés à la construction ; erreur à la validation |
| B-06 | Règles métier séparées du schéma | inspection | **PASS** | chronologie, `completed_at`, `paper_live.end_time`, contraintes SQL, approbation |
| B-07 | Conformité JSON Schema complète | analyse | **PARTIAL** | sous-ensemble volontaire, pas de conformité complète |
| B-08 | Définitions et références locales | tests réels | **PASS** | `$defs` et `$ref` locaux utilisés par les contrats |
| B-09 | `multipleOf` décimal | test indépendant | **FAIL (faible)** | 0.3 accepté par le système, refusé par `jsonschema` |
| B-10 | Champs `null`, limites, tableaux, dates, versions | 186 cas | **PASS** | catégories couvertes par la matrice |
| B-11 | Erreurs multiples | tests + indépendant | **PASS** | ordre et catégories vérifiés |

### Audit C — SQLite

| ID | Contrôle | Méthode | Résultat | Remarque |
|---|---|---|---|---|
| C-01 | `foreign_keys=ON` | test indépendant | **PASS** | refus avant validation, aucune ligne |
| C-02 | `recursive_triggers=ON` | test indépendant | **PASS** | refus avant validation |
| C-03 | `ignore_check_constraints=OFF` | test indépendant | **PASS** | refus si ON, pragma non modifié |
| C-04 | `isolation_level=None` | test indépendant | **PASS** | refus si non nul |
| C-05 | Transaction appelante active | test indépendant | **PASS** | refus, transaction et marqueur conservés |
| C-06 | `row_factory` non pris en charge | test indépendant | **PASS** | `None` et `sqlite3.Row` acceptés ; callable refusé avant validation |
| C-07 | Sous-classe de `sqlite3.Connection` | test indépendant | **PASS** | type exact exigé |
| C-08 | Référence FK inexistante | test indépendant | **PASS** | `ContractSQLiteError`, `foreign_key_check` vide |
| C-09 | Rollback après erreur SQL | tests | **PASS** | aucune ligne |
| C-10 | Rollback après divergence de relecture | test indépendant | **PASS** | `ContractPersistenceError`, aucune ligne |
| C-11 | Contrôles avant validation | test indépendant | **PASS** | connexion invalide + document invalide → `ContractConnectionError` |
| C-12 | Autres propriétés de connexion | inspection | **PARTIAL** | `journal_mode`, `busy_timeout`, `synchronous` ne sont pas revérifiés par le writer ; `open_connection` les applique |
| C-13 | Concurrence, crash, reprise | non exécuté | **NOT TESTED** | aucune garantie revendiquée |

### Audit D — erreurs et ordre

| ID | Contrôle | Méthode | Résultat | Remarque |
|---|---|---|---|---|
| D-01 | Ordre schéma → chronologie → version | tests + indépendant | **PASS** | période inversée + version `9.9.9` → `ContractChronologyError` |
| D-02 | Documents multi-erreurs | tests | **PASS** | `period` manquant + version manquante → `ContractSchemaError` pour `period` |
| D-03 | Classification des erreurs | inspection + tests | **PASS** | `spec`, `approval`, `connection`, `schema`, `chronology`, `version`, `business`, `validator`, `sql`, `persistence` |
| D-04 | Causes accessibles | tests | **PASS** | `ContractValidatorError → SchemaValidatorError → RuntimeError` ; `ContractApprovalError` cause registre |
| D-05 | Ordre approbation/transaction documenté | inspection | **PARTIAL** | la vérification finale est exécutée dans `BEGIN`, pas avant comme le décrit la liste |
| D-06 | Erreur masquée/reclassée | tests | **PASS** | version racine seule classée version ; version imbriquée classée schéma |
| D-07 | Erreurs SQL/persistance | tests | **PASS** | catégories correctes, rollback |
| D-08 | Erreurs de registre normalisées | tests | **PASS** | `from_approved("unknown")` → `ContractApprovalError` avec cause |
| D-09 | `ContractSchemaUnreadableError` | inspection | **NOT TESTED** | chemin de permission réelle non testé |
| D-10 | `ContractSchemaMismatchError` | inspection | **NOT TESTED** | pas de test direct dédié |
| D-11 | `contract_write_batch` | `grep` | **PASS (non implémenté)** | aucun symbole ; composition de groupe non fournie |
| D-12 | `INSERT` SQL direct | inspection | **PASS (limite documentée)** | contourne le writer ; non empêché |

### Audit E — migrations et manifeste

| ID | Contrôle | Méthode | Résultat | Remarque |
|---|---|---|---|---|
| E-01 | Format, périmètre, couverture explicites | tests | **PASS** | `format`, `scope`, `covered` |
| E-02 | Hashes des migrations | calcul + tests | **PASS** | 4/4 |
| E-03 | Migration modifiée détectée | copie temporaire + test | **PASS** | hash différent |
| E-04 | Empreinte du manifeste incorrecte détectée | copie temporaire + test | **PASS** | constante épinglée |
| E-05 | Modification conjointe migration + manifeste | copie temporaire | **PARTIAL** | si test et constante suivent, l'état cohérent passe ; limite intrinsèque |
| E-06 | Historique Git | `git ls-files` | **PARTIAL** | 0 fichier suivi ; pas de preuve d'historique |
| E-07 | Non-modification des migrations | mtimes + hashes | **PARTIAL** | mtimes antérieurs au candidat ; aucune baseline Git |
| E-08 | Avertissements historiques | inspection | **PASS** | rapports antérieurs conservés et marqués historiques |
| E-09 | Manifeste non appliqué comme migration | test runner | **PASS** | registre du runner sans `SHA256SUMS` |

### Audit F — reproductibilité

| ID | Contrôle | Résultat |
|---|---|---|
| F-01 | Suite complète | **PASS** : 717 passed |
| F-02 | Collecte | **PASS** : 717 collected |
| F-03 | `--runxfail` | **PASS** : 717 passed |
| F-04 | Tests P0 | **PASS** : 55 passed |
| F-05 | Contrats et parité SQL | **PASS** : 261 passed |
| F-06 | Writer + validateur + 0007 | **PASS** : 83 passed |
| F-07 | Manifeste | **PASS** : 11 passed |
| F-08 | Reproduction ciblée | **PASS** : 18 passed, 33 deselected |
| F-09 | Politique de connexion | **PASS** : 23 passed |
| F-10 | `git diff --check` | **PASS** : exit 0, CRLF seulement |
| F-11 | Suivi Git des migrations | **PASS (constat)** : 0 fichier |
| F-12 | Writer normal sans `jsonschema` | **PASS** : `python -S`, écriture valide |
| F-13 | Writer A1/A2 de production | **NOT TESTED** : aucun appel |

---

## 4. Validateur interne vs validateur de référence

### 4.1 Référence et méthode

`jsonschema==4.26.0` est disponible dans l'environnement de test et reste une
dépendance de test. Il a servi d'oracle sans être ajouté aux dépendances de
production. Le validateur système a été construit à partir des schémas
approuvés gelés ; le validateur de référence a été construit sur une copie
`thaw_json`.

Trois campagnes indépendantes ont été exécutées :

1. **186 cas construits** : documents valides minimaux/complets, champs
   obligatoires absents, propriétés supplémentaires, types incorrects,
   énumérations, bornes numériques, chaînes vides/longues, tableaux
   vides/dupliqués/invalides, dates et chronologies, versions absentes ou
   fausses, `null`, erreurs multiples.
2. **5 000 mutations déterministes** (`random.Random(20261027)`) de 1 à 4
   mutations par document sur les deux exemples, avec suppressions, ajouts,
   remplacements et valeurs limites.
3. **173 cas de mots-clés** sur les fonctionnalités supportées : types,
   `const`, `enum`, `pattern`, longueurs, bornes, `multipleOf`, `items`,
   `minItems`/`maxItems`, `uniqueItems`, `minProperties`/`maxProperties`,
   `required`, `additionalProperties`, `allOf`, `anyOf`, `oneOf`,
   `if/then/else`, `$ref`, schéma vide.

### 4.2 Résultats

| Campagne | Cas | Divergences |
|---|---:|---:|
| Contrats approuvés, cas construits | 186 | **0** |
| Mutations déterministes | 5 000 | **0** |
| Mots-clés supportés | 173 | **2** |
| **Total** | **5 359** | **2** |

Les deux divergences sont :

```text
multipleOf decimal : 0.3               système valide, référence invalide
multipleOf decimal : 0.30000000000000004 système valide, référence invalide
```

Le validateur système utilise une tolérance `math.isclose` pour `multipleOf` ;
`jsonschema` est plus strict sur ces flottants. Aucun schéma approuvé actuel
n'utilise `multipleOf` (`grep` sur `experiment` et `fee_schedule` : aucune
occurrence). La divergence n'affecte donc pas les documents actuels, mais elle
empêche de déclarer la parité complète du sous-ensemble supporté. Elle doit
être tranchée avant d'utiliser ce mot-clé dans un futur contrat.

Les 186 cas et les mutations ne révèlent aucune différence de validité sur les
schémas approuvés. Cela ne prouve pas une conformité JSON Schema complète : les
fonctionnalités non supportées sont refusées à la construction, et les cas
sémantiques très particuliers ne sont pas couverts.

### 4.3 Fonctionnalités supportées

Le socle couvre effectivement : `$ref` locaux, `$defs`, `type` (chaîne ou
liste), `properties`, `required`, `additionalProperties` booléen ou schéma,
`allOf`, `anyOf`, `oneOf`, `if`/`then`/`else`, `const`, `enum`, `pattern`,
`minLength`, `maxLength`, `minimum`, `maximum`, `exclusiveMinimum`,
`exclusiveMaximum`, `multipleOf`, `items`, `minItems`, `maxItems`,
`uniqueItems`, `minProperties`, `maxProperties`.

### 4.4 Fonctionnalités non supportées

Sont refusées à la construction : `patternProperties`, `format`,
`propertyNames`, `dependentRequired`, `dependentSchemas`,
`unevaluatedProperties`, `unevaluatedItems`, `prefixItems`, `contains`, `not`,
`minContains`, `maxContains`, `additionalItems`, les schémas booléens,
`items` sous forme booléenne, les listes `allOf`/`anyOf`/`oneOf` vides, les
`enum` vides, les références non locales, `$anchor`, les références dynamiques
et les extensions inconnues. Ce choix est fail-closed : un schéma futur utilisant
ces mots-clés sera refusé comme contrat inutilisable, pas interprété
partiellement.

### 4.5 Règles métier séparées

- Chronologie `x-polymarket-chronological-order` via `chronology_errors`.
- `completed_at` cohérent avec `status`.
- Clé `period.end_time` présente pour `paper_live`, y compris `null`.
- Approbation : nom, version, SHA-256, fichier, gel.
- Contraintes SQL, FK, triggers et triggers append-only.
- Mapping document → colonnes et relecture.
- Le validateur système ne remplace pas ces règles ; il ne les ignore pas non
  plus : elles sont appliquées après le schéma par `contract_issues`/writer.

### 4.6 Limites de la comparaison

- `jsonschema` est utilisé seulement comme oracle de test.
- Il n'y a pas de suite de conformité JSON Schema officielle externe.
- Les regex sont évaluées par `re` Python, comme `jsonschema`, pas par un moteur
  ECMA-262 indépendant.
- `multipleOf` décimal diverge de l'oracle.
- `$ref` vers non-schéma et `$ref` cyclique ne sont pas rejetés à la
  construction ; ils échouent à la validation (fail-closed) et n'écrivent rien.
- Aucune preuve de parité exhaustive pour les schémas futurs.

---

## 5. Tests exécutés et résultats exacts

```powershell
.\.venv\Scripts\python.exe -m pytest tests -q -rxX
# 717 passed in 25.88s

.\.venv\Scripts\python.exe -m pytest tests --collect-only -q
# 717 tests collected in 0.16s

.\.venv\Scripts\python.exe -m pytest tests -q --runxfail
# 717 passed in 27.97s

.\.venv\Scripts\python.exe -m pytest tests\integration\test_p0_candidates.py -q
# 55 passed in 6.18s

.\.venv\Scripts\python.exe -m pytest `
  tests\unit\test_contracts_negative.py `
  tests\unit\test_contracts_schema_validity.py `
  tests\integration\test_contract_sql_parity.py -q
# 261 passed in 3.13s

.\.venv\Scripts\python.exe -m pytest `
  tests\integration\test_0007_contract_sql_alignment.py `
  tests\unit\test_contract_validation.py `
  tests\integration\test_contract_writer.py `
  tests\unit\test_system_schema_validator.py -q
# 83 passed in 8.07s

.\.venv\Scripts\python.exe -m pytest tests\integration\test_migration_manifest.py -q
# 11 passed in 0.15s

.\.venv\Scripts\python.exe -m pytest tests\integration\test_contract_writer.py -q `
  -k "mutation or registry or forged or row_factory or ignore_check or normal_writer or custom_schema or permissive or from_approved"
# 18 passed, 33 deselected in 1.47s

.\.venv\Scripts\python.exe -m pytest tests\integration\test_connection_policy.py -q
# 23 passed in 0.42s

git diff --check
# exit 0 ; avertissements CRLF uniquement

git ls-files schemas/migrations
# aucun fichier
```

### 5.1 Contrôles indépendants

- Script writer/approbation temporaire :
  `52 PASS, 0 FAIL, 52 checks`.
- Script de parité contrats : `186 cas, 0 divergence`.
- Script de fuzz : `5 000 mutations, 0 divergence`.
- Script de mots-clés : `173 cas, 2 divergences` (`multipleOf` décimal).
- Manifeste sur copie temporaire : migration modifiée rejetée ; manifeste
  modifié rejeté.
- `python -S` avec `src/` : import du writer réussi, `jsonschema` absent,
  écriture valide d'une expérience acceptée.

### 5.2 Distinction preuves

- **Exécuté :** toutes les commandes ci-dessus, scripts indépendants, copies
  temporaires, test sans site-packages.
- **Inspection :** présence de la vérification finale d'approbation, ordre
  exact des appels, absence de `contract_write_batch`, exports.
- **Documentaire :** options A/B, limites TOCTOU/concurrence, manifeste.
- **Non testé :** concurrence, crash, reprise, permission réelle, packaging,
  A1/A2 réel.

---

## 6. Anomalies reproduites

### A5-C2-01 — `multipleOf` décimal diverge de l'oracle — **Faible**

**Scénario :** schéma `{"type": "number", "multipleOf": 0.1}`, valeurs `0.3`
et `0.30000000000000004`.  
**Attendu :** même décision que `jsonschema`.  
**Observé :** système valide, `jsonschema` invalide.  
**Méthode :** matrice 173 cas, comparaison de validité.  
**Preuve :** 2 divergences sur 173.  
**Gravité :** faible pour les contrats actuels ; aucun schéma approuvé
n'utilise `multipleOf`. Moyenne pour l'option B générale.  
**Action :** soit retirer `multipleOf` du sous-ensemble supporté (fail-closed),
soit définir et tester la sémantique exacte avant tout schéma futur.

### A5-C2-02 — Cible `$ref` non-schéma / cycle accepté à la construction — **Faible**

**Scénario :** `{"$ref": "#/examples/0", "examples": ["x"]}` ou
`{"$ref": "#/$defs/a", "$defs": {"a": {"$ref": "#/$defs/a"}}}`.  
**Attendu :** schéma mal formé refusé à la construction, ou au minimum erreur
explicite de schéma.  
**Observé :** construction acceptée ; `iter_errors` lève
`UnsupportedSchemaError` (`la référence ne pointe pas un schéma` /
`profondeur de schéma dépassée`). Aucun document n'est écrit : le writer
l'enveloppe en `ContractValidatorError`.  
**Méthode :** script indépendant de schémas mal formés.  
**Gravité :** faible ; les schémas approuvés actuels n'utilisent pas ces
formes.  
**Action :** vérifier à la construction que chaque cible `$ref` est un
schéma et détecter les cycles ; ajouter des tests.

### A5-C2-03 — Ordre documenté approbation/transaction inexact — **Faible**

**Scénario :** lecture de `WRITER_INTEGRATION.md:119-137` et du code.  
**Attendu documenté :** approbation finale (6) avant `BEGIN` (7).  
**Observé :** `_verify_approved_contract` est appelé dans le bloc
`with transaction(connection)`, après `BEGIN`, avant l'insertion.  
**Méthode :** inspection + test par patch de la vérification finale.  
**Gravité :** faible ; aucune écriture n'est effectuée et le rollback est
correct.  
**Action :** soit déplacer la vérification avant `BEGIN`, soit corriger la
documentation de l'ordre ; conserver le test « aucune ligne ».

### A5-C2-04 — Validation de permission illisible non testée — **Faible/NOT TESTED**

`ContractSchemaUnreadableError` est défini et le chemin `OSError` est présent,
mais aucun test réel de permission n'a été exécuté.  
**Action :** test de fichier non lisible ou simulation d'`OSError` ; vérifier
la normalisation en `ContractApprovalError`.

### A5-C2-05 — Baseline du manifeste auto-référentielle et migrations non suivies — **Info/Partiel**

**Scénario :** modification d'une migration, du manifeste, du test et de sa
constante.  
**Attendu :** le manifeste détecte une modification non répercutée ; il ne
prouve pas l'histoire.  
**Observé :** le test rejette une migration modifiée seule et un manifeste
modifié seul ; une modification coordonnée peut produire un état cohérent.  
**Méthode :** copies temporaires + tests.  
**Gravité :** information/limite de preuve.  
**Action :** commit Git de référence des migrations et du manifeste ; ne pas
présenter la baseline comme une signature externe.

### A5-C2-06 — Aucun writer A1/A2 de production — **Info/Partiel**

Aucun appel à `write_experiment`/`write_fee_schedule` hors du module, des
exports et des tests n'a été trouvé. L'intégration réelle reste à faire.  
**Action :** brancher A1/A2 uniquement après décision option A/B et conditions
ci-dessous.

### A5-C2-07 — Validateur système non approuvé pour la production — **Bloquant production**

A0 le classe candidat Option B, pas décision approuvée. Le writer normal
fonctionne sans `jsonschema`, mais l'usage en production n'est pas autorisé
par ce rapport.  
**Action :** décision propriétaire A/B ; aucune approbation automatique.

### A5-C2-08 — Code arbitraire dans le processus — **Limite assumée**

Les objets privés, le token `_APPROVED_SPEC_TOKEN`, `_APPROVED_CONTRACTS`,
`registry.ROOT`, les globals et les fonctions peuvent être remplacés par du
code Python arbitraire. Le writer n'est pas une frontière de sécurité de
processus.  
**Action :** aucune revendication d'isolation ; documenter et limiter l'accès
au code de production.

### A5-C2-09 — Concurrence, crash et reprise non testés — **Info/NOT TESTED**

Aucun test de course, verrou, timeout, crash après commit ou reprise.  
**Action :** ne pas revendiquer ces garanties ; tests dédiés si nécessaire.

---

## 7. Risques résiduels

1. **Sous-ensemble JSON Schema incomplet.** Le validateur système n'est pas
   une implémentation complète ; il refuse les mots-clés non supportés, mais
   une future évolution de contrat doit être testée.
2. **`multipleOf` décimal.** Divergence réelle avec l'oracle, non utilisée
   aujourd'hui.
3. **Références malformées/cycliques.** Acceptées à la construction, refusées
   à la validation ; fail-closed à l'écriture, mais le diagnostic est tardif.
4. **TOCTOU.** La vérification finale relit le fichier avant insertion, mais un
   changement entre cette lecture et l'insertion reste possible.
5. **Concurrence/crash.** Aucune preuve ; aucune garantie revendiquée.
6. **Code arbitraire.** Aucune isolation de processus ; les contournements par
   monkeypatch/privé restent possibles.
7. **Test path.** `contract_writer_testing` est un module séparé, mais un
   import délibéré ou un code A1/A2 fautif peut l'utiliser ; ce n'est pas une
   frontière de sécurité.
8. **Aucun writer A1/A2 réel.** L'intégration n'est pas faite.
9. **Validation de production non tranchée.** Option B candidate, option A
   non ajoutée.
10. **Migrations non suivies par Git.** Le manifeste prouve l'identité relative,
    pas l'historique.
11. **Packaging.** `registry.ROOT` dépend de la présence de `contracts/` à côté
    de `src/` ; non testé hors dépôt.
12. **`INSERT` direct.** Contourne le writer ; limite documentée.
13. **Restrictions de connexion.** Les wrappers/sous-classes légitimes sont
    refusés ; choix volontaire à revoir si besoin.

---

## 8. Blocages de production

### Blocages durs

1. **Décision propriétaire Option A/B.** Sans adoption explicite de
   `SystemSchemaValidator` ou de `jsonschema` en production, l'intégration de
   production reste bloquée.
2. **Parité du sous-ensemble.** `multipleOf` doit être corrigé ou retiré ;
   les références malformées/cycliques doivent être refusées à la construction
   ou documentées avec un test de non-écriture.
3. **Concurrence/crash/reprise.** Aucun test ; ne pas utiliser en production
   avec une exigence de résilience.
4. **Atomicité multi-documents.** Aucune composition de groupe ; deux appels
   indépendants ne sont pas atomiques.
5. **Migrations et manifeste.** Baseline non suivie par Git ; pas de preuve
   d'historique.
6. **A1/A2.** Aucun branchement réel ; les autres contrats ne sont pas couverts.

### Conditions d'une intégration expérimentale locale

- Utiliser uniquement l'API normale
  `write_experiment(connection, document)` / `write_fee_schedule(connection,
  document)`.
- Utiliser `open_connection` ; ne pas passer de connexion brute, de
  sous-classe, de `row_factory` personnalisé ou de pragma `ignore_check`.
- Ne jamais importer `contract_writer_testing` dans A1/A2.
- Ne pas utiliser `INSERT` direct pour `experiments`/`fee_schedules`.
- Ne pas utiliser `multipleOf` dans un schéma futur avant décision.
- Ne pas revendiquer d'atomicité de groupe, de concurrence, de crash ou de
  reprise.
- Conserver les contrats `experiment`/`fee_schedule` approuvés et leur hash.
- Faire trancher l'option A/B par le propriétaire avant tout passage en
  production.

---

## 9. Comparaison avec les deux audits A5 précédents

| Point | Audit A5 n°1 (653) | Audit A5 n°2 (672) | Candidat 2 (717) |
|---|---|---|---|
| Suite | 653/653/0 | 672/672/0 | **717/717/0** |
| FK OFF | contourné | refusé | **refusé** |
| RT OFF | non couvert | refusé | **refusé** |
| `ignore_check_constraints` | non couvert | contourné | **refusé** |
| `row_factory` | non couvert | falsifiable | **refusé** |
| Sous-classe `Connection` | non couvert | non couvert | **refusée** |
| Transaction active | non documentée | refusée, préservée | **refusée, préservée** |
| Schéma/validateur fournis | acceptés | validateur permissif accepté | **API normale sans schéma/validateur** |
| Mutation après approbation | non couverte | contournement accepté | **mutation ordinaire bloquée** |
| Registre public mutable | non couvert | contournement accepté | **mapping proxy + registre privé** |
| `allow_test_specs` | contournement | contournement | **supprimé ; parcours de test séparé** |
| Version `9.9.9` normale | refusée avec schéma officiel | contournable | **refusée** |
| Version absente | catégorie incorrecte | corrigée | **version** |
| Ordre validation | version > chronologie | version > chronologie | **schéma → chronologie → version** |
| Erreurs de registre | brute | brute | **normalisées avec cause** |
| Validateur de production | `jsonschema` test | `jsonschema` test | **`SystemSchemaValidator` interne + oracle test** |
| Parité validateur | non mesurée | non mesurée | **0/186, 0/5000, 2/173** |
| Manifeste | absent | baseline auto-référentielle | **format/périmètre/hash/constante, 11 tests** |
| Concurrence/crash | non testé | non testé | **non testé** |
| Writer A1/A2 | absent | absent | **absent** |
| Recommandation | A/PARTIEL | A/PARTIEL | **B sous conditions** |

Le candidat 2 ferme les contournements ordinaires précédents. Il introduit un
validateur interne réel, mais ce dernier reste un sous-ensemble et n'a pas de
validation de conformité externe complète.

---

## 10. Recommandation finale

**B — intégration expérimentale locale possible sous conditions, sans gel des
contrats.**

Le writer normal et l'approbation ont passé les contrôles indépendants :
aucun schéma/validateur fourni, registre public en lecture seule, gel profond,
rechargement et revérification à chaque écriture, test path séparé, connexion
et rollback contrôlés. Le validateur système est suffisamment proche de
`jsonschema` sur les schémas approuvés actuels pour un usage expérimental
local, mais pas pour une approbation de production générale.

Conditions explicites :

1. Le propriétaire tranche l'option A (`jsonschema` de production) ou l'option
   B (`SystemSchemaValidator`). Sans décision, pas d'intégration A1/A2.
2. Pour l'option B, limiter l'usage aux contrats `experiment`/`fee_schedule`
   approuvés actuels ; interdire `multipleOf` jusqu'à correction ou retrait du
   sous-ensemble supporté.
3. Refuser à la construction, ou tester et documenter, les `$ref` vers
   non-schéma et les cycles.
4. Utiliser uniquement l'API normale et `open_connection` ; aucun test module,
   aucune spec privée, aucun `INSERT` direct, aucun `row_factory`/sous-classe.
5. Ne pas promettre l'atomicité de groupe, la concurrence, le crash ou la
   reprise.
6. Committer migrations + `SHA256SUMS` dans un commit Git de référence avant
   toute revendication de traçabilité.
7. Ajouter les tests manquants : `ContractSchemaUnreadableError`, vérification
   finale d'approbation (déjà testée ici par patch, mais pas la course TOCTOU),
   `multipleOf`, refs malformées/cycliques.
8. Aucun gel, aucune approbation définitive des contrats, aucune production.

Si l'une des conditions 1, 2 ou 5 ne peut pas être tenue, la recommandation
revient à **A — corrections supplémentaires avant intégration expérimentale**.
La décision de gel reste réservée au propriétaire du projet.
