"""Tests négatifs des contrats JSON.

Chaque cas part d'un exemple valide, applique une mutation précise et exige un
rejet. Les invariants que JSON Schema standard ne peut pas exprimer sont
vérifiés par l'extension chronologique et le validateur applicatif commun
(``polymarket_lab.validation.contracts``).
"""

from __future__ import annotations

import copy

import pytest

from labtest.contracts import SCHEMA_FILENAMES, chronology_errors

BAD_TIMESTAMPS = [
    "2026-10-01T12:00:00+00:00",
    "2026-10-01T12:00:00.00000Z",
    "2026-10-01T12:00:00.0000000Z",
    "2026-10-01T12:00:00.000000z",
    "2026-10-01T12:00:00Z",
    "2026-10-01 12:00:00.000000Z",
    "2026-10-01",
]


def clone(document):
    return copy.deepcopy(document)


def set_path(document, path, value):
    node = document
    for key in path[:-1]:
        node = node[key]
    node[path[-1]] = value
    return document


def delete_key(document, key):
    del document[key]
    return document


def assert_invalid(validator, document, label=""):
    errors = list(validator.iter_errors(document))
    assert errors, f"Mutation acceptée alors qu'elle devait être rejetée : {label}"


def assert_valid(validator, document, label=""):
    errors = list(validator.iter_errors(document))
    assert not errors, f"Document valide rejeté : {label} -> {[e.message for e in errors]}"


# ---------------------------------------------------------------------------
# Enveloppe market_event
# ---------------------------------------------------------------------------


def test_market_event_required_fields_are_enforced(examples, validators):
    base = examples["market_event_trade.json"]
    schema = validators["market_event"].schema
    for key in schema["required"]:
        document = clone(base)
        delete_key(document, key)
        assert_invalid(validators["market_event"], document, f"required {key}")


def test_market_event_rejects_unknown_top_level_property(examples, validators):
    document = clone(examples["market_event_trade.json"])
    document["unexpected_field"] = 1
    assert_invalid(validators["market_event"], document, "additionalProperties")


def test_trade_event_requires_trade_payload(examples, validators):
    document = clone(examples["market_event_trade.json"])
    delete_key(document, "trade")
    assert_invalid(validators["market_event"], document, "trade sans trade")


def test_non_trade_event_rejects_trade_payload(examples, validators):
    document = clone(examples["market_event_book_snapshot.json"])
    document["trade"] = clone(examples["market_event_trade.json"])["trade"]
    assert_invalid(validators["market_event"], document, "snapshot avec trade")


@pytest.mark.parametrize("field", ["market_id", "token_id", "accounting_unit"])
def test_trade_event_requires_market_token_unit(examples, validators, field):
    document = clone(examples["market_event_trade.json"])
    delete_key(document, field)
    assert_invalid(validators["market_event"], document, field)


@pytest.mark.parametrize(
    "unit", ["1pUSD", "p$USD", "a", "a" * 33, ""],
)
def test_accounting_unit_pattern_is_enforced(examples, validators, unit):
    document = clone(examples["market_event_trade.json"])
    document["accounting_unit"] = unit
    assert_invalid(validators["market_event"], document, f"unit={unit!r}")


@pytest.mark.parametrize(
    "example_name,payload",
    [
        ("market_event_book_snapshot.json", "book_snapshot"),
        ("market_event_book_delta.json", "book_delta"),
    ],
)
def test_book_events_require_market_and_token(examples, validators, example_name, payload):
    for field in ("market_id", "token_id"):
        document = clone(examples[example_name])
        delete_key(document, field)
        assert_invalid(validators["market_event"], document, f"{payload} sans {field}")


@pytest.mark.parametrize(
    "example_name,payload",
    [
        ("market_event_market_metadata.json", "market_metadata"),
        ("market_event_market_resolution.json", "market_resolution"),
    ],
)
def test_metadata_and_resolution_require_market(examples, validators, example_name, payload):
    document = clone(examples[example_name])
    delete_key(document, "market_id")
    assert_invalid(validators["market_event"], document, f"{payload} sans market_id")


def test_connection_event_rejects_book_payload(examples, validators):
    document = clone(examples["market_event_connection_status.json"])
    document["book_snapshot"] = clone(examples["market_event_book_snapshot.json"])[
        "book_snapshot"
    ]
    assert_invalid(validators["market_event"], document, "connection avec book")


@pytest.mark.parametrize("bad_value", BAD_TIMESTAMPS)
def test_market_event_rejects_non_canonical_timestamps(examples, validators, bad_value):
    for field in ("source_timestamp", "received_timestamp"):
        document = clone(examples["market_event_trade.json"])
        document[field] = bad_value
        assert_invalid(validators["market_event"], document, f"{field}={bad_value}")


