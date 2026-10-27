# Rapport A5 — audit indépendant du parcours commun d’écriture

> **AUDIT HISTORIQUE.** Ce rapport a déclenché les corrections D-053. Ses
> chiffres 653/653/0 et son verdict PARTIEL décrivent l'état avant durcissement.
> L'état courant est **672/672/0**, voir
> `tests/REPORT_A0_WRITER_HARDENING.md`.

**Date :** 2026-10-27  
**Auditeur :** A5 — validation et benchmark  
**Objet :** audit indépendant de `ContractSpec`, `write_experiment` et
`write_fee_schedule`, en réponse au rapport
`tests/REPORT_A0_WRITER_VALIDATION_INTEGRATION.md`.  
**Périmètre :** `src/polymarket_lab/storage/contract_writer.py`,
`src/polymarket_lab/storage/connection.py`,
`src/polymarket_lab/validation/contracts.py`,
`tests/integration/test_contract_writer.py`, `WRITER_INTEGRATION.md`, contrats
`experiment`/`fee_schedule`, migrations `0005`/`0006`/`0007`.  
**Statut :** audit en lecture seule. Aucun code, contrat, test, migration ou
document existant modifié. Aucun commit. Aucun gel prononcé. Aucune base réelle
touchée, aucune collecte, aucune simulation, aucun accès réseau.

## 1. Verdict global — **PARTIEL**

Le parcours nominal est correctement ordonné et les 653 tests annoncés sont
reproductibles. Les refus de validation testés n’écrivent aucune ligne, les
erreurs SQL et de relecture annulent bien la transaction, et la version
persistée est explicite.

Le verdict reste **PARTIEL**, et non PASS, pour trois raisons :

1. **Le writer n’impose pas les pragmas de la connexion.** Avec une connexion
   SQLite brute où `foreign_keys=OFF`, il accepte et persiste des références
   inexistantes ; `PRAGMA foreign_key_check` signale ensuite des violations.
   C’est un risque d’intégrité élevé pour A1/A2 si la connexion n’est pas
   exactement celle d’`open_connection`.
2. **`ContractSpec` ne garantit pas à lui seul la version “officielle”.** Il
   accepte toute version épinglée par le schéma injecté. Un schéma copié avec
   `schema_version.const = "9.9.9"` et son validateur associé permet
   effectivement d’écrire une ligne `9.9.9`. Avec les schémas officiels, les
   versions `1.1.0` et `9.9.9` sont bien refusées, mais l’impossibilité n’est
   pas intrinsèque au writer.
3. **Deux écarts documentaires/erreurs sont confirmés :** une version absente
   est classée `ContractSchemaError`, alors que la documentation annonce
   `ContractVersionError` ; une exception interne du validateur remonte brute,
   non catégorisée.

Aucun de ces points ne provoque de perte de données dans les scénarios testés.
Ils interdisent toutefois de présenter le writer comme une garantie complète
pour A1/A2 sans conditions d’intégration explicites.

| Axe audité | Verdict |
|---|---|
| Ordre schéma → chronologie → version → métier → transaction → relecture | **PASS** |
| Refus avant écriture, absence de ligne | **PASS** |
| `ContractSpec` et version persistée | **PARTIEL** |
| `write_experiment` / `write_fee_schedule` nominal | **PASS** |
| Doublons, contraintes SQL, rollback, relecture | **PASS** avec réserves de couverture |
| Transactions et composition | **PARTIEL** |
| Concurrence et reprise après crash | **NON TESTÉ** |
| Dépendance validateur en production | **PARTIEL / bloquant pour A1/A2** |
| Limites A1/A2 documentées | **PASS** |
| Migrations `0005`/`0006`/`0007` non modifiées | **NON VÉRIFIABLE formellement** (fichiers non suivis par Git) |

## 2. Méthode et indépendance

- Lecture intégrale du writer, de `connection.py`, du validateur partagé, des
  14 tests writer, de `WRITER_INTEGRATION.md`, de D-052 et des rapports A0
  concernés.
- Exécution des commandes demandées sans installation ni réseau.
- Écriture d’un script d’audit séparé dans `%TEMP%`, non versionné, avec une
  base SQLite en mémoire reconstruite par les migrations officielles et les
  fixtures de test. Les assertions du script sont indépendantes de
  `test_contract_writer.py`, même si les fixtures de construction de base et
  les schémas officiels sont réutilisés.
