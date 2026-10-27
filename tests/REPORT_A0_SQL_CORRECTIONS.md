# Rapport A0 — correction des anomalies SQL après audit A5

> **RAPPORT HISTORIQUE.** Les chiffres `472/470/2` et `137/2` ci-dessous
> décrivent l'état antérieur à B-04 et à la préparation P0. Ils ne sont pas
> l'état courant. Voir `tests/README.md` et
> `tests/REPORT_A0_P0_REAUDIT_FIXES.md` pour les mesures actuelles.

**Date :** 2026-10-27  
**Auteur :** A0 — architecte / intégrateur  
**Schéma :** `schemas/initial_db_schema.sql` version `0.3`,
`PRAGMA user_version = 3`  
**Statut :** corrections appliquées, **aucun commit**, **aucun gel prononcé**.

## 1. Périmètre et méthode

L'audit A5 (`tests/REPORT_A5_CONTRACTS.md`) listait 24 anomalies. La mission A0
était de corriger en priorité A5-01, A5-02, A5-03, A5-08, A5-13 et A5-15, puis
d'examiner toutes les autres.

Pour chaque anomalie :

1. le comportement fautif a été reproduit par un test existant ou ajouté ;
2. la contrainte manquante a été identifiée ;
3. la correction la plus déclarative possible a été appliquée ;
4. les effets sur les tables, vues, triggers et FK ont été vérifiés ;
5. la cohérence avec les contrats JSON a été contrôlée ;
6. le test `xfail` a été retiré lorsque le comportement est désormais correct,
   sans supprimer ni affaiblir d'assertion.

Aucun test réseau Polymarket n'a été exécuté. Aucun module `core/`, aucun
simulateur A2 et aucune collecte réseau n'ont été ajoutés.

## 2. Résultats réels des tests

| Exécution | Commande | Résultat |
|---|---|---|
| Baseline A5 | `python -m pytest tests -q -rxX` | 450 collectés, 435 réussis, 15 xfail stricts, 0 échec |
| Après corrections | `python -m pytest tests -q -rxX` | **472 collectés, 470 réussis, 2 xfail documentés, 0 échec inattendu** |
| Vérification des xfail restants | `pytest tests/unit/test_contracts_negative.py -q --runxfail` | 137 réussis, **2 échouent** : les deux tests A5-06, qui ne peuvent pas être exprimés en JSON Schema |
| Intégrité SQLite | base fichier seedée, WAL, fermeture/réouverture | `integrity_check = ok`, `foreign_key_check` vide, `user_version = 3` |
| Propreté du diff | `git diff --check` | aucune erreur (avertissement CRLF global uniquement) |

Les 22 tests ajoutés couvrent les chemins indirects et les corrections qui
n'avaient pas encore de test : `INSERT OR REPLACE`, activation de
`recursive_triggers`, append-only des 8 tables d'événements, FK composite des
ordres, snapshot d'ordre/estimation, intention d'estimation, cohérence des
hashes, persistance des champs optionnels, `random_seed`, conversion de
présentation, unicité des outcomes, conversion et token gagnant de résolution.

## 3. Fichiers modifiés

- `schemas/initial_db_schema.sql` — corrections A5, version `0.3` ;
- `contracts/execution.schema.json` — A5-07 : résultat `rejected` avec
  `rejection_reason` obligatoire et non nul ;
- `ARCHITECTURE.md` — version `0.3`, invariants 10 à 16, règles sémantiques
  §5.1 et états d'ordre §5.2 ;
- `DECISIONS.md` — D-025 mis à jour vers `0.3`, ajout de D-026 (proposé) ;
- `contracts/CONTRACT_FREEZE_PROPOSAL.md` — versions et enregistrement des
  vérifications du 2026-10-27 ;
- `tests/integration/test_schema_sqlite.py` — attentes de triggers et de
  `user_version`, retrait des `xfail` corrigés, 22 tests ajoutés ;
- `tests/integration/test_contract_sql_parity.py` — retrait des `xfail`
  A5-08 à A5-11, colonnes de parité renforcées ;
- `tests/unit/test_contracts_negative.py` — retrait du `xfail` A5-07 ;
- `tests/labtest/sqlfixtures.py` — `intent_id`, notes, hashes, seed et devise
  de présentation paramétrables ;
- `tests/README.md` — version et compte de tests mis à jour.

## 4. Tableau de statut des anomalies A5

