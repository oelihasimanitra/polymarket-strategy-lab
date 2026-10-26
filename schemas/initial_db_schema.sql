-- ============================================================================
-- Polymarket Strategy Research Lab — schéma SQLite initial
-- Version : 0.2 (revue A0 du 2026-10-26)
-- Statut  : PROPOSITION — non gelée tant que D-009 à D-020 ne sont pas validées.
--
-- Conventions non négociables
-- ---------------------------
-- * Tout montant, prix ou taille est un INTEGER en micro-unités (1e-6).
--   - montant / cash / frais / PnL : micro-unités de la devise de collatéral
--     (si USDC : 1 000 000 = 1 USDC) ;
--   - prix : micro-probabilité (1 000 000 = 1.00) ;
--   - taille : micro-parts (1 000 000 = 1 part).
--   Aucun REAL n'est utilisé pour le grand livre.
-- * Timestamps : TEXT UTC canonique, exactement six décimales, suffixe Z.
--   Format : YYYY-MM-DDTHH:MM:SS.ffffffZ
--   Un offset (+00:00) est refusé car il casse le tri lexicographique.
-- * Trois notions monétaires distinctes, jamais confondues :
--   - actif de collatéral du marché      -> markets.collateral_asset ;
--   - unité comptable du ledger          -> experiments.accounting_unit ;
--   - actif de règlement du protocole    -> market_resolution_events.settlement_asset.
--   Aucune conversion implicite ; toute conversion exige une règle sourcée,
--   datée et versionnée (conversion_rule_json).
-- * Sources distinctes : gamma_api, clob_api, data_api, clob_ws, fixture.
--   Leurs champs ne sont pas interchangeables ; chaque adaptateur normalise
--   son propre schéma et conserve la provenance + le payload brut.
-- * Foreign keys : PRAGMA foreign_keys = ON est PAR CONNEXION, pas persistant.
--   L'application doit l'activer à chaque connexion.
-- * Mode WAL recommandé pour la V1 (collecteur + simulateur + dashboard) :
--   PRAGMA journal_mode = WAL; PRAGMA busy_timeout = 5000;
-- * Événements normalisés : append-only. Les corrections passent par une
--   nouvelle version de schéma ou un nouvel event_id, jamais par un UPDATE
--   silencieux. Les écritures comptables (fills, ledger) sont immuables ;
--   toute correction doit être une transaction de reversal.
-- * Idempotence : event_id déterministe, (source, source_event_id) unique,
--   (order_id, fill_index) unique, idempotency_key unique sur les transactions.
-- ============================================================================

PRAGMA foreign_keys = ON;

-- ----------------------------------------------------------------------------
-- 0. Versionnement du schéma
-- ----------------------------------------------------------------------------
CREATE TABLE schema_migrations (
    version    INTEGER PRIMARY KEY,
    name       TEXT NOT NULL,
    applied_at TEXT NOT NULL
) STRICT;

-- ----------------------------------------------------------------------------
-- 1. Référentiels
-- ----------------------------------------------------------------------------
CREATE TABLE traders (
    trader_id         TEXT PRIMARY KEY,
    display_name      TEXT NOT NULL,
    public_identifier TEXT NOT NULL UNIQUE,
    identifier_type   TEXT NOT NULL CHECK (identifier_type IN ('wallet', 'username', 'profile')),
    category          TEXT NOT NULL DEFAULT 'crypto',
    selection_notes   TEXT,
    selected_at       TEXT NOT NULL,
    created_at        TEXT NOT NULL,
    CHECK (selected_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9].[0-9][0-9][0-9][0-9][0-9][0-9]Z'),
    CHECK (created_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9].[0-9][0-9][0-9][0-9][0-9][0-9]Z')
) STRICT;

CREATE TABLE hypotheses (
    hypothesis_id  TEXT PRIMARY KEY,
    trader_id      TEXT NOT NULL REFERENCES traders(trader_id),
    schema_version TEXT NOT NULL,
    document_json  TEXT NOT NULL CHECK (json_valid(document_json)),
    created_at     TEXT NOT NULL,
    CHECK (created_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9].[0-9][0-9][0-9][0-9][0-9][0-9]Z')
) STRICT;

CREATE TABLE markets (
    market_id            TEXT PRIMARY KEY,
    condition_id         TEXT UNIQUE,
    slug                 TEXT,
    question             TEXT,
    category             TEXT,
    end_time             TEXT,
    status               TEXT NOT NULL DEFAULT 'unknown'
                         CHECK (status IN ('active', 'closed', 'resolved', 'void', 'unknown')),
    accepting_orders     INTEGER CHECK (accepting_orders IS NULL OR accepting_orders IN (0, 1)),
    tick_size_micros     INTEGER CHECK (tick_size_micros IS NULL OR tick_size_micros > 0),
    min_order_size_micros INTEGER CHECK (min_order_size_micros IS NULL OR min_order_size_micros >= 0),
    neg_risk             INTEGER CHECK (neg_risk IS NULL OR neg_risk IN (0, 1)),
    -- Actif de collatéral, décimales natives et actif de règlement sont trois
    -- notions distinctes. L'unité comptable du ledger est choisie par expérience.
    collateral_asset     TEXT,
    collateral_decimals  INTEGER CHECK (collateral_decimals IS NULL OR collateral_decimals BETWEEN 0 AND 18),
    settlement_asset     TEXT,
    metadata_json        TEXT NOT NULL DEFAULT '{}' CHECK (json_valid(metadata_json)),
    first_seen_at        TEXT NOT NULL,
    last_seen_at         TEXT,
    source               TEXT,
    CHECK (end_time IS NULL OR end_time GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9].[0-9][0-9][0-9][0-9][0-9][0-9]Z'),
    CHECK (first_seen_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9].[0-9][0-9][0-9][0-9][0-9][0-9]Z'),
    CHECK (last_seen_at IS NULL OR last_seen_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9].[0-9][0-9][0-9][0-9][0-9][0-9]Z')
) STRICT;

