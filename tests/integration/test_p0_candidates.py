"""Tests des candidats P0 : 0005, 0006 et invariants C-01/C-02/C-03.

Aucun test ne s'exécute sur la base de travail : toutes les connexions sont
en mémoire ou dans ``tmp_path``. Les migrations candidates restent non gelées.
"""

from __future__ import annotations

import hashlib
import importlib.util
import inspect
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pytest

from labtest import sqlfixtures as fx
from labtest.contracts import SQL_SCHEMA_PATH
from polymarket_lab.storage.clock import (
    FixedClock,
    replacement_timestamps,
)
from polymarket_lab.storage.replacements import record_replacement

MIGRATIONS = SQL_SCHEMA_PATH.parent / "migrations"
MIGRATION_0004 = MIGRATIONS / "0004_consolidation.sql"
MIGRATION_0005 = MIGRATIONS / "0005_p0_foundations.sql"
MIGRATION_0006 = MIGRATIONS / "0006_p0_ledger.sql"
RUNNER_PATH = MIGRATIONS / "run_migration.py"
BASELINE_SQL = SQL_SCHEMA_PATH.read_text(encoding="utf-8")

TS_3S = "2026-10-01T12:00:03.000000Z"
TS_4S = "2026-10-01T12:00:04.000000Z"


def load_runner():
    spec = importlib.util.spec_from_file_location("run_migration_p0", RUNNER_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def baseline_connection() -> sqlite3.Connection:
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.isolation_level = None
    connection.executescript(BASELINE_SQL)
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA recursive_triggers = ON")
    return connection


def apply(connection: sqlite3.Connection, *paths: Path) -> None:
    for path in paths:
        connection.executescript(path.read_text(encoding="utf-8"))


def schema_05(*, seed: bool = False, with_market: bool = True) -> sqlite3.Connection:
    connection = baseline_connection()
    apply(connection, MIGRATION_0004, MIGRATION_0005)
    if seed:
        fx.seed_basic(connection)
        connection.commit()
    if with_market:
        fx.insert_market(connection, "mkt_demo")
        fx.insert_token(connection, "tok_demo", "mkt_demo", "Yes", 0)
    return connection


def schema_06(*, seed: bool = False) -> sqlite3.Connection:
    connection = baseline_connection()
    apply(connection, MIGRATION_0004, MIGRATION_0005, MIGRATION_0006)
    if seed:
        fx.seed_basic(connection)
        connection.commit()
    return connection


def insert_v2_event(
    connection: sqlite3.Connection,
    event_id: str,
    event_type: str,
    *,
    source_event_id: str | None = "src-v2",
    raw_payload_sha256: str | None = None,
    market_id: str | None = "mkt_demo",
    token_id: str | None = "tok_demo",
    source_timestamp: str = fx.TS0,
    received_timestamp: str = fx.TS0,
    normalizer_version: str | None = "1.2.0",
    event_identity_version: str = "v2",
) -> str:
    connection.execute(
        """
        INSERT INTO market_events(
            event_id, schema_version, normalizer_version, event_identity_version,
            event_type, source, source_event_id, source_schema_version,
            source_timestamp, received_timestamp, received_monotonic_ns,
            ingested_at, market_id, token_id, accounting_unit, sequence_number,
            quality_flags_json, raw_payload_ref, raw_payload_sha256
        ) VALUES (?, '1.2.0', ?, ?, ?, 'fixture', ?, 'fixture-v2', ?, ?, NULL,
                  ?, ?, ?, ?, NULL, '["fixture"]', ?, ?)
        """,
        (
            event_id, normalizer_version, event_identity_version, event_type,
            source_event_id, source_timestamp, received_timestamp,
            received_timestamp, market_id, token_id, "pUSD",
            None if raw_payload_sha256 is None else f"fixture://{event_id}",
            raw_payload_sha256,
        ),
    )
    return event_id


def insert_replacement(
    connection: sqlite3.Connection,
    replacement_id: str,
    old_event_id: str,
    new_event_id: str,
    *,
    created_at: str,
    visible_from: str,
    normalizer_version: str = "1.1.0",
) -> None:
    connection.execute(
        """
        INSERT INTO event_replacements(
            replacement_id, old_event_id, new_event_id, reason,
            normalizer_version, created_at, visible_from_received_timestamp
        ) VALUES (?, ?, ?, 'reparse', ?, ?, ?)
        """,
        (
            replacement_id, old_event_id, new_event_id, normalizer_version,
            created_at, visible_from,
        ),
    )


# ---------------------------------------------------------------------------
# 0005 — fondations
# ---------------------------------------------------------------------------


def test_0005_applies_to_04_and_preserves_legacy_rows() -> None:
    connection = baseline_connection()
    apply(connection, MIGRATION_0004)
    ids = fx.seed_basic(connection)
    before = {
        table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        for table in (
            "market_events", "event_replacements", "experiments",
            "data_manifests", "simulated_orders", "simulated_fills",
            "fee_schedules", "hypotheses", "strategies",
        )
    }
    apply(connection, MIGRATION_0005)
    assert connection.execute("PRAGMA user_version").fetchone()[0] == 5
    assert [
        row[0] for row in connection.execute(
            "SELECT version FROM schema_migrations ORDER BY version"
        )
    ] == [4, 5]
    assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
    after = {
        table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        for table in before
    }
    assert after == before
    assert connection.execute(
        "SELECT event_identity_version FROM market_events WHERE event_id = ?",
        (ids["trade_event"],),
    ).fetchone()[0] == "v1"
    # Aucun manifeste legacy n'est recalculé ni scellé.
    row = connection.execute(
        "SELECT hash_version, event_id_algorithm FROM data_manifests LIMIT 1"
    ).fetchone()
    assert tuple(row) == ("legacy/v1", "event-id/v1")
    assert connection.execute(
        "SELECT config_hash_version FROM experiments WHERE experiment_id = ?",
        (ids["experiment_id"],),
    ).fetchone()[0] == "legacy/v1"
    indexes = {
        row[0] for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'index'"
        )
    }
    assert "idx_event_replacements_new" in indexes
    # Le trigger append-only a été restauré après le backfill.
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            "UPDATE market_events SET event_identity_version = 'v2' WHERE event_id = ?",
            (ids["trade_event"],),
        )
    connection.close()


def test_0005_backfills_v1_only_for_known_schema_versions() -> None:
    connection = baseline_connection()
    apply(connection, MIGRATION_0004)
    fx.insert_market(connection, "mkt_demo")
    fx.insert_token(connection, "tok_demo", "mkt_demo", "Yes", 0)
    # L'append-only interdit de rétrograder une ligne 1.1.0 : on insère
    # directement une ligne de version inconnue, sans normalizer_version.
    connection.execute(
        """
        INSERT INTO market_events(
            event_id, schema_version, event_type, source, source_event_id,
            source_schema_version, source_timestamp, received_timestamp,
            ingested_at, market_id, token_id, accounting_unit, quality_flags_json
        ) VALUES ('evt_unknown_schema', '0.9.0', 'trade', 'fixture', 'legacy-unknown',
                  'fixture-v0', ?, ?, ?, 'mkt_demo', 'tok_demo', 'pUSD', '["fixture"]')
        """,
        (fx.TS0, fx.TS0, fx.TS0),
    )
    apply(connection, MIGRATION_0005)
    assert connection.execute(
        "SELECT event_identity_version FROM market_events "
        "WHERE event_id = 'evt_unknown_schema'"
    ).fetchone()[0] is None
    connection.close()