| ID | Sévérité | Statut | Correction appliquée | Test reproductible |
|---|---|---|---|---|
| A5-01 | Critique | **CORRIGÉ** | 16 triggers `BEFORE UPDATE/DELETE` sur `market_events` et les 7 tables de détail. `INSERT OR REPLACE` déclenche le trigger DELETE avec `recursive_triggers=ON`. | `test_market_events_are_append_only`, `test_every_event_table_is_append_only` (8 tables), `test_replace_cannot_bypass_event_append_only` |
| A5-02 | Critique | **CORRIGÉ** | `UNIQUE(market_id, token_id)` sur `market_tokens` ; FK composite sur `market_events` et `simulated_orders` ; trigger token gagnant ↔ marché de résolution. | `test_event_token_must_belong_to_its_market`, `test_order_token_must_belong_to_its_market`, `test_resolution_winning_token_must_belong_to_the_market` |
| A5-03 | Élevée | **CORRIGÉ** | Triggers vérifiant que `book_snapshot_event_id` existe dans `book_snapshots` et correspond au marché/token de l'ordre, de l'estimation ou du fill. | `test_fill_book_reference_must_be_a_snapshot`, `test_order_book_snapshot_must_match_market_and_token`, `test_estimate_book_snapshot_must_be_a_snapshot_of_the_order` |
| A5-04 | Faible | **CORRIGÉ** | `substr(tx_hash,3) NOT GLOB '*[^0-9a-fA-F]*'` sur `trade_events` et `trader_activity_events`. | `test_tx_hash_hexadecimal_is_enforced` |
| A5-05 | Moyenne | **NON CORRIGÉ — barrière A1** | Le contrat décrit déjà l'ordre canonique ; JSON Schema ne peut pas l'imposer. A1 doit trier ou rejeter. | `test_json_schema_does_not_enforce_book_order` (caractérisation) |
| A5-06 | Moyenne | **NON CORRIGÉ — limite JSON Schema** | Comparaison de deux champs impossible en JSON Schema. Le SQL refuse déjà la chronologie invalide. A1/A2 doivent valider avant insertion. | 2 `xfail` conservés et documentés |
| A5-07 | Faible | **CORRIGÉ** | `execution_result` : `rejected` exige `rejection_reason` non nul. | `test_rejected_result_requires_rejection_reason` |
| A5-08 | Critique | **CORRIGÉ** | `simulated_orders.intent_id NOT NULL UNIQUE` ; `execution_estimates.intent_id NOT NULL` + FK composite `(order_id, intent_id)`. Cardinalité V1 : 1 intention → 0..1 ordre. | `test_intent_id_is_persisted_somewhere`, `test_estimate_intent_must_match_its_order`, `test_an_intent_cannot_be_reused_by_another_order`, `test_execution_tables_carry_schema_version` |
| A5-09 | Moyenne | **CORRIGÉ** | `schema_version` ajouté à `simulated_orders`, `execution_estimates`, `simulated_fills`. | `test_execution_tables_carry_schema_version`, parité |
| A5-10 | Moyenne | **CORRIGÉ** | `schema_version` ajouté à `experiments` et `fee_schedules`. | `test_configuration_tables_carry_schema_version`, parité |
| A5-11 | Moyenne | **CORRIGÉ** | `book_hash_before` / `book_hash_after` sur `book_delta_changes`, contraints identiques par événement. | `test_book_delta_hashes_are_persisted`, `test_book_delta_hashes_must_agree_within_an_event` |
| A5-12 | Faible | **CORRIGÉ** | CHECK de format `accounting_unit` (2 à 32 caractères, lettre initiale) sur les événements, ordres, estimations, fills, expériences et barèmes. | `test_sql_enforces_accounting_unit_pattern` |
| A5-13 | Élevée | **CORRIGÉ** | `trader_activity` ajouté aux types qui exigent `market_id`. | `test_trader_activity_requires_market_id_in_sql` |
| A5-14 | Faible | **CORRIGÉ** | Équivalence `(ref IS NULL) = (sha IS NULL)` et SHA-256 hexadécimal minuscule de 64 caractères. | `test_raw_payload_hash_requires_reference_in_sql` |
| A5-15 | Élevée | **CORRIGÉ** | Trigger refusant un fill sur un ordre `proposed`, `rejected` ou `expired`. | `test_rejected_order_cannot_have_fills` |
| A5-16 | Moyenne | **NON CORRIGÉ — barrière A2** | Somme nulle, `CASH >= 0`, quantité `>= 0` restent détectés par les vues d'audit, pas par contrainte déclarative. A2 doit les consulter et refuser la publication. | `test_ledger_invariants.py` (caractérisation) |
| A5-17 | Faible | **CORRIGÉ** | `notes` sur trade/activité ; `rationale` et `tags_json` sur les ordres. | `test_optional_trade_and_intent_fields_are_persisted`, parité |
| A5-18 | Faible | **CORRIGÉ** | CHECK d'égalité entre `experiments.random_seed` et `execution_assumptions_json.$.random_seed`. | `test_experiment_random_seed_must_match_execution_assumptions` |
| A5-19 | Faible | **CORRIGÉ** | En-tête `0.3`, `PRAGMA user_version = 3`, `schema_migrations` vide documentée. | `test_user_version_is_set`, `test_schema_migrations_table_exists_but_is_not_seeded` |
| A5-20 | Faible | **PARTIELLEMENT CORRIGÉ** | Trigger d'unicité `token_id` / `outcome_index` et de forme des outcomes. La validation complète contre le contrat reste à A1. | `test_metadata_outcomes_must_be_unique` |
| A5-21 | Faible | **PARTIELLEMENT CORRIGÉ** | CHECK expérience : conversion obligatoire si devise de présentation ≠ unité comptable. Trigger résolution : conversion obligatoire si actif de règlement ≠ collatéral. Le contenu et le taux restent à A1/A2 (Q-009). | `test_experiment_requires_conversion_if_presentation_differs`, `test_resolution_requires_conversion_when_assets_differ` |
| A5-22 | Faible | **NON CORRIGÉ — barrière A2** | Cohérence estimate/résultat rejeté, transitions d'état et niveaux d'une estimation rejetée restent validées par A2. | À ajouter avec A2 |
| A5-23 | Faible | **NON CORRIGÉ — barrière A1/A2** | Les blobs JSON restent validés syntaxiquement, puis contre les contrats avant écriture. | À ajouter avec A1/A2 |
| A5-24 | Faible | **DOCUMENTÉ** | Mapping `proposed`/`accepted` vs statuts de `execution_result` et machine d'états décrits dans `ARCHITECTURE.md` §5.2. | Revue d'architecture |