-- Projection du dernier état connu. L'historique fait foi dans
-- market_metadata_events ; ne jamais utiliser cette table pour un backtest
-- sans vérifier la métadonnée effective à l'instant de décision.
CREATE TABLE market_tokens (
    token_id      TEXT PRIMARY KEY,
    market_id     TEXT NOT NULL REFERENCES markets(market_id),
    outcome_label TEXT NOT NULL,
    outcome_index INTEGER NOT NULL CHECK (outcome_index >= 0),
    UNIQUE (market_id, outcome_index),
    UNIQUE (market_id, outcome_label)
) STRICT;

-- ----------------------------------------------------------------------------
-- 2. Manifestes de données, frais, stratégies, expériences
-- ----------------------------------------------------------------------------
-- Un manifeste fige l'ensemble des événements utilisables : cutoff de
-- réception (anti-look-ahead) + filtres + hash. Aucun événement reçu après
-- cutoff_received_timestamp ne peut être lu par une expérience.
CREATE TABLE data_manifests (
    manifest_id              TEXT PRIMARY KEY,
    created_at               TEXT NOT NULL,
    cutoff_received_timestamp TEXT NOT NULL,
    filters_json             TEXT NOT NULL CHECK (json_valid(filters_json)),
    first_source_timestamp   TEXT,
    last_source_timestamp    TEXT,
    event_count              INTEGER NOT NULL CHECK (event_count >= 0),
    -- SHA-256 de la séquence ordonnée des event_id filtrés, avec en-tête
    -- (manifest_id + JSON canonique des filtres). Voir ARCHITECTURE.md.
    sha256                   TEXT NOT NULL CHECK (length(sha256) = 64),
    notes                    TEXT NOT NULL DEFAULT '',
    CHECK (created_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9].[0-9][0-9][0-9][0-9][0-9][0-9]Z'),
    CHECK (cutoff_received_timestamp GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9].[0-9][0-9][0-9][0-9][0-9][0-9]Z'),
    CHECK (first_source_timestamp IS NULL OR first_source_timestamp GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9].[0-9][0-9][0-9][0-9][0-9][0-9]Z'),
    CHECK (last_source_timestamp IS NULL OR last_source_timestamp GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9].[0-9][0-9][0-9][0-9][0-9][0-9]Z')
) STRICT;

CREATE TABLE fee_schedules (
    fee_schedule_id          TEXT PRIMARY KEY,
    verification_status      TEXT NOT NULL
                             CHECK (verification_status IN ('verified', 'provisional', 'unverified')),
    source_url               TEXT NOT NULL,
    source_title             TEXT,
    source_retrieved_at      TEXT NOT NULL,
    effective_from           TEXT NOT NULL,
    effective_to             TEXT,
    scope_type               TEXT NOT NULL CHECK (scope_type IN ('global', 'category', 'market')),
    scope_value              TEXT NOT NULL DEFAULT '*',
    -- Preuve que le taux s'applique au périmètre visé. Obligatoire pour un
    -- barème verified global/category : un taux de catégorie n'est pas une preuve
    -- qu'il s'applique à chaque marché.
    scope_evidence_ref       TEXT,
    accounting_unit          TEXT NOT NULL,
    maker_rate_micros        INTEGER NOT NULL CHECK (maker_rate_micros BETWEEN 0 AND 1000000),
    taker_rate_micros        INTEGER NOT NULL CHECK (taker_rate_micros BETWEEN 0 AND 1000000),
    fee_formula              TEXT NOT NULL
                             CHECK (fee_formula IN ('none', 'linear_min_price_1mp', 'notional', 'per_share', 'custom')),
    custom_formula_ref       TEXT,
    fee_charge_unit          TEXT NOT NULL CHECK (fee_charge_unit IN ('collateral', 'outcome_token')),
    rounding_rule            TEXT NOT NULL
                             CHECK (rounding_rule IN ('half_even_micros', 'half_up_micros', 'floor_micros', 'ceil_micros', 'exchange_specific')),
    rounding_increment_micros INTEGER NOT NULL CHECK (rounding_increment_micros > 0),
    notes                    TEXT NOT NULL DEFAULT '',
    supersedes_fee_schedule_id TEXT REFERENCES fee_schedules(fee_schedule_id),
    created_at               TEXT NOT NULL,
    CHECK (effective_to IS NULL OR effective_to > effective_from),
    CHECK (fee_formula <> 'none' OR (maker_rate_micros = 0 AND taker_rate_micros = 0)),
    CHECK (fee_formula <> 'custom' OR custom_formula_ref IS NOT NULL),
    CHECK (verification_status <> 'verified' OR source_url LIKE 'https://%'),
    CHECK (verification_status <> 'verified' OR scope_type = 'market' OR scope_evidence_ref IS NOT NULL),
    CHECK (source_retrieved_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9].[0-9][0-9][0-9][0-9][0-9][0-9]Z'),
    CHECK (effective_from GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9].[0-9][0-9][0-9][0-9][0-9][0-9]Z'),
    CHECK (effective_to IS NULL OR effective_to GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9].[0-9][0-9][0-9][0-9][0-9][0-9]Z'),
    CHECK (created_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9].[0-9][0-9][0-9][0-9][0-9][0-9]Z')
) STRICT;

CREATE TABLE strategies (
    strategy_id     TEXT NOT NULL,
    version         TEXT NOT NULL,
    trader_id       TEXT REFERENCES traders(trader_id),
    hypothesis_id   TEXT NOT NULL REFERENCES hypotheses(hypothesis_id),
    hypothesis_json TEXT NOT NULL CHECK (json_valid(hypothesis_json)),
    config_json     TEXT NOT NULL CHECK (json_valid(config_json)),
    parameters_hash TEXT NOT NULL,
    status          TEXT NOT NULL CHECK (status IN ('draft', 'backtest', 'paper', 'retired')),
    created_at      TEXT NOT NULL,
    retired_at      TEXT,
    PRIMARY KEY (strategy_id, version),
    CHECK (created_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9].[0-9][0-9][0-9][0-9][0-9][0-9]Z'),
    CHECK (retired_at IS NULL OR retired_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9].[0-9][0-9][0-9][0-9][0-9][0-9]Z')
) STRICT;

