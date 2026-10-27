"""Constructeurs de lignes SQL valides pour les tests A5.

Le schéma est strict : chaque colonne NOT NULL et chaque CHECK doivent être
respectés. Ces fonctions évitent de recopier 200 lignes d'INSERT dans chaque
test et rendent les anomalies SQL reproductibles.
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any, Iterable

from polymarket_lab.storage.connection import ConnectionConfig, open_connection

TS0 = "2026-10-01T12:00:00.000000Z"
TS1 = "2026-10-01T12:00:01.000000Z"
TS2 = "2026-10-01T12:00:02.000000Z"
TS3 = "2026-10-01T13:00:00.000000Z"
TS_LATER = "2026-10-02T00:00:00.000000Z"

SHA256_ZERO = "0" * 64
SHA256_CONFIG = "sha256:" + "2" * 64

BIDS = [{"price_micros": 510000, "size_micros": 50000000},
        {"price_micros": 500000, "size_micros": 100000000}]
ASKS = [{"price_micros": 530000, "size_micros": 40000000},
        {"price_micros": 540000, "size_micros": 80000000}]
OUTCOMES = [
    {"token_id": "tok_fixture_yes", "outcome_label": "Yes", "outcome_index": 0},
    {"token_id": "tok_fixture_no", "outcome_label": "No", "outcome_index": 1},
]


def _dumps(value: Any) -> str:
    return json.dumps(value, separators=(",", ":"), ensure_ascii=False)


def execute(conn: sqlite3.Connection, sql: str, params: Iterable[Any] = ()) -> sqlite3.Cursor:
    return conn.execute(sql, tuple(params))


def insert_trader(conn: sqlite3.Connection, trader_id: str = "trader_fixture_a") -> str:
    execute(
        conn,
        """
        INSERT INTO traders(
            trader_id, display_name, public_identifier, identifier_type,
            category, selection_notes, selected_at, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (trader_id, "Trader fictif", f"public:{trader_id}", "profile", "crypto",
         None, TS0, TS0),
    )
    return trader_id