@pytest.mark.parametrize("bad_value", BAD_TIMESTAMPS)
def test_experiment_rejects_non_canonical_timestamps(examples, validators, bad_value):
    document = clone(examples["experiment.json"])
    document["created_at"] = bad_value
    assert_invalid(validators["experiment"], document, f"created_at={bad_value}")


@pytest.mark.parametrize("bad_value", BAD_TIMESTAMPS)
def test_fee_schedule_rejects_non_canonical_timestamps(examples, validators, bad_value):
    document = clone(examples["fee_schedule.json"])
    document["effective_from"] = bad_value
    assert_invalid(validators["fee_schedule"], document, f"effective_from={bad_value}")


@pytest.mark.parametrize("price", [-1, 1_000_001, 1.5, "530000"])
def test_trade_rejects_invalid_price(examples, validators, price):
    document = clone(examples["market_event_trade.json"])
    document["trade"]["price_micros"] = price
    assert_invalid(validators["market_event"], document, f"price={price!r}")


@pytest.mark.parametrize("size", [0, -1, 1.5])
def test_trade_rejects_invalid_size(examples, validators, size):
    document = clone(examples["market_event_trade.json"])
    document["trade"]["size_micros"] = size
    assert_invalid(validators["market_event"], document, f"size={size!r}")


def test_quality_flags_are_unique_and_lowercase(examples, validators):
    document = clone(examples["market_event_trade.json"])
    document["quality_flags"] = ["fixture", "fixture"]
    assert_invalid(validators["market_event"], document, "flags dupliqués")

    document = clone(examples["market_event_trade.json"])
    document["quality_flags"] = ["Fixture"]
    assert_invalid(validators["market_event"], document, "flag majuscule")


def test_raw_payload_reference_and_hash_are_coupled(examples, validators):
    base = examples["market_event_market_metadata.json"]

    document = clone(base)
    delete_key(document, "raw_payload_sha256")
    assert_invalid(validators["market_event"], document, "ref sans sha")

    document = clone(base)
    delete_key(document, "raw_payload_ref")
    assert_invalid(validators["market_event"], document, "sha sans ref")

    document = clone(base)
    document["raw_payload_sha256"] = "A" * 64
    assert_invalid(validators["market_event"], document, "sha non hex minuscule")

    document = clone(base)
    document["raw_payload_sha256"] = "0" * 63
    assert_invalid(validators["market_event"], document, "sha trop court")


def test_book_snapshot_rejects_invalid_levels(examples, validators):
    base = examples["market_event_book_snapshot.json"]

    document = clone(base)
    document["book_snapshot"]["bids"][0]["size_micros"] = 0
    assert_invalid(validators["market_event"], document, "taille nulle")

    document = clone(base)
    delete_key(document["book_snapshot"]["bids"][0], "price_micros")
    assert_invalid(validators["market_event"], document, "niveau sans prix")

    document = clone(base)
    document["book_snapshot"]["asks"][0]["unknown"] = 1
    assert_invalid(validators["market_event"], document, "niveau non strict")

    document = clone(base)
    document["book_snapshot"]["tick_size_micros"] = 0
    assert_invalid(validators["market_event"], document, "tick size nul")


@pytest.mark.parametrize(
    "action,size,valid",
    [("REMOVE", 1, False), ("ADD", 0, False), ("REPLACE", 0, False)],
)
def test_book_change_action_and_size_are_coherent(examples, validators, action, size, valid):
    document = clone(examples["market_event_book_delta.json"])
    change = document["book_delta"]["changes"][0]
    change["action"] = action
    change["size_micros"] = size
    if valid:
        assert_valid(validators["market_event"], document, f"{action}/{size}")
    else:
        assert_invalid(validators["market_event"], document, f"{action}/{size}")


def test_book_delta_requires_at_least_one_change(examples, validators):
    document = clone(examples["market_event_book_delta.json"])
    document["book_delta"]["changes"] = []
    assert_invalid(validators["market_event"], document, "changes vide")


def test_book_change_rejects_invalid_side(examples, validators):
    document = clone(examples["market_event_book_delta.json"])
    document["book_delta"]["changes"][0]["book_side"] = "MID"
    assert_invalid(validators["market_event"], document, "book_side invalide")


def test_trade_rejects_invalid_side_and_hash(examples, validators):
    document = clone(examples["market_event_trade.json"])
    document["trade"]["taker_side"] = "HOLD"
    assert_invalid(validators["market_event"], document, "taker_side")

    document = clone(examples["market_event_trade.json"])
    document["trade"]["tx_hash"] = "0x1234"
    assert_invalid(validators["market_event"], document, "tx_hash court")


