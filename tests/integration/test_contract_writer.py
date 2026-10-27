"""Tests du parcours commun writer → validation → SQLite."""

from __future__ import annotations

import copy
import hashlib
import inspect
import shutil
import sqlite3
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

import polymarket_lab.storage.contract_writer as writer_module
from polymarket_lab.storage.contract_writer import (
    ContractApprovalError,
    ContractBusinessError,
    ContractChronologyError,
    ContractConnectionError,
    ContractPersistenceError,
    ContractSchemaError,
    ContractSQLiteError,
    ContractSpec,
    ContractSpecError,
    ContractValidatorError,
    ContractVersionError,
    write_experiment,
    write_fee_schedule,
)
from polymarket_lab.storage.contract_writer_testing import (
    TestContractSpec,
    write_experiment_for_tests,
    write_fee_schedule_for_tests,
)
from polymarket_lab.validation.contracts import contract_issues
from polymarket_lab.validation import registry as registry_module
from polymarket_lab.validation.registry import (
    APPROVED_CONTRACTS,
    ApprovedContract,
    ContractHashMismatchError,
    ContractNotRegisteredError,
    ContractSchemaMalformedError,
    ContractSchemaMismatchError,
    ContractSchemaMissingError,
    ContractSchemaUnreadableError,
    load_approved_schema,
    verify_approved_schema,
)
from polymarket_lab.validation.schema_validator import (
    SystemSchemaValidator,
    UnsupportedSchemaError,
)


def _experiment_document(examples):
    document = copy.deepcopy(examples["experiment.json"])
    document["experiment_id"] = "exp_writer_001"
    return document


def _fee_document(examples):
    document = copy.deepcopy(examples["fee_schedule.json"])
    document["fee_schedule_id"] = "fee_writer_001"
    return document


def _test_experiment_spec(schemas, validators) -> TestContractSpec:
    return TestContractSpec(
        "experiment", copy.deepcopy(schemas["experiment"]), validators["experiment"]
    )


def _test_fee_spec(schemas, validators) -> TestContractSpec:
    return TestContractSpec(
        "fee_schedule", copy.deepcopy(schemas["fee_schedule"]), validators["fee_schedule"]
    )


def _count(db, table: str) -> int:
    return db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


def test_writer_persists_valid_experiment_with_validated_version(
    db_v7, seeded_v7, examples
):
    db_v7.commit()
    document = _experiment_document(examples)

    returned = write_experiment(db_v7, document)

    assert returned == document["experiment_id"]
    row = db_v7.execute(
        "SELECT schema_version, period_type, end_time, config_hash_version "
        "FROM experiments WHERE experiment_id = ?",
        (document["experiment_id"],),
    ).fetchone()
    assert tuple(row) == (
        "1.2.0", "research", document["period"]["end_time"], "config/v2"
    )
    assert db_v7.in_transaction is False


def test_writer_persists_valid_fee_schedule(db_v7, seeded_v7, examples):
    db_v7.commit()
    document = _fee_document(examples)

    returned = write_fee_schedule(db_v7, document)

    assert returned == document["fee_schedule_id"]
    row = db_v7.execute(
        "SELECT schema_version, effective_from, effective_to FROM fee_schedules "
        "WHERE fee_schedule_id = ?",
        (document["fee_schedule_id"],),
    ).fetchone()
    assert tuple(row) == ("1.2.0", document["effective_from"], None)


def _fee_reversed(document):
    document["effective_from"] = "2026-10-02T00:00:00.000000Z"
    document["effective_to"] = "2026-10-01T00:00:00.000000Z"


def _fee_equal(document):
    document["effective_to"] = document["effective_from"]


