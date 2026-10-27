# Audit A5 indépendant post-0007 — contrats, validateur et migration

> **AUDIT HISTORIQUE.** Ce rapport décrit l'état avant le durcissement du
> writer. Ses chiffres 653/653/0 et son verdict PARTIAL ne sont pas l'état
> courant ; voir `tests/REPORT_A0_WRITER_HARDENING.md` (672/672/0).

**Date :** 2026-10-27  
**Agent :** A5 — Validation et benchmark  
**Objet :** vérification indépendante de
`tests/REPORT_A0_CONTRACT_SQL_ALIGNMENT.md`, du validateur applicatif
`src/polymarket_lab/validation/contracts.py` et de la migration candidate
`schemas/migrations/0007_contract_sql_alignment.sql`.  
**Statut :** aucun gel, aucun commit, aucune migration sur une base de travail.
Toutes les bases sont en mémoire ou dans des fichiers temporaires isolés.

## 1. Verdict global

**PARTIAL.**

Le correctif A5-06 et la migration 0007 sont techniquement solides :

- `validate_contract` applique bien le schéma standard puis la règle
  chronologique ;
- les périodes inversées et les bornes égales sont refusées ;
- la migration 0007 réussit sur une base 0.6 synthétique, préserve les lignes,
  les triggers, vues, index et clés étrangères, et restaure la sauvegarde en
  cas d'échec ;
- les règles `end_time` demandées sont effectives :
  `research`/`validation`/`final_test` refusent `NULL`, `paper_live` l'accepte,
  et une fin non nulle doit être strictement postérieure au début ;
- les commandes annoncées par A0 sont reproductibles : 639 tests réussis,
  0 xfail, 55 tests P0, 261 tests ciblés.

Le verdict n'est pas PASS pour quatre raisons :

1. **Aucun writer applicatif n'existe encore.** `validate_contract` n'est appelé
   que par les tests ; le branchement runtime reste à faire. C'est acceptable
   pour poursuivre le développement, pas pour un gel.
2. **La distinction `end_time` absent vs `NULL` n'est pas résolue.** Elle ne
   peut pas l'être en SQL pour `paper_live` ; elle exige un writer qui valide le
   JSON. Le fait qu'elle soit documentée ne la rend pas appliquée.
3. **La version persistée n'est pas contrainte.** Les défauts SQL sont bien
   `1.2.0`, mais une insertion explicite avec `1.1.0`, `1.2.0` ou même `9.9.9`
   est acceptée. Le writer devra imposer la version du document validé.
4. **La preuve d'absence de modification rétroactive de 0005/0006 est limitée**
   par l'absence de suivi Git de ces fichiers ; aucune modification n'a été
   observée pendant l'audit, mais elle ne peut pas être prouvée par un diff.

Aucun défaut bloquant de la migration 0007 n'a été trouvé.

## 2. Commandes réellement exécutées

Depuis la racine du dépôt :

```powershell
.\.venv\Scripts\python.exe -m pytest tests -q -rxX
# 639 passed, 0 xfailed, 0 failed

.\.venv\Scripts\python.exe -m pytest tests --collect-only -q
# 639 tests collected

.\.venv\Scripts\python.exe -m pytest tests -q --runxfail
# 639 passed, 0 failed

.\.venv\Scripts\python.exe -m pytest tests\integration\test_p0_candidates.py -q
# 55 passed

.\.venv\Scripts\python.exe -m pytest tests\unit\test_contracts_negative.py `
  tests\unit\test_contracts_schema_validity.py `
  tests\integration\test_contract_sql_parity.py -q
# 261 passed

.\.venv\Scripts\python.exe -m pytest `
  tests\integration\test_0007_contract_sql_alignment.py `
  tests\unit\test_contract_validation.py -q
# 16 passed

git diff --check
# exit 0 ; avertissements CRLF uniquement
```

Audit indépendant hors dépôt :

```powershell
.\.venv\Scripts\python.exe "$env:TEMP\a5_post_0007_audit.py"
# 53 PASS, 0 FAIL, 53 checks
```

Le script d'audit n'a pas été ajouté au dépôt. Il a utilisé `:memory:` et des
fichiers temporaires, sans ouvrir de base réelle.

## 3. Audit du validateur chronologique