@pytest.mark.parametrize("missing", ["side", "price_micros", "size_micros"])
def test_trader_activity_trade_requires_execution_fields(examples, validators, missing):
    document = clone(examples["market_event_trader_activity.json"])
    delete_key(document["trader_activity"], missing)
    assert_invalid(validators["market_event"], document, f"TRADE sans {missing}")


def test_trader_activity_trade_rejects_null_side(examples, validators):
    document = clone(examples["market_event_trader_activity.json"])
    document["trader_activity"]["side"] = None
    assert_invalid(validators["market_event"], document, "TRADE side null")


def test_trader_activity_rejects_unknown_type(examples, validators):
    document = clone(examples["market_event_trader_activity.json"])
    document["trader_activity"]["activity_type"] = "AIRDROP"
    assert_invalid(validators["market_event"], document, "activity_type inconnu")


def test_non_trade_activity_can_omit_execution_fields(examples, validators):
    document = clone(examples["market_event_trader_activity.json"])
    activity = document["trader_activity"]
    activity["activity_type"] = "REDEEM"
    activity["side"] = None
    activity["price_micros"] = None
    activity["size_micros"] = None
    assert_valid(validators["market_event"], document, "REDEEM sans prix")


def test_market_metadata_requires_two_unique_outcomes(examples, validators):
    base = examples["market_event_market_metadata.json"]

    document = clone(base)
    document["market_metadata"]["outcomes"] = document["market_metadata"]["outcomes"][:1]
    assert_invalid(validators["market_event"], document, "un seul outcome")

    document = clone(base)
    document["market_metadata"]["outcomes"][1] = clone(
        document["market_metadata"]["outcomes"][0]
    )
    assert_invalid(validators["market_event"], document, "outcomes dupliqués")


@pytest.mark.parametrize("decimals", [-1, 19])
def test_market_metadata_rejects_invalid_collateral_decimals(examples, validators, decimals):
    document = clone(examples["market_event_market_metadata.json"])
    document["market_metadata"]["collateral_decimals"] = decimals
    assert_invalid(validators["market_event"], document, f"decimals={decimals}")


def test_market_metadata_requires_collateral_asset(examples, validators):
    document = clone(examples["market_event_market_metadata.json"])
    delete_key(document["market_metadata"], "collateral_asset")
    assert_invalid(validators["market_event"], document, "collateral_asset manquant")


def test_market_metadata_rejects_bad_end_time(examples, validators):
    document = clone(examples["market_event_market_metadata.json"])
    document["market_metadata"]["end_time"] = "2026-10-02T00:00:00+00:00"
    assert_invalid(validators["market_event"], document, "end_time offset")


@pytest.mark.parametrize(
    "field", ["winning_token_id", "settlement_asset", "payout_per_share_micros"]
)
def test_resolved_market_requires_settlement_fields(examples, validators, field):
    document = clone(examples["market_event_market_resolution.json"])
    delete_key(document["market_resolution"], field)
    assert_invalid(validators["market_event"], document, f"RESOLVED sans {field}")


def test_void_market_rejects_winning_token(examples, validators):
    document = clone(examples["market_event_market_resolution.json"])
    document["market_resolution"]["resolution_status"] = "VOID"
    document["market_resolution"]["winning_token_id"] = "tok_fixture_yes"
    assert_invalid(validators["market_event"], document, "VOID avec gagnant")


def test_resolution_rejects_payout_out_of_range(examples, validators):
    document = clone(examples["market_event_market_resolution.json"])
    document["market_resolution"]["payout_per_share_micros"] = 1_000_001
    assert_invalid(validators["market_event"], document, "payout > 1")


def test_resolution_rejects_invalid_conversion_rule(examples, validators):
    document = clone(examples["market_event_market_resolution.json"])
    document["market_resolution"]["conversion_rule"]["rate_micros"] = 0
    assert_invalid(validators["market_event"], document, "rate nul")


def test_connection_status_rejects_invalid_status(examples, validators):
    document = clone(examples["market_event_connection_status.json"])
    document["connection_status"]["status"] = "OK"
    assert_invalid(validators["market_event"], document, "status inconnu")


# ---------------------------------------------------------------------------
# Contrats d'exécution
# ---------------------------------------------------------------------------


EXECUTION_EXAMPLE = {
    "order_intent": "order_intent.json",
    "execution_assumptions": "execution_assumptions.json",
    "execution_estimate": "execution_estimate.json",
    "fill": None,  # premier fill de execution_result
    "execution_result": "execution_result.json",
}


def execution_document(examples, contract_type):
    if contract_type == "fill":
        return clone(examples["execution_result.json"]["fills"][0])
    return clone(examples[EXECUTION_EXAMPLE[contract_type]])


