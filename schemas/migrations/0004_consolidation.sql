-- ============================================================================
-- Migration 0004 — consolidation contrats 1.1.0 / schéma 0.4
-- Base source : schéma initial 0.3 (`schemas/initial_db_schema.sql`).
-- Base cible  : 0.4, PRAGMA user_version = 4.
--
-- Cette migration est une opération de maintenance. Elle doit être exécutée
-- sur une copie de sauvegarde, sans autre écrivain, avec foreign_keys=OFF
-- uniquement sur cette connexion. Le runner `run_migration.py` annule la
-- transaction en cas d'échec et restaure foreign_keys=ON ; il doit aussi
-- restaurer la sauvegarde si la base copiée est inutilisable.
--
-- Décisions appliquées : D-027, D-029, D-030, D-032, D-034, D-035, D-036,
-- D-038, D-039, D-040. Les données 0.3 non conformes aux nouvelles contraintes ne
-- sont jamais converties silencieusement : une pré-vérification fait échouer
-- la migration si des valeurs suspendues existent (per_share, custom,
-- outcome_token, not_required).
-- ============================================================================

PRAGMA foreign_keys = OFF;
BEGIN IMMEDIATE;

-- Les vues dépendent de tables reconstruites : les retirer avant les DROP.
DROP VIEW IF EXISTS v_order_execution;
DROP VIEW IF EXISTS v_experiment_cash;
DROP VIEW IF EXISTS v_experiment_positions;
DROP VIEW IF EXISTS v_ledger_anomalies;
DROP VIEW IF EXISTS v_experiment_latest_snapshot;
DROP VIEW IF EXISTS v_negative_cash;
DROP VIEW IF EXISTS v_position_anomalies;

-- ----------------------------------------------------------------------------
-- 0. Pré-vérifications : aucune conversion silencieuse
-- ----------------------------------------------------------------------------
CREATE TEMP TABLE _preflight_fee (
    bad INTEGER NOT NULL CHECK (bad = 0)
);
INSERT INTO _preflight_fee
SELECT COUNT(*) FROM fee_schedules
WHERE fee_formula IN ('per_share', 'custom')
   OR fee_charge_unit = 'outcome_token';
DROP TABLE _preflight_fee;

CREATE TEMP TABLE _preflight_fills (
    bad INTEGER NOT NULL CHECK (bad = 0)
);
INSERT INTO _preflight_fills
SELECT COUNT(*) FROM simulated_fills
WHERE fee_formula IN ('per_share', 'custom')
   OR fee_unit = 'outcome_token';
DROP TABLE _preflight_fills;

CREATE TEMP TABLE _preflight_experiments (
    bad INTEGER NOT NULL CHECK (bad = 0)
);
INSERT INTO _preflight_experiments
SELECT COUNT(*) FROM experiments WHERE fee_status = 'not_required';
DROP TABLE _preflight_experiments;

-- ----------------------------------------------------------------------------
-- 1. Reconstruire fee_schedules
-- ----------------------------------------------------------------------------
CREATE TABLE fee_schedules_v4 (
    fee_schedule_id          TEXT PRIMARY KEY,
    schema_version           TEXT NOT NULL DEFAULT '1.1.0',
    verification_status      TEXT NOT NULL
                             CHECK (verification_status IN ('verified', 'provisional', 'unverified')),
    source_url               TEXT NOT NULL,
    source_title             TEXT,
    source_retrieved_at      TEXT NOT NULL,
    effective_from           TEXT NOT NULL,
    effective_to             TEXT,
    scope_type               TEXT NOT NULL CHECK (scope_type IN ('global', 'category', 'market')),
    scope_value              TEXT NOT NULL DEFAULT '*',
    scope_evidence_ref       TEXT,
    accounting_unit          TEXT NOT NULL,
    maker_rate_micros        INTEGER NOT NULL CHECK (maker_rate_micros BETWEEN 0 AND 1000000),
    taker_rate_micros        INTEGER NOT NULL CHECK (taker_rate_micros BETWEEN 0 AND 1000000),
    fee_formula              TEXT NOT NULL
                             CHECK (fee_formula IN ('none', 'linear_min_price_1mp', 'notional')),
    formula_definition_ref   TEXT,
    -- Colonne conservée pour les données legacy ; aucune nouvelle ligne custom.
    custom_formula_ref       TEXT,
    fee_charge_unit          TEXT NOT NULL CHECK (fee_charge_unit IN ('collateral')),
    rounding_rule            TEXT NOT NULL
                             CHECK (rounding_rule IN ('half_even_micros', 'half_up_micros', 'floor_micros', 'ceil_micros', 'exchange_specific')),
    rounding_increment_micros INTEGER NOT NULL CHECK (rounding_increment_micros > 0),
    notes                    TEXT NOT NULL DEFAULT '',
    supersedes_fee_schedule_id TEXT REFERENCES fee_schedules_v4(fee_schedule_id),
    created_at               TEXT NOT NULL,
    CHECK (effective_to IS NULL OR effective_to > effective_from),
    CHECK (length(accounting_unit) BETWEEN 2 AND 32
           AND accounting_unit GLOB '[A-Za-z][A-Za-z0-9._-]*'),
    CHECK (fee_formula <> 'none' OR (maker_rate_micros = 0 AND taker_rate_micros = 0)),
    CHECK (verification_status <> 'verified' OR source_url LIKE 'https://%'),
    CHECK (verification_status <> 'verified' OR scope_type = 'market' OR scope_evidence_ref IS NOT NULL),
    CHECK (source_retrieved_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9].[0-9][0-9][0-9][0-9][0-9][0-9]Z'),
    CHECK (effective_from GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9].[0-9][0-9][0-9][0-9][0-9][0-9]Z'),
    CHECK (effective_to IS NULL OR effective_to GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9].[0-9][0-9][0-9][0-9][0-9][0-9]Z'),
    CHECK (created_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9].[0-9][0-9][0-9][0-9][0-9][0-9]Z')
) STRICT;

