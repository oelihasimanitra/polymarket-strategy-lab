# Rapport A0 — durcissement du writer commun

> **Mise à jour 2026-10-27 (post-audit A5).** Rapport historique. Les
> mécanismes `ContractSpec.for_tests` et `allow_test_specs=True` décrits ici
> ont été remplacés par un parcours de test séparé et une approbation
> intrinsèque. Voir `tests/REPORT_A0_WRITER_HARDENING_2.md`. Les chiffres
> 672/672/0 ci-dessous restent ceux de cette mesure.

**Date :** 2026-10-27  
**Auteur :** A0 — architecte / intégrateur  
**Objet :** traiter les constats de `tests/REPORT_A5_CONTRACT_WRITER_AUDIT.md`
(verdict PARTIEL, 79 PASS / 1 FAIL sur 80 contrôles) avant intégration A1/A2.  
**Statut :** corrections et tests sur bases synthétiques. **Aucun commit,
aucun gel, aucune collecte, aucune simulation, aucune base réelle modifiée.**

## 1. Synthèse

Le writer commun est renforcé sur quatre axes :

1. **Connexion** : refus explicite de `foreign_keys=OFF`,
   `recursive_triggers=OFF`, `isolation_level` non nul et transaction déjà
   ouverte. Aucune connexion n'est modifiée implicitement.
2. **Contrats approuvés** : registre nom/version/SHA-256 ; un schéma injecté
   arbitraire, y compris avec `schema_version.const = "9.9.9"`, ne peut pas
   être utilisé comme contrat de production.
3. **Validation centralisée** : `contract_issues` est la séquence commune
   schéma → chronologie → version ; le writer ne la duplique plus.
4. **Erreurs et transactions** : version absente classée `version`, exceptions
   du validateur enveloppées avec cause, `ContractSpec` mal formé rejeté
   proprement, transaction appelante refusée sans être annulée, absence
   d'atomicité multi-écritures documentée et testée.

La dépendance de validation de production reste un point ouvert : aucune
dépendance n'a été ajoutée sans décision.

## 2. Tâche A — connexion SQLite

`_check_connection` vérifie avant toute validation :

- `connection` est une `sqlite3.Connection` ;
- `connection.in_transaction` est faux ;
- `isolation_level is None` ;
- `PRAGMA foreign_keys = 1` ;
- `PRAGMA recursive_triggers = 1`.

Le writer **ne modifie pas** ces valeurs. Une connexion brute avec
`foreign_keys=OFF` est refusée avant insertion, même pour un document valide.
`open_connection` est vérifié par
`test_open_connection_satisfies_writer_requirements`.

Tests ajoutés :

- `test_writer_rejects_connection_with_foreign_keys_off` ;
- `test_writer_rejects_missing_fk_with_foreign_keys_on` ;
- `test_open_connection_satisfies_writer_requirements` ;
- `test_writer_refuses_existing_transaction_without_touching_it`.

Une référence inexistante ne peut donc pas être persistée par le writer :
la connexion FK OFF est refusée, et avec FK ON l'erreur SQL est catégorisée
`ContractSQLiteError` sans ligne. Aucun `PRAGMA foreign_key_check` après
écriture n'est nécessaire pour ces cas ; il n'est pas présenté comme une
garantie globale.

## 3. Tâche B — registre des contrats approuvés

`src/polymarket_lab/validation/registry.py` contient :

```python
ApprovedContract(
    name="experiment",
    version="1.2.0",
    schema_sha256="6d20ab72...e93fe85",
    relative_path="contracts/experiment.schema.json",
)
```

et l'entrée équivalente pour `fee_schedule`.

- `load_approved_schema(name)` vérifie le SHA-256 du fichier et sa version.
- `ContractSpec.from_approved(name, validator)` charge le schéma approuvé et
  vérifie que le validateur expose exactement ce schéma.
- `ContractSpec(..., approved=True)` vérifie le registre et le validateur ; un
  schéma falsifié ou un validateur construit sur un autre schéma lève
  `ContractApprovalError`.
- `ContractSpec.for_tests(...)` crée un schéma temporaire explicitement non
  approuvé.
- Les writers refusent un `ContractSpec.for_tests` sans
  `allow_test_specs=True`.

Une nouvelle version de contrat devra donc modifier le contrat, le registre
(hash + version), les décisions et les tests ; aucun appelant ne peut
simplement injecter un `const` arbitraire.