@pytest.mark.parametrize("contract_type", list(EXECUTION_EXAMPLE))
def test_execution_required_fields_are_enforced(examples, validators, contract_type):
    base = execution_document(examples, contract_type)
    required = validators["execution"].schema["$defs"][contract_type]["required"]
    for key in required:
        document = clone(base)
        delete_key(document, key)
        assert_invalid(
            validators["execution"], document, f"{contract_type} sans {key}"
        )


@pytest.mark.parametrize("contract_type", list(EXECUTION_EXAMPLE))
def test_execution_rejects_unknown_property(examples, validators, contract_type):
    document = execution_document(examples, contract_type)
    document["unexpected_field"] = 1
    assert_invalid(validators["execution"], document, contract_type)


def test_execution_rejects_unknown_contract_type(examples, validators):
    document = clone(examples["order_intent.json"])
    document["contract_type"] = "real_order"
    assert_invalid(validators["execution"], document, "contract_type inconnu")


def test_order_intent_is_taker_and_bounded(examples, validators):
    for mutation in (
        {"quantity_micros": 0},
        {"limit_price_micros": 1_000_001},
        {"side": "HOLD"},
        {"idempotency_key": "-bad"},
        {"order_type": "maker"},
    ):
        document = clone(examples["order_intent.json"])
        document.update(mutation)
        assert_invalid(validators["execution"], document, str(mutation))


def test_order_intent_requires_limit_price_even_for_market(examples, validators):
    document = clone(examples["order_intent.json"])
    delete_key(document, "limit_price_micros")
    assert_invalid(validators["execution"], document, "sans limite")


@pytest.mark.parametrize(
    "mutation",
    [
        {"latency_ms": -1},
        {"latency_jitter_ms": -1},
        {"latency_distribution": "poisson"},
        {"liquidity_haircut_bps": 10001},
        {"max_book_age_ms": -1},
        {"max_depth_levels": 0},
        {"random_seed": -1},
        {"rng_implementation": ""},
        {"rounding_rule": "banker"},
    ],
)
def test_execution_assumptions_reject_invalid_values(examples, validators, mutation):
    document = clone(examples["execution_assumptions.json"])
    document.update(mutation)
    assert_invalid(validators["execution"], document, str(mutation))


@pytest.mark.parametrize(
    "mutation",
    [
        {"executable_size_micros": 1},
        {"vwap_micros": 536000},
        {"fee_calculation": {}},
    ],
)
def test_rejected_estimate_must_be_empty_and_explained(examples, validators, mutation):
    document = clone(examples["execution_estimate.json"])
    document["status"] = "rejected"
    document["rejection_reason"] = "stale_book"
    document.update(mutation)
    assert_invalid(validators["execution"], document, str(mutation))


def test_rejected_estimate_requires_rejection_reason(examples, validators):
    document = clone(examples["execution_estimate.json"])
    document["status"] = "rejected"
    document["executable_size_micros"] = 0
    document["vwap_micros"] = None
    document["fee_calculation"] = None
    document["levels"] = []
    delete_key(document, "rejection_reason")
    assert_invalid(validators["execution"], document, "rejet sans motif")


@pytest.mark.parametrize("field", ["vwap_micros", "fee_calculation"])
def test_accepted_estimate_requires_vwap_and_fee(examples, validators, field):
    document = clone(examples["execution_estimate.json"])
    document[field] = None
    assert_invalid(validators["execution"], document, f"accepted sans {field}")


def test_accepted_estimate_requires_levels(examples, validators):
    document = clone(examples["execution_estimate.json"])
    document["levels"] = []
    assert_invalid(validators["execution"], document, "accepted sans niveaux")


@pytest.mark.parametrize("field", ["price_micros", "size_micros", "notional_micros"])
def test_fill_rejects_invalid_quantities(examples, validators, field):
    document = clone(examples["execution_result.json"]["fills"][0])
    if field == "price_micros":
        document[field] = 1_000_001
    else:
        document[field] = -1
    assert_invalid(validators["execution"], document, field)


def test_fill_rejects_invalid_fee(examples, validators):
    document = clone(examples["execution_result.json"]["fills"][0])
    document["fee_calculation"]["rate_micros"] = 1_000_001
    assert_invalid(validators["execution"], document, "taux > 100 %")

    document = clone(examples["execution_result.json"]["fills"][0])
    delete_key(document, "fee_calculation")
    assert_invalid(validators["execution"], document, "sans barème")


@pytest.mark.parametrize("status", ["filled", "partially_filled"])
def test_filled_result_requires_fills(examples, validators, status):
    document = clone(examples["execution_result.json"])
    document["status"] = status
    document["fills"] = []
    assert_invalid(validators["execution"], document, f"{status} sans fill")


