# Audit final A5 — correction A5-06 et divergence `end_time`

> **AUDIT HISTORIQUE.** Ce rapport décrit l'état **avant** la migration 0007
> et avant le writer. Il est conservé comme résultat d'origine ; ses chiffres
> 619/619/0 et son verdict PARTIAL ne sont pas l'état courant. État courant :
> 672/672/0, voir `tests/REPORT_A0_WRITER_HARDENING.md`.

**Date :** 2026-10-27  
**Agent :** A5 — Validation et benchmark  
**Objet :** vérification indépendante de la correction A5-06 annoncée dans
`tests/REPORT_A0_A5_06_FIX.md`, et analyse de la divergence
`experiments.end_time` entre le SQL et le contrat JSON.  
**Statut :** aucun gel, aucun commit, aucune migration sur une base de travail.
Toutes les bases utilisées sont en mémoire ou dans des répertoires temporaires
isolés.

## 1. Verdict global

**PARTIAL.**

Le correctif A5-06 au sens strict est réel et testé :

- `effective_to > effective_from` et `period.end_time > period.start_time` sont
  portés par l'extension `x-polymarket-chronological-order` ;
- `chronology_errors` refuse les périodes inversées et les bornes égales ;
- les deux anciens `xfail` sont devenus des tests verts ;
- 619 tests passent, y compris sous `--runxfail` ;
- les cas de format non canonique et d'offset sont refusés par le schéma JSON
  et par le SQL.

Le dossier reste toutefois incomplet pour un gel :

1. `chronology_errors` n'est appelé par aucun parcours applicatif dans `src/` ;
   il n'existe que dans les tests. Un validateur JSON Schema standard continue
   d'ignorer l'extension.
2. La divergence `end_time` est confirmée : le SQL accepte `NULL` pour
   `research`, `validation` et `final_test`, alors que le contrat JSON exige une
   valeur non nulle pour ces trois types.
3. La version persistée reste incohérente : les colonnes SQL
   `experiments.schema_version` et `fee_schedules.schema_version` ont encore
   pour défaut `1.1.0`, alors que les contrats candidats sont en `1.2.0`.
4. Le test de parité JSON ↔ SQL omet précisément le cas divergent
   `research` + `end_time NULL` ; les 619 tests verts ne prouvent donc pas la
   parité complète.

Aucun gel n'est prononcé.

## 2. Commandes réellement exécutées

Depuis la racine du dépôt :

```powershell
.\.venv\Scripts\python.exe -m pytest tests -q -rxX
# 619 passed, 0 xfailed, 0 failed

.\.venv\Scripts\python.exe -m pytest tests --collect-only -q
# 619 tests collected

.\.venv\Scripts\python.exe -m pytest tests -q --runxfail
# 619 passed, 0 failed

.\.venv\Scripts\python.exe -m pytest tests\integration\test_p0_candidates.py -q
# 55 passed

.\.venv\Scripts\python.exe -m pytest tests\unit\test_contracts_negative.py `
  tests\unit\test_contracts_schema_validity.py `
  tests\integration\test_contract_sql_parity.py -q
# 257 passed

git diff --check
# exit 0 ; seuls des avertissements CRLF sont émis
```

Audit indépendant hors dépôt :

```powershell
.\.venv\Scripts\python.exe "$env:TEMP\a5_a506_audit.py"
# 50 PASS, 2 FAIL, 52 checks
# Les 2 FAIL sont l'absence d'appel de chronology_errors dans src/
# et le paquet applicatif de validation vide.
```

Le script d'audit n'a pas été ajouté au dépôt. Il n'a utilisé que des bases
SQLite en mémoire (`:memory:`) ; un contrôle SQL complémentaire des barèmes a
été exécuté de la même manière.

## 3. Vérification de A5-06