| # | Contrôle | Verdict | Preuve |
|---:|---|---|---|
| 1 | `validate_contract` fait schéma puis chronologie | **PASS** | `src/polymarket_lab/validation/contracts.py` l. 97-115 : `_schema_messages` d'abord ; retour immédiat si erreurs ; `chronology_errors` seulement sinon. |
| 2 | Une erreur de structure interrompt la chronologie | **PASS** | `test_application_validator_reports_schema_errors_before_chronology` et audit indépendant : un `effective_from` court produit uniquement l'erreur de schéma, pas le message « strictement postérieur ». |
| 3 | Périodes inversées et bornes égales refusées | **PASS** | `chronology_errors` l. 88 ; audit indépendant sur barème et expérience : erreurs « strictement postérieur » pour inversé et égal. |
| 4 | Formats et offsets cohérents | **PASS avec dépendance** | Le schéma JSON et le SQL refusent les offsets et formats courts. `chronology_errors` ne valide pas le format ; il suppose des timestamps canoniques et doit être appelé après le schéma. C'est l'ordre implémenté par `validate_contract`. |
| 5 | `tests/labtest/contracts.py` réexporte l'implémentation de `src/` | **PASS** | Import direct de `polymarket_lab.validation.contracts` l. 15-18 ; aucune seconde fonction `chronology_errors` n'existe dans `tests/`. |
| 6 | Les tests prouvent le validateur commun | **PASS** | 8 tests dans `tests/unit/test_contract_validation.py` ; `_json_accepts` de la parité appelle `validate_contract`, et non une fonction auxiliaire. |
| 7 | Parcours runtime d'écriture | **FAIL / NON VÉRIFIÉ** | Aucun appel de `validate_contract` dans `src/` hors du module lui-même. `grep` ne trouve que tests et documentation. Aucun writer d'expérience ou de barème. |

### 3.1. Preuve du court-circuit des erreurs de schéma

Sur un barème dont `effective_from = "2026-10-01"` et `effective_to` est
antérieur, `validate_contract` retourne uniquement :

```text
effective_from: '2026-10-01' does not match '^...Z$'
```

Il ne retourne pas le message chronologique. Le comportement correspond à la
docstring : la règle sémantique suppose un document de forme valide.

### 3.2. Réserve runtime

Le constat d'A0 est exact : aucun writer n'existe dans `src/`.
`polymarket_lab.validation.contracts.validate_contract` est un point d'entrée
applicatif, mais il n'est branché sur aucun stockage.

Ce qui est déjà garanti :

- le module applicatif existe et est importable ;
- il applique le schéma fourni, puis l'extension ;
- il est testé directement ;
- les tests de parité passent par lui.

Ce qui n'est pas garanti :

- qu'un document soit validé avant une insertion réelle ;
- qu'un writer ne contourne pas `validate_contract` ;
- que les champs absents soient distingués des champs nuls à l'écriture ;
- que la version du document persisté soit celle du document validé.

Cette limite est **acceptable à ce stade** parce qu'aucun writer A1/A2 n'existe
encore. Elle ne l'est plus dès qu'un writer apparaît : le branchement doit
devenir obligatoire avant la première insertion d'expérience ou de barème,
avant tout run `paper_live`, et avant tout gel. Le contrôle devra être un test
d'intégration writer → `validate_contract` → SQL, pas seulement un test du
module isolé.

## 4. Audit de la migration 0007

### 4.1. Registre, préflight et restauration

| Contrôle | Verdict | Preuve |
|---|---|---|
| Registre `6→0007` | **PASS** | `run_migration.py` l. 62-75 : cible 7, journal `(4,5,6)`, sept tables préservées. |
| Préflight SQL | **PASS** | `0007` l. 37-44 : compte `period_type <> 'paper_live' AND end_time IS NULL` dans une table temporaire `CHECK (bad = 0)`. |
| Préflight runner avec compteur | **PASS** | `_preflight_end_time` l. 140-157 ; message « 1 expérience(s)… » vérifié. Avec deux lignes, le message indique bien `2`. |
| Rejet sans perte | **PASS** | Sur base temporaire : `user_version=6`, journal `[4,5,6]`, comptages et lignes inchangés, triggers et vues intacts, sauvegarde présente. |
| SQL direct sans runner | **PASS avec limite** | Le SQL seul échoue (`CHECK constraint failed: bad = 0`), `user_version` reste 6 après rollback. Le message ne contient pas le compteur ; le runner le fournit. Le SQL direct n'est pas autonome : après échec, l'appelant doit faire `rollback`, sinon les `DROP VIEW`/`DROP TRIGGER` déjà exécutés restent en attente. |
| Sauvegarde préalable | **PASS** | `apply_migration` crée une sauvegarde avant ouverture de la connexion ; vérifiée sur succès et échec. |
| Restauration après échec post-commit | **PASS** | Injection après `apply_migration_on_connection` : restauration à `user_version=6`, journal `[4,5,6]`, comptages et lignes d'expériences identiques, `integrity_check=ok`, `foreign_key_check` vide, sauvegarde présente. |

