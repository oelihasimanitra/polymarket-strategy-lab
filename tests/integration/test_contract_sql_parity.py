"""Parité entre les contrats JSON et le schéma SQL.

Trois familles de vérifications :

- les énumérations doivent être identiques de part et d'autre ;
- chaque champ obligatoire d'un contrat persisté doit avoir une colonne, ou un
  stockage explicitement identifié (JSON, table de détail, table référencée) ;
- les règles de chronologie et de nullité des périodes doivent être appliquées
  par le validateur JSON applicatif et par SQLite.

La validation JSON passe par ``validate_contract`` (schéma puis extension
``x-polymarket-chronological-order``), jamais par le validateur standard seul.
"""

from __future__ import annotations

import copy
import json
import sqlite3

import pytest

from labtest import sqlfixtures as fx
from labtest.sqlschema import check_in_values, column_names
from polymarket_lab.validation.contracts import validate_contract


def assert_columns(db, table, columns):
    missing = set(columns) - column_names(db, table)
    assert not missing, f"{table} : colonnes manquantes {sorted(missing)}"


# ---------------------------------------------------------------------------
# Énumérations
# ---------------------------------------------------------------------------


def test_event_type_enum_parity(schemas, db):
    expected = set(schemas["market_event"]["$defs"]["event_type"]["enum"])
    assert check_in_values(db, "market_events", "event_type") == expected
    experiment = set(
        schemas["experiment"]["properties"]["data"]["properties"]["filters"]
        ["properties"]["event_types"]["items"]["enum"]
    )
    assert experiment == expected


def test_source_enum_parity(schemas, db):
    expected = set(schemas["market_event"]["$defs"]["source"]["enum"])
    assert check_in_values(db, "market_events", "source") == expected
    experiment = set(
        schemas["experiment"]["properties"]["data"]["properties"]["filters"]
        ["properties"]["sources"]["items"]["enum"]
    )
    assert experiment == expected


def test_side_enum_parity(schemas, db):
    expected = set(schemas["execution"]["$defs"]["side"]["enum"])
    assert check_in_values(db, "simulated_orders", "side") == expected
    assert check_in_values(db, "trade_events", "taker_side") == expected
    assert check_in_values(db, "trader_activity_events", "side") == expected


def test_activity_type_enum_parity(schemas, db):
    expected = set(
        schemas["market_event"]["$defs"]["trader_activity"]["properties"]
        ["activity_type"]["enum"]
    )
    assert check_in_values(db, "trader_activity_events", "activity_type") == expected


def test_market_status_enum_parity(schemas, db):
    expected = set(
        schemas["market_event"]["$defs"]["market_metadata"]["properties"]["status"]["enum"]
    )
    assert check_in_values(db, "markets", "status") == expected
    assert check_in_values(db, "market_metadata_events", "status") == expected


def test_resolution_status_enum_parity(schemas, db):
    expected = set(
        schemas["market_event"]["$defs"]["market_resolution"]["properties"]
        ["resolution_status"]["enum"]
    )
    assert check_in_values(db, "market_resolution_events", "resolution_status") == expected


def test_connection_status_enum_parity(schemas, db):
    expected = set(
        schemas["market_event"]["$defs"]["connection_status"]["properties"]["status"]["enum"]
    )
    assert check_in_values(db, "connection_events", "status") == expected


def test_rejection_reason_enum_parity(schemas, db):
    expected = set(schemas["execution"]["$defs"]["rejection_reason"]["enum"])
    assert check_in_values(db, "simulated_orders", "rejection_reason") == expected
    assert check_in_values(db, "execution_estimates", "rejection_reason") == expected


def test_rounding_rule_enum_parity(schemas, db):
    expected = set(schemas["fee_schedule"]["properties"]["rounding_rule"]["enum"])
    assert set(schemas["execution"]["$defs"]["rounding_rule"]["enum"]) == expected
    assert check_in_values(db, "fee_schedules", "rounding_rule") == expected


def test_fee_formula_enum_parity(schemas, db):
    expected = set(schemas["fee_schedule"]["properties"]["fee_formula"]["enum"])
    assert set(schemas["execution"]["$defs"]["fee_formula"]["enum"]) == expected
    assert check_in_values(db, "fee_schedules", "fee_formula") == expected
    assert check_in_values(db, "simulated_fills", "fee_formula") == expected


def test_fee_unit_enum_parity(schemas, db):
    expected = set(schemas["execution"]["$defs"]["fee_unit"]["enum"])
    assert set(schemas["fee_schedule"]["properties"]["fee_charge_unit"]["enum"]) == expected
    assert check_in_values(db, "simulated_fills", "fee_unit") == expected
    assert check_in_values(db, "fee_schedules", "fee_charge_unit") == expected


