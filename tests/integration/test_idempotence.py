"""Idempotence des insertions concernées.

Le contrat repose sur des clés uniques et des identifiants déterministes. Le
SQL ne fait pas l'idempotence à lui seul : il doit rejeter un doublon, et
``INSERT OR IGNORE`` doit laisser la base inchangée après un redémarrage.
"""

from __future__ import annotations

import sqlite3

import pytest

from labtest import sqlfixtures as fx


def _event_count(db, event_id):
    return db.execute(
        "SELECT COUNT(*) FROM market_events WHERE event_id = ?", (event_id,)
    ).fetchone()[0]


def test_double_append_same_event_id_is_rejected(db, seeded):
    before = _event_count(db, seeded["trade_event"])
    with pytest.raises(sqlite3.IntegrityError):
        fx.insert_envelope(
            db, seeded["trade_event"], "trade",
            market_id=seeded["market_id"], token_id=seeded["token_yes"],
            accounting_unit="pUSD",
        )
    assert _event_count(db, seeded["trade_event"]) == before


def test_duplicate_source_event_id_is_rejected_between_two_event_ids(db, seeded):
    with pytest.raises(sqlite3.IntegrityError):
        fx.insert_envelope(
            db, "evt_same_source_record", "book_snapshot",
            market_id=seeded["market_id"], token_id=seeded["token_yes"],
            source_event_id=f"src-{seeded['trade_event']}",
        )


def test_insert_or_ignore_does_not_duplicate_an_event(db, seeded):
    before = db.execute("SELECT COUNT(*) FROM market_events").fetchone()[0]
    db.execute(
        """
        INSERT OR IGNORE INTO market_events(
            event_id, schema_version, event_type, source, source_timestamp,
            received_timestamp, ingested_at, market_id, token_id,
            accounting_unit, quality_flags_json
        ) VALUES (?, '1.0.0', 'trade', 'fixture', ?, ?, ?, ?, ?, 'pUSD', '[]')
        """,
        (
            seeded["trade_event"], fx.TS1, fx.TS1, fx.TS1,
            seeded["market_id"], seeded["token_yes"],
        ),
    )
    after = db.execute("SELECT COUNT(*) FROM market_events").fetchone()[0]
    assert after == before


def test_double_order_idempotency_key_is_rejected(db, seeded):
    with pytest.raises(sqlite3.IntegrityError):
        fx.insert_order(
            db, seeded["experiment_id"], seeded["market_id"], seeded["token_yes"],
            seeded["book_event"], order_id="ord_duplicate_key",
            idempotency_key="idem-order-fixture-001",
        )


def test_double_fill_index_for_same_order_is_rejected(db, seeded):
    with pytest.raises(sqlite3.IntegrityError):
        fx.insert_fill(
            db, seeded["order_id"], seeded["book_event"],
            fill_id="fill_duplicate_index", fill_index=0,
        )


def test_double_estimate_for_same_order_is_rejected(db, seeded):
    with pytest.raises(sqlite3.IntegrityError):
        fx.insert_estimate(
            db, seeded["order_id"], seeded["book_event"],
            estimate_id="est_duplicate_order",
        )


def test_double_ledger_idempotency_key_is_rejected(db, seeded):
    fx.insert_ledger_transaction(
        db, "tx_idem_1", fx.deposit_postings(),
        idempotency_key="idem:deposit:fixture",
    )
    with pytest.raises(sqlite3.IntegrityError):
        fx.insert_ledger_transaction(
            db, "tx_idem_2", fx.deposit_postings(),
            idempotency_key="idem:deposit:fixture",
        )


def test_double_ledger_reference_and_kind_is_rejected(db, seeded):
    fx.insert_ledger_transaction(
        db, "tx_ref_1", fx.deposit_postings(),
        kind="fill", ref_type="fill", ref_id="fill_fixture_001",
    )
    with pytest.raises(sqlite3.IntegrityError):
        fx.insert_ledger_transaction(
            db, "tx_ref_2", fx.deposit_postings(),
            kind="fill", ref_type="fill", ref_id="fill_fixture_001",
        )


def test_reversal_is_idempotent_by_reference(db, seeded):
    original = fx.buy_postings()
    fx.insert_ledger_transaction(
        db, "tx_original", original, kind="fill", ref_type="fill",
        ref_id="fill_fixture_001",
    )
    fx.insert_ledger_transaction(
        db, "tx_reversal", fx.negate_postings(original), kind="reversal",
        ref_type="fill", ref_id="fill_fixture_001",
        idempotency_key="idem:reversal:fill_fixture_001",
    )
    with pytest.raises(sqlite3.IntegrityError):
        fx.insert_ledger_transaction(
            db, "tx_reversal_again", fx.negate_postings(original),
            kind="reversal", ref_type="fill", ref_id="fill_fixture_001",
            idempotency_key="idem:reversal:fill_fixture_001",
        )


def test_double_portfolio_snapshot_timestamp_is_rejected(db, seeded):
    fx.insert_snapshot(
        db, seeded["experiment_id"], snapshot_id="snap_idem_1",
        as_of_timestamp=fx.TS1,
    )
    with pytest.raises(sqlite3.IntegrityError):
        fx.insert_snapshot(
            db, seeded["experiment_id"], snapshot_id="snap_idem_2",
            as_of_timestamp=fx.TS1,
        )


def test_token_outcome_uniqueness_is_enforced(db, seeded):
    with pytest.raises(sqlite3.IntegrityError):
        fx.insert_token(
            db, "tok_duplicate_index", seeded["market_id"], "Maybe", 0,
        )
    with pytest.raises(sqlite3.IntegrityError):
        fx.insert_token(
            db, "tok_duplicate_label", seeded["market_id"], "Yes", 2,
        )


def test_replay_after_reopening_the_database_stays_idempotent(file_db):
    connection, path = file_db
    seeded = fx.seed_basic(connection)
    event_count = connection.execute(
        "SELECT COUNT(*) FROM market_events"
    ).fetchone()[0]
    connection.commit()
    connection.close()

    reopened = fx.open_second_connection(path)
    try:
        reopened.execute(
            """
            INSERT OR IGNORE INTO market_events(
                event_id, schema_version, event_type, source, source_timestamp,
                received_timestamp, ingested_at, market_id, token_id,
                accounting_unit, quality_flags_json
            ) VALUES (?, '1.0.0', 'trade', 'fixture', ?, ?, ?, ?, ?, 'pUSD', '[]')
            """,
            (
                seeded["trade_event"], fx.TS1, fx.TS1, fx.TS1,
                seeded["market_id"], seeded["token_yes"],
            ),
        )
        reopened.commit()
        assert reopened.execute(
            "SELECT COUNT(*) FROM market_events"
        ).fetchone()[0] == event_count

        with pytest.raises(sqlite3.IntegrityError):
            fx.insert_envelope(
                reopened, seeded["trade_event"], "trade",
                market_id=seeded["market_id"], token_id=seeded["token_yes"],
                accounting_unit="pUSD",
            )
    finally:
        reopened.close()
