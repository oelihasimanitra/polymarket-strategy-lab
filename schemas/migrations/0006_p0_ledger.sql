-- ============================================================================
-- CANDIDAT NON GELÉ — 0006_p0_ledger (0.5 -> 0.6)
-- B-06 : unicité du grand livre et des conversions par expérience.
-- Ne pas exécuter sur la base de travail. Tester sur une copie temporaire.
-- ----------------------------------------------------------------------------
-- Préconditions : user_version = 5, journal [4, 5]. La migration n'invente
-- aucun rattachement : une conversion dont l'expérience ne peut pas être
-- dérivée de façon unique depuis le grand livre fait échouer le préflight.
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

-- ----------------------------------------------------------------------------
-- 0. Préflight : aucune conversion ambiguë ou orpheline
-- ----------------------------------------------------------------------------
CREATE TEMP TABLE _preflight_conversion_experiment (bad INTEGER NOT NULL CHECK (bad = 0));
INSERT INTO _preflight_conversion_experiment
SELECT COUNT(*)
FROM settlement_conversions c
WHERE (
    SELECT COUNT(DISTINCT t.experiment_id)
    FROM ledger_transactions t
    WHERE t.ref_type = 'market_resolution'
      AND t.ref_id = c.resolution_event_id
      AND t.kind = 'settlement'
) <> 1;
DROP TABLE _preflight_conversion_experiment;

CREATE TEMP TABLE _preflight_ledger_duplicates (bad INTEGER NOT NULL CHECK (bad = 0));
INSERT INTO _preflight_ledger_duplicates
SELECT COUNT(*) FROM (
    SELECT experiment_id, ref_type, ref_id, kind
    FROM ledger_transactions
    GROUP BY experiment_id, ref_type, ref_id, kind
    HAVING COUNT(*) > 1
);
DROP TABLE _preflight_ledger_duplicates;

CREATE TEMP TABLE _preflight_idempotency (bad INTEGER NOT NULL CHECK (bad = 0));
INSERT INTO _preflight_idempotency
SELECT COUNT(*) FROM (
    SELECT experiment_id, idempotency_key
    FROM ledger_transactions
    GROUP BY experiment_id, idempotency_key
    HAVING COUNT(*) > 1
);
DROP TABLE _preflight_idempotency;

-- ----------------------------------------------------------------------------
-- 1. Reconstruire ledger_transactions : unicité par expérience
-- ----------------------------------------------------------------------------
-- Ce trigger appartient à ledger_postings mais référence la table reconstruite.
DROP TRIGGER IF EXISTS trg_ledger_postings_unit_insert;

CREATE TABLE ledger_transactions_v6 (
    transaction_id TEXT PRIMARY KEY,
    experiment_id  TEXT NOT NULL REFERENCES experiments(experiment_id),
    occurred_at    TEXT NOT NULL,
    kind           TEXT NOT NULL
                   CHECK (kind IN ('deposit', 'withdrawal', 'fill', 'fee', 'settlement',
                                   'adjustment', 'reversal')),
    ref_type       TEXT NOT NULL CHECK (ref_type IN ('fill', 'market_resolution', 'manual', 'experiment')),
    ref_id         TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    memo           TEXT NOT NULL DEFAULT '',
    created_at     TEXT NOT NULL,
    UNIQUE (experiment_id, ref_type, ref_id, kind),
    UNIQUE (experiment_id, idempotency_key),
    CHECK (occurred_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9].[0-9][0-9][0-9][0-9][0-9][0-9]Z'),
    CHECK (created_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9].[0-9][0-9][0-9][0-9][0-9][0-9]Z')
) STRICT;

INSERT INTO ledger_transactions_v6 (
    transaction_id, experiment_id, occurred_at, kind, ref_type, ref_id,
    idempotency_key, memo, created_at
)
SELECT
    transaction_id, experiment_id, occurred_at, kind, ref_type, ref_id,
    idempotency_key, memo, created_at
FROM ledger_transactions;

DROP TABLE ledger_transactions;
ALTER TABLE ledger_transactions_v6 RENAME TO ledger_transactions;

CREATE INDEX idx_ledger_tx_experiment_time ON ledger_transactions(experiment_id, occurred_at);
CREATE INDEX idx_ledger_tx_ref ON ledger_transactions(ref_type, ref_id);
CREATE INDEX idx_ledger_tx_experiment_ref
    ON ledger_transactions(experiment_id, ref_type, ref_id);

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

CREATE TRIGGER trg_ledger_transactions_no_conflicting_insert
BEFORE INSERT ON ledger_transactions
WHEN EXISTS (
    SELECT 1 FROM ledger_transactions
    WHERE transaction_id = NEW.transaction_id
       OR (experiment_id = NEW.experiment_id
           AND idempotency_key = NEW.idempotency_key)
       OR (experiment_id = NEW.experiment_id
           AND ref_type = NEW.ref_type
           AND ref_id = NEW.ref_id
           AND kind = NEW.kind)
)
BEGIN
    SELECT RAISE(ABORT, 'INSERT OR REPLACE interdit sur ledger_transactions');