def insert_market(
    conn: sqlite3.Connection,
    market_id: str = "mkt_fixture_001",
    *,
    status: str = "active",
) -> str:
    execute(
        conn,
        """
        INSERT INTO markets(
            market_id, condition_id, slug, question, category, end_time, status,
            accepting_orders, tick_size_micros, min_order_size_micros, neg_risk,
            collateral_asset, collateral_decimals, settlement_asset,
            metadata_json, first_seen_at, last_seen_at, source
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            market_id, f"cond_{market_id}", f"{market_id}-slug", "Marché fictif",
            "crypto", "2026-10-02T00:00:00.000000Z", status, 1, 10000, 1000000,
            0, "pUSD", 6, "USDC", "{}", TS0, TS0, "fixture",
        ),
    )
    return market_id


def insert_token(
    conn: sqlite3.Connection,
    token_id: str,
    market_id: str,
    outcome_label: str,
    outcome_index: int,
) -> str:
    execute(
        conn,
        "INSERT INTO market_tokens(token_id, market_id, outcome_label, outcome_index) "
        "VALUES (?, ?, ?, ?)",
        (token_id, market_id, outcome_label, outcome_index),
    )
    return token_id


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}


def insert_manifest(
    conn: sqlite3.Connection,
    manifest_id: str = "manifest_fixture_001",
    *,
    source_class: str | None = "fixture",
) -> str:
    if {"hash_version", "event_id_algorithm"} <= _columns(conn, "data_manifests"):
        execute(
            conn,
            """
            INSERT INTO data_manifests(
                manifest_id, created_at, cutoff_received_timestamp, filters_json,
                first_source_timestamp, last_source_timestamp, event_count, sha256,
                notes, source_class, hash_version, event_id_algorithm
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (manifest_id, TS0, TS3, _dumps({"sources": ["fixture"]}), TS0, TS2, 7,
             SHA256_ZERO, "Manifeste fictif", source_class,
             "manifest/v2", "event-id/v2"),
        )
        return manifest_id
    execute(
        conn,
        """
        INSERT INTO data_manifests(
            manifest_id, created_at, cutoff_received_timestamp, filters_json,
            first_source_timestamp, last_source_timestamp, event_count, sha256,
            notes, source_class
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (manifest_id, TS0, TS3, _dumps({"sources": ["fixture"]}), TS0, TS2, 7,
         SHA256_ZERO, "Manifeste fictif", source_class),
    )
    return manifest_id


def insert_fee_schedule(
    conn: sqlite3.Connection,
    fee_schedule_id: str = "fee_fixture_001",
    *,
    schema_version: str = "1.2.0",
    verification_status: str = "unverified",
    source_url: str = "https://example.invalid/pending-polymarket-fees",
    scope_type: str = "global",
    scope_evidence_ref: str | None = None,
    fee_formula: str = "linear_min_price_1mp",
    custom_formula_ref: str | None = None,
    maker_rate_micros: int = 0,
    taker_rate_micros: int = 10000,
    effective_from: str = TS0,
    effective_to: str | None = None,
    rounding_rule: str = "half_up_micros",
    rounding_increment_micros: int = 1,
    created_at: str = TS0,
) -> str:
    execute(
        conn,
        """
        INSERT INTO fee_schedules(
            fee_schedule_id, schema_version, verification_status, source_url, source_title,
            source_retrieved_at, effective_from, effective_to, scope_type,
            scope_value, scope_evidence_ref, accounting_unit,
            maker_rate_micros, taker_rate_micros, fee_formula,
            custom_formula_ref, fee_charge_unit, rounding_rule,
            rounding_increment_micros, notes, supersedes_fee_schedule_id, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            fee_schedule_id, schema_version, verification_status, source_url,
            "FICTIF — aucune donnée Polymarket vérifiée", TS0, effective_from,
            effective_to, scope_type, "*", scope_evidence_ref, "pUSD",
            maker_rate_micros, taker_rate_micros, fee_formula,
            custom_formula_ref, "collateral", rounding_rule,
            rounding_increment_micros, "VALEURS FICTIVES", None, created_at,
        ),
    )
    return fee_schedule_id


def insert_hypothesis(
    conn: sqlite3.Connection,
    trader_id: str,
    hypothesis_id: str = "hyp_fixture_001",
    *,
    document: dict[str, Any] | None = None,
) -> str:
    execute(
        conn,
        "INSERT INTO hypotheses(hypothesis_id, trader_id, schema_version, "
        "document_json, created_at) VALUES (?, ?, ?, ?, ?)",
        (
            hypothesis_id, trader_id, "1.0.0",
            _dumps(document if document is not None else {"fixture": True}), TS0,
        ),
    )
    return hypothesis_id


def insert_strategy(
    conn: sqlite3.Connection,
    hypothesis_id: str,
    trader_id: str,
    strategy_id: str = "strat_fixture_001",
    version: str = "0.1.0",
    *,
    status: str = "draft",
) -> tuple[str, str]:
    execute(
        conn,
        """
        INSERT INTO strategies(
            strategy_id, version, trader_id, hypothesis_id, hypothesis_json,
            config_json, parameters_hash, status, created_at, retired_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (strategy_id, version, trader_id, hypothesis_id, "{}", "{}", "hash-fixture",
         status, TS0, None),
    )
    return strategy_id, version


def insert_experiment(
    conn: sqlite3.Connection,
    strategy_id: str,
    strategy_version: str,
    *,
    experiment_id: str = "exp_fixture_001",
    schema_version: str = "1.2.0",
    period_type: str = "research",
    start_time: str = TS0,
    end_time: str | None = TS3,
    data_manifest_id: str | None = "manifest_fixture_001",
    default_fee_schedule_id: str | None = "fee_fixture_001",
    fee_status: str = "unverified",
    random_seed: int = 42,
    assumptions_random_seed: int | None = None,
    presentation_currency: str = "pUSD",
    presentation_conversion_json: str | None = None,
    config_hash: str = SHA256_CONFIG,
    status: str = "planned",
) -> str:
    assumptions = _dumps({"latency_ms": 500,
                          "random_seed": random_seed if assumptions_random_seed is None
                          else assumptions_random_seed,
                          "rounding_increment_micros": 1})
    columns = _columns(conn, "experiments")
    if {"config_hash_version", "experiment_config_json"} <= columns:
        execute(
            conn,
            """
            INSERT INTO experiments(
                experiment_id, schema_version, strategy_id, strategy_version,
                period_type, start_time, end_time, initial_capital_micros,
                accounting_unit, presentation_currency, presentation_conversion_json,
                data_manifest_id, code_version, config_hash, config_hash_version,
                experiment_config_json, execution_assumptions_json, risk_limits_json,
                default_fee_schedule_id, fee_status, random_seed, status,
                created_at, completed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                experiment_id, schema_version, strategy_id, strategy_version,
                period_type, start_time, end_time, 1_000_000_000, "pUSD",
                presentation_currency, presentation_conversion_json,
                data_manifest_id, "git:fixture-0000000", config_hash,
                "config/v2", _dumps({"fixture": True}), assumptions,
                _dumps({"allow_short_positions": False}),
                default_fee_schedule_id, fee_status, random_seed, status, TS0, None,
            ),
        )
        return experiment_id
    execute(
        conn,
        """
        INSERT INTO experiments(
            experiment_id, schema_version, strategy_id, strategy_version,
            period_type, start_time, end_time, initial_capital_micros,
            accounting_unit, presentation_currency, presentation_conversion_json,
            data_manifest_id, code_version, config_hash,
            execution_assumptions_json, risk_limits_json,
            default_fee_schedule_id, fee_status, random_seed, status,
            created_at, completed_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            experiment_id, schema_version, strategy_id, strategy_version,
            period_type, start_time, end_time, 1_000_000_000, "pUSD",
            presentation_currency, presentation_conversion_json,
            data_manifest_id, "git:fixture-0000000", config_hash,
            assumptions,
            _dumps({"allow_short_positions": False}),
            default_fee_schedule_id, fee_status, random_seed, status, TS0, None,
        ),
    )
    return experiment_id


def insert_envelope(
    conn: sqlite3.Connection,
    event_id: str,
    event_type: str,
    *,
    source: str = "fixture",
    source_event_id: str | None = None,
    market_id: str | None = None,
    token_id: str | None = None,
    accounting_unit: str | None = None,
    source_timestamp: str = TS0,
    received_timestamp: str = TS0,
    quality_flags: list[str] | None = None,
    raw_payload_ref: str | None = None,
    raw_payload_sha256: str | None = None,
    normalizer_version: str | None = "1.1.0",
) -> str:
    execute(
        conn,
        """
        INSERT INTO market_events(
            event_id, schema_version, normalizer_version, event_type, source,
            source_event_id, source_schema_version, source_timestamp,
            received_timestamp, received_monotonic_ns, ingested_at, market_id,
            token_id, accounting_unit, sequence_number, quality_flags_json,
            raw_payload_ref, raw_payload_sha256
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            event_id, "1.1.0", normalizer_version, event_type, source,
            source_event_id or f"src-{event_id}", "fixture-v1",
            source_timestamp, received_timestamp, None, received_timestamp,
            market_id, token_id, accounting_unit, None,
            _dumps(quality_flags if quality_flags is not None else ["fixture"]),
            raw_payload_ref, raw_payload_sha256,
        ),
    )
    return event_id


def insert_trade_detail(
    conn: sqlite3.Connection,
    event_id: str,
    *,
    price_micros: int = 530000,
    size_micros: int = 40000000,
    taker_side: str = "BUY",
    trader_id: str | None = None,
    tx_hash: str | None = "0x" + "1" * 64,
    notes: str | None = None,
    trader_visibility: str | None = None,
) -> None:
    visibility = trader_visibility or ("identified" if trader_id is not None else "unknown")
    execute(
        conn,
        "INSERT INTO trade_events(event_id, price_micros, size_micros, taker_side, "
        "trader_id, tx_hash, notes, trader_visibility) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (event_id, price_micros, size_micros, taker_side, trader_id, tx_hash,
         notes, visibility),
    )