@pytest.mark.parametrize("status", ["rejected", "expired"])
def test_rejected_or_expired_result_forbids_fills(examples, validators, status):
    document = clone(examples["execution_result.json"])
    document["status"] = status
    assert_invalid(validators["execution"], document, f"{status} avec fills")


def test_execution_result_requires_estimate(examples, validators):
    document = clone(examples["execution_result.json"])
    delete_key(document, "estimate")
    assert_invalid(validators["execution"], document, "sans estimate")


def test_rejected_result_requires_rejection_reason(examples, validators):
    document = clone(examples["execution_result.json"])
    document["status"] = "rejected"
    document["fills"] = []
    delete_key(document, "rejection_reason")
    document["estimate"]["status"] = "rejected"
    document["estimate"]["executable_size_micros"] = 0
    document["estimate"]["vwap_micros"] = None
    document["estimate"]["fee_calculation"] = None
    document["estimate"]["levels"] = []
    document["estimate"]["rejection_reason"] = "stale_book"
    assert_invalid(validators["execution"], document, "rejet sans motif")


# ---------------------------------------------------------------------------
# Barème de frais
# ---------------------------------------------------------------------------


def test_fee_schedule_required_fields_are_enforced(examples, validators):
    base = examples["fee_schedule.json"]
    for key in validators["fee_schedule"].schema["required"]:
        document = clone(base)
        delete_key(document, key)
        assert_invalid(validators["fee_schedule"], document, f"required {key}")


def test_verified_fee_schedule_requires_https_and_evidence(examples, validators):
    document = clone(examples["fee_schedule.json"])
    document["verification_status"] = "verified"
    document["source_url"] = "http://example.invalid/fees"
    document["scope_evidence_ref"] = "doc://fees"
    assert_invalid(validators["fee_schedule"], document, "verified http")

    document = clone(examples["fee_schedule.json"])
    document["verification_status"] = "verified"
    document["scope_evidence_ref"] = None
    assert_invalid(validators["fee_schedule"], document, "verified global sans preuve")


def test_verified_market_scope_does_not_require_global_evidence(examples, validators):
    document = clone(examples["fee_schedule.json"])
    document["verification_status"] = "verified"
    document["scope_type"] = "market"
    document["scope_value"] = "mkt_fixture_001"
    document["scope_evidence_ref"] = None
    assert_valid(validators["fee_schedule"], document, "verified marché")


def test_fee_formula_semantics(examples, validators):
    document = clone(examples["fee_schedule.json"])
    document["fee_formula"] = "custom"
    document["custom_formula_ref"] = None
    assert_invalid(validators["fee_schedule"], document, "custom sans ref")

    document = clone(examples["fee_schedule.json"])
    document["fee_formula"] = "none"
    assert_invalid(validators["fee_schedule"], document, "none avec taux non nul")


def test_fee_schedule_rate_bounds(examples, validators):
    for rate in (-1, 1_000_001):
        document = clone(examples["fee_schedule.json"])
        document["taker_rate_micros"] = rate
        assert_invalid(validators["fee_schedule"], document, f"taux={rate}")


def test_fee_schedule_rounding_increment_is_positive(examples, validators):
    document = clone(examples["fee_schedule.json"])
    document["rounding_increment_micros"] = 0
    assert_invalid(validators["fee_schedule"], document, "increment 0")


def test_fee_schedule_effective_period_must_be_ordered(examples, schemas):
    document = clone(examples["fee_schedule.json"])
    document["effective_from"] = "2026-10-02T00:00:00.000000Z"
    document["effective_to"] = "2026-10-01T00:00:00.000000Z"
    assert chronology_errors(document, schemas["fee_schedule"]), "période inversée"


def test_fee_schedule_valid_effective_period_has_no_chronology_error(examples, schemas):
    assert chronology_errors(examples["fee_schedule.json"], schemas["fee_schedule"]) == []


def test_fee_schedule_equal_effective_bounds_are_rejected(examples, schemas):
    document = clone(examples["fee_schedule.json"])
    document["effective_to"] = document["effective_from"]
    assert chronology_errors(document, schemas["fee_schedule"]), "bornes égales"


def test_fee_schedule_null_effective_to_is_allowed(examples, schemas, validators):
    document = clone(examples["fee_schedule.json"])
    document["effective_to"] = None
    assert_valid(validators["fee_schedule"], document, "effective_to nul")
    assert chronology_errors(document, schemas["fee_schedule"]) == []


def test_fee_schedule_absent_effective_to_is_allowed(examples, schemas, validators):
    document = clone(examples["fee_schedule.json"])
    del document["effective_to"]
    assert_valid(validators["fee_schedule"], document, "effective_to absent")
    assert chronology_errors(document, schemas["fee_schedule"]) == []


