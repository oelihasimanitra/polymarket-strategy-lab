# ARCHITECTURE.md
# Polymarket Strategy Research Lab — Architecture technique

- **Version :** 0.5 — candidat P0 après alignement contrats/SQL (2026-10-27)
- **Statut :** proposition à valider par le propriétaire. Les contrats `1.2.0`
  et les migrations `0005`/`0006`/`0007` sont des **candidats non gelés et non
  exécutés**. Les références auditées restent les contrats `1.1.0` et le schéma
  SQL `0.4` ; elles ne sont pas modifiées en place.
- **Cible :** PC Windows, développement local, paper trading uniquement.
- **Principe :** monolithe modulaire ; les composants doivent rester séparables.

> Règle de lecture : ce document distingue les **décisions déjà validées** (D-001, D-002, D-008), les **décisions approuvées en principe** (D-009 à D-020, précisées par D-021 à D-024) et les **questions non résolues**. Aucun endpoint, champ Polymarket ou taux de frais n'est affirmé ici sans vérification documentaire. A0 n'a exécuté aucun test réseau.

## 1. Vue d'ensemble

```text
Polymarket public data / market WebSocket
                 |
                 v
        [1. Data Collectors]  -> payloads bruts + timestamps source/réception
                 |
                 v
   [2. Normalization & Quality] -> événements canoniques + incidents qualité
                 |
                 v
        [3. Local Data Store]  -> SQLite WAL, événements append-only,
                 |                manifestes de données, frais versionnés
       +---------+----------+
       |                    |
       v                    v
[4. Trader Analytics] [5. Market State]
       |                    |
       v                    |
[6. Strategy Registry]      |
       |                    |
       +---------+----------+
                 v
       [7. Simulation Engine] -> ordres, estimations, fills
                 |
                 v
       [8. Ledger & Metrics] -> journal double-entrée, snapshots, métriques
                 |
          +------+------+
          |             |
          v             v
 [9. Benchmark Engine] [10. Dashboard]
          |             |
          +------+------+
                 v
       [11. Validation & Reports]
```

Le flux de décision ne contient ni réseau, ni LLM, ni horloge murale implicite.
La simulation est une fonction déterministe de données horodatées, d'une
configuration figée et d'un générateur pseudo-aléatoire semé.

## 2. Conventions canoniques

### 2.1 Unités

| Domaine | Représentation | Échelle | Exemple |
|---|---|---|---|
| Cash, frais, PnL, coût | `INTEGER` en micro-unités de l'unité comptable | 1e-6 | `53600000` = 53.60 unités |
| Prix / probabilité | `INTEGER` en micro-probabilité | 1e-6 | `536000` = 0.536 |
| Taille / parts | `INTEGER` en micro-parts | 1e-6 | `100000000` = 100 parts |
| Taux de frais | `INTEGER` en micro-taux | 1e-6 | `10000` = 1 % |
| Ratio de haircut | `INTEGER` en points de base | 1e-4 | `1000` = 10 % |

L'échelle 1e-6 est retenue parce qu'elle couvre les décimales usuelles des
actifs à 6 décimales. **L'unité comptable reste explicite** (D-004, D-022) :
les tableaux parlent de micro-unités de l'unité comptable, jamais d'une devise
implicite. Selon la vérification documentaire du propriétaire (2026-10-26),
pUSD est présenté comme collatéral et le protocole règle en USDC natif ; ces
éléments sont portés séparément par le modèle de données.

Règles :

1. Le grand livre, les fills, les ordres et les snapshots ne contiennent **aucun
   `REAL`**. Les `REAL` sont réservés aux métriques statistiques dérivées.
2. Les noms de champs portent l'unité : `price_micros`, `size_micros`,
   `fee_amount_micros`, `liquidity_haircut_bps`. Un champ sans suffixe est
   ambigu et doit être refusé en revue.
3. Les conversions depuis les payloads sources utilisent `Decimal`, jamais
   `float`. L'arrondi est effectué à une frontière explicite et sa règle est
   enregistrée (`rounding_rule`, `rounding_increment_micros`).
4. La borne de prix `[0, 1]` est une hypothèse de marché. Elle doit être
   confirmée dans la documentation officielle avant toute collecte réseau.

### 2.2 Temps

- Format unique : `YYYY-MM-DDTHH:MM:SS.ffffffZ`, UTC, six décimales.
  Un offset (`+00:00`), une date locale ou une précision variable sont refusés.
- `source_timestamp` : horodatage de la source (échange / API).
- `received_timestamp` : horodatage de réception locale, en UTC.
- `ingested_at` : horodatage d'écriture en base ; il sert au diagnostic, pas à
  la décision.
- `received_monotonic_ns` : optionnel, horloge monotone du processus. Il n'est
  comparable ni entre processus, ni après redémarrage ; il ne doit jamais être
  persisté comme temps de marché.
- Une dérive d'horloge peut rendre `received_timestamp < source_timestamp`.
  Elle est signalée par `clock_skew` et **jamais corrigée silencieusement**.
- L'ordre de rejeu déterministe est `(source_timestamp, received_timestamp,
  event_id)`. `sequence_number` est opaque : il ne sert qu'à détecter les trous
  d'un même flux, jamais à ordonner deux flux.

### 2.3 Identifiants et idempotence

- `event_id` est **déterministe** pour un enregistrement source donné.
  Formule 1.2.0 (`event-id/v2`) : `evt_` + 32 premiers hex de
  `SHA-256(canonical_json([...]))`, avec
  `["polymarket-lab/event-id/v2", source, anchor, event_type, market_id,
  token_id, source_timestamp, normalizer_version]` et
  `anchor = source_event_id` si présent, sinon `raw_payload_sha256`.
  `event_identity_version` vaut `v2` pour un document 1.2.0. Les événements
  legacy v1 restent lisibles sans recalcul ; les lignes de version inconnue
  restent `NULL`.
- `(source, source_event_id)` est unique lorsqu'il existe. Un redémarrage ou une
  reconnexion ne doit pas créer un doublon.
- Unicité v2 : `(source, source_event_id, event_type, normalizer_version)` pour
  un ancrage `source_event_id` ; trois index de repli couvrent
  `(source, raw_payload_sha256, event_type, normalizer_version,
  source_timestamp, market_id?, token_id?)` avec token, marché seul ou sans
  marché. Un reparse exige un bump de `normalizer_version`. L'index legacy v1
  reste partiel et ne garantit rien rétroactivement pour les replis raw.
- Les doublons **inter-sources** (même trade vu par REST et WebSocket) ne sont
  pas garantis par cette contrainte. Ils doivent être détectés et signalés
  (`cross_source_duplicate`), pas fusionnés arbitrairement.
- Chaque ordre porte une `idempotency_key` unique par expérience.
- Chaque fill est unique par `(order_id, fill_index)`.
- Chaque transaction du grand livre porte une `idempotency_key` unique. Le
  schéma 0.4 la contraint globalement avec `(ref_type, ref_id, kind)` ; le
  candidat 0.6 isole les deux unicité par expérience :
  `(experiment_id, idempotency_key)` et
  `(experiment_id, ref_type, ref_id, kind)`.

### 2.3.1 Définitions normatives de `core/` (D-028)

```text
canonical_json(x) = json.dumps(x, sort_keys=True, separators=(",", ":"),
                               ensure_ascii=False, allow_nan=False).encode("utf-8")