| # | Contrôle | Verdict | Preuves |
|---:|---|---|---|
| 1 | Ordre strict conforme au SQL | **PASS** | Le SQL impose `effective_to > effective_from` (barèmes) et `end_time > start_time` (expériences). L'extension impose `strict: true` et `chronology_errors` compare avec `end < start` ou `end == start` (`tests/labtest/contracts.py` l. 195-233). |
| 2 | Bornes égales refusées | **PASS** | Cas JSON injectés et rejoués : erreur `effective_to doit être strictement postérieur…` et `end_time doit être strictement postérieur…`. Le SQL refuse aussi les bornes égales (`CHECK ... end_time > start_time`). |
| 3 | Dates inversées refusées | **PASS** | Même mécanisme ; le validateur standard accepte la forme, mais `chronology_errors` refuse. Les tests A5-06 et les tests de parité le vérifient. |
| 4 | Formats et offsets cohérents | **PASS avec dépendance** | Les schémas refusent les offsets `+00:00` et les formats courts ; le SQL les refuse par `GLOB`. `chronology_errors` seul ne valide pas le format : il suppose des timestamps canoniques. Il doit donc être appelé après la validation de schéma. |
| 5 | `chronology_errors` appelé par le parcours applicatif | **FAIL** | Aucun fichier de `src/` ne contient `chronology_errors` ni `x-polymarket-chronological-order`. `src/polymarket_lab/validation/__init__.py` est vide (0 octet). Les seuls appels sont dans les tests. |
| 6 | Règle pas uniquement dans une extension ignorée | **PARTIAL** | L'extension est déclarée dans les deux schémas et une référence exécutable existe (`chronology_errors`), mais elle n'est branchée sur aucun consommateur applicatif. Le validateur standard `Draft202012Validator` accepte toujours une période inversée. |
| 7 | Version `fee_schedule` 1.2.0 cohérente | **PARTIAL** | Le schéma, l'exemple et les tests sont en `1.2.0` ; mais le défaut SQL de `fee_schedules.schema_version` reste `1.1.0`, et une insertion via les fixtures stocke `1.1.0`. D-049 contient encore « `fee_schedule` reste `1.1.0` » avant sa note de mise à jour. |
| 8 | Tests exécutables et couvrant les cas annoncés | **PASS** | 619 tests passent ; 257 tests ciblés passent ; les deux anciens `xfail` ne sont plus des tests ignorés. Réserve de couverture : le test de parité n'inclut pas `research` + `end_time NULL`. |

### 3.1. Preuve de l'ordre strict

Pour un barème inversé, le validateur standard ne signale rien — JSON Schema
2020-12 ne compare pas deux champs — mais `chronology_errors` renvoie :

```text
effective_to doit être strictement postérieur à effective_from
```

Pour une expérience inversée, il renvoie :

```text
end_time doit être strictement postérieur à start_time
```

Les bornes égales produisent la même erreur. Les tests
`test_fee_schedule_equal_effective_bounds_are_rejected` et
`test_experiment_equal_period_bounds_are_rejected` couvrent ce cas. Le SQL
refuse aussi les bornes égales et les périodes inversées.

### 3.2. Formats et offsets

Les motifs JSON et les `CHECK ... GLOB` SQL imposent :

```text
YYYY-MM-DDTHH:MM:SS.ffffffZ
```

Les offsets `+00:00` et les formats courts sont refusés par le schéma. En
revanche, `chronology_errors` ne contient aucun contrôle de format : il compare
lexicographiquement les chaînes. Un offset seul peut donc ne pas produire
d'erreur sémantique (cas du barème), même s'il est refusé par le schéma. Le
contrat doit donc être validé par le schéma **puis** par `chronology_errors`.
Cette dépendance est correcte dans les tests (`_json_accepts` combine les deux),
mais elle n'est pas branchée dans un validateur applicatif.

Vérification SQL complémentaire sur les barèmes : valide et fin nulle acceptés ;
période inversée, bornes égales, offset et format court refusés par
`CHECK (effective_to IS NULL OR effective_to > effective_from)`.

### 3.3. Intégration réelle

Recherche effectuée dans `src/` :

```text
chronology_errors : 0 occurrence
x-polymarket-chronological-order : 0 occurrence
```

`src/polymarket_lab/validation/__init__.py` est vide. Le seul parcours qui
applique la règle est le parcours de test. C'est la limite principale de la
correction : la règle est exécutable, mais pas encore appliquée par
l'application. A1/A2 doivent appeler un validateur commun avant insertion ;
ce validateur n'existe pas encore.

### 3.4. Version `fee_schedule`

Version constatée :

- `contracts/fee_schedule.schema.json` : `schema_version.const = "1.2.0"` ;
- `contracts/examples/fee_schedule.json` : `"schema_version": "1.2.0"` ;
- `tests/unit/test_contracts_schema_validity.py` et
  `test_contracts_examples.py` : `1.2.0` ;
- documentation `ARCHITECTURE.md`, `contracts/README.md` et
  `CONTRACT_FREEZE_PROPOSAL.md` : candidat `1.2.0`.

Mais dans SQL 0.6 :

```text
fee_schedules.schema_version DEFAULT '1.1.0'
experiments.schema_version    DEFAULT '1.1.0'
```

Une insertion de barème ou d'expérience via les fixtures, sans
`schema_version` explicite, stocke `1.1.0`. C'est une incohérence de
persistance, pas une erreur de validation JSON. Elle doit être corrigée dans le
writer ou par une migration dédiée, et testée.

La version `1.1.0` n'existe pas comme fichier séparé dans le dépôt ; le commit
de référence contient `1.0.0`. La non-modification « en place » de l'ancienne
version est donc **NON VÉRIFIÉE** au niveau artefact : elle repose sur le
numéro de version et sur l'historique Git, pas sur un fichier `1.1.0` conservé.