CREATE TABLE experiments (
    experiment_id              TEXT PRIMARY KEY,
    strategy_id                TEXT NOT NULL,
    strategy_version           TEXT NOT NULL,
    period_type                TEXT NOT NULL
                               CHECK (period_type IN ('research', 'validation', 'final_test', 'paper_live')),
    start_time                 TEXT NOT NULL,
    end_time                   TEXT,
    initial_capital_micros     INTEGER NOT NULL CHECK (initial_capital_micros > 0),
    -- Trois niveaux distincts : unité comptable du ledger, devise d'affichage,
    -- et (par marché) actif de règlement. Aucune conversion implicite.
    accounting_unit            TEXT NOT NULL,
    presentation_currency      TEXT NOT NULL,
    presentation_conversion_json TEXT
                               CHECK (presentation_conversion_json IS NULL OR json_valid(presentation_conversion_json)),
    data_manifest_id           TEXT REFERENCES data_manifests(manifest_id),
    code_version               TEXT NOT NULL,
    config_hash                TEXT NOT NULL,
    execution_assumptions_json TEXT NOT NULL CHECK (json_valid(execution_assumptions_json)),
    risk_limits_json           TEXT NOT NULL CHECK (json_valid(risk_limits_json)),
    default_fee_schedule_id    TEXT REFERENCES fee_schedules(fee_schedule_id),
    fee_status                 TEXT NOT NULL
                               CHECK (fee_status IN ('verified', 'provisional', 'unverified', 'not_required')),
    random_seed                INTEGER NOT NULL CHECK (random_seed >= 0),
    status                     TEXT NOT NULL
                               CHECK (status IN ('planned', 'running', 'completed', 'aborted', 'invalid')),
    created_at                 TEXT NOT NULL,
    completed_at               TEXT,
    FOREIGN KEY (strategy_id, strategy_version) REFERENCES strategies(strategy_id, version),
    CHECK (end_time IS NULL OR end_time > start_time),
    CHECK (period_type = 'paper_live' OR data_manifest_id IS NOT NULL),
    CHECK (fee_status NOT IN ('verified', 'provisional') OR default_fee_schedule_id IS NOT NULL),
    CHECK (start_time GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9].[0-9][0-9][0-9][0-9][0-9][0-9]Z'),
    CHECK (end_time IS NULL OR end_time GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9].[0-9][0-9][0-9][0-9][0-9][0-9]Z'),
    CHECK (created_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9].[0-9][0-9][0-9][0-9][0-9][0-9]Z'),
    CHECK (completed_at IS NULL OR completed_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9].[0-9][0-9][0-9][0-9][0-9][0-9]Z')
) STRICT;

-- ----------------------------------------------------------------------------
-- 3. Événements de marché normalisés (append-only)
-- ----------------------------------------------------------------------------
CREATE TABLE market_events (
    event_id              TEXT PRIMARY KEY,
    schema_version        TEXT NOT NULL,
    event_type            TEXT NOT NULL
                          CHECK (event_type IN ('trade', 'book_snapshot', 'book_delta',
                                                'trader_activity', 'market_metadata',
                                                'market_resolution', 'connection_status')),
    source                TEXT NOT NULL
                          CHECK (source IN ('gamma_api', 'clob_api', 'data_api', 'clob_ws', 'fixture')),
    source_event_id       TEXT,
    source_schema_version TEXT,
    source_timestamp      TEXT NOT NULL
                          CHECK (source_timestamp GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9].[0-9][0-9][0-9][0-9][0-9][0-9]Z'),
    received_timestamp    TEXT NOT NULL
                          CHECK (received_timestamp GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9].[0-9][0-9][0-9][0-9][0-9][0-9]Z'),
    received_monotonic_ns INTEGER,
    ingested_at           TEXT NOT NULL,
    market_id             TEXT REFERENCES markets(market_id),
    token_id              TEXT REFERENCES market_tokens(token_id),
    accounting_unit       TEXT,
    sequence_number       TEXT,
    quality_flags_json    TEXT NOT NULL DEFAULT '[]' CHECK (json_valid(quality_flags_json)),
    raw_payload_ref       TEXT,
    raw_payload_sha256    TEXT CHECK (raw_payload_sha256 IS NULL OR length(raw_payload_sha256) = 64),
    CHECK (raw_payload_ref IS NULL OR raw_payload_sha256 IS NOT NULL),
    CHECK (event_type NOT IN ('trade', 'book_snapshot', 'book_delta', 'market_metadata', 'market_resolution')
           OR market_id IS NOT NULL),
    CHECK (event_type NOT IN ('trade', 'book_snapshot', 'book_delta') OR token_id IS NOT NULL),
    -- L'unité comptable est obligatoire pour les événements qui portent un
    -- notionnel. Ce n'est ni la devise de présentation ni l'actif de règlement.
    CHECK (event_type NOT IN ('trade', 'trader_activity') OR accounting_unit IS NOT NULL),
    CHECK (ingested_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9].[0-9][0-9][0-9][0-9][0-9][0-9]Z')
) STRICT;

CREATE UNIQUE INDEX ux_market_events_source_event
    ON market_events(source, source_event_id)
    WHERE source_event_id IS NOT NULL;

CREATE INDEX idx_market_events_market_time
    ON market_events(market_id, token_id, source_timestamp);
CREATE INDEX idx_market_events_type_time
    ON market_events(event_type, source_timestamp);
CREATE INDEX idx_market_events_token_type_time
    ON market_events(token_id, event_type, source_timestamp);
CREATE INDEX idx_market_events_received
    ON market_events(received_timestamp);

CREATE TABLE trade_events (
    event_id      TEXT PRIMARY KEY REFERENCES market_events(event_id) ON DELETE RESTRICT,
    price_micros  INTEGER NOT NULL CHECK (price_micros BETWEEN 0 AND 1000000),
    size_micros   INTEGER NOT NULL CHECK (size_micros > 0),
    taker_side    TEXT NOT NULL CHECK (taker_side IN ('BUY', 'SELL')),
    trader_id     TEXT REFERENCES traders(trader_id),
    tx_hash       TEXT CHECK (tx_hash IS NULL OR (length(tx_hash) = 66 AND substr(tx_hash, 1, 2) = '0x'))
) STRICT;

