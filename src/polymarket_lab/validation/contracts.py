"""Validation applicative commune des contrats JSON.

Le point d'entrée ``validate_contract`` applique **d'abord** le validateur JSON
Schema fourni par l'appelant, puis l'extension chronologique
``x-polymarket-chronological-order``. Un validateur JSON Schema standard ne
connaît pas cette extension : il ne doit donc jamais être utilisé seul pour
valider un contrat qui la déclare.

Le writer normal n'utilise pas ce point d'entrée avec un validateur fourni par
l'appelant : il construit un ``SystemSchemaValidator`` à partir du schéma
approuvé. ``contract_issues`` reste l'implémentation commune de l'ordre
schéma → chronologie → version et fournit des catégories stables au writer.

Le module n'importe pas ``jsonschema`` : l'implémentation du schéma est
injectée.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any, Iterator, Protocol

__all__ = [
    "CHRONOLOGY_KEYWORD",
    "ContractIssue",
    "SchemaValidator",
    "SchemaValidatorError",
    "chronology_errors",
    "contract_issues",
    "validate_contract",
]

#: Extension normative déclarée par les contrats qui comparent deux champs.
CHRONOLOGY_KEYWORD = "x-polymarket-chronological-order"


class SchemaValidatorError(RuntimeError):
    """Le validateur injecté a levé une exception non contractuelle."""


class SchemaValidator(Protocol):
    """Interface minimale d'un validateur JSON Schema (ex. Draft202012Validator)."""

    def iter_errors(self, instance: Any) -> Iterable[Any]:
        """Retourne les erreurs de validation de forme."""


@dataclass(frozen=True)
class ContractIssue:
    """Erreur de validation catégorisée, dans l'ordre du parcours."""

    category: str
    message: str


def _walk_dicts(
    node: Any, path: tuple[str, ...] = ()
) -> Iterator[tuple[tuple[str, ...], Mapping[str, Any]]]:
    # Les schémas approuvés sont gelés (MappingProxyType, tuples) : accepter
    # tous les Mapping évite de perdre silencieusement l'extension
    # chronologique après le gel.
    if isinstance(node, Mapping):
        yield path, node
        for key, value in node.items():
            yield from _walk_dicts(value, path + (key,))
    elif isinstance(node, (list, tuple)):
        for index, value in enumerate(node):
            yield from _walk_dicts(value, path + (str(index),))


_REQUIRED_MESSAGE = re.compile(r"^'([^']+)' is a required property$")


def _missing_required_property(error: Any) -> str | None:
    """Retourne le champ précis manquant d'une erreur ``required``.

    ``jsonschema`` expose l'ensemble des champs requis dans
    ``validator_value``, pas seulement celui qui manque. Classer l'erreur
    entière comme « version » quand cet ensemble contient ``schema_version``
    reclasserait à tort l'absence de ``period`` ou d'un autre champ.
    """
    if getattr(error, "validator", None) != "required":
        return None
    match = _REQUIRED_MESSAGE.match(str(getattr(error, "message", "")))
    return match.group(1) if match else None


def _is_version_error(error: Any, path: tuple[str, ...]) -> bool:
    """Une erreur est de version seulement si elle concerne la version racine.

    - une erreur au chemin exact ``schema_version`` (const, type, enum) ;
    - l'absence du seul champ racine ``schema_version``.

    Les ``schema_version`` imbriqués (par exemple dans
    ``execution_assumptions``) sont des erreurs de schéma, pas des erreurs de
    version du contrat enveloppe.
    """
    if path == ("schema_version",):
        return True
    if path == () and _missing_required_property(error) == "schema_version":
        return True
    return False


def _schema_issues(
    schema_validator: SchemaValidator, document: Any
) -> tuple[list[ContractIssue], list[ContractIssue]]:
    try:
        raw_errors = list(schema_validator.iter_errors(document))
    except Exception as exc:  # noqa: BLE001 - enveloppe explicite avec cause
        raise SchemaValidatorError(
            f"le validateur de schéma a levé {type(exc).__name__}: {exc}"
        ) from exc

    schema_errors: list[ContractIssue] = []
    version_errors: list[ContractIssue] = []
    for error in raw_errors:
        path = tuple(str(part) for part in error.absolute_path)
        message = f"{'/'.join(path) or '<root>'}: {error.message}"
        issue = ContractIssue(
            "version" if _is_version_error(error, path) else "schema",
            message,
        )
        (version_errors if issue.category == "version" else schema_errors).append(
            issue
        )
    return sorted(schema_errors, key=lambda i: i.message), sorted(
        version_errors, key=lambda i: i.message
    )


