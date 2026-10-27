"""Vérifie que les oracles sémantiques détectent réellement les défauts.

JSON Schema ne peut pas exprimer l'ordre d'un carnet ni les égalités
arithmétiques. Ces tests prouvent que les oracles indépendants utilisés sur les
exemples ont du mordant, et documentent ce que les contrats ne couvrent pas.
"""

from __future__ import annotations

import copy

from labtest.semantics import (
    book_order_errors,
    estimate_totals_errors,
    expected_linear_fee_micros,
    expected_notional_micros,
    fee_schedule_semantic_errors,
    fill_arithmetic_errors,
    level_consumption_errors,
    result_consistency_errors,
    weighted_average_price,
)


def test_unordered_book_is_detected(examples):
    snapshot = copy.deepcopy(examples["market_event_book_snapshot.json"]["book_snapshot"])
    snapshot["bids"] = list(reversed(snapshot["bids"]))
    assert book_order_errors(snapshot)


def test_duplicate_book_price_is_detected(examples):
    snapshot = copy.deepcopy(examples["market_event_book_snapshot.json"]["book_snapshot"])
    snapshot["asks"][1]["price_micros"] = snapshot["asks"][0]["price_micros"]
    assert book_order_errors(snapshot)


def test_json_schema_does_not_enforce_book_order(examples, validators):
    """Limite connue : l'ordre canonique est décrit, non validé par JSON Schema.

    A1 doit normaliser l'ordre (bids décroissants, asks croissants) et A5 doit
    le tester sur le normaliseur, pas seulement sur le contrat.
    """
    document = copy.deepcopy(examples["market_event_book_snapshot.json"])
    document["book_snapshot"]["bids"] = list(reversed(document["book_snapshot"]["bids"]))
    assert list(validators["market_event"].iter_errors(document)) == []


def test_notional_mismatch_is_detected(examples):
    fill = copy.deepcopy(examples["execution_result.json"]["fills"][0])
    fill["notional_micros"] += 1
    assert fill_arithmetic_errors(fill)
    assert expected_notional_micros(530000, 40000000) == 21200000


def test_linear_fee_mismatch_is_detected(examples):
    fill = copy.deepcopy(examples["execution_result.json"]["fills"][0])
    fill["fee_calculation"]["fee_amount_micros"] += 1
    assert fill_arithmetic_errors(fill)
    assert expected_linear_fee_micros(10000, 530000, 40000000) == 188000


def test_level_overconsumption_is_detected(examples):
    estimate = copy.deepcopy(examples["execution_estimate.json"])
    estimate["levels"][0]["consumed_size_micros"] = 40000001
    assert level_consumption_errors(estimate["levels"])


def test_vwap_mismatch_is_detected(examples):
    estimate = copy.deepcopy(examples["execution_estimate.json"])
    estimate["vwap_micros"] += 1
    assert estimate_totals_errors(estimate)
    assert weighted_average_price(examples["execution_estimate.json"]["levels"]) == 536000


def test_result_fill_total_mismatch_is_detected(examples):
    result = copy.deepcopy(examples["execution_result.json"])
    result["fills"][0]["size_micros"] -= 1
    result["fills"][0]["notional_micros"] = expected_notional_micros(
        result["fills"][0]["price_micros"], result["fills"][0]["size_micros"]
    )
    errors = result_consistency_errors(result)
    assert any("taille des fills" in error for error in errors), errors


def test_fee_schedule_period_inversion_is_detected(examples):
    schedule = copy.deepcopy(examples["fee_schedule.json"])
    schedule["effective_from"] = "2026-10-02T00:00:00.000000Z"
    schedule["effective_to"] = "2026-10-01T00:00:00.000000Z"
    assert fee_schedule_semantic_errors(schedule)