def test_0005_preserves_valid_legacy_replacement_visibility() -> None:
    connection = baseline_connection()
    apply(connection, MIGRATION_0004)
    ids = fx.seed_basic(connection)
    new_event = fx.insert_envelope(
        connection, "evt_trade_reparse", "trade", market_id=ids["market_id"],
        token_id=ids["token_yes"], accounting_unit="pUSD",
        received_timestamp=fx.TS2,
    )
    connection.execute(
        "INSERT INTO event_replacements(replacement_id, old_event_id, new_event_id, "
        "reason, normalizer_version, created_at) VALUES "
        "('repl_legacy_ok', ?, ?, 'reparse', '1.1.0', ?)",
        (ids["trade_event"], new_event, fx.TS2),
    )
    before = {
        table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        for table in ("event_replacements", "market_events",
                      "data_manifests", "experiments")
    }
    apply(connection, MIGRATION_0005)
    after = {
        table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        for table in before
    }
    assert after == before
    row = connection.execute(
        "SELECT created_at, visible_from_received_timestamp "
        "FROM event_replacements WHERE replacement_id = 'repl_legacy_ok'"
    ).fetchone()
    assert tuple(row) == (fx.TS2, fx.TS2)
    connection.close()


def test_0005_rejects_legacy_terminal_status_without_completed_at() -> None:
    connection = baseline_connection()
    apply(connection, MIGRATION_0004)
    ids = fx.seed_basic(connection)
    fx.insert_experiment(
        connection, ids["strategy_id"], ids["strategy_version"],
        experiment_id="exp_completed_bad", status="completed",
        config_hash=fx.SHA256_CONFIG,
    )
    with pytest.raises(sqlite3.IntegrityError):
        apply(connection, MIGRATION_0005)
    assert connection.execute("PRAGMA user_version").fetchone()[0] == 4
    connection.close()


def test_0005_rejects_legacy_replacement_created_before_events() -> None:
    connection = baseline_connection()
    apply(connection, MIGRATION_0004)
    fx.insert_market(connection, "mkt_demo")
    fx.insert_token(connection, "tok_demo", "mkt_demo", "Yes", 0)
    old = fx.insert_envelope(connection, "evt_old", "trade", market_id="mkt_demo",
                             token_id="tok_demo", accounting_unit="pUSD",
                             received_timestamp=fx.TS1)
    new = fx.insert_envelope(connection, "evt_new", "trade", market_id="mkt_demo",
                             token_id="tok_demo", accounting_unit="pUSD",
                             received_timestamp=fx.TS1)
    connection.execute(
        "INSERT INTO event_replacements(replacement_id, old_event_id, new_event_id, "
        "reason, normalizer_version, created_at) VALUES "
        "('repl_bad', ?, ?, 'reparse', '1.1.0', ?)",
        (old, new, fx.TS0),
    )
    with pytest.raises(sqlite3.IntegrityError):
        apply(connection, MIGRATION_0005)
    assert connection.execute("PRAGMA user_version").fetchone()[0] == 4
    connection.close()


def test_0005_rejects_bad_market_token_shape() -> None:
    connection = schema_05()
    with pytest.raises(sqlite3.IntegrityError):
        insert_v2_event(
            connection, "evt_bad_shape", "connection_status",
            market_id="mkt_demo", token_id="tok_demo",
        )
    with pytest.raises(sqlite3.IntegrityError):
        insert_v2_event(
            connection, "evt_bad_trade", "trade", market_id="mkt_demo",
            token_id=None,
        )
    connection.close()


# ---------------------------------------------------------------------------
# B-01 — identité v2 et index
# ---------------------------------------------------------------------------


def test_v2_source_identity_is_unique_per_type_and_normalizer() -> None:
    connection = schema_05()
    insert_v2_event(connection, "evt_a", "trade", source_event_id="native-1")
    with pytest.raises(sqlite3.IntegrityError):
        insert_v2_event(connection, "evt_b_dup", "trade", source_event_id="native-1")
    insert_v2_event(connection, "evt_c_other_type", "book_snapshot",
                    source_event_id="native-1")
    insert_v2_event(connection, "evt_d_other_norm", "trade",
                    source_event_id="native-1", normalizer_version="1.3.0")
    connection.close()


def test_v2_requires_source_anchor_and_identity_version() -> None:
    connection = schema_05()
    with pytest.raises(sqlite3.IntegrityError):
        insert_v2_event(connection, "evt_no_anchor", "trade", source_event_id=None)
    with pytest.raises(sqlite3.IntegrityError):
        insert_v2_event(connection, "evt_v1_identity", "trade",
                        event_identity_version="v1")
    connection.close()


def test_v2_raw_fallback_is_indexed() -> None:
    connection = schema_05()
    raw = "a" * 64
    insert_v2_event(connection, "evt_raw_a", "trade", source_event_id=None,
                    raw_payload_sha256=raw, market_id="mkt_demo",
                    token_id="tok_demo", source_timestamp=fx.TS1)
    with pytest.raises(sqlite3.IntegrityError):
        insert_v2_event(connection, "evt_raw_b", "trade", source_event_id=None,
                        raw_payload_sha256=raw, market_id="mkt_demo",
                        token_id="tok_demo", source_timestamp=fx.TS1)
    connection.close()


# ---------------------------------------------------------------------------
# C-01 — monotonie et cycles
# ---------------------------------------------------------------------------


def _replacement_events(connection: sqlite3.Connection) -> tuple[str, str, str]:
    old = fx.insert_envelope(connection, "evt_old", "trade", market_id="mkt_demo",
                             token_id="tok_demo", accounting_unit="pUSD",
                             received_timestamp=fx.TS0)
    middle = fx.insert_envelope(connection, "evt_mid", "trade", market_id="mkt_demo",
                                token_id="tok_demo", accounting_unit="pUSD",
                                received_timestamp=fx.TS1)
    new = fx.insert_envelope(connection, "evt_new", "trade", market_id="mkt_demo",
                             token_id="tok_demo", accounting_unit="pUSD",
                             received_timestamp=fx.TS1)
    return old, middle, new