### 4.2. Préservation des données et du schéma

Base synthétique 0.6 avec données historiques 1.1.0, deux barèmes liés par
`supersedes_fee_schedule_id`, une expérience historique, une expérience
`paper_live` à fin nulle, un ledger et une conversion :

| Contrôle | Résultat |
|---|---|
| `user_version` | 7 |
| Journal | `[4,5,6,7]`, une seule ligne 7 |
| Tables de données | Tous les comptages identiques ; `schema_migrations` gagne une ligne, comportement attendu |
| Lignes `experiments` | Identiques avant/après |
| Lignes `fee_schedules` | Identiques avant/après |
| Triggers | Mêmes noms et même SQL normalisé avant/après |
| Vues | Mêmes noms et même SQL normalisé avant/après |
| Index | Identiques |
| Clés étrangères | `PRAGMA foreign_key_list` identique pour toutes les tables, y compris l'auto-référence `fee_schedules` |
| `integrity_check` / `foreign_key_check` | `ok` / vide |
| Colonnes et types | Identiques pour `experiments` et `fee_schedules` |
| Défauts `schema_version` | `1.2.0` pour les deux tables |
| Lignes historiques 1.1.0 | Conservées |
| Nouvelles lignes par fixtures | Stockées en 1.2.0 |

Aucune structure perdue n'a été constatée. Les triggers dépendants
(`trg_orders_unit_*`, `trg_estimates_unit_*`, `trg_fills_unit_insert`,
`trg_ledger_postings_unit_insert`) et les sept vues sont recréés à l'identique.
L'auto-référence de `fee_schedules.supersedes_fee_schedule_id` est préservée.

### 4.3. Règles `end_time` sur 0.7

| Type | `end_time = NULL` | Résultat |
|---|---|---|
| `research` | `NULL` | refusé |
| `validation` | `NULL` | refusé |
| `final_test` | `NULL` | refusé |
| `paper_live` | `NULL` | accepté |
| `research` | fin égale au début | refusé |
| `research` | fin antérieure au début | refusé |
| `research` | fin strictement postérieure | accepté |

Les trois règles annoncées sont donc effectives.

### 4.4. Absence vs `NULL`

La migration ne peut pas distinguer une colonne omise d'un `NULL` : SQLite
stocke `NULL` dans les deux cas. Pour `paper_live`, une insertion qui omet
`end_time` est acceptée côté SQL, alors que le contrat JSON exige la clé
`period.end_time` (même si sa valeur peut être `null`).

Cette différence n'est **pas résolue** par 0007. Elle ne peut l'être que par un
writer qui valide le JSON avant insertion ; `validate_contract` le fait déjà,
mais aucun writer ne l'appelle. La documentation d'A0 le reconnaît ; cela ne
suffit pas à considérer la garantie comme appliquée.

### 4.5. Versions persistées

Les défauts sont bien passés à `1.2.0`, et les lignes historiques restent en
`1.1.0`. En revanche, SQL n'impose aucune valeur :

```text
experiment schema_version=1.1.0 : accepté
experiment schema_version=9.9.9 : accepté
fee_schedule schema_version=1.1.0 : accepté
fee_schedule schema_version=9.9.9 : accepté
```

Le défaut et les fixtures produisent `1.2.0`, mais une insertion explicite
arbitraire n'est pas bloquée. La garantie « nouvelles données en 1.2.0 » dépend
donc du writer et de `validate_contract`, pas de SQL. C'est une réserve de
runtime, pas une erreur de la migration 0007.

### 4.6. Absence de modification rétroactive de 0005/0006

Inspection : `0005` et `0006` conservent leurs règles auditées ; le nouveau
fichier est `0007`, et aucun élément de 0005/0006 n'a été réécrit pendant cet
audit. Les dates de modification de 0005/0006 sont antérieures à 0007.

**Limite de preuve :** les migrations sont non suivies par Git dans l'état
actuel ; il n'existe pas de diff de référence permettant une preuve
cryptographique. Le point est donc **PARTIAL / NON VÉRIFIÉ au sens fort**, sans
trace de modification observée.

## 5. Parité JSON ↔ SQL et versions

Les quatre cas `end_time = NULL` sont couverts sur 0.7 :