INSERT INTO fee_schedules_v4 (
    fee_schedule_id, schema_version, verification_status, source_url, source_title,
    source_retrieved_at, effective_from, effective_to, scope_type, scope_value,
    scope_evidence_ref, accounting_unit, maker_rate_micros, taker_rate_micros,
    fee_formula, formula_definition_ref, custom_formula_ref, fee_charge_unit,
    rounding_rule, rounding_increment_micros, notes, supersedes_fee_schedule_id,
    created_at
)
SELECT
    fee_schedule_id, schema_version, verification_status, source_url, source_title,
    source_retrieved_at, effective_from, effective_to, scope_type, scope_value,
    scope_evidence_ref, accounting_unit, maker_rate_micros, taker_rate_micros,
    fee_formula, NULL, custom_formula_ref, fee_charge_unit,
    rounding_rule, rounding_increment_micros, notes, supersedes_fee_schedule_id,
    created_at
FROM fee_schedules;
DROP TABLE fee_schedules;
ALTER TABLE fee_schedules_v4 RENAME TO fee_schedules;

-- ----------------------------------------------------------------------------
-- 2. Reconstruire simulated_fills
-- ----------------------------------------------------------------------------
CREATE TABLE simulated_fills_v4 (
    fill_id                TEXT PRIMARY KEY,
    schema_version         TEXT NOT NULL DEFAULT '1.1.0',
    order_id               TEXT NOT NULL REFERENCES simulated_orders(order_id),
    fill_index             INTEGER NOT NULL CHECK (fill_index >= 0),
    level_index            INTEGER NOT NULL CHECK (level_index >= 0),
    price_micros           INTEGER NOT NULL CHECK (price_micros BETWEEN 0 AND 1000000),
    size_micros            INTEGER NOT NULL CHECK (size_micros > 0),
    notional_micros        INTEGER NOT NULL CHECK (notional_micros >= 0),
    fee_schedule_id        TEXT NOT NULL REFERENCES fee_schedules(fee_schedule_id),
    fee_formula            TEXT NOT NULL
                           CHECK (fee_formula IN ('none', 'linear_min_price_1mp', 'notional')),
    rate_micros            INTEGER NOT NULL CHECK (rate_micros BETWEEN 0 AND 1000000),
    fee_unit               TEXT NOT NULL CHECK (fee_unit IN ('collateral')),
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

INSERT INTO simulated_fills_v4 (
    fill_id, schema_version, order_id, fill_index, level_index, price_micros,
    size_micros, notional_micros, fee_schedule_id, fee_formula, rate_micros,
    fee_unit, fee_amount_micros, fee_calculation_json, accounting_unit,
    book_snapshot_event_id, fill_timestamp, created_at
)
SELECT
    fill_id, schema_version, order_id, fill_index, level_index, price_micros,
    size_micros, notional_micros, fee_schedule_id, fee_formula, rate_micros,
    fee_unit, fee_amount_micros, fee_calculation_json, accounting_unit,
    book_snapshot_event_id, fill_timestamp, created_at
FROM simulated_fills;
DROP TABLE simulated_fills;
ALTER TABLE simulated_fills_v4 RENAME TO simulated_fills;

-- ----------------------------------------------------------------------------
-- 3. Reconstruire execution_estimates
-- ----------------------------------------------------------------------------
CREATE TABLE execution_estimates_v4 (
    estimate_id              TEXT PRIMARY KEY,
    order_id                 TEXT NOT NULL UNIQUE REFERENCES simulated_orders(order_id),
    intent_id                TEXT NOT NULL,
    schema_version           TEXT NOT NULL DEFAULT '1.1.0',
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
                                         ('stale_book', 'missing_book', 'incomplete_book',
                                          'insufficient_liquidity', 'missing_fee_schedule',
                                          'ambiguous_fee_schedule', 'risk_limit', 'invalid_order', 'other')),
    created_at               TEXT NOT NULL,
    FOREIGN KEY (order_id, intent_id) REFERENCES simulated_orders(order_id, intent_id),
    CHECK (length(accounting_unit) BETWEEN 2 AND 32
           AND accounting_unit GLOB '[A-Za-z][A-Za-z0-9._-]*'),
    CHECK (status <> 'rejected' OR rejection_reason IS NOT NULL),
    CHECK (status <> 'rejected' OR (executable_size_micros = 0 AND vwap_micros IS NULL)),
    CHECK (status = 'rejected' OR (vwap_micros IS NOT NULL AND fee_calculation_json IS NOT NULL)),
    CHECK (arrival_timestamp GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9].[0-9][0-9][0-9][0-9][0-9][0-9]Z'),
    CHECK (created_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9].[0-9][0-9][0-9][0-9][0-9][0-9]Z')
) STRICT;