def test_replacement_scope_rejects_different_source() -> None:
    connection = schema_05()
    old, _middle, _new = _replacement_events(connection)
    other = fx.insert_envelope(
        connection, "evt_scope_source", "trade", source="gamma_api",
        market_id="mkt_demo", token_id="tok_demo", accounting_unit="pUSD",
        received_timestamp=fx.TS1,
    )
    with pytest.raises(sqlite3.IntegrityError, match="même source"):
        insert_replacement(connection, "repl_scope_source", old, other,
                           created_at=fx.TS2, visible_from=fx.TS2)
    connection.close()


def test_replacement_scope_rejects_different_event_type() -> None:
    connection = schema_05()
    old, _middle, _new = _replacement_events(connection)
    other = fx.insert_envelope(
        connection, "evt_scope_type", "book_snapshot",
        market_id="mkt_demo", token_id="tok_demo",
        received_timestamp=fx.TS1,
    )
    with pytest.raises(sqlite3.IntegrityError, match="même source"):
        insert_replacement(connection, "repl_scope_type", old, other,
                           created_at=fx.TS2, visible_from=fx.TS2)
    connection.close()


def test_replacement_scope_rejects_different_market_or_token() -> None:
    connection = schema_05()
    old, _middle, _new = _replacement_events(connection)
    fx.insert_market(connection, "mkt_scope_other")
    fx.insert_token(connection, "tok_scope_other", "mkt_scope_other", "Yes", 0)
    other = fx.insert_envelope(
        connection, "evt_scope_market", "trade",
        market_id="mkt_scope_other", token_id="tok_scope_other",
        accounting_unit="pUSD", received_timestamp=fx.TS1,
    )
    with pytest.raises(sqlite3.IntegrityError, match="même source"):
        insert_replacement(connection, "repl_scope_market", old, other,
                           created_at=fx.TS2, visible_from=fx.TS2)
    connection.close()


def test_replacement_scope_rejects_different_token_same_market() -> None:
    connection = schema_05()
    old, _middle, _new = _replacement_events(connection)
    fx.insert_token(connection, "tok_scope_same_market", "mkt_demo", "No", 1)
    other = fx.insert_envelope(
        connection, "evt_scope_token", "trade", market_id="mkt_demo",
        token_id="tok_scope_same_market", accounting_unit="pUSD",
        received_timestamp=fx.TS1,
    )
    with pytest.raises(sqlite3.IntegrityError, match="même source"):
        insert_replacement(connection, "repl_scope_token", old, other,
                           created_at=fx.TS2, visible_from=fx.TS2)
    connection.close()


def test_replacement_normalizer_must_match_new_event() -> None:
    connection = schema_05()
    old, middle, _new = _replacement_events(connection)
    with pytest.raises(sqlite3.IntegrityError, match="normalizer_version"):
        insert_replacement(connection, "repl_scope_norm", old, middle,
                           created_at=fx.TS2, visible_from=fx.TS2,
                           normalizer_version="1.3.0")
    connection.close()


def test_replacement_scope_accepts_same_source_type_market_token() -> None:
    connection = schema_05()
    old, middle, _new = _replacement_events(connection)
    insert_replacement(connection, "repl_scope_ok", old, middle,
                       created_at=fx.TS2, visible_from=fx.TS2)
    assert connection.execute(
        "SELECT COUNT(*) FROM event_replacements WHERE replacement_id = 'repl_scope_ok'"
    ).fetchone()[0] == 1
    connection.close()


def test_replacement_chain_must_be_monotone() -> None:
    connection = schema_05()
    old, middle, new = _replacement_events(connection)
    insert_replacement(connection, "repl_1", old, middle,
                       created_at=TS_3S, visible_from=TS_3S)
    with pytest.raises(sqlite3.IntegrityError, match="monotone"):
        insert_replacement(connection, "repl_2", middle, new,
                           created_at=fx.TS2,
                           visible_from=fx.TS2)
    connection.close()


def test_monotone_chain_is_accepted() -> None:
    connection = schema_05()
    old, middle, new = _replacement_events(connection)
    insert_replacement(connection, "repl_1", old, middle,
                       created_at=fx.TS2, visible_from=fx.TS2)
    insert_replacement(connection, "repl_2", middle, new,
                       created_at=TS_3S, visible_from=TS_3S)
    ids = [row[0] for row in connection.execute(
        "SELECT event_id FROM v_current_market_events ORDER BY event_id"
    )]
    assert ids == ["evt_new"]
    connection.close()


def test_replacement_cycle_is_rejected() -> None:
    connection = schema_05()
    old, middle, new = _replacement_events(connection)
    insert_replacement(connection, "repl_1", old, middle,
                       created_at=fx.TS2, visible_from=fx.TS2)
    insert_replacement(connection, "repl_2", middle, new,
                       created_at=TS_3S, visible_from=TS_3S)
    with pytest.raises(sqlite3.IntegrityError):
        insert_replacement(connection, "repl_3", new, old,
                           created_at=TS_4S, visible_from=TS_4S)
    connection.close()


def test_replacement_visible_from_must_equal_generated_max() -> None:
    connection = schema_05()
    old, middle, _new = _replacement_events(connection)
    with pytest.raises(sqlite3.IntegrityError):
        insert_replacement(connection, "repl_bad_visible", old, middle,
                           created_at=fx.TS2, visible_from=TS_3S)
    connection.close()


def test_replacement_insert_or_replace_cannot_bypass_append_only() -> None:
    connection = schema_05()
    old, middle, _new = _replacement_events(connection)
    insert_replacement(connection, "repl_1", old, middle,
                       created_at=fx.TS2, visible_from=fx.TS2)
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            """
            INSERT OR REPLACE INTO event_replacements(
                replacement_id, old_event_id, new_event_id, reason,
                normalizer_version, created_at, visible_from_received_timestamp
            ) VALUES ('repl_1', ?, ?, 'other', '1.1.0', ?, ?)
            """,
            (old, middle, TS_3S, TS_3S),
        )
    connection.close()


def test_replacement_insert_or_replace_refused_even_with_recursive_triggers_off() -> None:
    connection = schema_05()
    old, middle, _new = _replacement_events(connection)
    insert_replacement(connection, "repl_1", old, middle,
                       created_at=fx.TS2, visible_from=fx.TS2)
    connection.execute("PRAGMA recursive_triggers = OFF")
    with pytest.raises(sqlite3.IntegrityError, match="INSERT OR REPLACE"):
        connection.execute(
            """
            INSERT OR REPLACE INTO event_replacements(
                replacement_id, old_event_id, new_event_id, reason,
                normalizer_version, created_at, visible_from_received_timestamp
            ) VALUES ('repl_1', ?, ?, 'other', '1.1.0', ?, ?)
            """,
            (old, middle, TS_3S, TS_3S),
        )
    connection.close()


def test_replacement_visibility_cannot_be_updated_directly() -> None:
    connection = schema_05()
    old, middle, _new = _replacement_events(connection)
    insert_replacement(connection, "repl_1", old, middle,
                       created_at=fx.TS2, visible_from=fx.TS2)
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            "UPDATE event_replacements SET visible_from_received_timestamp = ? "
            "WHERE replacement_id = 'repl_1'",
            (TS_3S,),
        )
    connection.close()


