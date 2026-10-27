"""Validation structurelle des cinq schémas JSON (candidat 1.2.0).

Formalise la vérification A0 du 2026-10-26 sans s'appuyer sur son résultat :
chaque schéma est revalidé par ``check_schema`` et chaque convention commune
est testée indépendamment.
"""

from __future__ import annotations

import re

import pytest
from jsonschema import Draft202012Validator

from labtest.contracts import (
    CANONICAL_TIMESTAMP_PATTERN,
    CHRONOLOGY_KEYWORD,
    EXECUTION_CONTRACT_TYPES,
    MARKET_EVENT_TYPES,
    SCHEMA_FILENAMES,
    SOURCES,
    TIMESTAMP_FIELDS,
    walk_dicts,
)

SCHEMA_NAMES = sorted(SCHEMA_FILENAMES)

OBJECT_SCHEMAS = ["market_event", "fee_schedule", "experiment", "strategy_hypothesis"]


@pytest.mark.parametrize("schema_name", SCHEMA_NAMES)
def test_schema_is_valid_draft_2020_12(schemas, schema_name):
    Draft202012Validator.check_schema(schemas[schema_name])


@pytest.mark.parametrize("schema_name", SCHEMA_NAMES)
def test_schema_declares_identity(schemas, schema_name):
    schema = schemas[schema_name]
    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert schema["$id"].startswith("https://polymarket-strategy-lab.invalid/contracts/")
    assert schema["title"]


@pytest.mark.parametrize("schema_name", OBJECT_SCHEMAS)
def test_root_object_is_strict(schemas, schema_name):
    assert schemas[schema_name]["additionalProperties"] is False


def test_execution_union_is_strict(schemas):
    schema = schemas["execution"]
    refs = [entry["$ref"] for entry in schema["oneOf"]]
    assert len(refs) == len(EXECUTION_CONTRACT_TYPES)
    for contract_type in EXECUTION_CONTRACT_TYPES:
        definition = schema["$defs"][contract_type]
        assert definition["additionalProperties"] is False


@pytest.mark.parametrize("schema_name", SCHEMA_NAMES)
def test_every_object_with_properties_is_strict(schemas, schema_name):
    """``additionalProperties: false`` est une convention non négociable."""
    offenders = []
    for path, node in walk_dicts(schemas[schema_name]):
        if (
            node.get("type") == "object"
            and "properties" in node
            and node.get("additionalProperties") is not False
        ):
            offenders.append("/".join(path) or "<root>")
    assert offenders == []


SCHEMA_VERSIONS = {
    "market_event": "1.2.0",
    "execution": "1.2.0",
    "fee_schedule": "1.2.0",
    "experiment": "1.2.0",
    "strategy_hypothesis": "1.0.0",
}


CHRONOLOGY_RULES = {
    "fee_schedule": ([], "effective_from", "effective_to"),
    "experiment": (["period"], "start_time", "end_time"),
}


@pytest.mark.parametrize("schema_name", sorted(CHRONOLOGY_RULES))
def test_chronology_extension_is_declared(schemas, schema_name):
    expected_path, start, end = CHRONOLOGY_RULES[schema_name]
    rules = [
        node[CHRONOLOGY_KEYWORD]
        for _path, node in walk_dicts(schemas[schema_name])
        if CHRONOLOGY_KEYWORD in node
    ]
    assert rules == [{
        "instance_path": expected_path,
        "start_field": start,
        "end_field": end,
        "strict": True,
        "allow_null_end": True,
    }]


@pytest.mark.parametrize("schema_name", SCHEMA_NAMES)
def test_every_schema_version_is_pinned(schemas, schema_name):
    values = set()
    for _path, node in walk_dicts(schemas[schema_name]):
        version_node = node.get("properties", {}).get("schema_version")
        if isinstance(version_node, dict):
            values.add(version_node.get("const"))
    assert values == {SCHEMA_VERSIONS[schema_name]}


@pytest.mark.parametrize("schema_name", SCHEMA_NAMES)
def test_contracts_contain_no_float_type(schemas, schema_name):
    """Aucun champ monétaire ne doit accepter ``number`` (donc un flottant)."""
    offenders = []
    for path, node in walk_dicts(schemas[schema_name]):
        node_type = node.get("type")
        types = node_type if isinstance(node_type, list) else [node_type]
        if "number" in types:
            offenders.append("/".join(path) or "<root>")
    assert offenders == []


def test_execution_definitions_are_the_union_members(schemas):
    schema = schemas["execution"]
    assert set(schema["$defs"]) >= set(EXECUTION_CONTRACT_TYPES)
    for contract_type in EXECUTION_CONTRACT_TYPES:
        definition = schema["$defs"][contract_type]
        assert definition["properties"]["contract_type"]["const"] == contract_type


@pytest.mark.parametrize("contract_type", EXECUTION_CONTRACT_TYPES)
def test_execution_contracts_require_type_and_version(schemas, contract_type):
    definition = schemas["execution"]["$defs"][contract_type]
    assert "contract_type" in definition["required"]
    assert "schema_version" in definition["required"]


def test_timestamp_patterns_are_identical_everywhere(schemas):
    patterns = set()
    for schema_name, schema in schemas.items():
        for path, node in walk_dicts(schema):
            if (
                isinstance(node.get("pattern"), str)
                and (path and (path[-1] in TIMESTAMP_FIELDS or path[-1] == "timestamp"))
                and re.fullmatch(r"\^\[0-9\]\{4\}-.*Z\$", node["pattern"])
            ):
                patterns.add(node["pattern"])
    assert patterns == {CANONICAL_TIMESTAMP_PATTERN}


def test_event_type_enum_matches_published_contract(schemas):
    assert schemas["market_event"]["$defs"]["event_type"]["enum"] == list(MARKET_EVENT_TYPES)
    experiment_event_types = (
        schemas["experiment"]["properties"]["data"]["properties"]["filters"]
        ["properties"]["event_types"]["items"]["enum"]
    )
    assert experiment_event_types == list(MARKET_EVENT_TYPES)


def test_source_enum_is_identical_in_event_and_experiment(schemas):
    assert schemas["market_event"]["$defs"]["source"]["enum"] == list(SOURCES)
    experiment_sources = (
        schemas["experiment"]["properties"]["data"]["properties"]["filters"]
        ["properties"]["sources"]["items"]["enum"]
    )
    assert experiment_sources == list(SOURCES)


def test_execution_contract_type_enum_is_pinned(schemas):
    assert schemas["execution"]["$defs"]["contract_type"]["enum"] == list(
        EXECUTION_CONTRACT_TYPES
    )


@pytest.mark.parametrize("schema_name", SCHEMA_NAMES)
def test_no_reference_escapes_the_schema_file(schemas, schema_name):
    """Toutes les ``$ref`` sont locales : chaque fichier se valide seul."""
    for path, node in walk_dicts(schemas[schema_name]):
        ref = node.get("$ref")
        if ref is not None:
            assert ref.startswith("#/"), f"{schema_name}:{'/'.join(path)} -> {ref}"
