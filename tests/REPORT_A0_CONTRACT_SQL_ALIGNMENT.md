# Rapport A0 — alignement contrats / SQL après audit A5-06

> **Rapport de l'étape 0007, historique pour l'état courant.** Les chiffres
> 639/639/0 ci-dessous décrivent l'état avant l'intégration du writer. L'état
> courant est **717/717/0** ; voir
> `tests/REPORT_A0_WRITER_HARDENING_2.md`.

**Date :** 2026-10-27  
**Auteur :** A0 — architecte / intégrateur  
**Objet :** traiter les constats de `tests/REPORT_A5_A5_06_FINAL_AUDIT.md`
(verdict PARTIAL), préparer un nouveau contrôle indépendant A5, sans gel ni
commit.  
**Statut :** corrections appliquées et testées sur bases synthétiques
uniquement. **Aucun commit, aucun gel, aucune collecte, aucune simulation,
aucune migration sur une base réelle.**

## 1. Verdict

Les quatre anomalies structurelles de l'audit sont traitées :

1. `chronology_errors` est maintenant appelé par un module applicatif dans
   `src/` via `validate_contract` ; le validateur standard seul n'est plus le
   chemin de validation.
2. La migration candidate `0007` aligne SQLite sur le contrat : `end_time`
   nul est refusé pour `research`, `validation` et `final_test`, accepté pour
   `paper_live`.
3. Les défauts `schema_version` de `experiments` et `fee_schedules` passent à
   `1.2.0` ; les lignes historiques gardent leur version d'origine.
4. La parité JSON ↔ SQL couvre désormais les quatre types de période avec
   `end_time = NULL`, plus les cas inversés/égaux et les formats non
   canoniques.

| Règle | Avant | Après |
|---|---|---|
| `fee_schedule` inversé/égal | SQL refusait ; JSON standard acceptait ; pas d'appel applicatif | `validate_contract` refuse ; tests de parité |
| `experiment` inversé/égal | SQL refusait ; JSON standard acceptait | `validate_contract` refuse ; SQL 0.7 refuse |
| `end_time=NULL` hors `paper_live` | SQL 0.6 acceptait | SQL 0.7 refuse ; JSON refuse ; parité testée |
| `end_time=NULL` en `paper_live` | SQL acceptait | SQL 0.7 accepte ; JSON accepte ; parité testée |
| `schema_version` par défaut | `1.1.0` dans SQL | `1.2.0` dans SQL 0.7 ; historique conservé |

Réserve principale restante : **aucun writer d'expériences ou de barèmes
n'existe encore dans `src/`**. Le point d'entrée applicatif existe et est
testé, mais A1/A2 doivent l'appeler depuis leur futur writer. Cette limite est
explicite et empêche de considérer le branchement runtime comme complet.

## 2. Fichiers modifiés ou ajoutés

- `src/polymarket_lab/validation/contracts.py` — **nouveau** point d'entrée
  `validate_contract`, `chronology_errors`, extension.
- `src/polymarket_lab/validation/__init__.py` — exports.
- `schemas/migrations/0007_contract_sql_alignment.sql` — **nouvelle**
  migration candidate 0.6 → 0.7.
- `schemas/migrations/run_migration.py` — registre `6→0007`, préflight compté.
- `schemas/migrations/README.md` — documentation 0007 et registre.
- `tests/labtest/contracts.py` — utilise le validateur de `src/` au lieu d'une
  implémentation locale.
- `tests/labtest/sqlfixtures.py` — `schema_version` explicite, paramétrable
  pour les données historiques.
- `tests/conftest.py` — fixtures `db_v7` / `seeded_v7`.
- `tests/unit/test_contract_validation.py` — **nouveau**, 8 tests.
- `tests/integration/test_0007_contract_sql_alignment.py` — **nouveau**,
  8 tests.
- `tests/integration/test_contract_sql_parity.py` — parité 0007 et validateur
  applicatif, 4 tests ajoutés.
- `tests/unit/test_contracts_negative.py` — docstring et cas A5-06.
- `tests/README.md` — couverture, chiffres, limites.
- `DECISIONS.md` — D-049 marquée comme décision initiale, D-050 actualisée,
  D-051 ajoutée.
- `ARCHITECTURE.md`, `contracts/README.md`,
  `contracts/CONTRACT_FREEZE_PROPOSAL.md`, `README.md` — versions candidates
  et point d'entrée.
- `tests/REPORT_A0_A5_06_FIX.md` et
  `tests/REPORT_A0_P0_REAUDIT_FIXES.md` — bannières historiques/actualisées.
- `tests/REPORT_A0_CONTRACT_SQL_ALIGNMENT.md` — présent rapport.

