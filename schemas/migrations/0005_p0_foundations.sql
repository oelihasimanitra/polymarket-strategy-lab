-- ============================================================================
-- CANDIDAT NON GELÉ — 0005_p0_foundations (0.4 -> 0.5)
-- B-01 (identité v2), B-02 (manifestes/hashes) et B-05 (provenance).
-- Ne pas exécuter sur la base de travail. Tester sur une copie temporaire.
-- ----------------------------------------------------------------------------
-- Préconditions : user_version = 4, journal [4]. Aucune valeur historique
-- inventée : les lignes legacy sont marquées v1/legacy, jamais recalculées.
-- ============================================================================

PRAGMA foreign_keys = OFF;
BEGIN IMMEDIATE;

DROP VIEW IF EXISTS v_current_market_events;
DROP VIEW IF EXISTS v_manifest_event_visibility;

-- ----------------------------------------------------------------------------
-- 0. Préflight : refuser les données legacy incompatibles
-- ----------------------------------------------------------------------------
CREATE TEMP TABLE _preflight_replacements (bad INTEGER NOT NULL CHECK (bad = 0));
INSERT INTO _preflight_replacements
SELECT COUNT(*)
FROM event_replacements r
JOIN market_events eo ON eo.event_id = r.old_event_id
JOIN market_events en ON en.event_id = r.new_event_id
WHERE r.created_at < MAX(eo.received_timestamp, en.received_timestamp);
DROP TABLE _preflight_replacements;

CREATE TEMP TABLE _preflight_final_fixture (bad INTEGER NOT NULL CHECK (bad = 0));
INSERT INTO _preflight_final_fixture
SELECT COUNT(*)
FROM experiments x
JOIN data_manifests m ON m.manifest_id = x.data_manifest_id
WHERE x.period_type = 'final_test' AND m.source_class = 'fixture';
DROP TABLE _preflight_final_fixture;

CREATE TEMP TABLE _preflight_experiment_status (bad INTEGER NOT NULL CHECK (bad = 0));
INSERT INTO _preflight_experiment_status
SELECT COUNT(*)
FROM experiments
WHERE (status IN ('completed', 'aborted', 'invalid') AND completed_at IS NULL)
   OR (status IN ('planned', 'running') AND completed_at IS NOT NULL);
DROP TABLE _preflight_experiment_status;

CREATE TEMP TABLE _preflight_shapes (bad INTEGER NOT NULL CHECK (bad = 0));
INSERT INTO _preflight_shapes
SELECT COUNT(*)
FROM market_events e
WHERE (e.event_type = 'connection_status'
       AND (e.market_id IS NOT NULL OR e.token_id IS NOT NULL))
   OR (e.event_type IN ('trade', 'book_snapshot', 'book_delta')
       AND (e.market_id IS NULL OR e.token_id IS NULL))
   OR (e.event_type IN ('market_metadata', 'trader_activity', 'market_resolution')
       AND e.market_id IS NULL);
DROP TABLE _preflight_shapes;

-- ----------------------------------------------------------------------------
-- 1. market_events : version d'identité et index v1/v2
-- ----------------------------------------------------------------------------
ALTER TABLE market_events ADD COLUMN event_identity_version TEXT;

-- Le backfill est une opération de migration unique. Le trigger append-only
-- existant est retiré puis recréé à l'identique autour de cet UPDATE.
DROP TRIGGER IF EXISTS trg_market_events_no_update;
UPDATE market_events
SET event_identity_version = 'v1'
WHERE event_identity_version IS NULL
  AND schema_version IN ('1.0.0', '1.1.0');
-- Les lignes de version inconnue restent NULL : aucune valeur n'est inventée.
CREATE TRIGGER trg_market_events_no_update
BEFORE UPDATE ON market_events
BEGIN
    SELECT RAISE(ABORT, 'market_events est append-only');
END;

DROP INDEX IF EXISTS ux_market_events_source_event;

CREATE UNIQUE INDEX ux_market_events_source_v1
ON market_events(source, source_event_id)
WHERE source_event_id IS NOT NULL
  AND (event_identity_version IS NULL OR event_identity_version = 'v1');