# ---------------------------------------------------------------------------
# C-02 — horloge et visibilité
# ---------------------------------------------------------------------------


def test_replacement_timestamps_use_injected_clock() -> None:
    clock = FixedClock(datetime(2026, 10, 1, 12, 0, 2, tzinfo=timezone.utc))
    created, visible = replacement_timestamps(fx.TS0, fx.TS1, clock)
    assert created == "2026-10-01T12:00:02.000000Z"
    assert visible == "2026-10-01T12:00:02.000000Z"


def test_replacement_timestamps_reject_naive_clock() -> None:
    with pytest.raises(ValueError):
        FixedClock(datetime(2026, 10, 1, 12, 0, 2))


def test_replacement_api_does_not_accept_visible_from() -> None:
    parameters = inspect.signature(replacement_timestamps).parameters
    assert list(parameters) == [
        "old_received_timestamp",
        "new_received_timestamp",
        "clock",
    ]


def test_storage_api_generates_timestamps_without_accepting_them() -> None:
    connection = schema_05()
    old, middle, _new = _replacement_events(connection)
    clock = FixedClock(datetime(2026, 10, 1, 12, 0, 2, tzinfo=timezone.utc))
    created, visible = record_replacement(
        connection,
        replacement_id="repl_api",
        old_event_id=old,
        new_event_id=middle,
        reason="reparse",
        normalizer_version="1.1.0",
        evidence_ref=None,
        clock=clock,
    )
    assert (created, visible) == (
        "2026-10-01T12:00:02.000000Z",
        "2026-10-01T12:00:02.000000Z",
    )
    row = connection.execute(
        "SELECT created_at, visible_from_received_timestamp "
        "FROM event_replacements WHERE replacement_id = 'repl_api'"
    ).fetchone()
    assert tuple(row) == (created, visible)
    parameters = inspect.signature(record_replacement).parameters
    assert "created_at" not in parameters
    assert "visible_from" not in parameters
    connection.close()


def test_storage_api_rejects_missing_event() -> None:
    connection = schema_05()
    clock = FixedClock(datetime(2026, 10, 1, 12, 0, 2, tzinfo=timezone.utc))
    with pytest.raises(ValueError):
        record_replacement(
            connection,
            replacement_id="repl_missing",
            old_event_id="evt_missing_old",
            new_event_id="evt_missing_new",
            reason="reparse",
            normalizer_version="1.1.0",
            evidence_ref=None,
            clock=clock,
        )
    connection.close()


def test_direct_insert_cannot_backdate_created_at_before_events() -> None:
    connection = schema_05()
    old, middle, _new = _replacement_events(connection)
    with pytest.raises(sqlite3.IntegrityError, match="précéder"):
        insert_replacement(connection, "repl_bad", old, middle,
                           created_at=fx.TS0, visible_from=fx.TS1)
    insert_replacement(connection, "repl_ok", old, middle,
                       created_at=fx.TS1, visible_from=fx.TS1)
    connection.close()


# ---------------------------------------------------------------------------
# C-03 — scellement obligatoire
# ---------------------------------------------------------------------------


def _manifest_with_event(connection: sqlite3.Connection) -> tuple[str, str]:
    manifest_id = fx.insert_manifest(connection, "manifest_p0")
    event_id = fx.insert_envelope(
        connection, "evt_manifest", "trade", market_id="mkt_demo",
        token_id="tok_demo", accounting_unit="pUSD",
    )
    connection.execute(
        "INSERT INTO manifest_events(manifest_id, event_id, ordinal) VALUES (?, ?, 0)",
        (manifest_id, event_id),
    )
    return manifest_id, event_id


def test_unsealed_manifest_is_not_visible() -> None:
    connection = schema_05()
    manifest_id, _event_id = _manifest_with_event(connection)
    assert connection.execute(
        "SELECT COUNT(*) FROM v_manifest_event_visibility WHERE manifest_id = ?",
        (manifest_id,),
    ).fetchone()[0] == 0
    connection.close()


def test_valid_seal_makes_manifest_visible_and_freezes_lists() -> None:
    connection = schema_05()
    manifest_id, event_id = _manifest_with_event(connection)
    connection.execute(
        "INSERT INTO manifest_seals(manifest_id, sealed_at, manifest_hash, "
        "event_count, replacement_count) VALUES (?, ?, ?, 1, 0)",
        (manifest_id, fx.TS3, fx.SHA256_ZERO),
    )
    assert connection.execute(
        "SELECT COUNT(*) FROM v_manifest_event_visibility WHERE manifest_id = ?",
        (manifest_id,),
    ).fetchone()[0] == 1

    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            "INSERT INTO manifest_events(manifest_id, event_id, ordinal) "
            "VALUES (?, 'evt_other', 1)",
            (manifest_id,),
        )
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            "DELETE FROM manifest_events WHERE manifest_id = ? AND event_id = ?",
            (manifest_id, event_id),
        )
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            "UPDATE manifest_seals SET manifest_hash = ? WHERE manifest_id = ?",
            ("f" * 64, manifest_id),
        )
    connection.close()


def test_manifest_lists_refuse_replace_with_recursive_triggers_off() -> None:
    connection = schema_05()
    manifest_id, event_id = _manifest_with_event(connection)
    connection.execute("PRAGMA recursive_triggers = OFF")
    with pytest.raises(sqlite3.IntegrityError, match="INSERT OR REPLACE"):
        connection.execute(
            "INSERT OR REPLACE INTO manifest_events(manifest_id, event_id, ordinal) "
            "VALUES (?, ?, 0)",
            (manifest_id, event_id),
        )
    with pytest.raises(sqlite3.IntegrityError, match="INSERT OR REPLACE"):
        connection.execute(
            "INSERT OR REPLACE INTO data_manifests(manifest_id, created_at, "
            "cutoff_received_timestamp, filters_json, first_source_timestamp, "
            "last_source_timestamp, event_count, sha256, notes, source_class, "
            "hash_version, event_id_algorithm) "
            "VALUES (?, ?, ?, '{}', ?, ?, 0, ?, 'x', 'fixture', "
            "'manifest/v2', 'event-id/v2')",
            (manifest_id, fx.TS0, fx.TS3, fx.TS0, fx.TS2, "f" * 64),
        )
    connection.close()


def test_seal_hash_must_match_manifest_hash() -> None:
    connection = schema_05()
    manifest_id, _event_id = _manifest_with_event(connection)
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            "INSERT INTO manifest_seals(manifest_id, sealed_at, manifest_hash, "
            "event_count, replacement_count) VALUES (?, ?, ?, 1, 0)",
            (manifest_id, fx.TS3, "f" * 64),
        )
    connection.close()


