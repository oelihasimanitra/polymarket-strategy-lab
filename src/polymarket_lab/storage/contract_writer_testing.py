"""Parcours d'écriture explicitement réservé aux tests.

Ce module est distinct du parcours normal. Il accepte un schéma et un
validateur fournis par l'appelant afin de tester des documents et des
validateurs personnalisés (schéma `9.9.9`, validateur qui lève, etc.).

Il ne constitue **pas** une frontière de sécurité : du code Python exécuté
dans le même processus peut toujours importer ce module. L'objectif est
d'empêcher un contournement accidentel du writer normal, dont l'API n'accepte
ni schéma, ni validateur, ni booléen d'activation. Aucun writer A1/A2 de
production ne doit importer ce module.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, ClassVar

from ..validation.contracts import SchemaValidator
from .contract_writer import (
    ContractSpecError,
    _check_connection,
    _execute_write,
    _experiment_values,
    _fee_values,
    _insert_experiment,
    _insert_fee_schedule,
)

__all__ = [
    "TestContractSpec",
    "write_experiment_for_tests",
    "write_fee_schedule_for_tests",
]


@dataclass(frozen=True)
class TestContractSpec:
    """Spécification de test ; jamais acceptée par le parcours normal."""

    # Empêche pytest de collecter cette classe comme classe de test lors de
    # l'import depuis les modules de test.
    __test__: ClassVar[bool] = False

    name: str
    schema: Mapping[str, Any]
    validator: SchemaValidator

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name:
            raise ContractSpecError("TestContractSpec.name doit être une chaîne non vide")
        if not isinstance(self.schema, Mapping):
            raise ContractSpecError("TestContractSpec.schema doit être un mapping")
        if not callable(getattr(self.validator, "iter_errors", None)):
            raise ContractSpecError(
                "TestContractSpec.validator doit exposer iter_errors()"
            )
        properties = self.schema.get("properties")
        if not isinstance(properties, Mapping):
            raise ContractSpecError(
                "TestContractSpec.schema.properties doit être un mapping"
            )
        version_node = properties.get("schema_version")
        if not isinstance(version_node, Mapping):
            raise ContractSpecError(
                "TestContractSpec.schema.properties.schema_version doit être un mapping"
            )
        version = version_node.get("const")
        if not isinstance(version, str) or not version:
            raise ContractSpecError(
                "TestContractSpec.schema doit épingler schema_version.const"
            )

    @property
    def version(self) -> str:
        return str(self.schema["properties"]["schema_version"]["const"])

    @property
    def approved(self) -> bool:
        return False


def write_experiment_for_tests(
    connection: sqlite3.Connection,
    document: Mapping[str, Any],
    spec: TestContractSpec,
) -> str:
    """Écrit une expérience avec un schéma de test explicite."""
    _check_connection(connection)
    return _execute_write(
        connection,
        document,
        spec,
        expected_name="experiment",
        values_builder=_experiment_values,
        table="experiments",
        key_column="experiment_id",
        insert=_insert_experiment,
        verify_approval=False,
    )


def write_fee_schedule_for_tests(
    connection: sqlite3.Connection,
    document: Mapping[str, Any],
    spec: TestContractSpec,
) -> str:
    """Écrit un barème avec un schéma de test explicite."""
    _check_connection(connection)
    return _execute_write(
        connection,
        document,
        spec,
        expected_name="fee_schedule",
        values_builder=_fee_values,
        table="fee_schedules",
        key_column="fee_schedule_id",
        insert=_insert_fee_schedule,
        verify_approval=False,
    )