@pytest.mark.parametrize(
    "mutate,kind",
    [
        (lambda d: d["period"].__setitem__("end_time", "2026-10-01T11:00:00.000000Z"), "experiment"),
        (lambda d: d["period"].__setitem__("end_time", d["period"]["start_time"]), "experiment"),
        (_fee_reversed, "fee"),
        (_fee_equal, "fee"),
    ],
)
def test_writer_rejects_invalid_chronology_without_row(
    db_v7, seeded_v7, examples, mutate, kind
):
    db_v7.commit()
    if kind == "experiment":
        document = _experiment_document(examples)
        mutate(document)
        table, write = "experiments", write_experiment
    else:
        document = _fee_document(examples)
        mutate(document)
        table, write = "fee_schedules", write_fee_schedule

    before = _count(db_v7, table)
    with pytest.raises(ContractChronologyError):
        write(db_v7, document)
    assert _count(db_v7, table) == before
    assert db_v7.in_transaction is False


def test_writer_rejects_schema_error_without_row(db_v7, seeded_v7, examples):
    db_v7.commit()
    document = _experiment_document(examples)
    document["capital"]["initial_micros"] = 0
    before = _count(db_v7, "experiments")
    with pytest.raises(ContractSchemaError):
        write_experiment(db_v7, document)
    assert _count(db_v7, "experiments") == before


@pytest.mark.parametrize("version", ["1.1.0", "9.9.9"])
def test_writer_rejects_incompatible_version_without_row(
    db_v7, seeded_v7, examples, version
):
    db_v7.commit()
    document = _experiment_document(examples)
    document["schema_version"] = version
    before = _count(db_v7, "experiments")
    with pytest.raises(ContractVersionError):
        write_experiment(db_v7, document)
    assert _count(db_v7, "experiments") == before


def test_writer_rejects_paper_live_without_end_time_key(
    db_v7, seeded_v7, examples
):
    db_v7.commit()
    document = _experiment_document(examples)
    document["period"]["type"] = "paper_live"
    del document["period"]["end_time"]
    document["data"]["manifest_id"] = None
    document["data"]["cutoff_received_timestamp"] = None
    before = _count(db_v7, "experiments")
    with pytest.raises(ContractSchemaError):
        write_experiment(db_v7, document)
    assert _count(db_v7, "experiments") == before


def test_writer_persists_paper_live_with_explicit_null_end(
    db_v7, seeded_v7, examples
):
    db_v7.commit()
    document = _experiment_document(examples)
    document["experiment_id"] = "exp_writer_live"
    document["period"]["type"] = "paper_live"
    document["period"]["end_time"] = None
    document["data"]["manifest_id"] = None
    document["data"]["cutoff_received_timestamp"] = None

    write_experiment(db_v7, document)
    row = db_v7.execute(
        "SELECT end_time, schema_version FROM experiments WHERE experiment_id = ?",
        ("exp_writer_live",),
    ).fetchone()
    assert tuple(row) == (None, "1.2.0")


def test_writer_rejects_business_inconsistency_without_row(
    db_v7, seeded_v7, examples
):
    db_v7.commit()
    document = _experiment_document(examples)
    document["status"] = "completed"
    document["completed_at"] = None
    before = _count(db_v7, "experiments")
    with pytest.raises(ContractBusinessError):
        write_experiment(db_v7, document)
    assert _count(db_v7, "experiments") == before


def test_writer_wraps_sql_error_and_preserves_existing_row(
    db_v7, seeded_v7, examples
):
    db_v7.commit()
    document = _fee_document(examples)
    write_fee_schedule(db_v7, document)
    before = _count(db_v7, "fee_schedules")

    with pytest.raises(ContractSQLiteError):
        write_fee_schedule(db_v7, document)

    assert _count(db_v7, "fee_schedules") == before
    assert db_v7.in_transaction is False


def test_writer_rolls_back_when_persisted_row_differs(
    db_v7, seeded_v7, examples
):
    db_v7.commit()
    document = _fee_document(examples)
    db_v7.execute(
        """
        CREATE TRIGGER test_tamper_fee AFTER INSERT ON fee_schedules
        BEGIN
            UPDATE fee_schedules SET notes = 'tampered'
            WHERE fee_schedule_id = NEW.fee_schedule_id;
        END
        """
    )
    db_v7.commit()
    before = _count(db_v7, "fee_schedules")
    try:
        with pytest.raises(ContractPersistenceError):
            write_fee_schedule(db_v7, document)
        assert _count(db_v7, "fee_schedules") == before
        assert db_v7.in_transaction is False
    finally:
        db_v7.execute("DROP TRIGGER test_tamper_fee")
        db_v7.commit()