def test_fee_schedule_absent_effective_from_is_rejected(examples, validators):
    document = clone(examples["fee_schedule.json"])
    del document["effective_from"]
    assert_invalid(validators["fee_schedule"], document, "effective_from absent")


def test_fee_schedule_non_canonical_offset_is_rejected(examples, validators):
    document = clone(examples["fee_schedule.json"])
    document["effective_from"] = "2026-10-01T00:00:00.000000+00:00"
    assert_invalid(validators["fee_schedule"], document, "offset non canonique")


def test_fee_schedule_bad_timestamp_format_is_rejected_by_schema(examples, validators):
    document = clone(examples["fee_schedule.json"])
    document["effective_from"] = "2026-10-01"
    assert_invalid(validators["fee_schedule"], document, "format non canonique")


# ---------------------------------------------------------------------------
# Expérience
# ---------------------------------------------------------------------------


def test_experiment_required_fields_are_enforced(examples, validators):
    base = examples["experiment.json"]
    for key in validators["experiment"].schema["required"]:
        document = clone(base)
        delete_key(document, key)
        assert_invalid(validators["experiment"], document, f"required {key}")


@pytest.mark.parametrize("period_type", ["research", "validation", "final_test"])
def test_historical_experiment_requires_end_time(examples, validators, period_type):
    document = clone(examples["experiment.json"])
    document["period"]["type"] = period_type
    document["period"]["end_time"] = None
    assert_invalid(validators["experiment"], document, f"{period_type} sans fin")


def test_paper_live_may_omit_final_manifest(examples, validators):
    document = clone(examples["experiment.json"])
    document["period"]["type"] = "paper_live"
    document["period"]["end_time"] = None
    document["data"]["manifest_id"] = None
    document["data"]["cutoff_received_timestamp"] = None
    assert_valid(validators["experiment"], document, "paper_live sans manifeste")


def test_historical_experiment_requires_manifest_and_cutoff(examples, validators):
    for field in ("manifest_id", "cutoff_received_timestamp"):
        document = clone(examples["experiment.json"])
        document["data"][field] = None
        assert_invalid(validators["experiment"], document, f"research sans {field}")


def test_experiment_forbids_short_positions(examples, validators):
    document = clone(examples["experiment.json"])
    document["risk_limits"]["allow_short_positions"] = True
    assert_invalid(validators["experiment"], document, "short autorisé")


@pytest.mark.parametrize(
    "mutation",
    [
        {"max_position_fraction_bps": 0},
        {"max_position_fraction_bps": 10001},
        {"max_open_positions": 0},
        {"max_exposure_micros": -1},
    ],
)
def test_experiment_rejects_invalid_risk_limits(examples, validators, mutation):
    document = clone(examples["experiment.json"])
    document["risk_limits"].update(mutation)
    assert_invalid(validators["experiment"], document, str(mutation))


@pytest.mark.parametrize("status", ["verified", "provisional"])
def test_verified_fee_status_requires_schedule(examples, validators, status):
    document = clone(examples["experiment.json"])
    document["fees"] = {"status": status, "default_fee_schedule_id": None}
    assert_invalid(validators["experiment"], document, f"{status} sans barème")


def test_unverified_fee_status_may_omit_schedule(examples, validators):
    document = clone(examples["experiment.json"])
    document["fees"] = {"status": "unverified", "default_fee_schedule_id": None}
    assert_valid(validators["experiment"], document, "unverified sans barème")


def test_experiment_rejects_invalid_config_hash_and_capital(examples, validators):
    document = clone(examples["experiment.json"])
    document["config_hash"] = "sha256:xyz"
    assert_invalid(validators["experiment"], document, "hash court")

    document = clone(examples["experiment.json"])
    document["capital"]["initial_micros"] = 0
    assert_invalid(validators["experiment"], document, "capital nul")


def test_experiment_filters_reject_duplicates(examples, validators):
    document = clone(examples["experiment.json"])
    document["data"]["filters"]["sources"] = ["fixture", "fixture"]
    assert_invalid(validators["experiment"], document, "sources dupliquées")

    document = clone(examples["experiment.json"])
    document["data"]["filters"]["event_types"] = ["trade", "trade"]
    assert_invalid(validators["experiment"], document, "event_types dupliqués")


def test_experiment_period_must_be_chronological(examples, schemas):
    document = clone(examples["experiment.json"])
    document["period"]["end_time"] = "2026-10-01T11:00:00.000000Z"
    assert chronology_errors(document, schemas["experiment"]), "fin avant début"


def test_experiment_valid_period_has_no_chronology_error(examples, schemas):
    assert chronology_errors(examples["experiment.json"], schemas["experiment"]) == []


