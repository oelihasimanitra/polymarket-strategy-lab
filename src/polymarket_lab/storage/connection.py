"""Fabrique de connexions SQLite pour le laboratoire.

SQLite applique ``foreign_keys``, ``recursive_triggers`` et
``ignore_check_constraints`` par connexion, pas par base. Une connexion brute
peut donc contourner les triggers append-only avec ``INSERT OR REPLACE`` ou
désactiver les contraintes ``CHECK``. Toute connexion applicative doit passer
par ``open_connection``, qui impose et vérifie ces pragmas. Le writer commun
refuse en plus une connexion dont l'un de ces pragmas n'est pas dans l'état
attendu.

Exception outillée : le runner de migration ouvre une connexion avec
``foreign_keys=OFF`` le temps de reconstruire les tables. Il doit restaurer
``foreign_keys=ON`` et ``recursive_triggers=ON`` avant de fermer.
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

__all__ = [
    "ConnectionConfig",
    "ConnectionConfigurationError",
    "open_connection",
    "transaction",
]


class ConnectionConfigurationError(RuntimeError):
    """Une garantie SQLite demandée n'a pas pu être appliquée ou vérifiée."""


@dataclass(frozen=True)
class ConnectionConfig:
    """Configuration explicite d'une connexion SQLite.

    Une connexion applicative en écriture sur fichier exige ``WAL``.
    ``journal_mode=None`` est réservé aux bases ``:memory:`` et à la lecture
    seule, où WAL ne peut pas être imposé.
    """

    path: str | Path
    read_only: bool = False
    busy_timeout_ms: int = 5000
    journal_mode: str | None = "WAL"
    synchronous: str = "NORMAL"


def _is_memory(path: str | Path) -> bool:
    text = str(path)
    return text == ":memory:" or text.startswith("file::memory:")


def _connect(config: ConnectionConfig) -> sqlite3.Connection:
    if config.busy_timeout_ms < 0:
        raise ConnectionConfigurationError("busy_timeout_ms doit être >= 0")
    if config.synchronous not in {"OFF", "NORMAL", "FULL", "EXTRA"}:
        raise ConnectionConfigurationError(
            f"synchronous invalide : {config.synchronous!r}"
        )
    if config.journal_mode is not None and config.journal_mode not in {
        "DELETE", "TRUNCATE", "PERSIST", "MEMORY", "WAL", "OFF"
    }:
        raise ConnectionConfigurationError(
            f"journal_mode invalide : {config.journal_mode!r}"
        )

    timeout_s = config.busy_timeout_ms / 1000
    if config.read_only:
        if _is_memory(config.path):
            raise ConnectionConfigurationError(
                "une connexion :memory: ne peut pas être en lecture seule"
            )
        if config.journal_mode is not None:
            raise ConnectionConfigurationError(
                "journal_mode doit être None en lecture seule"
            )
        path = Path(config.path)
        if not path.exists():
            raise ConnectionConfigurationError(f"base introuvable : {path}")
        # as_uri() percent-encode les caractères réservés (espace, #, %) ;
        # un chemin interpolé brut peut ouvrir un autre fichier ou échouer.
        uri = path.resolve().as_uri() + "?mode=ro"
        return sqlite3.connect(uri, uri=True, timeout=timeout_s)

    if config.journal_mode == "WAL" and _is_memory(config.path):
        raise ConnectionConfigurationError(
            "journal_mode=WAL n'est pas applicable à :memory: ; utiliser None"
        )
    if not _is_memory(config.path) and config.journal_mode != "WAL":
        raise ConnectionConfigurationError(
            "WAL est obligatoire pour une connexion applicative en écriture"
        )
    return sqlite3.connect(str(config.path), timeout=timeout_s)


def _pragma_int(connection: sqlite3.Connection, name: str) -> int:
    row = connection.execute(f"PRAGMA {name}").fetchone()
    return int(row[0]) if row is not None else -1