```

`canonical-json/v1` est UTF-8 sans BOM, clés ASCII pour les structures hachées,
entiers uniquement, refus des `float`/`NaN`/`Infinity`, refus des clés
dupliquées (`object_pairs_hook`) et des valeurs non finies. `manifest/v2` et
`config/v2` impliquent `canonical-json/v1`.

**`to_micros(value, unit_decimals, *, rounding="half_even") -> int`**
- Accepte `Decimal`, `int`, `str` ; refuse `float`, `bool`, `NaN`, `Infinity`.
- `unit_decimals` dans `[0, 18]`.
- `scaled = Decimal(value) * 10**unit_decimals` ; si non entier, rejet : on ne
  cache pas une précision que l'unité ne possède pas.
- `micros = scaled * 10**(6-unit_decimals)` ; arrondi explicite si nécessaire.
- Résultat int64 ; les bornes métier sont vérifiées par l'appelant.

**`base_units_to_micros(raw_units: int, unit_decimals: int) -> int`** traite
les entiers natifs de source : exact si `unit_decimals <= 6`, arrondi explicite
si `unit_decimals > 6`. Aucun `float` n'est accepté.

**`canonical_timestamp(dt)`** exige un `datetime` aware en UTC
(`utcoffset() == 0`), refuse un datetime naïf ou un offset non UTC, et retourne
`YYYY-MM-DDTHH:MM:SS.ffffffZ`. Un adaptateur qui reçoit un offset le convertit
explicitement et journalise le fuseau source.

**`deterministic_event_id` (v2)** : identité canonique
`["polymarket-lab/event-id/v2", source, anchor, event_type, market_id,
token_id, canonical_timestamp(source_timestamp), normalizer_version]`, avec
`anchor = source_event_id` prioritaire, sinon `raw_payload_sha256` (64 hex
minuscules) obligatoire. Résultat : `evt_` + 32 premiers hex du SHA-256. A1
vérifie les collisions ; un identifiant existant avec une autre identité est
une erreur. `event-id/v1` reste archivé pour les lignes legacy.

**`manifest_hash` (v2)** : SHA-256 du canonical JSON de
`{"header": ..., "event_ids": [...], "replacements": [...]}`. Le header contient
`hash_version`, `canonical_json_version`, `manifest_id`,
`cutoff_received_timestamp`, `filters` (sources, market_ids, token_ids,
event_types triés, `notes`), `event_count`, `replacement_count`,
`event_id_algorithm`, `schema_versions` et `source_classes`. `event_ids` et
`replacements` sont triés et sans doublon ; un remplacement est
`[old_event_id, new_event_id, visible_from_received_timestamp]`. Retourne 64
hex, stocké dans `data_manifests.sha256`. Le hash fige l'ensemble, pas l'ordre
de rejeu. Tout manifeste lisible exige un `manifest_seals` valide.

**`config_hash` (v2)** : SHA-256 de la projection immuable stockée dans
`experiments.experiment_config_json`, sans `config_hash`, `status`,
`created_at`, `completed_at` ; `code_version` et `config_hash_version` sont
inclus. Retourne `sha256:<64 hex>`. Les lignes legacy portent
`config_hash_version='legacy/v1'` et aucun document n'est inventé.

Les détails et vecteurs d'or sont testés par A1 et A5 ; A2 relit
`core/units.py`.

### 2.4 Devise, unité comptable, actif de règlement

Trois notions distinctes, jamais confondues :

| Notion | Champ / support | Rôle |
|---|---|---|
| Actif de collatéral | `market_metadata.collateral_asset` + `collateral_decimals` | Actif effectivement utilisé par le marché. pUSD selon la vérification documentaire du propriétaire (2026-10-26), à confirmer par marché. |
| Unité comptable | `experiments.accounting_unit`, `market_events.accounting_unit`, colonnes `accounting_unit` du ledger | Unité de tous les montants du ledger ; une seule par expérience. |
| Actif de règlement | `market_metadata.settlement_asset`, `market_resolution.settlement_asset` | Actif payé à la résolution. USDC natif selon la documentation actuelle, à confirmer par marché. |
| Devise de présentation | `experiments.presentation_currency`, config `reporting.presentation_currency` | Affichage uniquement ; n'affecte jamais le ledger. |

Règles :

- Aucune conversion implicite, y compris 1:1 entre pUSD et USDC.
- Provenance (D-029) : sur un événement de marché, `accounting_unit` est l'unité
  du notionnel dérivé et doit égaler le collatéral du marché à
  `received_timestamp` ; si la métadonnée manque, A1 rejette avec
  `metadata_missing`, sans valeur par défaut. Sur ordre, estimation, fill et
  posting, elle doit être exactement celle de l'expérience. Le SQL (0.4, puis
  candidats 0.5/0.6/0.7) ajoute des triggers d'égalité ; A1/A2 ne dupliquent
  pas la règle.
- Si l'unité comptable diffère de l'actif de règlement, l'événement de
  résolution porte une `conversion_rule` sourcée, datée et versionnée
  (`verified`, `provisional` ou `unverified`).
- Si la devise de présentation diffère de l'unité comptable, la conversion est
  une règle de reporting séparée ; le ledger n'est jamais réécrit.
- Un résultat net n'est définitif que si les frais **et** les conversions
  utilisées sont vérifiés.
- Aucune fonction de transaction réelle n'est développée, même si l'actif de
  règlement est connu.

### 2.5 Contrats JSON

- Les contrats sont **stricts** (`additionalProperties: false`).
- Chaque document persisté porte `schema_version`.
- `schema_version` est la version du contrat ; `source_schema_version` est la
  version du format amont ; `normalizer_version` est la version du code de
  normalisation. Ces trois valeurs ne sont pas interchangeables.
- **Phase pré-gel (D-040)** : les contrats ne sont pas des interfaces stables et
  aucun consommateur externe ne les utilise. Une extension compatible reste une
  version mineure. Une version mineure peut aussi inclure des changements
  incompatibles, à condition qu'ils soient documentés, testés et accompagnés
  d'une déclaration de compatibilité explicite.
- **Après gel (SemVer strict)** : un ajout de champ optionnel est une version
  mineure ; un changement de type, d'unité ou de sémantique, un retrait
  d'énumération ou un ajout de champ obligatoire est une version majeure.
- La version 1.1.0 ajoute des champs obligatoires (`normalizer_version`,
  `trader_visibility`, `order_id` dans l'estimation, incrément d'arrondi) et
  retire des énumérations suspendues (`per_share`, `custom`, `outcome_token`,
  `not_required`, latence `normal`). **Compatibilité déclarée :** les documents
  1.0.0 restent des archives lisibles, mais ne sont pas valides sous 1.1.0 ;
  aucun producteur 1.0.0 n'est compatible sans migration. Cette rupture est
  assumée avant gel, sans consommateur externe stable au 2026-10-27. Les lignes
  legacy restent lisibles sans valeurs inventées.
- **Candidat 1.2.0 (non gelé)** : `market_event`, `execution`, `experiment` et
  `fee_schedule` passent à `1.2.0`. Ajouts obligatoires pour les trois premiers :
  `event_identity_version='v2'`, ancrage `source_event_id` ou
  `raw_payload_sha256`, `rng_implementation='polymarket-lab/rng/v2'`,
  `config_hash_version='config/v2'`. `fee_schedule` porte l'extension
  chronologique A5-06. `strategy_hypothesis` reste `1.0.0`. Aucun document
  1.1.0 audité n'est modifié en place : la correction de `fee_schedule` est
  publiée comme version 1.2.0 (D-050).
- Les payloads bruts non normalisés ne sont jamais consommés par les modules
  cœur : ils sont conservés à part et référencés par `raw_payload_ref` +
  `raw_payload_sha256`.

## 3. Modules et responsabilités

### 3.1 Data Collectors

**Entrées :** interfaces publiques documentées.

**Sorties :** payloads bruts, événements de connexion, timestamps source/réception.

- Gérer reconnexion, limitation de débit, reprise et détection de trous.
- Enregistrer le payload brut et son SHA-256 **avant** normalisation.
- Ne jamais inventer un champ, un prix ou une taille.
- Ne jamais envoyer d'ordre réel ; aucune clé privée d'ordre en V1.
- Ne pas démarrer la collecte réseau avant validation de la checklist
  Polymarket (§16).

Responsabilités des sources — **vérification documentaire rapportée par le
propriétaire le 2026-10-26, non rejouée par A0** :

| Source (`source`) | Responsabilité | Ne doit pas servir à |
|---|---|---|
| `gamma_api` | Métadonnées de marchés et d'événements : question, outcomes, dates, statut, tick size, taille minimale | Carnet, trades, positions |
| `clob_api` | Carnet, prix, tick size, ordres et trades publics | Métadonnées canoniques sans recoupement |
| `data_api` | Activité publique des traders, positions et historique de trades | Profondeur ou carnet |
| `clob_ws` | Flux temps réel du carnet et des trades ; timestamps de réception | Historique profond ou résolution |

Règles :

- Les champs de ces sources **ne sont pas interchangeables**. Chaque adaptateur
  a son propre normaliseur, sa propre version de schéma amont
  (`source_schema_version`) et conserve le payload brut.
- Une valeur absente d'une source n'est pas « complétée » par une autre source
  sans règle explicite et sans incident de qualité.
- Un même trade vu par plusieurs sources produit un doublon inter-sources
  signalé, jamais une fusion silencieuse.
- La source d'origine est obligatoire sur chaque événement normalisé.

### 3.2 Normalization & Data Quality

**Entrées :** payloads bruts + contexte de connexion.

**Sorties :** événements conformes à `contracts/market_event.schema.json`,
incidents de qualité.

- Un normaliseur par source. Aucun mapping générique n'est supposé entre Gamma,
  CLOB, Data API et flux temps réel.
- Chaque événement porte `normalizer_version` (code) en plus de
  `schema_version` (contrat) et `source_schema_version` (amont). Une correction
  de parsing crée un nouvel `event_id` et une ligne append-only dans
  `event_replacements` ; l'ancien événement n'est jamais modifié.
- `trade_events` reçoit tous les prints publics des marchés observés ;
  `trader_visibility` vaut `identified` (trader_id non nul) ou `unknown`
  (trader_id nul). Aucun sentinel ni inférence. `trader_activity_events` exige
  un trader enregistré.
- Convertir en micro-unités avec `Decimal`.
- Normaliser les timestamps en UTC canonique.
- Valider le contrat avant écriture.
- Dédupliquer par `event_id` et `(source, source_event_id)`.
- Signaler : données tardives, trous, carnet incomplet, hash incohérent,
  dérive d'horloge, valeur d'activité inconnue, doublon inter-sources.
- Ne pas « réparer » une donnée manquante par une valeur par défaut.

### 3.3 Local Data Store

- SQLite en mode WAL pour la V1 : un seul écrivain, plusieurs lecteurs.
  Le dashboard est lecteur. Si la concurrence d'écriture devient un problème
  mesuré, migrer vers PostgreSQL ; ne pas le faire par anticipation.
- Événements normalisés append-only ; fills et écritures comptables immuables.
- Projections (`markets`, `market_tokens`) pour les lectures courantes ;
  l'historique fait foi dans les événements de métadonnées.
- Références aux payloads bruts sous `data/raw/`, jamais commités.
- Migrations versionnées dans `schema_migrations`.
- Paper trading en direct : enregistrer localement les **snapshots et deltas de
  carnet** ainsi que les trades. Un historique de prix ne permet pas de
  reconstituer la profondeur.
- Les snapshots et deltas de carnet sont conservés avec leur hash, leur source
  et leurs timestamps ; un trou de carnet est un incident de qualité.

### 3.4 Trader Analytics

**Entrées :** activités publiques, trades, positions et métadonnées.

**Sorties :** rapports qui séparent faits, hypothèses, inconnues, biais et
niveau de confiance.

- Ne jamais déduire une intention, un ordre non exécuté ou un portefeuille
  complet d'une transaction visible.
- Signaler la visibilité partielle et l'incertitude maker/taker.
- Ne jamais écrire dans le grand livre ni dans les fills.

### 3.5 Strategy Registry

Une stratégie est identifiée par `(strategy_id, version)`, liée à une hypothèse
et à une configuration sérialisée. Le statut est `draft`, `backtest`, `paper` ou
`retired`.

- Une stratégie est une fonction de décision **déterministe**.
- Les règles textuelles de l'hypothèse ne sont pas exécutables : elles doivent
  être traduites en configuration et en code testés.
- Un appel LLM ne doit jamais se trouver dans le chemin critique de décision.

### 3.6 Simulation Engine

- Ordres taker uniquement en V1 ; maker reporté.
- Consomme les niveaux du côté opposé, dans l'ordre des prix.
- Applique latence, haircut de liquidité, limite de profondeur et âge maximal
  du carnet.
- Autorise fill partiel, reliquat non exécuté et rejet explicite.
- Exige un ordre limite : même un ordre « market » porte une borne de prix.
- Exige un barème de frais référencé avant de produire un fill ; un barème de
  catégorie n'est pas une preuve pour un marché.
- Enregistre l'estimation, les niveaux consommés, le snapshot de référence et
  toutes les hypothèses.
- Aucun accès réseau, aucune horloge murale, aucun ordre réel, aucune fonction
  de transaction on-chain.

### 3.7 Ledger & Metrics

- Journal en partie double, source de vérité du cash, des positions, des frais
  et du PnL.
- Le PnL est calculé par du code testé, jamais par un LLM.
- Tous les montants d'une expérience utilisent une seule `accounting_unit` ;
  l'actif de règlement peut différer et exige alors une conversion explicite.
- Les snapshots de portefeuille séparent cash, valeur exécutable des positions,
  PnL réalisé, PnL latent et frais.
- Le mid-price peut être affiché, jamais utilisé comme valeur de liquidation
  garantie.
- Toute correction est une transaction de reversal ; pas d'UPDATE/DELETE.

### 3.8 Benchmark Engine

- Module séparé ; il ne lit jamais les décisions internes du bot évalué.
- Chaque benchmark est lui-même une **expérience** avec son propre ledger.
- Mêmes données (même manifeste), mêmes fenêtres, mêmes hypothèses
  d'exécution, mêmes limites de risque, même version de métriques.
- Les paramètres du benchmark sont figés avant le test final.

### 3.9 Dashboard

- Lecture seule sur le stockage et les vues.
- Affiche en permanence « PAPER TRADING — AUCUN ARGENT RÉEL ».
- Affiche les données manquantes comme manquantes ; n'interpole pas.
- Ne recalcule pas le PnL si le ledger ou les snapshots le fournissent.
- Affiche le statut des frais (`verified`, `provisional`, `unverified`) et les
  incidents de qualité.
- Aucun bouton ou endpoint d'ordre réel.

### 3.10 Validation & Reports

- Tests unitaires, d'intégration, comptables, anti-look-ahead, idempotence,
  robustesse aux coûts et stress tests.
- Audit indépendant des conclusions de rentabilité.
- Rapport de reproductibilité : version du code, configuration, manifeste de
  données, barème de frais, seed, version de métriques.

## 4. Flux d'événement canonique

Un événement possède une enveloppe commune et **un seul** payload typé,
discriminé par `event_type` :

| `event_type` | Payload obligatoire | Champs clés |
|---|---|---|
| `trade` | `trade` | `price_micros`, `size_micros`, `taker_side`, `accounting_unit` |
| `book_snapshot` | `book_snapshot` | `bids`, `asks`, ordre canonique |
| `book_delta` | `book_delta` | `changes[]` avec `book_side`, `action`, prix, taille |
| `trader_activity` | `trader_activity` | `trader_id`, `activity_type`, détails si TRADE |
| `market_metadata` | `market_metadata` | `outcomes[]`, `collateral_asset`, `collateral_decimals`, `settlement_asset`, statut |
| `market_resolution` | `market_resolution` | statut, token gagnant, `settlement_asset`, payout par part, conversion éventuelle |
| `connection_status` | `connection_status` | `stream_id`, statut, trou éventuel |

Règles :

1. `side` générique interdit : `taker_side` pour un trade, `book_side` pour un
   delta, `side` pour l'activité du trader sélectionné. Ces trois notions ne
   sont pas interchangeables.
2. `bids` : prix strictement décroissants, aucun doublon. `asks` : prix
   strictement croissants, aucun doublon. Un côté vide est autorisé mais
   signalé `incomplete_book`.
3. `sequence_number` est une chaîne opaque, jamais un entier triable.
4. Les métadonnées de marché sont historisées : un changement de tick size, de
   taille minimale ou de statut ne doit pas réécrire le passé.
5. Une résolution est un événement distinct ; elle ne doit pas être déduite d'un
   prix de carnet.
6. Tout payload brut est conservé avec son hash, même si le parseur échoue.
7. Une valeur d'activité non reconnue devient `UNKNOWN` + flag
   `unknown_activity_type` ; elle n'est pas supprimée.
8. `source` est obligatoire et limité au registre (`gamma_api`, `clob_api`,
   `data_api`, `clob_ws`, `fixture`). `source_schema_version` conserve la
   version amont. Aucun champ n'est supposé interchangeable entre sources.
9. `accounting_unit` est obligatoire pour un trade ou une activité monétaire ;
   ce n'est ni la devise de présentation ni nécessairement l'actif de
   règlement.
10. Une résolution `RESOLVED` porte obligatoirement un actif de règlement et un
    payout par part. Si cet actif diffère de l'unité comptable, une
    `conversion_rule` sourcée et datée est requise.

## 5. Stockage local et invariants

Le schéma de référence est `schemas/initial_db_schema.sql` (base 0.3,
`PRAGMA user_version = 3`) puis `schemas/migrations/0004_consolidation.sql`
(cible auditée 0.4, `PRAGMA user_version = 4`). Une base neuve applique la base
puis les migrations, dans l'ordre ; aucun schéma consolidé n'est dupliqué dans
le fichier initial.

Les migrations **candidates non approuvées** sont
`0005_p0_foundations.sql` (0.4 → 0.5, B-01/B-02/B-05),
`0006_p0_ledger.sql` (0.5 → 0.6, B-06) et
`0007_contract_sql_alignment.sql` (0.6 → 0.7, fin obligatoire hors
`paper_live`, défauts `schema_version=1.2.0`). Elles ne doivent pas être
appliquées à la base de travail. Le runner généralisé
(`python schemas/migrations/run_migration.py --database <fichier>`) sélectionne
la migration suivante dans un registre `3→0004`, `4→0005`, `5→0006`,
`6→0007`, vérifie la version source, le journal attendu et la version cible,
sauvegarde la base (`Connection.backup`), restaure la sauvegarde en cas
d'échec, et restaure toujours `PRAGMA foreign_keys = ON` et
`PRAGMA recursive_triggers = ON` sur sa connexion. Le préflight de `0007`
compte les expériences non `paper_live` sans fin et refuse la migration avant
toute reconstruction. Un échec après le `COMMIT` interne ne peut être annulé
par `ROLLBACK` : la sauvegarde est alors la seule voie de retour.

Toute connexion applicative passe par
`polymarket_lab.storage.connection.open_connection` (B-04). La fabrique impose
et vérifie `foreign_keys=ON`, `recursive_triggers=ON`, `busy_timeout`, WAL
**obligatoire pour toute écriture sur fichier** et `synchronous` (`NORMAL` par
défaut, `FULL` configurable). `journal_mode=None` est réservé à `:memory:` et
à la lecture seule. Aucune connexion
`sqlite3.connect` directe n'est admise hors de ce module ; le runner de
migration est la seule exception outillée, avec `foreign_keys=OFF` temporaire
et restauration vérifiée. Sans `recursive_triggers=ON`, un `INSERT OR REPLACE`
peut contourner les triggers DELETE append-only.

Groupes de tables :

- référentiels : `traders`, `hypotheses`, `markets`, `market_tokens` ;
- configuration et reproductibilité : `data_manifests`, `fee_schedules`,
  `strategies`, `experiments` ;
- événements : `market_events` + tables de détail par type
  (`trade_events`, `trader_activity_events`, `book_snapshots`,
  `book_delta_changes`, `market_metadata_events`,
  `market_resolution_events`, `connection_events`) ;
- qualité : `data_quality_incidents` ;
- simulation : `simulated_orders`, `execution_estimates`, `simulated_fills` ;
- comptabilité : `ledger_transactions`, `ledger_postings`,
  `portfolio_snapshots`, `experiment_metrics` ;
- benchmarks : `benchmark_runs` ;
- versionnement : `schema_migrations`.

Invariants :

1. `market_events` est append-only. Une correction de parsing produit un nouvel
   événement ou une nouvelle version de schéma, jamais un UPDATE silencieux.
2. `simulated_fills`, `ledger_transactions` et `ledger_postings` sont immuables
   (triggers SQLite). Une correction est un reversal.
3. Un fill référence obligatoirement un barème de frais et un snapshot de
   carnet.
4. Un ordre rejeté porte obligatoirement un motif.
5. Un ordre accepté référence obligatoirement le snapshot utilisé.
6. `equity_micros = cash_micros + positions_value_micros` dans les snapshots.
7. Une expérience `research`, `validation` ou `final_test` référence
   obligatoirement un manifeste de données.
8. Une expérience `final_test` sans manifeste est refusée.
9. Les index couvrent les lectures de rejeu et de dashboard ; les vues
   `v_experiment_cash`, `v_experiment_positions`, `v_order_execution`,
   `v_ledger_anomalies` et `v_experiment_latest_snapshot` sont la base des
   lectures A4.
10. `market_events` et ses sept tables de détail sont append-only y compris
    pour les mises à jour et suppressions directes. `INSERT OR REPLACE`
    déclenche les triggers DELETE si `PRAGMA recursive_triggers = ON` ; ce
    pragma est requis à chaque connexion. `INSERT OR IGNORE` reste idempotent.
11. Un événement, un ordre ou une estimation ne peut référencer que le token
    de son propre marché : `UNIQUE(market_id, token_id)` sur `market_tokens`
    et FK composites `(market_id, token_id)`. Le token gagnant d'une
    résolution appartient au marché résolu.
12. `book_snapshot_event_id` désigne un `book_snapshot` réel, du même marché et
    du même token que l'ordre, l'estimation ou le fill. Une FK vers
    `market_events` seule ne suffit pas.
13. Cardinalité V1 : une intention (`intent_id`) produit au plus un ordre ;
    l'ordre porte l'intention, y compris s'il est rejeté. Une estimation cite
    le couple `(order_id, intent_id)` de son ordre. Une intention ne peut pas
    être réutilisée par un autre ordre.
14. Un fill ne peut viser qu'un ordre `accepted`, `partially_filled` ou
    `filled`. Un ordre `proposed`, `rejected` ou `expired` ne produit aucune
    écriture d'exécution.
15. Une résolution réglée dans un actif différent du collatéral du marché
    exige `conversion_rule_json`. Le SQL impose sa présence, pas la validité
    de son contenu.
16. Les hashes `book_hash_before` / `book_hash_after` sont identiques sur
    toutes les lignes d'un même delta ; ils décrivent le carnet, pas la ligne.
17. Un événement 1.1.0 ou 1.2.0 porte `normalizer_version`. Un remplacement est
    une ligne append-only de `event_replacements` ; `v_current_market_events`
    exclut les événements remplacés.
18. Les ordres, estimations, fills et postings d'une expérience partagent son
    `accounting_unit` ; le SQL le vérifie par trigger.
19. `data_manifests.source_class` vaut `fixture`, `recorded` ou `live`. Une
    expérience `final_test` ne peut pas utiliser une fixture.
20. Une valorisation inconnue utilise des champs nuls avec
    `valuation_method='none'` ; aucun zéro de complaisance.
21. **C-01** — un remplacement `O→N` exige
    `visible_from >= current_from(O)` et, si `N` a déjà un remplacement
    sortant, `visible_from < min(visible_from des sortants de N)`. Les cycles
    sont refusés. Ces règles sont portées par des triggers SQL, pas seulement
    par l'API. Un trigger `BEFORE INSERT` refuse toute collision de clé, y
    compris `INSERT OR REPLACE` lorsque `recursive_triggers` est désactivé.
22. **C-02** — `created_at` et `visible_from_received_timestamp` sont générés
    par la couche de stockage à partir d'une horloge UTC injectée
    (`storage.clock`). L'API d'écriture n'accepte jamais `visible_from`.
    `visible_from = max(old.received, new.received, created_at)` et
    `created_at >= max(old.received, new.received)` sont vérifiés en SQL.
    Limite explicite : un accès SQL direct reste un canal privilégié et ne
    peut pas prouver l'horloge murale ; seule l'API de stockage garantit
    l'horodatage.
23. **C-03** — aucun manifeste n'est lisible par les vues as-of sans un
    `manifest_seals` valide ; `seal.manifest_hash = data_manifests.sha256`,
    les comptages doivent correspondre aux listes, et les listes
    `manifest_events`/`manifest_replacements` sont figées après scellement.
    Les collisions `INSERT OR REPLACE` sur `data_manifests` et les listes du
    manifeste sont refusées par trigger `BEFORE INSERT`, même avec
    `recursive_triggers` désactivé. Limite explicite : un audit privilégié peut
    lire les tables brutes ; les lectures as-of passent par la vue filtrée par
    le seal.
24. Les manifestes et expériences legacy ne sont ni recalculés ni scellés
    rétroactivement. Une conversion de règlement est rattachée à une seule
    expérience ; l'unicité du grand livre et des conversions est par
    expérience (`0006`). Le rattachement exige une transaction de ledger de la
    même expérience avec `ref_type='market_resolution'`,
    `ref_id=resolution_event_id` et `kind='settlement'` ; un ajustement seul ne
    suffit pas. Les collisions `INSERT OR REPLACE` sur
    `ledger_transactions` et `settlement_conversions` sont refusées par trigger
    `BEFORE INSERT`, même avec `recursive_triggers` désactivé.

Le schéma SQL est volontairement plus strict que le contrat JSON. Le contrat
valide la forme d'un document ; le SQL protège les invariants persistés.

### 5.1 Règles sémantiques non exprimables en SQL déclaratif ou JSON Schema

Ces règles restent des barrières applicatives explicites. A1 les applique à la
normalisation et A2 avant toute écriture ou publication.

- **Ordre canonique du carnet (A5-05)** : bids strictement décroissants, asks
  strictement croissants, pas de prix dupliqué. A1 trie ou rejette ; le test de
  contrat caractérise seulement que JSON Schema ne l'impose pas.
- **Chronologie (A5-06)** : `effective_to > effective_from` et
  `period.end_time > period.start_time`. JSON Schema 2020-12 ne compare pas
  deux champs ; les contrats `fee_schedule` et `experiment` déclarent donc
  l'extension normative `x-polymarket-chronological-order`. Le SQL refuse déjà
  la chronologie invalide à la persistance. Un validateur JSON Schema standard
  ignore l'extension : le point d'entrée applicatif
  `polymarket_lab.validation.contracts.contract_issues` (et
  `validate_contract`) applique le schéma fourni **puis** l'extension ; les
  writers A1/A2 doivent passer par lui et refuser le document avant insertion.
  La fin nulle est admise ; l'absence de fin n'est admise que si le champ n'est
  pas requis (`fee_schedule.effective_to`), tandis que
  `experiment.period.end_time` doit être présent et peut être nul.
- **Écriture contractuelle (A1/A2)** : `storage.contract_writer` expose
  `write_experiment` et `write_fee_schedule` **sans paramètre de schéma ou de
  validateur**. Le parcours recharge le registre approuvé à chaque écriture,
  vérifie le SHA-256 et la version, gèle profondément le schéma et construit
  un validateur système. Il impose une connexion `open_connection`
  (`foreign_keys=ON`, `recursive_triggers=ON`,
  `ignore_check_constraints=OFF`, `isolation_level=None`,
  `row_factory=sqlite3.Row`), puis validation schéma → chronologie → version →
  métier, vérification d'approbation, transaction et relecture persistée. Les
  writers ne doivent pas utiliser `INSERT` direct pour ces documents. Le
  parcours de test à schéma personnalisé est un module distinct,
  `storage.contract_writer_testing`, et ne doit pas être importé par A1/A2.
  Voir `WRITER_INTEGRATION.md`. L'intégration de production reste bloquée par
  le choix A/B de la dépendance de validation (D-054).
- **Invariants comptables (A5-16)** : somme nulle par transaction, `CASH >= 0`,
  quantité de position `>= 0`, pas de short. Le schéma fournit
  `v_ledger_anomalies`, `v_negative_cash` et `v_position_anomalies` ; A2 doit
  les consulter dans la même transaction et refuser la publication si elles ne
  sont pas vides.
- **Cohérence sémantique des JSON (A5-20, A5-22, A5-23)** : `outcomes_json`
  est vérifié par trigger pour l'unicité token/index ; la forme détaillée des
  `levels_json`, `quality_flags_json`, `assumptions_json`, la cohérence
  estimate/résultat rejeté et les transitions d'état des ordres restent
  validées par A1/A2 contre les contrats.
- **Contenu des conversions (A5-21)** : le SQL exige une règle de conversion
  quand les actifs diffèrent ; la source, la date et le taux sont vérifiés par
  A1/A2 et restent soumis à Q-009.

### 5.2 États d'un ordre simulé

Transitions autorisées en V1 :

`proposed -> accepted | rejected | expired`
`accepted -> partially_filled | filled | expired`
`partially_filled -> filled | expired`

`rejected`, `filled` et `expired` sont terminaux. Le SQL Interdit seulement les
fills sur un ordre non exécutable ; A2 doit refuser les autres transitions
invalides. Une correction d'état passe par un nouvel ordre ou une transaction
de reversal, jamais par une réécriture silencieuse de l'historique comptable.

## 6. Interfaces entre modules

Les signatures ci-dessous sont des **contrats de type**, pas une implémentation.
Les montants sont toujours des `Micros` (entiers).

```python
Micros = int
Timestamp = datetime  # UTC aware, précision microseconde

