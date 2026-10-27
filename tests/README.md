# Tests A5 — contrats JSON et schéma SQL

Ce répertoire contient la validation indépendante des contrats `1.2.0`
candidats et du schéma SQLite base `0.3` migré en `0.4`, avec les migrations
candidates `0005`/`0006`/`0007`. Il ne contient ni collecteur, ni simulateur, ni code
de production : uniquement des tests, des fixtures de test et des oracles
indépendants.

Dernière exécution après fermeture des contournements du writer :
**744 tests collectés, 744 réussis, 0 xfail, 0 échec inattendu**.

## Dépendances

Testé avec :

- Python `3.15.0`
- SQLite `3.53.4` (via le module standard `sqlite3`)
- pytest `9.1.1`
- jsonschema `4.26.0`

Installation dans l'environnement virtuel du projet :

```powershell
.\.venv\Scripts\python.exe -m pip install -r tests\requirements-test.txt
```

`jsonschema` est déclaré dans `tests/requirements-test.txt` comme dépendance de
test (D-018). Il n'est pas une dépendance de production. `requirements.txt`
reste la liste de production non épinglée, à traiter par D-037.

## Exécution

Depuis la racine du dépôt :

```powershell
.\.venv\Scripts\python.exe -m pytest tests -q
```

Avec le détail des échecs attendus :

```powershell
.\.venv\Scripts\python.exe -m pytest tests -q -rxX
```

