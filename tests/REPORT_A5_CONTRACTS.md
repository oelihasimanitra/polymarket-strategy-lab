# Rapport A5 — Validation des contrats JSON et du schéma SQL

**Date :** 2026-10-27  
**Agent :** A5 — Validation et benchmark  
**Périmètre :** contrats `contracts/`, exemples `contracts/examples/`, schéma
`schemas/initial_db_schema.sql`, tests correspondants dans `tests/`.  
**Hors périmètre :** collecteur réseau, simulateur, ledger applicatif A2,
dashboard, benchmarks, `core/`.

Aucun contrat, aucun schéma et aucun fichier de production n'a été modifié.
Aucun commit n'a été créé.

> **Note A0 du 2026-10-27** — ce rapport est l'instantané de l'audit A5 avant
> correction. Les corrections SQL, le statut de chaque anomalie et les tests
> après correction sont dans `tests/REPORT_A0_SQL_CORRECTIONS.md`. Le schéma
> est passé en `0.3` ; les chiffres de la §1 décrivent l'état antérieur.

## 1. Résultat exécuté

Environnement réellement utilisé :

- Python `3.15.0`
- SQLite `3.53.4` (module standard `sqlite3`)
- pytest `9.1.1`
- jsonschema `4.26.0`

Commande exacte :

```powershell
.\.venv\Scripts\python.exe -m pytest tests -q -rxX
```

Résultat final :

```text
435 passed, 15 xfailed in 2.74s
```

- **450 tests collectés**
- **435 réussis**
- **15 échoués attendus** (`xfail(strict=True)`), correspondant à 15 anomalies
  documentées ci-dessous
- **0 échec inattendu**

Les `xfail` ne sont pas des succès. Ils prouvent qu'un invariant déclaré n'est
pas respecté ; ils passeront en `XPASS` (et casseront la suite, volontairement)
si le défaut est corrigé, ce qui forcera la mise à jour du test et du rapport.

### Détail par fichier

| Fichier | Tests |
|---|---:|
| `tests/unit/test_contracts_schema_validity.py` | 45 |
| `tests/unit/test_contracts_examples.py` | 74 |
| `tests/unit/test_contracts_negative.py` | 139 |
| `tests/unit/test_execution_assumptions_parity.py` | 25 |
| `tests/unit/test_contract_semantics.py` | 9 |
| `tests/integration/test_schema_sqlite.py` | 97 |
| `tests/integration/test_idempotence.py` | 12 |
| `tests/integration/test_contract_sql_parity.py` | 35 |
| `tests/accounting/test_ledger_invariants.py` | 14 |

### Vérifications A0 formalisées

Les vérifications du 2026-10-26 ont été rejouées indépendamment, sans utiliser
leurs résultats comme preuve :

- les 5 schémas passent `Draft202012Validator.check_schema` ;
- les 14 exemples sont valides et couverts ;
- les cas négatifs JSON sont rejoués (139 tests) ;
- le schéma SQL est recréé sur une base neuve : 26 tables, 7 vues, 13 triggers,
  18 index explicites, 26 tables `STRICT` ;
- `PRAGMA integrity_check` et `PRAGMA foreign_key_check` passent sur des données
  semées valides.

## 2. Fichiers créés

Aucun fichier existant n'a été modifié. Fichiers ajoutés :

```text
tests/README.md
tests/requirements-test.txt
tests/REPORT_A5_CONTRACTS.md
tests/conftest.py
tests/labtest/__init__.py
tests/labtest/contracts.py
tests/labtest/semantics.py
tests/labtest/sqlfixtures.py
tests/labtest/sqlschema.py
tests/unit/test_contracts_schema_validity.py
tests/unit/test_contracts_examples.py
tests/unit/test_contracts_negative.py
tests/unit/test_execution_assumptions_parity.py
tests/unit/test_contract_semantics.py
tests/integration/test_schema_sqlite.py
tests/integration/test_idempotence.py
tests/integration/test_contract_sql_parity.py
tests/accounting/test_ledger_invariants.py
```

## 3. Ce qui est réellement vérifié

### Contrats JSON