def test_period_and_fee_status_enum_parity(schemas, db):
    experiment = schemas["experiment"]
    period = set(experiment["properties"]["period"]["properties"]["type"]["enum"])
    assert check_in_values(db, "experiments", "period_type") == period

    fee_status = set(experiment["properties"]["fees"]["properties"]["status"]["enum"])
    assert check_in_values(db, "experiments", "fee_status") == fee_status

    status = set(experiment["properties"]["status"]["enum"])
    assert check_in_values(db, "experiments", "status") == status


def test_fee_schedule_enum_parity(schemas, db):
    schedule = schemas["fee_schedule"]["properties"]
    assert check_in_values(db, "fee_schedules", "verification_status") == set(
        schedule["verification_status"]["enum"]
    )
    assert check_in_values(db, "fee_schedules", "scope_type") == set(
        schedule["scope_type"]["enum"]
    )


def test_estimate_status_enum_parity(schemas, db):
    expected = set(
        schemas["execution"]["$defs"]["execution_estimate"]["properties"]["status"]["enum"]
    )
    assert check_in_values(db, "execution_estimates", "status") == expected


def test_result_status_is_a_subset_of_order_status(schemas, db):
    result_status = set(
        schemas["execution"]["$defs"]["execution_result"]["properties"]["status"]["enum"]
    )
    order_status = check_in_values(db, "simulated_orders", "status")
    assert result_status <= order_status
    assert order_status - result_status == {"proposed", "accepted"}


def test_v1_has_only_taker_orders(db):
    assert check_in_values(db, "simulated_orders", "order_type") == {"taker"}


# ---------------------------------------------------------------------------
# Champs du contrat de marché
# ---------------------------------------------------------------------------


def test_market_event_envelope_is_persisted(db):
    assert_columns(
        db,
        "market_events",
        {
            "event_id",
            "schema_version",
            "normalizer_version",
            "event_type",
            "source",
            "source_event_id",
            "source_schema_version",
            "source_timestamp",
            "received_timestamp",
            "market_id",
            "token_id",
            "accounting_unit",
            "sequence_number",
            "quality_flags_json",
            "raw_payload_ref",
            "raw_payload_sha256",
        },
    )


def test_trade_payload_is_persisted(db):
    assert_columns(
        db,
        "trade_events",
        {"event_id", "price_micros", "size_micros", "taker_side", "trader_id",
         "trader_visibility", "tx_hash", "notes"},
    )


def test_book_snapshot_payload_is_persisted(db):
    assert_columns(
        db,
        "book_snapshots",
        {"event_id", "bids_json", "asks_json", "book_hash",
         "book_hash_algorithm", "internal_book_hash", "tick_size_micros"},
    )


def test_book_delta_changes_are_persisted(db):
    assert_columns(
        db,
        "book_delta_changes",
        {"event_id", "change_index", "book_side", "action", "price_micros",
         "size_micros", "book_hash_algorithm", "internal_book_hash_before",
         "internal_book_hash_after"},
    )


def test_trader_activity_payload_is_persisted(db):
    assert_columns(
        db,
        "trader_activity_events",
        {"event_id", "trader_id", "activity_type", "side", "price_micros",
         "size_micros", "tx_hash", "notes"},
    )


def test_market_metadata_payload_is_persisted(db):
    assert_columns(
        db,
        "market_metadata_events",
        {
            "event_id",
            "condition_id",
            "question",
            "slug",
            "category",
            "end_time",
            "status",
            "accepting_orders",
            "tick_size_micros",
            "min_order_size_micros",
            "neg_risk",
            "collateral_asset",
            "collateral_decimals",
            "settlement_asset",
            "outcomes_json",
        },
    )


def test_market_resolution_payload_is_persisted(db):
    assert_columns(
        db,
        "market_resolution_events",
        {
            "event_id",
            "resolution_status",
            "winning_token_id",
            "resolved_at",
            "resolution_source",
            "settlement_asset",
            "payout_per_share_micros",
            "conversion_rule_json",
            "void_rule_ref",
            "notes",
        },
    )


def test_connection_payload_is_persisted(db):
    assert_columns(
        db,
        "connection_events",
        {
            "event_id",
            "stream_id",
            "status",
            "reason",
            "gap_start_timestamp",
            "gap_end_timestamp",
        },
    )


# ---------------------------------------------------------------------------
# Champs des contrats d'exécution
# ---------------------------------------------------------------------------