def test_seal_counts_must_match_lists() -> None:
    connection = schema_05()
    manifest_id, _event_id = _manifest_with_event(connection)
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            "INSERT INTO manifest_seals(manifest_id, sealed_at, manifest_hash, "
            "event_count, replacement_count) VALUES (?, ?, ?, 2, 0)",
            (manifest_id, fx.TS3, fx.SHA256_ZERO),
        )
    connection.close()


def test_seal_requires_replacement_set_for_new_event() -> None:
    connection = schema_05()
    manifest_id, event_id = _manifest_with_event(connection)
    old = fx.insert_envelope(connection, "evt_old_manifest", "trade",
                             market_id="mkt_demo", token_id="tok_demo",
                             accounting_unit="pUSD")
    connection.execute(
        "INSERT INTO event_replacements(replacement_id, old_event_id, new_event_id, "
        "reason, normalizer_version, created_at, visible_from_received_timestamp) "
        "VALUES ('repl_manifest', ?, ?, 'reparse', '1.1.0', ?, ?)",
        (old, event_id, fx.TS1, fx.TS1),
    )
    connection.execute(
        "INSERT INTO manifest_events(manifest_id, event_id, ordinal) VALUES (?, ?, 1)",
        (manifest_id, old),
    )
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            "INSERT INTO manifest_seals(manifest_id, sealed_at, manifest_hash, "
            "event_count, replacement_count) VALUES (?, ?, ?, 2, 0)",
            (manifest_id, fx.TS3, fx.SHA256_ZERO),
        )
    connection.close()


# ---------------------------------------------------------------------------
# 0006 — ledger et conversions
# ---------------------------------------------------------------------------


def _second_experiment(connection: sqlite3.Connection, ids: dict) -> str:
    return fx.insert_experiment(
        connection, ids["strategy_id"], ids["strategy_version"],
        experiment_id="exp_fixture_002", config_hash=fx.SHA256_CONFIG,
    )


def test_0006_applies_and_keeps_rows() -> None:
    connection = baseline_connection()
    apply(connection, MIGRATION_0004, MIGRATION_0005)
    ids = fx.seed_basic(connection)
    connection.execute(
        "INSERT INTO ledger_transactions(transaction_id, experiment_id, occurred_at, "
        "kind, ref_type, ref_id, idempotency_key, memo, created_at) "
        "VALUES ('tx_before', ?, ?, 'adjustment', 'manual', 'm1', 'idem-before', '', ?)",
        (ids["experiment_id"], fx.TS1, fx.TS1),
    )
    connection.execute(
        "INSERT INTO ledger_transactions(transaction_id, experiment_id, occurred_at, "
        "kind, ref_type, ref_id, idempotency_key, memo, created_at) "
        "VALUES ('tx_settle_before', ?, ?, 'settlement', 'market_resolution', "
        "'evt_resolution_001', 'idem-settle-before', '', ?)",
        (ids["experiment_id"], fx.TS2, fx.TS2),
    )
    connection.execute(
        """
        INSERT INTO settlement_conversions(
            conversion_id, resolution_event_id, source_asset, source_amount_micros,
            target_unit, target_amount_micros, conversion_rule_ref, rate_micros,
            conversion_timestamp, created_at
        ) VALUES ('conv_before', 'evt_resolution_001', 'pUSD', 1000000,
                  'USDC', 1000000, 'fixture-rule', NULL, ?, ?)
        """,
        (fx.TS2, fx.TS2),
    )
    apply(connection, MIGRATION_0006)
    assert connection.execute("PRAGMA user_version").fetchone()[0] == 6
    assert connection.execute(
        "SELECT COUNT(*) FROM ledger_transactions WHERE transaction_id = 'tx_before'"
    ).fetchone()[0] == 1
    assert connection.execute(
        "SELECT experiment_id FROM settlement_conversions WHERE conversion_id = 'conv_before'"
    ).fetchone()[0] == ids["experiment_id"]
    assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
    connection.close()


def test_ledger_uniqueness_is_scoped_per_experiment() -> None:
    connection = schema_06(seed=True)
    ids = {
        "strategy_id": "strat_fixture_001",
        "strategy_version": "0.1.0",
    }
    second = _second_experiment(connection, ids)
    fx.insert_ledger_transaction(
        connection, "tx_a", fx.deposit_postings(), experiment_id="exp_fixture_001",
        kind="adjustment", ref_type="manual", ref_id="same-ref",
        idempotency_key="same-idem",
    )
    fx.insert_ledger_transaction(
        connection, "tx_b", fx.deposit_postings(), experiment_id=second,
        kind="adjustment", ref_type="manual", ref_id="same-ref",
        idempotency_key="same-idem",
    )
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            "UPDATE ledger_transactions SET memo = 'changed' "
            "WHERE transaction_id = 'tx_a'"
        )
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            "DELETE FROM ledger_transactions WHERE transaction_id = 'tx_a'"
        )
    connection.execute("PRAGMA recursive_triggers = OFF")
    with pytest.raises(sqlite3.IntegrityError, match="INSERT OR REPLACE"):
        connection.execute(
            "INSERT OR REPLACE INTO ledger_transactions(transaction_id, "
            "experiment_id, occurred_at, kind, ref_type, ref_id, "
            "idempotency_key, memo, created_at) VALUES ('tx_a', "
            "'exp_fixture_001', ?, 'adjustment', 'manual', 'same-ref', "
            "'same-idem', '', ?)",
            (fx.TS1, fx.TS1),
        )
    connection.execute("PRAGMA recursive_triggers = ON")
    with pytest.raises(sqlite3.IntegrityError):
        fx.insert_ledger_transaction(
            connection, "tx_c", fx.deposit_postings(),
            experiment_id="exp_fixture_001", kind="adjustment",
            ref_type="manual", ref_id="same-ref",
            idempotency_key="other-idem",
        )
    with pytest.raises(sqlite3.IntegrityError):
        fx.insert_ledger_transaction(
            connection, "tx_d", fx.deposit_postings(),
            experiment_id="exp_fixture_001", kind="adjustment",
            ref_type="manual", ref_id="other-ref",
            idempotency_key="same-idem",
        )
    connection.close()


