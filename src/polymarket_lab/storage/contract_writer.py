"""Parcours commun d'écriture des documents contractuels dans SQLite.

Le parcours normal ne reçoit **aucun** schéma ni validateur de l'appelant. Il
charge à chaque écriture le contrat approuvé depuis le registre, vérifie son
SHA-256 et sa version, construit lui-même le validateur système, puis applique
la séquence suivante :

1. contrôle de la connexion et de ses pragmas ;
2. validation JSON Schema par le validateur système ;
3. validation chronologique ;
4. vérification de la version du contrat approuvé ;
5. contrôles métier explicitement documentés ;
6. vérification que le contrat correspond toujours à l'approbation ;
7. écriture dans une transaction ;
8. relecture et comparaison du résultat persisté.

Aucune écriture n'est commencée si l'une des étapes 1 à 6 échoue. Une erreur
SQL annule la transaction. Les erreurs sont typées pour que l'appelant puisse
distinguer connexion, schéma, chronologie, version, approbation, métier, SQL,
validateur et vérification de persistance.

Les schémas temporaires de test ne passent pas par ce module : ils utilisent
``contract_writer_testing``. Aucun booléen public ne permet d'activer un mode
test dans le writer normal.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from ..validation.contracts import (
    SchemaValidator,
    SchemaValidatorError,
    contract_issues,
)
from ..validation.registry import (
    ApprovedContract,
    ContractRegistryError,
    load_approved_schema,
    verify_approved_schema,
)
from ..validation.schema_validator import (
    SystemSchemaValidator,
    UnsupportedSchemaError,
)
from .connection import ConnectionConfigurationError, transaction

__all__ = [
    "ContractApprovalError",
    "ContractBusinessError",
    "ContractChronologyError",
    "ContractConnectionError",
    "ContractPersistenceError",
    "ContractSchemaError",
    "ContractSQLiteError",
    "ContractSpec",
    "ContractSpecError",
    "ContractValidatorError",
    "ContractVersionError",
    "ContractWriteError",
    "write_experiment",
    "write_fee_schedule",
]


class ContractWriteError(ValueError):
    """Base des refus du writer, avec une catégorie stable."""

    category = "contract"

    def __init__(self, message: str, *, issues: tuple[str, ...] = ()) -> None:
        super().__init__(message)
        self.issues = issues


class ContractSpecError(ContractWriteError):
    category = "spec"


class ContractApprovalError(ContractWriteError):
    category = "approval"


class ContractConnectionError(ContractWriteError):
    category = "connection"


class ContractSchemaError(ContractWriteError):
    category = "schema"


class ContractChronologyError(ContractWriteError):
    category = "chronology"


class ContractVersionError(ContractWriteError):
    category = "version"


class ContractBusinessError(ContractWriteError):
    category = "business"


class ContractValidatorError(ContractWriteError):
    category = "validator"


class ContractSQLiteError(ContractWriteError):
    category = "sql"


class ContractPersistenceError(ContractWriteError):
    category = "persistence"


_APPROVED_SPEC_TOKEN = object()


@dataclass(frozen=True)
class _ApprovedParts:
    name: str
    schema: Mapping[str, Any]
    validator: SystemSchemaValidator
    approval: ApprovedContract


class ContractSpec:
    """Contrat approuvé, immuable, construit par le système.

    Le constructeur exige un jeton privé. Le seul chemin public est
    ``ContractSpec.from_approved(name)``, qui ne prend ni schéma ni validateur.
    Il n'existe donc pas de paramètre permettant à un appelant de fournir un
    validateur permissif et de le déclarer approuvé.

    Le schéma et ``validator.schema`` sont des vues profondément gelées. Une
    mutation ordinaire lève ``TypeError``. Le writer normal ne réutilise pas
    cet objet entre deux écritures : il recharge le registre à chaque appel.
    """

    __slots__ = ("_approval", "_name", "_schema", "_validator")

    def __init__(self, *, _token: object, parts: _ApprovedParts) -> None:
        if _token is not _APPROVED_SPEC_TOKEN:
            raise ContractSpecError(
                "ContractSpec ne peut pas être construit directement ; "
                "utiliser ContractSpec.from_approved"
            )
        object.__setattr__(self, "_name", parts.name)
        object.__setattr__(self, "_schema", parts.schema)
        object.__setattr__(self, "_validator", parts.validator)
        object.__setattr__(self, "_approval", parts.approval)

    def __setattr__(self, name: str, value: Any) -> None:
        raise AttributeError("ContractSpec est immuable")

    @classmethod
    def from_approved(cls, name: str) -> "ContractSpec":
        """Charge le contrat approuvé et construit son validateur système.

        Aucun schéma, validateur ou chemin de racine n'est accepté. Toute
        erreur de registre ou de schéma est normalisée en
        ``ContractApprovalError`` avec la cause d'origine, afin qu'un appelant
        qui attrape la famille ``ContractWriteError`` ne reçoive pas une
        exception de registre brute.
        """
        try:
            schema, approval = load_approved_schema(name)
            validator = SystemSchemaValidator(schema, name=name)
        except (ContractRegistryError, UnsupportedSchemaError) as exc:
            raise ContractApprovalError(
                f"contrat approuvé inutilisable pour {name!r}: {exc}"
            ) from exc
        return cls(
            _token=_APPROVED_SPEC_TOKEN,
            parts=_ApprovedParts(
                name=name,
                schema=schema,
                validator=validator,
                approval=approval,
            ),
        )

    @property
    def name(self) -> str:
        return self._name

    @property
    def schema(self) -> Mapping[str, Any]:
        return self._schema

    @property
    def validator(self) -> SystemSchemaValidator:
        return self._validator

    @property
    def approval(self) -> ApprovedContract:
        return self._approval

    @property
    def approved(self) -> bool:
        return True

    @property
    def version(self) -> str:
        return str(self._schema["properties"]["schema_version"]["const"])

    @property
    def schema_sha256(self) -> str:
        return self._approval.schema_sha256

    def __repr__(self) -> str:
        return (
            f"ContractSpec(name={self._name!r}, version={self.version!r}, "
            f"sha256={self.schema_sha256!r})"
        )


def _check_connection(connection: sqlite3.Connection) -> None:
    """Refuse une connexion non conforme sans modifier aucun de ses pragmas.

    ``row_factory`` est volontairement restreint à ``None`` ou
    ``sqlite3.Row``. Un callable arbitraire peut falsifier la lecture des
    pragmas ; plutôt que de lire des valeurs contrôlées par l'appelant, le
    writer refuse la configuration. Le type exact de connexion est également
    exigé : une sous-classe peut redéfinir ``execute``.
    """
    if not isinstance(connection, sqlite3.Connection):
        raise ContractConnectionError("le writer exige une connexion sqlite3")
    if type(connection) is not sqlite3.Connection:
        raise ContractConnectionError(
            "le writer exige une connexion sqlite3.Connection exacte ; "
            "les sous-classes ne sont pas prises en charge"
        )
    if connection.row_factory is not None and connection.row_factory is not sqlite3.Row:
        raise ContractConnectionError(
            "row_factory personnalisé refusé : utiliser None ou sqlite3.Row"
        )
    try:
        if connection.in_transaction:
            raise ContractConnectionError(
                "transaction déjà ouverte sur la connexion ; le writer ne "
                "l'annule pas et exige un appel hors transaction"
            )
        if connection.isolation_level is not None:
            raise ContractConnectionError(
                "isolation_level doit être None ; utiliser open_connection"
            )
        foreign_keys = _pragma(connection, "foreign_keys")
        recursive = _pragma(connection, "recursive_triggers")
        ignore_checks = _pragma(connection, "ignore_check_constraints")
    except sqlite3.Error as exc:
        raise ContractConnectionError(
            f"connexion SQLite non inspectable: {exc}"
        ) from exc
    if foreign_keys != 1:
        raise ContractConnectionError("PRAGMA foreign_keys doit être ON")
    if recursive != 1:
        raise ContractConnectionError("PRAGMA recursive_triggers doit être ON")
    if ignore_checks != 0:
        raise ContractConnectionError(
            "PRAGMA ignore_check_constraints doit être OFF"
        )


def _pragma(connection: sqlite3.Connection, name: str) -> int:
    # Les appels ne viennent que de _check_connection, avec des noms constants.
    row = connection.execute(f"PRAGMA {name}").fetchone()
    if row is None:
        raise ContractConnectionError(f"PRAGMA {name} illisible")
    return int(row[0])


def _issue_messages(issues: list[Any]) -> tuple[str, ...]:
    return tuple(issue.message for issue in issues)


def _raise_issues(issues: list[Any]) -> None:
    categories = {issue.category for issue in issues}
    if "schema" in categories:
        raise ContractSchemaError(
            "document invalide selon le schéma JSON",
            issues=_issue_messages(issues),
        )
    if "chronology" in categories:
        raise ContractChronologyError(
            "période chronologique invalide",
            issues=_issue_messages(issues),
        )
    if "version" in categories:
        raise ContractVersionError(
            "version de contrat incompatible",
            issues=_issue_messages(issues),
        )
    raise ContractValidatorError(
        "validateur: catégorie d'erreur inconnue",
        issues=_issue_messages(issues),
    )


def _validate_document(spec: Any, document: Any) -> None:
    try:
        issues = contract_issues(
            document,
            spec.schema,
            spec.validator,
            expected_version=spec.version,
        )
    except SchemaValidatorError as exc:
        raise ContractValidatorError(
            f"exception du validateur de schéma: {exc}"
        ) from exc
    if issues:
        _raise_issues(issues)
    if not isinstance(document, Mapping):
        raise ContractSchemaError("le document doit être un objet JSON")


def _verify_approved_contract(spec: ContractSpec) -> None:
    """Vérifie l'approbation au plus près de l'insertion.

    Le registre et le fichier sont relus. Si le schéma sur disque a changé
    depuis le chargement, ou si le validateur système ne correspond plus au
    schéma gelé, l'écriture est refusée avant toute insertion.
    """
    if not spec.approved:
        raise ContractApprovalError("contrat non approuvé pour l'écriture")
    if not isinstance(spec.validator, SystemSchemaValidator):
        raise ContractApprovalError(
            "le validateur d'un contrat approuvé doit être construit par le système"
        )
    if spec.validator.schema != spec.schema:
        raise ContractApprovalError(
            "le validateur système ne correspond plus au schéma approuvé"
        )
    try:
        verify_approved_schema(spec.name, spec.schema)
    except ContractRegistryError as exc:
        raise ContractApprovalError(
            f"approbation du contrat {spec.name!r} invalide à l'écriture: {exc}"
        ) from exc


def _business_issues(spec: Any, document: Mapping[str, Any]) -> list[str]:
    business: list[str] = []
    if spec.name == "experiment":
        period = document.get("period", {})
        if period.get("type") == "paper_live" and "end_time" not in period:
            business.append("paper_live exige la clé period.end_time, même nulle")
        status = document.get("status")
        completed_at = document.get("completed_at")
        if status in {"completed", "aborted", "invalid"} and completed_at is None:
            business.append("completed_at obligatoire pour ce statut")
        if status in {"planned", "running"} and completed_at is not None:
            business.append("completed_at interdit pour ce statut")
    return business


def _json(value: Any) -> str | None:
    if value is None:
        return None
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _experiment_values(document: Mapping[str, Any]) -> dict[str, Any]:
    period = document["period"]
    capital = document["capital"]
    data = document["data"]
    assumptions = document["execution_assumptions"]
    fees = document["fees"]
    strategy = document["strategy"]
    return {
        "experiment_id": document["experiment_id"],
        "schema_version": document["schema_version"],
        "strategy_id": strategy["strategy_id"],
        "strategy_version": strategy["version"],
        "period_type": period["type"],
        "start_time": period["start_time"],
        # La clé doit exister, même si sa valeur est NULL (paper_live).
        "end_time": period["end_time"],
        "initial_capital_micros": capital["initial_micros"],
        "accounting_unit": capital["accounting_unit"],
        "presentation_currency": capital["presentation_currency"],
        "presentation_conversion_json": _json(
            capital.get("presentation_conversion")
        ),
        "data_manifest_id": data["manifest_id"],
        "code_version": document["code_version"],
        "config_hash": document["config_hash"],
        "execution_assumptions_json": _json(assumptions),
        "risk_limits_json": _json(document["risk_limits"]),
        "default_fee_schedule_id": fees["default_fee_schedule_id"],
        "fee_status": fees["status"],
        "random_seed": assumptions["random_seed"],
        "status": document["status"],
        "created_at": document["created_at"],
        "completed_at": document.get("completed_at"),
        "config_hash_version": document["config_hash_version"],
        "experiment_config_json": _json(document),
    }


def _fee_values(document: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "fee_schedule_id": document["fee_schedule_id"],
        "schema_version": document["schema_version"],
        "verification_status": document["verification_status"],
        "source_url": document["source_url"],
        "source_title": document.get("source_title"),
        "source_retrieved_at": document["source_retrieved_at"],
        "effective_from": document["effective_from"],
        "effective_to": document.get("effective_to"),
        "scope_type": document["scope_type"],
        "scope_value": document["scope_value"],
        "scope_evidence_ref": document.get("scope_evidence_ref"),
        "accounting_unit": document["accounting_unit"],
        "maker_rate_micros": document["maker_rate_micros"],
        "taker_rate_micros": document["taker_rate_micros"],
        "fee_formula": document["fee_formula"],
        "formula_definition_ref": document.get("formula_definition_ref"),
        "custom_formula_ref": None,
        "fee_charge_unit": document["fee_charge_unit"],
        "rounding_rule": document["rounding_rule"],
        "rounding_increment_micros": document["rounding_increment_micros"],
        "notes": document["notes"],
        "supersedes_fee_schedule_id": document.get("supersedes_fee_schedule_id"),
        "created_at": document["created_at"],
    }


def _insert_experiment(
    connection: sqlite3.Connection, values: Mapping[str, Any]
) -> None:
    columns = (
        "experiment_id", "schema_version", "strategy_id", "strategy_version",
        "period_type", "start_time", "end_time", "initial_capital_micros",
        "accounting_unit", "presentation_currency", "presentation_conversion_json",
        "data_manifest_id", "code_version", "config_hash",
        "execution_assumptions_json", "risk_limits_json",
        "default_fee_schedule_id", "fee_status", "random_seed", "status",
        "created_at", "completed_at", "config_hash_version", "experiment_config_json",
    )
    placeholders = ", ".join("?" for _ in columns)
    connection.execute(
        f"INSERT INTO experiments({', '.join(columns)}) VALUES ({placeholders})",
        tuple(values[name] for name in columns),
    )


def _insert_fee_schedule(
    connection: sqlite3.Connection, values: Mapping[str, Any]
) -> None:
    columns = (
        "fee_schedule_id", "schema_version", "verification_status", "source_url",
        "source_title", "source_retrieved_at", "effective_from", "effective_to",
        "scope_type", "scope_value", "scope_evidence_ref", "accounting_unit",
        "maker_rate_micros", "taker_rate_micros", "fee_formula",
        "formula_definition_ref", "custom_formula_ref", "fee_charge_unit",
        "rounding_rule", "rounding_increment_micros", "notes",
        "supersedes_fee_schedule_id", "created_at",
    )
    placeholders = ", ".join("?" for _ in columns)
    connection.execute(
        f"INSERT INTO fee_schedules({', '.join(columns)}) VALUES ({placeholders})",
        tuple(values[name] for name in columns),
    )


def _verify_row(
    connection: sqlite3.Connection,
    *,
    table: str,
    key_column: str,
    key_value: str,
    values: Mapping[str, Any],
) -> None:
    columns = tuple(values)
    row = connection.execute(
        f"SELECT {', '.join(columns)} FROM {table} WHERE {key_column} = ?",
        (key_value,),
    ).fetchone()
    if row is None:
        raise ContractPersistenceError(
            f"{table}: ligne {key_value!r} absente après insertion"
        )
    mismatches = [
        f"{column}: attendu {values[column]!r}, persisté {actual!r}"
        for column, actual in zip(columns, row, strict=True)
        if values[column] != actual
    ]
    if mismatches:
        raise ContractPersistenceError(
            f"{table}: résultat persisté différent du document validé",
            issues=tuple(mismatches),
        )


def _execute_write(
    connection: sqlite3.Connection,
    document: Mapping[str, Any],
    spec: Any,
    *,
    expected_name: str,
    values_builder: Callable[[Mapping[str, Any]], dict[str, Any]],
    table: str,
    key_column: str,
    insert: Callable[[sqlite3.Connection, Mapping[str, Any]], None],
    verify_approval: bool,
) -> str:
    """Séquence commune aux parcours normal et test explicite."""
    if spec.name != expected_name:
        raise ContractBusinessError(
            f"writer {expected_name} utilisé avec le contrat {spec.name!r}"
        )
    _check_connection(connection)
    _validate_document(spec, document)
    business = _business_issues(spec, document)
    if business:
        raise ContractBusinessError(
            "contrôles métier refusés",
            issues=tuple(business),
        )
    try:
        values = values_builder(document)
    except (KeyError, TypeError) as exc:
        raise ContractBusinessError(
            f"document incomplet pour {expected_name}: {exc}"
        ) from exc

    try:
        with transaction(connection):
            if verify_approval:
                _verify_approved_contract(spec)
            insert(connection, values)
            _verify_row(
                connection,
                table=table,
                key_column=key_column,
                key_value=str(values[key_column]),
                values=values,
            )
    except ContractWriteError:
        raise
    except (sqlite3.Error, ConnectionConfigurationError) as exc:
        raise ContractSQLiteError(
            f"écriture SQLite refusée pour {expected_name}: {exc}"
        ) from exc
    return str(values[key_column])


def _write_approved(
    connection: sqlite3.Connection,
    document: Mapping[str, Any],
    *,
    expected_name: str,
    values_builder: Callable[[Mapping[str, Any]], dict[str, Any]],
    table: str,
    key_column: str,
    insert: Callable[[sqlite3.Connection, Mapping[str, Any]], None],
) -> str:
    # Contrôle de connexion d'abord, puis chargement de l'approbation.
    _check_connection(connection)
    spec = ContractSpec.from_approved(expected_name)
    return _execute_write(
        connection,
        document,
        spec,
        expected_name=expected_name,
        values_builder=values_builder,
        table=table,
        key_column=key_column,
        insert=insert,
        verify_approval=True,
    )


def write_experiment(
    connection: sqlite3.Connection,
    document: Mapping[str, Any],
) -> str:
    """Valide et écrit une expérience approuvée ; retourne ``experiment_id``.

    Le schéma et le validateur ne sont pas fournis par l'appelant : ils sont
    construits à partir du registre approuvé. Le document doit contenir
    ``period.end_time``, y compris avec la valeur ``None`` pour ``paper_live``.
    """
    return _write_approved(
        connection,
        document,
        expected_name="experiment",
        values_builder=_experiment_values,
        table="experiments",
        key_column="experiment_id",
        insert=_insert_experiment,
    )


def write_fee_schedule(
    connection: sqlite3.Connection,
    document: Mapping[str, Any],
) -> str:
    """Valide et écrit un barème approuvé ; retourne ``fee_schedule_id``."""
    return _write_approved(
        connection,
        document,
        expected_name="fee_schedule",
        values_builder=_fee_values,
        table="fee_schedules",
        key_column="fee_schedule_id",
        insert=_insert_fee_schedule,
    )