@dataclass(frozen=True)
class BookView:
    snapshot_event_id: str
    token_id: str
    bids: tuple[BookLevel, ...]      # prix décroissants
    asks: tuple[BookLevel, ...]      # prix croissants
    source_timestamp: Timestamp
    received_timestamp: Timestamp
    age_source_ms: int
    age_received_ms: int
    is_stale: bool
    quality_flags: tuple[str, ...]


class EventStore(Protocol):
    def append(self, event: MarketEvent) -> AppendResult: ...          # idempotent
    def get(self, event_id: str) -> MarketEvent | None: ...
    def iterate(self, query: EventQuery) -> Iterator[MarketEvent]: ... # cutoff inclus
    def latest_book(self, token_id: str, *, as_of_received: Timestamp,
                    max_age_ms: int) -> BookView | None: ...
    def market_metadata(self, market_id: str, *,
                        as_of_received: Timestamp) -> MarketMetadata | None: ...
    def fee_schedule(self, *, market_id: str, at: Timestamp,
                     accepted_status: set[str]) -> FeeSchedule | None: ...


class MarketState(Protocol):
    def book(self, token_id: str, decision_ts: Timestamp,
             max_age_ms: int) -> BookView: ...   # lève StaleBook, MissingBook


class Strategy(Protocol):
    strategy_id: str
    version: str
    def on_event(self, ctx: DecisionContext) -> Sequence[OrderIntent]: ...


