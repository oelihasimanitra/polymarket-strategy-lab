"""Tests d'intégration du schéma SQLite consolidé (version 0.4).

Ces tests exécutent le schéma initial 0.3 puis la migration 0004 sur une base
neuve, et vérifient les contraintes réellement présentes.
"""

from __future__ import annotations

import sqlite3

import pytest

from labtest import sqlfixtures as fx
from labtest.sqlschema import (
    column_info,
    explicit_index_names,
    table_names,
    trigger_names,
    view_names,
)

EXPECTED_TABLES = {
    "schema_migrations",
    "traders",
    "hypotheses",
    "markets",
    "market_tokens",
    "data_manifests",
    "fee_schedules",
    "strategies",
    "experiments",
    "market_events",
    "trade_events",
    "trader_activity_events",
    "book_snapshots",
    "book_delta_changes",
    "market_metadata_events",
    "market_resolution_events",
    "connection_events",
    "data_quality_incidents",
    "simulated_orders",
    "execution_estimates",
    "simulated_fills",
    "ledger_transactions",
    "ledger_postings",
    "portfolio_snapshots",
    "experiment_metrics",
    "benchmark_runs",
    "event_replacements",
    "position_valuations",
    "settlement_conversions",
}

EXPECTED_VIEWS = {
    "v_experiment_cash",
    "v_experiment_positions",
    "v_order_execution",
    "v_ledger_anomalies",
    "v_experiment_latest_snapshot",
    "v_negative_cash",
    "v_position_anomalies",
    "v_current_market_events",
}

EXPECTED_TRIGGERS = {
    "trg_trade_events_type",
    "trg_trader_activity_events_type",
    "trg_book_snapshots_type",
    "trg_book_delta_changes_type",
    "trg_market_metadata_events_type",
    "trg_market_resolution_events_type",
    "trg_connection_events_type",
    # Cohérence des événements de détail et des résolutions
    "trg_market_metadata_outcomes_unique",
    "trg_resolution_winning_token_market",
    "trg_resolution_conversion_required",
    "trg_book_delta_hash_consistency",
    # Append-only : enveloppe et sept tables de détail
    "trg_market_events_no_update",
    "trg_market_events_no_delete",
    "trg_trade_events_no_update",
    "trg_trade_events_no_delete",
    "trg_trader_activity_events_no_update",
    "trg_trader_activity_events_no_delete",
    "trg_book_snapshots_no_update",
    "trg_book_snapshots_no_delete",
    "trg_book_delta_changes_no_update",
    "trg_book_delta_changes_no_delete",
    "trg_market_metadata_events_no_update",
    "trg_market_metadata_events_no_delete",
    "trg_market_resolution_events_no_update",
    "trg_market_resolution_events_no_delete",
    "trg_connection_events_no_update",
    "trg_connection_events_no_delete",
    # Références de carnet et cohérence des fills
    "trg_orders_book_snapshot_insert",
    "trg_orders_book_snapshot_update",
    "trg_estimates_book_snapshot_insert",
    "trg_estimates_book_snapshot_update",
    "trg_fills_book_snapshot_insert",
    "trg_fills_order_status_insert",
    # Immuabilité comptable
    "trg_simulated_fills_no_update",
    "trg_simulated_fills_no_delete",
    "trg_ledger_transactions_no_update",
    "trg_ledger_transactions_no_delete",
    "trg_ledger_postings_no_update",
    "trg_ledger_postings_no_delete",
    # Consolidation 0.4
    "trg_market_events_normalizer_version",
    "trg_trade_events_visibility",
    "trg_book_snapshot_hash_fields",
    "trg_book_delta_hash_fields",
    "trg_resolution_void_rule",
    "trg_data_manifests_source_class",
    "trg_data_manifests_sha256",
    "trg_experiments_config_hash",
    "trg_orders_unit_insert",
    "trg_orders_unit_update",
    "trg_estimates_unit_insert",
    "trg_estimates_unit_update",
    "trg_fills_unit_insert",
    "trg_ledger_postings_unit_insert",
    "trg_ledger_postings_token_shape",
    "trg_orders_identity_update",
    "trg_estimates_identity_update",
    "trg_event_replacements_no_update",
    "trg_event_replacements_no_delete",
    "trg_event_replacements_same_market",
    "trg_fee_schedules_custom_formula_insert",
    "trg_fee_schedules_custom_formula_update",
    "trg_ledger_fee_ref_fill",
    "trg_schema_migrations_applied_at",
}

EXPECTED_INDEXES = {
    "ux_market_events_source_event",
    "idx_market_events_market_time",
    "idx_market_events_type_time",
    "idx_market_events_token_type_time",
    "idx_market_events_received",
    "idx_trade_events_trader",
    "idx_trader_activity_trader",
    "idx_incidents_stream_time",
    "idx_incidents_market_time",
    "idx_orders_experiment_time",
    "idx_orders_status",
    "idx_orders_market_token",
    "idx_fills_order",
    "idx_ledger_tx_experiment_time",
    "idx_ledger_tx_ref",
    "idx_ledger_postings_transaction",
    "idx_ledger_postings_account_token",
    "idx_benchmarks_evaluated",
    "idx_event_replacements_new",
    "idx_position_valuations_token",
    "idx_settlement_conversions_resolution",
}

