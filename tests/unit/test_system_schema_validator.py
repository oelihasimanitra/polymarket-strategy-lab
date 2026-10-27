"""Parité du validateur système avec ``jsonschema`` sur les contrats approuvés.

``jsonschema`` reste une dépendance de test. Le writer normal construit
``SystemSchemaValidator`` à partir du schéma gelé du registre ; ces tests
vérifient que, sur les cas couverts, il accepte et refuse les mêmes documents.
Ils ne prouvent pas une conformité JSON Schema complète.
"""

from __future__ import annotations

import copy
import json
from collections.abc import Mapping

import pytest
from jsonschema import Draft202012Validator

from polymarket_lab.validation.contracts import contract_issues
from polymarket_lab.validation.immutability import thaw_json
from polymarket_lab.validation.registry import load_approved_schema
from polymarket_lab.validation.schema_validator import (
    SystemSchemaValidator,
    UnsupportedSchemaError,
)


def _validators(schema):
    return SystemSchemaValidator(schema), Draft202012Validator(thaw_json(schema))


@pytest.mark.parametrize("name", ["experiment", "fee_schedule"])
def test_system_validator_accepts_approved_examples(name, examples):
    schema, _ = load_approved_schema(name)
    system = SystemSchemaValidator(schema, name=name)
    assert list(system.iter_errors(examples[f"{name}.json"])) == []


def _experiment_cases(base):
    cases = []
    cases.append(("valid", copy.deepcopy(base)))
    document = copy.deepcopy(base)
    document.pop("schema_version")
    cases.append(("missing version", document))
    document = copy.deepcopy(base)
    document.pop("period")
    cases.append(("missing period", document))
    document = copy.deepcopy(base)
    document["schema_version"] = "9.9.9"
    cases.append(("bad version", document))
    document = copy.deepcopy(base)
    document["additional"] = True
    cases.append(("additional root", document))
    document = copy.deepcopy(base)
    document["capital"]["initial_micros"] = 0
    cases.append(("capital zero", document))
    document = copy.deepcopy(base)
    document["period"]["end_time"] = None
    cases.append(("research null end", document))
    document = copy.deepcopy(base)
    document["code_version"] = ""
    cases.append(("empty code version", document))
    document = copy.deepcopy(base)
    document["execution_assumptions"].pop("schema_version")
    cases.append(("missing nested schema_version", document))
    document = copy.deepcopy(base)
    document["risk_limits"]["max_position_fraction_bps"] = 10001
    cases.append(("risk bps above max", document))
    return cases


def _fee_cases(base):
    cases = []
    cases.append(("valid", copy.deepcopy(base)))
    document = copy.deepcopy(base)
    document.pop("schema_version")
    cases.append(("missing version", document))
    document = copy.deepcopy(base)
    document.pop("effective_from")
    cases.append(("missing effective_from", document))
    document = copy.deepcopy(base)
    document["schema_version"] = "9.9.9"
    cases.append(("bad version", document))
    document = copy.deepcopy(base)
    document["additional"] = True
    cases.append(("additional root", document))
    document = copy.deepcopy(base)
    document["verification_status"] = "verified"
    document["source_url"] = "http://example.invalid/fees"
    cases.append(("verified non https", document))
    document = copy.deepcopy(base)
    document["fee_formula"] = "none"
    document["maker_rate_micros"] = 1
    cases.append(("none with nonzero rate", document))
    document = copy.deepcopy(base)
    document["taker_rate_micros"] = 1000001
    cases.append(("rate above max", document))
    return cases


@pytest.mark.parametrize(
    "name,cases",
    [
        ("experiment", _experiment_cases),
        ("fee_schedule", _fee_cases),
    ],
)
def test_system_validator_matches_jsonschema_on_cases(
    name, cases, examples
):
    schema, _ = load_approved_schema(name)
    system, reference = _validators(schema)
    for label, document in cases(examples[f"{name}.json"]):
        system_invalid = bool(list(system.iter_errors(document)))
        reference_invalid = bool(list(reference.iter_errors(document)))
        assert system_invalid == reference_invalid, f"{name}/{label}"