class FeeCalculator(Protocol):
    def calculate(self, *, schedule: FeeSchedule, side: Side,
                  price_micros: Micros, size_micros: Micros) -> FeeBreakdown: ...


class ExecutionModel(Protocol):
    def estimate(self, intent: OrderIntent, book: BookView,
                 assumptions: ExecutionAssumptions) -> ExecutionEstimate: ...


class Simulator(Protocol):
    def submit(self, intent: OrderIntent, *, decision_ts: Timestamp,
               experiment: ExperimentSnapshot) -> ExecutionResult: ...


class Ledger(Protocol):
    def open(self, *, experiment_id: str, initial_capital_micros: Micros,
             accounting_unit: str, occurred_at: Timestamp) -> LedgerTransaction: ...
    def apply_fill(self, fill: Fill) -> LedgerTransaction: ...          # idempotent
    def settle(self, result: MarketResolution) -> LedgerTransaction: ...# idempotent
    def reverse(self, transaction_id: str, reason: str) -> LedgerTransaction: ...
    def snapshot(self, *, experiment_id: str, as_of: Timestamp,
                 valuations: Sequence[PositionValuation]) -> PortfolioSnapshot: ...
    def reconcile(self, experiment_id: str) -> ReconciliationReport: ...


class MetricsCalculator(Protocol):
    def compute(self, *, experiment_id: str, metrics_version: str,
                as_of: Timestamp) -> MetricsReport: ...