BAD_TIMESTAMPS = [
    "2026-10-01T12:00:00+00:00",
    "2026-10-01T12:00:00.00000Z",
    "2026-10-01T12:00:00.0000000Z",
    "2026-10-01T12:00:00.000000z",
    "2026-10-01 12:00:00.000000Z",
]


# ---------------------------------------------------------------------------
# Structure
# ---------------------------------------------------------------------------


def test_schema_applies_on_a_fresh_database(db):
    assert table_names(db) == EXPECTED_TABLES


def test_expected_views(db):
    assert view_names(db) == EXPECTED_VIEWS


def test_expected_triggers(db):
    assert trigger_names(db) == EXPECTED_TRIGGERS


def test_expected_indexes(db):
    assert explicit_index_names(db) == EXPECTED_INDEXES


def test_all_user_tables_are_strict(db):
    rows = db.execute(
        "SELECT name, strict FROM pragma_table_list "
        "WHERE schema = 'main' AND type = 'table' AND name NOT LIKE 'sqlite_%'"
    ).fetchall()
    assert {row["name"] for row in rows} == EXPECTED_TABLES
    assert all(row["strict"] == 1 for row in rows), [
        row["name"] for row in rows if row["strict"] != 1
    ]


def test_user_version_is_set(db):
    assert db.execute("PRAGMA user_version").fetchone()[0] == 4


def test_foreign_keys_are_enabled_on_the_test_connection(db):
    assert db.execute("PRAGMA foreign_keys").fetchone()[0] == 1


def test_recursive_triggers_are_enabled_on_the_test_connection(db):
    # Nécessaire pour que INSERT OR REPLACE déclenche les triggers DELETE
    # d'append-only. PRAGMA est par connexion, pas persistant.
    assert db.execute("PRAGMA recursive_triggers").fetchone()[0] == 1


def test_only_metrics_may_use_real(db):
    real_columns = []
    for table in EXPECTED_TABLES:
        for name, info in column_info(db, table).items():
            if "REAL" in info["type"].upper():
                real_columns.append((table, name))
    assert real_columns == [("experiment_metrics", "value_real")]


def test_every_micros_column_is_integer(db):
    offenders = []
    for table in EXPECTED_TABLES:
        for name, info in column_info(db, table).items():
            if name.endswith("_micros") and info["type"].upper() != "INTEGER":
                offenders.append((table, name, info["type"]))
    assert offenders == []


def test_schema_migrations_table_records_0004(db):
    rows = db.execute(
        "SELECT version, name FROM schema_migrations ORDER BY version"
    ).fetchall()
    assert [(row["version"], row["name"]) for row in rows] == [
        (4, "0004_consolidation")
    ]


def test_database_integrity_checks_pass_on_seeded_data(db, seeded):
    assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    assert db.execute("PRAGMA foreign_key_check").fetchall() == []


# ---------------------------------------------------------------------------
# Clés étrangères
# ---------------------------------------------------------------------------


def test_foreign_key_violations_are_rejected(db, seeded):
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            "INSERT INTO market_tokens(token_id, market_id, outcome_label, outcome_index) "
            "VALUES ('tok_orphan', 'mkt_missing', 'Yes', 0)"
        )
    with pytest.raises(sqlite3.IntegrityError):
        fx.insert_envelope(
            db, "evt_orphan_001", "book_snapshot",
            market_id="mkt_missing", token_id=seeded["token_yes"],
        )
    with pytest.raises(sqlite3.IntegrityError):
        fx.insert_experiment(
            db, "strat_missing", "0.1.0", experiment_id="exp_orphan"
        )
    with pytest.raises(sqlite3.IntegrityError):
        fx.insert_fill(
            db, "ord_missing", seeded["book_event"], fill_id="fill_orphan"
        )
    with pytest.raises(sqlite3.IntegrityError):
        fx.insert_ledger_transaction(
            db, "tx_orphan", fx.deposit_postings(),
            experiment_id="exp_missing",
        )


def test_delete_is_restricted_when_children_exist(db, seeded):
    with pytest.raises(sqlite3.IntegrityError):
        db.execute("DELETE FROM markets WHERE market_id = ?", (seeded["market_id"],))
    with pytest.raises(sqlite3.IntegrityError):
        db.execute("DELETE FROM experiments WHERE experiment_id = ?",
                   (seeded["experiment_id"],))
    with pytest.raises(sqlite3.IntegrityError):
        db.execute("DELETE FROM simulated_orders WHERE order_id = ?",
                   (seeded["order_id"],))


# ---------------------------------------------------------------------------
# STRICT et timestamps
# ---------------------------------------------------------------------------


def test_strict_tables_reject_wrong_types(db, seeded):
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            "INSERT INTO markets(market_id, first_seen_at, tick_size_micros) "
            "VALUES ('mkt_bad_type', ?, 'abc')",
            (fx.TS0,),
        )
    with pytest.raises(sqlite3.IntegrityError):
        fx.insert_ledger_transaction(
            db, "tx_bad_type",
            [
                {"account": "CASH", "amount_micros": "not-an-integer"},
                {"account": "CAPITAL", "amount_micros": -1000},
            ],
        )