CREATE INDEX idx_trade_events_trader ON trade_events(trader_id);

CREATE TABLE trader_activity_events (
    event_id      TEXT PRIMARY KEY REFERENCES market_events(event_id) ON DELETE RESTRICT,
    trader_id     TEXT NOT NULL REFERENCES traders(trader_id),
    activity_type TEXT NOT NULL
                  CHECK (activity_type IN ('TRADE', 'SPLIT', 'MERGE', 'REDEEM', 'REWARD',
                                           'CONVERSION', 'UNKNOWN')),
    side          TEXT CHECK (side IS NULL OR side IN ('BUY', 'SELL')),
    price_micros  INTEGER CHECK (price_micros IS NULL OR price_micros BETWEEN 0 AND 1000000),
    size_micros   INTEGER CHECK (size_micros IS NULL OR size_micros > 0),
    tx_hash       TEXT CHECK (tx_hash IS NULL OR (length(tx_hash) = 66 AND substr(tx_hash, 1, 2) = '0x')),
    CHECK (activity_type <> 'TRADE'
           OR (side IS NOT NULL AND price_micros IS NOT NULL AND size_micros IS NOT NULL))
) STRICT;

CREATE INDEX idx_trader_activity_trader ON trader_activity_events(trader_id);

CREATE TABLE book_snapshots (
    event_id          TEXT PRIMARY KEY REFERENCES market_events(event_id) ON DELETE RESTRICT,
    bids_json         TEXT NOT NULL
                      CHECK (CASE WHEN json_valid(bids_json) THEN json_type(bids_json) = 'array' ELSE 0 END),
    asks_json         TEXT NOT NULL
                      CHECK (CASE WHEN json_valid(asks_json) THEN json_type(asks_json) = 'array' ELSE 0 END),
    book_hash         TEXT,
    tick_size_micros  INTEGER CHECK (tick_size_micros IS NULL OR tick_size_micros > 0)
) STRICT;

CREATE TABLE book_delta_changes (
    event_id      TEXT NOT NULL REFERENCES market_events(event_id) ON DELETE RESTRICT,
    change_index  INTEGER NOT NULL CHECK (change_index >= 0),
    book_side     TEXT NOT NULL CHECK (book_side IN ('BID', 'ASK')),
    action        TEXT NOT NULL CHECK (action IN ('ADD', 'REMOVE', 'REPLACE')),
    price_micros  INTEGER NOT NULL CHECK (price_micros BETWEEN 0 AND 1000000),
    size_micros   INTEGER NOT NULL CHECK (size_micros >= 0),
    PRIMARY KEY (event_id, change_index),
    CHECK (action <> 'REMOVE' OR size_micros = 0),
    CHECK (action = 'REMOVE' OR size_micros > 0)
) STRICT;

CREATE TABLE market_metadata_events (
    event_id                TEXT PRIMARY KEY REFERENCES market_events(event_id) ON DELETE RESTRICT,
    condition_id            TEXT,
    question                TEXT,
    slug                    TEXT,
    category                TEXT,
    end_time                TEXT,
    status                  TEXT NOT NULL
                            CHECK (status IN ('active', 'closed', 'resolved', 'void', 'unknown')),
    accepting_orders        INTEGER CHECK (accepting_orders IS NULL OR accepting_orders IN (0, 1)),
    tick_size_micros        INTEGER CHECK (tick_size_micros IS NULL OR tick_size_micros > 0),
    min_order_size_micros   INTEGER CHECK (min_order_size_micros IS NULL OR min_order_size_micros >= 0),
    neg_risk                INTEGER CHECK (neg_risk IS NULL OR neg_risk IN (0, 1)),
    collateral_asset        TEXT NOT NULL,
    collateral_decimals     INTEGER NOT NULL CHECK (collateral_decimals BETWEEN 0 AND 18),
    settlement_asset        TEXT,
    outcomes_json           TEXT NOT NULL
                            CHECK (CASE WHEN json_valid(outcomes_json)
                                        THEN json_array_length(outcomes_json) >= 2 ELSE 0 END),
    CHECK (end_time IS NULL OR end_time GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9].[0-9][0-9][0-9][0-9][0-9][0-9]Z')
) STRICT;

CREATE TABLE market_resolution_events (
    event_id          TEXT PRIMARY KEY REFERENCES market_events(event_id) ON DELETE RESTRICT,
    resolution_status TEXT NOT NULL CHECK (resolution_status IN ('RESOLVED', 'VOID')),
    winning_token_id  TEXT REFERENCES market_tokens(token_id),
    resolved_at       TEXT NOT NULL,
    resolution_source TEXT NOT NULL,
    settlement_asset  TEXT,
    payout_per_share_micros INTEGER
                      CHECK (payout_per_share_micros IS NULL OR payout_per_share_micros BETWEEN 0 AND 1000000),
    conversion_rule_json TEXT
                      CHECK (conversion_rule_json IS NULL OR json_valid(conversion_rule_json)),
    notes             TEXT,
    CHECK (resolution_status <> 'RESOLVED' OR winning_token_id IS NOT NULL),
    CHECK (resolution_status <> 'RESOLVED'
           OR (settlement_asset IS NOT NULL AND payout_per_share_micros IS NOT NULL)),
    CHECK (resolution_status <> 'VOID' OR winning_token_id IS NULL),
    CHECK (resolved_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9].[0-9][0-9][0-9][0-9][0-9][0-9]Z')
) STRICT;

