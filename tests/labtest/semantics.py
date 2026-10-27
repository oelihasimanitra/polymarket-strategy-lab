"""Oracles sémantiques indépendants des contrats JSON.

JSON Schema valide la forme, pas les invariants arithmétiques ni l'ordre d'un
carnet. Ces fonctions rejouent les règles écrites dans ARCHITECTURE.md et dans
les descriptions de contrats. Elles ne sont pas une implémentation de
production : elles servent d'oracle de test.
"""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Iterable

MICROS = 1_000_000


def half_up_div(numerator: int, denominator: int) -> int:
    """Division entière avec arrondi half-up, pour des entiers positifs."""
    if denominator <= 0:
        raise ValueError("denominator doit être > 0")
    if numerator < 0:
        raise ValueError("numerator négatif non pris en charge")
    return (numerator + denominator // 2) // denominator


def expected_notional_micros(price_micros: int, size_micros: int) -> int:
    """notionnel = prix (micro-probabilité) × taille (micro-parts)."""
    return half_up_div(price_micros * size_micros, MICROS)


def expected_linear_fee_micros(rate_micros: int, price_micros: int, size_micros: int) -> int:
    """Formule ``linear_min_price_1mp`` :

    taux × min(prix, 1 − prix) × quantité, tout en micro-unités.
    """
    min_price = min(price_micros, MICROS - price_micros)
    numerator = rate_micros * min_price * size_micros
    denominator = MICROS * MICROS
    return int(
        (Decimal(numerator) / Decimal(denominator)).quantize(
            Decimal("1"), rounding=ROUND_HALF_UP
        )
    )


def weighted_average_price(levels: Iterable[dict[str, Any]]) -> int | None:
    total_size = sum(level["consumed_size_micros"] for level in levels)
    if total_size == 0:
        return None
    total_cost = sum(
        level["price_micros"] * level["consumed_size_micros"] for level in levels
    )
    return half_up_div(total_cost, total_size)


def book_order_errors(snapshot: dict[str, Any]) -> list[str]:
    """Vérifie l'ordre canonique décrit par le contrat book_snapshot."""
    errors: list[str] = []

    bids = [level["price_micros"] for level in snapshot["bids"]]
    asks = [level["price_micros"] for level in snapshot["asks"]]

    for previous, current in zip(bids, bids[1:]):
        if current >= previous:
            errors.append(f"bids non strictement décroissants : {previous} puis {current}")
    for previous, current in zip(asks, asks[1:]):
        if current <= previous:
            errors.append(f"asks non strictement croissants : {previous} puis {current}")
    if len(set(bids)) != len(bids):
        errors.append("prix de bids dupliqué")
    if len(set(asks)) != len(asks):
        errors.append("prix d'asks dupliqué")
    return errors


def level_consumption_errors(levels: Iterable[dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    for level in levels:
        consumed = level["consumed_size_micros"]
        available = level["available_size_micros"]
        excluded = level.get("excluded_size_micros", 0)
        if consumed > available:
            errors.append(
                f"niveau {level.get('level_index')} : consommé {consumed} > disponible {available}"
            )
        if consumed + excluded > available:
            errors.append(
                f"niveau {level.get('level_index')} : consommé + exclu "
                f"({consumed} + {excluded}) > disponible {available}"
            )
    return errors


def estimate_totals_errors(estimate: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    levels = estimate["levels"]
    errors.extend(level_consumption_errors(levels))
    consumed_total = sum(level["consumed_size_micros"] for level in levels)
    if consumed_total != estimate["executable_size_micros"]:
        errors.append(
            "executable_size_micros ne correspond pas à la somme des niveaux : "
            f"{estimate['executable_size_micros']} != {consumed_total}"
        )
    if levels:
        vwap = weighted_average_price(levels)
        if estimate["status"] in {"accepted", "partial"} and vwap != estimate["vwap_micros"]:
            errors.append(
                f"vwap_micros {estimate['vwap_micros']} != VWAP pondéré {vwap}"
            )
    return errors


def fill_arithmetic_errors(fill: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    expected_notional = expected_notional_micros(
        fill["price_micros"], fill["size_micros"]
    )
    if fill["notional_micros"] != expected_notional:
        errors.append(
            f"notionnel {fill['notional_micros']} != prix × taille {expected_notional}"
        )

    fee = fill["fee_calculation"]
    if fee["fee_formula"] == "linear_min_price_1mp":
        expected_fee = expected_linear_fee_micros(
            fee["rate_micros"], fill["price_micros"], fill["size_micros"]
        )
        if fee["fee_amount_micros"] != expected_fee:
            errors.append(
                f"frais {fee['fee_amount_micros']} != formule linéaire {expected_fee}"
            )
    return errors


def example_timestamp_errors(document: dict[str, Any]) -> list[str]:
    """Vérifie l'ordre source/réception et la présence du flag clock_skew.

    Règle ARCHITECTURE §2.2 : une réception antérieure à la source n'est jamais
    corrigée silencieusement ; elle doit porter ``clock_skew``.
    """
    errors: list[str] = []
    source = document.get("source_timestamp")
    received = document.get("received_timestamp")
    if source and received and received < source:
        flags = document.get("quality_flags", [])
        if "clock_skew" not in flags:
            errors.append(
                "received_timestamp < source_timestamp sans quality_flag clock_skew"
            )
    return errors


def result_consistency_errors(result: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    estimate = result["estimate"]
    fills = result["fills"]

    for fill in fills:
        errors.extend(fill_arithmetic_errors(fill))
        if fill["order_id"] != result["order_id"]:
            errors.append(
                f"fill {fill['fill_id']} rattaché à {fill['order_id']} "
                f"au lieu de {result['order_id']}"
            )

    if fills:
        filled = sum(fill["size_micros"] for fill in fills)
        if estimate["status"] in {"accepted", "partial"} and filled != estimate["executable_size_micros"]:
            errors.append(
                f"taille des fills {filled} != executable_size_micros {estimate['executable_size_micros']}"
            )
        indexes = [fill["fill_index"] for fill in fills]
        if len(set(indexes)) != len(indexes):
            errors.append("fill_index dupliqué dans execution_result")
    return errors


def fee_schedule_semantic_errors(schedule: dict[str, Any]) -> list[str]:
    """Invariants exprimés dans le contrat mais non validables par JSON Schema."""
    errors: list[str] = []
    effective_from = schedule.get("effective_from")
    effective_to = schedule.get("effective_to")
    if effective_from and effective_to and effective_to <= effective_from:
        errors.append("effective_to doit être strictement postérieur à effective_from")

    if schedule.get("fee_formula") == "none":
        if schedule.get("maker_rate_micros") != 0 or schedule.get("taker_rate_micros") != 0:
            errors.append("fee_formula=none avec un taux non nul")
    if schedule.get("fee_formula") == "custom" and not schedule.get("custom_formula_ref"):
        errors.append("fee_formula=custom sans custom_formula_ref")
    if schedule.get("verification_status") == "verified":
        if not str(schedule.get("source_url", "")).startswith("https://"):
            errors.append("barème verified sans source https")
        if (
            schedule.get("scope_type") in {"global", "category"}
            and not schedule.get("scope_evidence_ref")
        ):
            errors.append("barème verified global/category sans scope_evidence_ref")
    return errors