Tests ajoutés :

- `test_forged_production_schema_is_rejected` ;
- `test_unapproved_test_schema_cannot_be_used_as_production` ;
- `test_approved_validator_must_match_schema` ;
- `test_contract_spec_from_approved_registry_writes` ;
- `test_test_spec_requires_explicit_test_permission`.

## 4. Tâche C — validation centralisée

`src/polymarket_lab/validation/contracts.py` expose désormais
`contract_issues(document, schema, validator, expected_version=...)` :

1. erreurs de schéma, avec les erreurs `schema_version` classées `version` ;
2. erreurs de chronologie ;
3. vérification de la version attendue.

`validate_contract` appelle cette fonction et renvoie les messages. Le writer
n'a plus de copie de la séquence : il mappe les catégories
`ContractSchemaError`, `ContractChronologyError` et `ContractVersionError`.

Les erreurs de forme court-circuitent la chronologie, comme avant. Une erreur
de version absente est désormais classée `ContractVersionError` :
le cas est couvert par `test_writer_rejects_missing_version_as_version_error`.

## 5. Tâche D — erreurs

Nouvelles classes publiques :

| Classe | Catégorie | Cas |
|---|---|---|
| `ContractSpecError` | `spec` | `ContractSpec` mal formé |
| `ContractApprovalError` | `approval` | schéma non approuvé/falsifié |
| `ContractConnectionError` | `connection` | pragmas/isolation/transaction |
| `ContractValidatorError` | `validator` | exception du validateur |
| `ContractSchemaError` | `schema` | forme invalide |
| `ContractChronologyError` | `chronology` | ordre invalide |
| `ContractVersionError` | `version` | version absente/incompatible |
| `ContractBusinessError` | `business` | contrôle métier |
| `ContractSQLiteError` | `sql` | contrainte/FK/trigger/doublon |
| `ContractPersistenceError` | `persistence` | relecture divergente |

Une exception du validateur est enveloppée dans `ContractValidatorError`,
elle-même causée par `SchemaValidatorError`, qui conserve l'exception d'origine
via `from`. Un document non `Mapping` est refusé par une erreur de schéma.

## 6. Tâche E — dépendance de validation en production

Aucune dépendance n'a été ajoutée. Le writer reste sans import de
`jsonschema` ; le validateur est injecté.

Options documentées :

1. approuver `jsonschema` en dépendance de production avec version épinglée ;
2. fournir une autre implémentation `iter_errors` documentée et testée.

`ContractSpec.from_approved` exige que le validateur expose le même `.schema`
que le schéma approuvé. Le point bloquant pour A1/A2 est donc l'absence de
validateur de production approuvé, pas le writer lui-même. Décision
propriétaire requise ; aucune modification de `requirements.txt` n'a été faite.

## 7. Tâche F — transactions et atomicité

- Une transaction appelante active est refusée par `ContractConnectionError`
  avant validation ; le writer ne la rollback pas.
