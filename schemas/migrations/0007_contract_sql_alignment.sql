-- ============================================================================
-- CANDIDAT NON GELÉ — 0007_contract_sql_alignment (0.6 -> 0.7)
-- Aligne SQLite sur le contrat 1.2.0 :
--   * une expérience non paper_live exige end_time NOT NULL ;
--   * une fin existante reste strictement postérieure à start_time ;
--   * les défauts schema_version deviennent 1.2.0 ;
--   * les lignes existantes conservent leur schema_version d'origine.
-- Ne pas exécuter sur la base de travail. Tester sur une copie temporaire.
-- ----------------------------------------------------------------------------
-- Préconditions : user_version = 6, journal [4, 5, 6]. Le préflight refuse
-- toute ligne non paper_live sans end_time ; aucune date n'est inventée.
-- ============================================================================

PRAGMA foreign_keys = OFF;
BEGIN IMMEDIATE;

DROP VIEW IF EXISTS v_order_execution;
DROP VIEW IF EXISTS v_experiment_cash;
DROP VIEW IF EXISTS v_experiment_positions;
DROP VIEW IF EXISTS v_ledger_anomalies;
DROP VIEW IF EXISTS v_experiment_latest_snapshot;
DROP VIEW IF EXISTS v_negative_cash;
DROP VIEW IF EXISTS v_position_anomalies;

-- Les triggers des tables dépendantes compilent une référence à experiments.
-- Ils sont recréés après la reconstruction, à l'identique.
DROP TRIGGER IF EXISTS trg_estimates_unit_insert;
DROP TRIGGER IF EXISTS trg_estimates_unit_update;
DROP TRIGGER IF EXISTS trg_fills_unit_insert;
DROP TRIGGER IF EXISTS trg_ledger_postings_unit_insert;
DROP TRIGGER IF EXISTS trg_orders_unit_insert;
DROP TRIGGER IF EXISTS trg_orders_unit_update;

-- ----------------------------------------------------------------------------
-- 0. Préflight : compter les expériences incompatibles
-- ----------------------------------------------------------------------------
CREATE TEMP TABLE _preflight_0007_end_time (
    bad INTEGER NOT NULL CHECK (bad = 0)
);
INSERT INTO _preflight_0007_end_time(bad)
SELECT COUNT(*)
FROM experiments
WHERE period_type <> 'paper_live' AND end_time IS NULL;
DROP TABLE _preflight_0007_end_time;