Aucune modification de `0005` ni `0006`.

## 3. Tâche A — validation chronologique applicative

### Point d'entrée

```python
polymarket_lab.validation.contracts.validate_contract(
    document, schema, schema_validator
) -> list[str]
```

Ordre d'exécution :

1. `schema_validator.iter_errors(document)` : validation de forme JSON Schema
   fournie par l'appelant ;
2. si des erreurs de forme existent, elles sont retournées seules ;
3. sinon, `chronology_errors(document, schema)` applique
   `x-polymarket-chronological-order`.

Le module n'importe pas `jsonschema` : le validateur de schéma est injecté.
Cela respecte D-018 (`jsonschema` dépendance de test) tout en gardant
l'extension dans le code applicatif.

### Preuve que le validateur standard ne suffit pas

`test_standard_validator_alone_ignores_chronology_extension` vérifie qu'un
`Draft202012Validator` seul accepte un barème inversé, puis que
`validate_contract` le refuse.

### Appels actuels

- `tests/unit/test_contract_validation.py` : parcours applicatif direct.
- `tests/integration/test_contract_sql_parity.py::_json_accepts` : tous les
  tests de parité passent par `validate_contract`.
- `tests/labtest/contracts.py` réexporte `chronology_errors` pour les tests
  historiques.

**Aucun writer d'expérience/barème n'existe dans `src/`.** Le validateur est
donc branché au niveau du module commun, pas encore à un point d'écriture réel.
A1/A2 doivent l'appeler avant toute insertion ; c'est une limite, pas une
réussite déclarée.

## 4. Tâche B — migration 0007

### Règle

- `paper_live` : `end_time` peut être `NULL`.
- `research`, `validation`, `final_test` : `end_time IS NOT NULL`.
- Si `end_time` existe : `end_time > start_time`.
- `schema_version` par défaut : `1.2.0` pour les nouvelles lignes.
- Les lignes existantes conservent leur `schema_version` (pas de backfill
  global).

### Conception

`0007_contract_sql_alignment.sql` :

1. préflight SQL : compte
   `period_type <> 'paper_live' AND end_time IS NULL` et échoue si le compte
   est non nul ;
2. le runner ajoute un préflight Python qui **nomme le nombre** de lignes
   incompatibles ;
3. reconstruction de `fee_schedules` avec défaut `1.2.0` ;
4. reconstruction de `experiments` avec défaut `1.2.0` et
   `CHECK (period_type = 'paper_live' OR end_time IS NOT NULL)` ;
5. recréation des vues, des triggers des tables reconstruites et des triggers
   dépendants qui compilent une référence à `experiments` ;
6. journal `[4,5,6,7]`, `user_version = 7`.

Le runner enregistre `6→0007`, sauvegarde avant écriture, vérifie les comptages
des sept tables, `integrity_check`, `foreign_key_check`, et restaure la
sauvegarde en cas d'échec avant ou après le `COMMIT`.

### Preuves exécutées

- `test_0007_runner_success_preserves_rows_and_resets_defaults` :
  - chemin réel du runner sur fichier temporaire ;
  - sauvegarde créée ;
  - journal `[4,5,6,7]`, `user_version = 7` ;
  - comptages identiques sur `experiments`, `fee_schedules`,
    `simulated_orders`, `simulated_fills`, `ledger_transactions`,
    `ledger_postings`, `settlement_conversions` ;
  - comparaison ligne complète avant/après pour `experiments` et
    `fee_schedules` ;
  - ensembles de triggers, vues et index identiques avant/après ;
  - ligne historique `1.1.0` conservée ;
  - nouvelle ligne sans version explicite stockée en `1.2.0` ;
  - triggers et vues recréés.
- `test_0007_preflight_refuses_null_end_with_count` :
  - `research`, `validation`, `final_test` avec `NULL` ;
  - refus avant reconstruction, message contenant le nombre ;
  - `user_version = 6`, journal `[4,5,6]`, données intactes, sauvegarde.
- `test_0007_sql_preflight_aborts_without_runner` : le SQL seul refuse aussi
  (table temporaire `CHECK (bad = 0)`), `user_version = 6`.
- `test_0007_post_commit_failure_restores_v6` : échec injecté après le
  `COMMIT`, restauration effective, données et journal à 6.
- `test_0007_enforces_end_time_by_period_type` : les trois types non
  `paper_live` refusent `NULL`, `paper_live` l'accepte et stocke `1.2.0`.
- `test_0007_preserves_strict_and_chronology_checks` : bornes égales et
  période inversée refusées.

## 5. Tâche C — parité JSON ↔ SQL

