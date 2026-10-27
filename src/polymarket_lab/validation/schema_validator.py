"""Validateur JSON Schema construit par le système, sans dépendance externe.

Le writer ne peut pas déclarer approuvé un validateur fourni par l'appelant :
il construit ce validateur à partir du schéma gelé du registre. Cette
implémentation couvre volontairement un sous-ensemble explicite de
JSON Schema 2020-12, celui utilisé par les contrats approuvés. Tout mot-clé
d'assertion non pris en charge est refusé à la construction
(``UnsupportedSchemaError``) au lieu d'être ignoré silencieusement.
``multipleOf`` est volontairement refusé : sa sémantique décimale divergeait
de ``jsonschema`` sur les flottants (A5-C2-01). Les ``$ref`` locales sont
résolues et vérifiées à la construction ; les cibles non-schéma et les cycles
sont refusés (A5-C2-02).

Limite importante : ce n'est pas une implémentation complète de JSON Schema.
La décision d'adopter ce validateur en production, ou d'ajouter
``jsonschema`` comme dépendance épinglée, relève du propriétaire du projet.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Iterator

from .immutability import freeze_json

__all__ = [
    "SchemaValidationIssue",
    "SystemSchemaValidator",
    "UnsupportedSchemaError",
]

#: Annotations sans effet sur la validité. Les ignorer ne change pas le résultat.
_ANNOTATIONS = frozenset(
    {
        "$schema",
        "$id",
        "title",
        "description",
        "$comment",
        "default",
        "examples",
        "deprecated",
        "readOnly",
        "writeOnly",
        # Extension normative du laboratoire : un validateur JSON Schema
        # standard l'ignore ; elle est appliquée séparément par contract_issues.
        "x-polymarket-chronological-order",
    }
)

_SCALAR_KEYWORDS = frozenset(
    {
        "const",
        "enum",
        "pattern",
        "minLength",
        "maxLength",
        "minimum",
        "maximum",
        "exclusiveMinimum",
        "exclusiveMaximum",
        "uniqueItems",
        "minItems",
        "maxItems",
        "minProperties",
        "maxProperties",
    }
)

_SCHEMA_KEYWORDS = frozenset(
    {"additionalProperties", "items", "if", "then", "else", "contains", "not"}
)

_JSON_TYPES = frozenset(
    {"object", "array", "string", "number", "integer", "boolean", "null"}
)


class UnsupportedSchemaError(RuntimeError):
    """Le schéma utilise un mot-clé ou une construction non supporté."""


@dataclass(frozen=True)
class SchemaValidationIssue:
    """Erreur de validation avec l'interface minimale de ``jsonschema``.

    ``absolute_path`` est exposé comme une propriété pour que
    ``validation.contracts`` puisse traiter les erreurs du validateur système
    comme celles de ``jsonschema``.
    """

    message: str
    path: tuple[str, ...] = ()
    validator: str = ""
    validator_value: Any = None

    @property
    def absolute_path(self) -> tuple[str, ...]:
        return self.path

    def __str__(self) -> str:
        prefix = "/".join(self.path)
        return f"{prefix or '<root>'}: {self.message}"


def _kind(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, (list, tuple)):
        return "array"
    if isinstance(value, Mapping):
        return "object"
    return "other"


def _json_equal(left: Any, right: Any) -> bool:
    """Égalité JSON : 1 et 1.0 sont égaux, ``true`` et 1 ne le sont pas."""
    left_kind = _kind(left)
    right_kind = _kind(right)
    if left_kind == "number" and right_kind == "number":
        return left == right
    if left_kind != right_kind:
        return False
    if left_kind == "array":
        return len(left) == len(right) and all(
            _json_equal(a, b) for a, b in zip(left, right, strict=True)
        )
    if left_kind == "object":
        return set(left) == set(right) and all(
            _json_equal(left[key], right[key]) for key in left
        )
    return left == right


def _matches_type(instance: Any, expected: str) -> bool:
    if expected == "object":
        return isinstance(instance, Mapping)
    if expected == "array":
        return isinstance(instance, (list, tuple))
    if expected == "string":
        return isinstance(instance, str)
    if expected == "boolean":
        return isinstance(instance, bool)
    if expected == "null":
        return instance is None
    if expected == "integer":
        if isinstance(instance, bool):
            return False
        if isinstance(instance, int):
            return True
        return isinstance(instance, float) and instance.is_integer()
    if expected == "number":
        return not isinstance(instance, bool) and isinstance(instance, (int, float))
    return False


def _resolve_pointer(root: Mapping[str, Any], ref: str) -> Any:
    if not isinstance(ref, str) or not ref.startswith("#/"):
        raise UnsupportedSchemaError(
            f"seules les références locales '#/...' sont supportées : {ref!r}"
        )
    node: Any = root
    for raw_part in ref[2:].split("/"):
        part = raw_part.replace("~1", "/").replace("~0", "~")
        if isinstance(node, Mapping):
            if part not in node:
                raise UnsupportedSchemaError(f"référence introuvable : {ref}")
            node = node[part]
        elif isinstance(node, (list, tuple)):
            try:
                node = node[int(part)]
            except (ValueError, IndexError) as exc:
                raise UnsupportedSchemaError(f"référence introuvable : {ref}") from exc
        else:
            raise UnsupportedSchemaError(f"référence introuvable : {ref}")
    return node


def _require_schema(node: Any, where: str) -> None:
    if not isinstance(node, Mapping):
        raise UnsupportedSchemaError(f"{where} doit être un schéma objet")
    _validate_schema_node(node, where)


def _validate_schema_node(node: Mapping[str, Any], where: str = "<root>") -> None:
    """Refuse à la construction tout mot-clé non supporté.

    Le parcours est conscient de la structure : les clés de ``properties`` et
    de ``$defs`` sont des noms de champs, pas des mots-clés.
    """
    for key, value in node.items():
        if key in _ANNOTATIONS:
            continue
        if key in {"properties", "$defs"}:
            if not isinstance(value, Mapping):
                raise UnsupportedSchemaError(f"{where}.{key} doit être un objet")
            for name, subschema in value.items():
                _require_schema(subschema, f"{where}.{key}.{name}")
            continue
        if key == "$ref":
            if not isinstance(value, str) or not value.startswith("#/"):
                raise UnsupportedSchemaError(
                    f"{where}.$ref doit être une référence locale '#/...'"
                )
            # La résolution effective est vérifiée par _validate_references,
            # qui dispose du schéma racine.
            continue
        if key in {"allOf", "anyOf", "oneOf"}:
            if not isinstance(value, (list, tuple)) or not value:
                raise UnsupportedSchemaError(
                    f"{where}.{key} doit être une liste non vide de schémas"
                )
            for index, subschema in enumerate(value):
                _require_schema(subschema, f"{where}.{key}[{index}]")
            continue
        if key in _SCHEMA_KEYWORDS:
            if key == "additionalProperties" and isinstance(value, bool):
                continue
            if key == "not":
                raise UnsupportedSchemaError("le mot-clé 'not' n'est pas supporté")
            if key == "contains":
                raise UnsupportedSchemaError("le mot-clé 'contains' n'est pas supporté")
            _require_schema(value, f"{where}.{key}")
            continue
        if key == "multipleOf":
            raise UnsupportedSchemaError(
                f"{where}.multipleOf n'est pas supporté : la sémantique décimale "
                "doit être tranchée avant tout usage (A5-C2-01)"
            )
        if key == "type":
            if isinstance(value, str):
                types = (value,)
            elif isinstance(value, (list, tuple)) and value:
                types = tuple(value)
            else:
                raise UnsupportedSchemaError(f"{where}.type est invalide")
            if any(not isinstance(item, str) or item not in _JSON_TYPES for item in types):
                raise UnsupportedSchemaError(f"{where}.type contient un type inconnu")
            continue
        if key == "required":
            if not isinstance(value, (list, tuple)) or any(
                not isinstance(item, str) for item in value
            ):
                raise UnsupportedSchemaError(f"{where}.required doit être une liste de chaînes")
            continue
        if key in _SCALAR_KEYWORDS:
            _validate_scalar_keyword(key, value, where)
            continue
        raise UnsupportedSchemaError(
            f"mot-clé JSON Schema non supporté dans {where} : {key!r}"
        )


def _validate_scalar_keyword(key: str, value: Any, where: str) -> None:
    if key == "pattern":
        if not isinstance(value, str):
            raise UnsupportedSchemaError(f"{where}.pattern doit être une chaîne")
        try:
            re.compile(value)
        except re.error as exc:
            raise UnsupportedSchemaError(f"{where}.pattern invalide : {exc}") from exc
        return
    if key in {"minLength", "maxLength", "minItems", "maxItems", "minProperties", "maxProperties"}:
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise UnsupportedSchemaError(f"{where}.{key} doit être un entier >= 0")
        return
    if key in {"minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum"}:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise UnsupportedSchemaError(f"{where}.{key} doit être un nombre")
        return
    if key == "uniqueItems":
        if not isinstance(value, bool):
            raise UnsupportedSchemaError(f"{where}.uniqueItems doit être un booléen")
        return
    if key == "enum":
        if not isinstance(value, (list, tuple)) or not value:
            raise UnsupportedSchemaError(f"{where}.enum doit être une liste non vide")
        return
    if key == "const":
        return
    raise UnsupportedSchemaError(f"mot-clé non supporté : {key}")


class SystemSchemaValidator:
    """Validateur construit par le système à partir du schéma approuvé."""

    __slots__ = ("_name", "_schema")

    def __init__(self, schema: Mapping[str, Any], *, name: str = "contract") -> None:
        if not isinstance(schema, Mapping):
            raise UnsupportedSchemaError("le schéma doit être un objet JSON")
        frozen = freeze_json(schema)
        assert isinstance(frozen, Mapping)
        self._validate_references(frozen)
        _validate_schema_node(frozen)
        object.__setattr__(self, "_name", name)
        object.__setattr__(self, "_schema", frozen)

    def __setattr__(self, name: str, value: Any) -> None:
        raise AttributeError("SystemSchemaValidator est immuable")

    @staticmethod
    def _validate_references(schema: Mapping[str, Any]) -> None:
        """Vérifie les ``$ref`` à la construction.

        Seules les références locales ``#/...`` sont acceptées. La cible doit
        être un schéma objet valide, et les cycles de références sont refusés :
        le validateur ne possède pas de sémantique récursive. Cette limitation
        est volontaire et fail-closed.
        """

        def visit(node: Any, active_targets: set[int]) -> None:
            if not isinstance(node, Mapping):
                return
            ref = node.get("$ref")
            if ref is not None:
                target = _resolve_pointer(schema, ref)
                if not isinstance(target, Mapping):
                    raise UnsupportedSchemaError(
                        f"la référence {ref!r} ne pointe pas un schéma objet"
                    )
                target_id = id(target)
                if target_id in active_targets:
                    raise UnsupportedSchemaError(
                        f"cycle de références détecté autour de {ref!r}"
                    )
                _validate_schema_node(target, f"$ref {ref}")
                active_targets.add(target_id)
                try:
                    visit(target, active_targets)
                finally:
                    active_targets.remove(target_id)

            for key, value in node.items():
                if key in _ANNOTATIONS or key == "$ref":
                    continue
                if key in {"properties", "$defs"}:
                    if isinstance(value, Mapping):
                        for subschema in value.values():
                            visit(subschema, active_targets)
                elif key in {"allOf", "anyOf", "oneOf"}:
                    if isinstance(value, (list, tuple)):
                        for subschema in value:
                            visit(subschema, active_targets)
                elif key in {"additionalProperties", "items", "if", "then", "else"}:
                    visit(value, active_targets)

        visit(schema, set())

    @property
    def schema(self) -> Mapping[str, Any]:
        return self._schema

    @property
    def name(self) -> str:
        return self._name

    def iter_errors(self, instance: Any) -> Iterator[SchemaValidationIssue]:
        yield from _validate(instance, self._schema, self._schema, (), depth=0)


def _error(
    message: str,
    path: tuple[str, ...],
    validator: str,
    validator_value: Any,
) -> SchemaValidationIssue:
    return SchemaValidationIssue(
        message=message,
        path=path,
        validator=validator,
        validator_value=validator_value,
    )


def _validate(
    instance: Any,
    schema: Mapping[str, Any],
    root: Mapping[str, Any],
    path: tuple[str, ...],
    *,
    depth: int,
) -> Iterator[SchemaValidationIssue]:
    if depth > 128:
        raise UnsupportedSchemaError("profondeur de schéma dépassée (référence cyclique ?)")
    if "multipleOf" in schema:
        # Défense secondaire : la construction le refuse déjà, mais une
        # mutation en mémoire ne doit pas le faire ignorer silencieusement.
        raise UnsupportedSchemaError(
            "multipleOf n'est pas supporté par le validateur système"
        )

    ref = schema.get("$ref")
    if ref is not None:
        target = _resolve_pointer(root, ref)
        if not isinstance(target, Mapping):
            raise UnsupportedSchemaError(f"la référence {ref} ne pointe pas un schéma")
        yield from _validate(instance, target, root, path, depth=depth + 1)
        siblings = {key: value for key, value in schema.items() if key != "$ref"}
        if siblings:
            yield from _validate(instance, siblings, root, path, depth=depth + 1)

    expected = schema.get("type")
    if expected is not None:
        types = (expected,) if isinstance(expected, str) else tuple(expected)
        if not any(_matches_type(instance, item) for item in types):
            label = " or ".join(types)
            yield _error(
                f"{instance!r} is not of type {label!r}",
                path,
                "type",
                expected,
            )

    if "const" in schema and not _json_equal(instance, schema["const"]):
        yield _error(
            f"{schema['const']!r} was expected",
            path,
            "const",
            schema["const"],
        )

    enum = schema.get("enum")
    if enum is not None and not any(_json_equal(instance, item) for item in enum):
        yield _error(
            f"{instance!r} is not one of {list(enum)!r}",
            path,
            "enum",
            enum,
        )

    for index, subschema in enumerate(schema.get("allOf", ())):
        yield from _validate(instance, subschema, root, path, depth=depth + 1)

    any_of = schema.get("anyOf")
    if any_of is not None:
        if not any(_is_valid(instance, subschema, root, depth + 1) for subschema in any_of):
            yield _error(
                f"{instance!r} is not valid under any of the given schemas",
                path,
                "anyOf",
                any_of,
            )

    one_of = schema.get("oneOf")
    if one_of is not None:
        matches = sum(
            1 for subschema in one_of if _is_valid(instance, subschema, root, depth + 1)
        )
        if matches != 1:
            yield _error(
                f"{instance!r} is valid under {matches} of the given schemas; "
                "exactly one is required",
                path,
                "oneOf",
                one_of,
            )

    if "if" in schema:
        if _is_valid(instance, schema["if"], root, depth + 1):
            if "then" in schema:
                yield from _validate(instance, schema["then"], root, path, depth=depth + 1)
        elif "else" in schema:
            yield from _validate(instance, schema["else"], root, path, depth=depth + 1)

    if isinstance(instance, Mapping):
        yield from _validate_object(instance, schema, root, path, depth=depth)
    if isinstance(instance, (list, tuple)):
        yield from _validate_array(instance, schema, root, path, depth=depth)
    if isinstance(instance, str):
        yield from _validate_string(instance, schema, path)
    if not isinstance(instance, bool) and isinstance(instance, (int, float)):
        yield from _validate_number(instance, schema, path)


def _is_valid(
    instance: Any,
    schema: Mapping[str, Any],
    root: Mapping[str, Any],
    depth: int,
) -> bool:
    try:
        next(_validate(instance, schema, root, (), depth=depth))
    except StopIteration:
        return True
    return False


def _validate_object(
    instance: Mapping[str, Any],
    schema: Mapping[str, Any],
    root: Mapping[str, Any],
    path: tuple[str, ...],
    *,
    depth: int,
) -> Iterator[SchemaValidationIssue]:
    required = schema.get("required")
    if required is not None:
        for name in required:
            if name not in instance:
                yield _error(
                    f"'{name}' is a required property",
                    path,
                    "required",
                    tuple(required),
                )

    properties = schema.get("properties", {})
    if not isinstance(properties, Mapping):
        raise UnsupportedSchemaError("properties doit être un objet")
    for name, subschema in properties.items():
        if name in instance:
            yield from _validate(
                instance[name],
                subschema,
                root,
                path + (str(name),),
                depth=depth + 1,
            )

    additional = schema.get("additionalProperties", True)
    extras = [name for name in instance if name not in properties]
    if additional is False:
        for name in extras:
            yield _error(
                f"Additional properties are not allowed ('{name}' was unexpected)",
                path,
                "additionalProperties",
                False,
            )
    elif isinstance(additional, Mapping):
        for name in extras:
            yield from _validate(
                instance[name],
                additional,
                root,
                path + (str(name),),
                depth=depth + 1,
            )

    minimum = schema.get("minProperties")
    if minimum is not None and len(instance) < minimum:
        yield _error(
            f"{instance!r} has less properties than the minimum of {minimum}",
            path,
            "minProperties",
            minimum,
        )
    maximum = schema.get("maxProperties")
    if maximum is not None and len(instance) > maximum:
        yield _error(
            f"{instance!r} has more properties than the maximum of {maximum}",
            path,
            "maxProperties",
            maximum,
        )


def _validate_array(
    instance: Sequence[Any],
    schema: Mapping[str, Any],
    root: Mapping[str, Any],
    path: tuple[str, ...],
    *,
    depth: int,
) -> Iterator[SchemaValidationIssue]:
    items = schema.get("items")
    if items is not None:
        if not isinstance(items, Mapping):
            raise UnsupportedSchemaError("items doit être un schéma objet")
        for index, item in enumerate(instance):
            yield from _validate(
                item,
                items,
                root,
                path + (str(index),),
                depth=depth + 1,
            )

    if schema.get("uniqueItems"):
        for left in range(len(instance)):
            for right in range(left + 1, len(instance)):
                if _json_equal(instance[left], instance[right]):
                    yield _error(
                        f"{instance!r} has non-unique elements",
                        path,
                        "uniqueItems",
                        True,
                    )
                    break

    minimum = schema.get("minItems")
    if minimum is not None and len(instance) < minimum:
        yield _error(
            f"{instance!r} is too short",
            path,
            "minItems",
            minimum,
        )
    maximum = schema.get("maxItems")
    if maximum is not None and len(instance) > maximum:
        yield _error(
            f"{instance!r} is too long",
            path,
            "maxItems",
            maximum,
        )


def _validate_string(
    instance: str, schema: Mapping[str, Any], path: tuple[str, ...]
) -> Iterator[SchemaValidationIssue]:
    pattern = schema.get("pattern")
    if pattern is not None and re.search(pattern, instance) is None:
        yield _error(
            f"{instance!r} does not match {pattern!r}",
            path,
            "pattern",
            pattern,
        )
    minimum = schema.get("minLength")
    if minimum is not None and len(instance) < minimum:
        yield _error(
            f"{instance!r} is too short",
            path,
            "minLength",
            minimum,
        )
    maximum = schema.get("maxLength")
    if maximum is not None and len(instance) > maximum:
        yield _error(
            f"{instance!r} is too long",
            path,
            "maxLength",
            maximum,
        )


def _validate_number(
    instance: int | float, schema: Mapping[str, Any], path: tuple[str, ...]
) -> Iterator[SchemaValidationIssue]:
    minimum = schema.get("minimum")
    if minimum is not None and instance < minimum:
        yield _error(
            f"{instance!r} is less than the minimum of {minimum}",
            path,
            "minimum",
            minimum,
        )
    maximum = schema.get("maximum")
    if maximum is not None and instance > maximum:
        yield _error(
            f"{instance!r} is greater than the maximum of {maximum}",
            path,
            "maximum",
            maximum,
        )
    exclusive_minimum = schema.get("exclusiveMinimum")
    if exclusive_minimum is not None and instance <= exclusive_minimum:
        yield _error(
            f"{instance!r} is less than or equal to the minimum of {exclusive_minimum}",
            path,
            "exclusiveMinimum",
            exclusive_minimum,
        )
    exclusive_maximum = schema.get("exclusiveMaximum")
    if exclusive_maximum is not None and instance >= exclusive_maximum:
        yield _error(
            f"{instance!r} is greater than or equal to the maximum of {exclusive_maximum}",
            path,
            "exclusiveMaximum",
            exclusive_maximum,
        )