def insert_book_snapshot_detail(
    conn: sqlite3.Connection,
    event_id: str,
    *,
    bids: list[dict[str, int]] | None = None,
    asks: list[dict[str, int]] | None = None,
    book_hash: str = "fixture_book_001",
    tick_size_micros: int | None = 10000,
    book_hash_algorithm: str | None = None,
    internal_book_hash: str | None = None,
) -> None:
    execute(
        conn,
        "INSERT INTO book_snapshots(event_id, bids_json, asks_json, book_hash, "
        "tick_size_micros, book_hash_algorithm, internal_book_hash) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (event_id, _dumps(bids if bids is not None else BIDS),
         _dumps(asks if asks is not None else ASKS), book_hash, tick_size_micros,
         book_hash_algorithm, internal_book_hash),
    )


def insert_book_delta_detail(
    conn: sqlite3.Connection,
    event_id: str,
    *,
    changes: list[dict[str, Any]] | None = None,
    book_hash_before: str | None = None,
    book_hash_after: str | None = None,
    book_hash_algorithm: str | None = None,
    internal_book_hash_before: str | None = None,
    internal_book_hash_after: str | None = None,
) -> None:
    default_changes = [
        {"book_side": "ASK", "action": "REPLACE", "price_micros": 530000,
         "size_micros": 30000000},
        {"book_side": "BID", "action": "REMOVE", "price_micros": 500000,
         "size_micros": 0},
    ]
    for index, change in enumerate(changes if changes is not None else default_changes):
        execute(
            conn,
            "INSERT INTO book_delta_changes(event_id, change_index, book_side, action, "
            "price_micros, size_micros, book_hash_before, book_hash_after, "
            "book_hash_algorithm, internal_book_hash_before, internal_book_hash_after) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (event_id, index, change["book_side"], change["action"],
             change["price_micros"], change["size_micros"],
             book_hash_before, book_hash_after, book_hash_algorithm,
             internal_book_hash_before, internal_book_hash_after),
        )