## 4. Divergence `experiments.end_time`

### 4.1. Constat SQL

Le schéma SQL définit :

```sql
end_time TEXT,
CHECK (end_time IS NULL OR end_time > start_time),
CHECK (period_type = 'paper_live' OR data_manifest_id IS NOT NULL)
```

aux lignes 216, 238 et 239 de `schemas/initial_db_schema.sql`, et reprend la
même règle dans `schemas/migrations/0004_consolidation.sql` l. 309-310.
`0005` et `0006` ne reconstruisent pas `experiments` : la règle reste celle de
0.4/0.6.

Vérification indépendante sur bases 0.4 et 0.6 :

| Type de période | `end_time = NULL` | Résultat SQL |
|---|---|---|
| `research` | `NULL` | accepté |
| `validation` | `NULL` | accepté |
| `final_test` | `NULL` | accepté (manifeste `recorded` en 0.6, pour éviter le trigger fixture) |
| `paper_live` | `NULL` | accepté |
| `research` | inversé / égal | refusé |
| `research` | offset / format court | refusé |

Le SQL ne distingue donc pas une fin absente d'une fin nulle : une insertion
omettant la colonne produit `NULL`, et `NULL` est accepté.

### 4.2. Constat JSON

Le contrat `experiment.schema.json` :

- exige `period.end_time` dans `period.required` (l. 61-65) ;
- autorise `null` dans `oneOf` (l. 78-87) ;
- mais impose un timestamp non nul pour `research`, `validation` et
  `final_test` via le `if/then` (l. 89-111).

Vérification indépendante :

| Type de période | `end_time = null` | `end_time` absent | Résultat JSON |
|---|---|---|---|
| `research` | refusé | refusé | `None is not of type 'string'` / required |
| `validation` | refusé | refusé | idem |
| `final_test` | refusé | refusé | idem |
| `paper_live` | accepté | refusé | `null` accepté, clé absente refusée |

Le barème `fee_schedule` n'a pas cette divergence : `effective_to` est
optionnel, `null` et l'absence sont acceptés côté JSON comme côté SQL.

### 4.3. Différence exacte

La divergence n'est pas la comparaison `>` — celle-ci est corrigée — mais la
**présence et la nullité** de la fin :

- SQL : `NULL` accepté pour les quatre types ;
- JSON : `NULL` refusé pour `research`, `validation`, `final_test`, accepté
  pour `paper_live` ;
- absence : JSON refuse la clé pour tous les types ; SQL ne peut pas distinguer
  une colonne omise d'un `NULL`.

Les tests de parité
(`tests/integration/test_contract_sql_parity.py` l. 564-590) n'insèrent que
`paper_live` + `NULL` et n'ont pas de cas `research` + `NULL`. C'est pourquoi la
suite reste verte malgré la divergence.

### 4.4. Conséquences sur la reproductibilité

Une expérience `research`, `validation` ou `final_test` sans fin peut être
insérée directement en SQL. Le manifeste et le cutoff de données peuvent
borner les données disponibles, mais la fenêtre d'évaluation n'est plus
définie par le contrat. Cela complique :

- la délimitation de la période de mesure et du PnL ;
- la vérification d'absence de look-ahead et de réutilisation d'une fenêtre
  `final_test` ;
- la comparaison reproductible de deux runs ;
- l'audit des expériences historiques.

Le risque est faible dans l'immédiat car aucune base de travail réelle ni aucun
writer applicatif n'existe, mais il est structurel dès qu'A1/A2 écriront en SQL.

### 4.5. Conséquences sur les données existantes et les migrations

Aucune base réelle n'existe dans le dépôt (`data/` ne contient que
`.gitkeep`). Une migration restrictive devrait néanmoins prévoir un préflight :
compter les lignes `period_type <> 'paper_live' AND end_time IS NULL`, refuser
la migration si le compte est non nul, et exiger une correction explicite des
données legacy. Il ne faut pas remplir silencieusement `end_time` avec une date
inventée.

### 4.6. Recommandation : **A**, avec réserve si la règle métier change

**A. Rendre le SQL cohérent avec le contrat par une migration dédiée et
versionnée.** C'est la recommandation principale.

La règle métier actuelle du contrat est claire : une expérience historique a
une fin non nulle et strictement postérieure au début. Le SQL est le seul
composant plus permissif. La satisfaire sans modifier le SQL exigerait soit de
relâcher le contrat JSON (B), soit de compter uniquement sur une validation
applicative (C) alors que des écritures SQL directes resteraient possibles.
Aucune de ces deux options ne préserve la garantie actuelle au niveau stockage.

Migration proposée :

- nouvelle migration `0007` après `0006` (0.6 → 0.7), sans modifier les
  migrations candidates déjà auditées `0005`/`0006` ;