-- ----------------------------------------------------------------------------
-- 1. Reconstruire fee_schedules avec le défaut 1.2.0
-- ----------------------------------------------------------------------------
CREATE TABLE fee_schedules_v7 (
    fee_schedule_id          TEXT PRIMARY KEY,
    schema_version           TEXT NOT NULL DEFAULT '1.2.0',
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
    supersedes_fee_schedule_id TEXT REFERENCES fee_schedules_v7(fee_schedule_id),
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

INSERT INTO fee_schedules_v7 (
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
    fee_formula, formula_definition_ref, custom_formula_ref, fee_charge_unit,
    rounding_rule, rounding_increment_micros, notes, supersedes_fee_schedule_id,
    created_at
FROM fee_schedules;

DROP TABLE fee_schedules;
ALTER TABLE fee_schedules_v7 RENAME TO fee_schedules;

-- ----------------------------------------------------------------------------
-- 2. Reconstruire experiments : fin obligatoire hors paper_live
-- ----------------------------------------------------------------------------
CREATE TABLE experiments_v7 (
    experiment_id              TEXT PRIMARY KEY,
    schema_version             TEXT NOT NULL DEFAULT '1.2.0',
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
    config_hash_version        TEXT,
    experiment_config_json     TEXT,
    FOREIGN KEY (strategy_id, strategy_version) REFERENCES strategies(strategy_id, version),
    CHECK (end_time IS NULL OR end_time > start_time),
    CHECK (period_type = 'paper_live' OR end_time IS NOT NULL),
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

INSERT INTO experiments_v7 (
    experiment_id, schema_version, strategy_id, strategy_version, period_type,
    start_time, end_time, initial_capital_micros, accounting_unit,
    presentation_currency, presentation_conversion_json, data_manifest_id,
    code_version, config_hash, execution_assumptions_json, risk_limits_json,
    default_fee_schedule_id, fee_status, random_seed, status, created_at,
    completed_at, config_hash_version, experiment_config_json
)
SELECT
    experiment_id, schema_version, strategy_id, strategy_version, period_type,
    start_time, end_time, initial_capital_micros, accounting_unit,
    presentation_currency, presentation_conversion_json, data_manifest_id,
    code_version, config_hash, execution_assumptions_json, risk_limits_json,
    default_fee_schedule_id, fee_status, random_seed, status, created_at,
    completed_at, config_hash_version, experiment_config_json
FROM experiments;

DROP TABLE experiments;
ALTER TABLE experiments_v7 RENAME TO experiments;

-- ----------------------------------------------------------------------------
-- 3. Recréer les triggers des tables reconstruites
-- ----------------------------------------------------------------------------
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

CREATE TRIGGER trg_experiments_config_hash
BEFORE INSERT ON experiments
WHEN length(NEW.config_hash) <> 71
 OR substr(NEW.config_hash, 1, 7) <> 'sha256:'
 OR substr(NEW.config_hash, 8) GLOB '*[^0-9a-f]*'
BEGIN
    SELECT RAISE(ABORT, 'config_hash doit être sha256:<64 hex minuscules>');
END;

CREATE TRIGGER trg_experiments_immutable_update
BEFORE UPDATE ON experiments
WHEN NEW.experiment_id IS NOT OLD.experiment_id
 OR NEW.schema_version IS NOT OLD.schema_version
 OR NEW.strategy_id IS NOT OLD.strategy_id
 OR NEW.strategy_version IS NOT OLD.strategy_version
 OR NEW.period_type IS NOT OLD.period_type
 OR NEW.start_time IS NOT OLD.start_time
 OR NEW.end_time IS NOT OLD.end_time
 OR NEW.initial_capital_micros IS NOT OLD.initial_capital_micros
 OR NEW.accounting_unit IS NOT OLD.accounting_unit
 OR NEW.presentation_currency IS NOT OLD.presentation_currency
 OR NEW.presentation_conversion_json IS NOT OLD.presentation_conversion_json
 OR NEW.data_manifest_id IS NOT OLD.data_manifest_id
 OR NEW.code_version IS NOT OLD.code_version
 OR NEW.config_hash IS NOT OLD.config_hash
 OR NEW.config_hash_version IS NOT OLD.config_hash_version
 OR NEW.experiment_config_json IS NOT OLD.experiment_config_json
 OR NEW.execution_assumptions_json IS NOT OLD.execution_assumptions_json
 OR NEW.risk_limits_json IS NOT OLD.risk_limits_json
 OR NEW.default_fee_schedule_id IS NOT OLD.default_fee_schedule_id
 OR NEW.fee_status IS NOT OLD.fee_status
 OR NEW.random_seed IS NOT OLD.random_seed
 OR NEW.created_at IS NOT OLD.created_at
BEGIN
    SELECT RAISE(ABORT, 'champs de reproductibilité de l''expérience immuables');
END;

CREATE TRIGGER trg_experiments_status_transition
BEFORE UPDATE OF status ON experiments
WHEN NOT (
    NEW.status IS OLD.status
    OR (OLD.status = 'planned' AND NEW.status IN ('running', 'aborted', 'invalid'))
    OR (OLD.status = 'running' AND NEW.status IN ('completed', 'aborted', 'invalid'))
)
BEGIN
    SELECT RAISE(ABORT, 'transition de statut non autorisée');
END;

CREATE TRIGGER trg_experiments_completed_at
BEFORE INSERT ON experiments
WHEN (NEW.status IN ('completed', 'aborted', 'invalid') AND NEW.completed_at IS NULL)
 OR (NEW.status IN ('planned', 'running') AND NEW.completed_at IS NOT NULL)
BEGIN
    SELECT RAISE(ABORT, 'completed_at incohérent avec le statut');
END;

CREATE TRIGGER trg_experiments_completed_at_update
BEFORE UPDATE OF status, completed_at ON experiments
WHEN (NEW.status IN ('completed', 'aborted', 'invalid') AND NEW.completed_at IS NULL)
 OR (NEW.status IN ('planned', 'running') AND NEW.completed_at IS NOT NULL)
BEGIN
    SELECT RAISE(ABORT, 'completed_at incohérent avec le statut');
END;

CREATE TRIGGER trg_experiments_final_fixture_insert
BEFORE INSERT ON experiments
WHEN NEW.period_type = 'final_test'
 AND NEW.data_manifest_id IS NOT NULL
 AND (SELECT source_class FROM data_manifests WHERE manifest_id = NEW.data_manifest_id) = 'fixture'
BEGIN
    SELECT RAISE(ABORT, 'final_test ne peut pas utiliser un manifeste fixture');
END;

CREATE TRIGGER trg_experiments_final_fixture_update
BEFORE UPDATE OF period_type, data_manifest_id ON experiments
WHEN NEW.period_type = 'final_test'
 AND NEW.data_manifest_id IS NOT NULL
 AND (SELECT source_class FROM data_manifests WHERE manifest_id = NEW.data_manifest_id) = 'fixture'
BEGIN
    SELECT RAISE(ABORT, 'final_test ne peut pas utiliser un manifeste fixture');
END;

CREATE TRIGGER trg_experiments_config_v2
BEFORE INSERT ON experiments
WHEN NEW.config_hash_version IS NOT 'config/v2'
 OR NEW.experiment_config_json IS NULL
BEGIN
    SELECT RAISE(ABORT, 'nouvelle expérience : config/v2 et document de config requis');
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

-- ----------------------------------------------------------------------------
-- 4. Recréer les vues qui lisent les tables reconstruites
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
-- 5. Version et journal
-- ----------------------------------------------------------------------------
PRAGMA user_version = 7;
INSERT INTO schema_migrations(version, name, applied_at)
VALUES (
    7,
    '0007_contract_sql_alignment',
    strftime('%Y-%m-%dT%H:%M:%f', 'now') || '000Z'
);

COMMIT;
PRAGMA foreign_keys = ON;