def _bad_trader(db, seed, timestamp):
    db.execute(
        "INSERT INTO traders(trader_id, display_name, public_identifier, "
        "identifier_type, selected_at, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        ("trader_bad_ts", "T", "public:bad", "wallet", timestamp, timestamp),
    )


def _bad_event(db, seed, timestamp):
    fx.insert_envelope(
        db, "evt_bad_ts", "book_snapshot", market_id=seed["market_id"],
        token_id=seed["token_yes"], source_timestamp=timestamp,
        received_timestamp=timestamp,
    )


def _bad_fee_schedule(db, seed, timestamp):
    fx.insert_fee_schedule(db, "fee_bad_ts", created_at=timestamp)


def _bad_experiment(db, seed, timestamp):
    fx.insert_experiment(
        db, seed["strategy_id"], seed["strategy_version"],
        experiment_id="exp_bad_ts", start_time=timestamp,
    )


def _bad_order(db, seed, timestamp):
    fx.insert_order(
        db, seed["experiment_id"], seed["market_id"], seed["token_yes"],
        seed["book_event"], order_id="ord_bad_ts",
        decision_timestamp=timestamp,
    )


def _bad_snapshot(db, seed, timestamp):
    fx.insert_snapshot(
        db, seed["experiment_id"], snapshot_id="snap_bad_ts",
        as_of_timestamp=timestamp,
    )


def _bad_ledger(db, seed, timestamp):
    fx.insert_ledger_transaction(
        db, "tx_bad_ts", fx.deposit_postings(), occurred_at=timestamp,
    )


def _bad_incident(db, seed, timestamp):
    fx.insert_incident(db, incident_id="inc_bad_ts", detected_at=timestamp)


TIMESTAMP_CASES = {
    "traders.created_at": _bad_trader,
    "market_events.received_timestamp": _bad_event,
    "fee_schedules.created_at": _bad_fee_schedule,
    "experiments.start_time": _bad_experiment,
    "simulated_orders.decision_timestamp": _bad_order,
    "portfolio_snapshots.as_of_timestamp": _bad_snapshot,
    "ledger_transactions.occurred_at": _bad_ledger,
    "data_quality_incidents.detected_at": _bad_incident,
}


@pytest.mark.parametrize("case_name", sorted(TIMESTAMP_CASES))
@pytest.mark.parametrize("bad_timestamp", BAD_TIMESTAMPS)
def test_non_canonical_timestamps_are_rejected(db, seeded, case_name, bad_timestamp):
    case = TIMESTAMP_CASES[case_name]
    with pytest.raises(sqlite3.IntegrityError):
        case(db, seeded, bad_timestamp)


def test_market_events_require_accounting_unit_for_notional_events(db, seeded):
    with pytest.raises(sqlite3.IntegrityError):
        fx.insert_envelope(
            db, "evt_no_unit_trade", "trade",
            market_id=seeded["market_id"], token_id=seeded["token_yes"],
        )
    with pytest.raises(sqlite3.IntegrityError):
        fx.insert_envelope(
            db, "evt_no_unit_activity", "trader_activity",
            market_id=seeded["market_id"], token_id=seeded["token_yes"],
        )
    fx.insert_envelope(
        db, "evt_no_unit_book", "book_snapshot",
        market_id=seeded["market_id"], token_id=seeded["token_yes"],
    )


def test_sql_enforces_accounting_unit_pattern(db, seeded):
    with pytest.raises(sqlite3.IntegrityError):
        fx.insert_envelope(
            db, "evt_bad_unit", "trade",
            market_id=seeded["market_id"], token_id=seeded["token_yes"],
            accounting_unit="1pUSD",
        )


def test_trader_activity_requires_market_id_in_sql(db, seeded):
    with pytest.raises(sqlite3.IntegrityError):
        fx.insert_envelope(
            db, "evt_activity_no_market", "trader_activity",
            token_id=seeded["token_yes"], accounting_unit="pUSD",
        )


def test_raw_payload_hash_requires_reference_in_sql(db, seeded):
    with pytest.raises(sqlite3.IntegrityError):
        fx.insert_envelope(
            db, "evt_hash_without_ref", "book_snapshot",
            market_id=seeded["market_id"], token_id=seeded["token_yes"],
            raw_payload_sha256="0" * 64,
        )


def test_rejected_order_cannot_have_fills(db, seeded):
    fx.insert_order(
        db, seeded["experiment_id"], seeded["market_id"], seeded["token_yes"],
        None, order_id="ord_rejected_fill", idempotency_key="idem-rejected-fill",
        status="rejected", rejection_reason="stale_book",
        simulated_arrival_timestamp=None,
    )
    with pytest.raises(sqlite3.IntegrityError):
        fx.insert_fill(
            db, "ord_rejected_fill", seeded["book_event"],
            fill_id="fill_on_rejected_order", fill_index=0,
        )


# ---------------------------------------------------------------------------
# CHECK d'énumération
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "builder",
    [
        lambda db, s: fx.insert_envelope(
            db, "evt_enum_bad", "not_an_event_type",
            market_id=s["market_id"], token_id=s["token_yes"],
            accounting_unit="pUSD",
        ),
        lambda db, s: fx.insert_envelope(
            db, "evt_enum_bad", "book_snapshot", source="twitter",
            market_id=s["market_id"], token_id=s["token_yes"],
        ),
        lambda db, s: fx.insert_market(db, "mkt_enum_bad", status="paused"),
    ],
    ids=["event_type", "source", "market_status"],
)
def test_market_enum_checks(db, seeded, builder):
    with pytest.raises(sqlite3.IntegrityError):
        builder(db, seeded)