def test_settlement_conversion_is_scoped_and_traceable() -> None:
    connection = schema_06(seed=True)
    ids = {
        "strategy_id": "strat_fixture_001",
        "strategy_version": "0.1.0",
    }
    second = _second_experiment(connection, ids)
    third = fx.insert_experiment(
        connection, ids["strategy_id"], ids["strategy_version"],
        experiment_id="exp_fixture_003", config_hash=fx.SHA256_CONFIG,
    )
    fx.insert_ledger_transaction(
        connection, "tx_settle_a", fx.settlement_win_postings(),
        experiment_id="exp_fixture_001", kind="settlement",
        ref_type="market_resolution", ref_id="evt_resolution_001",
        idempotency_key="idem-settle-a",
    )
    fx.insert_ledger_transaction(
        connection, "tx_settle_b", fx.settlement_win_postings(),
        experiment_id=second, kind="settlement",
        ref_type="market_resolution", ref_id="evt_resolution_001",
        idempotency_key="idem-settle-b",
    )
    connection.execute(
        """
        INSERT INTO settlement_conversions(
            conversion_id, experiment_id, resolution_event_id, source_asset,
            source_amount_micros, target_unit, target_amount_micros,
            conversion_rule_ref, rate_micros, conversion_timestamp, created_at
        ) VALUES ('conv_a', 'exp_fixture_001', 'evt_resolution_001', 'pUSD',
                  1000000, 'USDC', 1000000, 'fixture-rule', NULL, ?, ?)
        """,
        (fx.TS2, fx.TS2),
    )
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            "UPDATE settlement_conversions SET target_amount_micros = 2 "
            "WHERE conversion_id = 'conv_a'"
        )
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            "DELETE FROM settlement_conversions WHERE conversion_id = 'conv_a'"
        )
    connection.execute("PRAGMA recursive_triggers = OFF")
    with pytest.raises(sqlite3.IntegrityError, match="INSERT OR REPLACE"):
        connection.execute(
            """
            INSERT OR REPLACE INTO settlement_conversions(
                conversion_id, experiment_id, resolution_event_id, source_asset,
                source_amount_micros, target_unit, target_amount_micros,
                conversion_rule_ref, rate_micros, conversion_timestamp, created_at
            ) VALUES ('conv_a', 'exp_fixture_001', 'evt_resolution_001', 'pUSD',
                      1000000, 'USDC', 1000000, 'fixture-rule', NULL, ?, ?)
            """,
            (fx.TS2, fx.TS2),
        )
    connection.execute("PRAGMA recursive_triggers = ON")
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            """
            INSERT INTO settlement_conversions(
                conversion_id, experiment_id, resolution_event_id, source_asset,
                source_amount_micros, target_unit, target_amount_micros,
                conversion_rule_ref, rate_micros, conversion_timestamp, created_at
            ) VALUES ('conv_dup', 'exp_fixture_001', 'evt_resolution_001', 'pUSD',
                      1000000, 'USDC', 1000000, 'fixture-rule', NULL, ?, ?)
            """,
            (fx.TS2, fx.TS2),
        )
    connection.execute(
        """
        INSERT INTO settlement_conversions(
            conversion_id, experiment_id, resolution_event_id, source_asset,
            source_amount_micros, target_unit, target_amount_micros,
            conversion_rule_ref, rate_micros, conversion_timestamp, created_at
        ) VALUES ('conv_b', ?, 'evt_resolution_001', 'pUSD',
                  1000000, 'USDC', 1000000, 'fixture-rule', NULL, ?, ?)
        """,
        (second, fx.TS2, fx.TS2),
    )
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            """
            INSERT INTO settlement_conversions(
                conversion_id, experiment_id, resolution_event_id, source_asset,
                source_amount_micros, target_unit, target_amount_micros,
                conversion_rule_ref, rate_micros, conversion_timestamp, created_at
            ) VALUES ('conv_no_ledger', ?, 'evt_resolution_001',
                      'other', 1, 'USDC', 1, 'fixture-rule', NULL, ?, ?)
            """,
            (third, fx.TS2, fx.TS2),
        )
    connection.close()


def _conversion_setup(connection: sqlite3.Connection) -> dict:
    ids = fx.seed_basic(connection)
    connection.execute(
        """
        INSERT INTO settlement_conversions(
            conversion_id, resolution_event_id, source_asset, source_amount_micros,
            target_unit, target_amount_micros, conversion_rule_ref, rate_micros,
            conversion_timestamp, created_at
        ) VALUES ('conv_legacy', 'evt_resolution_001', 'pUSD', 1000000,
                  'USDC', 1000000, 'fixture-rule', NULL, ?, ?)
        """,
        (fx.TS2, fx.TS2),
    )
    return ids


def test_0006_preflight_aborts_conversion_without_ledger_context() -> None:
    connection = baseline_connection()
    apply(connection, MIGRATION_0004, MIGRATION_0005)
    _conversion_setup(connection)
    with pytest.raises(sqlite3.IntegrityError):
        apply(connection, MIGRATION_0006)
    assert connection.execute("PRAGMA user_version").fetchone()[0] == 5
    connection.close()


def test_0006_settlement_in_one_experiment_ignores_adjustment_in_other() -> None:
    connection = baseline_connection()
    apply(connection, MIGRATION_0004, MIGRATION_0005)
    ids = _conversion_setup(connection)
    second = _second_experiment(connection, {
        "strategy_id": ids["strategy_id"],
        "strategy_version": ids["strategy_version"],
    })
    # Même résolution dans deux expériences, mais seule la première porte un
    # settlement ; l'ajustement de la seconde ne doit pas créer d'ambiguïté.
    for transaction_id, experiment_id, kind in (
        ("tx_a", ids["experiment_id"], "settlement"),
        ("tx_b", second, "adjustment"),
    ):
        connection.execute(
            "INSERT INTO ledger_transactions(transaction_id, experiment_id, occurred_at, "
            "kind, ref_type, ref_id, idempotency_key, memo, created_at) "
            "VALUES (?, ?, ?, ?, 'market_resolution', "
            "'evt_resolution_001', ?, '', ?)",
            (transaction_id, experiment_id, fx.TS2, kind,
             f"idem-{transaction_id}", fx.TS2),
        )
    apply(connection, MIGRATION_0006)
    assert connection.execute("PRAGMA user_version").fetchone()[0] == 6
    assert connection.execute(
        "SELECT experiment_id FROM settlement_conversions "
        "WHERE conversion_id = 'conv_legacy'"
    ).fetchone()[0] == ids["experiment_id"]
    connection.close()


def test_0006_preflight_rejects_multiple_settlement_candidates() -> None:
    """Branche défensive : un 0.5 valide interdit ce cas par son index global.

    La copie est volontairement corrompue pour exercer le préflight ; elle ne
    représente pas un schéma source valide et n'est jamais utilisée ailleurs.
    """
    connection = baseline_connection()
    apply(connection, MIGRATION_0004, MIGRATION_0005)
    ids = _conversion_setup(connection)
    second = _second_experiment(connection, {
        "strategy_id": ids["strategy_id"],
        "strategy_version": ids["strategy_version"],
    })
    connection.execute("PRAGMA foreign_keys = OFF")
    connection.execute("DROP TRIGGER IF EXISTS trg_ledger_postings_unit_insert")
    connection.execute("DROP TABLE ledger_transactions")
    connection.execute(
        """
        CREATE TABLE ledger_transactions(
            transaction_id TEXT PRIMARY KEY,
            experiment_id TEXT NOT NULL,
            occurred_at TEXT NOT NULL,
            kind TEXT NOT NULL,
            ref_type TEXT NOT NULL,
            ref_id TEXT NOT NULL,
            idempotency_key TEXT NOT NULL,
            memo TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL
        )
        """
    )
    for transaction_id, experiment_id, idem in (
        ("tx_multi_one", ids["experiment_id"], "idem-multi-one"),
        ("tx_multi_two", second, "idem-multi-two"),
    ):
        connection.execute(
            "INSERT INTO ledger_transactions(transaction_id, experiment_id, "
            "occurred_at, kind, ref_type, ref_id, idempotency_key, memo, created_at) "
            "VALUES (?, ?, ?, 'settlement', 'market_resolution', "
            "'evt_resolution_001', ?, '', ?)",
            (transaction_id, experiment_id, fx.TS2, idem, fx.TS2),
        )
    with pytest.raises(sqlite3.IntegrityError):
        apply(connection, MIGRATION_0006)
    assert connection.execute("PRAGMA user_version").fetchone()[0] == 5
    assert connection.execute(
        "SELECT COUNT(*) FROM settlement_conversions"
    ).fetchone()[0] == 1
    connection.close()