- Chaque appel writer ouvre et commit sa propre transaction.
- Deux appels séparés ne forment pas une transaction commune :
  `test_two_writer_calls_are_not_one_transaction` le démontre (un barème reste
  commité quand l'expérience suivante échoue).
- Une erreur SQL ou de persistance annule la transaction du writer
  (`test_writer_wraps_sql_error_and_preserves_existing_row`,
  `test_writer_rolls_back_when_persisted_row_differs`).
- Concurrence, verrous, timeout, crash après commit et reprise ne sont pas
  testés. Aucun résultat n'est revendiqué pour ces cas.
- Une composition de groupe (`contract_write_batch`) est proposée dans
  `WRITER_INTEGRATION.md`, non implémentée.

## 8. Tâche G — traçabilité des migrations

Constat :

- `git ls-files schemas/migrations` ne retourne aucun fichier ;
- `0004`, `0005`, `0006`, `0007` et le nouveau `SHA256SUMS` ne sont pas suivis
  par Git dans l'état observé ;
- les mtimes ne prouvent pas l'historique.

Solution proposée et partiellement ajoutée :

- `schemas/migrations/SHA256SUMS` donne la baseline des quatre migrations ;
- `tests/integration/test_migration_manifest.py` vérifie les hashes et la
  couverture complète.

Cette baseline prouve l'identité **actuelle** des fichiers, pas leur
non-modification historique. La preuve formelle exige que le propriétaire
ajoute les migrations et `SHA256SUMS` dans un commit Git, puis conserve ce
commit comme référence. Aucun historique Git n'a été initialisé, modifié ou
inventé.

## 9. Fichiers modifiés ou ajoutés

- `src/polymarket_lab/validation/contracts.py` — `contract_issues`,
  `ContractIssue`, `SchemaValidatorError`, classification version absente.
- `src/polymarket_lab/validation/registry.py` — **nouveau** registre
  approuvé.
- `src/polymarket_lab/validation/__init__.py` — exports.
- `src/polymarket_lab/storage/contract_writer.py` — connexion, approbation,
  erreurs, validation centralisée.
- `src/polymarket_lab/storage/__init__.py` — exports.
- `tests/integration/test_contract_writer.py` — 31 tests writer.
- `tests/integration/test_migration_manifest.py` — **nouveau**, 2 tests.
- `schemas/migrations/SHA256SUMS` — **nouveau** baseline.
- `schemas/migrations/README.md` — traçabilité.
- `WRITER_INTEGRATION.md` — interface, connexion, registre, transactions.
- `ARCHITECTURE.md` — writer durci.
- `DECISIONS.md` — D-053.
- `contracts/README.md` — registre.
- `tests/README.md` — 672/672/0, tests et limites.
- `contracts/CONTRACT_FREEZE_PROPOSAL.md` — statistiques.
- Rapports historiques — avertissements et chiffres datés.
- `tests/REPORT_A0_WRITER_HARDENING.md` — présent rapport.

Aucune migration `0005`, `0006` ou `0007` n'a été modifiée. Aucun commit.

## 10. Tests réellement exécutés

```powershell
.\.venv\Scripts\python.exe -m pytest tests -q -rxX
# 672 passed in 28.09s

.\.venv\Scripts\python.exe -m pytest tests --collect-only -q
# 672 tests collected

.\.venv\Scripts\python.exe -m pytest tests -q --runxfail
# 672 passed in 29.37s

.\.venv\Scripts\python.exe -m pytest tests\integration\test_p0_candidates.py -q
# 55 passed in 6.33s

.\.venv\Scripts\python.exe -m pytest tests\unit\test_contracts_negative.py `
  tests\unit\test_contracts_schema_validity.py `
  tests\integration\test_contract_sql_parity.py -q
# 261 passed in 3.22s

.\.venv\Scripts\python.exe -m pytest `
  tests\integration\test_0007_contract_sql_alignment.py `
  tests\unit\test_contract_validation.py `
  tests\integration\test_contract_writer.py -q
# 47 passed in 6.68s

.\.venv\Scripts\python.exe -m pytest tests\integration\test_migration_manifest.py -q
# 2 passed in 0.02s

git diff --check
# exit 0 ; avertissements CRLF uniquement
```

## 11. Limites restantes

1. Aucun writer A1/A2 de production n'appelle encore le parcours.
2. `jsonschema` reste une dépendance de test ; A1/A2 n'ont pas de validateur de
   production approuvé.
3. Seuls `experiment` et `fee_schedule` sont couverts.
4. Un `INSERT` SQL direct peut contourner le writer.
5. Les règles métier non déclarées dans les contrats/le SQL ne sont pas
   inventées.
6. Aucune base réelle ; aucune preuve de concurrence, crash ou reprise.
7. Le registre dépend de la présence du dépôt `contracts/` à côté de `src/` ;
   un packaging installé séparément devra embarquer ces fichiers.
8. La baseline SHA-256 ne remplace pas Git ; les migrations restent non
   suivies dans l'état observé.
9. Aucun gel, aucun commit.

## 12. Recommandation pour A5

Le dépôt est prêt pour un nouvel audit A5 ciblé sur :

- le refus d'une connexion FK OFF/RT OFF/isolation non nulle/transaction
  active ;
- le registre approuvé et le refus d'un schéma `9.9.9` injecté ;
- les erreurs `version` absente, `ContractSpecError` et
  `ContractValidatorError` avec cause ;
- l'absence de ligne après chaque refus ;
- l'atomicité limitée à un appel writer et l'absence d'atomicité de groupe ;
- la baseline SHA-256 et la limite de preuve Git.

Le branchement à un writer A1/A2 réel et le choix de la dépendance de
validation restent à faire. Aucun gel n'est prononcé.