def insert_activity_detail(
    conn: sqlite3.Connection,
    event_id: str,
    trader_id: str,
    *,
    activity_type: str = "TRADE",
    side: str | None = "BUY",
    price_micros: int | None = 530000,
    size_micros: int | None = 40000000,
    tx_hash: str | None = "0x" + "1" * 64,
    notes: str | None = None,
) -> None:
    execute(
        conn,
        """
        INSERT INTO trader_activity_events(
            event_id, trader_id, activity_type, side, price_micros, size_micros,
            tx_hash, notes
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (event_id, trader_id, activity_type, side, price_micros, size_micros,
         tx_hash, notes),
    )


def insert_metadata_detail(
    conn: sqlite3.Connection,
    event_id: str,
    *,
    status: str = "active",
    collateral_asset: str = "pUSD",
    collateral_decimals: int = 6,
    outcomes: list[dict[str, Any]] | None = None,
) -> None:
    execute(
        conn,
        """
        INSERT INTO market_metadata_events(
            event_id, condition_id, question, slug, category, end_time, status,
            accepting_orders, tick_size_micros, min_order_size_micros, neg_risk,
            collateral_asset, collateral_decimals, settlement_asset, outcomes_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            event_id, "0x" + "1" * 64, "Marché fictif", "marche-fictif", "crypto",
            "2026-10-02T00:00:00.000000Z", status, 1, 10000, 1000000, 0,
            collateral_asset, collateral_decimals, "USDC",
            _dumps(outcomes if outcomes is not None else OUTCOMES),
        ),
    )