def test_order_intent_execution_fields_are_persisted(db):
    assert_columns(
        db,
        "simulated_orders",
        {
            "order_id",
            "intent_id",
            "schema_version",
            "experiment_id",
            "market_id",
            "token_id",
            "side",
            "requested_size_micros",
            "limit_price_micros",
            "decision_timestamp",
            "idempotency_key",
            "rationale",
            "tags_json",
            "created_at",
        },
    )
    assert_columns(db, "experiments", {"strategy_id", "strategy_version"})


def test_fill_fields_are_persisted(db):
    assert_columns(
        db,
        "simulated_fills",
        {
            "fill_id",
            "schema_version",
            "order_id",
            "fill_index",
            "level_index",
            "price_micros",
            "size_micros",
            "notional_micros",
            "accounting_unit",
            "fee_calculation_json",
            "book_snapshot_event_id",
            "fill_timestamp",
        },
    )


def test_execution_estimate_fields_are_persisted(db):
    assert_columns(
        db,
        "execution_estimates",
        {
            "estimate_id",
            "order_id",
            "intent_id",
            "schema_version",
            "book_snapshot_event_id",
            "arrival_timestamp",
            "status",
            "accounting_unit",
            "executable_size_micros",
            "unfilled_size_micros",
            "vwap_micros",
            "levels_json",
            "assumptions_json",
            "fee_calculation_json",
            "rejection_reason",
            "created_at",
        },
    )


def test_execution_result_components_exist(db):
    assert_columns(
        db,
        "simulated_orders",
        {"order_id", "status"},
    )
    assert_columns(db, "execution_estimates", {"estimate_id"})
    assert_columns(db, "simulated_fills", {"fill_id"})


# ---------------------------------------------------------------------------
# Champs de configuration
# ---------------------------------------------------------------------------


def test_experiment_fields_are_persisted(db):
    assert_columns(
        db,
        "experiments",
        {
            "experiment_id",
            "schema_version",
            "strategy_id",
            "strategy_version",
            "period_type",
            "start_time",
            "end_time",
            "initial_capital_micros",
            "accounting_unit",
            "presentation_currency",
            "presentation_conversion_json",
            "data_manifest_id",
            "code_version",
            "config_hash",
            "execution_assumptions_json",
            "risk_limits_json",
            "default_fee_schedule_id",
            "fee_status",
            "random_seed",
            "status",
            "created_at",
            "completed_at",
        },
    )
    assert_columns(
        db,
        "data_manifests",
        {"manifest_id", "cutoff_received_timestamp", "filters_json", "source_class"},
    )


def test_fee_schedule_fields_are_persisted(db):
    assert_columns(
        db,
        "fee_schedules",
        {
            "fee_schedule_id",
            "schema_version",
            "verification_status",
            "source_url",
            "source_title",
            "source_retrieved_at",
            "effective_from",
            "effective_to",
            "scope_type",
            "scope_value",
            "scope_evidence_ref",
            "formula_definition_ref",
            "accounting_unit",
            "maker_rate_micros",
            "taker_rate_micros",
            "fee_formula",
            "custom_formula_ref",
            "fee_charge_unit",
            "rounding_rule",
            "rounding_increment_micros",
            "notes",
            "supersedes_fee_schedule_id",
            "created_at",
        },
    )


def test_hypothesis_document_roundtrip(db, seeded, examples):
    document = examples["strategy_hypothesis.json"]
    db.execute(
        "UPDATE hypotheses SET document_json = ? WHERE hypothesis_id = ?",
        (json.dumps(document), seeded["hypothesis_id"]),
    )
    stored = db.execute(
        "SELECT document_json FROM hypotheses WHERE hypothesis_id = ?",
        (seeded["hypothesis_id"],),
    ).fetchone()[0]
    assert json.loads(stored) == document
    assert_columns(
        db, "hypotheses",
        {"hypothesis_id", "trader_id", "schema_version", "document_json", "created_at"},
    )


# ---------------------------------------------------------------------------
# Écarts connus
# ---------------------------------------------------------------------------


def test_intent_id_is_persisted_somewhere(db):
    assert "intent_id" in column_names(db, "simulated_orders")
    assert "intent_id" in column_names(db, "execution_estimates")


def test_execution_tables_carry_schema_version(db):
    assert "schema_version" in column_names(db, "simulated_orders")
    assert "schema_version" in column_names(db, "execution_estimates")


def test_configuration_tables_carry_schema_version(db):
    assert "schema_version" in column_names(db, "experiments")
    assert "schema_version" in column_names(db, "fee_schedules")


def test_book_delta_hashes_are_persisted(db):
    assert_columns(
        db, "book_delta_changes",
        {"book_hash_before", "book_hash_after"},
    )