def test_writer_rejects_missing_version_as_version_error(
    db_v7, seeded_v7, examples
):
    db_v7.commit()
    document = _experiment_document(examples)
    document.pop("schema_version")
    before = _count(db_v7, "experiments")
    with pytest.raises(ContractVersionError):
        write_experiment(db_v7, document)
    assert _count(db_v7, "experiments") == before


@pytest.mark.parametrize(
    "schema",
    [
        {},
        {"properties": None},
        {"properties": {"schema_version": "bad"}},
        {"properties": {"schema_version": {}}},
    ],
)
def test_contract_spec_malformed_is_rejected(validators, schema):
    with pytest.raises(ContractSpecError):
        TestContractSpec("experiment", schema, validators["experiment"])


def test_validator_exception_is_wrapped_with_cause(
    db_v7, seeded_v7, schemas, examples
):
    class RaisingValidator:
        def iter_errors(self, instance):
            raise RuntimeError("validator boom")

    spec = TestContractSpec(
        "experiment", copy.deepcopy(schemas["experiment"]), RaisingValidator()
    )
    db_v7.commit()
    before = _count(db_v7, "experiments")
    with pytest.raises(ContractValidatorError) as raised:
        write_experiment_for_tests(
            db_v7, _experiment_document(examples), spec
        )
    assert isinstance(raised.value.__cause__, Exception)
    assert isinstance(raised.value.__cause__.__cause__, RuntimeError)
    assert _count(db_v7, "experiments") == before


def test_forged_version_is_rejected_by_normal_path(
    db_v7, seeded_v7, examples
):
    document = _experiment_document(examples)
    document["schema_version"] = "9.9.9"
    db_v7.commit()
    before = _count(db_v7, "experiments")
    with pytest.raises(ContractVersionError):
        write_experiment(db_v7, document)
    assert _count(db_v7, "experiments") == before


def test_normal_writer_accepts_no_schema_or_validator_argument(
    db_v7, seeded_v7, schemas, validators, examples
):
    assert list(inspect.signature(write_experiment).parameters) == [
        "connection",
        "document",
    ]
    assert list(inspect.signature(write_fee_schedule).parameters) == [
        "connection",
        "document",
    ]

    document = _experiment_document(examples)
    with pytest.raises(TypeError):
        write_experiment(
            db_v7,
            document,
            _test_experiment_spec(schemas, validators),
            allow_test_specs=True,
        )


def test_approved_spec_is_built_by_the_system_without_caller_validator():
    spec = ContractSpec.from_approved("experiment")
    assert spec.approved is True
    assert isinstance(spec.validator, SystemSchemaValidator)
    assert spec.version == "1.2.0"
    assert spec.validator.schema == spec.schema

    with pytest.raises(TypeError):
        ContractSpec.from_approved(
            "experiment", Draft202012Validator(spec.schema)
        )
    with pytest.raises(TypeError):
        ContractSpec()


def test_approved_schema_and_validator_schema_are_deeply_immutable():
    spec = ContractSpec.from_approved("experiment")

    with pytest.raises(TypeError):
        spec.schema["title"] = "mutated"
    with pytest.raises(TypeError):
        spec.schema["properties"]["schema_version"]["const"] = "9.9.9"
    with pytest.raises(TypeError):
        spec.validator.schema["properties"]["schema_version"]["const"] = "9.9.9"
    with pytest.raises(AttributeError):
        spec._schema = {"properties": {"schema_version": {"const": "9.9.9"}}}
    with pytest.raises(AttributeError):
        spec.validator._schema = {"properties": {"schema_version": {"const": "9.9.9"}}}

    # Le document forgé reste refusé par le parcours normal, qui recharge le
    # registre et ne réutilise aucun objet de spécification.
    assert spec.schema["properties"]["schema_version"]["const"] == "1.2.0"