def insert_resolution_detail(
    conn: sqlite3.Connection,
    event_id: str,
    *,
    resolution_status: str = "RESOLVED",
    winning_token_id: str | None = "tok_fixture_yes",
    settlement_asset: str | None = "USDC",
    payout_per_share_micros: int | None = 1000000,
    conversion_rule_json: str | None = "{}",
    void_rule_ref: str | None = None,
) -> None:
    execute(
        conn,
        """
        INSERT INTO market_resolution_events(
            event_id, resolution_status, winning_token_id, resolved_at,
            resolution_source, settlement_asset, payout_per_share_micros,
            conversion_rule_json, void_rule_ref, notes
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (event_id, resolution_status, winning_token_id, TS2, "fixture://resolution",
         settlement_asset, payout_per_share_micros, conversion_rule_json,
         void_rule_ref, "Résolution fictive"),
    )


def insert_connection_detail(
    conn: sqlite3.Connection,
    event_id: str,
    *,
    stream_id: str = "fixture_stream_001",
    status: str = "DISCONNECTED",
    gap_start_timestamp: str | None = TS0,
    gap_end_timestamp: str | None = TS2,
) -> None:
    execute(
        conn,
        "INSERT INTO connection_events(event_id, stream_id, status, reason, "
        "gap_start_timestamp, gap_end_timestamp) VALUES (?, ?, ?, ?, ?, ?)",
        (event_id, stream_id, status, "Test de coupure fictif",
         gap_start_timestamp, gap_end_timestamp),
    )


def insert_order(
    conn: sqlite3.Connection,
    experiment_id: str,
    market_id: str,
    token_id: str,
    book_snapshot_event_id: str,
    *,
    order_id: str = "ord_fixture_001",
    intent_id: str | None = None,
    idempotency_key: str = "idem-order-fixture-001",
    side: str = "BUY",
    requested_size_micros: int = 100000000,
    limit_price_micros: int = 550000,
    status: str = "accepted",
    rejection_reason: str | None = None,
    decision_timestamp: str = TS1,
    simulated_arrival_timestamp: str | None = TS1,
    accounting_unit: str = "pUSD",
) -> str:
    execute(
        conn,
        """
        INSERT INTO simulated_orders(
            order_id, intent_id, idempotency_key, experiment_id, market_id,
            token_id, order_type, side, requested_size_micros,
            limit_price_micros, status, rejection_reason, decision_timestamp,
            simulated_arrival_timestamp, book_snapshot_event_id, assumptions_json,
            accounting_unit, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            order_id, intent_id if intent_id is not None else order_id,
            idempotency_key, experiment_id, market_id, token_id,
            "taker", side, requested_size_micros, limit_price_micros, status,
            rejection_reason, decision_timestamp, simulated_arrival_timestamp,
            book_snapshot_event_id, "{}", accounting_unit, TS1,
        ),
    )
    return order_id


def insert_estimate(
    conn: sqlite3.Connection,
    order_id: str,
    book_snapshot_event_id: str,
    *,
    estimate_id: str = "est_fixture_001",
    intent_id: str | None = None,
    status: str = "accepted",
    arrival_timestamp: str = TS1,
    accounting_unit: str = "pUSD",
    executable_size_micros: int = 100000000,
    unfilled_size_micros: int = 0,
    vwap_micros: int | None = 536000,
    levels: list[dict[str, Any]] | None = None,
    fee_calculation: dict[str, Any] | None = None,
    rejection_reason: str | None = None,
) -> str:
    default_levels = [
        {"level_index": 0, "price_micros": 530000, "available_size_micros": 40000000,
         "consumed_size_micros": 40000000, "excluded_size_micros": 0},
        {"level_index": 1, "price_micros": 540000, "available_size_micros": 80000000,
         "consumed_size_micros": 60000000, "excluded_size_micros": 0},
    ]
    default_fee = {
        "fee_schedule_id": "fee_fixture_001",
        "fee_formula": "linear_min_price_1mp",
        "rate_micros": 10000,
        "fee_unit": "collateral",
        "fee_amount_micros": 464000,
        "rounding_rule": "half_up_micros",
    }
    if intent_id is None:
        row = conn.execute(
            "SELECT intent_id FROM simulated_orders WHERE order_id = ?", (order_id,)
        ).fetchone()
        intent_id = row[0] if row is not None else order_id
    execute(
        conn,
        """
        INSERT INTO execution_estimates(
            estimate_id, order_id, intent_id, book_snapshot_event_id,
            arrival_timestamp, status, accounting_unit, executable_size_micros,
            unfilled_size_micros, vwap_micros, levels_json, assumptions_json,
            fee_calculation_json, rejection_reason, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            estimate_id, order_id, intent_id, book_snapshot_event_id,
            arrival_timestamp,
            status, accounting_unit, executable_size_micros, unfilled_size_micros,
            vwap_micros,
            _dumps(levels if levels is not None else default_levels),
            "{}",
            _dumps(fee_calculation if fee_calculation is not None else default_fee),
            rejection_reason, TS1,
        ),
    )
    return estimate_id


def insert_fill(
    conn: sqlite3.Connection,
    order_id: str,
    book_snapshot_event_id: str,
    *,
    fill_id: str = "fill_fixture_001",
    fill_index: int = 0,
    level_index: int = 0,
    price_micros: int = 530000,
    size_micros: int = 40000000,
    notional_micros: int = 21200000,
    fee_schedule_id: str = "fee_fixture_001",
    fee_formula: str = "linear_min_price_1mp",
    rate_micros: int = 10000,
    fee_unit: str = "collateral",
    fee_amount_micros: int = 188000,
    fee_calculation: dict[str, Any] | None = None,
    accounting_unit: str = "pUSD",
    fill_timestamp: str = TS1,
) -> str:
    default_fee = {
        "fee_schedule_id": fee_schedule_id,
        "fee_formula": fee_formula,
        "rate_micros": rate_micros,
        "fee_unit": fee_unit,
        "fee_amount_micros": fee_amount_micros,
        "rounding_rule": "half_up_micros",
    }
    execute(
        conn,
        """
        INSERT INTO simulated_fills(
            fill_id, order_id, fill_index, level_index, price_micros, size_micros,
            notional_micros, fee_schedule_id, fee_formula, rate_micros, fee_unit,
            fee_amount_micros, fee_calculation_json, accounting_unit,
            book_snapshot_event_id, fill_timestamp, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            fill_id, order_id, fill_index, level_index, price_micros, size_micros,
            notional_micros, fee_schedule_id, fee_formula, rate_micros, fee_unit,
            fee_amount_micros,
            _dumps(fee_calculation if fee_calculation is not None else default_fee),
            accounting_unit, book_snapshot_event_id, fill_timestamp, TS1,
        ),
    )
    return fill_id