def chronology_errors(document: Any, schema: Mapping[str, Any]) -> list[str]:
    """Applique l'extension chronologique déclarée par un schéma.

    La comparaison lexicographique est valide pour les timestamps canoniques
    UTC ``YYYY-MM-DDTHH:MM:SS.ffffffZ``. Une fin nulle est ignorée si
    ``allow_null_end`` est vrai ; une borne absente est laissée au schéma.
    """
    errors: list[str] = []
    for path, node in _walk_dicts(schema):
        rule = node.get(CHRONOLOGY_KEYWORD)
        if not isinstance(rule, Mapping):
            continue
        target: Any = document
        for part in rule.get("instance_path", []):
            if not isinstance(target, Mapping) or part not in target:
                target = None
                break
            target = target[part]
        if not isinstance(target, Mapping):
            continue
        start = target.get(rule.get("start_field"))
        end = target.get(rule.get("end_field"))
        if start is None:
            continue
        if end is None:
            if not rule.get("allow_null_end", False):
                errors.append(
                    f"{'/'.join(path) or '<root>'}: fin nulle interdite"
                )
            continue
        if not isinstance(start, str) or not isinstance(end, str):
            continue
        if end < start or (rule.get("strict", True) and end == start):
            errors.append(
                f"{'/'.join(path) or '<root>'}: "
                f"{rule.get('end_field')} doit être strictement postérieur à "
                f"{rule.get('start_field')}"
            )
    return errors


def contract_issues(
    document: Any,
    schema: Mapping[str, Any],
    schema_validator: SchemaValidator,
    *,
    expected_version: str | None = None,
) -> list[ContractIssue]:
    """Valide un document et retourne des erreurs catégorisées.

    Ordre de priorité explicite :

    1. erreurs de schéma (hors champ racine ``schema_version``) ;
    2. erreurs chronologiques ;
    3. erreurs de version, y compris l'absence du champ racine
       ``schema_version`` et la version attendue.

    Une catégorie antérieure court-circuite les suivantes. Ainsi un document
    qui a la fois une période inversée et une version incompatible produit une
    erreur de chronologie, conformément à l'ordre annoncé. Un document auquel
    il manque à la fois ``period`` et ``schema_version`` produit d'abord une
    erreur de schéma pour ``period`` : l'absence de ``schema_version`` ne doit
    pas reclasser les autres champs manquants.

    Les exceptions du validateur sont enveloppées dans
    ``SchemaValidatorError``.
    """
    schema_errors, version_errors = _schema_issues(schema_validator, document)
    if schema_errors:
        return schema_errors

    chronology = chronology_errors(document, schema)
    if chronology:
        return [ContractIssue("chronology", message) for message in chronology]

    if version_errors:
        return version_errors

    if expected_version is not None:
        actual = (
            document.get("schema_version")
            if isinstance(document, Mapping)
            else None
        )
        if actual != expected_version:
            return [
                ContractIssue(
                    "version",
                    f"schema_version attendu {expected_version}, reçu {actual!r}",
                )
            ]
    return []


def validate_contract(
    document: Any,
    schema: Mapping[str, Any],
    schema_validator: SchemaValidator,
) -> list[str]:
    """Valide un document : forme JSON Schema, puis extension chronologique.

    Les erreurs de schéma sont retournées seules si elles existent : la règle
    chronologique suppose des timestamps canoniques et ne doit pas produire de
    diagnostic trompeur sur un document déjà invalide. Si la forme est valide,
    les erreurs de l'extension sont ajoutées.

    L'appelant **doit** fournir le validateur du schéma effectivement utilisé.
    Aucun validateur standard n'est instancié ici.
    """
    return [issue.message for issue in contract_issues(document, schema, schema_validator)]