def test_public_registry_mapping_is_read_only():
    with pytest.raises(TypeError):
        APPROVED_CONTRACTS["experiment"] = ApprovedContract(
            "experiment", "9.9.9", "0" * 64, "contracts/experiment.schema.json"
        )
    assert not hasattr(APPROVED_CONTRACTS, "pop")


def test_reassigning_public_registry_alias_does_not_change_writer(
    db_v7, seeded_v7, examples, monkeypatch
):
    fake = dict(APPROVED_CONTRACTS)
    fake["experiment"] = ApprovedContract(
        "experiment", "9.9.9", "0" * 64, "contracts/experiment.schema.json"
    )
    monkeypatch.setattr(registry_module, "APPROVED_CONTRACTS", fake)

    document = _experiment_document(examples)
    document["schema_version"] = "9.9.9"
    db_v7.commit()
    before = _count(db_v7, "experiments")
    with pytest.raises(ContractVersionError):
        write_experiment(db_v7, document)
    assert _count(db_v7, "experiments") == before


def test_modified_schema_on_disk_without_registry_update_is_refused(
    db_v7, seeded_v7, examples, monkeypatch, tmp_path
):
    original_root = registry_module.ROOT
    contracts = tmp_path / "contracts"
    contracts.mkdir()
    target = contracts / "experiment.schema.json"
    shutil.copyfile(original_root / "contracts" / "experiment.schema.json", target)
    text = target.read_text(encoding="utf-8")
    target.write_text(
        text.replace('"const": "1.2.0"', '"const": "9.9.9"'),
        encoding="utf-8",
    )
    monkeypatch.setattr(registry_module, "ROOT", tmp_path)

    document = _experiment_document(examples)
    db_v7.commit()
    before = _count(db_v7, "experiments")
    with pytest.raises(ContractApprovalError) as raised:
        write_experiment(db_v7, document)
    assert isinstance(raised.value.__cause__, ContractHashMismatchError)
    assert _count(db_v7, "experiments") == before


def test_from_approved_normalizes_unknown_registry_name():
    with pytest.raises(ContractApprovalError) as raised:
        ContractSpec.from_approved("unknown_contract")
    assert isinstance(raised.value.__cause__, ContractNotRegisteredError)


def test_from_approved_normalizes_missing_schema_file(monkeypatch, tmp_path):
    monkeypatch.setattr(registry_module, "ROOT", tmp_path)
    with pytest.raises(ContractApprovalError) as raised:
        ContractSpec.from_approved("experiment")
    assert isinstance(raised.value.__cause__, ContractSchemaMissingError)


def test_from_approved_normalizes_malformed_schema(monkeypatch, tmp_path):
    contracts = tmp_path / "contracts"
    contracts.mkdir()
    broken = contracts / "broken.json"
    broken.write_text("{not valid json", encoding="utf-8")
    digest = hashlib.sha256(broken.read_bytes()).hexdigest()
    entry = ApprovedContract(
        "experiment", "1.2.0", digest, "contracts/broken.json"
    )
    monkeypatch.setattr(registry_module, "_APPROVED_CONTRACTS", (entry,))
    monkeypatch.setattr(registry_module, "ROOT", tmp_path)

    with pytest.raises(ContractApprovalError) as raised:
        ContractSpec.from_approved("experiment")
    assert isinstance(raised.value.__cause__, ContractSchemaMalformedError)


def test_from_approved_normalizes_bad_hash(monkeypatch, tmp_path):
    contracts = tmp_path / "contracts"
    contracts.mkdir()
    target = contracts / "experiment.schema.json"
    target.write_text('{"properties": {}}', encoding="utf-8")
    monkeypatch.setattr(registry_module, "ROOT", tmp_path)

    with pytest.raises(ContractApprovalError) as raised:
        ContractSpec.from_approved("experiment")
    assert isinstance(raised.value.__cause__, ContractHashMismatchError)