def test_0006_preflight_aborts_adjustment_only_conversion_context() -> None:
    connection = baseline_connection()
    apply(connection, MIGRATION_0004, MIGRATION_0005)
    _conversion_setup(connection)
    connection.execute(
        "INSERT INTO ledger_transactions(transaction_id, experiment_id, occurred_at, "
        "kind, ref_type, ref_id, idempotency_key, memo, created_at) "
        "VALUES ('tx_adjust_only', 'exp_fixture_001', ?, 'adjustment', "
        "'market_resolution', 'evt_resolution_001', 'idem-adjust-only', '', ?)",
        (fx.TS2, fx.TS2),
    )
    with pytest.raises(sqlite3.IntegrityError):
        apply(connection, MIGRATION_0006)
    assert connection.execute("PRAGMA user_version").fetchone()[0] == 5
    assert connection.execute(
        "SELECT COUNT(*) FROM settlement_conversions"
    ).fetchone()[0] == 1
    connection.close()


# ---------------------------------------------------------------------------
# Runner généralisé : registre, sauvegarde, restauration
# ---------------------------------------------------------------------------


def _file_database(tmp_path: Path, version: int) -> Path:
    path = tmp_path / f"lab_{version}.db"
    connection = sqlite3.connect(path)
    try:
        connection.executescript(BASELINE_SQL)
        if version >= 4:
            connection.executescript(MIGRATION_0004.read_text(encoding="utf-8"))
        if version >= 5:
            connection.executescript(MIGRATION_0005.read_text(encoding="utf-8"))
        assert connection.execute("PRAGMA user_version").fetchone()[0] == version
    finally:
        connection.close()
    return path


def _seed_v5_with_conversion(
    path: Path,
    *,
    settlement: bool = True,
    conversion: bool = True,
) -> dict:
    connection = sqlite3.connect(path)
    connection.isolation_level = None
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA recursive_triggers = ON")
    try:
        ids = fx.seed_basic(connection)
        if settlement:
            fx.insert_ledger_transaction(
                connection, "tx_settle_runner", fx.settlement_win_postings(),
                experiment_id=ids["experiment_id"], kind="settlement",
                ref_type="market_resolution", ref_id="evt_resolution_001",
                idempotency_key="idem-settle-runner",
            )
        if conversion:
            connection.execute(
                """
                INSERT INTO settlement_conversions(
                    conversion_id, resolution_event_id, source_asset,
                    source_amount_micros, target_unit, target_amount_micros,
                    conversion_rule_ref, rate_micros, conversion_timestamp,
                    created_at
                ) VALUES ('conv_runner', 'evt_resolution_001', 'pUSD',
                          1000000, 'USDC', 1000000, 'fixture-rule', NULL, ?, ?)
                """,
                (fx.TS2, fx.TS2),
            )
    finally:
        connection.close()
    return ids


def _database_counts(path: Path) -> dict[str, int]:
    connection = sqlite3.connect(path)
    try:
        return {
            table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in (
                "market_events", "event_replacements", "data_manifests",
                "experiments", "ledger_transactions", "ledger_postings",
                "settlement_conversions", "simulated_orders", "simulated_fills",
            )
        }
    finally:
        connection.close()


def test_runner_5_to_6_success_journal_backup_and_counts(tmp_path: Path) -> None:
    path = _file_database(tmp_path, 5)
    ids = _seed_v5_with_conversion(path)
    before = _database_counts(path)
    runner = load_runner()
    backup = runner.apply_migration(path)
    assert backup.exists()

    connection = sqlite3.connect(path)
    try:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 6
        assert [
            row[0] for row in connection.execute(
                "SELECT version FROM schema_migrations ORDER BY version"
            )
        ] == [4, 5, 6]
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
        assert connection.execute(
            "SELECT experiment_id FROM settlement_conversions "
            "WHERE conversion_id = 'conv_runner'"
        ).fetchone()[0] == ids["experiment_id"]
    finally:
        connection.close()
    assert _database_counts(path) == before

    backup_connection = sqlite3.connect(backup)
    try:
        assert backup_connection.execute("PRAGMA user_version").fetchone()[0] == 5
        assert [
            row[0] for row in backup_connection.execute(
                "SELECT version FROM schema_migrations ORDER BY version"
            )
        ] == [4, 5]
    finally:
        backup_connection.close()
    assert _database_counts(backup) == before


def test_runner_5_to_6_preflight_failure_restores_v5(tmp_path: Path) -> None:
    path = _file_database(tmp_path, 5)
    _seed_v5_with_conversion(path, settlement=False, conversion=True)
    before = _database_counts(path)
    runner = load_runner()
    with pytest.raises(sqlite3.IntegrityError):
        runner.apply_migration(path)

    connection = sqlite3.connect(path)
    try:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 5
        assert [
            row[0] for row in connection.execute(
                "SELECT version FROM schema_migrations ORDER BY version"
            )
        ] == [4, 5]
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        connection.close()
    assert _database_counts(path) == before
    assert list(tmp_path.glob("lab_5.db.bak.*"))


def test_runner_5_to_6_post_commit_failure_restores_v5(
    tmp_path: Path, monkeypatch
) -> None:
    path = _file_database(tmp_path, 5)
    _seed_v5_with_conversion(path)
    before = _database_counts(path)
    runner = load_runner()
    original = runner.apply_migration_on_connection

    def wrapper(connection, migration):
        original(connection, migration)
        raise RuntimeError("injected post-commit failure")

    monkeypatch.setattr(runner, "apply_migration_on_connection", wrapper)
    with pytest.raises(RuntimeError, match="injected post-commit failure"):
        runner.apply_migration(path)

    connection = sqlite3.connect(path)
    try:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 5
        assert [
            row[0] for row in connection.execute(
                "SELECT version FROM schema_migrations ORDER BY version"
            )
        ] == [4, 5]
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    finally:
        connection.close()
    assert _database_counts(path) == before
    assert list(tmp_path.glob("lab_5.db.bak.*"))


