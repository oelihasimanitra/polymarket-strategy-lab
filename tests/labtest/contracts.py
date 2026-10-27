"""Chargement des contrats et oracles indépendants.

Les tests ne modifient jamais les contrats. Ils les lisent depuis le dépôt et
les comparent à des ensembles canoniques explicites, afin qu'une dérive de
contrat casse un test au lieu de passer inaperçue.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Iterator

from polymarket_lab.validation.contracts import (
    CHRONOLOGY_KEYWORD,
    chronology_errors,
)

ROOT = Path(__file__).resolve().parents[2]
CONTRACTS_DIR = ROOT / "contracts"
EXAMPLES_DIR = CONTRACTS_DIR / "examples"
SQL_SCHEMA_PATH = ROOT / "schemas" / "initial_db_schema.sql"

SCHEMA_FILENAMES = {
    "market_event": "market_event.schema.json",
    "execution": "execution.schema.json",
    "fee_schedule": "fee_schedule.schema.json",
    "experiment": "experiment.schema.json",
    "strategy_hypothesis": "strategy_hypothesis.schema.json",
}

#: Associe chaque fichier d'exemple au schéma qui doit le valider.
EXAMPLE_SCHEMAS = {
    "market_event_trade.json": "market_event",
    "market_event_book_snapshot.json": "market_event",
    "market_event_book_delta.json": "market_event",
    "market_event_trader_activity.json": "market_event",
    "market_event_market_metadata.json": "market_event",
    "market_event_market_resolution.json": "market_event",
    "market_event_connection_status.json": "market_event",
    "order_intent.json": "execution",
    "execution_assumptions.json": "execution",
    "execution_estimate.json": "execution",
    "execution_result.json": "execution",
    "execution_result_missing_book.json": "execution",
    "fee_schedule.json": "fee_schedule",
    "experiment.json": "experiment",
    "strategy_hypothesis.json": "strategy_hypothesis",
}

#: Format canonique exigé par ARCHITECTURE.md §2.2 et par tous les contrats.
CANONICAL_TIMESTAMP_PATTERN = (
    r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}"
    r"\.[0-9]{6}Z$"
)
CANONICAL_TIMESTAMP_RE = re.compile(CANONICAL_TIMESTAMP_PATTERN)

#: Champs dont la valeur doit être un timestamp canonique.
TIMESTAMP_FIELDS = frozenset(
    {
        "source_timestamp",
        "received_timestamp",
        "created_at",
        "completed_at",
        "recorded_at",
        "resolved_at",
        "decision_timestamp",
        "fill_timestamp",
        "arrival_timestamp",
        "start_time",
        "end_time",
        "effective_from",
        "effective_to",
        "source_retrieved_at",
        "gap_start_timestamp",
        "gap_end_timestamp",
    }
)

#: Types de contrats d'exécution discriminés par contract_type.
EXECUTION_CONTRACT_TYPES = (
    "order_intent",
    "execution_assumptions",
    "execution_estimate",
    "fill",
    "execution_result",
)

#: Les sept types d'événements du contrat de marché.
MARKET_EVENT_TYPES = (
    "trade",
    "book_snapshot",
    "book_delta",
    "trader_activity",
    "market_metadata",
    "market_resolution",
    "connection_status",
)

#: Les cinq sources autorisées. Toute nouvelle source exige un nouveau contrat.
SOURCES = ("gamma_api", "clob_api", "data_api", "clob_ws", "fixture")


def load_json(path: Path) -> Any:
    """Charge un document JSON UTF-8 en refusant les BOM et les encodages dérivés."""
    return json.loads(path.read_text(encoding="utf-8"))


def load_schemas() -> dict[str, dict[str, Any]]:
    return {
        key: load_json(CONTRACTS_DIR / filename)
        for key, filename in SCHEMA_FILENAMES.items()
    }


def load_examples() -> dict[str, Any]:
    return {path.name: load_json(path) for path in sorted(EXAMPLES_DIR.glob("*.json"))}


def schema_key_for_example(filename: str) -> str:
    try:
        return EXAMPLE_SCHEMAS[filename]
    except KeyError as exc:  # pragma: no cover - dépend du dépôt
        raise AssertionError(
            f"Exemple non déclaré dans EXAMPLE_SCHEMAS : {filename}. "
            "Ajouter le mapping avant de committer l'exemple."
        ) from exc


def resolve_pointer(root: dict[str, Any], ref: str) -> Any:
    """Résout une référence JSON Pointer locale (``#/$defs/...``)."""
    if not ref.startswith("#/"):
        raise ValueError(f"Référence non locale refusée par le test : {ref}")
    node: Any = root
    for raw_part in ref[2:].split("/"):
        part = raw_part.replace("~1", "/").replace("~0", "~")
        node = node[part]
    return node


def deref(node: Any, root: dict[str, Any], stack: tuple[str, ...] = ()) -> Any:
    """Résout les ``$ref`` locaux et retire les annotations non sémantiques.

    Sert uniquement à comparer deux définitions (parité
    ``execution_assumptions``). Les descriptions et titres ne changent pas la
    validation et sont retirés ; les contraintes de validation sont conservées.
    """
    if isinstance(node, dict):
        if "$ref" in node:
            ref = node["$ref"]
            if ref in stack:
                raise ValueError(f"Référence cyclique dans le test : {ref}")
            siblings = {
                key: value
                for key, value in node.items()
                if key not in {"$ref", "description", "title", "$comment"}
            }
            if siblings:
                raise AssertionError(
                    f"Référence avec attributs frères non gérés : {sorted(siblings)}"
                )
            return deref(resolve_pointer(root, ref), root, stack + (ref,))
        return {
            key: deref(value, root, stack)
            for key, value in node.items()
            if key not in {"description", "title", "$comment", "$schema", "$id"}
        }
    if isinstance(node, list):
        return [deref(value, root, stack) for value in node]
    return node


def walk_dicts(node: Any, path: tuple[str, ...] = ()) -> Iterator[tuple[tuple[str, ...], dict[str, Any]]]:
    if isinstance(node, dict):
        yield path, node
        for key, value in node.items():
            yield from walk_dicts(value, path + (key,))
    elif isinstance(node, list):
        for index, value in enumerate(node):
            yield from walk_dicts(value, path + (str(index),))


def iter_timestamp_values(doc: Any, path: tuple[str, ...] = ()) -> Iterator[tuple[tuple[str, ...], str]]:
    if isinstance(doc, dict):
        for key, value in doc.items():
            if key in TIMESTAMP_FIELDS and isinstance(value, str):
                yield path + (key,), value
            else:
                yield from iter_timestamp_values(value, path + (key,))
    elif isinstance(doc, list):
        for index, value in enumerate(doc):
            yield from iter_timestamp_values(value, path + (str(index),))


def schema_validation_messages(validator: Any, document: Any) -> list[str]:
    """Messages triés, pour rendre les échecs reproductibles."""
    return sorted(
        f"{'/'.join(str(p) for p in error.absolute_path) or '<root>'}: {error.message}"
        for error in validator.iter_errors(document)
    )