def insert_ledger_transaction(
    conn: sqlite3.Connection,
    transaction_id: str,
    postings: list[dict[str, Any]],
    *,
    experiment_id: str = "exp_fixture_001",
    kind: str = "fill",
    ref_type: str = "fill",
    ref_id: str | None = None,
    idempotency_key: str | None = None,
    occurred_at: str = TS1,
    memo: str = "",
) -> str:
    execute(
        conn,
        """
        INSERT INTO ledger_transactions(
            transaction_id, experiment_id, occurred_at, kind, ref_type, ref_id,
            idempotency_key, memo, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            transaction_id, experiment_id, occurred_at, kind, ref_type,
            ref_id or transaction_id, idempotency_key or f"idem:{transaction_id}",
            memo, TS1,
        ),
    )
    for posting in postings:
        execute(
            conn,
            """
            INSERT INTO ledger_postings(
                transaction_id, account, token_id, amount_micros,
                quantity_micros, accounting_unit
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                transaction_id, posting["account"], posting.get("token_id"),
                posting["amount_micros"], posting.get("quantity_micros"),
                posting.get("accounting_unit", "pUSD"),
            ),
        )
    return transaction_id


def open_second_connection(path: Any) -> sqlite3.Connection:
    return open_connection(ConnectionConfig(path))


def deposit_postings(amount_micros: int = 1_000_000_000) -> list[dict[str, Any]]:
    return [
        {"account": "CASH", "amount_micros": amount_micros},
        {"account": "CAPITAL", "amount_micros": -amount_micros},
    ]


def buy_postings(
    token_id: str = "tok_fixture_yes",
    cost_micros: int = 53_600_000,
    quantity_micros: int = 100_000_000,
    fee_micros: int = 464_000,
) -> list[dict[str, Any]]:
    return [
        {"account": "POSITION", "token_id": token_id, "amount_micros": cost_micros,
         "quantity_micros": quantity_micros},
        {"account": "CASH", "amount_micros": -cost_micros},
        {"account": "FEES", "amount_micros": fee_micros},
        {"account": "CASH", "amount_micros": -fee_micros},
    ]


def sell_postings(
    token_id: str = "tok_fixture_yes",
    cost_micros: int = 53_600_000,
    quantity_micros: int = 100_000_000,
    proceeds_micros: int = 60_000_000,
    realized_pnl_micros: int = -6_400_000,
    fee_micros: int = 400_000,
) -> list[dict[str, Any]]:
    return [
        {"account": "POSITION", "token_id": token_id, "amount_micros": -cost_micros,
         "quantity_micros": -quantity_micros},
        {"account": "CASH", "amount_micros": proceeds_micros},
        {"account": "REALIZED_PNL", "amount_micros": realized_pnl_micros},
        {"account": "FEES", "amount_micros": fee_micros},
        {"account": "CASH", "amount_micros": -fee_micros},
    ]