- Structure Draft 2020-12, `$id`, `title`, `additionalProperties: false` sur
  chaque objet, `$ref` locales uniquement.
- `schema_version` figé à `1.0.0` dans les cinq schémas.
- Aucun type `number` dans les contrats : tous les montants sont des entiers.
- Timestamps canoniques à six décimales et suffixe `Z`, identiques dans tous
  les schémas ; offsets et précisions variables rejetés.
- Les sept types d'événements, un seul payload typé par événement, champs
  obligatoires par type (`market_id`, `token_id`, `accounting_unit`).
- Prix dans `[0, 1 000 000]`, tailles strictement positives, flags de qualité
  uniques, couplage `raw_payload_ref` / `raw_payload_sha256`.
- `book_change` `REMOVE`/`ADD`/`REPLACE`, `trader_activity` `TRADE`,
  `market_metadata` (deux outcomes), résolution `RESOLVED`/`VOID`,
  `connection_status`.
- `order_intent`, `execution_assumptions`, `execution_estimate`, `fill`,
  `execution_result` : champs requis, rejets, états `accepted`/`partial`/
  `rejected` et `filled`/`partially_filled`/`rejected`/`expired`.
- Barème de frais : `verified` exige https et preuve de périmètre, `custom`
  exige une référence, `none` exige des taux nuls, bornes de taux et d'arrondi.
- Expérience : manifeste obligatoire hors `paper_live`, pas de short, limites de
  risque, statut de frais cohérent, hash de configuration.
- Hypothèse : faits / hypothèse / inconnues / biais, règles non exécutables.
- Arithmétique des exemples : notionnel = prix × taille, VWAP pondéré, frais
  `linear_min_price_1mp`, somme des niveaux consommés.
- Parité complète des deux définitions `execution_assumptions` après résolution
  des `$ref`, y compris les champs requis et les valeurs rejetées.

### Schéma SQL

- Création complète sur une base neuve, tables `STRICT`, `user_version`,
  triggers, index et vues attendus.
- Clés étrangères, restrictions de suppression, rejets des orphelins.
- CHECK de timestamps, d'énumérations, de prix, de tailles, de taux, de
  résolution, de gap de connexion, de snapshots et de postings comptables.
- Index uniques : `event_id`, `(source, source_event_id)`,
  `idempotency_key`, `(order_id, fill_index)`, `(ref_type, ref_id, kind)`,
  `(experiment_id, as_of_timestamp)`.
- Idempotence : double append, double fill, double transaction, double
  estimate, rejeu après fermeture/réouverture de la base.
- Triggers de type : un détail ne peut pas être rattaché à une enveloppe d'un
  autre `event_type`.
- Triggers d'immutabilité sur `simulated_fills`, `ledger_transactions` et
  `ledger_postings`.
- Grand livre : dépôt, achat, vente, settlement gagnant/perdant, frais en
  collatéral, frais en parts, reversal, somme nulle, cash, positions, vues
  `v_experiment_cash`, `v_experiment_positions`, `v_order_execution`,
  `v_ledger_anomalies`, `v_negative_cash`, `v_position_anomalies`,
  `v_experiment_latest_snapshot`.
- Parité JSON ↔ SQL : énumérations (`event_type`, `source`, `side`,
  `activity_type`, statuts, `fee_formula`, `fee_unit`, `rounding_rule`,
  `rejection_reason`, etc.) et présence des champs obligatoires.

## 4. Tests non exécutés

Ces catégories sont explicitement **non exécutées** et ne doivent pas être
présentées comme validées :

- `tests/unit/test_units_decimal.py` : `src/polymarket_lab/core/units.py`
  n'existe pas encore (D-017, propriétaire A1). Aucun test de `to_micros`,
  `canonical_timestamp` ou `deterministic_event_id`.
- Anti-look-ahead d'exécution : aucun `EventStore`, aucun manifeste
  applicatif, aucune stratégie. Le cutoff n'est pas testé à l'exécution.
  Seule la structure SQL du manifeste est vérifiée.
- Code de simulation A2 : fills partiels, latence, haircut, profondeur,
  carnet périmé, rejet pour liquidité insuffisante.