def test_trade_and_activity_enum_checks(db, seeded):
    trade_event = "evt_enum_trade"
    fx.insert_envelope(
        db, trade_event, "trade", market_id=seeded["market_id"],
        token_id=seeded["token_yes"], accounting_unit="pUSD",
    )
    with pytest.raises(sqlite3.IntegrityError):
        fx.insert_trade_detail(db, trade_event, taker_side="HOLD")

    activity_event = "evt_enum_activity"
    fx.insert_envelope(
        db, activity_event, "trader_activity", market_id=seeded["market_id"],
        token_id=seeded["token_yes"], accounting_unit="pUSD",
    )
    with pytest.raises(sqlite3.IntegrityError):
        fx.insert_activity_detail(
            db, activity_event, seeded["trader_id"], activity_type="AIRDROP",
        )


def test_fee_schedule_enum_checks(db, seeded):
    with pytest.raises(sqlite3.IntegrityError):
        fx.insert_fee_schedule(db, "fee_enum_1", verification_status="official")
    with pytest.raises(sqlite3.IntegrityError):
        fx.insert_fee_schedule(db, "fee_enum_2", fee_formula="percentage")
    with pytest.raises(sqlite3.IntegrityError):
        fx.insert_fee_schedule(db, "fee_enum_3", rounding_rule="banker")


def test_experiment_enum_checks(db, seeded):
    for index, kwargs in enumerate(
        [
            {"period_type": "backtest"},
            {"fee_status": "official"},
            {"status": "done"},
        ]
    ):
        with pytest.raises(sqlite3.IntegrityError):
            fx.insert_experiment(
                db, seeded["strategy_id"], seeded["strategy_version"],
                experiment_id=f"exp_enum_{index}", **kwargs,
            )


def test_order_estimate_and_fill_enum_checks(db, seeded):
    with pytest.raises(sqlite3.IntegrityError):
        fx.insert_order(
            db, seeded["experiment_id"], seeded["market_id"], seeded["token_yes"],
            seeded["book_event"], order_id="ord_enum_1", side="HOLD",
        )
    with pytest.raises(sqlite3.IntegrityError):
        fx.insert_fill(
            db, seeded["order_id"], seeded["book_event"], fill_id="fill_enum_1",
            fill_index=5, fee_formula="percentage",
        )
    with pytest.raises(sqlite3.IntegrityError):
        fx.insert_fill(
            db, seeded["order_id"], seeded["book_event"], fill_id="fill_enum_2",
            fill_index=6, fee_unit="usdc",
        )


def test_ledger_enum_checks(db, seeded):
    with pytest.raises(sqlite3.IntegrityError):
        fx.insert_ledger_transaction(
            db, "tx_enum_1", fx.deposit_postings(), kind="magic",
        )
    with pytest.raises(sqlite3.IntegrityError):
        fx.insert_ledger_transaction(
            db, "tx_enum_2", fx.deposit_postings(), ref_type="magic",
        )
    with pytest.raises(sqlite3.IntegrityError):
        fx.insert_ledger_transaction(
            db, "tx_enum_3",
            [
                {"account": "MAGIC", "amount_micros": 1},
                {"account": "CAPITAL", "amount_micros": -1},
            ],
        )


# ---------------------------------------------------------------------------
# CHECK métier
# ---------------------------------------------------------------------------


def test_experiment_business_checks(db, seeded):
    with pytest.raises(sqlite3.IntegrityError):
        fx.insert_experiment(
            db, seeded["strategy_id"], seeded["strategy_version"],
            experiment_id="exp_no_manifest", data_manifest_id=None,
        )
    with pytest.raises(sqlite3.IntegrityError):
        fx.insert_experiment(
            db, seeded["strategy_id"], seeded["strategy_version"],
            experiment_id="exp_verified_no_fee", fee_status="verified",
            default_fee_schedule_id=None,
        )
    with pytest.raises(sqlite3.IntegrityError):
        fx.insert_experiment(
            db, seeded["strategy_id"], seeded["strategy_version"],
            experiment_id="exp_bad_period", start_time=fx.TS2, end_time=fx.TS1,
        )


def test_paper_live_may_start_without_manifest(db, seeded):
    fx.insert_experiment(
        db, seeded["strategy_id"], seeded["strategy_version"],
        experiment_id="exp_paper_live", period_type="paper_live",
        data_manifest_id=None, end_time=None,
    )
    assert db.execute(
        "SELECT COUNT(*) FROM experiments WHERE experiment_id = 'exp_paper_live'"
    ).fetchone()[0] == 1