def test_from_approved_normalizes_version_mismatch(monkeypatch, tmp_path):
    contracts = tmp_path / "contracts"
    contracts.mkdir()
    target = contracts / "version.json"
    target.write_text(
        '{"properties": {"schema_version": {"const": "9.9.9"}}}',
        encoding="utf-8",
    )
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    entry = ApprovedContract(
        "experiment", "1.2.0", digest, "contracts/version.json"
    )
    monkeypatch.setattr(registry_module, "_APPROVED_CONTRACTS", (entry,))
    monkeypatch.setattr(registry_module, "ROOT", tmp_path)

    from polymarket_lab.validation.registry import ContractVersionMismatchError

    with pytest.raises(ContractApprovalError) as raised:
        ContractSpec.from_approved("experiment")
    assert isinstance(raised.value.__cause__, ContractVersionMismatchError)


def test_writer_rejects_connection_with_foreign_keys_off(
    db_v7, seeded_v7, examples
):
    db_v7.commit()
    document = _experiment_document(examples)
    document["strategy"]["strategy_id"] = "strategy_missing"
    before = _count(db_v7, "experiments")
    db_v7.execute("PRAGMA foreign_keys = OFF")
    try:
        with pytest.raises(ContractConnectionError):
            write_experiment(db_v7, document)
    finally:
        db_v7.execute("PRAGMA foreign_keys = ON")
    assert _count(db_v7, "experiments") == before
    assert db_v7.execute("PRAGMA foreign_keys").fetchone()[0] == 1


def test_writer_rejects_connection_with_recursive_triggers_off(
    db_v7, seeded_v7, examples
):
    db_v7.commit()
    document = _experiment_document(examples)
    before = _count(db_v7, "experiments")
    db_v7.execute("PRAGMA recursive_triggers = OFF")
    try:
        with pytest.raises(ContractConnectionError):
            write_experiment(db_v7, document)
    finally:
        db_v7.execute("PRAGMA recursive_triggers = ON")
    assert _count(db_v7, "experiments") == before
    assert db_v7.execute("PRAGMA recursive_triggers").fetchone()[0] == 1


def test_writer_rejects_non_none_isolation_level(
    db_v7, seeded_v7, examples
):
    db_v7.commit()
    document = _experiment_document(examples)
    before = _count(db_v7, "experiments")
    db_v7.isolation_level = ""
    try:
        with pytest.raises(ContractConnectionError):
            write_experiment(db_v7, document)
    finally:
        db_v7.isolation_level = None
    assert _count(db_v7, "experiments") == before


def test_standard_row_factory_none_is_accepted(
    db_v7, seeded_v7, examples
):
    db_v7.commit()
    db_v7.row_factory = None
    try:
        write_experiment(db_v7, _experiment_document(examples))
    finally:
        db_v7.row_factory = sqlite3.Row
    assert db_v7.execute(
        "SELECT COUNT(*) FROM experiments WHERE experiment_id = 'exp_writer_001'"
    ).fetchone()[0] == 1


def test_writer_rejects_missing_fk_with_foreign_keys_on(
    db_v7, seeded_v7, examples
):
    db_v7.commit()
    document = _experiment_document(examples)
    document["strategy"]["strategy_id"] = "strategy_missing"
    before = _count(db_v7, "experiments")
    with pytest.raises(ContractSQLiteError):
        write_experiment(db_v7, document)
    assert _count(db_v7, "experiments") == before
    assert db_v7.execute("PRAGMA foreign_key_check").fetchall() == []


def test_open_connection_satisfies_writer_requirements(db_v7):
    assert db_v7.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    assert db_v7.execute("PRAGMA recursive_triggers").fetchone()[0] == 1
    assert db_v7.execute("PRAGMA ignore_check_constraints").fetchone()[0] == 0
    assert db_v7.isolation_level is None
    assert db_v7.in_transaction is False
    assert db_v7.row_factory is sqlite3.Row