- **80 contrôles principaux : 79 PASS, 1 FAIL.** Le seul FAIL est le classement
  de la version absente.
- **6 contrôles complémentaires de mapping : 6 conformes** (JSON canonique du
  document, des hypothèses, des limites de risque, `random_seed`,
  `presentation_conversion_json = NULL`, `effective_to = NULL`).
- **1 contrôle complémentaire d’injection de schéma : exposition confirmée**
  (version `9.9.9` acceptée avec un schéma non officiel épinglé sur `9.9.9`).
- Deux contrôles métier complémentaires : `planned` avec `completed_at`
  non nul et `completed` sans `completed_at` sont refusés sans ligne ;
  `running` avec `completed_at = NULL` est accepté.

## 3. Commandes exécutées et résultats

```powershell
.\.venv\Scripts\python.exe -m pytest tests -q -rxX
# 653 passed

.\.venv\Scripts\python.exe -m pytest tests --collect-only -q
# 653 tests collected

.\.venv\Scripts\python.exe -m pytest tests -q --runxfail
# 653 passed

.\.venv\Scripts\python.exe -m pytest tests\integration\test_p0_candidates.py -q
# 55 passed

.\.venv\Scripts\python.exe -m pytest tests\unit\test_contracts_negative.py `
  tests\unit\test_contracts_schema_validity.py `
  tests\integration\test_contract_sql_parity.py -q
# 261 passed

.\.venv\Scripts\python.exe -m pytest `
  tests\integration\test_0007_contract_sql_alignment.py `
  tests\unit\test_contract_validation.py `
  tests\integration\test_contract_writer.py -q
# 30 passed