- Code du ledger A2 : `apply_fill`, `settle`, `reverse`, `reconcile` et
  application réelle des règles de frais.
- Benchmarks et audit de biais : aucun benchmark indépendant, aucune donnée
  réelle.
- Tests réseau Polymarket : aucun, conformément à la mission.
- Tests de reprise de migration : il n'existe pas encore de répertoire de
  migrations ; `schema_migrations` est vide.
- Tests de concurrence, WAL, performance, fuzzing, property-based testing,
  mutation testing.
- Compatibilité avec une autre version de Python/SQLite que celles exécutées.
- Validation des payloads bruts amont et des endpoints : hors périmètre A5 et
  non documentés par A1 à ce jour.

## 5. Anomalies détectées

Légende de sévérité :

- **Critique** : compromet la traçabilité, l'immutabilité ou l'intégrité
  multi-marchés ; bloque le gel.
- **Élevée** : contradiction directe contrat/SQL ou trou d'intégrité ; à
  corriger avant gel.
- **Moyenne** : décision de stockage ou de validation manquante ; à trancher
  avant gel ou à différer explicitement.
- **Faible** : contrôle plus faible que le contrat ; correction peu coûteuse.

Les identifiants `A5-xx` sont ceux des `xfail` ou des tests de
caractérisation.