class BenchmarkRunner(Protocol):
    def run(self, *, evaluated_experiment_id: str, benchmark_type: str,
            parameters: Mapping[str, object], metrics_version: str) -> BenchmarkRun: ...
```

### 6.1 Règles d'interface

- `DecisionContext` ne contient que des données reçues avant
  `decision_timestamp` ; il ne donne accès ni au réseau, ni à l'horloge, ni au
  système de fichiers brut.
- `Strategy.on_event` est pure : aucun effet de bord, aucune écriture ledger,
  aucun appel LLM.
- `ExecutionModel.estimate` est pure et déterministe pour un même
  `(intent, book, assumptions, seed)`.
- `Simulator.submit` peut rejeter pour carnet périmé, liquidité insuffisante,
  barème manquant, limite de risque ou données invalides. Un rejet est un
  résultat normal, pas une exception.
- `Ledger.apply_fill` ne recalcule jamais les frais : il comptabilise le fill
  fourni. Le recalcul des frais appartient à `FeeCalculator`.
- `Ledger` est le seul module autorisé à écrire les tables comptables.
- `Dashboard` ne reçoit que des read models ou des vues ; il ne peut pas écrire
  le ledger.
- Le type `Fill` contient déjà le prix, la taille, le notionnel,
  l'`accounting_unit`, le frais, son unité et sa règle d'arrondi. Aucun module
  aval ne « réinterprète » ces champs.
- `ExecutionEstimate` et `Fill` portent l'`accounting_unit` de l'expérience ;
  un fill dont l'unité diffère de celle de l'expérience est rejeté.
- Un `Fill` ne porte pas l'actif de règlement : celui-ci appartient à
  l'événement de résolution et au ledger de settlement.

### 6.2 Propriété des modules

| Module | Propriétaire | Remarque |
|---|---|---|
| `contracts/`, `schemas/`, décisions | A0 | Toute modification d'interface passe par A0 |
| `src/polymarket_lab/core/` (unités, temps, IDs) | **A1 propriétaire** | A2 relecture obligatoire de `core/units.py` ; A5 tests. D-017 |
| `src/polymarket_lab/collectors/`, `normalization/`, `storage/` | A1 | Ne modifie pas les contrats sans A0 |
| `src/polymarket_lab/simulation/`, `ledger/` | A2 | Dépend du module `core` |
| `src/polymarket_lab/analytics/`, `strategies/` | A3 | Configurations déterministes uniquement |
| `src/polymarket_lab/dashboard/` | A4 | Lecture seule |
| `tests/`, `benchmarks/`, `validation/` | A5 | Tests de contrat, audit indépendant |

Le module `core/` expose au minimum `to_micros(Decimal, decimals) -> int`,
`canonical_timestamp(datetime) -> str` et `deterministic_event_id(...) -> str`.
A1 en est propriétaire ; A2 relit obligatoirement les conversions utilisées par
le ledger ; A5 teste les cas limites (arrondis, décimales, fuseaux, collisions
d'identifiants). Aucun autre module ne duplique ces fonctions. Le prompt A1 et
`COORDINATION.md` doivent être mis à jour par le propriétaire pour inclure
`core/` dans le périmètre d'A1 ; A0 ne les modifie pas.

## 7. Comptabilité et PnL

### 7.1 Convention de signe

`amount_micros > 0` = débit ; `< 0` = crédit. Le compte `POSITION` porte en plus
`quantity_micros` (parts, signe identique à la variation de position).

| Compte | Type | Débit | Crédit |
|---|---|---|---|
| `CASH` | actif | augmentation | diminution |
| `POSITION` | actif | acquisition au coût | cession au coût |
| `FEES` | charge | frais payés | — |
| `REALIZED_PNL` | produit/charge | perte réalisée | gain réalisé |
| `CAPITAL` | capitaux propres | retrait | apport |

Pour un posting `POSITION`, `amount_micros` est le **coût** en devise de
collatéral et `quantity_micros` est la **quantité de parts**. La devise ne
s'applique pas aux parts.

### 7.2 Exemples (micro-unités)

Hypothèse fictive : achat de 100 parts à un VWAP de 0.536, frais de 0.464
unité comptable (pUSD dans cet exemple).

```text
tx_deposit   CASH       +1_000_000_000
             CAPITAL    -1_000_000_000