def test_fee_schedule_business_checks(db, seeded):
    cases = [
        dict(verification_status="verified", source_url="http://example.invalid/fees",
             scope_type="market"),
        dict(verification_status="verified", scope_type="global",
             scope_evidence_ref=None),
        dict(fee_formula="custom", custom_formula_ref=None),
        dict(fee_formula="none", maker_rate_micros=0, taker_rate_micros=10000),
        dict(effective_from=fx.TS2, effective_to=fx.TS1),
        dict(taker_rate_micros=1_000_001),
        dict(rounding_increment_micros=0),
    ]
    for index, kwargs in enumerate(cases):
        with pytest.raises(sqlite3.IntegrityError):
            fx.insert_fee_schedule(db, f"fee_check_{index}", **kwargs)


def test_market_resolution_checks(db, seeded):
    event = "evt_resolution_check"
    fx.insert_envelope(db, event, "market_resolution", market_id=seeded["market_id"])
    for kwargs in (
        {"winning_token_id": None},
        {"settlement_asset": None},
        {"payout_per_share_micros": None},
    ):
        with pytest.raises(sqlite3.IntegrityError):
            fx.insert_resolution_detail(db, event, **kwargs)

    with pytest.raises(sqlite3.IntegrityError):
        fx.insert_resolution_detail(
            db, event, resolution_status="VOID", winning_token_id=seeded["token_yes"],
        )


def test_connection_gap_ordering(db, seeded):
    event = "evt_connection_check"
    fx.insert_envelope(db, event, "connection_status")
    with pytest.raises(sqlite3.IntegrityError):
        fx.insert_connection_detail(
            db, event, gap_start_timestamp=fx.TS2, gap_end_timestamp=fx.TS1,
        )


def test_market_metadata_outcomes_are_an_array_of_two(db, seeded):
    event = "evt_metadata_check"
    fx.insert_envelope(db, event, "market_metadata", market_id=seeded["market_id"])
    with pytest.raises(sqlite3.IntegrityError):
        fx.insert_metadata_detail(db, event, outcomes=[fx.OUTCOMES[0]])
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            "INSERT INTO market_metadata_events(event_id, status, collateral_asset, "
            "collateral_decimals, outcomes_json) VALUES (?, 'active', 'pUSD', 6, 'not-json')",
            (event,),
        )


def test_book_payload_constraints(db, seeded):
    event = "evt_book_check"
    fx.insert_envelope(
        db, event, "book_snapshot", market_id=seeded["market_id"],
        token_id=seeded["token_yes"],
    )
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            "INSERT INTO book_snapshots(event_id, bids_json, asks_json) "
            "VALUES (?, '{}', '[]')",
            (event,),
        )
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            "INSERT INTO book_snapshots(event_id, bids_json, asks_json) "
            "VALUES (?, 'not-json', '[]')",
            (event,),
        )


def test_book_delta_action_size_constraints(db, seeded):
    event = "evt_delta_check"
    fx.insert_envelope(
        db, event, "book_delta", market_id=seeded["market_id"],
        token_id=seeded["token_yes"],
    )
    with pytest.raises(sqlite3.IntegrityError):
        fx.insert_book_delta_detail(
            db, event,
            changes=[{"book_side": "BID", "action": "REMOVE", "price_micros": 500000,
                      "size_micros": 1}],
        )
    with pytest.raises(sqlite3.IntegrityError):
        fx.insert_book_delta_detail(
            db, event,
            changes=[{"book_side": "BID", "action": "ADD", "price_micros": 500000,
                      "size_micros": 0}],
        )


def test_trade_and_fill_numeric_checks(db, seeded):
    trade_event = "evt_trade_check"
    fx.insert_envelope(
        db, trade_event, "trade", market_id=seeded["market_id"],
        token_id=seeded["token_yes"], accounting_unit="pUSD",
    )
    for kwargs in ({"price_micros": 1_000_001}, {"size_micros": 0}):
        with pytest.raises(sqlite3.IntegrityError):
            fx.insert_trade_detail(db, trade_event, **kwargs)

    for index, kwargs in enumerate(
        [
            {"size_micros": 0},
            {"notional_micros": -1},
            {"fee_amount_micros": -1},
            {"rate_micros": 1_000_001},
        ]
    ):
        with pytest.raises(sqlite3.IntegrityError):
            fx.insert_fill(
                db, seeded["order_id"], seeded["book_event"],
                fill_id=f"fill_num_{index}", fill_index=10 + index, **kwargs,
            )


def test_order_and_estimate_checks(db, seeded):
    with pytest.raises(sqlite3.IntegrityError):
        fx.insert_order(
            db, seeded["experiment_id"], seeded["market_id"], seeded["token_yes"],
            seeded["book_event"], order_id="ord_check_1",
            requested_size_micros=0,
        )
    with pytest.raises(sqlite3.IntegrityError):
        fx.insert_order(
            db, seeded["experiment_id"], seeded["market_id"], seeded["token_yes"],
            seeded["book_event"], order_id="ord_check_2",
            limit_price_micros=1_000_001,
        )
    with pytest.raises(sqlite3.IntegrityError):
        fx.insert_order(
            db, seeded["experiment_id"], seeded["market_id"], seeded["token_yes"],
            seeded["book_event"], order_id="ord_check_3",
            status="rejected", rejection_reason=None,
        )
    estimate_order = fx.insert_order(
        db, seeded["experiment_id"], seeded["market_id"], seeded["token_yes"],
        seeded["book_event"], order_id="ord_est_check",
        idempotency_key="idem-est-check",
    )
    with pytest.raises(sqlite3.IntegrityError):
        fx.insert_estimate(
            db, estimate_order, seeded["book_event"],
            estimate_id="est_check_1", vwap_micros=None,
        )
    with pytest.raises(sqlite3.IntegrityError):
        fx.insert_estimate(
            db, estimate_order, seeded["book_event"],
            estimate_id="est_check_2", status="rejected",
            executable_size_micros=1, vwap_micros=None,
            fee_calculation=None, rejection_reason="stale_book",
        )