INSERT INTO execution_estimates_v4 (
    estimate_id, order_id, intent_id, schema_version, book_snapshot_event_id,
    arrival_timestamp, status, accounting_unit, executable_size_micros,
    unfilled_size_micros, vwap_micros, levels_json, assumptions_json,
    fee_calculation_json, rejection_reason, created_at
)
SELECT
    estimate_id, order_id, intent_id, schema_version, book_snapshot_event_id,
    arrival_timestamp, status, accounting_unit, executable_size_micros,
    unfilled_size_micros, vwap_micros, levels_json, assumptions_json,
    fee_calculation_json, rejection_reason, created_at
FROM execution_estimates;
DROP TABLE execution_estimates;
ALTER TABLE execution_estimates_v4 RENAME TO execution_estimates;

-- ----------------------------------------------------------------------------
-- 4. Reconstruire simulated_orders
-- ----------------------------------------------------------------------------
CREATE TABLE simulated_orders_v4 (
    order_id                 TEXT PRIMARY KEY,
    intent_id                TEXT NOT NULL UNIQUE,
    schema_version           TEXT NOT NULL DEFAULT '1.1.0',
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
                                         ('stale_book', 'missing_book', 'incomplete_book',
                                          'insufficient_liquidity', 'missing_fee_schedule',
                                          'ambiguous_fee_schedule', 'risk_limit', 'invalid_order', 'other')),
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
    FOREIGN KEY (market_id, token_id) REFERENCES market_tokens(market_id, token_id),
    CHECK (length(accounting_unit) BETWEEN 2 AND 32
           AND accounting_unit GLOB '[A-Za-z][A-Za-z0-9._-]*'),
    CHECK (status <> 'rejected' OR rejection_reason IS NOT NULL),
    CHECK (status <> 'rejected' OR rejection_reason <> 'missing_book'
           OR book_snapshot_event_id IS NULL),
    CHECK (simulated_arrival_timestamp IS NULL OR simulated_arrival_timestamp >= decision_timestamp),
    CHECK (status IN ('proposed', 'rejected') OR book_snapshot_event_id IS NOT NULL),
    CHECK (decision_timestamp GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9].[0-9][0-9][0-9][0-9][0-9][0-9]Z'),
    CHECK (simulated_arrival_timestamp IS NULL OR simulated_arrival_timestamp GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9].[0-9][0-9][0-9][0-9][0-9][0-9]Z'),
    CHECK (created_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9].[0-9][0-9][0-9][0-9][0-9][0-9]Z')
) STRICT;

INSERT INTO simulated_orders_v4 (
    order_id, intent_id, schema_version, idempotency_key, experiment_id,
    market_id, token_id, order_type, side, requested_size_micros,
    limit_price_micros, status, rejection_reason, decision_timestamp,
    simulated_arrival_timestamp, book_snapshot_event_id, assumptions_json,
    rationale, tags_json, accounting_unit, created_at
)
SELECT
    order_id, intent_id, schema_version, idempotency_key, experiment_id,
    market_id, token_id, order_type, side, requested_size_micros,
    limit_price_micros, status, rejection_reason, decision_timestamp,
    simulated_arrival_timestamp, book_snapshot_event_id, assumptions_json,
    rationale, tags_json, accounting_unit, created_at
FROM simulated_orders;
DROP TABLE simulated_orders;
ALTER TABLE simulated_orders_v4 RENAME TO simulated_orders;

