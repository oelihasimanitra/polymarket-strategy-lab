-- ============================================================================
-- Polymarket Strategy Research Lab — schéma SQLite initial
-- Version : 0.3 (correction A0 après audit A5 du 2026-10-27)
-- Statut  : PROPOSITION — non gelée ; voir DECISIONS.md D-025 et le rapport A0.
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
-- * Triggers récursifs : PRAGMA recursive_triggers = ON est PAR CONNEXION.
--   Il est requis pour que les triggers DELETE se déclenchent aussi lors d'un
--   INSERT OR REPLACE. L'application doit l'activer ; les triggers UPDATE/DELETE
--   protègent les UPDATE/DELETE directs, pas DROP TABLE / ALTER TABLE.
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
PRAGMA recursive_triggers = ON;

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
    UNIQUE (market_id, outcome_label),
    -- Cible des FK composites (market_id, token_id) : un token appartient à un
    -- seul marché. Le UNIQUE sur token_id seul (PK) ne prouve pas cette
    -- appartenance ; cette contrainte la rend vérifiable par SQLite.
    UNIQUE (market_id, token_id)
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
    -- Version du document fee_schedule persisté. Les barèmes existants sont en
    -- 1.0.0 ; la colonne rend une future évolution traçable sans migration
    -- silencieuse.
    schema_version           TEXT NOT NULL DEFAULT '1.0.0',
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
    CHECK (length(accounting_unit) BETWEEN 2 AND 32
           AND accounting_unit GLOB '[A-Za-z][A-Za-z0-9._-]*'),
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
    -- Version du document experiment persisté (contrat experiment 1.0.0).
    schema_version             TEXT NOT NULL DEFAULT '1.0.0',
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
    -- Une devise de présentation différente de l'unité comptable exige une
    -- règle de conversion explicite ; aucune conversion implicite.
    CHECK (presentation_currency = accounting_unit
           OR presentation_conversion_json IS NOT NULL),
    -- random_seed est dupliqué entre colonne et JSON d'hypothèses d'exécution.
    -- Le doublon n'est acceptable que s'il est toujours identique ; la clé
    -- JSON doit exister et être un entier.
    CHECK (json_valid(execution_assumptions_json) = 0
           OR (json_type(execution_assumptions_json, '$.random_seed') = 'integer'
               AND json_extract(execution_assumptions_json, '$.random_seed') = random_seed)),
    CHECK (length(accounting_unit) BETWEEN 2 AND 32
           AND accounting_unit GLOB '[A-Za-z][A-Za-z0-9._-]*'),
    CHECK (length(presentation_currency) BETWEEN 2 AND 32
           AND presentation_currency GLOB '[A-Za-z][A-Za-z0-9._-]*'),
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
    -- Le couple référence/empreinte est indissociable dans les deux sens :
    -- une empreinte sans payload conservé n'est pas auditable, et un payload
    -- sans empreinte ne permet pas de vérifier l'intégrité.
    raw_payload_sha256    TEXT CHECK (raw_payload_sha256 IS NULL
                                      OR (length(raw_payload_sha256) = 64
                                          AND raw_payload_sha256 NOT GLOB '*[^0-9a-f]*')),
    CHECK ((raw_payload_ref IS NULL) = (raw_payload_sha256 IS NULL)),
    CHECK (event_type NOT IN ('trade', 'trader_activity', 'book_snapshot', 'book_delta',
                              'market_metadata', 'market_resolution')
           OR market_id IS NOT NULL),
    CHECK (event_type NOT IN ('trade', 'book_snapshot', 'book_delta') OR token_id IS NOT NULL),
    -- (market_id, token_id) est une clé étrangère composite : un événement ne
    -- peut pas référencer le token d'un autre marché. Une FK simple sur
    -- token_id ne suffisait pas.
    FOREIGN KEY (market_id, token_id) REFERENCES market_tokens(market_id, token_id),
    -- L'unité comptable est obligatoire pour les événements qui portent un
    -- notionnel. Ce n'est ni la devise de présentation ni l'actif de règlement.
    CHECK (event_type NOT IN ('trade', 'trader_activity') OR accounting_unit IS NOT NULL),
    -- Même format que les contrats JSON : lettre initiale, 2 à 32 caractères.
    CHECK (accounting_unit IS NULL
           OR (length(accounting_unit) BETWEEN 2 AND 32
               AND accounting_unit GLOB '[A-Za-z][A-Za-z0-9._-]*')),
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
    -- 0x + 64 chiffres hexadécimaux, comme le contrat JSON. Le préfixe seul ne
    -- prouvait rien : '0x' + 64 'z' passait.
    tx_hash       TEXT CHECK (tx_hash IS NULL
                              OR (length(tx_hash) = 66
                                  AND substr(tx_hash, 1, 2) = '0x'
                                  AND substr(tx_hash, 3) NOT GLOB '*[^0-9a-fA-F]*')),
    notes         TEXT CHECK (notes IS NULL OR length(notes) <= 1024)
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
    tx_hash       TEXT CHECK (tx_hash IS NULL
                              OR (length(tx_hash) = 66
                                  AND substr(tx_hash, 1, 2) = '0x'
                                  AND substr(tx_hash, 3) NOT GLOB '*[^0-9a-fA-F]*')),
    notes         TEXT CHECK (notes IS NULL OR length(notes) <= 1024),
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
    -- Les hashes décrivent le carnet entier avant/après le delta, pas une ligne
    -- de changement. Ils sont donc répétés à l'identique sur toutes les lignes
    -- d'un même event_id ; un trigger vérifie cette égalité. Alternative plus
    -- normalisée : table d'en-tête 1:1, différée pour ne pas multiplier les
    -- tables sans besoin applicatif démontré.
    book_hash_before TEXT CHECK (book_hash_before IS NULL
                                 OR length(book_hash_before) BETWEEN 1 AND 128),
    book_hash_after  TEXT CHECK (book_hash_after IS NULL
                                 OR length(book_hash_after) BETWEEN 1 AND 128),
    PRIMARY KEY (event_id, change_index),
    CHECK (action <> 'REMOVE' OR size_micros = 0),
    CHECK (action = 'REMOVE' OR size_micros > 0)
) STRICT;