`test_experiment_null_end_json_sql_parity_v7` couvre, sur une base 0.7 :

| Type | JSON `end_time=null` | SQL 0.7 | Accord |
|---|---|---|---|
| `research` | refusé | refusé | oui |
| `validation` | refusé | refusé | oui |
| `final_test` | refusé | refusé | oui |
| `paper_live` | accepté | accepté | oui |

La valeur explicite `NULL` est testée. Les champs absents sont testés côté JSON
dans `test_contracts_negative.py` : `period.end_time` absent est refusé pour
tous les types, `effective_to` absent est accepté. SQLite ne distingue pas une
colonne omise d'un `NULL` ; pour `paper_live`, une insertion omettant la colonne
reste donc acceptée côté SQL alors que le JSON exige la clé. Cette différence
structurelle est documentée, pas masquée.

## 6. Tâche D — versions persistées

- `experiments.schema_version` : défaut SQL `1.2.0` après 0007.
- `fee_schedules.schema_version` : défaut SQL `1.2.0` après 0007.
- Fixtures : `schema_version` explicite `1.2.0` par défaut, paramètre
  `schema_version` pour représenter volontairement une ligne historique.
- Ligne historique `1.1.0` : conservée lors de la migration, testée.
- Exemples JSON : `experiment` et `fee_schedule` en `1.2.0`.
- Aucun remplacement global de `1.1.0` ; `normalizer_version` et les golden
  vectors historiques ne sont pas touchés.

## 7. Tâche E — documentation

- D-049 est désormais explicitement « décision initiale avant A5-06 », avec la
  révision D-050.
- D-050 pointe vers le validateur `src/`.
- D-051 documente le validateur, 0007 et le défaut de writer.
- Les docstrings `xfail` de `test_contracts_negative.py` et
  `test_contract_sql_parity.py` sont corrigées.
- Les rapports A0 antérieurs sont marqués historiques ou actualisés vers
  639/639/0.
- Les documents de versions indiquent SQL candidate 0.7 et contrats 1.2.0.
- Aucun gel n'est annoncé.

## 8. Commandes réellement exécutées

Depuis la racine du dépôt, avec `.\.venv\Scripts\python.exe` :

```powershell
.\.venv\Scripts\python.exe -m pytest tests -q -rxX
# 639 passed in 34.89s

.\.venv\Scripts\python.exe -m pytest tests --collect-only -q
# 639 tests collected

.\.venv\Scripts\python.exe -m pytest tests -q --runxfail
# 639 passed in 23.28s

.\.venv\Scripts\python.exe -m pytest tests\integration\test_p0_candidates.py -q
# 55 passed in 6.31s

.\.venv\Scripts\python.exe -m pytest tests\unit\test_contracts_negative.py `
  tests\unit\test_contracts_schema_validity.py `
  tests\integration\test_contract_sql_parity.py -q
# 261 passed in 3.75s

git diff --check
# exit 0 ; avertissements CRLF uniquement
```

Ces commandes ont réellement été exécutées. Les résultats ci-dessus sont ceux
des sorties, pas des estimations.

## 9. Limites et points non vérifiés

1. **Pas de writer applicatif** : `validate_contract` est le point d'entrée
   commun, mais aucun code de `src/` n'insère encore une expérience ou un
   barème. Le branchement à A1/A2 reste à faire et doit être audité.
2. **Aucune base réelle** : `data/` ne contient que `.gitkeep`. La migration
   0007 n'est prouvée que sur bases synthétiques en mémoire ou `tmp_path`.
3. **Absence vs NULL** : SQLite ne peut pas distinguer une colonne omise d'un
   `NULL`. Pour `paper_live`, l'absence de `end_time` côté SQL reste acceptée
   alors que la clé JSON est requise. La règle de nullité est alignée ; la
   présence de clé ne l'est pas totalement.
4. **Préflight direct** : le message détaillé avec compteur est fourni par le
   runner. L'exécution SQL directe échoue avec le message générique
   `CHECK constraint failed: bad = 0`.
5. **0007 candidate** : aucune application à une base de travail, aucun gel.
6. Aucun test réseau, aucune collecte Polymarket, aucune simulation de trading.
7. Le validateur de schéma reste injecté : les consumers doivent fournir un
   validateur JSON Schema réel, pas un objet factice.

## 10. État pour un nouvel audit A5

**Le dépôt est prêt pour un nouvel audit indépendant A5**, avec la réserve
explicite n° 1 : le validateur commun et la migration sont testés, mais aucun
writer A1/A2 n'appelle encore le validateur en production. L'audit doit
vérifier ce point séparément du module de validation.

Aucun commit, aucun gel, aucune migration réelle.