-- ----------------------------------------------------------------------------
-- 5. Reconstruire experiments
-- ----------------------------------------------------------------------------
CREATE TABLE experiments_v4 (
    experiment_id              TEXT PRIMARY KEY,
    schema_version             TEXT NOT NULL DEFAULT '1.1.0',
    strategy_id                TEXT NOT NULL,
    strategy_version           TEXT NOT NULL,
    period_type                TEXT NOT NULL
                               CHECK (period_type IN ('research', 'validation', 'final_test', 'paper_live')),
    start_time                 TEXT NOT NULL,
    end_time                   TEXT,
    initial_capital_micros     INTEGER NOT NULL CHECK (initial_capital_micros > 0),
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
                               CHECK (fee_status IN ('verified', 'provisional', 'unverified')),
    random_seed                INTEGER NOT NULL CHECK (random_seed >= 0),
    status                     TEXT NOT NULL
                               CHECK (status IN ('planned', 'running', 'completed', 'aborted', 'invalid')),
    created_at                 TEXT NOT NULL,
    completed_at               TEXT,
    FOREIGN KEY (strategy_id, strategy_version) REFERENCES strategies(strategy_id, version),
    CHECK (end_time IS NULL OR end_time > start_time),
    CHECK (period_type = 'paper_live' OR data_manifest_id IS NOT NULL),
    CHECK (fee_status NOT IN ('verified', 'provisional') OR default_fee_schedule_id IS NOT NULL),
    CHECK (presentation_currency = accounting_unit
           OR presentation_conversion_json IS NOT NULL),
    CHECK (json_valid(execution_assumptions_json) = 0
           OR (json_type(execution_assumptions_json, '$.random_seed') = 'integer'
               AND json_extract(execution_assumptions_json, '$.random_seed') = random_seed)),
    CHECK (length(accounting_unit) BETWEEN 2 AND 32
           AND accounting_unit GLOB '[A-Za-z][A-Za-z0-9._-]*'),
    CHECK (length(presentation_currency) BETWEEN 2 AND 32
           AND presentation_currency GLOB '[A-Za-z][A-Za-z0-9._-]*'),
    CHECK (length(config_hash) = 71
           AND substr(config_hash, 1, 7) = 'sha256:'
           AND substr(config_hash, 8) NOT GLOB '*[^0-9a-f]*'),
    CHECK (start_time GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9].[0-9][0-9][0-9][0-9][0-9][0-9]Z'),
    CHECK (end_time IS NULL OR end_time GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9].[0-9][0-9][0-9][0-9][0-9][0-9]Z'),
    CHECK (created_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9].[0-9][0-9][0-9][0-9][0-9][0-9]Z'),
    CHECK (completed_at IS NULL OR completed_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9].[0-9][0-9][0-9][0-9][0-9][0-9]Z')
) STRICT;

INSERT INTO experiments_v4 (
    experiment_id, schema_version, strategy_id, strategy_version, period_type,
    start_time, end_time, initial_capital_micros, accounting_unit,
    presentation_currency, presentation_conversion_json, data_manifest_id,
    code_version, config_hash, execution_assumptions_json, risk_limits_json,
    default_fee_schedule_id, fee_status, random_seed, status, created_at,
    completed_at
)
SELECT
    experiment_id, schema_version, strategy_id, strategy_version, period_type,
    start_time, end_time, initial_capital_micros, accounting_unit,
    presentation_currency, presentation_conversion_json, data_manifest_id,
    code_version, config_hash, execution_assumptions_json, risk_limits_json,
    default_fee_schedule_id, fee_status, random_seed, status, created_at,
    completed_at
FROM experiments;
DROP TABLE experiments;
ALTER TABLE experiments_v4 RENAME TO experiments;

-- ----------------------------------------------------------------------------
-- 6. Reconstruire portfolio_snapshots (valorisation inconnue)
-- ----------------------------------------------------------------------------
CREATE TABLE portfolio_snapshots_v4 (
    snapshot_id             TEXT PRIMARY KEY,
    experiment_id           TEXT NOT NULL REFERENCES experiments(experiment_id),
    as_of_timestamp         TEXT NOT NULL,
    cash_micros             INTEGER NOT NULL CHECK (cash_micros >= 0),
    positions_value_micros  INTEGER CHECK (positions_value_micros IS NULL OR positions_value_micros >= 0),
    equity_micros           INTEGER,
    realized_pnl_micros     INTEGER NOT NULL,
    unrealized_pnl_micros   INTEGER,
    fees_paid_micros        INTEGER NOT NULL CHECK (fees_paid_micros >= 0),
    accounting_unit         TEXT NOT NULL,
    valuation_method        TEXT NOT NULL
                            CHECK (valuation_method IN ('executable_bid_book', 'mid_price_reference', 'none')),
    data_quality_status     TEXT NOT NULL
                            CHECK (data_quality_status IN ('complete', 'partial', 'stale', 'gap')),
    metrics_json            TEXT NOT NULL DEFAULT '{}' CHECK (json_valid(metrics_json)),
    created_at              TEXT NOT NULL,
    UNIQUE (experiment_id, as_of_timestamp),
    CHECK (
        (valuation_method = 'none'
         AND (positions_value_micros IS NULL OR positions_value_micros = 0)
         AND (equity_micros IS NULL OR equity_micros = cash_micros)
         AND (unrealized_pnl_micros IS NULL OR unrealized_pnl_micros = 0))
        OR
        (valuation_method <> 'none'
         AND positions_value_micros IS NOT NULL
         AND equity_micros IS NOT NULL
         AND unrealized_pnl_micros IS NOT NULL
         AND equity_micros = cash_micros + positions_value_micros)
    ),
    CHECK (as_of_timestamp GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9].[0-9][0-9][0-9][0-9][0-9][0-9]Z'),
    CHECK (created_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9].[0-9][0-9][0-9][0-9][0-9][0-9]Z')
) STRICT;

