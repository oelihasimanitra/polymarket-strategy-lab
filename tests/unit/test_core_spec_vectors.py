"""Vecteurs d'or indépendants pour les définitions de `core/` (D-028, D-039).

Ce fichier ne teste pas encore une implémentation A1 : il fige les valeurs que
A1/A2 devront reproduire. Il sert d'oracle A5 pour les conversions, les hashes
et le générateur déterministe indépendant de Python.
"""

from __future__ import annotations

import hashlib
import json
from decimal import Decimal, ROUND_HALF_EVEN, ROUND_HALF_UP

import pytest


def canonical_json(value) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"),
        ensure_ascii=False, allow_nan=False,
    ).encode("utf-8")


def reference_to_micros(value, unit_decimals: int, *, rounding=ROUND_HALF_EVEN) -> int:
    if isinstance(value, float) or isinstance(value, bool):
        raise TypeError("float/bool interdits")
    amount = value if isinstance(value, Decimal) else Decimal(str(value))
    scaled = amount * (Decimal(10) ** unit_decimals)
    if scaled != scaled.to_integral_value():
        raise ValueError("précision supérieure à l'unité")
    micros = scaled * (Decimal(10) ** (6 - unit_decimals))
    if micros == micros.to_integral_value():
        return int(micros)
    return int(micros.quantize(Decimal(1), rounding=rounding))


def reference_base_units_to_micros(raw_units: int, unit_decimals: int) -> int:
    if isinstance(raw_units, bool) or not isinstance(raw_units, int):
        raise TypeError("raw_units doit être un entier")
    scaled = Decimal(raw_units) * (Decimal(10) ** (6 - unit_decimals))
    if scaled == scaled.to_integral_value():
        return int(scaled)
    return int(scaled.quantize(Decimal(1), rounding=ROUND_HALF_EVEN))


def reference_event_id(source, source_event_id, market_id, token_id, timestamp):
    identity = [
        "polymarket-lab/event-id/v1", source, source_event_id,
        market_id, token_id, timestamp,
    ]
    return "evt_" + hashlib.sha256(canonical_json(identity)).hexdigest()[:32]


def reference_config_hash(config: dict) -> str:
    return "sha256:" + hashlib.sha256(canonical_json(config)).hexdigest()


def reference_stable_u64(seed: int, purpose: str, counter: int) -> int:
    payload = f"{seed}|{purpose}|{counter}".encode("utf-8")
    return int.from_bytes(hashlib.sha256(payload).digest()[:8], "big")


def reference_uniform_int(seed: int, purpose: str, low: int, high: int) -> int:
    span = high - low + 1
    limit = (2**64 // span) * span
    counter = 0
    while True:
        value = reference_stable_u64(seed, purpose, counter)
        if value < limit:
            return low + value % span
        counter += 1


def test_to_micros_golden_values():
    assert reference_to_micros(Decimal("1.23"), 2) == 1_230_000
    assert reference_to_micros(Decimal("0.536"), 6) == 536_000
    assert reference_to_micros(Decimal("1.23456789"), 8) == 1_234_568
    assert reference_to_micros(Decimal("-0.5"), 6) == -500_000


def test_to_micros_rejects_float_and_excess_precision():
    with pytest.raises(TypeError):
        reference_to_micros(1.23, 2)
    with pytest.raises(ValueError):
        reference_to_micros(Decimal("1.234"), 2)


def test_base_units_to_micros_golden_values():
    assert reference_base_units_to_micros(123, 2) == 1_230_000
    assert reference_base_units_to_micros(123_456_789, 8) == 1_234_568


def test_event_id_is_stable_and_identity_sensitive():
    args = (
        "fixture", "src-evt_demo", "mkt_demo", "tok_demo",
        "2026-10-01T12:00:00.000000Z",
    )
    expected = "evt_3f4290309046d1473e229dcf31264828"
    assert reference_event_id(*args) == expected
    assert reference_event_id(*args) == reference_event_id(*args)
    changed = list(args)
    changed[2] = "tok_other"
    assert reference_event_id(*changed) != expected


def test_config_hash_golden_value():
    config = {
        "schema_version": "1.1.0",
        "experiment_id": "exp_demo",
        "capital": {"micros": 1_000_000},
    }
    assert reference_config_hash(config) == (
        "sha256:ed996ee193d5aa9159fd9bb71a607dfe8fcb5bba28c2dc06a89e4001bf2fd1ea"
    )


def test_stable_rng_matches_golden_vector_and_is_not_python_random():
    assert reference_uniform_int(42, "latency", 0, 100) == 72
    assert reference_uniform_int(42, "latency", 0, 100) == 72
    assert reference_uniform_int(42, "haircut", 0, 100) != 72


def test_stable_rng_is_bounded():
    for purpose in ("latency", "haircut", "control"):
        for low, high in ((0, 0), (0, 1), (10, 20)):
            draw = reference_uniform_int(7, purpose, low, high)
            assert low <= draw <= high
