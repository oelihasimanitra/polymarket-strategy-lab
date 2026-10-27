"""Tests du validateur applicatif commun (schéma puis chronologie)."""

from __future__ import annotations

import copy

import pytest

from polymarket_lab.validation.contracts import contract_issues, validate_contract


def _fee_reversed(examples):
    document = copy.deepcopy(examples["fee_schedule.json"])
    document["effective_from"] = "2026-10-02T00:00:00.000000Z"
    document["effective_to"] = "2026-10-01T00:00:00.000000Z"
    return document


def _fee_equal(examples):
    document = copy.deepcopy(examples["fee_schedule.json"])
    document["effective_to"] = document["effective_from"]
    return document


def _experiment_reversed(examples):
    document = copy.deepcopy(examples["experiment.json"])
    document["period"]["end_time"] = "2026-10-01T11:00:00.000000Z"
    return document


def _experiment_equal(examples):
    document = copy.deepcopy(examples["experiment.json"])
    document["period"]["end_time"] = document["period"]["start_time"]
    return document


def test_standard_validator_alone_ignores_chronology_extension(
    examples, schemas, validators
):
    document = _fee_reversed(examples)
    assert list(validators["fee_schedule"].iter_errors(document)) == []
    assert validate_contract(
        document, schemas["fee_schedule"], validators["fee_schedule"]
    )


@pytest.mark.parametrize(
    "make_document,name",
    [
        (_fee_reversed, "fee_schedule inversé"),
        (_fee_equal, "fee_schedule bornes égales"),
        (_experiment_reversed, "experiment inversé"),
        (_experiment_equal, "experiment bornes égales"),
    ],
)
def test_application_validator_rejects_invalid_chronology(
    examples, schemas, validators, make_document, name
):
    schema_name = "fee_schedule" if name.startswith("fee_schedule") else "experiment"
    errors = validate_contract(
        make_document(examples), schemas[schema_name], validators[schema_name]
    )
    assert errors, name
    assert any("strictement postérieur" in message for message in errors), name


@pytest.mark.parametrize("schema_name", ["fee_schedule", "experiment"])
def test_application_validator_accepts_valid_examples(
    examples, schemas, validators, schema_name
):
    assert validate_contract(
        examples[f"{schema_name}.json"],
        schemas[schema_name],
        validators[schema_name],
    ) == []


def test_application_validator_reports_schema_errors_before_chronology(
    examples, schemas, validators
):
    document = copy.deepcopy(examples["fee_schedule.json"])
    document["effective_from"] = "2026-10-01"
    document["effective_to"] = "2026-09-01T00:00:00.000000Z"
    errors = validate_contract(
        document, schemas["fee_schedule"], validators["fee_schedule"]
    )
    assert errors
    assert not any("strictement postérieur" in message for message in errors)


def test_chronology_takes_priority_over_version(examples, schemas, validators):
    document = _experiment_reversed(examples)
    document["schema_version"] = "9.9.9"
    issues = contract_issues(
        document,
        schemas["experiment"],
        validators["experiment"],
        expected_version="1.2.0",
    )
    assert issues
    assert {issue.category for issue in issues} == {"chronology"}


def test_version_is_checked_after_a_valid_chronology(examples, schemas, validators):
    document = copy.deepcopy(examples["experiment.json"])
    document["schema_version"] = "9.9.9"
    issues = contract_issues(
        document,
        schemas["experiment"],
        validators["experiment"],
        expected_version="1.2.0",
    )
    assert issues
    assert {issue.category for issue in issues} == {"version"}


def test_missing_period_is_not_reclassified_as_version(
    examples, schemas, validators
):
    document = copy.deepcopy(examples["experiment.json"])
    document.pop("schema_version")
    document.pop("period")
    issues = contract_issues(
        document,
        schemas["experiment"],
        validators["experiment"],
        expected_version="1.2.0",
    )
    assert issues
    assert {issue.category for issue in issues} == {"schema"}
    assert any("period" in issue.message for issue in issues)
    assert not any(
        issue.category == "version" and "period" in issue.message
        for issue in issues
    )


def test_missing_schema_version_alone_is_version(examples, schemas, validators):
    document = copy.deepcopy(examples["experiment.json"])
    document.pop("schema_version")
    issues = contract_issues(
        document,
        schemas["experiment"],
        validators["experiment"],
        expected_version="1.2.0",
    )
    assert issues
    assert {issue.category for issue in issues} == {"version"}