| Type | JSON | SQL 0.7 | Accord |
|---|---|---|---|
| `research` | refusé | refusé | oui |
| `validation` | refusé | refusé | oui |
| `final_test` | refusé | refusé | oui |
| `paper_live` | accepté | accepté | oui |

Le test `test_experiment_null_end_json_sql_parity_v7` vérifie ces quatre cas et
utilise `validate_contract`. Le cas absent est traité côté JSON par les tests
négatifs ; il reste la limite SQL décrite en 4.4.

Versions et documentation :

- contrats, exemples et tests : `1.2.0` ;
- SQL 0.7 : défauts `1.2.0`, historique conservé ;
- D-049 est désormais explicitement « décision initiale avant A5-06 » ;
- D-050 et D-051 documentent le validateur et 0007 ;
- `tests/README.md` et `CONTRACT_FREEZE_PROPOSAL.md` annoncent 639/639/0 ;
- `REPORT_A0_CONTRACT_SQL_ALIGNMENT.md` annonce 639/639/0.

Contradictions de documentation restantes :

- `tests/REPORT_A0_A5_06_FIX.md` a une bannière 639/639/0 mais contient encore
  des sections 619/619/0 ; elles sont historiques mais pas balisées localement.
- `tests/REPORT_A5_A5_06_FINAL_AUDIT.md` reste à 619/619/0 et PARTIAL, sans
  bannière « historique » ; il est antérieur à 0007.
- Ces écarts sont documentaires et ne changent pas les résultats exécutés.

## 6. Anomalies et points non vérifiés

### A5-0007-01 — Writer absent — **Élevée pour le gel, acceptable pour le développement**

`validate_contract` n'est appelé par aucun writer. Le branchement doit devenir
obligatoire avant toute insertion A1/A2 et avant le gel. Ajouter un test
d'intégration writer → validation → SQL.

### A5-0007-02 — Absence vs `NULL` pour `paper_live` — **Moyenne, non résolue**

SQL accepte une colonne omise comme `NULL` ; le contrat JSON exige la clé. La
seule solution est un writer validant le JSON. La documentation ne suffit pas.

### A5-0007-03 — `schema_version` explicite non contraint — **Moyenne**

Le défaut est `1.2.0`, mais SQL accepte `1.1.0`, `9.9.9`, etc. Le writer doit
persister la version du document validé, ou une contrainte SQL doit être
décidée sans casser l'historique.

### A5-0007-04 — Preuve de non-modification de 0005/0006 — **Info / NON VÉRIFIÉ**

Fichiers non suivis par Git ; aucune preuve cryptographique possible. Aucun
changement observé ; les règles critiques sont conformes.

### A5-0007-05 — Rapports historiques non balisés — **Faible**

`REPORT_A0_A5_06_FIX.md` et `REPORT_A5_A5_06_FINAL_AUDIT.md` contiennent encore
619/619/0 sans bannière locale. Ils doivent être marqués historiques ou
actualisés.

### A5-0007-06 — Test de défaut SQL indirect — **Faible**

Le test A0 « nouvelle ligne sans version explicite » insère via
`sqlfixtures.insert_fee_schedule`/`insert_experiment`, qui passent
`schema_version="1.2.0"` explicitement. Il ne teste donc pas réellement le
défaut SQL. L'audit indépendant a vérifié le défaut par insertion SQL réelle :
`1.2.0` pour les deux tables. Le défaut est correct, mais l'affirmation du
rapport est imprécise.

## 7. Recommandation sur la poursuite du développement

**La poursuite du développement est autorisée**, avec les migrations 0007 et
les contrats `1.2.0` maintenus comme candidats non gelés.

Conditions avant le prochain jalon sérieux :

1. créer le writer A1/A2 et l'obliger à appeler `validate_contract` avant toute
   insertion d'expérience ou de barème ;
2. ajouter un test d'intégration writer → validation → SQL ;
3. faire persister par le writer la version `1.2.0` du document validé ;
4. traiter explicitement la présence de `end_time` pour `paper_live` dans le
   writer (le SQL ne peut pas la distinguer de `NULL`) ;
5. baliser ou actualiser les rapports historiques 619 ;
6. rejouer la suite et cet audit après le branchement du writer.

**Je ne prononce aucun gel des contrats.** Le gel reste interdit tant que le
writer n'applique pas le validateur, que la présence de `end_time` n'est pas
garantie à l'écriture et que la version persistée n'est pas imposée par le
chemin d'écriture.

Aucun commit, aucun gel, aucune migration réelle. Aucun fichier `.db`/`.sqlite`
n'a été créé dans le dépôt ; `data/` ne contient que `.gitkeep`.