CREATE TRIGGER trg_book_delta_hash_consistency
BEFORE INSERT ON book_delta_changes
WHEN EXISTS (
    SELECT 1 FROM book_delta_changes
    WHERE event_id = NEW.event_id
      AND (book_hash_before IS NOT NEW.book_hash_before
           OR book_hash_after IS NOT NEW.book_hash_after)
)
BEGIN
    SELECT RAISE(ABORT, 'book_hash_before/after doivent être identiques pour un même delta');
END;

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

-- Le JSON outcomes d'un événement de métadonnées doit être auto-cohérent :
-- token_id et outcome_index uniques, éléments objet avec identifiants. Le
-- contrat JSON le décrit ; le SQL le vérifie aussi car un événement de
-- métadonnées incohérent ne doit pas être stocké, même si market_tokens est
-- corrigé en aval.
CREATE TRIGGER trg_market_metadata_outcomes_unique
BEFORE INSERT ON market_metadata_events
WHEN json_valid(NEW.outcomes_json)
 AND json_type(NEW.outcomes_json) = 'array'
 AND (
     (SELECT COUNT(*) FROM json_each(NEW.outcomes_json))
         <> (SELECT COUNT(DISTINCT json_extract(value, '$.token_id'))
             FROM json_each(NEW.outcomes_json))
     OR (SELECT COUNT(*) FROM json_each(NEW.outcomes_json))
         <> (SELECT COUNT(DISTINCT json_extract(value, '$.outcome_index'))
             FROM json_each(NEW.outcomes_json))
     OR EXISTS (
         SELECT 1 FROM json_each(NEW.outcomes_json)
         WHERE json_type(value) IS NOT 'object'
            OR json_type(value, '$.token_id') IS NOT 'text'
            OR length(json_extract(value, '$.token_id')) = 0
            OR json_type(value, '$.outcome_index') IS NOT 'integer'
            OR json_extract(value, '$.outcome_index') < 0
     )
 )
BEGIN
    SELECT RAISE(ABORT, 'outcomes_json doit contenir des token_id et outcome_index uniques');
END;