Sous-ensembles :

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit -q
.\.venv\Scripts\python.exe -m pytest tests\integration -q
.\.venv\Scripts\python.exe -m pytest tests\accounting -q
```

Aucun test n'envoie de requête réseau. Aucun test n'écrit dans `data/`,
`logs/` ou `reports/`. Les bases SQL sont en mémoire, sauf les tests de
migration/redémarrage qui utilisent un fichier temporaire fourni par pytest
(`tmp_path`).

## Organisation

| Fichier | Rôle | Tests collectés |
|---|---|---:|
| `unit/test_contracts_schema_validity.py` | structure des 5 schémas, conventions communes, extension chronologique | 47 |
| `unit/test_contracts_examples.py` | 15 exemples, couverture, arithmétique, fixturation | 78 |
| `unit/test_contracts_negative.py` | champs manquants, types, timestamps, prix, tailles, énumérations, suspensions V1, identité v2, RNG v2, chronologie A5-06 | 173 |
| `unit/test_contract_validation.py` | validateur applicatif commun : schéma puis extension, ordre schéma → chronologie → version, rejet des bornes inversées/égales | 12 |
| `unit/test_system_schema_validator.py` | validateur système : parité `jsonschema`, fail-closed (`multipleOf`, `$ref`, mots-clés), gel du schéma | 32 |
| `unit/test_execution_assumptions_parity.py` | égalité des deux définitions `execution_assumptions` | 25 |
| `unit/test_contract_semantics.py` | oracles carnet, notionnel, frais, VWAP | 9 |
| `unit/test_core_spec_vectors.py` | vecteurs d'or to_micros, event_id, config_hash, RNG stable | 7 |
| `integration/test_schema_sqlite.py` | création, tables, vues, triggers, index, FK, CHECK, STRICT | 119 |
| `integration/test_connection_policy.py` | fabrique SQLite, pragmas, WAL, lecture seule, append-only, connexions directes | 23 |
| `integration/test_consolidation_0004.py` | migration 0.3→0.4, préservation, préflight, runner, nouveaux invariants | 20 |
| `integration/test_p0_candidates.py` | candidats 0005/0006, identité v2, C-01/C-02/C-03, provenance des conversions, runner 5→6, comptages, vecteurs | 55 |
| `integration/test_0007_contract_sql_alignment.py` | migration 0.7, préflight, préservation, défauts 1.2.0, fin obligatoire hors paper_live, sauvegarde/restauration | 8 |
| `integration/test_contract_writer.py` | writer commun : approbation intrinsèque, immutabilité, parcours test séparé, connexion, pragmas, validation, version, transaction, relecture, erreurs SQL | 58 |
| `integration/test_migration_manifest.py` | manifeste explicite, couverture exacte, empreinte épinglée, détection de modification, non-migration | 11 |
| `integration/test_idempotence.py` | doublons, clés uniques, rejeu après redémarrage | 12 |
| `integration/test_contract_sql_parity.py` | énumérations, champs contrat ↔ SQL, chronologie et nullité JSON ↔ SQL | 41 |
| `accounting/test_ledger_invariants.py` | partie double, cash, positions, frais, settlement, reversal, vues d'audit | 14 |

Les helpers sont dans `tests/labtest/` :

- `contracts.py` : chargement, résolution locale des `$ref`, conventions ;
- `semantics.py` : oracles indépendants (arithmétique, ordre du carnet) ;
- `sqlfixtures.py` : lignes SQL valides et scénarios comptables ;
- `sqlschema.py` : introspection du schéma et des CHECK `IN (...)`.

## Ce que les tests couvrent

- Validité Draft 2020-12 des cinq schémas et stricte (`additionalProperties:
  false`) de chaque objet.
- Tous les exemples positifs ; les cas négatifs par mutation d'un exemple
  valide.
- Les sept types d'événements et l'exclusivité de leur payload.
- Les timestamps UTC canoniques à six décimales, côté JSON et côté SQL.
- La chronologie A5-06 : période valide, inversée, bornes égales, fin nulle,
  fin absente selon le caractère requis du champ, formats non canoniques ; et
  la parité JSON ↔ SQL sur les cas couverts.
- Les montants en micro-unités, l'absence de `number`/`REAL` monétaire, les
  bornes de prix et les tailles strictement positives.
- Les règles conditionnelles : `RESOLVED`/`VOID`, `TRADE`, `REMOVE`/`ADD`,
  `accepted`/`partial`/`rejected`, `filled`/`rejected`,
  `verified`/`provisional`/`unverified`.
- La parité des deux définitions `execution_assumptions`.
- La cohérence des énumérations et la présence des champs obligatoires entre
  contrats JSON et SQL.
- La création du schéma sur une base neuve, les FK, CHECK, index uniques,
  tables STRICT, triggers de type et d'immutabilité.
- Les connexions SQLite : `foreign_keys`, `recursive_triggers`, WAL obligatoire
  en écriture fichier, `synchronous`, lecture seule `mode=ro`/`query_only`,
  transactions explicites et refus de `INSERT OR REPLACE` sur l'append-only.
- Le test statique AST des connexions directes dans `src/` et `scripts/`.
- L'idempotence par clé unique et le rejeu après fermeture/réouverture.
- Les invariants comptables observables par les vues, y compris les cas
  d'anomalie volontairement insérés.
- Les candidats `0005`/`0006`/`0007` sur bases temporaires : backfill legacy sans
  recalcul, index d'identité v2, monotonie/cycles de remplacement (C-01),
  horloge injectée et refus d'antidatage (C-02), seal obligatoire (C-03),
  refus de `INSERT OR REPLACE` même avec `recursive_triggers=OFF` sur les
  remplacements, manifestes, ledger et conversions, unicité du ledger et
  provenance des conversions par expérience, avec `kind='settlement'` exigé.
- La portée et la normalisation des remplacements, les parcours réels du
  runner `5→0006` et `6→0007` (sauvegarde, journal, comptages), l'échec
  préflight et l'échec post-commit simulé.
- Le validateur applicatif `validate_contract` : schéma standard puis extension
  chronologique, avec rejet des périodes inversées et des bornes égales.
- Le parcours writer `write_experiment`/`write_fee_schedule` : registre de
  schémas approuvés rechargé à chaque écriture, validateur système, schéma gelé,
  refus des connexions FK OFF / `recursive_triggers` OFF /
  `ignore_check_constraints` ON / `row_factory` falsifié / transaction active,
  validation complète, version explicite, transaction et relecture de la ligne
  persistée ; aucune ligne sur validation refusée, erreurs catégorisées.
- Le parcours de test séparé `contract_writer_testing` : schémas personnalisés
  exécutés uniquement par une API explicitement nommée, jamais par le writer
  normal.
- Le validateur système : parité avec `jsonschema` sur les cas couverts des
  contrats approuvés, refus fail-closed des mots-clés non supportés, refus de
  `multipleOf`, validation des cibles `$ref` et détection des cycles à la
  construction.
- Les erreurs `ContractSchemaUnreadableError` et `ContractSchemaMismatchError`,
  leur normalisation en `ContractApprovalError` et l'absence de ligne.
- La position de la vérification finale d'approbation : dans la transaction,
  après `BEGIN IMMEDIATE`, avant l'INSERT.
- La baseline SHA-256 des migrations : format explicite, couverture exacte,
  empreinte du manifeste épinglée, détection d’un fichier modifié ou ajouté et
  absence de traitement comme migration.
- Les vecteurs v2 : canonical JSON, manifeste vide/avec remplacement,
  `event_id`, `intent_id`, RNG v2.

## Limites explicites

- **Chronologie A5-06** : la comparaison croisée est portée par l'extension
  normative `x-polymarket-chronological-order`, déclarée dans
  `fee_schedule.schema.json` et `experiment.schema.json`. Un validateur JSON
  Schema standard l'ignore ; le point d'entrée applicatif
  `polymarket_lab.validation.contracts.validate_contract` applique le schéma
  fourni puis l'extension. Le writer commun
  `polymarket_lab.storage.contract_writer` recharge le registre, construit son
  validateur système et applique le parcours complet avant insertion ; il n'est
  pas encore appelé par un writer A1/A2 de production. Le validateur système
  est un sous-ensemble fail-closed, pas JSON Schema complet (option A/B non
  tranchée).
  Un `INSERT` SQL direct peut toujours le contourner. Voir
  `tests/REPORT_A0_A5_06_FIX.md`, `tests/REPORT_A0_CONTRACT_SQL_ALIGNMENT.md`
  et `WRITER_INTEGRATION.md`.
- **Validateur système** : `multipleOf` est refusé à la construction ; les
  `$ref` valides doivent être locales, pointer vers un schéma objet et ne pas
  former de cycle. Les schémas récursifs valides en JSON Schema sont donc
  refusés. Voir `tests/REPORT_A0_FINAL_CANDIDATE_FIXES.md`.
- Le writer ne couvre que `experiment` et `fee_schedule` ; les autres
  documents n'ont pas encore de parcours d'écriture commun.
- Les tests ne couvrent pas `core/units.py`, `core/time.py`, `core/ids.py` :
  ces modules n'existent pas encore (A1, D-017).
- Les tests ne couvrent pas le code de simulation/ledger d'A2, ni
  l'anti-look-ahead d'exécution, ni les benchmarks : hors périmètre de cette
  mission et non exécutés.
- Les tests ne prouvent aucune rentabilité, aucun endpoint Polymarket et aucun
  barème réel. Les exemples restent fictifs et le barème d'exemple reste
  `unverified`.
- JSON Schema standard ne peut pas comparer deux champs (ordre temporel,
  devise de règlement vs unité comptable) ni imposer l'ordre d'un carnet.
  A5-06 est couvert par l'extension chronologique et son validateur
  sémantique ; les autres règles restent à valider par A1/A2 et à tester sur
  leurs modules.
- Le test A5 des frais en parts est conservé mais **différé** : en V1,
  `outcome_token` est suspendu (Q-011) et une transaction `kind='fee'` séparée
  sur un fill est refusée (D-034). Le scénario complet sera réactivé si Q-011
  est tranchée, dans la transaction unique du fill.
- `0005`, `0006` et `0007` sont des **candidats non approuvés** : les tests
  prouvent leur exécution sur des bases temporaires, pas leur application à la
  base de travail ni une migration de production.
- C-02 : SQL impose `visible_from = max(old.received, new.received, created_at)`
  et `created_at >= max(received)` ; il ne peut pas prouver qu'une horloge
  murale est saine pour un accès SQL direct. La couche de stockage et son
  horloge injectée sont testées séparément ; aucun écrivain d'événements
  complet n'existe encore côté A1.
- C-03 : les tables brutes `manifest_events`/`manifest_replacements` restent
  lisibles par un `SELECT` direct privilégié ; seules les vues as-of
  (`v_manifest_event_visibility`) et les lectures applicatives exigent le seal.
- Les campagnes A5 antérieures (48 PASS/3 PARTIEL et ré-audit 5 PASS/2 PARTIEL/
  1 FAIL) sont **historiques** ; voir `REPORT_A5_P0_AUDIT.md` et
  `REPORT_A5_P0_REAUDIT.md`. Les corrections et l'état courant sont dans
  `REPORT_A0_P0_REAUDIT_FIXES.md`, `REPORT_A0_A5_06_FIX.md` et
  `REPORT_A0_CONTRACT_SQL_ALIGNMENT.md`.

## Contrôles manuels vs tests automatisés (2026-10-27)

Les lignes « manuel » sont des sondes exécutées dans un répertoire temporaire
isolé, non committées. Les lignes « automatisé » sont dans
`tests/integration/test_p0_candidates.py` et sont exécutées par pytest.

| Contrôle | Type | Périmètre | Résultat |
|---|---|---|---:|
| C-01/C-02/C-03 | manuel | base synthétique migrée, chaînes, horloge, seal | 19/19 PASS |
| Contraintes 0006 | manuel | ledger, conversions, `REPLACE`, provenance | 13/13 PASS |
| Récupération runner | manuel | échec avant/après COMMIT, FK/RT, sauvegardes | 4/4 PASS |
| Suite complète | automatisé | `pytest tests -q -rxX` | 744 réussis, 0 xfail |
| P0 ciblé | automatisé | `pytest tests/integration/test_p0_candidates.py -q` | 55 réussis |
| `--runxfail` | automatisé | aucune anomalie A5-06 masquée | 744 réussis, 0 échoué |

Les sondes manuelles ont été exécutées le 2026-10-27 avec
`.\.venv\Scripts\python.exe` sur une base synthétique isolée dans
`%TEMP%\polymarket_p0_dry_run_20261027_1430` (scripts `probe_c01_c02_c03.py`,
`probe_0006.py`, `probe_recovery.py`, non committés). Elles ne remplacent pas
les tests committés ; elles ont servi à identifier les cas limites, désormais
couverts par les tests P0 lorsque possible.