CREATE UNIQUE INDEX ux_market_events_source_v2
ON market_events(source, source_event_id, event_type, COALESCE(normalizer_version, ''))
WHERE source_event_id IS NOT NULL
  AND event_identity_version = 'v2';

CREATE UNIQUE INDEX ux_market_events_payload_v2_token
ON market_events(
    source, raw_payload_sha256, event_type, COALESCE(normalizer_version, ''),
    source_timestamp, market_id, token_id
)
WHERE source_event_id IS NULL
  AND event_identity_version = 'v2'
  AND market_id IS NOT NULL AND token_id IS NOT NULL;

CREATE UNIQUE INDEX ux_market_events_payload_v2_market
ON market_events(
    source, raw_payload_sha256, event_type, COALESCE(normalizer_version, ''),
    source_timestamp, market_id
)
WHERE source_event_id IS NULL
  AND event_identity_version = 'v2'
  AND market_id IS NOT NULL AND token_id IS NULL;

CREATE UNIQUE INDEX ux_market_events_payload_v2_global
ON market_events(
    source, raw_payload_sha256, event_type, COALESCE(normalizer_version, ''),
    source_timestamp
)
WHERE source_event_id IS NULL
  AND event_identity_version = 'v2'
  AND market_id IS NULL AND token_id IS NULL;

-- ----------------------------------------------------------------------------
-- 2. event_replacements : visibilité temporelle
-- ----------------------------------------------------------------------------
CREATE TABLE event_replacements_v5 (
    replacement_id    TEXT PRIMARY KEY,
    old_event_id      TEXT NOT NULL UNIQUE REFERENCES market_events(event_id),
    new_event_id      TEXT NOT NULL UNIQUE REFERENCES market_events(event_id),
    reason            TEXT NOT NULL
                      CHECK (reason IN ('reparse', 'source_correction', 'contract_migration', 'other')),
    normalizer_version TEXT NOT NULL,
    evidence_ref      TEXT,
    created_at        TEXT NOT NULL,
    visible_from_received_timestamp TEXT NOT NULL,
    CHECK (old_event_id <> new_event_id),
    CHECK (created_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9].[0-9][0-9][0-9][0-9][0-9][0-9]Z'),
    CHECK (visible_from_received_timestamp GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9].[0-9][0-9][0-9][0-9][0-9][0-9]Z')
) STRICT;

INSERT INTO event_replacements_v5(
    replacement_id, old_event_id, new_event_id, reason, normalizer_version,
    evidence_ref, created_at, visible_from_received_timestamp
)
SELECT
    r.replacement_id, r.old_event_id, r.new_event_id, r.reason,
    r.normalizer_version, r.evidence_ref, r.created_at, r.created_at
FROM event_replacements r;
DROP TABLE event_replacements;
ALTER TABLE event_replacements_v5 RENAME TO event_replacements;
CREATE INDEX idx_event_replacements_new ON event_replacements(new_event_id);

-- ----------------------------------------------------------------------------
-- 3. Manifestes : version, événements, remplacements, scellement
-- ----------------------------------------------------------------------------
ALTER TABLE data_manifests ADD COLUMN hash_version TEXT;
ALTER TABLE data_manifests ADD COLUMN event_id_algorithm TEXT;
UPDATE data_manifests
SET hash_version = 'legacy/v1',
    event_id_algorithm = 'event-id/v1'
WHERE hash_version IS NULL;

CREATE TABLE manifest_events (
    manifest_id TEXT NOT NULL REFERENCES data_manifests(manifest_id),
    event_id    TEXT NOT NULL REFERENCES market_events(event_id),
    ordinal     INTEGER NOT NULL CHECK (ordinal >= 0),
    PRIMARY KEY (manifest_id, event_id),
    UNIQUE (manifest_id, ordinal)
) STRICT;

CREATE TABLE manifest_replacements (
    manifest_id    TEXT NOT NULL REFERENCES data_manifests(manifest_id),
    replacement_id TEXT NOT NULL REFERENCES event_replacements(replacement_id),
    ordinal        INTEGER NOT NULL CHECK (ordinal >= 0),
    PRIMARY KEY (manifest_id, replacement_id),
    UNIQUE (manifest_id, ordinal)
) STRICT;

