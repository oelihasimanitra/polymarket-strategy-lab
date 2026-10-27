"""Parité des deux définitions ``execution_assumptions``.

Le README des contrats impose l'égalité entre
``execution.schema.json#/$defs/execution_assumptions`` et
``experiment.schema.json#/$defs/execution_assumptions``. La comparaison porte
sur les propriétés et les champs requis après résolution des ``$ref`` locales.
"""

from __future__ import annotations

import copy

import pytest
from jsonschema import Draft202012Validator

from labtest.contracts import deref


def execution_definition(schemas):
    return schemas["execution"]["$defs"]["execution_assumptions"]


def experiment_definition(schemas):
    return schemas["experiment"]["$defs"]["execution_assumptions"]


def resolved(schemas, which):
    if which == "execution":
        return deref(execution_definition(schemas), schemas["execution"])
    return deref(experiment_definition(schemas), schemas["experiment"])


def test_required_fields_are_identical(schemas):
    assert set(execution_definition(schemas)["required"]) == set(
        experiment_definition(schemas)["required"]
    )


def test_property_names_are_identical(schemas):
    assert set(execution_definition(schemas)["properties"]) == set(
        experiment_definition(schemas)["properties"]
    )


def test_resolved_definitions_are_identical(schemas):
    assert resolved(schemas, "execution") == resolved(schemas, "experiment")


def test_both_definitions_accept_the_shared_example(examples, schemas):
    document = examples["execution_assumptions.json"]
    for which in ("execution", "experiment"):
        validator = Draft202012Validator(resolved(schemas, which))
        assert list(validator.iter_errors(document)) == [], which


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
        {"unknown": 1},
    ],
)
def test_both_definitions_reject_the_same_invalid_values(
    examples, schemas, mutation
):
    document = copy.deepcopy(examples["execution_assumptions.json"])
    document.update(mutation)
    for which in ("execution", "experiment"):
        validator = Draft202012Validator(resolved(schemas, which))
        assert list(validator.iter_errors(document)), f"{which} accepte {mutation}"


@pytest.mark.parametrize(
    "field",
    [
        "contract_type",
        "schema_version",
        "latency_ms",
        "latency_jitter_ms",
        "latency_distribution",
        "liquidity_haircut_bps",
        "max_book_age_ms",
        "random_seed",
        "rng_implementation",
        "rounding_rule",
    ],
)
def test_both_definitions_require_the_same_fields(examples, schemas, field):
    document = copy.deepcopy(examples["execution_assumptions.json"])
    del document[field]
    for which in ("execution", "experiment"):
        validator = Draft202012Validator(resolved(schemas, which))
        assert list(validator.iter_errors(document)), f"{which} accepte sans {field}"


def test_parity_oracle_detects_a_deliberate_drift(schemas):
    """Prouve que le test de parité n'est pas tautologique."""
    mutated = copy.deepcopy(experiment_definition(schemas))
    mutated["properties"]["latency_ms"]["minimum"] = 1
    assert deref(mutated, schemas["experiment"]) != resolved(schemas, "execution")