def test_portfolio_snapshot_checks(db, seeded):
    with pytest.raises(sqlite3.IntegrityError):
        fx.insert_snapshot(
            db, seeded["experiment_id"], snapshot_id="snap_bad_equity",
            cash_micros=100, positions_value_micros=100, equity_micros=999,
        )
    with pytest.raises(sqlite3.IntegrityError):
        fx.insert_snapshot(
            db, seeded["experiment_id"], snapshot_id="snap_negative_cash",
            cash_micros=-1, positions_value_micros=0,
        )


def test_experiment_metrics_require_exactly_one_value(db, seeded):
    with pytest.raises(sqlite3.IntegrityError):
        fx.insert_metric(db, seeded["experiment_id"], metric_key="both",
                         value_micros=1, value_real=1.0)
    with pytest.raises(sqlite3.IntegrityError):
        fx.insert_metric(db, seeded["experiment_id"], metric_key="none",
                         value_micros=None, value_real=None)
    fx.insert_metric(db, seeded["experiment_id"], metric_key="valid_real",
                     value_micros=None, value_real=1.0)


def test_ledger_posting_shape_checks(db, seeded):
    with pytest.raises(sqlite3.IntegrityError):
        fx.insert_ledger_transaction(
            db, "tx_shape_1",
            [
                {"account": "POSITION", "amount_micros": 10,
                 "quantity_micros": None, "token_id": seeded["token_yes"]},
                {"account": "CASH", "amount_micros": -10},
            ],
        )
    with pytest.raises(sqlite3.IntegrityError):
        fx.insert_ledger_transaction(
            db, "tx_shape_2",
            [
                {"account": "CASH", "amount_micros": 10, "quantity_micros": 5},
                {"account": "CAPITAL", "amount_micros": -10},
            ],
        )
    with pytest.raises(sqlite3.IntegrityError):
        fx.insert_ledger_transaction(
            db, "tx_shape_3",
            [
                {"account": "POSITION", "amount_micros": 10,
                 "quantity_micros": 0, "token_id": seeded["token_yes"]},
                {"account": "CASH", "amount_micros": -10},
            ],
        )


# ---------------------------------------------------------------------------
# Triggers de type et d'immutabilité
# ---------------------------------------------------------------------------


DETAIL_TRIGGER_CASES = {
    "trade_events": lambda db, s: fx.insert_trade_detail(db, s["book_event"]),
    "trader_activity_events": lambda db, s: fx.insert_activity_detail(
        db, s["book_event"], s["trader_id"]
    ),
    "book_snapshots": lambda db, s: fx.insert_book_snapshot_detail(
        db, s["trade_event"]
    ),
    "book_delta_changes": lambda db, s: fx.insert_book_delta_detail(
        db, s["book_event"]
    ),
    "market_metadata_events": lambda db, s: fx.insert_metadata_detail(
        db, s["book_event"]
    ),
    "market_resolution_events": lambda db, s: fx.insert_resolution_detail(
        db, s["book_event"]
    ),
    "connection_events": lambda db, s: fx.insert_connection_detail(
        db, s["book_event"]
    ),
}


@pytest.mark.parametrize("detail_table", sorted(DETAIL_TRIGGER_CASES))
def test_detail_rows_must_match_the_envelope_type(db, seeded, detail_table):
    with pytest.raises(sqlite3.IntegrityError):
        DETAIL_TRIGGER_CASES[detail_table](db, seeded)


@pytest.mark.parametrize(
    "statement",
    [
        "UPDATE simulated_fills SET price_micros = 1 WHERE fill_id = 'fill_fixture_001'",
        "DELETE FROM simulated_fills WHERE fill_id = 'fill_fixture_001'",
        "UPDATE ledger_transactions SET memo = 'x' WHERE transaction_id = 'tx_probe'",
        "DELETE FROM ledger_transactions WHERE transaction_id = 'tx_probe'",
        "UPDATE ledger_postings SET amount_micros = 1 WHERE transaction_id = 'tx_probe'",
        "DELETE FROM ledger_postings WHERE transaction_id = 'tx_probe'",
    ],
)
def test_accounting_rows_are_immutable(db, seeded, statement):
    fx.insert_ledger_transaction(db, "tx_probe", fx.deposit_postings())
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(statement)


# ---------------------------------------------------------------------------
# Écarts connus entre le schéma déclaré et le comportement observé
# ---------------------------------------------------------------------------


def test_market_events_are_append_only(db, seeded):
    accepted = []

    try:
        db.execute(
            "UPDATE market_events SET accounting_unit = 'USDC' WHERE event_id = ?",
            (seeded["trade_event"],),
        )
        accepted.append("UPDATE market_events")
    except sqlite3.IntegrityError:
        pass

    try:
        db.execute("DELETE FROM trade_events WHERE event_id = ?",
                   (seeded["trade_event"],))
        db.execute("DELETE FROM market_events WHERE event_id = ?",
                   (seeded["trade_event"],))
        accepted.append("DELETE market_events")
    except sqlite3.IntegrityError:
        pass

    assert accepted == []