## 5. Décisions d'architecture à approuver

1. **Cardinalité intention → ordre** : une intention produit au plus un ordre
   en V1 ; l'ordre porte l'intention, y compris rejetée. Une même intention ne
   peut pas être réutilisée. Cette règle bloque le fractionnement d'une
   intention en plusieurs ordres. Si A2 a besoin de ce fractionnement, la FK
   unique devra être remplacée par une table `order_intents` avant le gel.
2. **Hashes de delta** : stockés sur chaque ligne de `book_delta_changes` avec
   un trigger d'égalité, au lieu d'une table d'en-tête. Moins normalisé, mais
   aucune table supplémentaire. Une migration vers une table d'en-tête reste
   possible sans changer le contrat.
3. **`schema_version` par défaut `1.0.0`** : permet d'ajouter la colonne sans
   réécrire les fixtures et les données existantes. Toute future version devra
   être explicite ; la valeur par défaut ne doit pas servir à masquer un
   document d'une autre version.
4. **A5-06 reste `xfail`** : ce n'est pas un test masqué. Le comportement
   attendu (rejet d'une période inversée) est déjà garanti à la persistance
   SQL ; seule la validation JSON Schema reste impossible. A1/A2 doivent
   refuser le document avant insertion.
5. **A5-16 reste une barrière applicative** : une contrainte SQL de somme nulle
   par transaction exigerait un trigger différé ou une table de staging. Le
   choix V1 est de conserver les vues d'audit et d'obliger A2 à les vérifier
   dans la transaction de publication.

## 6. Limites et anomalies restantes

- A5-05, A5-06, A5-16, A5-22 et A5-23 restent des règles sémantiques. Elles
  sont documentées dans `ARCHITECTURE.md` §5.1 et devront être couvertes par
  les tests d'A1 et A2.
- A5-20 et A5-21 sont partiellement couvertes : le SQL impose l'unicité et la
  présence d'une conversion, pas la conformité complète ni le taux.
- Les triggers ne protègent pas `DROP TABLE`, `ALTER TABLE` ni une connexion
  ouverte sans `PRAGMA recursive_triggers = ON`. Ce sont des opérations
  d'administration ou de configuration de connexion, documentées dans l'en-tête
  du schéma et dans `ARCHITECTURE.md`.
- `schema_migrations` reste vide : le script est le schéma initial, pas un
  runner de migrations. Le runner devra enregistrer la version 3.
- Aucun test réseau n'a été exécuté ; les valeurs de frais et les règles de
  conversion restent non vérifiées.

## 7. Recommandation sur le gel

**Je ne prononce pas le gel.** Les anomalies SQL bloquantes listées par A5 sont
corrigées et la suite passe, mais le gel reste conditionné à :

1. l'approbation de D-026 et des cinq décisions du §5 ;
2. l'acceptation écrite des règles sémantiques §5.1 par A1 et A2 ;
3. la validation des critères d'acceptation A1/A2 de
   `contracts/CONTRACT_FREEZE_PROPOSAL.md` ;
4. l'autorisation explicite du propriétaire pour committer et geler.

Tant que ces conditions ne sont pas remplies, le schéma reste une proposition
`0.3` non gelée.