INSERT INTO portfolio_snapshots_v4 (
    snapshot_id, experiment_id, as_of_timestamp, cash_micros,
    positions_value_micros, equity_micros, realized_pnl_micros,
    unrealized_pnl_micros, fees_paid_micros, accounting_unit,
    valuation_method, data_quality_status, metrics_json, created_at
)
SELECT
    snapshot_id, experiment_id, as_of_timestamp, cash_micros,
    positions_value_micros, equity_micros, realized_pnl_micros,
    unrealized_pnl_micros, fees_paid_micros, accounting_unit,
    valuation_method, data_quality_status, metrics_json, created_at
FROM portfolio_snapshots;
DROP TABLE portfolio_snapshots;
ALTER TABLE portfolio_snapshots_v4 RENAME TO portfolio_snapshots;

-- ----------------------------------------------------------------------------
-- 7. Colonnes ajoutées sans reconstruction
-- ----------------------------------------------------------------------------
ALTER TABLE market_events ADD COLUMN normalizer_version TEXT;
ALTER TABLE trade_events ADD COLUMN trader_visibility TEXT;
ALTER TABLE book_snapshots ADD COLUMN book_hash_algorithm TEXT;
ALTER TABLE book_snapshots ADD COLUMN internal_book_hash TEXT;
ALTER TABLE book_delta_changes ADD COLUMN book_hash_algorithm TEXT;
ALTER TABLE book_delta_changes ADD COLUMN internal_book_hash_before TEXT;
ALTER TABLE book_delta_changes ADD COLUMN internal_book_hash_after TEXT;
ALTER TABLE market_resolution_events ADD COLUMN void_rule_ref TEXT;
ALTER TABLE data_manifests ADD COLUMN source_class TEXT;

-- ----------------------------------------------------------------------------
-- 8. Nouvelles tables
-- ----------------------------------------------------------------------------
CREATE TABLE event_replacements (
    replacement_id    TEXT PRIMARY KEY,
    old_event_id      TEXT NOT NULL UNIQUE REFERENCES market_events(event_id),
    new_event_id      TEXT NOT NULL UNIQUE REFERENCES market_events(event_id),
    reason            TEXT NOT NULL
                      CHECK (reason IN ('reparse', 'source_correction', 'contract_migration', 'other')),
    normalizer_version TEXT NOT NULL,
    evidence_ref      TEXT,
    created_at        TEXT NOT NULL,
    CHECK (old_event_id <> new_event_id),
    CHECK (created_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9].[0-9][0-9][0-9][0-9][0-9][0-9]Z')
) STRICT;

CREATE TABLE position_valuations (
    snapshot_id             TEXT NOT NULL REFERENCES portfolio_snapshots(snapshot_id),
    token_id                TEXT NOT NULL REFERENCES market_tokens(token_id),
    quantity_micros         INTEGER NOT NULL CHECK (quantity_micros >= 0),
    price_micros            INTEGER CHECK (price_micros IS NULL OR price_micros BETWEEN 0 AND 1000000),
    book_snapshot_event_id  TEXT REFERENCES market_events(event_id),
    method                  TEXT NOT NULL
                            CHECK (method IN ('executable_bid_book', 'mid_price_reference', 'none')),
    PRIMARY KEY (snapshot_id, token_id),
    CHECK (method <> 'none' OR price_micros IS NULL)
) STRICT;

CREATE TABLE settlement_conversions (
    conversion_id           TEXT PRIMARY KEY,
    resolution_event_id     TEXT NOT NULL REFERENCES market_resolution_events(event_id),
    source_asset            TEXT NOT NULL,
    source_amount_micros    INTEGER NOT NULL CHECK (source_amount_micros >= 0),
    target_unit             TEXT NOT NULL,
    target_amount_micros    INTEGER NOT NULL CHECK (target_amount_micros >= 0),
    conversion_rule_ref     TEXT NOT NULL,
    rate_micros             INTEGER CHECK (rate_micros IS NULL OR rate_micros >= 0),
    conversion_timestamp    TEXT NOT NULL,
    created_at              TEXT NOT NULL,
    UNIQUE (resolution_event_id, source_asset, target_unit),
    CHECK (length(target_unit) BETWEEN 2 AND 32
           AND target_unit GLOB '[A-Za-z][A-Za-z0-9._-]*'),
    CHECK (conversion_timestamp GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9].[0-9][0-9][0-9][0-9][0-9][0-9]Z'),
    CHECK (created_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9].[0-9][0-9][0-9][0-9][0-9][0-9]Z')
) STRICT;

CREATE INDEX idx_orders_experiment_time ON simulated_orders(experiment_id, decision_timestamp);
CREATE INDEX idx_orders_status ON simulated_orders(status);
CREATE INDEX idx_orders_market_token ON simulated_orders(experiment_id, market_id, token_id);
CREATE INDEX idx_fills_order ON simulated_fills(order_id);
CREATE INDEX idx_event_replacements_new ON event_replacements(new_event_id);
CREATE INDEX idx_position_valuations_token ON position_valuations(token_id);
CREATE INDEX idx_settlement_conversions_resolution ON settlement_conversions(resolution_event_id);