git diff --check
# exit 0 ; avertissements CRLF uniquement
```

**Limite de preuve :** `git diff --check` ne contrôle que les fichiers suivis.
Le writer, les tests writer et les migrations `0005`/`0006`/`0007` sont non
suivis dans l’état Git observé. Ce contrôle ne prouve donc pas leur contenu ni
leur historique.

## 4. Ordre de validation réellement appliqué

L’ordre effectif est conforme à l’ordre annoncé :

| Étape | Implémentation | Erreur | Preuve |
|---|---|---|---|
| 1. JSON Schema | `spec.validator.iter_errors` via `_schema_issues` | `ContractSchemaError` | `contract_writer.py:102-125` |
| 2. Chronologie | `chronology_errors(document, schema)` | `ContractChronologyError` | `contract_writer.py:126-131` |
| 3. Version | erreurs de chemin `schema_version`, puis comparaison à `spec.version` | `ContractVersionError` | `contract_writer.py:133-145` |
| 4. Métier | `completed_at`/statut, clé `paper_live.end_time` | `ContractBusinessError` | `contract_writer.py:147-162` |
| 5. Insertion | `with transaction(connection)` et `INSERT` | `ContractSQLiteError` | `contract_writer.py:323-338` |
| 6. Relecture | `_verify_row`, comparaison de toutes les colonnes écrites | `ContractPersistenceError` | `contract_writer.py:271-297` |

Aucune transaction n’est ouverte avant l’étape 5. Les tests et les 80 contrôles
indépendants confirment l’absence de ligne après refus aux étapes 1 à 4.

### 4.1 Écart avec le rapport A0

Le rapport A0 affirme que le writer « réutilise
`validate_contract`/`chronology_errors` ». Le code importe seulement
`chronology_errors` ; il **n’appelle pas `validate_contract`** et réimplémente
la séquence schéma/chronologie/version (`contract_writer.py:29` et
`118-162`). L’ordre actuel est équivalent pour les règles présentes, mais une
évolution future de `validate_contract` ne sera pas automatiquement héritée.
C’est un risque de dérive, pas un défaut fonctionnel démontré aujourd’hui.

### 4.2 Version absente — FAIL confirmé

Le schéma officiel déclare `schema_version` comme propriété requise. Une clé
absente produit une erreur de type « required » dont le chemin est la racine,
pas `schema_version`. `_schema_issues` la classe donc en
`ContractSchemaError` (`contract_writer.py:111-125`).

La documentation de `WRITER_INTEGRATION.md:90-97` et le rapport A0 annoncent
`ContractVersionError` pour une version absente. Le contrôle indépendant
`version absente: catégorie version` échoue :

```text
FAIL version absente: catégorie version :: catégorie=ContractSchemaError
```

La version absente est bien refusée et aucune ligne n’est créée ; seul le
classement de l’erreur diverge. C’est un défaut de contrat d’erreur, de
sévérité faible, mais réel.

### 4.3 `paper_live` sans clé `end_time`

Avec le schéma officiel, la clé absente est refusée à l’étape 1 comme
`ContractSchemaError`, avant le contrôle métier de l’étape 4. Le test
`test_writer_rejects_paper_live_without_end_time_key`
(`test_contract_writer.py:148-160`) attend d’ailleurs `ContractSchemaError`.
Le contrôle métier du writer est donc une défense en profondeur, pas le
mécanisme principal pour ce cas. La documentation doit éviter de laisser croire
que ce cas produit nécessairement `ContractBusinessError`.

## 5. `ContractSpec` — version, schéma et validateur

### 5.1 Extraction de version

`ContractSpec.__post_init__` lit
`properties.schema_version.const` et exige une chaîne non vide
(`contract_writer.py:88-95`). Le writer écrit cette même version explicitement
dans `schema_version`, sans dépendre du `DEFAULT 1.2.0` SQL
(`contract_writer.py:171-232`). Les écritures valides observées persistent
`1.2.0`, et la relecture compare cette colonne comme les autres.

### 5.2 Cas de schéma absents ou mal formés

| Cas | Comportement observé | Appréciation |
|---|---|---|
| Schéma sans `properties` | `ValueError` explicite | Correct |
| `properties` non mapping | `AttributeError` (`NoneType.get`) | Non typé, à corriger |
| `properties.schema_version` non mapping | `AttributeError` (`str.get`) | Non typé, à corriger |
| `const` non chaîne ou vide | `ValueError` explicite | Correct |
| Schéma avec version épinglée par `$ref`/`allOf` uniquement | Rejeté, car aucun `const` direct | Limitation de conception |
| `const` et `enum`/`default` divergents | Seul `const` est lu | Ambiguïté non détectée ; le validateur peut diverger |
| `schema`/`validator` construits sur deux schémas différents | Aucun contrôle croisé | Responsabilité de l’appelant |

Les deux `AttributeError` ne sont pas des erreurs de domaine et ne sont pas
documentées. Elles n’entraînent aucune écriture, mais le contrat d’erreur de
construction n’est pas stable.

### 5.3 Versions `1.1.0`, `9.9.9` et injection arbitraire

Avec les schémas officiels :

- document `1.1.0` → refus `ContractVersionError`, aucune ligne ;
- document `9.9.9` → refus `ContractVersionError`, aucune ligne ;
- document `1.2.0` → écriture et persistance de `1.2.0`.

Mais le contrôle complémentaire suivant a été exécuté :

```python
schema = deepcopy(experiment_schema)
schema["properties"]["schema_version"]["const"] = "9.9.9"
spec = ContractSpec("experiment", schema, Draft202012Validator(schema))
document["schema_version"] = "9.9.9"
write_experiment(connection, document, spec)
```

Résultat observé : **accepté**, avec `<schema_version> = 9.9.9` dans
`experiments`. La colonne SQL est un `TEXT NOT NULL DEFAULT '1.2.0'` sans
`CHECK` limitant les valeurs (`0007_contract_sql_alignment.sql:51,114`).

Conclusion : l’impossibilité d’écrire une version arbitraire **n’est pas
garantie par le writer**. Elle dépend de l’utilisation des schémas officiels
immuables. Si A1/A2 charge un schéma modifié, un schéma ancien ou un schéma
injecté, le writer suivra sa version. Une liste blanche de versions supportées
ou une vérification d’identité/hash du schéma serait nécessaire pour une
garantie intrinsèque.

## 6. `write_experiment` et `write_fee_schedule`

### 6.1 Garanties vérifiées

| Garantie | Résultat |
|---|---|
| Écriture valide `experiment` et `fee_schedule` | PASS ; transaction refermée |
| Version explicitement écrite et relue | PASS (`1.2.0`) |
| Période inversée, expérience et barème | PASS ; aucune ligne |
| Bornes égales, expérience et barème | PASS ; aucune ligne |
| Erreur de schéma | PASS ; aucune ligne |
| Versions incompatibles avec schéma officiel | PASS ; aucune ligne |
| `paper_live` sans clé `end_time` | PASS ; refus, aucune ligne |
| `paper_live` avec `end_time: null` | PASS ; ligne avec `NULL` et `1.2.0` |
| `completed_at` incohérent | PASS ; aucune ligne |
| Doublon barème | PASS ; `ContractSQLiteError`, lignes existantes conservées |
| Doublon expérience | PASS en contrôle indépendant ; non couvert par les 14 tests |
| FK absente avec `foreign_keys=ON` | PASS ; erreur SQL, rollback |
| CHECK SQL | PASS ; erreur SQL, rollback |
| Trigger de relecture sur barème | PASS ; `ContractPersistenceError`, rollback |
| Trigger de relecture sur expérience | PASS en contrôle indépendant ; non couvert par les 14 tests |

Les doublons ne modifient pas les lignes existantes : les counts avant/après
sont identiques. Le writer ne fait que des `INSERT`, sans `UPDATE` ni
`DELETE` ; il ne réécrit donc pas les lignes historiques.

### 6.2 Relecture persistée

`_verify_row` sélectionne toutes les colonnes du mapping et compare
`(colonne, valeur attendue)` à `(colonne, valeur relue)`
(`contract_writer.py:271-297`). Une valeur différente ou une ligne absente
produit `ContractPersistenceError`, puis le contexte `transaction` annule
l’insertion. Le test officiel ne couvre que `fee_schedule` ; le contrôle
indépendant couvre aussi `experiment`.

La relecture ne vérifie pas :

- les colonnes non écrites par le writer et remplies par un défaut SQL ;
- les effets d’un trigger sur des colonnes non écrites ;
- `PRAGMA foreign_key_check` ;
- `PRAGMA integrity_check` ;
- l’absence d’autres lignes modifiées par un trigger.

Elle est donc suffisante pour « la ligne écrite correspond aux valeurs
soumises », pas pour « la base entière est cohérente ».

### 6.3 Exceptions du validateur et erreurs non typées

Un validateur qui lève `RuntimeError` propage l’exception brute :

```text
RuntimeError: validator boom
```

Aucune ligne n’est créée et la transaction reste refermée, mais l’appelant ne
reçoit ni `ContractSchemaError` ni une erreur catégorisée. Le contrat d’erreur
public n’est donc pas garanti face à un validateur défaillant. Le writer ne
protège pas non plus contre un document non `Mapping` : l’accès `.get` peut
lever une exception brute avant la catégorisation. Ces cas sont de sévérité
faible, mais doivent être traités par A1/A2 ou par une évolution du writer.

## 7. Transactions, concurrence et atomicité

### 7.1 Ce qui est garanti par le code

`transaction` (`connection.py:208-229`) :

- refuse une connexion déjà en transaction avec
  `ConnectionConfigurationError` ;
- ouvre `BEGIN IMMEDIATE` par défaut ;
- annule sur toute exception, y compris `BaseException` ;
- annule aussi si le `commit()` échoue.

Le writer convertit `ConnectionConfigurationError` en `ContractSQLiteError`
(`contract_writer.py:333-338`). Avec une transaction appelante active, le
writer est donc refusé avant toute insertion ; la transaction et les opérations
de l’appelant ne sont **pas** annulées. Le contrôle indépendant confirme que le
marqueur de l’appelant et son état `in_transaction` sont conservés.

Ce comportement est sûr, mais il n’est pas documenté dans
`WRITER_INTEGRATION.md`. Il n’existe pas de composition par savepoint : A1/A2
doit appeler le writer hors de toute transaction, ou étendre explicitement
l’interface.

### 7.2 Absence d’atomicité multi-documents

Chaque appel de writer ouvre et valide sa propre transaction. Le contrôle
indépendant a écrit un barème valide, puis tenté une expérience invalide
(FK absente) : le barème est resté commité et l’expérience absente. Aucune
atomicité entre plusieurs documents n’est garantie.

Si A1/A2 doit écrire un barème et une expérience ensemble, il faut une
transaction de composition ou une procédure de compensation explicite.

### 7.3 Concurrence, crash et reprise

Aucun test de concurrence multi-connexions, de verrou `BEGIN IMMEDIATE`, de
timeout, de crash après commit ou de reprise après crash n’a été exécuté. Les
garanties suivantes sont donc des garanties de code, pas des garanties
mesurées :

- une erreur SQL ou de relecture annule la transaction ;
- un commit réussi est atomique au sens SQLite ;
- un crash après commit peut laisser la ligne écrite alors que l’appelant n’a
  pas reçu son identifiant ; un nouvel essai produira probablement une erreur
  de doublon. Aucune idempotence n’est fournie.

Ces points ne doivent pas être présentés comme testés.

### 7.4 Point critique : la connexion n’est pas contrôlée

`write_experiment` et `write_fee_schedule` acceptent n’importe quel
`sqlite3.Connection` (`contract_writer.py:342-380`) et ne vérifient pas :

- `PRAGMA foreign_keys` ;
- `PRAGMA recursive_triggers` ;
- `busy_timeout` ;
- `isolation_level` ;
- `journal_mode`.

Le contrôle indépendant a ouvert une base valide avec
`PRAGMA foreign_keys=OFF`, puis écrit une expérience dont
`strategy.strategy_id` et `data.manifest_id` n’existent pas. Résultat :
**écriture acceptée**, puis `PRAGMA foreign_key_check` a retourné des
violations persistées.

`connection.py` documente pourtant que `open_connection` impose et vérifie ces
pragmas (`connection.py:3-10, 173-204`). La garantie dépend donc entièrement de
la discipline de l’appelant. Pour un writer présenté comme parcours commun,
c’est un risque d’intégrité **élevé**.

## 8. Edge cases — synthèse

| Cas | Résultat |
|---|---|
| Période inversée `experiment` / `fee_schedule` | Refus, aucune ligne |
| Bornes égales `experiment` / `fee_schedule` | Refus, aucune ligne |
| Version `1.1.0` avec schéma officiel | Refus, aucune ligne |
| Version `9.9.9` avec schéma officiel | Refus, aucune ligne |
| Version `9.9.9` avec schéma injecté épinglé `9.9.9` | **Acceptée et persistée** |
| `paper_live` sans clé `end_time` | Refus `ContractSchemaError`, aucune ligne |
| `paper_live` avec `end_time: null` | Accepté, `NULL` persisté |
| `completed` sans `completed_at` | Refus métier, aucune ligne |
| `planned` avec `completed_at` non nul | Refus métier, aucune ligne |
| `running` avec `completed_at = NULL` | Accepté |
| Doublon `fee_schedule` | `ContractSQLiteError`, lignes existantes intactes |
| Doublon `experiment` | `ContractSQLiteError`, lignes existantes intactes |
| FK invalide avec FK ON | `ContractSQLiteError`, rollback |
| FK invalide avec FK OFF | **Ligne acceptée, violations persistées** |
| CHECK SQL invalide | `ContractSQLiteError`, rollback |
| Relecture altérée par trigger | `ContractPersistenceError`, rollback |
| Transaction appelante active | Refus, transaction appelante préservée |
| Deux writes successifs dont le second échoue | Premier commit conservé |
| Validateur qui lève | Exception brute, aucune ligne |
| `ContractSpec` sans `properties` | `ValueError` |
| `ContractSpec` avec `properties` mal formé | `AttributeError` |
| Schéma sans version épinglée | `ValueError` |
| Version absente du document | Refus `ContractSchemaError` (documentation : version) |

## 9. Dépendance et intégration A1/A2

### 9.1 Validateur

Le writer n’importe pas `jsonschema` : `grep` sur `src/` ne trouve aucun import.
`jsonschema==4.26.0` est déclaré uniquement dans
`tests/requirements-test.txt` et commenté comme dépendance de test (D-018).
`requirements.txt` ne le contient pas.

Conséquence : le module s’importe sans `jsonschema`, mais **un writer de
production ne peut pas valider sans fournir une implémentation de
`SchemaValidator`**. Il manque donc, avant A1/A2 :

- soit une décision approuvant `jsonschema` comme dépendance de production,
  avec version épinglée ;
- soit une autre implémentation compatible `iter_errors` ;
- dans les deux cas, une fabrique qui construit schéma et validateur à partir
  de la même source officielle.

Le writer ne vérifie pas que le validateur injecté correspond au `schema`
passé dans `ContractSpec`. Un appelant peut fournir un validateur plus
permissif ou construit sur un autre schéma ; la version est alors comparée au
`const` du schéma déclaré, mais la validation de forme peut ne pas être celle
du contrat attendu.

### 9.2 Conditions à remplir avant branchement A1/A2

1. **Connexion contrôlée :** n’accepter que les connexions issues
   d’`open_connection`, ou vérifier `foreign_keys`, `recursive_triggers` et
   `isolation_level` dans le writer. À défaut, exécuter
   `PRAGMA foreign_key_check` après insertion et refuser la ligne en cas de
   violation.
2. **Schémas officiels :** charger les fichiers de `contracts/` sans
   transformation, construire le validateur avec le même objet, et empêcher
   l’injection d’une version arbitraire. Une liste blanche des versions
   supportées (`1.2.0` pour les nouvelles écritures) ou un contrôle d’identité
   du schéma est recommandé.
3. **Dépendance de production :** trancher `jsonschema` ou fournir un
   validateur équivalent, avec version épinglée et test dédié.
4. **Transactions :** documenter l’interdiction d’une transaction appelante
   active, ou ajouter une composition par savepoint. Décider qui porte
   l’atomicité d’un groupe d’écritures.
5. **Erreurs :** aligner le classement de la version absente avec la
   documentation ; envelopper les exceptions du validateur et les documents
   mal formés dans une erreur catégorisée.
6. **Relecture :** conserver la comparaison actuelle, mais ne pas la présenter
   comme une vérification d’intégrité référentielle globale. Ajouter un
   contrôle FK si la connexion n’est pas garantie.
7. **Tests :** ajouter au minimum : doublon expérience, relecture altérée
   expérience, erreur SQL expérience, versions des deux writers, transaction
   appelante active, connexion FK OFF/ON, validateur qui lève, schéma/validateur
   incohérents. Les tests de concurrence et de crash restent à planifier
   séparément.

### 9.3 Limites d’intégration déjà documentées

- Seuls `experiment` et `fee_schedule` sont couverts. Les événements, ordres,
  fills, transactions du ledger, manifestes et conversions n’ont pas de
  parcours commun.
- Aucun appel de `write_experiment`/`write_fee_schedule` hors du module,
  de `storage/__init__.py` et des tests n’a été trouvé. Aucun writer A1/A2 de
  production n’existe.
- Un `INSERT` SQL direct peut contourner le writer. La garantie dépend de la
  discipline et de la revue de code, comme indiqué dans D-052 et
  `WRITER_INTEGRATION.md`.
- Aucune base réelle n’existe ; les preuves sont synthétiques et en mémoire.

## 10. Migrations et avertissements historiques

- `0005_p0_foundations.sql` (mtime 2026-10-27 14:28),
  `0006_p0_ledger.sql` (15:05), `0007_contract_sql_alignment.sql` (16:18) sont
  antérieurs au writer (16:59) et n’ont pas été modifiés pendant cet audit.
- Ces fichiers sont **non suivis par Git** dans l’état observé. Il n’existe
  donc pas de diff de référence permettant de prouver qu’ils n’ont pas été
  modifiés depuis une version antérieure. La vérification est **non
  vérifiable formellement**, même si aucune modification n’a été observée
  pendant l’audit.
- Les rapports historiques (`REPORT_A0_A5_06_FIX.md`,
  `REPORT_A0_CONTRACT_SQL_ALIGNMENT.md`, `REPORT_A0_P0_REAUDIT_FIXES.md`,
  `REPORT_A5_P0_FINAL_REAUDIT.md`, `REPORT_A5_A5_06_FINAL_AUDIT.md`) portent
  des bannières historiques ou des chiffres datés. Aucune suppression des
  résultats d’origine n’a été constatée. Les avertissements sont cohérents avec
  l’état courant 653.
- `tests/README.md`, D-052 et `CONTRACT_FREEZE_PROPOSAL.md` présentent le
  writer comme préparé, non branché, et ne prononcent aucun gel. Cette
  présentation est cohérente avec le code.

## 11. Constats classés

### A5-CW-01 — FK désactivées : writer accepte des références inexistantes — **Élevé**

`contract_writer.py:342-380` accepte toute connexion. Avec
`foreign_keys=OFF`, une expérience référençant `strategy_missing` et
`manifest_missing` est acceptée ; `foreign_key_check` montre les violations
persistées. La documentation impose `open_connection`, mais le writer ne le
vérifie pas et ne contrôle pas les FK après écriture.

### A5-CW-02 — Version arbitraire par schéma injecté — **Moyen**

`ContractSpec` épingle la version au `const` du schéma fourni. Un schéma
`9.9.9` permet d’écrire `9.9.9`. Les schémas officiels protègent le cas
nominal, mais l’impossibilité n’est pas intrinsèque. Une liste blanche ou un
chargement verrouillé est nécessaire.

### A5-CW-03 — Version absente mal catégorisée — **Faible**

Version absente → `ContractSchemaError` ; documentation → `ContractVersionError`.
Refus et absence de ligne corrects, contrat d’erreur incorrect.

### A5-CW-04 — Exception du validateur non catégorisée — **Faible**

Un validateur qui lève propage `RuntimeError` brute. Aucune ligne, mais
l’appelant ne peut pas traiter l’erreur selon `category`.

### A5-CW-05 — `ContractSpec` mal formé : `AttributeError` — **Faible**

`properties=None` ou `schema_version="bad"` produisent `AttributeError`, pas
une erreur de domaine explicite.

### A5-CW-06 — Transaction appelante non documentée — **Moyen pour l’intégration**

Le refus est sûr, mais il n’est pas dans `WRITER_INTEGRATION.md` et il n’existe
pas de composition. A1/A2 pourrait croire qu’il peut envelopper le writer dans
sa transaction.

### A5-CW-07 — Pas d’atomicité multi-écritures — **Moyen**

Chaque writer commit séparément. Un barème peut rester écrit si l’expérience
suivante échoue. Aucun mécanisme de transaction de groupe.

### A5-CW-08 — Pas de validateur de production — **Moyen / bloquant A1/A2**

`jsonschema` n’est que dans les dépendances de test. Le writer est importable,
mais A1/A2 doit fournir un validateur ou faire approuver la dépendance de
production.

### A5-CW-09 — Duplication de la séquence de validation — **Faible**

Le writer n’appelle pas `validate_contract` ; il réimplémente
schéma/chronologie/version. Risque de dérive si le validateur partagé évolue.
Le rapport A0 surestime la réutilisation.

### A5-CW-10 — Couverture de tests incomplète — **Faible**

Les 14 tests couvrent le nominal, les chronologies, une erreur de schéma, les
versions de l’expérience, `paper_live`, une incohérence métier, un doublon de
barème et une relecture de barème. Ne sont pas couverts par la suite :
doublon expérience, relecture expérience, erreur SQL expérience, versions du
barème, transaction appelante active, FK OFF, validateur qui lève, schéma
injecté. Les contrôles indépendants couvrent plusieurs de ces cas, mais ils ne
sont pas des tests de régression versionnés.

### A5-CW-11 — Concurrence, crash et reprise non testés — **Info / risque non mesuré**

Aucun test multi-thread, timeout, crash après commit, reprise ou idempotence
n’a été exécuté. Les garanties correspondantes sont des garanties de code ou
des hypothèses, pas des résultats mesurés.

## 12. Recommandation

**Avis défavorable à un gel des contrats et du writer en l’état.** Le writer
peut continuer à être développé et utilisé dans des tests synthétiques, mais
A1/A2 ne devrait pas l’intégrer en production sans lever les conditions
suivantes :

1. contrôler ou imposer la connexion `open_connection` et les pragmas FK ;
2. verrouiller la source des schémas et des versions supportées ;
3. choisir et épingler le validateur de production ;
4. documenter la composition transactionnelle et l’absence d’atomicité
   multi-documents ;
5. aligner les catégories d’erreur et envelopper les exceptions du validateur ;
6. compléter les tests de régression pour les deux writers et les cas
   d’intégration ci-dessus.

Après ces corrections, un nouvel audit A5 ciblé pourra réévaluer un passage à
PASS. **Aucun gel n’est prononcé dans ce rapport.**
