"""Tous les exemples du dépôt doivent être valides et cohérents.

Les exemples sont fictifs. Le test vérifie aussi que cette qualité de fixture
n'a pas été perdue (barème non vérifié, source ``fixture``, domaine
``example.invalid``).
"""

from __future__ import annotations

import re
from decimal import Decimal

import pytest

from labtest.contracts import (
    CANONICAL_TIMESTAMP_RE,
    EXECUTION_CONTRACT_TYPES,
    EXAMPLE_SCHEMAS,
    MARKET_EVENT_TYPES,
    iter_timestamp_values,
    schema_key_for_example,
    schema_validation_messages,
)
from labtest.semantics import (
    book_order_errors,
    estimate_totals_errors,
    example_timestamp_errors,
    fee_schedule_semantic_errors,
    result_consistency_errors,
)

EXAMPLE_NAMES = sorted(EXAMPLE_SCHEMAS)


def test_every_example_file_is_mapped():
    assert set(EXAMPLE_SCHEMAS) == {
        "market_event_trade.json",
        "market_event_book_snapshot.json",
        "market_event_book_delta.json",
        "market_event_trader_activity.json",
        "market_event_market_metadata.json",
        "market_event_market_resolution.json",
        "market_event_connection_status.json",
        "order_intent.json",
        "execution_assumptions.json",
        "execution_estimate.json",
        "execution_result.json",
        "execution_result_missing_book.json",
        "fee_schedule.json",
        "experiment.json",
        "strategy_hypothesis.json",
    }


@pytest.mark.parametrize("example_name", EXAMPLE_NAMES)
def test_example_validates_against_its_contract(examples, validators, example_name):
    document = examples[example_name]
    schema_key = schema_key_for_example(example_name)
    messages = schema_validation_messages(validators[schema_key], document)
    assert messages == []


def test_examples_cover_all_market_event_types(examples):
    event_types = {
        document["event_type"]
        for name, document in examples.items()
        if name.startswith("market_event_")
    }
    assert event_types == set(MARKET_EVENT_TYPES)


def test_examples_cover_all_execution_contract_types(examples):
    contract_types = {
        document["contract_type"]
        for name, document in examples.items()
        if name in {"order_intent.json", "execution_assumptions.json",
                    "execution_estimate.json", "execution_result.json"}
    }
    assert contract_types == set(EXECUTION_CONTRACT_TYPES) - {"fill"}
    fill_types = {
        fill["contract_type"]
        for fill in examples["execution_result.json"]["fills"]
    }
    assert fill_types == {"fill"}


EXAMPLE_VERSIONS = {
    "strategy_hypothesis.json": "1.0.0",
    "fee_schedule.json": "1.2.0",
}


@pytest.mark.parametrize("example_name", EXAMPLE_NAMES)
def test_example_schema_version_is_pinned(examples, example_name):
    expected = EXAMPLE_VERSIONS.get(example_name, "1.2.0")
    assert examples[example_name].get("schema_version") == expected


@pytest.mark.parametrize("example_name", EXAMPLE_NAMES)
def test_all_example_timestamps_are_canonical(examples, example_name):
    for path, value in iter_timestamp_values(examples[example_name]):
        assert CANONICAL_TIMESTAMP_RE.fullmatch(value), f"{example_name}:{'.'.join(path)}"


@pytest.mark.parametrize("example_name", EXAMPLE_NAMES)
def test_examples_are_utf8_json_objects(examples, example_name):
    assert isinstance(examples[example_name], dict)


def test_market_event_examples_have_exactly_one_typed_payload(examples):
    payload_keys = {
        "trade": "trade",
        "book_snapshot": "book_snapshot",
        "book_delta": "book_delta",
        "trader_activity": "trader_activity",
        "market_metadata": "market_metadata",
        "market_resolution": "market_resolution",
        "connection_status": "connection_status",
    }
    for name, document in examples.items():
        if not name.startswith("market_event_"):
            continue
        event_type = document["event_type"]
        present = [key for key in payload_keys.values() if key in document]
        assert present == [payload_keys[event_type]], name


def test_market_event_examples_are_marked_fixture(examples):
    for name, document in examples.items():
        if name.startswith("market_event_"):
            assert document["source"] == "fixture"
            assert "fixture" in document["quality_flags"]