def test_experiment_equal_period_bounds_are_rejected(examples, schemas):
    document = clone(examples["experiment.json"])
    document["period"]["end_time"] = document["period"]["start_time"]
    assert chronology_errors(document, schemas["experiment"]), "bornes égales"


def test_experiment_null_end_time_is_allowed_for_paper_live(
    examples, schemas, validators
):
    document = clone(examples["experiment.json"])
    document["period"]["type"] = "paper_live"
    document["period"]["end_time"] = None
    document["data"]["manifest_id"] = None
    document["data"]["cutoff_received_timestamp"] = None
    assert_valid(validators["experiment"], document, "paper_live sans fin")
    assert chronology_errors(document, schemas["experiment"]) == []


def test_experiment_null_end_time_is_rejected_for_research(examples, validators):
    document = clone(examples["experiment.json"])
    document["period"]["end_time"] = None
    assert_invalid(validators["experiment"], document, "research sans fin")


def test_experiment_absent_end_time_is_rejected_even_for_paper_live(
    examples, validators
):
    document = clone(examples["experiment.json"])
    document["period"]["type"] = "paper_live"
    del document["period"]["end_time"]
    document["data"]["manifest_id"] = None
    document["data"]["cutoff_received_timestamp"] = None
    assert_invalid(validators["experiment"], document, "end_time absent")


def test_experiment_absent_start_time_is_rejected(examples, validators):
    document = clone(examples["experiment.json"])
    del document["period"]["start_time"]
    assert_invalid(validators["experiment"], document, "start_time absent")


def test_experiment_non_canonical_offset_is_rejected(examples, validators):
    document = clone(examples["experiment.json"])
    document["period"]["start_time"] = "2026-10-01T12:00:00.000000+00:00"
    assert_invalid(validators["experiment"], document, "offset non canonique")


def test_experiment_bad_timestamp_format_is_rejected_by_schema(examples, validators):
    document = clone(examples["experiment.json"])
    document["period"]["start_time"] = "2026-10-01"
    assert_invalid(validators["experiment"], document, "format non canonique")


# ---------------------------------------------------------------------------
# Hypothèse de stratégie
# ---------------------------------------------------------------------------


def test_hypothesis_required_fields_are_enforced(examples, validators):
    base = examples["strategy_hypothesis.json"]
    for key in validators["strategy_hypothesis"].schema["required"]:
        document = clone(base)
        delete_key(document, key)
        assert_invalid(validators["strategy_hypothesis"], document, f"required {key}")


def test_hypothesis_rejects_empty_text_and_bad_implementation(examples, validators):
    document = clone(examples["strategy_hypothesis.json"])
    document["hypothesis"] = ""
    assert_invalid(validators["strategy_hypothesis"], document, "hypothèse vide")

    document = clone(examples["strategy_hypothesis.json"])
    document["implementation"] = {"strategy_id": "strat_fixture_001"}
    assert_invalid(validators["strategy_hypothesis"], document, "implémentation incomplète")


def test_hypothesis_implementation_null_is_allowed(examples, validators):
    document = clone(examples["strategy_hypothesis.json"])
    document["implementation"] = None
    assert_valid(validators["strategy_hypothesis"], document, "implémentation null")


def test_hypothesis_rejects_unknown_property_and_bad_date(examples, validators):
    document = clone(examples["strategy_hypothesis.json"])
    document["executable_code"] = "print('not allowed')"
    assert_invalid(validators["strategy_hypothesis"], document, "champ inconnu")

    document = clone(examples["strategy_hypothesis.json"])
    document["created_at"] = "2026-10-01T10:00:00+00:00"
    assert_invalid(validators["strategy_hypothesis"], document, "date offset")


# ---------------------------------------------------------------------------
# Consolidation 1.1.0 : champs obligatoires et suspensions V1
# ---------------------------------------------------------------------------


def test_missing_book_result_may_have_null_estimate(examples, validators):
    document = clone(examples["execution_result_missing_book.json"])
    assert_valid(validators["execution"], document, "missing_book sans estimation")


def test_other_rejected_result_requires_an_estimate(examples, validators):
    document = clone(examples["execution_result.json"])
    document["status"] = "rejected"
    document["rejection_reason"] = "stale_book"
    document["fills"] = []
    document["estimate"] = None
    assert_invalid(validators["execution"], document, "stale_book sans estimation")


def test_execution_estimate_requires_order_id(examples, validators):
    document = clone(examples["execution_estimate.json"])
    delete_key(document, "order_id")
    assert_invalid(validators["execution"], document, "estimation sans order_id")


def test_suspended_fee_formulas_are_rejected(examples, validators):
    for formula in ("per_share", "custom"):
        document = clone(examples["fee_schedule.json"])
        document["fee_formula"] = formula
        assert_invalid(validators["fee_schedule"], document, formula)