-- ----------------------------------------------------------------------------
-- 9. Triggers des tables reconstruites (recréés)
-- ----------------------------------------------------------------------------
-- `custom_formula_ref` est conservé uniquement pour les lignes legacy 0.3.
-- Aucune nouvelle ligne ne peut le renseigner : la formule `custom` est
-- suspendue en V1 et n'a pas de définition testable dans le contrat 1.1.0.
CREATE TRIGGER trg_fee_schedules_custom_formula_insert
BEFORE INSERT ON fee_schedules
WHEN NEW.custom_formula_ref IS NOT NULL
BEGIN
    SELECT RAISE(ABORT, 'custom_formula_ref est suspendu en V1');
END;

CREATE TRIGGER trg_fee_schedules_custom_formula_update
BEFORE UPDATE OF custom_formula_ref ON fee_schedules
WHEN NEW.custom_formula_ref IS NOT NULL
 AND (OLD.custom_formula_ref IS NULL
      OR NEW.custom_formula_ref IS NOT OLD.custom_formula_ref)
BEGIN
    SELECT RAISE(ABORT, 'custom_formula_ref est suspendu en V1');
END;

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

CREATE TRIGGER trg_orders_book_snapshot_insert
BEFORE INSERT ON simulated_orders
WHEN NEW.book_snapshot_event_id IS NOT NULL
 AND NOT EXISTS (
     SELECT 1 FROM book_snapshots bs
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
     SELECT 1 FROM book_snapshots bs
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
    SELECT 1 FROM book_snapshots bs
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
    SELECT 1 FROM book_snapshots bs
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
    SELECT 1 FROM book_snapshots bs
    JOIN market_events e ON e.event_id = bs.event_id
    JOIN simulated_orders o ON o.order_id = NEW.order_id
    WHERE bs.event_id = NEW.book_snapshot_event_id
      AND e.market_id = o.market_id
      AND e.token_id = o.token_id
)
BEGIN
    SELECT RAISE(ABORT, 'book_snapshot_event_id doit être un snapshot du marché et du token de l''ordre exécuté');
END;

CREATE TRIGGER trg_fills_order_status_insert
BEFORE INSERT ON simulated_fills
WHEN (SELECT status FROM simulated_orders WHERE order_id = NEW.order_id)
     NOT IN ('accepted', 'partially_filled', 'filled')
BEGIN
    SELECT RAISE(ABORT, 'un fill exige un ordre accepté, partiellement rempli ou rempli');
END;

-- ----------------------------------------------------------------------------
-- 10. Triggers de cohérence des nouveaux champs
-- ----------------------------------------------------------------------------
CREATE TRIGGER trg_market_events_normalizer_version
BEFORE INSERT ON market_events
WHEN NEW.schema_version = '1.1.0'
 AND (NEW.normalizer_version IS NULL
      OR length(NEW.normalizer_version) < 5
      OR NEW.normalizer_version NOT GLOB '*.*.*')
BEGIN
    SELECT RAISE(ABORT, 'normalizer_version semver obligatoire pour un événement 1.1.0');
END;

CREATE TRIGGER trg_trade_events_visibility
BEFORE INSERT ON trade_events
WHEN (SELECT schema_version FROM market_events WHERE event_id = NEW.event_id) = '1.1.0'
 AND (NEW.trader_visibility IS NULL
      OR NEW.trader_visibility NOT IN ('identified', 'unknown')
      OR (NEW.trader_visibility = 'identified' AND NEW.trader_id IS NULL)
      OR (NEW.trader_visibility = 'unknown' AND NEW.trader_id IS NOT NULL))
BEGIN
    SELECT RAISE(ABORT, 'trader_visibility incohérente avec trader_id');
END;

CREATE TRIGGER trg_book_snapshot_hash_fields
BEFORE INSERT ON book_snapshots
WHEN NEW.book_hash_algorithm IS NOT NULL
 AND NEW.book_hash_algorithm NOT IN ('sha256', 'source_specific', 'unknown')
 OR (NEW.internal_book_hash IS NOT NULL
     AND (length(NEW.internal_book_hash) <> 64
          OR NEW.internal_book_hash GLOB '*[^0-9a-f]*'))
BEGIN
    SELECT RAISE(ABORT, 'book_hash_algorithm ou internal_book_hash invalide');
END;

CREATE TRIGGER trg_book_delta_hash_fields
BEFORE INSERT ON book_delta_changes
WHEN NEW.book_hash_algorithm IS NOT NULL
 AND NEW.book_hash_algorithm NOT IN ('sha256', 'source_specific', 'unknown')
 OR (NEW.internal_book_hash_before IS NOT NULL
     AND (length(NEW.internal_book_hash_before) <> 64
          OR NEW.internal_book_hash_before GLOB '*[^0-9a-f]*'))
 OR (NEW.internal_book_hash_after IS NOT NULL
     AND (length(NEW.internal_book_hash_after) <> 64
          OR NEW.internal_book_hash_after GLOB '*[^0-9a-f]*'))
BEGIN
    SELECT RAISE(ABORT, 'hash de carnet invalide');
END;

CREATE TRIGGER trg_resolution_void_rule
BEFORE INSERT ON market_resolution_events
WHEN NEW.resolution_status = 'VOID'
 AND NEW.payout_per_share_micros IS NOT NULL
 AND (NEW.void_rule_ref IS NULL OR NEW.settlement_asset IS NULL)