END;

CREATE TRIGGER trg_ledger_fee_ref_fill
BEFORE INSERT ON ledger_transactions
WHEN NEW.kind = 'fee' AND NEW.ref_type = 'fill'
BEGIN
    SELECT RAISE(ABORT, 'V1 : les frais sont inclus dans la transaction du fill');
END;

-- Recréé à l'identique après reconstruction de sa table cible.
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

-- ----------------------------------------------------------------------------
-- 2. Reconstruire settlement_conversions : experiment_id obligatoire
-- ----------------------------------------------------------------------------
CREATE TABLE settlement_conversions_v6 (
    conversion_id           TEXT PRIMARY KEY,
    experiment_id           TEXT NOT NULL REFERENCES experiments(experiment_id),
    resolution_event_id     TEXT NOT NULL REFERENCES market_resolution_events(event_id),
    source_asset            TEXT NOT NULL,
    source_amount_micros    INTEGER NOT NULL CHECK (source_amount_micros >= 0),
    target_unit             TEXT NOT NULL,
    target_amount_micros    INTEGER NOT NULL CHECK (target_amount_micros >= 0),
    conversion_rule_ref     TEXT NOT NULL,
    rate_micros             INTEGER CHECK (rate_micros IS NULL OR rate_micros >= 0),
    conversion_timestamp    TEXT NOT NULL,
    created_at              TEXT NOT NULL,
    UNIQUE (experiment_id, resolution_event_id, source_asset, target_unit),
    CHECK (length(target_unit) BETWEEN 2 AND 32
           AND target_unit GLOB '[A-Za-z][A-Za-z0-9._-]*'),
    CHECK (conversion_timestamp GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9].[0-9][0-9][0-9][0-9][0-9][0-9]Z'),
    CHECK (created_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9].[0-9][0-9][0-9][0-9][0-9][0-9]Z')
) STRICT;

INSERT INTO settlement_conversions_v6 (
    conversion_id, experiment_id, resolution_event_id, source_asset,
    source_amount_micros, target_unit, target_amount_micros,
    conversion_rule_ref, rate_micros, conversion_timestamp, created_at
)
SELECT
    c.conversion_id,
    (
        SELECT MIN(t.experiment_id)
        FROM ledger_transactions t
        WHERE t.ref_type = 'market_resolution'
          AND t.ref_id = c.resolution_event_id
          AND t.kind = 'settlement'
    ),
    c.resolution_event_id, c.source_asset, c.source_amount_micros,
    c.target_unit, c.target_amount_micros, c.conversion_rule_ref,
    c.rate_micros, c.conversion_timestamp, c.created_at
FROM settlement_conversions c;

DROP TABLE settlement_conversions;
ALTER TABLE settlement_conversions_v6 RENAME TO settlement_conversions;

CREATE INDEX idx_settlement_conversions_resolution
    ON settlement_conversions(resolution_event_id);
CREATE INDEX idx_settlement_conversions_experiment
    ON settlement_conversions(experiment_id, resolution_event_id);

CREATE TRIGGER trg_settlement_conversions_no_update
BEFORE UPDATE ON settlement_conversions
BEGIN
    SELECT RAISE(ABORT, 'settlement_conversions est append-only');
END;

CREATE TRIGGER trg_settlement_conversions_no_delete
BEFORE DELETE ON settlement_conversions
BEGIN
    SELECT RAISE(ABORT, 'settlement_conversions est append-only');
END;

CREATE TRIGGER trg_settlement_conversions_no_conflicting_insert
BEFORE INSERT ON settlement_conversions
WHEN EXISTS (
    SELECT 1 FROM settlement_conversions
    WHERE conversion_id = NEW.conversion_id
       OR (experiment_id = NEW.experiment_id
           AND resolution_event_id = NEW.resolution_event_id
           AND source_asset = NEW.source_asset
           AND target_unit = NEW.target_unit)
)
BEGIN
    SELECT RAISE(ABORT, 'INSERT OR REPLACE interdit sur settlement_conversions');
END;

CREATE TRIGGER trg_settlement_conversions_provenance
BEFORE INSERT ON settlement_conversions
WHEN NOT EXISTS (
    SELECT 1 FROM ledger_transactions t
    WHERE t.experiment_id = NEW.experiment_id
      AND t.ref_type = 'market_resolution'
      AND t.ref_id = NEW.resolution_event_id
      AND t.kind = 'settlement'
)
BEGIN
    SELECT RAISE(ABORT, 'conversion sans transaction de settlement de la même expérience');
END;

-- ----------------------------------------------------------------------------
-- 3. Recréer les vues de lecture
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
-- 4. Version et journal
-- ----------------------------------------------------------------------------
PRAGMA user_version = 6;
INSERT INTO schema_migrations(version, name, applied_at)
VALUES (
    6,
    '0006_p0_ledger',
    strftime('%Y-%m-%dT%H:%M:%f', 'now') || '000Z'
);

COMMIT;
PRAGMA foreign_keys = ON;