@pytest.mark.parametrize(
    "schema",
    [
        {"type": "object", "patternProperties": {"^x": {}}},
        {"type": "object", "format": "email"},
        {"type": "object", "not": {}},
        {"type": "object", "contains": {"type": "string"}},
        {"$ref": "https://example.invalid/schema.json"},
        {"type": "object", "properties": {"x": {"$ref": "#/missing"}}},
    ],
)
def test_system_validator_fails_closed_on_unsupported_schema(schema):
    with pytest.raises(UnsupportedSchemaError):
        SystemSchemaValidator(schema)


def test_system_validator_schema_is_immutable(examples):
    schema, _ = load_approved_schema("experiment")
    system = SystemSchemaValidator(schema)
    assert isinstance(system.schema, Mapping)
    with pytest.raises(TypeError):
        system.schema["properties"]["schema_version"]["const"] = "9.9.9"


def test_nested_schema_version_missing_is_not_a_contract_version_error(
    examples,
):
    schema, _ = load_approved_schema("experiment")
    system = SystemSchemaValidator(schema)
    document = copy.deepcopy(examples["experiment.json"])
    document["execution_assumptions"].pop("schema_version")
    issues = contract_issues(
        document, schema, system, expected_version="1.2.0"
    )
    assert issues
    assert {issue.category for issue in issues} == {"schema"}
    assert any(
        issue.message.startswith("execution_assumptions:")
        and "'schema_version' is a required property" in issue.message
        for issue in issues
    )


@pytest.mark.parametrize(
    "multiple",
    [0.1, 0.3, 0.30000000000000004, 1, 2, -1, 0, 1e-12, 1e308],
)
def test_multiple_of_is_rejected_fail_closed(multiple):
    with pytest.raises(UnsupportedSchemaError) as raised:
        SystemSchemaValidator({"type": "number", "multipleOf": multiple})
    assert "multipleOf" in str(raised.value)


def test_approved_schemas_do_not_use_multiple_of():
    for name in ("experiment", "fee_schedule"):
        schema, _ = load_approved_schema(name)
        assert "multipleOf" not in json.dumps(thaw_json(schema))


def test_valid_local_ref_is_supported():
    validator = SystemSchemaValidator(
        {"$defs": {"decimal": {"type": "number", "minimum": 0}}, "$ref": "#/$defs/decimal"}
    )
    assert list(validator.iter_errors(1.5)) == []
    assert list(validator.iter_errors(-1)) != []


@pytest.mark.parametrize(
    "schema,label",
    [
        ({"$ref": "#/missing"}, "cible inexistante"),
        ({"$ref": "#/examples/0", "examples": ["x"]}, "cible non-schéma"),
        (
            {"$defs": {"a": {"$ref": "#/$defs/a"}}, "$ref": "#/$defs/a"},
            "cycle direct",
        ),
        (
            {
                "$defs": {
                    "a": {"$ref": "#/$defs/b"},
                    "b": {"$ref": "#/$defs/a"},
                },
                "$ref": "#/$defs/a",
            },
            "cycle mutuel",
        ),
        ({"$ref": "https://example.invalid/s.json"}, "référence distante"),
        ({"$ref": "#/examples/0", "examples": [{"unknown": 1}]}, "cible non-schéma objet"),
    ],
)
def test_invalid_ref_is_rejected_at_construction(schema, label):
    with pytest.raises(UnsupportedSchemaError):
        SystemSchemaValidator(schema)


@pytest.mark.parametrize("document_value", [0.3, 0.30000000000000004])
def test_multiple_of_decimal_audit_cases_are_rejected_before_validation(
    document_value,
):
    # A5-C2-01 : le schéma ne doit jamais atteindre la validation du document.
    schema = {"type": "number", "multipleOf": 0.1}
    with pytest.raises(UnsupportedSchemaError) as raised:
        SystemSchemaValidator(schema)
    assert "multipleOf" in str(raised.value)


def test_multiple_of_injected_after_construction_fails_closed():
    validator = SystemSchemaValidator({"type": "number"})
    object.__setattr__(
        validator, "_schema", {"type": "number", "multipleOf": 0.1}
    )
    with pytest.raises(UnsupportedSchemaError):
        list(validator.iter_errors(0.3))