CREATE TABLE manifest_seals (
    manifest_id       TEXT PRIMARY KEY REFERENCES data_manifests(manifest_id),
    sealed_at         TEXT NOT NULL,
    manifest_hash     TEXT NOT NULL CHECK (length(manifest_hash) = 64
                                           AND manifest_hash NOT GLOB '*[^0-9a-f]*'),
    event_count       INTEGER NOT NULL CHECK (event_count >= 0),
    replacement_count INTEGER NOT NULL CHECK (replacement_count >= 0),
    CHECK (sealed_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9].[0-9][0-9][0-9][0-9][0-9][0-9]Z')
) STRICT;

-- ----------------------------------------------------------------------------
-- 4. Expériences : config document et version de hash
-- ----------------------------------------------------------------------------
ALTER TABLE experiments ADD COLUMN config_hash_version TEXT;
ALTER TABLE experiments ADD COLUMN experiment_config_json TEXT;
UPDATE experiments
SET config_hash_version = 'legacy/v1'
WHERE config_hash_version IS NULL;

-- ----------------------------------------------------------------------------
-- 5. Triggers market_events : forme et identité
-- ----------------------------------------------------------------------------
CREATE TRIGGER trg_market_events_identity_v2
BEFORE INSERT ON market_events
WHEN NEW.schema_version = '1.2.0'
 AND (NEW.event_identity_version IS NOT 'v2'
      OR NEW.normalizer_version IS NULL)
BEGIN
    SELECT RAISE(ABORT, '1.2.0 exige event_identity_version=v2 et normalizer_version');
END;

CREATE TRIGGER trg_market_events_anchor_v2
BEFORE INSERT ON market_events
WHEN NEW.schema_version = '1.2.0'
 AND NEW.source_event_id IS NULL
 AND NEW.raw_payload_sha256 IS NULL
BEGIN
    SELECT RAISE(ABORT, '1.2.0 exige source_event_id ou raw_payload_sha256');
END;

CREATE TRIGGER trg_market_events_shape_v2
BEFORE INSERT ON market_events
WHEN NEW.schema_version = '1.2.0'
 AND (
      (NEW.event_type = 'connection_status'
       AND (NEW.market_id IS NOT NULL OR NEW.token_id IS NOT NULL))
   OR (NEW.event_type IN ('trade', 'book_snapshot', 'book_delta')
       AND (NEW.market_id IS NULL OR NEW.token_id IS NULL))
   OR (NEW.event_type IN ('market_metadata', 'trader_activity', 'market_resolution')
       AND NEW.market_id IS NULL)
 )
BEGIN
    SELECT RAISE(ABORT, 'forme market_id/token_id invalide pour ce type d''événement');
END;

-- ----------------------------------------------------------------------------
-- 6. Triggers event_replacements
-- ----------------------------------------------------------------------------
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

-- `INSERT OR REPLACE` contourne le trigger DELETE quand recursive_triggers=OFF.
-- Ce trigger BEFORE INSERT refuse toute collision avant la résolution REPLACE.
CREATE TRIGGER trg_event_replacements_no_conflicting_insert
BEFORE INSERT ON event_replacements
WHEN EXISTS (
    SELECT 1 FROM event_replacements
    WHERE replacement_id = NEW.replacement_id
       OR old_event_id = NEW.old_event_id
       OR new_event_id = NEW.new_event_id
)
BEGIN
    SELECT RAISE(ABORT, 'INSERT OR REPLACE interdit sur event_replacements');
END;

CREATE TRIGGER trg_event_replacements_scope
BEFORE INSERT ON event_replacements
WHEN (SELECT source FROM market_events WHERE event_id = NEW.old_event_id)
     IS NOT (SELECT source FROM market_events WHERE event_id = NEW.new_event_id)
 OR (SELECT event_type FROM market_events WHERE event_id = NEW.old_event_id)
     IS NOT (SELECT event_type FROM market_events WHERE event_id = NEW.new_event_id)
 OR (SELECT market_id FROM market_events WHERE event_id = NEW.old_event_id)
     IS NOT (SELECT market_id FROM market_events WHERE event_id = NEW.new_event_id)
 OR (SELECT token_id FROM market_events WHERE event_id = NEW.old_event_id)
     IS NOT (SELECT token_id FROM market_events WHERE event_id = NEW.new_event_id)