-- Le token gagnant doit appartenir au marché de l'événement de résolution.
CREATE TRIGGER trg_resolution_winning_token_market
BEFORE INSERT ON market_resolution_events
WHEN NEW.winning_token_id IS NOT NULL
 AND (SELECT mt.market_id FROM market_tokens mt WHERE mt.token_id = NEW.winning_token_id)
     IS NOT (SELECT e.market_id FROM market_events e WHERE e.event_id = NEW.event_id)
BEGIN
    SELECT RAISE(ABORT, 'winning_token_id doit appartenir au marché de la résolution');
END;

-- Une résolution réglée dans un actif différent du collatéral du marché exige
-- une règle de conversion explicite. Le contenu de la règle est validé par le
-- contrat JSON et par A2 ; le SQL impose seulement sa présence.
CREATE TRIGGER trg_resolution_conversion_required
BEFORE INSERT ON market_resolution_events
WHEN NEW.resolution_status = 'RESOLVED'
 AND NEW.conversion_rule_json IS NULL
 AND EXISTS (
     SELECT 1
     FROM markets m
     JOIN market_events e ON e.market_id = m.market_id
     WHERE e.event_id = NEW.event_id
       AND m.collateral_asset IS NOT NULL
       AND m.collateral_asset IS NOT NEW.settlement_asset
 )
BEGIN
    SELECT RAISE(ABORT, 'conversion_rule_json exigée si settlement_asset diffère du collatéral');
END;

-- ----------------------------------------------------------------------------
-- 3bis. Immuabilité des événements normalisés (append-only)
-- ----------------------------------------------------------------------------
-- Toute correction passe par un nouvel event_id. Ces triggers couvrent les
-- UPDATE/DELETE directs. INSERT OR REPLACE déclenche les triggers DELETE
-- seulement si PRAGMA recursive_triggers=ON (activé en tête de schéma) ;
-- INSERT OR IGNORE n'écrit rien et reste idempotent. DROP TABLE/ALTER TABLE
-- restent des opérations d'administration hors du contrôle d'un trigger.
CREATE TRIGGER trg_market_events_no_update
BEFORE UPDATE ON market_events
BEGIN
    SELECT RAISE(ABORT, 'market_events est append-only');
END;

CREATE TRIGGER trg_market_events_no_delete
BEFORE DELETE ON market_events
BEGIN
    SELECT RAISE(ABORT, 'market_events est append-only');
END;

CREATE TRIGGER trg_trade_events_no_update
BEFORE UPDATE ON trade_events
BEGIN
    SELECT RAISE(ABORT, 'trade_events est append-only');
END;

CREATE TRIGGER trg_trade_events_no_delete
BEFORE DELETE ON trade_events
BEGIN
    SELECT RAISE(ABORT, 'trade_events est append-only');
END;

CREATE TRIGGER trg_trader_activity_events_no_update
BEFORE UPDATE ON trader_activity_events
BEGIN
    SELECT RAISE(ABORT, 'trader_activity_events est append-only');
END;

CREATE TRIGGER trg_trader_activity_events_no_delete
BEFORE DELETE ON trader_activity_events
BEGIN
    SELECT RAISE(ABORT, 'trader_activity_events est append-only');
END;

CREATE TRIGGER trg_book_snapshots_no_update
BEFORE UPDATE ON book_snapshots
BEGIN
    SELECT RAISE(ABORT, 'book_snapshots est append-only');
END;

CREATE TRIGGER trg_book_snapshots_no_delete
BEFORE DELETE ON book_snapshots
BEGIN
    SELECT RAISE(ABORT, 'book_snapshots est append-only');
END;

CREATE TRIGGER trg_book_delta_changes_no_update
BEFORE UPDATE ON book_delta_changes
BEGIN
    SELECT RAISE(ABORT, 'book_delta_changes est append-only');
END;

CREATE TRIGGER trg_book_delta_changes_no_delete
BEFORE DELETE ON book_delta_changes
BEGIN
    SELECT RAISE(ABORT, 'book_delta_changes est append-only');
END;

CREATE TRIGGER trg_market_metadata_events_no_update
BEFORE UPDATE ON market_metadata_events
BEGIN
    SELECT RAISE(ABORT, 'market_metadata_events est append-only');