| ID | Sévérité | Anomalie | Preuve | Correction proposée |
|---|---|---|---|---|
| A5-01 | Critique | `market_events` est déclaré append-only mais UPDATE/DELETE sont autorisés ; les tables de détail sont aussi modifiables. | `test_schema_sqlite.py::test_market_events_are_append_only` (xfail). En-tête SQL l. 30-33 ; aucun trigger sur `market_events` ni sur les tables de détail. | Triggers `BEFORE UPDATE/DELETE` sur `market_events` et les 7 tables de détail. Toute correction passe par un nouvel `event_id`. Test de rejeu. |
| A5-02 | Critique | Aucune contrainte ne garantit que `market_events.token_id` appartient à `market_events.market_id`. Un trade peut référencer le token d'un autre marché. | `test_event_token_must_belong_to_its_market` (xfail). FK indépendantes l. 250-251. | `UNIQUE(market_id, token_id)` sur `market_tokens` + FK composite `(market_id, token_id)` sur `market_events` et `simulated_orders`, ou trigger équivalent. |
| A5-08 | Critique | `intent_id` n'existe ni dans `simulated_orders` ni dans `execution_estimates`. `execution_estimate.intent_id` et `execution_result.intent_id` n'ont aucune colonne cible ; le lien `intent_id → order_id` n'est documenté nulle part. | `test_contract_sql_parity.py::test_intent_id_is_persisted_somewhere` (xfail). Contrats `execution.schema.json` l. 96, 356, 586. | Ajouter `intent_id TEXT NOT NULL UNIQUE` à `simulated_orders`, puis `intent_id` à `execution_estimates` (ou dériver via `order_id` et le documenter formellement). Migration + tests. |
| A5-03 | Élevée | `simulated_fills.book_snapshot_event_id` référence n'importe quel `market_event`, pas nécessairement un `book_snapshot`. Idem pour `simulated_orders` et `execution_estimates`. | `test_fill_book_reference_must_be_a_snapshot` (xfail). SQL l. 547. | Trigger vérifiant l'existence dans `book_snapshots`, ou FK vers une table d'en-tête `book_snapshot_events`. |
| A5-13 | Élevée | Le CHECK SQL omet `trader_activity` dans les types qui exigent `market_id`, alors que le contrat JSON l'exige. | `test_trader_activity_requires_market_id_in_sql` (xfail). Contrat l. 266-281 ; SQL l. 258. | Ajouter `'trader_activity'` à la liste du CHECK. |
| A5-15 | Élevée | Rien n'empêche un fill rattaché à un ordre rejeté, alors que `execution_result` interdit les fills pour `rejected`. | `test_rejected_order_cannot_have_fills` (xfail). | Trigger sur `simulated_fills` refusant les ordres `rejected`/`expired`/`proposed`, ou règle A2 explicite + test. |
| A5-09 | Moyenne | `simulated_orders` et `execution_estimates` n'ont pas de colonne `schema_version`. | `test_execution_tables_carry_schema_version` (xfail). | Ajouter la colonne aux tables qui persistent un contrat versionné, ou amender ARCHITECTURE §2.5 pour dire que seuls les documents JSON/événements la portent. |
| A5-10 | Moyenne | `experiments` et `fee_schedules` n'ont pas de `schema_version`, alors que `hypotheses` et `market_events` l'ont. | `test_configuration_tables_carry_schema_version` (xfail). | Même décision que A5-09. |
| A5-11 | Moyenne | `book_hash_before` et `book_hash_after` du contrat `book_delta` ne sont stockés nulle part. | `test_book_delta_hashes_are_persisted` (xfail). Contrat l. 616-629 ; SQL l. 317-327. | Table d'en-tête `book_delta_events` avec les deux hashes, ou suppression explicite de ces champs du contrat v1. |
| A5-06 | Moyenne | JSON Schema n'impose pas `effective_to > effective_from` ni `period.end_time > period.start_time`, alors que le SQL le fait. | `test_fee_schedule_effective_period_must_be_ordered` et `test_experiment_period_must_be_chronological` (xfail). | Validation sémantique obligatoire dans A1/A2 avant insertion, ou couche de post-validation documentée. JSON Schema seul ne peut pas comparer deux champs. |
| A5-05 | Moyenne | L'ordre canonique du carnet est décrit mais non validé : bids non triés ou prix dupliqués passent le schéma. | `test_contract_semantics.py::test_json_schema_does_not_enforce_book_order` (caractérisation). | A1 doit trier ou rejeter ; tests dédiés sur le normaliseur. Le contrat doit le dire explicitement. |
| A5-04 | Faible | Le CHECK SQL sur `tx_hash` ne vérifie que longueur et préfixe `0x`, pas l'hexadécimal ; `0x` + 64 `z` est accepté. | `test_tx_hash_hexadecimal_is_enforced` (xfail). SQL l. 286, 300. | CHECK `substr(tx_hash,3) NOT GLOB '*[^0-9a-fA-F]*'` sur les deux tables. |
| A5-07 | Faible | `execution_result.status=rejected` n'exige pas `rejection_reason`, alors que `simulated_orders` l'exige. | `test_rejected_result_requires_rejection_reason` (xfail). | Ajouter un `if/then` dans `execution.schema.json` : `rejected`/`expired` ⇒ `rejection_reason` requis et non nul. |
| A5-12 | Faible | `market_events.accounting_unit` n'a pas de CHECK de format ; `''` ou `1pUSD` sont acceptés. | `test_sql_enforces_accounting_unit_pattern` (xfail). Contrat l. 76. | CHECK de longueur + premier caractère + caractères autorisés, ou validation A1 documentée. |
| A5-14 | Faible | Le CHECK SQL n'impose que `ref ⇒ sha` ; le contrat impose aussi `sha ⇒ ref`. | `test_raw_payload_hash_requires_reference_in_sql` (xfail). Contrat l. 133-140 ; SQL l. 257. | `CHECK ((raw_payload_ref IS NULL) = (raw_payload_sha256 IS NULL))` + format hex. |

### Risques résiduels documentés mais non transformés en `xfail`

