r"""Fixtures pytest A5 — contrats JSON et schéma SQLite.

Exécution reproductible depuis la racine du dépôt :

    .\.venv\Scripts\python.exe -m pytest tests -q

Dépendances : pytest, jsonschema (voir tests/README.md).
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

TESTS_DIR = Path(__file__).resolve().parent
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))

SRC_DIR = TESTS_DIR.parent / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from labtest.contracts import SQL_SCHEMA_PATH, load_examples, load_schemas  # noqa: E402
from labtest.sqlfixtures import seed_basic  # noqa: E402
from polymarket_lab.storage.connection import (  # noqa: E402
    ConnectionConfig,
    open_connection,
)

MIGRATION_0004_PATH = SQL_SCHEMA_PATH.parent / "migrations" / "0004_consolidation.sql"
MIGRATION_0005_PATH = SQL_SCHEMA_PATH.parent / "migrations" / "0005_p0_foundations.sql"
MIGRATION_0006_PATH = SQL_SCHEMA_PATH.parent / "migrations" / "0006_p0_ledger.sql"
MIGRATION_0007_PATH = (
    SQL_SCHEMA_PATH.parent / "migrations" / "0007_contract_sql_alignment.sql"
)


def apply_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(SQL_SCHEMA_PATH.read_text(encoding="utf-8"))
    connection.executescript(MIGRATION_0004_PATH.read_text(encoding="utf-8"))
    connection.execute("PRAGMA foreign_keys = ON")


@pytest.fixture(scope="session")
def schemas() -> dict[str, dict]:
    return load_schemas()


@pytest.fixture(scope="session")
def examples() -> dict[str, dict]:
    return load_examples()


@pytest.fixture(scope="session")
def validators(schemas: dict[str, dict]) -> dict[str, Draft202012Validator]:
    return {
        name: Draft202012Validator(schema)
        for name, schema in schemas.items()
    }


def _connect_in_memory() -> sqlite3.Connection:
    connection = open_connection(
        ConnectionConfig(":memory:", journal_mode=None)
    )
    apply_schema(connection)
    return connection


@pytest.fixture()
def db() -> sqlite3.Connection:
    connection = _connect_in_memory()
    try:
        yield connection
    finally:
        connection.close()


@pytest.fixture()
def db_v7() -> sqlite3.Connection:
    """Base 0.7 isolée : 0.4 + 0005 + 0006 + 0007."""
    connection = _connect_in_memory()
    try:
        for path in (MIGRATION_0005_PATH, MIGRATION_0006_PATH, MIGRATION_0007_PATH):
            connection.executescript(path.read_text(encoding="utf-8"))
        connection.execute("PRAGMA foreign_keys = ON")
        yield connection
    finally:
        connection.close()


@pytest.fixture()
def seeded(db: sqlite3.Connection) -> dict:
    return seed_basic(db)


@pytest.fixture()
def seeded_v7(db_v7: sqlite3.Connection) -> dict:
    return seed_basic(db_v7)


@pytest.fixture()
def file_db(tmp_path: Path) -> tuple[sqlite3.Connection, Path]:
    """Base sur fichier, pour tester l'idempotence après réouverture."""
    path = tmp_path / "lab_fixture.sqlite3"
    connection = open_connection(ConnectionConfig(path))
    apply_schema(connection)
    try:
        yield connection, path
    finally:
        connection.close()


def open_second_connection(path: Path) -> sqlite3.Connection:
    return open_connection(ConnectionConfig(path))