END;

CREATE TRIGGER trg_market_metadata_events_no_delete
BEFORE DELETE ON market_metadata_events
BEGIN
    SELECT RAISE(ABORT, 'market_metadata_events est append-only');
END;

CREATE TRIGGER trg_market_resolution_events_no_update
BEFORE UPDATE ON market_resolution_events
BEGIN
    SELECT RAISE(ABORT, 'market_resolution_events est append-only');
END;

CREATE TRIGGER trg_market_resolution_events_no_delete
BEFORE DELETE ON market_resolution_events
BEGIN
    SELECT RAISE(ABORT, 'market_resolution_events est append-only');
END;

CREATE TRIGGER trg_connection_events_no_update
BEFORE UPDATE ON connection_events
BEGIN
    SELECT RAISE(ABORT, 'connection_events est append-only');
END;

CREATE TRIGGER trg_connection_events_no_delete
BEFORE DELETE ON connection_events
BEGIN
    SELECT RAISE(ABORT, 'connection_events est append-only');
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
    -- Cardinalité V1 : une intention produit au plus un ordre ; l'ordre porte
    -- l'intention (y compris un ordre rejeté, qui conserve la décision). Le
    -- couple (order_id, intent_id) sert de cible à la FK composite des
    -- estimations, qui ne peuvent donc pas citer l'intention d'un autre ordre.
    intent_id                TEXT NOT NULL UNIQUE,
    schema_version           TEXT NOT NULL DEFAULT '1.0.0',
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
    rationale                TEXT CHECK (rationale IS NULL OR length(rationale) <= 2048),
    tags_json                TEXT NOT NULL DEFAULT '[]'
                             CHECK (json_valid(tags_json) AND json_type(tags_json) = 'array'),
    accounting_unit          TEXT NOT NULL,
    created_at               TEXT NOT NULL,
    UNIQUE (order_id, intent_id),
    -- Le token de l'ordre doit appartenir au marché de l'ordre.
    FOREIGN KEY (market_id, token_id) REFERENCES market_tokens(market_id, token_id),
    CHECK (length(accounting_unit) BETWEEN 2 AND 32
           AND accounting_unit GLOB '[A-Za-z][A-Za-z0-9._-]*'),
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
    intent_id                TEXT NOT NULL,
    schema_version           TEXT NOT NULL DEFAULT '1.0.0',
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
    -- L'estimation doit citer l'intention de son ordre, pas une intention
    -- quelconque. La FK composite le garantit.
    FOREIGN KEY (order_id, intent_id) REFERENCES simulated_orders(order_id, intent_id),
    CHECK (length(accounting_unit) BETWEEN 2 AND 32
           AND accounting_unit GLOB '[A-Za-z][A-Za-z0-9._-]*'),
    CHECK (status <> 'rejected' OR rejection_reason IS NOT NULL),
    CHECK (status <> 'rejected' OR (executable_size_micros = 0 AND vwap_micros IS NULL)),
    CHECK (status = 'rejected' OR (vwap_micros IS NOT NULL AND fee_calculation_json IS NOT NULL)),
    CHECK (arrival_timestamp GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9].[0-9][0-9][0-9][0-9][0-9][0-9]Z'),
    CHECK (created_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9].[0-9][0-9][0-9][0-9][0-9][0-9]Z')
) STRICT;