tx_fill      POSITION   +53_600_000   quantité +100_000_000
             CASH       -53_600_000
             FEES            +464_000
             CASH           -464_000
```

Vente des 100 parts à 0.60, frais 0.40 unité comptable :

```text
tx_sell      POSITION   -53_600_000   quantité -100_000_000
             CASH       +60_000_000
             REALIZED_PNL -6_400_000
             FEES          +400_000
             CASH          -400_000
```

Résolution gagnante à 1.00 en actif de règlement, sans frais de règlement
(la conversion pUSD → USDC est fictive et doit être vérifiée) :

```text
tx_settle    POSITION   -53_600_000   quantité -100_000_000
             CASH      +100_000_000
             REALIZED_PNL -46_400_000
```

Résolution perdante : `POSITION -53_600_000`, `REALIZED_PNL +53_600_000`,
aucun cash.

Si l'actif de règlement diffère de l'unité comptable, l'événement de résolution
conserve le montant dans l'actif d'origine et sa `conversion_rule` ; le ledger
applique ensuite la conversion explicite, puis comptabilise dans l'unité
comptable. L'exemple ci-dessus suppose une conversion 1:1 **fictive** ; elle
doit être vérifiée avant tout PnL net définitif.

**V1 suspend les frais en parts** (`fee_charge_unit = outcome_token`) avec
Q-011 : aucun fill ne peut les produire. Le paragraphe suivant décrit le modèle
cible si Q-011 est tranchée, mais il ne constitue pas une autorisation V1. Quand
il sera activé, le frais en parts devra être inclus dans la transaction unique
du fill, jamais dans une transaction `kind='fee'` séparée (D-034).

Modèle cible : la position diminue en quantité et en coût, et la perte
correspondante est comptabilisée dans `REALIZED_PNL`. Le frais ne crée jamais de
cash. Un frais en parts ne peut être prélevé que sur une position existante ;
si le prélèvement rendrait la quantité négative, le fill est rejeté, sauf règle
officielle vérifiée de conversion en collatéral.

Sur une cession partielle, le coût retiré est arrondi selon la règle de
l'expérience ; le dernier lot absorbe le résidu pour que le coût restant soit
nul après clôture complète. `fees_paid_micros` dans un snapshot ne compte que
les frais en collatéral ; si Q-011 active les frais en parts, ceux-ci seront
représentés par la réduction de position et la perte réalisée, dans la
transaction du fill.

### 7.3 Invariants comptables

1. Somme des `amount_micros` = 0 pour chaque transaction.
2. `CASH >= 0` ; aucune marge, aucun effet de levier en V1.
3. Quantité de position `>= 0` ; aucun short implicite.
4. Un fill produit exactement une transaction, clé `fill:<fill_id>`, frais
   inclus. Aucune transaction `kind='fee'` séparée avec `ref_type='fill'`.
5. Une résolution produit exactement une transaction, clé
   `resolution:<event_id>`.
6. Le PnL réalisé ne provient que d'une cession ou d'un règlement.
7. Le PnL latent n'entre jamais dans le cash.
8. `equity = cash + valeur exécutable des positions`. Les frais sont déjà
   sortis du cash : ne pas les soustraire une seconde fois.
9. La valorisation d'une position utilise le côté opposé du carnet, pour la
   taille considérée, si la profondeur est disponible. Le mid n'est qu'une
   référence d'affichage.
10. Chaque montant est un entier ; l'arrondi est explicite et versionné.
    L'arrondi des **frais** suit le barème (`fee_schedules.rounding_rule`) ;
    l'arrondi des **notionnels et du VWAP** suit
    `execution_assumptions.rounding_rule`. Les deux règles ne se confondent pas.
11. Toute anomalie de somme est visible dans `v_ledger_anomalies` ; elle bloque
    la publication d'un résultat.
12. Aucune écriture comptable sans barème de frais référencé.

### 7.4 Statut des frais et claims de PnL

- `verified` : barème officiel, URL, date de consultation, période d'effet.
- `provisional` : barème plausible mais incomplet ; résultat étiqueté
  provisoire.
- `unverified` : valeur fictive ou non vérifiée ; le PnL net ne peut pas servir
  de critère de succès.
- Si aucun barème n'est disponible, le simulateur rejette le fill avec
  `missing_fee_schedule` ; il ne suppose pas zéro.
- Si plusieurs barèmes couvrent le même instant, la sélection suit : périmètre
  le plus spécifique (`market` > `category` > `global`), puis `effective_from`
  le plus récent. Une égalité est une ambiguïté refusée, pas un choix arbitraire.
- **Un taux de catégorie ou global n'est pas une preuve qu'il s'applique à un
  marché donné.** Un barème `verified` de portée `global` ou `category` doit
  porter un `scope_evidence_ref` précis. Sans cette preuve, il reste
  `provisional` ou `unverified`, et le PnL net n'est pas définitif.
- La configuration `fees.allow_category_rate_as_proof` doit rester `false` en
  V1.
- Le statut de frais d'une expérience est le plus faible des statuts utilisés :
  un seul barème `unverified` rend le résultat net non définitif.
- Aucun PnL net définitif n'est affiché si les frais ou une conversion de
  règlement restent non vérifiés.

### 7.5 Formules V1 et unités (D-033, D-034)

Avec `P = price_micros`, `S = size_micros`, `R = rate_micros` :

- `notional` : `fee_micros = round(R * P * S / 10^12)`.
- `linear_min_price_1mp` :
  `fee_micros = round(R * min(P, 10^6-P) * S / 10^12)`.
- `per_share` et `custom` : **suspendus en V1**.
- Les frais sont prélevés uniquement en collatéral ; `outcome_token` est
  suspendu avec Q-011. `fee_amount_micros` et
  `rounding_increment_micros` sont dans l'unité de prélèvement.
- Arrondi une fois sur le total du fill ; `rounding_rule` du barème pour les
  frais, `execution_assumptions.rounding_rule` et
  `rounding_increment_micros` pour les notionnels, le VWAP et le coût retiré.
- Sélection : spécificité `market > category > global`, puis
  `effective_from` le plus récent, puis `source_retrieved_at` le plus récent ;
  le barème doit être consulté avant `decision_timestamp`. Égalité au sommet =
  `ambiguous_fee_schedule`, refus.
- Une transaction par fill, frais inclus. Coût moyen pondéré ; frais en charge
  séparée ; PnL réalisé hors frais. Vente partielle :
  `cost_removed = round_half_even(cost * qty_sold / qty_held)` ; vente totale =
  coût entier ; le dernier lot absorbe le résidu.
- Valorisation inconnue : `positions_value_micros`, `equity_micros` et
  `unrealized_pnl_micros` nuls avec `valuation_method='none'` ; le détail par
  token est dans `position_valuations`. Aucun zéro de complaisance.
- `VOID` : aucun settlement sans `void_rule_ref` sourcé ; Q-012 reste ouverte.

## 8. Qualité des données et anti-look-ahead

### 8.1 Visibilité d'une décision

À l'instant de décision `T`, une stratégie ne peut lire que les événements
vérifiant :

```text
received_timestamp <= T
et, si un manifeste est utilisé :
received_timestamp <= manifest.cutoff_received_timestamp
et e.event_id IN manifest_events(manifest)
et aucun remplacement r de manifest_replacements(manifest) avec
    r.old_event_id = e.event_id et r.visible_from <= T
et (e.event_id n'est new_event_id d'aucun remplacement du manifeste,
     ou un tel remplacement a r.visible_from <= T)
