"""Migration 0.3 -> 0.4 et invariants de consolidation.

Ces tests partent volontairement du schéma 0.3 seul, insèrent des lignes
compatibles 0.3, puis appliquent la migration. Ils ne remplacent pas la suite
A5 : ils vérifient le chemin de migration et les nouvelles barrières.
"""

from __future__ import annotations

import importlib.util
import re
import sqlite3
from pathlib import Path

import pytest

from labtest import sqlfixtures as fx
from labtest.contracts import SQL_SCHEMA_PATH

MIGRATION_PATH = SQL_SCHEMA_PATH.parent / "migrations" / "0004_consolidation.sql"
RUNNER_PATH = MIGRATION_PATH.with_name("run_migration.py")
BASELINE_SQL = SQL_SCHEMA_PATH.read_text(encoding="utf-8")
MIGRATION_SQL = MIGRATION_PATH.read_text(encoding="utf-8")


def load_runner():
    spec = importlib.util.spec_from_file_location("run_migration", RUNNER_PATH)
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
    return connection


def seed_legacy_03(connection: sqlite3.Connection) -> dict[str, str]:
    """Jeu minimal 0.3 : aucune colonne 0.4 n'est utilisée."""
    trader_id = fx.insert_trader(connection)
    market_id = fx.insert_market(connection)
    token_id = fx.insert_token(connection, "tok_fixture_yes", market_id, "Yes", 0)
    connection.execute(
        """
        INSERT INTO data_manifests(
            manifest_id, created_at, cutoff_received_timestamp, filters_json,
            first_source_timestamp, last_source_timestamp, event_count, sha256, notes
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        ("manifest_fixture_001", fx.TS0, fx.TS3,
         fx._dumps({"sources": ["fixture"]}), fx.TS0, fx.TS2, 1,
         fx.SHA256_ZERO, "Manifeste legacy 0.3"),
    )
    fx.insert_fee_schedule(connection)
    hypothesis_id = fx.insert_hypothesis(connection, trader_id)
    strategy_id, strategy_version = fx.insert_strategy(
        connection, hypothesis_id, trader_id
    )
    experiment_id = fx.insert_experiment(connection, strategy_id, strategy_version)

    book_event = "evt_legacy_book"
    connection.execute(
        """
        INSERT INTO market_events(
            event_id, schema_version, event_type, source, source_event_id,
            source_schema_version, source_timestamp, received_timestamp,
            ingested_at, market_id, token_id, quality_flags_json
        ) VALUES (?, '1.0.0', 'book_snapshot', 'fixture', 'legacy-book',
                  'fixture-v0', ?, ?, ?, ?, ?, '["fixture"]')
        """,
        (book_event, fx.TS0, fx.TS0, fx.TS0, market_id, token_id),
    )
    connection.execute(
        "INSERT INTO book_snapshots(event_id, bids_json, asks_json, book_hash, "
        "tick_size_micros) VALUES (?, ?, ?, ?, ?)",
        (book_event, fx._dumps(fx.BIDS), fx._dumps(fx.ASKS), "legacy-book", 10000),
    )
    trade_event = "evt_legacy_trade"
    connection.execute(
        """
        INSERT INTO market_events(
            event_id, schema_version, event_type, source, source_event_id,
            source_schema_version, source_timestamp, received_timestamp,
            ingested_at, market_id, token_id, accounting_unit, quality_flags_json
        ) VALUES (?, '1.0.0', 'trade', 'fixture', 'legacy-trade',
                  'fixture-v0', ?, ?, ?, ?, ?, 'pUSD', '["fixture"]')
        """,
        (trade_event, fx.TS1, fx.TS1, fx.TS1, market_id, token_id),
    )
    connection.execute(
        "INSERT INTO trade_events(event_id, price_micros, size_micros, taker_side, "
        "trader_id, tx_hash) VALUES (?, ?, ?, ?, ?, ?)",
        (trade_event, 530000, 1000000, "BUY", trader_id, "0x" + "1" * 64),
    )
    order_id = fx.insert_order(
        connection, experiment_id, market_id, token_id, book_event,
        order_id="ord_legacy", idempotency_key="idem-legacy",
    )
    fx.insert_estimate(connection, order_id, book_event, estimate_id="est_legacy")
    fx.insert_fill(connection, order_id, book_event, fill_id="fill_legacy")
    return {
        "market_id": market_id,
        "token_id": token_id,
        "experiment_id": experiment_id,
        "book_event": book_event,
        "trade_event": trade_event,
        "order_id": order_id,
    }


def test_migration_preserves_rows_and_versions() -> None:
    connection = baseline_connection()
    seeded = seed_legacy_03(connection)
    before = {
        table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        for table in ("market_events", "simulated_orders", "simulated_fills")
    }
    connection.executescript(MIGRATION_SQL)

    assert connection.execute("PRAGMA user_version").fetchone()[0] == 4
    assert [
        tuple(row) for row in connection.execute(
            "SELECT version, name FROM schema_migrations ORDER BY version"
        )
    ] == [(4, "0004_consolidation")]
    assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    assert connection.execute("PRAGMA foreign_key_check").fetchall() == []

    after = {
        table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        for table in before
    }
    assert after == before

    # Les lignes legacy restent lisibles, sans valeur inventée.
    assert connection.execute(
        "SELECT normalizer_version FROM market_events WHERE event_id = ?",
        (seeded["trade_event"],),
    ).fetchone()[0] is None
    assert connection.execute(
        "SELECT trader_visibility FROM trade_events WHERE event_id = ?",
        (seeded["trade_event"],),
    ).fetchone()[0] is None
    assert connection.execute(
        "SELECT source_class FROM data_manifests WHERE manifest_id = 'manifest_fixture_001'"
    ).fetchone()[0] is None
    connection.close()


def test_migration_journal_uses_canonical_timestamp() -> None:
    connection = baseline_connection()
    seed_legacy_03(connection)
    connection.executescript(MIGRATION_SQL)
    applied_at = connection.execute(
        "SELECT applied_at FROM schema_migrations WHERE version = 4"
    ).fetchone()[0]
    assert re.fullmatch(
        r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}"
        r"\.[0-9]{6}Z",
        applied_at,
    ), applied_at
    connection.close()


def test_migration_refuses_suspended_fee_formula() -> None:
    connection = baseline_connection()
    fx.insert_fee_schedule(connection, "fee_per_share_legacy", fee_formula="per_share")
    with pytest.raises(sqlite3.IntegrityError):
        connection.executescript(MIGRATION_SQL)
    assert connection.execute("PRAGMA user_version").fetchone()[0] == 3
    connection.close()


def test_new_event_requires_normalizer_version() -> None:
    connection = baseline_connection()
    seeded = seed_legacy_03(connection)
    connection.executescript(MIGRATION_SQL)
    with pytest.raises(sqlite3.IntegrityError):
        fx.insert_envelope(
            connection, "evt_missing_normalizer", "book_snapshot",
            market_id=seeded["market_id"], token_id=seeded["token_id"],
            normalizer_version=None,
        )
    connection.close()


def test_trade_visibility_must_match_trader_id() -> None:
    connection = baseline_connection()
    seeded = seed_legacy_03(connection)
    connection.executescript(MIGRATION_SQL)
    event = "evt_visibility_bad"
    fx.insert_envelope(
        connection, event, "trade", market_id=seeded["market_id"],
        token_id=seeded["token_id"], accounting_unit="pUSD",
    )
    with pytest.raises(sqlite3.IntegrityError):
        fx.insert_trade_detail(
            connection, event, trader_id=None, trader_visibility="identified",
        )
    connection.close()


def test_order_accounting_unit_must_match_experiment() -> None:
    connection = baseline_connection()
    seeded = seed_legacy_03(connection)
    connection.executescript(MIGRATION_SQL)
    with pytest.raises(sqlite3.IntegrityError):
        fx.insert_order(
            connection, seeded["experiment_id"], seeded["market_id"],
            seeded["token_id"], seeded["book_event"],
            order_id="ord_bad_unit", idempotency_key="idem-bad-unit",
            accounting_unit="USDC",
        )
    connection.close()


def test_order_identity_is_immutable() -> None:
    connection = baseline_connection()
    seeded = seed_legacy_03(connection)
    connection.executescript(MIGRATION_SQL)
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            "UPDATE simulated_orders SET requested_size_micros = 1 WHERE order_id = ?",
            (seeded["order_id"],),
        )
    connection.execute(
        "UPDATE simulated_orders SET rationale = 'ok' WHERE order_id = ?",
        (seeded["order_id"],),
    )
    connection.close()


def test_unknown_valuation_uses_nulls() -> None:
    connection = baseline_connection()
    seeded = seed_legacy_03(connection)
    connection.executescript(MIGRATION_SQL)
    fx.insert_snapshot(
        connection, seeded["experiment_id"], snapshot_id="snap_unknown",
        positions_value_micros=None, equity_micros=None,
        unrealized_pnl_micros=None, valuation_method="none",
    )
    row = connection.execute(
        "SELECT positions_value_micros, equity_micros, unrealized_pnl_micros "
        "FROM portfolio_snapshots WHERE snapshot_id = 'snap_unknown'"
    ).fetchone()
    assert tuple(row) == (None, None, None)
    connection.close()


def test_event_replacement_is_traceable_and_current_view_excludes_old() -> None:
    connection = baseline_connection()
    seeded = seed_legacy_03(connection)
    connection.executescript(MIGRATION_SQL)
    new_event = "evt_replacement"
    fx.insert_envelope(
        connection, new_event, "trade", market_id=seeded["market_id"],
        token_id=seeded["token_id"], accounting_unit="pUSD",
        source_event_id="legacy-trade-v2",
    )
    connection.execute(
        "INSERT INTO event_replacements(replacement_id, old_event_id, new_event_id, "
        "reason, normalizer_version, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        ("repl_001", seeded["trade_event"], new_event, "reparse", "1.1.0", fx.TS2),
    )
    current_ids = {
        row[0] for row in connection.execute(
            "SELECT event_id FROM v_current_market_events"
        )
    }
    assert new_event in current_ids
    assert seeded["trade_event"] not in current_ids
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            "UPDATE event_replacements SET reason = 'other' WHERE replacement_id = 'repl_001'"
        )
    connection.close()


def test_manifest_requires_source_class() -> None:
    connection = baseline_connection()
    seeded = seed_legacy_03(connection)
    connection.executescript(MIGRATION_SQL)
    with pytest.raises(sqlite3.IntegrityError):
        fx.insert_manifest(connection, "manifest_no_class", source_class=None)
    connection.close()


def test_bad_config_hash_is_rejected() -> None:
    connection = baseline_connection()
    seeded = seed_legacy_03(connection)
    connection.executescript(MIGRATION_SQL)
    with pytest.raises(sqlite3.IntegrityError):
        fx.insert_experiment(
            connection, "strategy_fixture_001", "0.1.0",
            experiment_id="exp_bad_hash", config_hash="not-a-sha256",
        )
    connection.close()


def test_book_internal_hash_format_is_checked() -> None:
    connection = baseline_connection()
    seeded = seed_legacy_03(connection)
    connection.executescript(MIGRATION_SQL)
    event = "evt_bad_book_hash"
    fx.insert_envelope(
        connection, event, "book_snapshot", market_id=seeded["market_id"],
        token_id=seeded["token_id"],
    )
    with pytest.raises(sqlite3.IntegrityError):
        fx.insert_book_snapshot_detail(
            connection, event, internal_book_hash="z" * 64,
        )
    connection.close()


def test_void_payout_requires_documented_rule() -> None:
    connection = baseline_connection()
    seeded = seed_legacy_03(connection)
    connection.executescript(MIGRATION_SQL)
    event = "evt_void_no_rule"
    fx.insert_envelope(connection, event, "market_resolution", market_id=seeded["market_id"])
    with pytest.raises(sqlite3.IntegrityError):
        fx.insert_resolution_detail(
            connection, event, resolution_status="VOID",
            winning_token_id=None, payout_per_share_micros=1_000_000,
            settlement_asset="USDC", void_rule_ref=None,
        )
    connection.close()


def test_custom_formula_ref_is_suspended_for_new_rows() -> None:
    connection = baseline_connection()
    seed_legacy_03(connection)
    connection.executescript(MIGRATION_SQL)
    with pytest.raises(sqlite3.IntegrityError, match="custom_formula_ref"):
        fx.insert_fee_schedule(
            connection, "fee_custom_new", custom_formula_ref="legacy-custom"
        )
    fx.insert_fee_schedule(connection, "fee_valid_new")
    with pytest.raises(sqlite3.IntegrityError, match="custom_formula_ref"):
        connection.execute(
            "UPDATE fee_schedules SET custom_formula_ref = 'legacy-custom' "
            "WHERE fee_schedule_id = 'fee_valid_new'"
        )
    connection.close()


def test_runner_restores_foreign_keys_after_failure() -> None:
    connection = baseline_connection()
    fx.insert_fee_schedule(connection, "fee_per_share_legacy", fee_formula="per_share")
    runner = load_runner()
    with pytest.raises(sqlite3.IntegrityError):
        runner.apply_migration_on_connection(connection, MIGRATION_PATH)
    assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    assert connection.execute("PRAGMA recursive_triggers").fetchone()[0] == 1
    assert connection.execute("PRAGMA user_version").fetchone()[0] == 3
    assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    connection.close()


def test_runner_applies_migration_and_keeps_foreign_keys_on() -> None:
    connection = baseline_connection()
    seed_legacy_03(connection)
    runner = load_runner()
    runner.apply_migration_on_connection(connection, MIGRATION_PATH)
    assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    assert connection.execute("PRAGMA recursive_triggers").fetchone()[0] == 1
    assert connection.execute("PRAGMA user_version").fetchone()[0] == 4
    assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    connection.close()


def test_runner_restores_pragmas_after_preflight_failure() -> None:
    connection = baseline_connection()
    connection.execute("PRAGMA foreign_keys = OFF")
    connection.execute("PRAGMA recursive_triggers = OFF")
    connection.execute("PRAGMA user_version = 0")
    runner = load_runner()
    with pytest.raises(runner.MigrationError):
        runner.apply_migration_on_connection(connection, MIGRATION_PATH)
    assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    assert connection.execute("PRAGMA recursive_triggers").fetchone()[0] == 1
    connection.close()


def test_runner_refuses_missing_database_without_creating(tmp_path: Path) -> None:
    runner = load_runner()
    path = tmp_path / "missing.sqlite3"
    with pytest.raises(runner.MigrationError):
        runner.apply_migration(path, MIGRATION_PATH)
    assert not path.exists()


def test_runner_restore_failure_does_not_mask_migration_error(monkeypatch) -> None:
    connection = baseline_connection()
    connection.execute("PRAGMA user_version = 0")
    runner = load_runner()
    original = runner._configure_connection
    calls = {"count": 0}

    def failing_configure(conn, **kwargs):
        calls["count"] += 1
        if calls["count"] >= 2:
            raise RuntimeError("restore-fail")
        return original(conn, **kwargs)

    monkeypatch.setattr(runner, "_configure_connection", failing_configure)
    with pytest.raises(runner.MigrationError, match="restauration"):
        runner.apply_migration_on_connection(connection, MIGRATION_PATH)
    connection.close()


def test_ledger_posting_shape_and_unit_are_enforced() -> None:
    connection = baseline_connection()
    seeded = seed_legacy_03(connection)
    connection.executescript(MIGRATION_SQL)
    with pytest.raises(sqlite3.IntegrityError):
        fx.insert_ledger_transaction(
            connection, "tx_bad_cash_token",
            [
                {"account": "CASH", "amount_micros": 10,
                 "token_id": seeded["token_id"]},
                {"account": "CAPITAL", "amount_micros": -10},
            ],
        )
    with pytest.raises(sqlite3.IntegrityError):
        fx.insert_ledger_transaction(
            connection, "tx_bad_position_no_token",
            [
                {"account": "POSITION", "amount_micros": 10,
                 "quantity_micros": 10},
                {"account": "CASH", "amount_micros": -10},
            ],
        )
    with pytest.raises(sqlite3.IntegrityError):
        fx.insert_ledger_transaction(
            connection, "tx_bad_unit",
            [
                {"account": "CASH", "amount_micros": 10,
                 "accounting_unit": "USDC"},
                {"account": "CAPITAL", "amount_micros": -10,
                 "accounting_unit": "USDC"},
            ],
        )
    connection.close()