def test_writer_rejects_ignore_check_constraints_on(
    db_v7, seeded_v7, examples
):
    db_v7.commit()
    document = _experiment_document(examples)
    document["capital"]["presentation_currency"] = "USD"
    document["capital"]["presentation_conversion"] = None
    before = _count(db_v7, "experiments")
    db_v7.execute("PRAGMA ignore_check_constraints = ON")
    try:
        with pytest.raises(ContractConnectionError):
            write_experiment(db_v7, document)
        # Le writer ne modifie pas le pragma de l'appelant.
        assert db_v7.execute("PRAGMA ignore_check_constraints").fetchone()[0] == 1
    finally:
        db_v7.execute("PRAGMA ignore_check_constraints = OFF")
    assert _count(db_v7, "experiments") == before


def test_ignore_check_constraints_off_allows_normal_path(
    db_v7, seeded_v7, examples
):
    assert db_v7.execute("PRAGMA ignore_check_constraints").fetchone()[0] == 0
    write_experiment(db_v7, _experiment_document(examples))
    assert db_v7.execute(
        "SELECT COUNT(*) FROM experiments WHERE experiment_id = 'exp_writer_001'"
    ).fetchone()[0] == 1


def test_connection_subclass_is_refused(examples):
    class ConnectionSubclass(sqlite3.Connection):
        pass

    connection = sqlite3.connect(":memory:", factory=ConnectionSubclass)
    try:
        with pytest.raises(ContractConnectionError):
            write_experiment(connection, _experiment_document(examples))
    finally:
        connection.close()


def test_custom_row_factory_is_refused_before_validation(
    db_v7, seeded_v7, examples
):
    db_v7.commit()
    document = _experiment_document(examples)
    before = _count(db_v7, "experiments")
    db_v7.row_factory = lambda cursor, row: (1,)
    try:
        with pytest.raises(ContractConnectionError):
            write_experiment(db_v7, document)
    finally:
        db_v7.row_factory = sqlite3.Row
    assert _count(db_v7, "experiments") == before


def test_falsified_row_factory_cannot_hide_foreign_keys_off(
    db_v7, seeded_v7, examples
):
    db_v7.commit()
    document = _experiment_document(examples)
    document["strategy"]["strategy_id"] = "strategy_missing"
    before = _count(db_v7, "experiments")
    db_v7.execute("PRAGMA foreign_keys = OFF")
    db_v7.row_factory = lambda cursor, row: (1,)
    try:
        with pytest.raises(ContractConnectionError):
            write_experiment(db_v7, document)
    finally:
        db_v7.row_factory = sqlite3.Row
    actual_foreign_keys = db_v7.execute("PRAGMA foreign_keys").fetchone()[0]
    db_v7.execute("PRAGMA foreign_keys = ON")
    assert actual_foreign_keys == 0
    assert _count(db_v7, "experiments") == before


def test_writer_refuses_existing_transaction_without_touching_it(
    db_v7, seeded_v7, examples
):
    db_v7.commit()
    db_v7.execute("BEGIN IMMEDIATE")
    before = _count(db_v7, "experiments")
    try:
        with pytest.raises(ContractConnectionError):
            write_experiment(db_v7, _experiment_document(examples))
        assert db_v7.in_transaction is True
        assert _count(db_v7, "experiments") == before
    finally:
        db_v7.rollback()


def test_writer_does_not_modify_historical_rows(
    db_v7, seeded_v7, examples
):
    db_v7.commit()
    before = db_v7.execute(
        "SELECT * FROM experiments WHERE experiment_id = 'exp_fixture_001'"
    ).fetchone()
    write_experiment(db_v7, _experiment_document(examples))
    after = db_v7.execute(
        "SELECT * FROM experiments WHERE experiment_id = 'exp_fixture_001'"
    ).fetchone()
    assert tuple(after) == tuple(before)