def settlement_win_postings(
    token_id: str = "tok_fixture_yes",
    cost_micros: int = 53_600_000,
    quantity_micros: int = 100_000_000,
    payout_micros: int = 100_000_000,
    realized_pnl_micros: int = -46_400_000,
) -> list[dict[str, Any]]:
    return [
        {"account": "POSITION", "token_id": token_id, "amount_micros": -cost_micros,
         "quantity_micros": -quantity_micros},
        {"account": "CASH", "amount_micros": payout_micros},
        {"account": "REALIZED_PNL", "amount_micros": realized_pnl_micros},
    ]


def settlement_lose_postings(
    token_id: str = "tok_fixture_yes",
    cost_micros: int = 53_600_000,
    quantity_micros: int = 100_000_000,
) -> list[dict[str, Any]]:
    return [
        {"account": "POSITION", "token_id": token_id, "amount_micros": -cost_micros,
         "quantity_micros": -quantity_micros},
        {"account": "REALIZED_PNL", "amount_micros": cost_micros},
    ]


def negate_postings(postings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    negated: list[dict[str, Any]] = []
    for posting in postings:
        item = dict(posting)
        item["amount_micros"] = -posting["amount_micros"]
        if posting.get("quantity_micros") is not None:
            item["quantity_micros"] = -posting["quantity_micros"]
        negated.append(item)
    return negated


def insert_snapshot(
    conn: sqlite3.Connection,
    experiment_id: str,
    *,
    snapshot_id: str = "snap_fixture_001",
    as_of_timestamp: str = TS1,
    cash_micros: int = 1_000_000_000,
    positions_value_micros: int | None = 0,
    equity_micros: int | None = None,
    realized_pnl_micros: int = 0,
    unrealized_pnl_micros: int | None = 0,
    fees_paid_micros: int = 0,
    valuation_method: str = "executable_bid_book",
    data_quality_status: str = "complete",
    created_at: str = TS1,
) -> str:
    execute(
        conn,
        """
        INSERT INTO portfolio_snapshots(
            snapshot_id, experiment_id, as_of_timestamp, cash_micros,
            positions_value_micros, equity_micros, realized_pnl_micros,
            unrealized_pnl_micros, fees_paid_micros, accounting_unit,
            valuation_method, data_quality_status, metrics_json, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            snapshot_id, experiment_id, as_of_timestamp, cash_micros,
            positions_value_micros,
            equity_micros if equity_micros is not None
            else (None if positions_value_micros is None
                  else cash_micros + positions_value_micros),
            realized_pnl_micros, unrealized_pnl_micros, fees_paid_micros,
            "pUSD", valuation_method, data_quality_status, "{}", created_at,
        ),
    )
    return snapshot_id


def insert_incident(
    conn: sqlite3.Connection,
    *,
    incident_id: str = "inc_fixture_001",
    incident_type: str = "feed_gap",
    stream_id: str | None = "fixture_stream_001",
    market_id: str | None = None,
    token_id: str | None = None,
    start_time: str = TS0,
    end_time: str | None = TS1,
    detected_at: str = TS1,
    severity: str = "warning",
    details_json: str = "{}",
) -> str:
    execute(
        conn,
        """
        INSERT INTO data_quality_incidents(
            incident_id, incident_type, stream_id, market_id, token_id,
            start_time, end_time, detected_at, severity, details_json, resolved_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (incident_id, incident_type, stream_id, market_id, token_id,
         start_time, end_time, detected_at, severity, details_json, None),
    )
    return incident_id


def insert_metric(
    conn: sqlite3.Connection,
    experiment_id: str,
    *,
    metric_key: str = "sharpe",
    value_micros: int | None = None,
    value_real: float | None = 1.5,
    unit: str = "ratio",
    metrics_version: str = "1",
) -> None:
    execute(
        conn,
        """
        INSERT INTO experiment_metrics(
            experiment_id, metric_key, value_micros, value_real, unit,
            sample_size, metrics_version, computed_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (experiment_id, metric_key, value_micros, value_real, unit, 10,
         metrics_version, TS1),
    )


def seed_basic(conn: sqlite3.Connection) -> dict[str, Any]:
    """Crée un jeu complet mais minimal de lignes valides.

    Retourne les identifiants utilisés par les tests.
    """
    trader_id = insert_trader(conn)
    market_id = insert_market(conn)
    other_market_id = insert_market(conn, "mkt_fixture_002")
    token_yes = insert_token(conn, "tok_fixture_yes", market_id, "Yes", 0)
    token_no = insert_token(conn, "tok_fixture_no", market_id, "No", 1)
    other_token = insert_token(conn, "tok_fixture_other", other_market_id, "Other", 0)
    manifest_id = insert_manifest(conn)
    fee_schedule_id = insert_fee_schedule(conn)
    hypothesis_id = insert_hypothesis(conn, trader_id)
    strategy_id, strategy_version = insert_strategy(conn, hypothesis_id, trader_id)
    experiment_id = insert_experiment(conn, strategy_id, strategy_version)

    book_event = "evt_book_snapshot_001"
    insert_envelope(conn, book_event, "book_snapshot", market_id=market_id,
                    token_id=token_yes)
    insert_book_snapshot_detail(conn, book_event)

    trade_event = "evt_trade_001"
    insert_envelope(conn, trade_event, "trade", market_id=market_id,
                    token_id=token_yes, accounting_unit="pUSD", source_timestamp=TS1,
                    received_timestamp=TS1)
    insert_trade_detail(conn, trade_event, trader_id=trader_id)

    delta_event = "evt_book_delta_001"
    insert_envelope(conn, delta_event, "book_delta", market_id=market_id,
                    token_id=token_yes, source_timestamp=TS1, received_timestamp=TS1)
    insert_book_delta_detail(conn, delta_event)

    activity_event = "evt_activity_001"
    insert_envelope(conn, activity_event, "trader_activity", market_id=market_id,
                    token_id=token_yes, accounting_unit="pUSD", source_timestamp=TS1,
                    received_timestamp=TS1)
    insert_activity_detail(conn, activity_event, trader_id)

    metadata_event = "evt_metadata_001"
    insert_envelope(conn, metadata_event, "market_metadata", market_id=market_id)
    insert_metadata_detail(conn, metadata_event)

    resolution_event = "evt_resolution_001"
    insert_envelope(conn, resolution_event, "market_resolution", market_id=market_id,
                    source_timestamp=TS2, received_timestamp=TS2)
    insert_resolution_detail(conn, resolution_event)

    connection_event = "evt_connection_001"
    insert_envelope(conn, connection_event, "connection_status", source_timestamp=TS0,
                    received_timestamp=TS0)
    insert_connection_detail(conn, connection_event)

    order_id = insert_order(conn, experiment_id, market_id, token_yes, book_event)
    estimate_id = insert_estimate(conn, order_id, book_event)
    fill_id_0 = insert_fill(conn, order_id, book_event, fill_id="fill_fixture_001",
                            fill_index=0, level_index=0, price_micros=530000,
                            size_micros=40000000, notional_micros=21200000,
                            fee_amount_micros=188000)
    fill_id_1 = insert_fill(conn, order_id, book_event, fill_id="fill_fixture_002",
                            fill_index=1, level_index=1, price_micros=540000,
                            size_micros=60000000, notional_micros=32400000,
                            fee_amount_micros=276000)

    return {
        "trader_id": trader_id,
        "market_id": market_id,
        "other_market_id": other_market_id,
        "token_yes": token_yes,
        "token_no": token_no,
        "other_token": other_token,
        "manifest_id": manifest_id,
        "fee_schedule_id": fee_schedule_id,
        "hypothesis_id": hypothesis_id,
        "strategy_id": strategy_id,
        "strategy_version": strategy_version,
        "experiment_id": experiment_id,
        "book_event": book_event,
        "trade_event": trade_event,
        "delta_event": delta_event,
        "activity_event": activity_event,
        "metadata_event": metadata_event,
        "resolution_event": resolution_event,
        "connection_event": connection_event,
        "order_id": order_id,
        "estimate_id": estimate_id,
        "fill_ids": [fill_id_0, fill_id_1],
    }
