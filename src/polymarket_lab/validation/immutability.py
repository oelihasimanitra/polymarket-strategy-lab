"""Utilitaires d'immutabilité profonde pour les schémas approuvés.

``MappingProxyType`` seul ne protège que le premier niveau. Un schéma JSON
contient des dictionnaires et des listes imbriqués : une copie superficielle
laisse donc l'appelant muter un sous-objet après l'approbation. ``freeze_json``
convertit récursivement les dictionnaires en vues en lecture seule et les
listes en tuples.

Cette protection empêche les mutations accidentelles par du code Python
ordinaire. Elle ne constitue pas une frontière de sécurité contre du code
arbitraire exécuté dans le même processus, qui peut toujours contourner les
attributs privés ou réassigner des globals.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from types import MappingProxyType
from typing import Any

__all__ = ["canonical_json", "freeze_json", "thaw_json"]


def freeze_json(value: Any) -> Any:
    """Retourne une copie profondément immuable d'une valeur JSON."""
    if isinstance(value, Mapping):
        frozen = {key: freeze_json(item) for key, item in value.items()}
        return MappingProxyType(frozen)
    if isinstance(value, (list, tuple)):
        return tuple(freeze_json(item) for item in value)
    return value


def thaw_json(value: Any) -> Any:
    """Retourne une copie mutable d'une valeur JSON gelée.

    Réservé aux diagnostics et aux tests de comparaison. Le writer ne doit pas
    utiliser cette copie pour valider ou écrire.
    """
    if isinstance(value, Mapping):
        return {key: thaw_json(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [thaw_json(item) for item in value]
    return value


def canonical_json(value: Any) -> str:
    """Sérialisation JSON canonique utilisée pour les empreintes de schéma."""
    return json.dumps(
        thaw_json(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