def test_runner_selects_next_migration_and_creates_backup(tmp_path: Path) -> None:
    path = _file_database(tmp_path, 4)
    runner = load_runner()
    backup = runner.apply_migration(path)
    assert backup.exists()
    connection = sqlite3.connect(path)
    try:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 5
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    finally:
        connection.close()


def test_runner_restores_backup_on_failure(tmp_path: Path) -> None:
    path = _file_database(tmp_path, 3)
    connection = sqlite3.connect(path)
    try:
        fx.insert_fee_schedule(connection, "fee_per_share_legacy",
                               fee_formula="per_share")
        connection.commit()
    finally:
        connection.close()
    runner = load_runner()
    with pytest.raises(sqlite3.IntegrityError):
        runner.apply_migration(path, MIGRATION_0004)
    connection = sqlite3.connect(path)
    try:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 3
        assert connection.execute(
            "SELECT COUNT(*) FROM fee_schedules WHERE fee_formula = 'per_share'"
        ).fetchone()[0] == 1
    finally:
        connection.close()
    assert list(tmp_path.glob("lab_3.db.bak.*"))


def test_runner_backup_names_do_not_collide(tmp_path: Path) -> None:
    path = _file_database(tmp_path, 4)
    runner = load_runner()
    first = runner._backup_database(path)
    second = runner._backup_database(path)
    assert first != second
    assert first.exists() and second.exists()


def test_runner_refuses_empty_database(tmp_path: Path) -> None:
    path = tmp_path / "empty.db"
    path.touch()
    runner = load_runner()
    with pytest.raises(runner.MigrationError):
        runner.apply_migration(path)
    assert path.stat().st_size == 0


# ---------------------------------------------------------------------------
# Vecteurs B-02 / B-03
# ---------------------------------------------------------------------------


def canonical_json(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"),
        ensure_ascii=False, allow_nan=False,
    ).encode("utf-8")


def test_canonical_json_reference_vector() -> None:
    payload = {"a": [1, True, None, "é"], "b": 2, "c": {"y": -1, "z": 0}}
    assert hashlib.sha256(canonical_json(payload)).hexdigest() == (
        "afed54d28ba8364eb6f7109022284842db2d4026f6c6360c5f09ecfdb9153238"
    )


def manifest_payload(replacements: list[list[str]]) -> dict:
    return {
        "header": {
            "hash_version": "manifest/v2",
            "canonical_json_version": "canonical-json/v1",
            "manifest_id": "manifest_demo",
            "cutoff_received_timestamp": "2026-10-01T13:00:00.000000Z",
            "filters": {
                "sources": ["fixture"],
                "market_ids": ["mkt_demo"],
                "token_ids": ["tok_demo"],
                "event_types": ["trade"],
                "notes": "",
            },
            "event_count": 1 if not replacements else 2,
            "replacement_count": len(replacements),
            "event_id_algorithm": "event-id/v2",
            "schema_versions": ["1.2.0"],
            "source_classes": ["fixture"],
        },
        "event_ids": ["evt_demo"] if not replacements
        else ["evt_new", "evt_old"],
        "replacements": replacements,
    }


def test_manifest_hash_reference_vectors() -> None:
    assert hashlib.sha256(canonical_json(manifest_payload([]))).hexdigest() == (
        "764f0762a010d9a28a870c779eb087b03d3c4bd7059128a57f62ee50014791ea"
    )
    replacement = [["evt_old", "evt_new", "2026-10-01T12:00:03.000000Z"]]
    assert hashlib.sha256(canonical_json(manifest_payload(replacement))).hexdigest() == (
        "86e11b35a6cfab533c3c2a49b118316b4b14c3156e3afa1c17bcbe77e727ad33"
    )


def test_event_id_v2_reference_vector() -> None:
    identity = [
        "polymarket-lab/event-id/v2", "fixture", "src-evt_demo", "trade",
        "mkt_demo", "tok_demo", "2026-10-01T12:00:00.000000Z", "1.2.0",
    ]
    assert "evt_" + hashlib.sha256(canonical_json(identity)).hexdigest()[:32] == (
        "evt_a68cc56ca1629dd0c60671231448eb22"
    )


def test_experiment_example_config_hash_recomputes() -> None:
    examples_dir = SQL_SCHEMA_PATH.parent.parent / "contracts" / "examples"
    document = json.loads(
        (examples_dir / "experiment.json").read_text(encoding="utf-8")
    )
    stored = document["config_hash"]
    projection = {
        key: value for key, value in document.items()
        if key not in {"config_hash", "status", "created_at", "completed_at"}
    }
    digest = hashlib.sha256(canonical_json(projection)).hexdigest()
    assert stored == "sha256:" + digest


def test_market_event_examples_use_the_v2_event_id_recipe() -> None:
    examples_dir = SQL_SCHEMA_PATH.parent.parent / "contracts" / "examples"
    for path in sorted(examples_dir.glob("market_event_*.json")):
        document = json.loads(path.read_text(encoding="utf-8"))
        anchor = document.get("source_event_id") or document.get("raw_payload_sha256")
        identity = [
            "polymarket-lab/event-id/v2",
            document["source"],
            anchor,
            document["event_type"],
            document.get("market_id"),
            document.get("token_id"),
            document["source_timestamp"],
            document["normalizer_version"],
        ]
        expected = "evt_" + hashlib.sha256(canonical_json(identity)).hexdigest()[:32]
        assert document["event_id"] == expected, path.name


def rng_v2(seed: int, intent_id: str, purpose: str, low: int, high: int) -> int:
    domain = "polymarket-lab/rng/v2"
    seed_bytes = hashlib.sha256(
        canonical_json([domain, seed, intent_id, purpose])
    ).digest()
    span = high - low + 1
    if span <= 0 or span > 2**64:
        raise ValueError("span hors de 1..2^64")
    limit = (2**64 // span) * span
    counter = 0
    while True:
        value = int.from_bytes(
            hashlib.sha256(seed_bytes + counter.to_bytes(8, "big")).digest()[:8],
            "big",
        )
        if value < limit:
            return low + value % span
        counter += 1


def test_rng_v2_reference_vector_and_bounds() -> None:
    assert rng_v2(42, "", "latency", 0, 100) == 39
    assert rng_v2(42, "", "latency", 0, 1000) == 823
    assert rng_v2(42, "", "control", 0, 100) == 53
    assert rng_v2(42, "intent_a", "latency", 0, 100) == 87
    assert rng_v2(42, "intent_b", "latency", 0, 100) == 81
    with pytest.raises(ValueError):
        rng_v2(42, "", "latency", 1, 0)
    with pytest.raises(ValueError):
        rng_v2(42, "", "latency", 0, 2**64)


def test_intent_id_reference_vector() -> None:
    digest = hashlib.sha256(canonical_json([
        "polymarket-lab/intent-id/v1", "exp_demo", "idem_demo",
    ])).hexdigest()
    assert "intent_" + digest[:32] == "intent_dee0c4e16f24817236214e90558c5cef"