BEGIN
    SELECT RAISE(ABORT, 'un remplacement doit viser la même source, type, marché et token');
END;

CREATE TRIGGER trg_event_replacements_visible_from
BEFORE INSERT ON event_replacements
WHEN NEW.visible_from_received_timestamp IS NOT MAX(
    (SELECT received_timestamp FROM market_events WHERE event_id = NEW.old_event_id),
    (SELECT received_timestamp FROM market_events WHERE event_id = NEW.new_event_id),
    NEW.created_at
)
BEGIN
    SELECT RAISE(ABORT, 'visible_from doit être max(old.received, new.received, created_at)');
END;

CREATE TRIGGER trg_event_replacements_created_at_not_before
BEFORE INSERT ON event_replacements
WHEN NEW.created_at < MAX(
    (SELECT received_timestamp FROM market_events WHERE event_id = NEW.old_event_id),
    (SELECT received_timestamp FROM market_events WHERE event_id = NEW.new_event_id)
)
BEGIN
    SELECT RAISE(ABORT, 'created_at ne peut pas précéder les événements remplacés');
END;

CREATE TRIGGER trg_event_replacements_normalizer
BEFORE INSERT ON event_replacements
WHEN NEW.normalizer_version IS NOT
     (SELECT normalizer_version FROM market_events WHERE event_id = NEW.new_event_id)
BEGIN
    SELECT RAISE(ABORT, 'normalizer_version doit être celle du nouvel événement');
END;

CREATE TRIGGER trg_event_replacements_no_cycle
BEFORE INSERT ON event_replacements
WHEN EXISTS (
    WITH RECURSIVE reach(event_id) AS (
        SELECT NEW.new_event_id
        UNION
        SELECT r.new_event_id
        FROM event_replacements r
        JOIN reach ON r.old_event_id = reach.event_id
    )
    SELECT 1 FROM reach WHERE event_id = NEW.old_event_id
)
BEGIN
    SELECT RAISE(ABORT, 'cycle de remplacement interdit');
END;

CREATE TRIGGER trg_event_replacements_monotone
BEFORE INSERT ON event_replacements
WHEN NEW.visible_from_received_timestamp < COALESCE(
        (SELECT r.visible_from_received_timestamp
         FROM event_replacements r WHERE r.new_event_id = NEW.old_event_id),
        (SELECT received_timestamp FROM market_events WHERE event_id = NEW.old_event_id)
    )
 OR EXISTS (
     SELECT 1 FROM event_replacements r
     WHERE r.old_event_id = NEW.new_event_id
       AND r.visible_from_received_timestamp <= NEW.visible_from_received_timestamp
 )
BEGIN
    SELECT RAISE(ABORT, 'chaîne de remplacement non monotone');
END;

-- ----------------------------------------------------------------------------
-- 7. Triggers manifestes
-- ----------------------------------------------------------------------------
CREATE TRIGGER trg_data_manifests_no_update
BEFORE UPDATE ON data_manifests
BEGIN
    SELECT RAISE(ABORT, 'data_manifests est append-only');
END;

CREATE TRIGGER trg_data_manifests_no_delete
BEFORE DELETE ON data_manifests
BEGIN
    SELECT RAISE(ABORT, 'data_manifests est append-only');
END;

CREATE TRIGGER trg_data_manifests_no_conflicting_insert
BEFORE INSERT ON data_manifests
WHEN EXISTS (SELECT 1 FROM data_manifests WHERE manifest_id = NEW.manifest_id)
BEGIN
    SELECT RAISE(ABORT, 'INSERT OR REPLACE interdit sur data_manifests');
END;

CREATE TRIGGER trg_data_manifests_v2_insert
BEFORE INSERT ON data_manifests
WHEN NEW.hash_version IS NOT 'manifest/v2'
 OR NEW.event_id_algorithm IS NOT 'event-id/v2'