CREATE TABLE connection_events (
    event_id           TEXT PRIMARY KEY REFERENCES market_events(event_id) ON DELETE RESTRICT,
    stream_id          TEXT NOT NULL,
    status             TEXT NOT NULL
                       CHECK (status IN ('CONNECTED', 'DISCONNECTED', 'RECONNECTING', 'ERROR', 'CLOSED')),
    reason             TEXT,
    gap_start_timestamp TEXT,
    gap_end_timestamp   TEXT,
    CHECK (gap_start_timestamp IS NULL OR gap_end_timestamp IS NULL
           OR gap_end_timestamp >= gap_start_timestamp),
    CHECK (gap_start_timestamp IS NULL OR gap_start_timestamp GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9].[0-9][0-9][0-9][0-9][0-9][0-9]Z'),
    CHECK (gap_end_timestamp IS NULL OR gap_end_timestamp GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9].[0-9][0-9][0-9][0-9][0-9][0-9]Z')
) STRICT;

-- Un détail doit correspondre au type de son enveloppe. Sans ces triggers, une
-- ligne trade_events pourrait être rattachée à un book_snapshot.
CREATE TRIGGER trg_trade_events_type
BEFORE INSERT ON trade_events
WHEN (SELECT event_type FROM market_events WHERE event_id = NEW.event_id) IS NOT 'trade'
BEGIN
    SELECT RAISE(ABORT, 'trade_events exige event_type=trade');
END;

CREATE TRIGGER trg_trader_activity_events_type
BEFORE INSERT ON trader_activity_events
WHEN (SELECT event_type FROM market_events WHERE event_id = NEW.event_id) IS NOT 'trader_activity'
BEGIN
    SELECT RAISE(ABORT, 'trader_activity_events exige event_type=trader_activity');
END;

CREATE TRIGGER trg_book_snapshots_type
BEFORE INSERT ON book_snapshots
WHEN (SELECT event_type FROM market_events WHERE event_id = NEW.event_id) IS NOT 'book_snapshot'
BEGIN
    SELECT RAISE(ABORT, 'book_snapshots exige event_type=book_snapshot');
END;

CREATE TRIGGER trg_book_delta_changes_type
BEFORE INSERT ON book_delta_changes
WHEN (SELECT event_type FROM market_events WHERE event_id = NEW.event_id) IS NOT 'book_delta'
BEGIN
    SELECT RAISE(ABORT, 'book_delta_changes exige event_type=book_delta');
END;

CREATE TRIGGER trg_market_metadata_events_type
BEFORE INSERT ON market_metadata_events
WHEN (SELECT event_type FROM market_events WHERE event_id = NEW.event_id) IS NOT 'market_metadata'
BEGIN
    SELECT RAISE(ABORT, 'market_metadata_events exige event_type=market_metadata');
END;

CREATE TRIGGER trg_market_resolution_events_type
BEFORE INSERT ON market_resolution_events
WHEN (SELECT event_type FROM market_events WHERE event_id = NEW.event_id) IS NOT 'market_resolution'
BEGIN
    SELECT RAISE(ABORT, 'market_resolution_events exige event_type=market_resolution');
END;

CREATE TRIGGER trg_connection_events_type
BEFORE INSERT ON connection_events
WHEN (SELECT event_type FROM market_events WHERE event_id = NEW.event_id) IS NOT 'connection_status'
BEGIN
    SELECT RAISE(ABORT, 'connection_events exige event_type=connection_status');
END;

-- Incidents de qualité : trous, reconnexions, lateness, dérive d'horloge,
-- doublons inter-sources, hash de carnet incohérent, etc. Le dashboard et les
-- rapports doivent les afficher ; une période incomplète ne doit pas produire
-- silencieusement des métriques complètes.
CREATE TABLE data_quality_incidents (
    incident_id   TEXT PRIMARY KEY,
    incident_type TEXT NOT NULL
                  CHECK (incident_type IN ('feed_disconnected', 'feed_gap', 'stale_book',
                                           'late_event', 'duplicate_event', 'cross_source_duplicate',
                                           'invalid_payload', 'out_of_order', 'clock_skew',
                                           'missing_book_side', 'book_hash_mismatch',
                                           'metadata_missing', 'unknown_activity_type', 'other')),
    stream_id     TEXT,
    market_id     TEXT REFERENCES markets(market_id),
    token_id      TEXT REFERENCES market_tokens(token_id),
    start_time    TEXT NOT NULL,
    end_time      TEXT,
    detected_at   TEXT NOT NULL,
    severity      TEXT NOT NULL CHECK (severity IN ('info', 'warning', 'error', 'critical')),
    details_json  TEXT NOT NULL DEFAULT '{}' CHECK (json_valid(details_json)),
    resolved_at   TEXT,
    CHECK (end_time IS NULL OR end_time >= start_time),
    CHECK (start_time GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9].[0-9][0-9][0-9][0-9][0-9][0-9]Z'),
    CHECK (end_time IS NULL OR end_time GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9].[0-9][0-9][0-9][0-9][0-9][0-9]Z'),
    CHECK (detected_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9].[0-9][0-9][0-9][0-9][0-9][0-9]Z'),
    CHECK (resolved_at IS NULL OR resolved_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9].[0-9][0-9][0-9][0-9][0-9][0-9]Z')
) STRICT;

CREATE INDEX idx_incidents_stream_time ON data_quality_incidents(stream_id, start_time);
CREATE INDEX idx_incidents_market_time ON data_quality_incidents(market_id, start_time);