def _configure_connection(
    connection: sqlite3.Connection,
    *,
    foreign_keys: bool = True,
    recursive_triggers: bool = True,
    busy_timeout_ms: int = 5000,
    journal_mode: str | None = "WAL",
    synchronous: str = "NORMAL",
    read_only: bool = False,
) -> None:
    """Applique puis vérifie les pragmas de sécurité.

    Lève ``ConnectionConfigurationError`` si SQLite n'applique pas la valeur
    demandée. Ne pas appeler pendant une transaction : ``foreign_keys`` est
    alors un no-op.
    """
    if connection.in_transaction:
        raise ConnectionConfigurationError(
            "_configure_connection ne peut pas s'exécuter dans une transaction"
        )
    if busy_timeout_ms < 0:
        raise ConnectionConfigurationError("busy_timeout_ms doit être >= 0")
    if synchronous not in {"OFF", "NORMAL", "FULL", "EXTRA"}:
        raise ConnectionConfigurationError(
            f"synchronous invalide : {synchronous!r}"
        )
    if journal_mode is not None and journal_mode not in {
        "DELETE", "TRUNCATE", "PERSIST", "MEMORY", "WAL", "OFF"
    }:
        raise ConnectionConfigurationError(
            f"journal_mode invalide : {journal_mode!r}"
        )

    connection.execute(f"PRAGMA busy_timeout = {int(busy_timeout_ms)}")
    if _pragma_int(connection, "busy_timeout") != int(busy_timeout_ms):
        raise ConnectionConfigurationError("busy_timeout non appliqué")

    connection.execute(f"PRAGMA synchronous = {synchronous}")
    synchronous_values = {"OFF": 0, "NORMAL": 1, "FULL": 2, "EXTRA": 3}
    if _pragma_int(connection, "synchronous") != synchronous_values[synchronous]:
        raise ConnectionConfigurationError("synchronous non appliqué")

    if journal_mode is not None:
        actual = connection.execute(
            f"PRAGMA journal_mode = {journal_mode}"
        ).fetchone()
        actual_mode = "" if actual is None else str(actual[0]).lower()
        if actual_mode != journal_mode.lower():
            raise ConnectionConfigurationError(
                f"journal_mode demandé {journal_mode}, obtenu {actual_mode or 'aucun'}"
            )

    connection.execute(
        "PRAGMA foreign_keys = " + ("ON" if foreign_keys else "OFF")
    )
    if _pragma_int(connection, "foreign_keys") != int(foreign_keys):
        raise ConnectionConfigurationError("foreign_keys non appliqué")

    connection.execute(
        "PRAGMA recursive_triggers = "
        + ("ON" if recursive_triggers else "OFF")
    )
    if _pragma_int(connection, "recursive_triggers") != int(recursive_triggers):
        raise ConnectionConfigurationError("recursive_triggers non appliqué")

    # SQLite autorise le contournement de tous les CHECK avec ce pragma. Il
    # n'est pas persistant et vaut OFF par défaut, mais une connexion
    # applicative ne doit jamais le laisser activé.
    connection.execute("PRAGMA ignore_check_constraints = OFF")
    if _pragma_int(connection, "ignore_check_constraints") != 0:
        raise ConnectionConfigurationError("ignore_check_constraints non désactivé")

    if read_only:
        connection.execute("PRAGMA query_only = ON")
        if _pragma_int(connection, "query_only") != 1:
            raise ConnectionConfigurationError("query_only non appliqué")


def open_connection(config: ConnectionConfig) -> sqlite3.Connection:
    """Ouvre une connexion applicative et vérifie toutes ses garanties."""
    connection = _connect(config)
    try:
        connection.row_factory = sqlite3.Row
        # Transactions sont explicites, via transaction() ; pas de BEGIN
        # implicite déclenché par une instruction DML.
        connection.isolation_level = None
        _configure_connection(
            connection,
            foreign_keys=True,
            recursive_triggers=True,
            busy_timeout_ms=config.busy_timeout_ms,
            journal_mode=config.journal_mode,
            synchronous=config.synchronous,
            read_only=config.read_only,
        )
        if not _is_memory(config.path):
            rows = connection.execute("PRAGMA database_list").fetchall()
            actual = Path(rows[0][2]).resolve() if rows and rows[0][2] else None
            expected = Path(config.path).resolve()
            if actual != expected:
                raise ConnectionConfigurationError(
                    f"SQLite a ouvert {actual}, attendu {expected}"
                )
    except BaseException:
        try:
            connection.close()
        except Exception:
            pass
        raise
    return connection


@contextmanager
def transaction(
    connection: sqlite3.Connection,
    *,
    immediate: bool = True,
) -> Iterator[sqlite3.Connection]:
    """Transaction explicite avec COMMIT/ROLLBACK garanti."""
    if connection.in_transaction:
        raise ConnectionConfigurationError(
            "une transaction est déjà ouverte sur cette connexion"
        )
    connection.execute("BEGIN IMMEDIATE" if immediate else "BEGIN")
    try:
        yield connection
    except BaseException:
        connection.rollback()
        raise
    else:
        try:
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