BEGIN
    SELECT RAISE(ABORT, 'VOID avec payout exige settlement_asset et void_rule_ref');
END;

CREATE TRIGGER trg_data_manifests_source_class
BEFORE INSERT ON data_manifests
WHEN NEW.source_class IS NULL
 OR NEW.source_class NOT IN ('fixture', 'recorded', 'live')
BEGIN
    SELECT RAISE(ABORT, 'source_class obligatoire et limité à fixture/recorded/live');
END;

CREATE TRIGGER trg_data_manifests_sha256
BEFORE INSERT ON data_manifests
WHEN length(NEW.sha256) <> 64 OR NEW.sha256 GLOB '*[^0-9a-f]*'
BEGIN
    SELECT RAISE(ABORT, 'sha256 doit être 64 hex minuscules');
END;

CREATE TRIGGER trg_experiments_config_hash
BEFORE INSERT ON experiments
WHEN length(NEW.config_hash) <> 71
 OR substr(NEW.config_hash, 1, 7) <> 'sha256:'
 OR substr(NEW.config_hash, 8) GLOB '*[^0-9a-f]*'
BEGIN
    SELECT RAISE(ABORT, 'config_hash doit être sha256:<64 hex minuscules>');
END;

-- Unités comptables : ordre/estimation/fill/posting = expérience.
CREATE TRIGGER trg_orders_unit_insert
BEFORE INSERT ON simulated_orders
WHEN NEW.accounting_unit IS NOT (SELECT accounting_unit FROM experiments WHERE experiment_id = NEW.experiment_id)
BEGIN
    SELECT RAISE(ABORT, 'accounting_unit de l''ordre différente de l''expérience');
END;

CREATE TRIGGER trg_orders_unit_update
BEFORE UPDATE OF accounting_unit ON simulated_orders
WHEN NEW.accounting_unit IS NOT (SELECT accounting_unit FROM experiments WHERE experiment_id = NEW.experiment_id)
BEGIN
    SELECT RAISE(ABORT, 'accounting_unit de l''ordre différente de l''expérience');
END;

CREATE TRIGGER trg_estimates_unit_insert
BEFORE INSERT ON execution_estimates
WHEN NEW.accounting_unit IS NOT (
    SELECT e.accounting_unit FROM simulated_orders o
    JOIN experiments e ON e.experiment_id = o.experiment_id
    WHERE o.order_id = NEW.order_id
)
BEGIN
    SELECT RAISE(ABORT, 'accounting_unit de l''estimation différente de l''expérience');
END;

CREATE TRIGGER trg_estimates_unit_update
BEFORE UPDATE OF accounting_unit ON execution_estimates
WHEN NEW.accounting_unit IS NOT (
    SELECT e.accounting_unit FROM simulated_orders o
    JOIN experiments e ON e.experiment_id = o.experiment_id
    WHERE o.order_id = NEW.order_id
)
BEGIN
    SELECT RAISE(ABORT, 'accounting_unit de l''estimation différente de l''expérience');
END;

CREATE TRIGGER trg_fills_unit_insert
BEFORE INSERT ON simulated_fills
WHEN NEW.accounting_unit IS NOT (
    SELECT e.accounting_unit FROM simulated_orders o
    JOIN experiments e ON e.experiment_id = o.experiment_id
    WHERE o.order_id = NEW.order_id
)
BEGIN
    SELECT RAISE(ABORT, 'accounting_unit du fill différente de l''expérience');
END;

CREATE TRIGGER trg_ledger_postings_unit_insert
BEFORE INSERT ON ledger_postings
WHEN NEW.accounting_unit IS NOT (
    SELECT e.accounting_unit FROM ledger_transactions t
    JOIN experiments e ON e.experiment_id = t.experiment_id
    WHERE t.transaction_id = NEW.transaction_id
)
 OR length(NEW.accounting_unit) < 2
 OR length(NEW.accounting_unit) > 32
 OR NEW.accounting_unit NOT GLOB '[A-Za-z][A-Za-z0-9._-]*'
BEGIN
    SELECT RAISE(ABORT, 'accounting_unit du posting invalide ou différente de l''expérience');
END;

CREATE TRIGGER trg_ledger_postings_token_shape
BEFORE INSERT ON ledger_postings
WHEN (NEW.account = 'POSITION') <> (NEW.token_id IS NOT NULL)
BEGIN
    SELECT RAISE(ABORT, 'POSITION exige token_id ; les autres comptes l''interdisent');
END;

-- D-034 : une transaction par fill, frais inclus. Une transaction `fee`
-- séparée sur un fill est refusée ; les lignes legacy 0.3 restent lisibles.
CREATE TRIGGER trg_ledger_fee_ref_fill
BEFORE INSERT ON ledger_transactions
WHEN NEW.kind = 'fee' AND NEW.ref_type = 'fill'
BEGIN
    SELECT RAISE(ABORT, 'V1 : les frais sont inclus dans la transaction du fill');
END;