et manifest_seals(manifest) est valide
```

Le manifeste ne contient que des remplacements dont les deux extrémités sont
dans `manifest_events` et dont `visible_from <= cutoff`. Aucun manifeste non
scellé n'est admissible.

`source_timestamp` sert à l'ordre du marché et au calcul de fraîcheur ; il ne
sert **jamais** à admettre un événement reçu après `T`. Un événement dont le
`source_timestamp` est postérieur à `T` mais reçu avant `T` est signalé
`clock_skew` et ne doit pas être utilisé pour une décision sans revue.

### 8.2 Fraîcheur du carnet

Deux âges sont calculés :

- `age_source_ms = T - source_timestamp` : fraîcheur du marché ;
- `age_received_ms = T - received_timestamp` : temps depuis la réception.

Un carnet est rejeté si l'un des deux dépasse `max_book_age_ms`. Une valeur
négative de `age_source_ms` n'est pas « très fraîche » : c'est une dérive
d'horloge à signaler.

### 8.3 Latence et exécution

La V1 utilise le snapshot connu à la décision, applique la latence simulée et
un haircut de liquidité. Elle ne « regarde pas » le carnet futur pour améliorer
le fill. Si un mode de stress utilise un carnet plus tardif, il doit être
étiqueté comme scénario et ne jamais alimenter la stratégie.

### 8.4 Générateur aléatoire

Tout tirage (jitter de latence, contrôle contraint) utilise un générateur semé.
Le seed et l'identifiant d'implémentation (`rng_implementation`) sont stockés
dans l'expérience.

Le contrat 1.2.0 utilise `polymarket-lab/rng/v2` :

```text
DOMAIN = "polymarket-lab/rng/v2"
seed_bytes = SHA-256(canonical_json([DOMAIN, master_seed, intent_id, purpose]))
u64(counter) = int.from_bytes(SHA-256(seed_bytes || counter[8 bytes BE])[:8], "big")
uniform(low, high) = rejet de u64 >= (2**64 // span) * span, puis low + u64 % span
```

`master_seed` est un entier de `0` à `2^63-1` ; `intent_id` est non vide pour un
ordre et `""` pour l'expérience ; `purpose` vaut `latency` ou `control` ; `span`
est dans `1..2^64`. Un seul tirage logique par `(intent_id, purpose)`. Le mode
`fixed` ne tire pas et impose `latency_jitter_ms=0` ; le haircut est
déterministe. `intent_id = "intent_" + SHA-256(canonical_json(
["polymarket-lab/intent-id/v1", experiment_id, idempotency_key]))[:32]`.
`rng/v1` reste archivé et testé ; aucun résultat v1 n'est recalculé. A1/A2
implémentent la même fonction, A5 recalcule des vecteurs fixés.
`random.Random` n'est pas un contrat reproductible.

### 8.5 Trous et données manquantes

- Une déconnexion, un trou ou un carnet incomplet produit un incident
  `data_quality_incidents`.
- Une période incomplète ne produit pas de métrique « complète » : le snapshot
  porte `data_quality_status` (`complete`, `partial`, `stale`, `gap`).
- Le dashboard et les rapports affichent ces statuts.

### 8.6 Reconstruction du carnet (D-031)

- **Visibilité** : seuls les événements `received_timestamp <= T` et
  `<= manifest.cutoff_received_timestamp` sont visibles à `T`.
- **Ordre décision** : `(received_timestamp, source_timestamp, event_id)`.
  L'ordre `(source_timestamp, received_timestamp, event_id)` est réservé à
  l'audit et ne doit jamais alimenter une décision.
- **Snapshot** : initialise ou resynchronise l'état. Un snapshot plus ancien est
  ignoré avec incident `out_of_order`.
- **Delta sans snapshot** : état `EMPTY`, incident `missing_book`, aucune
  profondeur déduite d'un prix.
- **Séquence** : `seq <= last_seq` = doublon/tardif ignoré ; `seq > last_seq+1`
  = `GAP`, delta non appliqué jusqu'au snapshot suivant ; `seq == last_seq+1`
  s'applique.
- **Hash** : le hash source est opaque. Il n'est comparé que si
  `book_hash_algorithm` est connu et implémenté ; sinon incident
  `book_hash_unverifiable` et état `DEGRADED`. Un hash interne SHA-256 vérifie
  notre reconstruction.
- **Tardif** : un delta reçu après `T` n'est jamais appliqué rétroactivement à
  une décision passée ; lors d'une reconstruction ultérieure, il s'applique à
  son instant de réception.
- **Côté manquant** : accepté mais marqué `incomplete_book` ; A2 refuse ou
  applique un haircut explicite.
- **Coupure** : un delta reçu après le cutoff est exclu. Sans snapshot avant le
  cutoff, l'état est `missing_book`.
- Un carnet dont l'ordre ne peut pas être établi est `DEGRADED`, jamais présenté
  comme fiable. Q-010 reste ouverte.

### 8.7 Historique des prix ≠ historique des carnets

- Un historique de prix (dernier prix, mid, séries de prix) ne contient ni
  profondeur, ni tailles par niveau, ni liquidité exécutable.
- Il est interdit de reconstituer une profondeur historique à partir des seuls
  prix. Un backtest qui a besoin de profondeur exige des snapshots/deltas de
  carnet enregistrés.
- Sans carnet historique, l'exécution reste une **estimation** explicitement
  étiquetée : référence de prix, hypothèse de profondeur, haircut et
  incertitude. Aucun rapport ne doit parler de « backtest d'exécution fidèle ».
- Le paper trading en direct doit enregistrer localement les snapshots, les
  deltas, les trades et les payloads bruts. Un flux de prix seul ne suffit pas.
- `data_quality_incidents` signale les trous de carnet et les périodes où seule
  une série de prix est disponible.

## 9. Périodes et protocole de recherche

Chaque expérience référence une fenêtre et un type :

- `research` : exploration et réglage ;
- `validation` : choix entre variantes et stabilité ;
- `final_test` : période tenue à l'écart jusqu'à la décision finale ;
- `paper_live` : données nouvelles, sans argent réel.

Une fenêtre `final_test` ne peut pas être réutilisée pour choisir des
paramètres. Toute modification après consultation du test final crée une
nouvelle expérience et, si possible, un nouveau test indépendant.

Le manifeste de données fige l'ensemble des événements utilisables. Un
manifeste est identifié par son cutoff de réception, ses filtres, son nombre
d'événements et son SHA-256.

Définitions normatives : voir §2.3.1. `manifest_hash` v2 fige l'en-tête, les
`event_id` triés et les `replacements` triés, pas l'ordre de rejeu. Il exige un
`manifest_seals` valide pour toute lecture as-of. `config_hash` v2 inclut
`code_version` et `config_hash_version` et exclut les champs volatils via
`experiment_config_json`. A1 documente l'implémentation, A5 la recalcule
indépendamment, A2 la partage. Un hash non reproductible invalide l'expérience.

## 10. Benchmarks

Chaque benchmark est une expérience à part entière :

- `delayed_copy` : signal issu des transactions observées, avec latence ;
- `no_signal_control` : contrôle simple, mêmes limites de risque ;
- `passive_baseline` : seulement si une comparaison passive pertinente existe ;
- `constrained_random` : extension ultérieure, mêmes fréquences et expositions,
  sans accès au futur.

Garanties :

- même manifeste de données ;
- mêmes hypothèses d'exécution (latence, haircut, frais) ;
- mêmes limites de risque et même capital ;
- même version de métriques ;
- paramètres figés avant le test final ;
- aucun import des décisions internes du bot évalué.

## 11. Dashboard

Vues minimales :

- synthèse multi-expériences et multi-bots ;
- capital, PnL, drawdown, courbe d'équité ;
- positions ouvertes et historique ;
- ordres, fills, frais et statut de vérification des frais ;
- unité comptable, devise de présentation et actif de règlement, avec la règle
  de conversion utilisée ;
- carnet, spread, profondeur et prix moyen simulé ;
- comparaison trader / bot / benchmark ;
- qualité des données, latence, rejets et incidents ;
- statut `paper_live` et bannière « PAPER TRADING — AUCUN ARGENT RÉEL ».

Le dashboard lit les vues et snapshots. Il ne recalcule pas le PnL et n'écrit
jamais dans le ledger. Il n'applique aucune conversion de présentation sans
règle vérifiée. Les seules actions autorisées sont des contrôles sans effet
financier (pause/reprise d'un bot virtuel), et elles doivent être journalisées.

## 12. Validation

A5 doit couvrir au minimum :

- validation de tous les contrats et de tous les exemples ;
- cas négatifs : payload manquant, type incohérent, unité fausse, timestamp
  non canonique, prix hors borne, propriété inconnue ;
- tests de contrat SQL : clés étrangères, CHECK, index uniques, triggers
  d'immutabilité, vues ;
- idempotence : double append d'un événement, double fill, double transaction ;
- comptabilité : somme nulle, cash/positions/PnL, frais en collatéral et en
  parts, résolution gagnante/perdante, reversal ;
- anti-look-ahead : aucun événement reçu après `T` n'est visible ;
- reproductibilité : même seed + même manifeste + même configuration ⇒ même
  résultat ;
- robustesse : latence, haircut, profondeur insuffisante, carnet périmé,
  frais manquants ;
- benchmarks indépendants et mêmes conventions ;
- audit des biais : survivant, surapprentissage, concentration des gains,
  taille d'échantillon.

Un test non exécuté doit être déclaré comme tel. Un test vert ne prouve pas
une rentabilité.

## 13. Stack et déploiement local Windows

- Python : 3.15.0 est la seule version testée localement ; `requires-python`
  doit rester `>=3.15,<3.16` jusqu'à une matrice de tests. Q-007 reste ouverte.
- `pyproject.toml` (PEP 621) et un lock avec hashes sont requis ; les extras
  `test`, `dashboard` et `research` séparent les dépendances.
- `asyncio` + `websockets` pour les flux.
- Client HTTP : `requests` est le seul client installé et validé localement ;
  il doit être exécuté via `asyncio.to_thread` dans un collecteur asyncio.
  `httpx`/`aiohttp` ne seront ajoutés qu'après installation et validation
  explicites. Aucune dépendance n'est présentée comme validée sans test local.
- `pandas`, `numpy`, `scipy` pour l'analyse ; jamais pour les montants du
  ledger.
- `pytest` pour les tests ; `jsonschema` pour la validation des contrats.
- Streamlit + Plotly pour le dashboard local.
- SQLite + WAL pour la V1 ; PostgreSQL/TimescaleDB seulement si le volume ou la
  concurrence l'exigent.
- `.env.example` ne contient aucun secret. `.env` réel interdit au dépôt.
- Le mode paper doit être explicite et verrouillé ; aucune clé d'ordre réel.

Points bloquants constatés :

- `requirements.txt` n'est pas épinglé ; `jsonschema` est déclaré dans
  `tests/requirements-test.txt` comme dépendance de test, pas en production ;
- `pyproject.toml` est absent alors que `ARCHITECTURE.md` le prévoit ;
- `configs/app.example.yaml` distingue désormais l'unité comptable, la devise
  de présentation et l'actif de règlement ; l'actif de règlement reste porté
  par les métadonnées de marché et doit être vérifié par marché ;
- les seuils `stale_book_threshold_ms`, `max_book_age_ms` et les haircuts
  globaux ne sont que des valeurs par défaut : les valeurs utilisées doivent
  être figées dans `execution_assumptions` de chaque expérience.

## 14. Structure du dépôt

```text
polymarket-strategy-lab/
├── README.md
├── PROJECT_SPEC.md
├── ARCHITECTURE.md
├── SIMULATION_RULES.md
├── VALIDATION_PLAN.md
├── DECISIONS.md
├── pyproject.toml              # à créer
├── .env.example
├── configs/
│   ├── app.example.yaml
│   ├── traders.yaml
│   └── strategies/
├── contracts/
│   ├── README.md
│   ├── CONTRACT_FREEZE_PROPOSAL.md
│   ├── market_event.schema.json
│   ├── execution.schema.json
│   ├── fee_schedule.schema.json
│   ├── experiment.schema.json
│   ├── strategy_hypothesis.schema.json
│   └── examples/
├── schemas/
│   ├── initial_db_schema.sql   # base 0.3
│   └── migrations/
│       ├── README.md
│       └── 0004_consolidation.sql
├── src/
│   └── polymarket_lab/
│       ├── core/               # unités, temps, IDs — propriétaire A1
│       ├── collectors/
│       ├── normalization/
│       ├── storage/
│       ├── analytics/
│       ├── strategies/
│       ├── simulation/
│       ├── ledger/
│       ├── benchmarks/
│       ├── validation/
│       └── dashboard/
├── tests/
│   ├── unit/                    # core/ (A1), simulation/ledger (A2)
│   ├── integration/             # A5
│   ├── accounting/              # A5
│   ├── labtest/                 # fixtures et oracles A5
│   └── fixtures/
│       ├── raw/                 # payloads amont, propriétaire A1
│       └── canonical/           # fixtures canoniques, propriétaire A5
├── data/                       # local, ignoré par Git
├── reports/
└── logs/                       # local, ignoré par Git
```

## 15. Coordination des agents

Avant le travail en parallèle :

1. le propriétaire a approuvé en principe D-009 à D-020 (2026-10-26) ;
2. les critères d'acceptation de `contracts/CONTRACT_FREEZE_PROPOSAL.md` sont
   validés et le gel formel est prononcé ;
3. A5 committe les tests de contrat et de schéma ;
4. A1 peut démarrer sur fixtures + stockage + `core/` sans réseau ;
5. A2 peut démarrer sur carnets et barèmes fictifs explicitement marqués ;
6. A3 et A4 attendent les interfaces gelées ;
7. la collecte réseau attend la documentation exacte des sources par A1.

Toute modification d'interface passe par une proposition A0, un test et une
note de migration. Les agents ne modifient pas simultanément les mêmes
fichiers.

## 16. Points Polymarket — vérification documentaire

**A0 n'a exécuté aucun test réseau.** Les conclusions ci-dessous sont des
vérifications documentaires **rapportées par le propriétaire le 2026-10-26**.
Elles ne constituent ni un test d'endpoint, ni une preuve d'implémentation.
A1 doit documenter les noms exacts, les unités et les dates de consultation
avant toute collecte réseau.

| Sujet | Statut | Reste à faire |
|---|---|---|
| Responsabilités Gamma / CLOB / Data API / temps réel | Documentaire (propriétaire) : sources distinctes, champs non interchangeables | Documenter les endpoints et champs exacts par adaptateur |
| Formule de frais documentée | Documentaire (propriétaire) | Vérifier les paramètres **par marché** ; un taux de catégorie n'est pas une preuve |
| pUSD comme collatéral | Documentaire (propriétaire) | Confirmer par marché, décimales, adresse et réseau |
| Règlement en USDC natif | Documentaire (propriétaire) | Confirmer par marché, règles de conversion, negRisk et VOID |
| Prix vs carnets | Documentaire (propriétaire) : un historique de prix ne donne pas la profondeur | Enregistrer localement snapshots/deltas pour le paper live |
| Endpoints, méthodes, limites de débit | À documenter par A1 | URL officielle + date |
| Timestamps, unités, fuseau | À documenter par A1 | Secondes/ms, précision, ordre |
| Sémantique de `side` | À documenter par A1 | Taker/maker, côté du token de résultat |
| Messages de carnet | À documenter par A1 | Snapshot vs delta, hash/séquence, tick_size_change |
| Types d'activité trader | À documenter par A1 | `TRADE`, `SPLIT`, `MERGE`, `REDEEM`, `REWARD`, `CONVERSION` |
| Historique de carnet | À vérifier | Disponibilité et granularité ; sinon D-005 reste bloquant |
| Doublons inter-sources | À définir | Q-002 |
| Légal / ToS | À vérifier | Usage des données publiques |

Tant que les endpoints, champs et unités exacts ne sont pas documentés par A1,
les collecteurs réseau restent désactivés. Les fixtures, le stockage et la
simulation sur données fictives peuvent avancer.

## 17. Décisions et gel

Voir `DECISIONS.md` :

- **Approuvées en principe (2026-10-26)** : D-009 à D-020, avec les précisions
  D-021 à D-024.
- **D-003 / D-007** : propositions antérieures ; l'avis A0 (SQLite WAL, périodes
  séparées) est intégré.
- **D-004 / D-005 / D-006** : restent à confirmer par marché et par source.
- **D-025** : proposition de gel des contrats ; voir
  `contracts/CONTRACT_FREEZE_PROPOSAL.md`.
- **D-027 à D-039** : principes de consolidation approuvés pour préparation ;
  D-028, D-031, D-033, D-037 et D-039 sous réserve. **D-040** : versionnement
  pré-gel et compatibilité assumée 1.1.0 / 1.0.0. **D-041** : B-04 clos.
  **D-042 à D-053** : spécifications et fichiers candidats P0 (identité v2,
  manifestes/config, RNG v2, migrations 0005/0006/0007, C-01/C-02/C-03,
  validateur applicatif, alignement des fins d'expérience et parcours commun
  d'écriture) au statut PRÉPARÉ, non approuvés et non exécutés. Q-010 à Q-012 restent ouvertes. Aucun
  gel n'est prononcé.

Précisions apportées par la vérification documentaire du propriétaire :

- **D-021** — responsabilités distinctes Gamma / CLOB / Data API / temps réel ;
  champs non interchangeables.
- **D-022** — trois niveaux monétaires : actif de collatéral (pUSD selon la
  documentation actuelle), unité comptable du ledger, actif de règlement (USDC
  natif selon la documentation actuelle), plus la devise de présentation.
- **D-023** — l'historique des prix ne permet pas de reconstituer la profondeur ;
  les carnets sont enregistrés localement pour le paper live.
- **D-024** — la résolution est un événement distinct, avec actif de règlement,
  payout par part et règle de conversion éventuelle.

Le gel formel des contrats reste à prononcer après validation des critères
d'acceptation de `contracts/CONTRACT_FREEZE_PROPOSAL.md`. Tant qu'il n'est pas
prononcé, A1 et A2 peuvent avancer sur fixtures mais ne doivent pas figer leurs
interfaces internes.