CREATE TABLE simulated_fills (
    fill_id                TEXT PRIMARY KEY,
    schema_version         TEXT NOT NULL DEFAULT '1.0.0',
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
    CHECK (length(accounting_unit) BETWEEN 2 AND 32
           AND accounting_unit GLOB '[A-Za-z][A-Za-z0-9._-]*'),
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
-- 4bis. Références de carnet et cohérence ordre -> fill
-- ----------------------------------------------------------------------------
-- book_snapshot_event_id doit désigner un book_snapshot du même marché et du
-- même token. Une FK vers market_events seule acceptait un trade ou un snapshot
-- d'un autre marché.
CREATE TRIGGER trg_orders_book_snapshot_insert
BEFORE INSERT ON simulated_orders
WHEN NEW.book_snapshot_event_id IS NOT NULL
 AND NOT EXISTS (
     SELECT 1
     FROM book_snapshots bs
     JOIN market_events e ON e.event_id = bs.event_id
     WHERE bs.event_id = NEW.book_snapshot_event_id
       AND e.market_id = NEW.market_id
       AND e.token_id = NEW.token_id
 )
BEGIN
    SELECT RAISE(ABORT, 'book_snapshot_event_id doit être un snapshot du marché et du token de l''ordre');
END;

CREATE TRIGGER trg_orders_book_snapshot_update
BEFORE UPDATE OF book_snapshot_event_id ON simulated_orders
WHEN NEW.book_snapshot_event_id IS NOT NULL
 AND NOT EXISTS (
     SELECT 1
     FROM book_snapshots bs
     JOIN market_events e ON e.event_id = bs.event_id
     WHERE bs.event_id = NEW.book_snapshot_event_id
       AND e.market_id = NEW.market_id
       AND e.token_id = NEW.token_id
 )
BEGIN
    SELECT RAISE(ABORT, 'book_snapshot_event_id doit être un snapshot du marché et du token de l''ordre');
END;

CREATE TRIGGER trg_estimates_book_snapshot_insert
BEFORE INSERT ON execution_estimates
WHEN EXISTS (SELECT 1 FROM simulated_orders WHERE order_id = NEW.order_id)
 AND NOT EXISTS (
    SELECT 1
    FROM book_snapshots bs
    JOIN market_events e ON e.event_id = bs.event_id
    JOIN simulated_orders o ON o.order_id = NEW.order_id
    WHERE bs.event_id = NEW.book_snapshot_event_id
      AND e.market_id = o.market_id
      AND e.token_id = o.token_id
)
BEGIN
    SELECT RAISE(ABORT, 'book_snapshot_event_id doit être un snapshot du marché et du token de l''ordre estimé');
END;

CREATE TRIGGER trg_estimates_book_snapshot_update
BEFORE UPDATE OF book_snapshot_event_id ON execution_estimates
WHEN EXISTS (SELECT 1 FROM simulated_orders WHERE order_id = NEW.order_id)
 AND NOT EXISTS (
    SELECT 1
    FROM book_snapshots bs
    JOIN market_events e ON e.event_id = bs.event_id
    JOIN simulated_orders o ON o.order_id = NEW.order_id
    WHERE bs.event_id = NEW.book_snapshot_event_id
      AND e.market_id = o.market_id
      AND e.token_id = o.token_id
)
BEGIN
    SELECT RAISE(ABORT, 'book_snapshot_event_id doit être un snapshot du marché et du token de l''ordre estimé');
END;

CREATE TRIGGER trg_fills_book_snapshot_insert
BEFORE INSERT ON simulated_fills
WHEN EXISTS (SELECT 1 FROM simulated_orders WHERE order_id = NEW.order_id)
 AND NOT EXISTS (
    SELECT 1
    FROM book_snapshots bs
    JOIN market_events e ON e.event_id = bs.event_id
    JOIN simulated_orders o ON o.order_id = NEW.order_id
    WHERE bs.event_id = NEW.book_snapshot_event_id
      AND e.market_id = o.market_id
      AND e.token_id = o.token_id
)
BEGIN
    SELECT RAISE(ABORT, 'book_snapshot_event_id doit être un snapshot du marché et du token de l''ordre exécuté');
END;

-- Un fill ne peut exister que pour un ordre accepté, partiellement rempli ou
-- rempli. proposed/rejected/expired n'ont pas d'exécution.
CREATE TRIGGER trg_fills_order_status_insert
BEFORE INSERT ON simulated_fills
WHEN (SELECT status FROM simulated_orders WHERE order_id = NEW.order_id)
     NOT IN ('accepted', 'partially_filled', 'filled')
BEGIN
    SELECT RAISE(ABORT, 'un fill exige un ordre accepté, partiellement rempli ou rempli');
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

-- Version du schéma de stockage (pas la version des contrats JSON, portée par
-- les colonnes schema_version). schema_migrations est alimenté par le runner de
-- migrations incrémentales ; le script de base n'y insère pas de ligne.
PRAGMA user_version = 3;