BEGIN
    SELECT RAISE(ABORT, 'nouveau manifeste : hash_version=manifest/v2 et event-id/v2 requis');
END;

CREATE TRIGGER trg_manifest_events_no_update
BEFORE UPDATE ON manifest_events
BEGIN
    SELECT RAISE(ABORT, 'manifest_events est append-only');
END;

CREATE TRIGGER trg_manifest_events_no_delete
BEFORE DELETE ON manifest_events
BEGIN
    SELECT RAISE(ABORT, 'manifest_events est append-only');
END;

CREATE TRIGGER trg_manifest_events_no_conflicting_insert
BEFORE INSERT ON manifest_events
WHEN EXISTS (
    SELECT 1 FROM manifest_events
    WHERE (manifest_id = NEW.manifest_id AND event_id = NEW.event_id)
       OR (manifest_id = NEW.manifest_id AND ordinal = NEW.ordinal)
)
BEGIN
    SELECT RAISE(ABORT, 'INSERT OR REPLACE interdit sur manifest_events');
END;

CREATE TRIGGER trg_manifest_replacements_no_update
BEFORE UPDATE ON manifest_replacements
BEGIN
    SELECT RAISE(ABORT, 'manifest_replacements est append-only');
END;

CREATE TRIGGER trg_manifest_replacements_no_delete
BEFORE DELETE ON manifest_replacements
BEGIN
    SELECT RAISE(ABORT, 'manifest_replacements est append-only');
END;

CREATE TRIGGER trg_manifest_replacements_no_conflicting_insert
BEFORE INSERT ON manifest_replacements
WHEN EXISTS (
    SELECT 1 FROM manifest_replacements
    WHERE (manifest_id = NEW.manifest_id AND replacement_id = NEW.replacement_id)
       OR (manifest_id = NEW.manifest_id AND ordinal = NEW.ordinal)
)
BEGIN
    SELECT RAISE(ABORT, 'INSERT OR REPLACE interdit sur manifest_replacements');
END;

CREATE TRIGGER trg_manifest_events_sealed
BEFORE INSERT ON manifest_events
WHEN EXISTS (SELECT 1 FROM manifest_seals WHERE manifest_id = NEW.manifest_id)
BEGIN
    SELECT RAISE(ABORT, 'manifeste déjà scellé');
END;

CREATE TRIGGER trg_manifest_replacements_sealed
BEFORE INSERT ON manifest_replacements
WHEN EXISTS (SELECT 1 FROM manifest_seals WHERE manifest_id = NEW.manifest_id)
BEGIN
    SELECT RAISE(ABORT, 'manifeste déjà scellé');
END;

CREATE TRIGGER trg_manifest_events_cutoff
BEFORE INSERT ON manifest_events
WHEN (SELECT received_timestamp FROM market_events WHERE event_id = NEW.event_id)
     > (SELECT cutoff_received_timestamp FROM data_manifests WHERE manifest_id = NEW.manifest_id)
BEGIN
    SELECT RAISE(ABORT, 'événement reçu après le cutoff du manifeste');
END;

CREATE TRIGGER trg_manifest_replacements_scope
BEFORE INSERT ON manifest_replacements
WHEN NOT EXISTS (
        SELECT 1 FROM manifest_events
        WHERE manifest_id = NEW.manifest_id
          AND event_id = (SELECT old_event_id FROM event_replacements WHERE replacement_id = NEW.replacement_id)
    )
 OR NOT EXISTS (
        SELECT 1 FROM manifest_events
        WHERE manifest_id = NEW.manifest_id
          AND event_id = (SELECT new_event_id FROM event_replacements WHERE replacement_id = NEW.replacement_id)
    )
 OR (SELECT visible_from_received_timestamp FROM event_replacements WHERE replacement_id = NEW.replacement_id)
     > (SELECT cutoff_received_timestamp FROM data_manifests WHERE manifest_id = NEW.manifest_id)
BEGIN
    SELECT RAISE(ABORT, 'remplacement hors du manifeste ou après son cutoff');
END;