APPEND_ONLY_EVENT_TABLES = {
    "market_events": "schema_version = '9.9.9'",
    "trade_events": "notes = 'x'",
    "trader_activity_events": "notes = 'x'",
    "book_snapshots": "tick_size_micros = 20000",
    "book_delta_changes": "book_hash_after = 'x'",
    "market_metadata_events": "status = 'closed'",
    "market_resolution_events": "resolution_source = 'fixture://x'",
    "connection_events": "reason = 'x'",
}


@pytest.mark.parametrize("table,assignment", sorted(APPEND_ONLY_EVENT_TABLES.items()))
def test_every_event_table_is_append_only(db, seeded, table, assignment):
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(f"UPDATE {table} SET {assignment}")
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(f"DELETE FROM {table}")


def test_event_token_must_belong_to_its_market(db, seeded):
    with pytest.raises(sqlite3.IntegrityError):
        fx.insert_envelope(
            db, "evt_cross_market", "trade",
            market_id=seeded["market_id"], token_id=seeded["other_token"],
            accounting_unit="pUSD",
            source_timestamp=fx.TS1, received_timestamp=fx.TS1,
        )


def test_fill_book_reference_must_be_a_snapshot(db, seeded):
    with pytest.raises(sqlite3.IntegrityError):
        fx.insert_fill(
            db, seeded["order_id"], seeded["trade_event"],
            fill_id="fill_wrong_book_ref", fill_index=20,
        )


def test_tx_hash_hexadecimal_is_enforced(db, seeded):
    event = "evt_tx_hash_check"
    fx.insert_envelope(
        db, event, "trade", market_id=seeded["market_id"],
        token_id=seeded["token_yes"], accounting_unit="pUSD",
    )
    with pytest.raises(sqlite3.IntegrityError):
        fx.insert_trade_detail(db, event, tx_hash="0x" + "z" * 64)


# ---------------------------------------------------------------------------
# Corrections A5 : chemins indirects et invariants ajoutés
# ---------------------------------------------------------------------------


def test_replace_cannot_bypass_event_append_only(db, seeded):
    """INSERT OR REPLACE supprime puis réinsère : le trigger DELETE doit agir."""
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            "INSERT OR REPLACE INTO market_events SELECT * FROM market_events "
            "WHERE event_id = ?",
            (seeded["trade_event"],),
        )
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            "INSERT OR REPLACE INTO trade_events SELECT * FROM trade_events "
            "WHERE event_id = ?",
            (seeded["trade_event"],),
        )


def test_order_token_must_belong_to_its_market(db, seeded):
    with pytest.raises(sqlite3.IntegrityError):
        fx.insert_order(
            db, seeded["experiment_id"], seeded["market_id"],
            seeded["other_token"], None, order_id="ord_cross_market",
            idempotency_key="idem-cross-market", status="rejected",
            rejection_reason="invalid_order",
            simulated_arrival_timestamp=None,
        )


def test_order_book_snapshot_must_match_market_and_token(db, seeded):
    other_book = "evt_book_other_market"
    fx.insert_envelope(
        db, other_book, "book_snapshot", market_id=seeded["other_market_id"],
        token_id=seeded["other_token"],
    )
    fx.insert_book_snapshot_detail(db, other_book)
    with pytest.raises(sqlite3.IntegrityError):
        fx.insert_order(
            db, seeded["experiment_id"], seeded["market_id"], seeded["token_yes"],
            other_book, order_id="ord_wrong_book", idempotency_key="idem-wrong-book",
        )


def test_estimate_book_snapshot_must_be_a_snapshot_of_the_order(db, seeded):
    order_id = fx.insert_order(
        db, seeded["experiment_id"], seeded["market_id"], seeded["token_yes"],
        seeded["book_event"], order_id="ord_est_book", idempotency_key="idem-est-book",
    )
    with pytest.raises(sqlite3.IntegrityError):
        fx.insert_estimate(
            db, order_id, seeded["trade_event"], estimate_id="est_wrong_book",
        )


def test_estimate_intent_must_match_its_order(db, seeded):
    order_id = fx.insert_order(
        db, seeded["experiment_id"], seeded["market_id"], seeded["token_yes"],
        seeded["book_event"], order_id="ord_intent_a", intent_id="intent_a",
        idempotency_key="idem-intent-a",
    )
    with pytest.raises(sqlite3.IntegrityError):
        fx.insert_estimate(
            db, order_id, seeded["book_event"], estimate_id="est_intent_b",
            intent_id="intent_b",
        )


def test_an_intent_cannot_be_reused_by_another_order(db, seeded):
    fx.insert_order(
        db, seeded["experiment_id"], seeded["market_id"], seeded["token_yes"],
        seeded["book_event"], order_id="ord_intent_first",
        intent_id="intent_shared", idempotency_key="idem-intent-first",
    )
    with pytest.raises(sqlite3.IntegrityError):
        fx.insert_order(
            db, seeded["experiment_id"], seeded["market_id"], seeded["token_yes"],
            seeded["book_event"], order_id="ord_intent_second",
            intent_id="intent_shared", idempotency_key="idem-intent-second",
        )