def test_two_writer_calls_are_not_one_transaction(
    db_v7, seeded_v7, examples
):
    db_v7.commit()
    fee = _fee_document(examples)
    write_fee_schedule(db_v7, fee)
    bad_experiment = _experiment_document(examples)
    bad_experiment["strategy"]["strategy_id"] = "strategy_missing"
    with pytest.raises(ContractSQLiteError):
        write_experiment(db_v7, bad_experiment)
    # Le premier writer a déjà commité : ce n'est pas une transaction de groupe.
    assert db_v7.execute(
        "SELECT COUNT(*) FROM fee_schedules WHERE fee_schedule_id = 'fee_writer_001'"
    ).fetchone()[0] == 1
    assert db_v7.execute(
        "SELECT COUNT(*) FROM experiments WHERE experiment_id = 'exp_writer_001'"
    ).fetchone()[0] == 0


def test_contract_spec_from_approved_registry_writes(
    db_v7, seeded_v7, examples
):
    spec = ContractSpec.from_approved("experiment")
    assert spec.approval.version == "1.2.0"
    db_v7.commit()
    write_experiment(db_v7, _experiment_document(examples))
    row = db_v7.execute(
        "SELECT schema_version FROM experiments WHERE experiment_id = ?",
        ("exp_writer_001",),
    ).fetchone()
    assert row[0] == spec.version


def test_test_path_is_explicit_and_normal_path_never_accepts_test_spec(
    db_v7, seeded_v7, schemas, validators, examples
):
    spec = _test_fee_spec(schemas, validators)
    document = _fee_document(examples)
    db_v7.commit()
    with pytest.raises(TypeError):
        write_fee_schedule(db_v7, document, spec)

    write_fee_schedule_for_tests(db_v7, document, spec)
    assert db_v7.execute(
        "SELECT COUNT(*) FROM fee_schedules WHERE fee_schedule_id = 'fee_writer_001'"
    ).fetchone()[0] == 1


def test_custom_schema_is_exercised_only_through_test_path(
    db_v7, seeded_v7, schemas, examples
):
    schema = copy.deepcopy(schemas["experiment"])
    schema["properties"]["schema_version"]["const"] = "9.9.9"
    spec = TestContractSpec(
        "experiment", schema, Draft202012Validator(schema)
    )
    document = _experiment_document(examples)
    document["experiment_id"] = "exp_writer_custom"
    document["schema_version"] = "9.9.9"
    db_v7.commit()

    write_experiment_for_tests(db_v7, document, spec)
    assert db_v7.execute(
        "SELECT schema_version FROM experiments WHERE experiment_id = 'exp_writer_custom'"
    ).fetchone()[0] == "9.9.9"

    forged = _experiment_document(examples)
    forged["experiment_id"] = "exp_writer_forged"
    forged["schema_version"] = "9.9.9"
    with pytest.raises(ContractVersionError):
        write_experiment(db_v7, forged)
    assert db_v7.execute(
        "SELECT COUNT(*) FROM experiments WHERE experiment_id = 'exp_writer_forged'"
    ).fetchone()[0] == 0


def test_permissive_validator_is_confined_to_explicit_test_path(
    db_v7, seeded_v7, schemas, examples
):
    class PermissiveValidator:
        schema = copy.deepcopy(schemas["experiment"])

        def iter_errors(self, instance):
            return []

    spec = TestContractSpec(
        "experiment", copy.deepcopy(schemas["experiment"]), PermissiveValidator()
    )
    document = _experiment_document(examples)
    document["experiment_id"] = "exp_writer_permissive"
    document["code_version"] = ""
    db_v7.commit()
    write_experiment_for_tests(db_v7, document, spec)
    assert db_v7.execute(
        "SELECT COUNT(*) FROM experiments WHERE experiment_id = 'exp_writer_permissive'"
    ).fetchone()[0] == 1

    rejected = _experiment_document(examples)
    rejected["experiment_id"] = "exp_writer_rejected"
    rejected["code_version"] = ""
    before = _count(db_v7, "experiments")
    with pytest.raises(ContractSchemaError):
        write_experiment(db_v7, rejected)
    assert _count(db_v7, "experiments") == before


def test_multi_error_document_prioritizes_schema_over_version(
    examples, schemas, validators
):
    document = _experiment_document(examples)
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


