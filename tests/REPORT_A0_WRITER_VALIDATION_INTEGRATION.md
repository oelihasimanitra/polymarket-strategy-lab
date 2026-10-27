# Rapport A0 — intégration du parcours d'écriture validé

> **Rapport historique avant durcissement.** Les chiffres 653/653/0 et les 14
> tests writer décrivent l'état d'origine. L'état courant après fermeture des
> contournements est **717/717/0**, avec 51 tests writer, approbation
> intrinsèque et parcours de test séparé. Voir
> `tests/REPORT_A0_WRITER_HARDENING_2.md`.

**Date :** 2026-10-27  
**Auteur :** A0 — architecte / intégrateur  
**Objet :** répondre au verdict PARTIAL de
`tests/REPORT_A5_AUDIT_POST_0007.md` en préparant un parcours commun
writer → validation → SQLite pour A1/A2.  
**Statut :** interface et tests préparés sur bases synthétiques. **Aucun
commit, aucun gel, aucune collecte, aucune simulation, aucune base réelle
modifiée.**

## 1. Interface commune proposée

```python
from polymarket_lab.storage import (
    ContractSpec,
    write_experiment,
    write_fee_schedule,
)

spec = ContractSpec(
    "experiment",
    experiment_schema,
    experiment_schema_validator,
)
write_experiment(connection, document, spec)
```

`ContractSpec(name, schema, validator)` porte :

- le nom du document (`experiment` ou `fee_schedule`) ;
- le schéma JSON chargé depuis `contracts/` ;
- un validateur JSON Schema fourni par l'appelant.

La version acceptée est lue dans
`properties.schema_version.const` du schéma. Un schéma non épinglé est refusé
à la construction. Le module n'importe pas `jsonschema` : la dépendance reste
injectée par A1/A2.

Mapping : `experiment_config_json` reçoit le document validé en JSON canonique,
les sous-objets `execution_assumptions`/`risk_limits`/`presentation_conversion`
sont sérialisés de la même manière, et `custom_formula_ref` reste `NULL`
(champ absent du contrat, formule suspendue). Aucun timestamp n'est inventé.

Fonctions publiques :

- `write_experiment(connection, document, spec) -> experiment_id` ;
- `write_fee_schedule(connection, document, spec) -> fee_schedule_id`.

Le parcours commun est dans
`src/polymarket_lab/storage/contract_writer.py`. Il réutilise
`validate_contract`/`chronology_errors` et `storage.transaction` ; il ne
duplique pas le validateur ni les règles SQL.

## 2. Ordre de validation et erreurs

1. **Schéma JSON** → `ContractSchemaError`.
2. **Chronologie** → `ContractChronologyError`.
3. **Version** → `ContractVersionError` (une erreur `schema_version` du schéma
   est classée comme erreur de version).
4. **Métier** → `ContractBusinessError`.
5. **Écriture transactionnelle** → `ContractSQLiteError` pour toute erreur
   SQLite.
6. **Relecture persistée** → `ContractPersistenceError`.

Une erreur aux étapes 1 à 4 interdit toute ouverture de transaction. Une erreur
SQL ou de relecture annule la transaction.

Chaque exception expose `category` (`schema`, `chronology`, `version`,
`business`, `sql`, `persistence`) et `issues`, la liste des messages détaillés.

## 3. Garanties effectivement testées

`tests/integration/test_contract_writer.py` contient 14 tests :

| Garantie | Test |
|---|---|
| Écriture valide d'une expérience | `test_writer_persists_valid_experiment_with_validated_version` |
| Écriture valide d'un barème | `test_writer_persists_valid_fee_schedule` |
| Version persistée = version validée | deux tests d'écriture valide |
| Période inversée refusée, aucune ligne | paramètres `experiment` et `fee_schedule` |
| Bornes égales refusées, aucune ligne | paramètres `experiment` et `fee_schedule` |
| Erreur de schéma refusée, aucune ligne | `test_writer_rejects_schema_error_without_row` |
| Versions `1.1.0` et `9.9.9` refusées | `test_writer_rejects_incompatible_version_without_row` |
| `paper_live` sans clé `end_time` refusé | `test_writer_rejects_paper_live_without_end_time_key` |
| `paper_live` avec `end_time: null` accepté | `test_writer_persists_paper_live_with_explicit_null_end` |
| Incohérence métier `completed_at` refusée | `test_writer_rejects_business_inconsistency_without_row` |
| Doublon SQL converti en erreur catégorisée, ligne existante conservée | `test_writer_wraps_sql_error_and_preserves_existing_row` |
| Relecture différente → rollback | `test_writer_rolls_back_when_persisted_row_differs` |

La version est écrite explicitement dans la colonne `schema_version` ; le
writer ne dépend pas du `DEFAULT 1.2.0` de la migration `0007`.

`paper_live` : le schéma exige la clé `period.end_time` ; le writer lit cette
clé après validation et refuse une clé absente avant insertion. SQLite reçoit
un `NULL` explicite uniquement quand la clé existe avec la valeur `null`.

## 4. Fichiers modifiés ou ajoutés

- `src/polymarket_lab/storage/contract_writer.py` — **nouveau** parcours
  commun et erreurs typées.
- `src/polymarket_lab/storage/__init__.py` — exports.
- `tests/integration/test_contract_writer.py` — **nouveau**, 14 tests.
- `WRITER_INTEGRATION.md` — **nouveau**, instructions A1/A2.
- `ARCHITECTURE.md` — §5.1 : writer commun et garanties.
- `DECISIONS.md` — D-052.
- `README.md`, `contracts/README.md` — liens vers l'interface.
- `tests/README.md` — 653/653/0, nouveau fichier et limites.
- `contracts/CONTRACT_FREEZE_PROPOSAL.md` — statistiques historisées et
  ligne courante 653.