# ---------------------------------------------------------------------------
# Parité chronologique JSON ↔ SQL (A5-06)
# ---------------------------------------------------------------------------


def _json_accepts(document, schema, validator) -> bool:
    return not validate_contract(document, schema, validator)


def _sql_accepts_fee(db, fee_id: str, effective_from: str, effective_to: str | None) -> bool:
    try:
        fx.insert_fee_schedule(
            db, fee_id, effective_from=effective_from, effective_to=effective_to
        )
    except sqlite3.IntegrityError:
        db.rollback()
        return False
    db.commit()
    return True


def _sql_accepts_experiment(
    db,
    seeded: dict,
    experiment_id: str,
    *,
    period_type: str,
    start_time: str,
    end_time: str | None,
) -> bool:
    try:
        fx.insert_experiment(
            db, seeded["strategy_id"], seeded["strategy_version"],
            experiment_id=experiment_id, period_type=period_type,
            start_time=start_time, end_time=end_time,
            data_manifest_id=None if period_type == "paper_live"
            else seeded["manifest_id"],
        )
    except sqlite3.IntegrityError:
        db.rollback()
        return False
    db.commit()
    return True


def test_fee_schedule_chronology_json_sql_parity(
    db, examples, validators, schemas
):
    db.commit()
    cases = [
        ("valid", fx.TS0, fx.TS1, False),
        ("reversed", fx.TS1, fx.TS0, False),
        ("equal", fx.TS0, fx.TS0, False),
        ("null_end", fx.TS0, None, False),
        ("absent_end", fx.TS0, None, True),
        ("bad_format", "2026-10-01", fx.TS1, False),
    ]
    for name, effective_from, effective_to, absent_end in cases:
        document = copy.deepcopy(examples["fee_schedule.json"])
        document["effective_from"] = effective_from
        if absent_end:
            document.pop("effective_to", None)
        else:
            document["effective_to"] = effective_to
        json_ok = _json_accepts(
            document, schemas["fee_schedule"], validators["fee_schedule"]
        )
        sql_ok = _sql_accepts_fee(
            db, f"fee_chronology_{name}", effective_from, effective_to
        )
        assert json_ok == sql_ok, name


def test_experiment_chronology_json_sql_parity(
    db, seeded, examples, validators, schemas
):
    db.commit()
    cases = [
        ("valid", "research", fx.TS0, fx.TS1),
        ("reversed", "research", fx.TS1, fx.TS0),
        ("equal", "research", fx.TS0, fx.TS0),
        ("null_end", "paper_live", fx.TS0, None),
        ("bad_format", "research", "2026-10-01", fx.TS1),
    ]
    for name, period_type, start_time, end_time in cases:
        document = copy.deepcopy(examples["experiment.json"])
        document["period"]["type"] = period_type
        document["period"]["start_time"] = start_time
        document["period"]["end_time"] = end_time
        if period_type == "paper_live":
            document["data"]["manifest_id"] = None
            document["data"]["cutoff_received_timestamp"] = None
        json_ok = _json_accepts(
            document, schemas["experiment"], validators["experiment"]
        )
        sql_ok = _sql_accepts_experiment(
            db, seeded, f"exp_chronology_{name}",
            period_type=period_type, start_time=start_time, end_time=end_time,
        )
        assert json_ok == sql_ok, name


@pytest.mark.parametrize(
    "period_type", ["research", "validation", "final_test", "paper_live"]
)
def test_experiment_null_end_json_sql_parity_v7(
    db_v7, seeded_v7, examples, validators, schemas, period_type
):
    """0007 aligne le SQL : null interdit hors paper_live, accepté en paper_live."""
    db_v7.commit()
    fx.insert_manifest(db_v7, "manifest_recorded", source_class="recorded")
    db_v7.commit()
    seeded = dict(seeded_v7)
    seeded["manifest_id"] = "manifest_recorded"

    document = copy.deepcopy(examples["experiment.json"])
    document["period"]["type"] = period_type
    document["period"]["start_time"] = fx.TS0
    document["period"]["end_time"] = None
    if period_type == "paper_live":
        document["data"]["manifest_id"] = None
        document["data"]["cutoff_received_timestamp"] = None

    json_ok = _json_accepts(
        document, schemas["experiment"], validators["experiment"]
    )
    sql_ok = _sql_accepts_experiment(
        db_v7, seeded, f"exp_null_end_{period_type}",
        period_type=period_type, start_time=fx.TS0, end_time=None,
    )
    assert json_ok == sql_ok, period_type
    assert json_ok is (period_type == "paper_live")