- préflight des lignes `period_type <> 'paper_live' AND end_time IS NULL` ;
- reconstruction de `experiments` avec
  `CHECK (period_type = 'paper_live' OR end_time IS NOT NULL)` et conservation
  de `CHECK (end_time IS NULL OR end_time > start_time)` ;
- sauvegarde/restauration, journal `[4,5,6,7]`, `user_version = 7`, tests
  d'échec préflight et post-commit ;
- tests de parité JSON ↔ SQL incluant enfin `research` + `NULL` : les deux
  doivent refuser.

**B. Modifier le contrat JSON** pour accepter explicitement `end_time` nul ou
absent pour les types prévus par le SQL. Cette option n'est défendable que si
le propriétaire décide qu'une recherche ou une validation peut être ouverte.
Elle exige une nouvelle version de contrat (`1.3.0`, pas une modification en
place de `1.2.0`), la mise à jour des exemples, tests, docs et une analyse de
reproductibilité. Elle affaiblit la garantie actuelle et n'est pas ma
recommandation par défaut.

**C. Maintenir la divergence temporairement**, documenter le risque et
interdire le gel. C'est acceptable comme état transitoire, mais insuffisant
pour un gel : le SQL reste plus permissif que le contrat et aucune validation
applicative n'est encore branchée.

## 5. Anomalies restantes

### A5-A506-01 — `chronology_errors` non branché dans l'application — **Élevée**

Aucun appel dans `src/` ; seul le parcours de test applique la règle. Le
validateur standard ignore l'extension. Un document inversé ou à bornes égales
peut donc franchir la validation applicative standard et n'être arrêté que par
le SQL, ou plus tard. La règle n'est pas encore une barrière runtime.

### A5-A506-02 — `end_time` nul accepté par le SQL pour trois types — **Élevée**

`research`, `validation` et `final_test` acceptent `end_time IS NULL` en SQL
alors que le contrat JSON l'interdit. La divergence est confirmée sur 0.4 et
0.6. Elle touche la définition même de la fenêtre d'expérience et la
reproductibilité.

### A5-A506-03 — `schema_version` persisté en 1.1.0 — **Moyenne**

Les défauts SQL de `experiments` et `fee_schedules` restent `1.1.0`, et les
fixtures y stockent `1.1.0`, alors que les contrats/exemples/tests sont en
`1.2.0`. Le numéro de version du document persisté n'est donc pas cohérent avec
le contrat validé.

### A5-A506-04 — Parité JSON ↔ SQL incomplète — **Moyenne**

Le test de parité omet `research` + `end_time NULL`, le cas précis de la
divergence. Le résultat 619/619 ne prouve pas la parité complète des champs
nuls.

### A5-A506-05 — Documentation contradictoire ou obsolète — **Faible**

- `DECISIONS.md` D-049 affirme encore « `fee_schedule` reste `1.1.0` » avant sa
  note de mise à jour D-050.
- `tests/unit/test_contracts_negative.py` et
  `tests/integration/test_contract_sql_parity.py` ont encore une docstring qui
  mentionne `xfail(strict=True)`, alors que les tests A5-06 sont verts.
- La version `1.1.0` n'existe pas comme artefact séparé dans le dépôt ; sa
  non-modification en place est **NON VÉRIFIÉE**.

### A5-A506-06 — Sondes et intégration runtime — **Info / NON VÉRIFIÉ**

Il n'existe pas de parcours applicatif de validation à tester : le paquet
`src/polymarket_lab/validation/` est vide. Le comportement runtime de
`chronology_errors` est donc **NON VÉRIFIÉ** ; seuls les tests et le SQL sont
observables.

## 6. Recommandation sur le gel

**Je ne prononce pas le gel des contrats.**

Le correctif A5-06 au sens strict est effectif : la comparaison `>` est
implémentée, testée et les deux anciens `xfail` sont verts. Mais le dossier de
gel n'est pas complet :

1. brancher `chronology_errors` dans un validateur applicatif commun
   (schéma standard **puis** règle chronologique) et le tester depuis `src/` ;
2. trancher `end_time` — recommandation A, migration `0007` dédiée ;
3. aligner `schema_version` persisté et contrat `1.2.0` (writer ou migration) ;
4. ajouter le cas de parité `research` + `NULL` et corriger les docstrings /
   D-049 ;
5. relancer la suite et ce ré-audit.

Tant que ces points ne sont pas traités, le gel doit rester interdit. Si le
propriétaire choisit C, la divergence doit être explicitement acceptée et
documentée, mais le gel reste prématuré.

Aucun gel n'est prononcé. Aucun commit n'est créé. Aucune base de travail réelle
n'a été ouverte en écriture ; aucun fichier `.db`/`.sqlite`/`.sqlite3` n'existe
dans le dépôt et `data/` ne contient que `.gitkeep`.