-- ----------------------------------------------------------------------------
-- 4. Simulation : intentions -> estimation -> ordres -> fills
-- ----------------------------------------------------------------------------
CREATE TABLE simulated_orders (
    order_id                 TEXT PRIMARY KEY,
    idempotency_key          TEXT NOT NULL UNIQUE,
    experiment_id            TEXT NOT NULL REFERENCES experiments(experiment_id),
    market_id                TEXT NOT NULL REFERENCES markets(market_id),
    token_id                 TEXT NOT NULL REFERENCES market_tokens(token_id),
    order_type               TEXT NOT NULL DEFAULT 'taker' CHECK (order_type IN ('taker')),
    side                     TEXT NOT NULL CHECK (side IN ('BUY', 'SELL')),
    requested_size_micros    INTEGER NOT NULL CHECK (requested_size_micros > 0),
    limit_price_micros       INTEGER NOT NULL CHECK (limit_price_micros BETWEEN 0 AND 1000000),
    status                   TEXT NOT NULL
                             CHECK (status IN ('proposed', 'accepted', 'partially_filled',
                                               'filled', 'expired', 'rejected')),
    rejection_reason         TEXT CHECK (rejection_reason IS NULL OR rejection_reason IN
                                         ('stale_book', 'missing_book', 'insufficient_liquidity',
                                          'missing_fee_schedule', 'risk_limit', 'invalid_order', 'other')),
    decision_timestamp       TEXT NOT NULL,
    simulated_arrival_timestamp TEXT,
    book_snapshot_event_id   TEXT REFERENCES market_events(event_id),
    assumptions_json         TEXT NOT NULL CHECK (json_valid(assumptions_json)),
    accounting_unit          TEXT NOT NULL,
    created_at               TEXT NOT NULL,
    CHECK (status <> 'rejected' OR rejection_reason IS NOT NULL),
    CHECK (simulated_arrival_timestamp IS NULL OR simulated_arrival_timestamp >= decision_timestamp),
    CHECK (status IN ('proposed', 'rejected') OR book_snapshot_event_id IS NOT NULL),
    CHECK (decision_timestamp GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9].[0-9][0-9][0-9][0-9][0-9][0-9]Z'),
    CHECK (simulated_arrival_timestamp IS NULL OR simulated_arrival_timestamp GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9].[0-9][0-9][0-9][0-9][0-9][0-9]Z'),
    CHECK (created_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9].[0-9][0-9][0-9][0-9][0-9][0-9]Z')
) STRICT;

CREATE INDEX idx_orders_experiment_time ON simulated_orders(experiment_id, decision_timestamp);
CREATE INDEX idx_orders_status ON simulated_orders(status);
CREATE INDEX idx_orders_market_token ON simulated_orders(experiment_id, market_id, token_id);

CREATE TABLE execution_estimates (
    estimate_id              TEXT PRIMARY KEY,
    order_id                 TEXT NOT NULL UNIQUE REFERENCES simulated_orders(order_id),
    book_snapshot_event_id   TEXT NOT NULL REFERENCES market_events(event_id),
    arrival_timestamp        TEXT NOT NULL,
    status                   TEXT NOT NULL CHECK (status IN ('accepted', 'partial', 'rejected')),
    accounting_unit          TEXT NOT NULL,
    executable_size_micros   INTEGER NOT NULL CHECK (executable_size_micros >= 0),
    unfilled_size_micros     INTEGER NOT NULL CHECK (unfilled_size_micros >= 0),
    vwap_micros              INTEGER CHECK (vwap_micros IS NULL OR vwap_micros BETWEEN 0 AND 1000000),
    levels_json              TEXT NOT NULL
                             CHECK (CASE WHEN json_valid(levels_json)
                                         THEN json_type(levels_json) = 'array' ELSE 0 END),
    assumptions_json         TEXT NOT NULL CHECK (json_valid(assumptions_json)),
    fee_calculation_json     TEXT CHECK (fee_calculation_json IS NULL OR json_valid(fee_calculation_json)),
    rejection_reason         TEXT CHECK (rejection_reason IS NULL OR rejection_reason IN
                                         ('stale_book', 'missing_book', 'insufficient_liquidity',
                                          'missing_fee_schedule', 'risk_limit', 'invalid_order', 'other')),
    created_at               TEXT NOT NULL,
    CHECK (status <> 'rejected' OR rejection_reason IS NOT NULL),
    CHECK (status <> 'rejected' OR (executable_size_micros = 0 AND vwap_micros IS NULL)),
    CHECK (status = 'rejected' OR (vwap_micros IS NOT NULL AND fee_calculation_json IS NOT NULL)),
    CHECK (arrival_timestamp GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9].[0-9][0-9][0-9][0-9][0-9][0-9]Z'),
    CHECK (created_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9].[0-9][0-9][0-9][0-9][0-9][0-9]Z')
) STRICT;

CREATE TABLE simulated_fills (
    fill_id                TEXT PRIMARY KEY,
    order_id               TEXT NOT NULL REFERENCES simulated_orders(order_id),
    fill_index             INTEGER NOT NULL CHECK (fill_index >= 0),
    level_index            INTEGER NOT NULL CHECK (level_index >= 0),
    price_micros           INTEGER NOT NULL CHECK (price_micros BETWEEN 0 AND 1000000),
    size_micros            INTEGER NOT NULL CHECK (size_micros > 0),
    notional_micros        INTEGER NOT NULL CHECK (notional_micros >= 0),
    fee_schedule_id        TEXT NOT NULL REFERENCES fee_schedules(fee_schedule_id),
    fee_formula            TEXT NOT NULL
                           CHECK (fee_formula IN ('none', 'linear_min_price_1mp', 'notional', 'per_share', 'custom')),
    rate_micros            INTEGER NOT NULL CHECK (rate_micros BETWEEN 0 AND 1000000),
    -- fee_amount_micros est exprimé dans fee_unit. Les colonnes fee_* sont
    -- autoritatives ; fee_calculation_json est le détail d'audit.
    fee_unit               TEXT NOT NULL CHECK (fee_unit IN ('collateral', 'outcome_token')),
    fee_amount_micros      INTEGER NOT NULL CHECK (fee_amount_micros >= 0),
    fee_calculation_json   TEXT NOT NULL CHECK (json_valid(fee_calculation_json)),
    accounting_unit        TEXT NOT NULL,
    book_snapshot_event_id TEXT NOT NULL REFERENCES market_events(event_id),
    fill_timestamp         TEXT NOT NULL,
    created_at             TEXT NOT NULL,
    UNIQUE (order_id, fill_index),
    CHECK (fill_timestamp GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9].[0-9][0-9][0-9][0-9][0-9][0-9]Z'),
    CHECK (created_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9].[0-9][0-9][0-9][0-9][0-9][0-9]Z')
) STRICT;

CREATE INDEX idx_fills_order ON simulated_fills(order_id);

CREATE TRIGGER trg_simulated_fills_no_update
BEFORE UPDATE ON simulated_fills
BEGIN
    SELECT RAISE(ABORT, 'simulated_fills est append-only');
END;