CREATE TRIGGER trg_manifest_seals_no_update
BEFORE UPDATE ON manifest_seals
BEGIN
    SELECT RAISE(ABORT, 'manifest_seals est append-only');
END;

CREATE TRIGGER trg_manifest_seals_no_delete
BEFORE DELETE ON manifest_seals
BEGIN
    SELECT RAISE(ABORT, 'manifest_seals est append-only');
END;

CREATE TRIGGER trg_manifest_seals_no_conflicting_insert
BEFORE INSERT ON manifest_seals
WHEN EXISTS (SELECT 1 FROM manifest_seals WHERE manifest_id = NEW.manifest_id)
BEGIN
    SELECT RAISE(ABORT, 'INSERT OR REPLACE interdit sur manifest_seals');
END;

CREATE TRIGGER trg_manifest_seals_valid
BEFORE INSERT ON manifest_seals
WHEN (SELECT hash_version FROM data_manifests WHERE manifest_id = NEW.manifest_id)
     IS NOT 'manifest/v2'
 OR NEW.manifest_hash IS NOT (SELECT sha256 FROM data_manifests WHERE manifest_id = NEW.manifest_id)
 OR NEW.event_count IS NOT (SELECT COUNT(*) FROM manifest_events WHERE manifest_id = NEW.manifest_id)
 OR NEW.replacement_count IS NOT (SELECT COUNT(*) FROM manifest_replacements WHERE manifest_id = NEW.manifest_id)
 OR EXISTS (
     SELECT 1
     FROM manifest_events me
     JOIN market_events e ON e.event_id = me.event_id
     WHERE me.manifest_id = NEW.manifest_id
       AND EXISTS (SELECT 1 FROM event_replacements r WHERE r.new_event_id = me.event_id)
       AND NOT EXISTS (
           SELECT 1 FROM manifest_replacements mr
           JOIN event_replacements r ON r.replacement_id = mr.replacement_id
           WHERE mr.manifest_id = NEW.manifest_id
             AND r.new_event_id = me.event_id
       )
 )
BEGIN
    SELECT RAISE(ABORT, 'seal invalide : hash, comptage ou remplacement manquant');
END;

-- ----------------------------------------------------------------------------
-- 8. Triggers experiments : immuabilité et provenance
-- ----------------------------------------------------------------------------
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

-- ----------------------------------------------------------------------------
-- 9. Vues
-- ----------------------------------------------------------------------------
CREATE VIEW v_current_market_events AS
SELECT e.*
FROM market_events e
WHERE NOT EXISTS (
    SELECT 1 FROM event_replacements r WHERE r.old_event_id = e.event_id
);

-- Aucun manifeste n'est lisible par cette vue sans seal valide.
CREATE VIEW v_manifest_event_visibility AS
SELECT
    me.manifest_id,
    me.event_id,
    e.received_timestamp,
    CASE WHEN mro.replacement_id IS NOT NULL
         THEN ro.visible_from_received_timestamp END AS old_visible_from,
    CASE WHEN mrn.replacement_id IS NOT NULL
         THEN rn.visible_from_received_timestamp END AS new_visible_from
FROM manifest_events me
JOIN manifest_seals ms ON ms.manifest_id = me.manifest_id
JOIN market_events e ON e.event_id = me.event_id
LEFT JOIN event_replacements ro ON ro.old_event_id = me.event_id
LEFT JOIN manifest_replacements mro
       ON mro.manifest_id = me.manifest_id AND mro.replacement_id = ro.replacement_id
LEFT JOIN event_replacements rn ON rn.new_event_id = me.event_id
LEFT JOIN manifest_replacements mrn
       ON mrn.manifest_id = me.manifest_id AND mrn.replacement_id = rn.replacement_id;

-- ----------------------------------------------------------------------------
-- 10. Version et journal
-- ----------------------------------------------------------------------------
PRAGMA user_version = 5;
INSERT INTO schema_migrations(version, name, applied_at)
VALUES (
    5,
    '0005_p0_foundations',
    strftime('%Y-%m-%dT%H:%M:%f', 'now') || '000Z'
);

COMMIT;
PRAGMA foreign_keys = ON;
