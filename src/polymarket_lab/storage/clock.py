"""Horloge UTC injectable pour les timestamps générés par le stockage.

C-02 : la couche de stockage génère ``created_at`` et
``visible_from_received_timestamp``. Aucune API d'écriture n'accepte ces
valeurs depuis l'appelant. Les tests utilisent ``FixedClock``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol


class Clock(Protocol):
    """Source de temps UTC, injectable pour les tests déterministes."""

    def now(self) -> datetime:
        """Retourne un datetime conscient du fuseau, en UTC."""


class SystemUtcClock:
    """Horloge système en UTC."""

    def now(self) -> datetime:
        return datetime.now(timezone.utc)


@dataclass(frozen=True)
class FixedClock:
    """Horloge figée : les tests ne dépendent pas du temps réel."""

    instant: datetime

    def __post_init__(self) -> None:
        if self.instant.tzinfo is None:
            raise ValueError("FixedClock exige un datetime conscient du fuseau")

    def now(self) -> datetime:
        return self.instant.astimezone(timezone.utc)


def canonical_timestamp(value: datetime) -> str:
    """Formate en ``YYYY-MM-DDTHH:MM:SS.ffffffZ`` (UTC, six décimales)."""
    if value.tzinfo is None:
        raise ValueError("un timestamp naïf n'est pas un instant UTC")
    utc = value.astimezone(timezone.utc)
    return utc.strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def replacement_timestamps(
    old_received_timestamp: str,
    new_received_timestamp: str,
    clock: Clock,
) -> tuple[str, str]:
    """Génère ``(created_at, visible_from)`` sans accepter de valeur appelant.

    ``visible_from`` est le maximum des deux réceptions et de l'instant généré.
    L'API de stockage ne doit jamais recevoir ``visible_from`` en paramètre.
    """
    created_at = canonical_timestamp(clock.now())
    visible_from = max(
        old_received_timestamp,
        new_received_timestamp,
        created_at,
    )
    return created_at, visible_from
