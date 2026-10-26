# ARCHITECTURE.md
# Polymarket Strategy Research Lab — Architecture technique

- **Version :** 0.2 — revue A0 du 2026-10-26
- **Statut :** proposition à valider par le propriétaire. Les contrats `1.0.0` et le schéma SQL `0.2` ne sont pas gelés.
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
  Recommandation A0 : `evt_` + SHA-256 tronqué de
  `(source, source_event_id ou contenu canonique, market_id, token_id,
  source_timestamp)`. A1 doit documenter la formule exacte.
- `(source, source_event_id)` est unique lorsqu'il existe. Un redémarrage ou une
  reconnexion ne doit pas créer un doublon.
- Les doublons **inter-sources** (même trade vu par REST et WebSocket) ne sont
  pas garantis par cette contrainte. Ils doivent être détectés et signalés
  (`cross_source_duplicate`), pas fusionnés arbitrairement.
- Chaque ordre porte une `idempotency_key` unique par expérience.
- Chaque fill est unique par `(order_id, fill_index)`.
- Chaque transaction du grand livre porte une `idempotency_key` unique et une
  contrainte `(ref_type, ref_id, kind)`.

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
- Un ajout de champ est une nouvelle version mineure ; un changement de type,
  d'unité ou de sémantique est une version majeure.
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

Le schéma complet est dans `schemas/initial_db_schema.sql` (version 0.2).

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

Le schéma SQL est volontairement plus strict que le contrat JSON. Le contrat
valide la forme d'un document ; le SQL protège les invariants persistés.

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

Si un frais est prélevé en parts (`fee_charge_unit = outcome_token`), la
position diminue en quantité et en coût, et la perte correspondante est
comptabilisée dans `REALIZED_PNL`. Le frais ne crée jamais de cash. Un frais en
parts ne peut être prélevé que sur une position existante ; si le prélèvement
rendrait la quantité négative, le fill est rejeté, sauf règle officielle
vérifiée de conversion en collatéral.

Sur une cession partielle, le coût retiré est arrondi selon la règle de
l'expérience ; le dernier lot absorbe le résidu pour que le coût restant soit
nul après clôture complète. `fees_paid_micros` dans un snapshot ne compte que
les frais en collatéral ; les frais en parts sont représentés par la réduction
de position et la perte réalisée.

### 7.3 Invariants comptables

1. Somme des `amount_micros` = 0 pour chaque transaction.
2. `CASH >= 0` ; aucune marge, aucun effet de levier en V1.
3. Quantité de position `>= 0` ; aucun short implicite.
4. Un fill produit exactement une transaction, clé `fill:<fill_id>`.
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

## 8. Qualité des données et anti-look-ahead

### 8.1 Visibilité d'une décision

À l'instant de décision `T`, une stratégie ne peut lire que les événements
vérifiant :

```text
received_timestamp <= T
et, si un manifeste est utilisé :
received_timestamp <= manifest.cutoff_received_timestamp
```

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

Tout tirage (jitter de latence, haircut aléatoire, contrôle contraint) utilise
un générateur semé. Le seed et l'implémentation exacte
(`rng_implementation`) sont stockés dans l'expérience. Deux implémentations
différentes ne sont pas comparables.

### 8.5 Trous et données manquantes

- Une déconnexion, un trou ou un carnet incomplet produit un incident
  `data_quality_incidents`.
- Une période incomplète ne produit pas de métrique « complète » : le snapshot
  porte `data_quality_status` (`complete`, `partial`, `stale`, `gap`).
- Le dashboard et les rapports affichent ces statuts.

### 8.6 Historique des prix ≠ historique des carnets

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

Définition du hash : SHA-256 de l'enchaînement UTF-8, une ligne par `event_id`,
dans l'ordre de rejeu `(source_timestamp, received_timestamp, event_id)`, après
application des filtres et du cutoff, précédé d'une ligne d'en-tête contenant
`manifest_id` et le JSON canonique des filtres. A1 documente la fonction ;
A5 la recalcule et la compare. Un hash non reproductible invalide l'expérience.

De même, `config_hash` est le SHA-256 du JSON canonique (clés triées, sans
espaces) de `{strategy_id, version, config_json, execution_assumptions,
risk_limits, fees, capital, period, data.filters, code_version}`. A1, A2 et A5
partagent la même fonction.

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

- Python : 3.15.0 vérifié dans l'environnement local de cette revue.
  La version doit être verrouillée dans `pyproject.toml` (fichier absent à ce
  jour) et les dépendances épinglées.
- `asyncio` + `websockets` pour les flux.
- Client HTTP : `requests` est synchrone ; dans un collecteur asyncio, utiliser
  un client asynchrone (`httpx` ou `aiohttp`) ou exécuter les appels dans un
  thread. Ce point est à trancher par A1.
- `pandas`, `numpy`, `scipy` pour l'analyse ; jamais pour les montants du
  ledger.
- `pytest` pour les tests ; `jsonschema` pour la validation des contrats.
- Streamlit + Plotly pour le dashboard local.
- SQLite + WAL pour la V1 ; PostgreSQL/TimescaleDB seulement si le volume ou la
  concurrence l'exigent.
- `.env.example` ne contient aucun secret. `.env` réel interdit au dépôt.
- Le mode paper doit être explicite et verrouillé ; aucune clé d'ordre réel.

Points bloquants constatés :

- `requirements.txt` n'est pas épinglé et ne liste pas `jsonschema` ;
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
│   └── initial_db_schema.sql
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
│   ├── unit/
│   ├── integration/
│   ├── accounting/
│   └── fixtures/
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