def test_book_delta_hashes_must_agree_within_an_event(db, seeded):
    event = "evt_delta_hash_check"
    fx.insert_envelope(
        db, event, "book_delta", market_id=seeded["market_id"],
        token_id=seeded["token_yes"],
    )
    fx.insert_book_delta_detail(
        db, event,
        changes=[{"book_side": "BID", "action": "ADD", "price_micros": 490000,
                  "size_micros": 10}],
        book_hash_before="a" * 16, book_hash_after="b" * 16,
    )
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            "INSERT INTO book_delta_changes(event_id, change_index, book_side, action, "
            "price_micros, size_micros, book_hash_before, book_hash_after) "
            "VALUES (?, 1, 'BID', 'ADD', 480000, 10, ?, ?)",
            (event, "c" * 16, "b" * 16),
        )


def test_optional_trade_and_intent_fields_are_persisted(db, seeded):
    event = "evt_optional_fields"
    fx.insert_envelope(
        db, event, "trade", market_id=seeded["market_id"],
        token_id=seeded["token_yes"], accounting_unit="pUSD",
    )
    fx.insert_trade_detail(db, event, notes="note de trade")
    assert db.execute(
        "SELECT notes FROM trade_events WHERE event_id = ?", (event,)
    ).fetchone()[0] == "note de trade"

    activity = "evt_optional_activity"
    fx.insert_envelope(
        db, activity, "trader_activity", market_id=seeded["market_id"],
        token_id=seeded["token_yes"], accounting_unit="pUSD",
    )
    fx.insert_activity_detail(
        db, activity, seeded["trader_id"], notes="note d'activité",
    )
    assert db.execute(
        "SELECT notes FROM trader_activity_events WHERE event_id = ?", (activity,)
    ).fetchone()[0] == "note d'activité"

    db.execute(
        "UPDATE simulated_orders SET rationale = ?, tags_json = ? WHERE order_id = ?",
        ("raison", '["test"]', seeded["order_id"]),
    )
    row = db.execute(
        "SELECT rationale, tags_json FROM simulated_orders WHERE order_id = ?",
        (seeded["order_id"],),
    ).fetchone()
    assert row["rationale"] == "raison"
    assert row["tags_json"] == '["test"]'


def test_experiment_random_seed_must_match_execution_assumptions(db, seeded):
    with pytest.raises(sqlite3.IntegrityError):
        fx.insert_experiment(
            db, seeded["strategy_id"], seeded["strategy_version"],
            experiment_id="exp_seed_mismatch", random_seed=1,
            assumptions_random_seed=2,
        )
    fx.insert_experiment(
        db, seeded["strategy_id"], seeded["strategy_version"],
        experiment_id="exp_seed_ok", random_seed=1, assumptions_random_seed=1,
    )


def test_experiment_requires_conversion_if_presentation_differs(db, seeded):
    with pytest.raises(sqlite3.IntegrityError):
        fx.insert_experiment(
            db, seeded["strategy_id"], seeded["strategy_version"],
            experiment_id="exp_presentation_no_conversion",
            presentation_currency="USD", presentation_conversion_json=None,
        )
    fx.insert_experiment(
        db, seeded["strategy_id"], seeded["strategy_version"],
        experiment_id="exp_presentation_conversion",
        presentation_currency="USD",
        presentation_conversion_json='{"source":"fixture"}',
    )


def test_metadata_outcomes_must_be_unique(db, seeded):
    event = "evt_metadata_dup_token"
    fx.insert_envelope(db, event, "market_metadata", market_id=seeded["market_id"])
    with pytest.raises(sqlite3.IntegrityError):
        fx.insert_metadata_detail(
            db, event,
            outcomes=[
                {"token_id": "tok_dup", "outcome_label": "Yes", "outcome_index": 0},
                {"token_id": "tok_dup", "outcome_label": "No", "outcome_index": 1},
            ],
        )
    event = "evt_metadata_dup_index"
    fx.insert_envelope(db, event, "market_metadata", market_id=seeded["market_id"])
    with pytest.raises(sqlite3.IntegrityError):
        fx.insert_metadata_detail(
            db, event,
            outcomes=[
                {"token_id": "tok_a", "outcome_label": "Yes", "outcome_index": 0},
                {"token_id": "tok_b", "outcome_label": "No", "outcome_index": 0},
            ],
        )


def test_resolution_requires_conversion_when_assets_differ(db, seeded):
    event = "evt_resolution_no_conversion"
    fx.insert_envelope(db, event, "market_resolution", market_id=seeded["market_id"])
    with pytest.raises(sqlite3.IntegrityError):
        fx.insert_resolution_detail(db, event, conversion_rule_json=None)
    fx.insert_resolution_detail(db, event, conversion_rule_json='{"source":"fixture"}')


def test_resolution_winning_token_must_belong_to_the_market(db, seeded):
    event = "evt_resolution_cross_market"
    fx.insert_envelope(db, event, "market_resolution", market_id=seeded["market_id"])
    with pytest.raises(sqlite3.IntegrityError):
        fx.insert_resolution_detail(
            db, event, winning_token_id=seeded["other_token"],
        )