- `tests/REPORT_A0_A5_06_FIX.md`, `tests/REPORT_A0_CONTRACT_SQL_ALIGNMENT.md`,
  `tests/REPORT_A0_P0_REAUDIT_FIXES.md`, `tests/REPORT_A5_P0_FINAL_REAUDIT.md`,
  `tests/REPORT_A5_A5_06_FINAL_AUDIT.md` — avertissements historiques sans
  suppression des résultats d'origine.
- `tests/REPORT_A0_WRITER_VALIDATION_INTEGRATION.md` — présent rapport.

Aucune migration `0005`, `0006` ou `0007` n'a été modifiée.

## 5. Commandes réellement exécutées

```powershell
.\.venv\Scripts\python.exe -m pytest tests -q -rxX
# 653 passed in 24.98s

.\.venv\Scripts\python.exe -m pytest tests --collect-only -q
# 653 tests collected

.\.venv\Scripts\python.exe -m pytest tests -q --runxfail
# 653 passed in 24.76s

.\.venv\Scripts\python.exe -m pytest tests\integration\test_p0_candidates.py -q
# 55 passed in 6.17s

.\.venv\Scripts\python.exe -m pytest tests\unit\test_contracts_negative.py `
  tests\unit\test_contracts_schema_validity.py `
  tests\integration\test_contract_sql_parity.py -q
# 261 passed in 3.31s

.\.venv\Scripts\python.exe -m pytest `
  tests\integration\test_0007_contract_sql_alignment.py `
  tests\unit\test_contract_validation.py `
  tests\integration\test_contract_writer.py -q
# 30 passed in 5.51s

git diff --check
# exit 0 ; avertissements CRLF uniquement
```

Aucun résultat ci-dessus n'est estimé : les commandes ont été exécutées après
les modifications. Les tests writer utilisent `db_v7` en mémoire et `tmp_path`
pour les chemins de migration.

## 6. Ce qui est garanti, et par qui

| Règle | Garantie |
|---|---|
| Forme JSON, champs requis, types | `validate_contract` via `ContractSpec.validator` |
| Période inversée / bornes égales | extension `x-polymarket-chronological-order` |
| Version supportée | `ContractSpec.version` et writer |
| `end_time` présent pour `paper_live` | schéma + contrôle writer avant mapping |
| Cohérence `completed_at`/statut | contrôle métier du writer |
| Aucune ligne sur validation échouée | validation avant `BEGIN` |
| Atomicité SQL | `storage.transaction` |
| Version persistée | binding explicite et relecture |
| Contraintes SQL, FK, triggers | SQLite 0.7 |
| Ligne relue identique | `ContractPersistenceError` + rollback |

## 7. Instructions d'intégration A1/A2

1. Charger le schéma réel depuis `contracts/experiment.schema.json` ou
   `contracts/fee_schedule.schema.json`.
2. Construire un `Draft202012Validator` (ou un validateur compatible
   `iter_errors`) avec ce même schéma.
3. Construire `ContractSpec` avec le nom exact.
4. Appeler `write_experiment` ou `write_fee_schedule` dans le point d'écriture
   A1/A2, avec la connexion applicative ouverte par `open_connection`.
5. Ne jamais exécuter d'`INSERT` direct sur `experiments` ou `fee_schedules`
   dans le code applicatif.
6. Laisser les écritures historiques hors de ce parcours ; ne pas réécrire
   les lignes `1.1.0`.
7. Pour les autres documents, étendre le parcours commun sans dupliquer
   l'ordre de validation.

Détails et exemple : `WRITER_INTEGRATION.md`.

## 8. Limites restantes

1. **Aucun writer A1/A2 de production** n'appelle encore
   `write_experiment`/`write_fee_schedule`. Le module est préparé et testé,
   mais le branchement au futur point d'écriture reste à faire.
2. Seuls `experiment` et `fee_schedule` sont couverts. Les événements, ordres,
   fills et transactions du ledger n'ont pas encore de parcours commun.
3. Un `INSERT` SQL direct peut contourner le writer. La garantie dépend de la
   discipline des writers A1/A2 et de la revue de code.
4. Les règles métier non déclarées dans les contrats ou le SQL ne sont pas
   inventées par le writer.
5. `jsonschema` reste une dépendance de test (D-018). A1/A2 doivent fournir un
   validateur compatible ou faire approuver son ajout aux dépendances de
   production ; le writer ne l'importe pas.
6. Aucune base réelle n'existe ; toutes les preuves sont synthétiques.
7. Aucun test de performance, de concurrence d'écriture ou de reprise après
   crash n'a été exécuté.
8. Aucun gel, aucun commit.

## 9. Recommandation pour le nouvel audit A5

Le dépôt est prêt pour un nouvel audit A5 ciblé sur le parcours
writer → validation → SQL. L'audit devrait vérifier :

- les 14 tests du writer et l'absence de ligne après chaque refus ;
- que les erreurs sont bien catégorisées ;
- que la version persistée est celle du document ;
- que `paper_live` sans clé `end_time` est refusé ;
- que les writers A1/A2 futurs appellent ce module et n'utilisent pas
  d'`INSERT` direct ;
- que les migrations `0005`/`0006`/`0007` n'ont pas été modifiées.

Le branchement à un writer de production reste la principale réserve. Aucun
gel n'est prononcé.
