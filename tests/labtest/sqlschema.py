"""Introspection du schéma SQLite pour les tests de contrat.

Les CHECK ``IN (...)`` sont lus depuis ``sqlite_master`` plutôt que recopiés :
un ajout ou une suppression de valeur dans le SQL casse le test de parité.
"""

from __future__ import annotations

import re
import sqlite3
from typing import Any


def object_names(conn: sqlite3.Connection, object_type: str) -> set[str]:
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type = ? AND name NOT LIKE 'sqlite_%'",
        (object_type,),
    ).fetchall()
    return {row[0] for row in rows}


def table_names(conn: sqlite3.Connection) -> set[str]:
    return object_names(conn, "table")


def view_names(conn: sqlite3.Connection) -> set[str]:
    return object_names(conn, "view")


def trigger_names(conn: sqlite3.Connection) -> set[str]:
    return object_names(conn, "trigger")


def explicit_index_names(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'index' "
        "AND sql IS NOT NULL AND name NOT LIKE 'sqlite_%'"
    ).fetchall()
    return {row[0] for row in rows}


def table_sql(conn: sqlite3.Connection, table: str) -> str:
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = ?", (table,)
    ).fetchone()
    assert row is not None, f"table absente : {table}"
    return row[0]


def column_info(conn: sqlite3.Connection, table: str) -> dict[str, dict[str, Any]]:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {
        row[1]: {
            "type": row[2],
            "notnull": bool(row[3]),
            "default": row[4],
            "pk": bool(row[5]),
        }
        for row in rows
    }


def column_names(conn: sqlite3.Connection, table: str) -> set[str]:
    return set(column_info(conn, table))


def check_in_value_sets(conn: sqlite3.Connection, table: str, column: str) -> list[set[str]]:
    """Retourne toutes les listes ``IN (...)`` trouvées pour une colonne.

    Certaines colonnes ont plusieurs CHECK IN : par exemple
    ``simulated_orders.status`` a l'énumération complète puis un sous-ensemble
    utilisé par une autre contrainte.
    """
    sql = table_sql(conn, table)
    pattern = re.compile(
        rf"CHECK\s*\([^()]*?\b{re.escape(column)}\s+IN\s*\(([^)]*)\)",
        re.IGNORECASE | re.DOTALL,
    )
    matches = pattern.findall(sql)
    assert matches, f"aucun CHECK IN pour {table}.{column}"
    result = []
    for match in matches:
        values = re.findall(r"'([^']*)'", match)
        assert values, f"CHECK IN vide pour {table}.{column}"
        result.append(set(values))
    return result


def check_in_values(conn: sqlite3.Connection, table: str, column: str) -> set[str]:
    """Extrait l'énumération complète : le plus grand ensemble trouvé."""
    sets = check_in_value_sets(conn, table, column)
    return max(sets, key=len)