| ID | Sévérité | Constat | Conséquence |
|---|---|---|---|
| A5-16 | Moyenne | La somme nulle, `CASH >= 0` et quantité `>= 0` ne sont pas des contraintes SQL ; seules les vues d'audit les détectent. | `test_unbalanced_transaction_is_accepted_but_flagged`, `test_negative_cash_is_accepted_but_flagged`, `test_negative_position_is_accepted_but_flagged` prouvent que la base accepte l'écriture et que la vue la signale. A2 doit consulter ces vues et bloquer la publication ; à documenter comme barrière applicative. |
| A5-17 | Faible | Champs optionnels non persistés : `trade.notes`, `trader_activity.notes`, `order_intent.rationale`, `order_intent.tags`. | Perte d'information si le payload brut n'est pas conservé. Ajouter colonnes ou `metadata_json`, ou documenter la rétention. |
| A5-18 | Faible | `experiments.random_seed` duplique `execution_assumptions.random_seed` stocké dans `execution_assumptions_json`. Aucun CHECK d'égalité. | Deux valeurs peuvent diverger. Supprimer la colonne ou imposer l'égalité à l'écriture. |
| A5-19 | Faible | L'en-tête SQL dit « version 0.2 », `PRAGMA user_version = 1`, et `schema_migrations` est vide. | Ambiguïté de versionnement ; à aligner avant gel. |
| A5-20 | Faible | `market_metadata.outcomes` exige deux éléments mais pas l'unicité par `token_id`/`outcome_index` dans le JSON ; le SQL ne vérifie que la longueur du JSON. | `market_tokens` impose l'unicité en aval, mais l'événement de métadonnées peut être incohérent. A1 doit valider sémantiquement. |
| A5-21 | Faible | `capital.presentation_conversion` et `market_resolution.conversion_rule` sont décrits comme obligatoires si les actifs diffèrent, mais aucun des deux schémas ne l'impose. | Conversion implicite possible. A2 doit rejeter ; test à ajouter avec le module A2. |
| A5-22 | Faible | Un `execution_estimate` rejeté peut encore porter des `levels` ; un `rejection_reason` nul est accepté si la clé est présente. Un `execution_result` rejeté peut avoir un `estimate` incohérent. | Cohérence sémantique à porter par A2. |
| A5-23 | Faible | Les blobs JSON SQL (`quality_flags_json`, `levels_json`, `outcomes_json`, `assumptions_json`) ne sont validés que syntaxiquement (`json_valid`) ou par longueur. | Le SQL ne protège pas la forme ; A1/A2 doivent valider contre les contrats avant écriture. |
| A5-24 | Faible | `simulated_orders.status` contient `proposed` et `accepted` en plus des statuts de `execution_result`. | Mapping acceptable, mais à documenter. |

## 6. Corrections proposées

Aucune correction n'a été appliquée : les fichiers `contracts/`, `schemas/` et
`requirements.txt` sont hors du périmètre d'écriture d'A5.

### Schéma SQL 0.3 (proposition)

1. Triggers d'append-only sur `market_events` et les sept tables de détail.
2. `UNIQUE(market_id, token_id)` sur `market_tokens`, puis FK composite sur
   `market_events` et `simulated_orders`.
3. `intent_id TEXT NOT NULL UNIQUE` sur `simulated_orders` ; `intent_id` sur
   `execution_estimates` (ou règle `order_id = intent_id` documentée).
4. Trigger ou FK garantissant que `book_snapshot_event_id` pointe vers un
   `book_snapshot`.
5. Ajouter `'trader_activity'` au CHECK `market_id`.
6. Trigger interdisant les fills sur un ordre rejeté/expiré/proposé.
7. Décider et appliquer la règle `schema_version` sur les tables qui
   persistent un contrat versionné (ou amender ARCHITECTURE §2.5).
8. Stocker `book_hash_before`/`book_hash_after`, ou les retirer du contrat.
9. CHECK de format `tx_hash`, `accounting_unit`, `raw_payload_sha256` et du
   couplage ref/sha.
10. Aligner la version déclarée, `PRAGMA user_version` et `schema_migrations`.

### Contrats JSON (proposition)

1. `execution.schema.json` : exiger `rejection_reason` non nul pour
   `execution_result.status` `rejected`/`expired` (A5-07).
2. Documenter explicitement que l'ordre du carnet, les comparaisons
   `effective_to > effective_from`, `end_time > start_time`, les conversions de
   règlement et l'unicité sémantique des outcomes sont validés par A1/A2, pas
   par JSON Schema.
3. Si le gel veut rester purement structurel, ces règles doivent être listées
   comme « non définitives » dans les rapports qui utilisent le PnL.
4. Ajouter `tests/requirements-test.txt` à la documentation de build, et
   `jsonschema` à `requirements.txt` (D-018).

## 7. Blocages restant avant le gel

**Bloquants :**