CREATE TRIGGER trg_simulated_fills_no_delete
BEFORE DELETE ON simulated_fills
BEGIN
    SELECT RAISE(ABORT, 'simulated_fills est append-only');
END;

-- ----------------------------------------------------------------------------
-- 5. Grand livre en partie double (source de vérité comptable)
-- ----------------------------------------------------------------------------
-- Convention de signe : amount_micros > 0 = débit, < 0 = crédit.
-- Comptes :
--   CASH          actif, débit = augmentation du cash
--   POSITION      actif, débit = coût d'acquisition ; quantity_micros = parts
--   FEES          charge, débit = frais payés
--   REALIZED_PNL  produit/charge, crédit = gain réalisé, débit = perte réalisée
--   CAPITAL       capitaux propres, crédit = apport initial
-- Invariant : somme(amount_micros) = 0 par transaction.
-- Invariant : le solde du compte POSITION n'est jamais négatif (pas de short).
-- Invariant : CASH >= 0 (aucun effet de levier en V1).
-- Toute correction = transaction de reversal, jamais UPDATE/DELETE.
CREATE TABLE ledger_transactions (
    transaction_id TEXT PRIMARY KEY,
    experiment_id  TEXT NOT NULL REFERENCES experiments(experiment_id),
    occurred_at    TEXT NOT NULL,
    kind           TEXT NOT NULL
                   CHECK (kind IN ('deposit', 'withdrawal', 'fill', 'fee', 'settlement',
                                   'adjustment', 'reversal')),
    ref_type       TEXT NOT NULL CHECK (ref_type IN ('fill', 'market_resolution', 'manual', 'experiment')),
    ref_id         TEXT NOT NULL,
    idempotency_key TEXT NOT NULL UNIQUE,
    memo           TEXT NOT NULL DEFAULT '',
    created_at     TEXT NOT NULL,
    UNIQUE (ref_type, ref_id, kind),
    CHECK (occurred_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9].[0-9][0-9][0-9][0-9][0-9][0-9]Z'),
    CHECK (created_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9].[0-9][0-9][0-9][0-9][0-9][0-9]Z')
) STRICT;

CREATE INDEX idx_ledger_tx_experiment_time ON ledger_transactions(experiment_id, occurred_at);
CREATE INDEX idx_ledger_tx_ref ON ledger_transactions(ref_type, ref_id);

CREATE TABLE ledger_postings (
    posting_id      INTEGER PRIMARY KEY,
    transaction_id  TEXT NOT NULL REFERENCES ledger_transactions(transaction_id),
    account         TEXT NOT NULL
                    CHECK (account IN ('CASH', 'POSITION', 'FEES', 'REALIZED_PNL', 'CAPITAL')),
    token_id        TEXT REFERENCES market_tokens(token_id),
    amount_micros   INTEGER NOT NULL,
    quantity_micros INTEGER,
    accounting_unit TEXT NOT NULL,
    CHECK ((account = 'POSITION') = (quantity_micros IS NOT NULL)),
    CHECK (account <> 'POSITION' OR quantity_micros <> 0)
) STRICT;

CREATE INDEX idx_ledger_postings_transaction ON ledger_postings(transaction_id);
CREATE INDEX idx_ledger_postings_account_token ON ledger_postings(account, token_id);

CREATE TRIGGER trg_ledger_transactions_no_update
BEFORE UPDATE ON ledger_transactions
BEGIN
    SELECT RAISE(ABORT, 'ledger_transactions est append-only');
END;

CREATE TRIGGER trg_ledger_transactions_no_delete
BEFORE DELETE ON ledger_transactions
BEGIN
    SELECT RAISE(ABORT, 'ledger_transactions est append-only');
END;

CREATE TRIGGER trg_ledger_postings_no_update
BEFORE UPDATE ON ledger_postings
BEGIN
    SELECT RAISE(ABORT, 'ledger_postings est append-only');
END;

CREATE TRIGGER trg_ledger_postings_no_delete
BEFORE DELETE ON ledger_postings
BEGIN
    SELECT RAISE(ABORT, 'ledger_postings est append-only');
END;

-- ----------------------------------------------------------------------------
-- 6. Snapshots de portefeuille, métriques, benchmarks
-- ----------------------------------------------------------------------------
CREATE TABLE portfolio_snapshots (
    snapshot_id             TEXT PRIMARY KEY,
    experiment_id           TEXT NOT NULL REFERENCES experiments(experiment_id),
    as_of_timestamp         TEXT NOT NULL,
    cash_micros             INTEGER NOT NULL CHECK (cash_micros >= 0),
    positions_value_micros  INTEGER NOT NULL CHECK (positions_value_micros >= 0),
    equity_micros           INTEGER NOT NULL,
    realized_pnl_micros     INTEGER NOT NULL,
    unrealized_pnl_micros   INTEGER NOT NULL,
    -- Frais en collatéral uniquement. Les frais prélevés en parts sont
    -- représentés par la réduction de position et le PnL réalisé du ledger.
    fees_paid_micros        INTEGER NOT NULL CHECK (fees_paid_micros >= 0),
    accounting_unit         TEXT NOT NULL,
    valuation_method        TEXT NOT NULL
                            CHECK (valuation_method IN ('executable_bid_book', 'mid_price_reference', 'none')),
    data_quality_status     TEXT NOT NULL
                            CHECK (data_quality_status IN ('complete', 'partial', 'stale', 'gap')),
    metrics_json            TEXT NOT NULL DEFAULT '{}' CHECK (json_valid(metrics_json)),
    created_at              TEXT NOT NULL,
    UNIQUE (experiment_id, as_of_timestamp),
    CHECK (equity_micros = cash_micros + positions_value_micros),
    CHECK (as_of_timestamp GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9].[0-9][0-9][0-9][0-9][0-9][0-9]Z'),
    CHECK (created_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9].[0-9][0-9][0-9][0-9][0-9][0-9]Z')
) STRICT;