def test_outcome_token_fee_unit_is_suspended(examples, validators):
    document = clone(examples["fee_schedule.json"])
    document["fee_charge_unit"] = "outcome_token"
    assert_invalid(validators["fee_schedule"], document, "frais en parts")


def test_not_required_fee_status_is_removed(examples, validators):
    document = clone(examples["experiment.json"])
    document["fees"]["status"] = "not_required"
    assert_invalid(validators["experiment"], document, "not_required")


def test_normal_latency_is_suspended(examples, validators):
    document = clone(examples["execution_assumptions.json"])
    document["latency_distribution"] = "normal"
    assert_invalid(validators["execution"], document, "latence normale")


def test_execution_assumptions_require_rounding_increment(examples, validators):
    document = clone(examples["execution_assumptions.json"])
    delete_key(document, "rounding_increment_micros")
    assert_invalid(validators["execution"], document, "sans incrément")


def test_trade_visibility_must_match_trader_id(examples, validators):
    document = clone(examples["market_event_trade.json"])
    document["trade"]["trader_visibility"] = "identified"
    assert_invalid(validators["market_event"], document, "identified sans trader")

    document = clone(examples["market_event_trade.json"])
    document["trade"]["trader_visibility"] = "unknown"
    document["trade"]["trader_id"] = "trader_fixture_a"
    assert_invalid(validators["market_event"], document, "unknown avec trader")


def test_market_event_requires_normalizer_version(examples, validators):
    document = clone(examples["market_event_trade.json"])
    delete_key(document, "normalizer_version")
    assert_invalid(validators["market_event"], document, "sans normalizer_version")


def test_market_event_requires_event_identity_v2(examples, validators):
    document = clone(examples["market_event_trade.json"])
    delete_key(document, "event_identity_version")
    assert_invalid(validators["market_event"], document, "sans event_identity_version")

    document = clone(examples["market_event_trade.json"])
    document["event_identity_version"] = "v1"
    assert_invalid(validators["market_event"], document, "identité v1 en 1.2.0")


def test_market_event_requires_source_id_or_raw_hash(examples, validators):
    document = clone(examples["market_event_trade.json"])
    document["source_event_id"] = None
    document["raw_payload_sha256"] = None
    assert_invalid(validators["market_event"], document, "aucun ancrage")


def test_connection_status_cannot_have_market_or_token(examples, validators):
    document = clone(examples["market_event_connection_status.json"])
    document["market_id"] = "mkt_fixture_001"
    assert_invalid(validators["market_event"], document, "connexion avec marché")


def test_fixed_latency_requires_zero_jitter(examples, validators):
    document = clone(examples["execution_assumptions.json"])
    document["latency_distribution"] = "fixed"
    document["latency_jitter_ms"] = 10
    assert_invalid(validators["execution"], document, "fixed avec jitter")


def test_rng_v1_is_not_accepted_in_1_2_0(examples, validators):
    document = clone(examples["execution_assumptions.json"])
    document["rng_implementation"] = "polymarket-lab/rng/v1"
    assert_invalid(validators["execution"], document, "rng v1 en 1.2.0")


def test_random_seed_is_bounded(examples, validators):
    document = clone(examples["execution_assumptions.json"])
    document["random_seed"] = 2**63
    assert_invalid(validators["execution"], document, "seed > 2^63-1")


def test_experiment_requires_config_hash_version(examples, validators):
    document = clone(examples["experiment.json"])
    delete_key(document, "config_hash_version")
    assert_invalid(validators["experiment"], document, "sans config_hash_version")

    document = clone(examples["experiment.json"])
    document["config_hash_version"] = "config/v1"
    assert_invalid(validators["experiment"], document, "config/v1 en 1.2.0")


def test_experiment_nested_assumptions_follow_rng_v2(examples, validators):
    document = clone(examples["experiment.json"])
    document["execution_assumptions"]["rng_implementation"] = "polymarket-lab/rng/v1"
    assert_invalid(validators["experiment"], document, "rng v1 imbriqué")

    document = clone(examples["experiment.json"])
    document["execution_assumptions"]["latency_distribution"] = "fixed"
    document["execution_assumptions"]["latency_jitter_ms"] = 1
    assert_invalid(validators["experiment"], document, "fixed avec jitter imbriqué")


def test_void_payout_requires_a_documented_rule(examples, validators):
    document = clone(examples["market_event_market_resolution.json"])
    document["market_resolution"]["resolution_status"] = "VOID"
    document["market_resolution"]["winning_token_id"] = None
    document["market_resolution"]["payout_per_share_micros"] = 1000000
    document["market_resolution"]["void_rule_ref"] = None
    assert_invalid(validators["market_event"], document, "VOID avec payout sans règle")