- A5-01 (append-only non appliqué).
- A5-02 (token d'un autre marché accepté).
- A5-08 (`intent_id` absent).
- A5-03 (fill lié à un événement qui n'est pas un snapshot).
- A5-13 (market_id de `trader_activity`).
- A5-15 (fill sur ordre rejeté).
- Décision explicite sur A5-09/A5-10 (colonnes `schema_version`) et A5-11
  (hashes de carnet).
- Décision explicite sur les validations sémantiques A5-05/A5-06 et sur la
  barrière applicative A5-16 (somme nulle, cash, positions).

**Non bloquants mais à corriger ou diffuser :**

- A5-04, A5-07, A5-12, A5-14 (contrôles faibles, correction peu coûteuse).
- A5-17 à A5-24 (champs optionnels, versionnement, blobs JSON).
- Ajout de `jsonschema` aux dépendances de production de test (D-018).

## 8. Avis motivé sur le gel

**Je ne recommande pas de prononcer le gel global dans l'état actuel.**

Raisons :

1. Les contrats JSON sont globalement cohérents et bien testés sur leur forme.
   Les défauts JSON restants sont peu nombreux et surtout des limites de JSON
   Schema (comparaisons de champs, ordre de carnet, conversion conditionnelle).
   Un gel **des seules formes JSON** serait défendable si A0 écrit noir sur
   blanc que ces règles sémantiques sont à la charge d'A1/A2 et seront testées
   sur leurs modules. Mais A5-07 est corrigeable immédiatement et devrait
   l'être avant le gel.
2. Le schéma SQL, lui, n'est pas gelable : les anomalies A5-01, A5-02, A5-03,
   A5-08, A5-13 et A5-15 touchent précisément ce que le SQL est censé protéger
   (immuabilité, intégrité multi-marchés, traçabilité des intentions,
   cohérence des fills). Les corriger ne demande pas de refonte : ce sont des
   triggers, des FK composites et quelques colonnes.
3. Les contrats d'exécution ne peuvent pas être déclarés traçables tant que
   `intent_id` n'a pas de cible SQL et que `schema_version` n'est pas tranché.
4. La barrière comptable (somme nulle, cash/positions non négatifs) repose sur
   les vues, pas sur des contraintes. Ce n'est pas nécessairement un défaut de
   schéma, mais cela doit être une règle d'acceptation explicite d'A2, testée
   sur le module A2, pas seulement sur les vues.

**Proposition de séquence :**

1. A0 produit un schéma SQL `0.3` corrigeant les points bloquants.
2. A0 tranche A5-09/A5-10/A5-11 et écrit la règle de validation sémantique
   A5-05/A5-06/A5-16.
3. A0 applique la correction A5-07 à `execution.schema.json` (ou la diffère
   explicitement).
4. A5 relance la suite ; les 15 `xfail` doivent devenir des tests verts ou des
   tests retirés avec justification.
5. Le gel peut alors être prononcé, avec une liste datée des points différés
   (Q-001 à Q-009) et l'étiquette « non définitif » sur tout PnL affecté par
   les frais, conversions ou positions ouvertes.

**Ce que cette suite ne prouve pas :** elle valide la conformité des contrats
et du schéma à des invariants testés. Elle ne prouve ni la rentabilité, ni la
qualité des données Polymarket, ni la fidélité d'un backtest, ni le bon
fonctionnement du collecteur, du simulateur ou du ledger applicatif. Aucun test
réseau n'a été exécuté.

## 9. Reproductibilité

- Les tests sont déterministes : aucun tirage aléatoire, aucune horloge murale,
  aucun réseau.
- Les bases sont en mémoire ; le test de rejeu utilise `tmp_path`.
- Les schémas sont lus depuis `contracts/` et `schemas/` à chaque exécution :
  toute modification de contrat casse la suite.
- Les dépendances sont documentées dans `tests/requirements-test.txt` et
  `tests/README.md`.
- `jsonschema` n'est pas dans `requirements.txt` : en environnement propre,
  `pytest` échouera à l'import tant que la dépendance n'est pas installée.
  C'est une condition de reproductibilité, pas un défaut des tests.
