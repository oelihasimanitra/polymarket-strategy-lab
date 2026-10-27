"""Écriture d'un remplacement d'événement avec des timestamps générés.

C-02 : cette API ne reçoit ni ``created_at`` ni ``visible_from``. Les deux
valeurs sont dérivées des horodatages stockés et d'une horloge UTC injectée.
Les triggers SQL restent la barrière de dernier recours pour les accès directs.
"""

from __future__ import annotations

import sqlite3

from .clock import Clock, replacement_timestamps


def record_replacement(
    connection: sqlite3.Connection,
    *,
    replacement_id: str,
    old_event_id: str,
    new_event_id: str,
    reason: str,
    normalizer_version: str,
    evidence_ref: str | None,
    clock: Clock,
) -> tuple[str, str]:
    """Insère un remplacement et retourne ``(created_at, visible_from)``.

    Aucun paramètre de temps n'est accepté depuis l'appelant. Une erreur
    ``ValueError`` est levée si l'un des événements n'existe pas.
    """
    rows = connection.execute(
        "SELECT event_id, received_timestamp FROM market_events "
        "WHERE event_id IN (?, ?)",
        (old_event_id, new_event_id),
    ).fetchall()
    received = {row[0]: row[1] for row in rows}
    if old_event_id not in received or new_event_id not in received:
        raise ValueError("les deux événements du remplacement doivent exister")

    created_at, visible_from = replacement_timestamps(
        received[old_event_id],
        received[new_event_id],
        clock,
    )
    connection.execute(
        """
        INSERT INTO event_replacements(
            replacement_id, old_event_id, new_event_id, reason,
            normalizer_version, evidence_ref, created_at,
            visible_from_received_timestamp
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            replacement_id, old_event_id, new_event_id, reason,
            normalizer_version, evidence_ref, created_at, visible_from,
        ),
    )
    return created_at, visible_from