def test_fee_example_remains_explicitly_unverified(examples):
    schedule = examples["fee_schedule.json"]
    assert schedule["verification_status"] == "unverified"
    assert "example.invalid" in schedule["source_url"]
    assert "FICTIF" in schedule["source_title"].upper()


def test_fee_example_semantics(examples):
    assert fee_schedule_semantic_errors(examples["fee_schedule.json"]) == []


def test_book_snapshot_example_has_canonical_order(examples):
    snapshot = examples["market_event_book_snapshot.json"]["book_snapshot"]
    assert book_order_errors(snapshot) == []


def test_execution_estimate_example_totals_and_vwap(examples):
    estimate = examples["execution_estimate.json"]
    assert estimate_totals_errors(estimate) == []


def test_execution_result_example_arithmetic(examples):
    result = examples["execution_result.json"]
    assert result_consistency_errors(result) == []


def test_execution_assumptions_are_identical_across_examples(examples):
    assumptions = {
        name: document
        for name, document in examples.items()
        if name == "execution_assumptions.json"
        or document.get("contract_type") == "execution_assumptions"
        or name == "experiment.json"
    }
    values = {
        "execution_assumptions.json": examples["execution_assumptions.json"],
        "execution_estimate.json": examples["execution_estimate.json"]["assumptions"],
        "execution_result.json": examples["execution_result.json"]["estimate"]["assumptions"],
        "experiment.json": examples["experiment.json"]["execution_assumptions"],
    }
    reference = values["execution_assumptions.json"]
    for name, value in values.items():
        assert value == reference, f"hypothèses divergentes dans {name}"


def test_examples_reference_each_other_consistently(examples):
    result = examples["execution_result.json"]
    estimate = examples["execution_estimate.json"]
    intent = examples["order_intent.json"]
    assert result["intent_id"] == estimate["intent_id"] == intent["intent_id"]
    assert result["order_id"] == result["fills"][0]["order_id"]
    assert {fill["fill_id"] for fill in result["fills"]} == {"fill_fixture_001", "fill_fixture_002"}
    assert result["estimate"] == estimate
    assert examples["experiment.json"]["experiment_id"] == intent["experiment_id"]
    assert examples["experiment.json"]["execution_assumptions"] == examples[
        "execution_assumptions.json"
    ]


def test_example_market_events_have_consistent_clock_flags(examples):
    for name, document in examples.items():
        if name.startswith("market_event_"):
            assert example_timestamp_errors(document) == [], name


def test_market_metadata_outcome_identifiers_are_unique(examples):
    metadata = examples["market_event_market_metadata.json"]["market_metadata"]
    token_ids = [outcome["token_id"] for outcome in metadata["outcomes"]]
    indexes = [outcome["outcome_index"] for outcome in metadata["outcomes"]]
    labels = [outcome["outcome_label"] for outcome in metadata["outcomes"]]
    assert len(set(token_ids)) == len(token_ids)
    assert len(set(indexes)) == len(indexes)
    assert len(set(labels)) == len(labels)


def test_experiment_period_is_chronological(examples):
    period = examples["experiment.json"]["period"]
    assert period["start_time"] < period["end_time"]


def test_micros_values_are_integers_not_floats(examples):
    """Un flottant dans un exemple monétaire serait invisible après parsing."""
    offenders = []

    def walk(value, path):
        if isinstance(value, dict):
            for key, child in value.items():
                walk(child, path + (key,))
        elif isinstance(value, list):
            for index, child in enumerate(value):
                walk(child, path + (str(index),))
        elif isinstance(value, float):
            offenders.append(".".join(path))

    for name, document in examples.items():
        walk(document, (name,))
    assert offenders == []


def test_example_decimal_arithmetic_uses_exact_values(examples):
    """Garde-fou : le notionnel de l'exemple est exact en Decimal."""
    for fill in examples["execution_result.json"]["fills"]:
        expected = Decimal(fill["price_micros"]) * Decimal(fill["size_micros"]) / Decimal(1_000_000)
        assert expected == fill["notional_micros"]


def test_example_timestamps_are_sorted_where_the_flow_requires_it(examples):
    trade = examples["market_event_trade.json"]
    book = examples["market_event_book_snapshot.json"]
    assert book["source_timestamp"] <= trade["source_timestamp"]
    assert trade["source_timestamp"] <= examples["market_event_market_resolution.json"]["source_timestamp"]