CREATE TABLE experiment_metrics (
    experiment_id  TEXT NOT NULL REFERENCES experiments(experiment_id),
    metric_key     TEXT NOT NULL,
    value_micros   INTEGER,
    value_real     REAL,
    unit           TEXT NOT NULL,
    sample_size    INTEGER CHECK (sample_size IS NULL OR sample_size >= 0),
    metrics_version TEXT NOT NULL,
    computed_at    TEXT NOT NULL,
    PRIMARY KEY (experiment_id, metric_key),
    CHECK ((value_micros IS NULL) <> (value_real IS NULL)),
    CHECK (computed_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9].[0-9][0-9][0-9][0-9][0-9][0-9]Z')
) STRICT;

CREATE TABLE benchmark_runs (
    benchmark_run_id        TEXT PRIMARY KEY,
    evaluated_experiment_id TEXT NOT NULL REFERENCES experiments(experiment_id),
    benchmark_experiment_id TEXT NOT NULL UNIQUE REFERENCES experiments(experiment_id),
    benchmark_type          TEXT NOT NULL
                            CHECK (benchmark_type IN ('delayed_copy', 'no_signal_control',
                                                      'passive_baseline', 'constrained_random')),
    comparison_json         TEXT NOT NULL CHECK (json_valid(comparison_json)),
    metrics_version         TEXT NOT NULL,
    created_at              TEXT NOT NULL,
    UNIQUE (evaluated_experiment_id, benchmark_type, benchmark_experiment_id),
    CHECK (evaluated_experiment_id <> benchmark_experiment_id),
    CHECK (created_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9].[0-9][0-9][0-9][0-9][0-9][0-9]Z')
) STRICT;

CREATE INDEX idx_benchmarks_evaluated ON benchmark_runs(evaluated_experiment_id);

-- ----------------------------------------------------------------------------
-- 7. Vues de lecture (dashboard et audit)
-- ----------------------------------------------------------------------------
CREATE VIEW v_experiment_cash AS
SELECT
    e.experiment_id,
    e.accounting_unit,
    COALESCE(SUM(p.amount_micros), 0) AS cash_micros
FROM experiments e
LEFT JOIN ledger_transactions t ON t.experiment_id = e.experiment_id
LEFT JOIN ledger_postings p ON p.transaction_id = t.transaction_id AND p.account = 'CASH'
GROUP BY e.experiment_id, e.accounting_unit;

CREATE VIEW v_experiment_positions AS
SELECT
    t.experiment_id,
    e.accounting_unit,
    p.token_id,
    mt.market_id,
    mt.outcome_label,
    SUM(p.quantity_micros) AS quantity_micros,
    SUM(p.amount_micros)   AS remaining_cost_basis_micros
FROM ledger_transactions t
JOIN experiments e ON e.experiment_id = t.experiment_id
JOIN ledger_postings p ON p.transaction_id = t.transaction_id AND p.account = 'POSITION'
JOIN market_tokens mt ON mt.token_id = p.token_id
GROUP BY t.experiment_id, e.accounting_unit, p.token_id, mt.market_id, mt.outcome_label
HAVING SUM(p.quantity_micros) <> 0 OR SUM(p.amount_micros) <> 0;

CREATE VIEW v_order_execution AS
SELECT
    o.order_id,
    o.experiment_id,
    o.accounting_unit,
    o.side,
    o.requested_size_micros,
    COALESCE(SUM(f.size_micros), 0) AS filled_size_micros,
    CASE
        WHEN COALESCE(SUM(f.size_micros), 0) = 0 THEN NULL
        ELSE CAST((SUM(f.price_micros * f.size_micros) + SUM(f.size_micros) / 2)
                  / SUM(f.size_micros) AS INTEGER)
    END AS vwap_micros,
    COALESCE(SUM(CASE WHEN f.fee_unit = 'collateral' THEN f.fee_amount_micros ELSE 0 END), 0)
        AS fees_collateral_micros,
    COALESCE(SUM(CASE WHEN f.fee_unit = 'outcome_token' THEN f.fee_amount_micros ELSE 0 END), 0)
        AS fees_outcome_micros,
    COUNT(f.fill_id) AS fill_count
FROM simulated_orders o
LEFT JOIN simulated_fills f ON f.order_id = o.order_id
GROUP BY o.order_id, o.experiment_id, o.accounting_unit, o.side, o.requested_size_micros;

CREATE VIEW v_ledger_anomalies AS
SELECT
    t.transaction_id,
    t.experiment_id,
    COUNT(p.posting_id) AS posting_count,
    COALESCE(SUM(p.amount_micros), 0) AS imbalance_micros
FROM ledger_transactions t
LEFT JOIN ledger_postings p ON p.transaction_id = t.transaction_id
GROUP BY t.transaction_id, t.experiment_id
HAVING COUNT(p.posting_id) < 2 OR COALESCE(SUM(p.amount_micros), 0) <> 0;

CREATE VIEW v_experiment_latest_snapshot AS
SELECT ps.*
FROM portfolio_snapshots ps
JOIN (
    SELECT experiment_id, MAX(as_of_timestamp) AS max_as_of
    FROM portfolio_snapshots
    GROUP BY experiment_id
) latest
ON latest.experiment_id = ps.experiment_id
AND latest.max_as_of = ps.as_of_timestamp;

-- Audit : un solde de cash négatif viole l'interdiction de levier de la V1.
CREATE VIEW v_negative_cash AS
SELECT
    t.experiment_id,
    SUM(p.amount_micros) AS cash_micros
FROM ledger_transactions t
JOIN ledger_postings p ON p.transaction_id = t.transaction_id AND p.account = 'CASH'
GROUP BY t.experiment_id
HAVING SUM(p.amount_micros) < 0;

-- Audit : une quantité de position négative viole l'interdiction du short.
CREATE VIEW v_position_anomalies AS
SELECT
    t.experiment_id,
    p.token_id,
    SUM(p.quantity_micros) AS quantity_micros
FROM ledger_transactions t
JOIN ledger_postings p ON p.transaction_id = t.transaction_id AND p.account = 'POSITION'
GROUP BY t.experiment_id, p.token_id
HAVING SUM(p.quantity_micros) < 0;

PRAGMA user_version = 1;