def test_schema_unreadable_is_normalized_and_writes_no_row(
    db_v7, seeded_v7, examples, monkeypatch, tmp_path
):
    contracts = tmp_path / "contracts"
    contracts.mkdir()
    # Un répertoire au chemin du fichier force Path.read_bytes() à lever une
    # OSError réelle sans dépendre des permissions Windows.
    (contracts / "experiment.schema.json").mkdir()
    monkeypatch.setattr(registry_module, "ROOT", tmp_path)

    document = _experiment_document(examples)
    db_v7.commit()
    before = _count(db_v7, "experiments")
    with pytest.raises(ContractApprovalError) as raised:
        write_experiment(db_v7, document)
    assert raised.value.category == "approval"
    assert isinstance(raised.value.__cause__, ContractSchemaUnreadableError)
    assert isinstance(raised.value.__cause__.__cause__, OSError)
    assert _count(db_v7, "experiments") == before


def test_schema_mismatch_is_detected_directly():
    schema, _ = load_approved_schema("experiment")
    mutated = dict(schema)
    mutated["title"] = "mutated"
    with pytest.raises(ContractSchemaMismatchError):
        verify_approved_schema("experiment", mutated)


def test_schema_mismatch_during_final_check_rolls_back(
    db_v7, seeded_v7, examples, monkeypatch
):
    def reject(*args, **kwargs):
        raise ContractSchemaMismatchError("forced mismatch")

    monkeypatch.setattr(writer_module, "verify_approved_schema", reject)
    document = _experiment_document(examples)
    db_v7.commit()
    before = _count(db_v7, "experiments")
    with pytest.raises(ContractApprovalError) as raised:
        write_experiment(db_v7, document)
    assert raised.value.category == "approval"
    assert isinstance(raised.value.__cause__, ContractSchemaMismatchError)
    assert _count(db_v7, "experiments") == before
    assert db_v7.in_transaction is False


def test_final_approval_check_runs_inside_transaction(
    db_v7, seeded_v7, examples, monkeypatch
):
    original = writer_module._verify_approved_contract
    observed: list[bool] = []

    def wrapped(spec):
        observed.append(db_v7.in_transaction)
        return original(spec)

    monkeypatch.setattr(writer_module, "_verify_approved_contract", wrapped)
    db_v7.commit()
    write_experiment(db_v7, _experiment_document(examples))
    assert observed == [True]


@pytest.mark.parametrize(
    "schema,label",
    [
        (
            {
                "type": "object",
                "properties": {"schema_version": {"const": "1.2.0"}},
                "multipleOf": 0.1,
            },
            "multipleOf",
        ),
        (
            {
                "type": "object",
                "properties": {"schema_version": {"const": "1.2.0"}},
                "$ref": "#/examples/0",
                "examples": ["not a schema"],
            },
            "ref non-schéma",
        ),
        (
            {
                "type": "object",
                "properties": {"schema_version": {"const": "1.2.0"}},
                "$defs": {"a": {"$ref": "#/$defs/a"}},
                "$ref": "#/$defs/a",
            },
            "cycle de refs",
        ),
    ],
)
def test_invalid_approved_schema_is_refused_without_row(
    db_v7, seeded_v7, examples, monkeypatch, tmp_path, schema, label
):
    contracts = tmp_path / "contracts"
    contracts.mkdir()
    target = contracts / "invalid.json"
    import json

    target.write_text(json.dumps(schema), encoding="utf-8")
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    entry = ApprovedContract("experiment", "1.2.0", digest, "contracts/invalid.json")
    monkeypatch.setattr(registry_module, "_APPROVED_CONTRACTS", (entry,))
    monkeypatch.setattr(registry_module, "ROOT", tmp_path)

    document = _experiment_document(examples)
    db_v7.commit()
    before = _count(db_v7, "experiments")
    with pytest.raises(ContractApprovalError) as raised:
        write_experiment(db_v7, document)
    assert isinstance(raised.value.__cause__, UnsupportedSchemaError), label
    assert _count(db_v7, "experiments") == before