-- Journal de migration : timestamp canonique à six décimales.
CREATE TRIGGER trg_schema_migrations_applied_at
BEFORE INSERT ON schema_migrations
WHEN NEW.applied_at NOT GLOB
     '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9].[0-9][0-9][0-9][0-9][0-9][0-9]Z'
BEGIN
    SELECT RAISE(ABORT, 'applied_at doit être un timestamp canonique à six décimales');
END;

-- Identité et champs économiques d'un ordre/estimation non réécrits.
CREATE TRIGGER trg_orders_identity_update
BEFORE UPDATE ON simulated_orders
WHEN NEW.order_id IS NOT OLD.order_id
 OR NEW.intent_id IS NOT OLD.intent_id
 OR NEW.idempotency_key IS NOT OLD.idempotency_key
 OR NEW.experiment_id IS NOT OLD.experiment_id
 OR NEW.market_id IS NOT OLD.market_id
 OR NEW.token_id IS NOT OLD.token_id
 OR NEW.side IS NOT OLD.side
 OR NEW.requested_size_micros IS NOT OLD.requested_size_micros
 OR NEW.limit_price_micros IS NOT OLD.limit_price_micros
 OR NEW.decision_timestamp IS NOT OLD.decision_timestamp
 OR NEW.book_snapshot_event_id IS NOT OLD.book_snapshot_event_id
 OR NEW.accounting_unit IS NOT OLD.accounting_unit
BEGIN
    SELECT RAISE(ABORT, 'identité ou champs économiques de l''ordre immuables');
END;

CREATE TRIGGER trg_estimates_identity_update
BEFORE UPDATE ON execution_estimates
WHEN NEW.estimate_id IS NOT OLD.estimate_id
 OR NEW.order_id IS NOT OLD.order_id
 OR NEW.intent_id IS NOT OLD.intent_id
 OR NEW.book_snapshot_event_id IS NOT OLD.book_snapshot_event_id
 OR NEW.arrival_timestamp IS NOT OLD.arrival_timestamp
 OR NEW.accounting_unit IS NOT OLD.accounting_unit
 OR NEW.executable_size_micros IS NOT OLD.executable_size_micros
 OR NEW.unfilled_size_micros IS NOT OLD.unfilled_size_micros
 OR NEW.vwap_micros IS NOT OLD.vwap_micros
 OR NEW.levels_json IS NOT OLD.levels_json
 OR NEW.assumptions_json IS NOT OLD.assumptions_json
BEGIN
    SELECT RAISE(ABORT, 'identité ou champs économiques de l''estimation immuables');
END;

-- Remplacements d'événements : append-only et même marché/token.
CREATE TRIGGER trg_event_replacements_no_update
BEFORE UPDATE ON event_replacements
BEGIN
    SELECT RAISE(ABORT, 'event_replacements est append-only');
END;

CREATE TRIGGER trg_event_replacements_no_delete
BEFORE DELETE ON event_replacements
BEGIN
    SELECT RAISE(ABORT, 'event_replacements est append-only');
END;

CREATE TRIGGER trg_event_replacements_same_market
BEFORE INSERT ON event_replacements
WHEN (SELECT market_id FROM market_events WHERE event_id = NEW.old_event_id)
     IS NOT (SELECT market_id FROM market_events WHERE event_id = NEW.new_event_id)
 OR (SELECT token_id FROM market_events WHERE event_id = NEW.old_event_id)
     IS NOT (SELECT token_id FROM market_events WHERE event_id = NEW.new_event_id)
BEGIN
    SELECT RAISE(ABORT, 'un remplacement doit viser le même marché et le même token');
END;

CREATE VIEW v_current_market_events AS
SELECT e.*
FROM market_events e
WHERE NOT EXISTS (
    SELECT 1 FROM event_replacements r WHERE r.old_event_id = e.event_id
);

-- ----------------------------------------------------------------------------
-- 10bis. Recréation des vues de lecture
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

CREATE VIEW v_negative_cash AS
SELECT
    t.experiment_id,
    SUM(p.amount_micros) AS cash_micros
FROM ledger_transactions t
JOIN ledger_postings p ON p.transaction_id = t.transaction_id AND p.account = 'CASH'
GROUP BY t.experiment_id
HAVING SUM(p.amount_micros) < 0;

CREATE VIEW v_position_anomalies AS
SELECT
    t.experiment_id,
    p.token_id,
    SUM(p.quantity_micros) AS quantity_micros
FROM ledger_transactions t
JOIN ledger_postings p ON p.transaction_id = t.transaction_id AND p.account = 'POSITION'
GROUP BY t.experiment_id, p.token_id
HAVING SUM(p.quantity_micros) < 0;

-- ----------------------------------------------------------------------------
-- 11. Version et journal
-- ----------------------------------------------------------------------------
PRAGMA user_version = 4;
INSERT INTO schema_migrations(version, name, applied_at)
VALUES (
    4,
    '0004_consolidation',
    strftime('%Y-%m-%dT%H:%M:%f', 'now') || '000Z'
);

COMMIT;
PRAGMA foreign_keys = ON;
