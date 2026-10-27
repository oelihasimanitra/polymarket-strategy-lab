"""B-04 : garanties de connexion SQLite et append-only réel.

Ces tests vérifient que la fabrique impose les pragmas par connexion et que
``INSERT OR REPLACE`` ne contourne pas les triggers DELETE. Ils ne modifient
aucun schéma ni contrat.
"""

from __future__ import annotations

import ast
import sqlite3
from pathlib import Path

import pytest

from conftest import apply_schema
from labtest import sqlfixtures as fx
from polymarket_lab.storage.connection import (
    ConnectionConfig,
    ConnectionConfigurationError,
    open_connection,
    transaction,
)


def _pragma(connection: sqlite3.Connection, name: str) -> int:
    return int(connection.execute(f"PRAGMA {name}").fetchone()[0])


def test_memory_connection_has_required_pragmas() -> None:
    connection = open_connection(
        ConnectionConfig(":memory:", journal_mode=None)
    )
    try:
        assert _pragma(connection, "foreign_keys") == 1
        assert _pragma(connection, "recursive_triggers") == 1
        assert _pragma(connection, "busy_timeout") == 5000
        assert _pragma(connection, "query_only") == 0
    finally:
        connection.close()


def test_file_connection_uses_wal_and_reopens(tmp_path: Path) -> None:
    path = tmp_path / "lab.sqlite3"
    connection = open_connection(ConnectionConfig(path))
    try:
        assert connection.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        assert _pragma(connection, "synchronous") == 1
    finally:
        connection.close()

    reopened = open_connection(ConnectionConfig(path))
    try:
        assert _pragma(reopened, "foreign_keys") == 1
        assert _pragma(reopened, "recursive_triggers") == 1
        assert reopened.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    finally:
        reopened.close()


def test_read_only_connection_sets_query_only(tmp_path: Path) -> None:
    path = tmp_path / "lab.sqlite3"
    writer = open_connection(ConnectionConfig(path))
    try:
        writer.execute("CREATE TABLE t (value INTEGER)")
        writer.execute("INSERT INTO t VALUES (1)")
        writer.commit()
    finally:
        writer.close()

    reader = open_connection(
        ConnectionConfig(path, read_only=True, journal_mode=None)
    )
    try:
        assert _pragma(reader, "foreign_keys") == 1
        assert _pragma(reader, "recursive_triggers") == 1
        assert _pragma(reader, "query_only") == 1
        with pytest.raises(sqlite3.OperationalError):
            reader.execute("INSERT INTO t VALUES (2)")
    finally:
        reader.close()


def test_missing_read_only_database_is_refused(tmp_path: Path) -> None:
    with pytest.raises(ConnectionConfigurationError):
        open_connection(
            ConnectionConfig(
                tmp_path / "missing.sqlite3",
                read_only=True,
                journal_mode=None,
            )
        )


def test_read_only_rejects_wal_configuration(tmp_path: Path) -> None:
    path = tmp_path / "lab.sqlite3"
    writer = open_connection(ConnectionConfig(path))
    writer.close()
    with pytest.raises(ConnectionConfigurationError, match="lecture seule"):
        open_connection(ConnectionConfig(path, read_only=True))


@pytest.mark.parametrize("name", ["lab #1.sqlite3", "lab%20name.sqlite3"])
def test_read_only_escapes_reserved_path_characters(
    tmp_path: Path, name: str
) -> None:
    path = tmp_path / name
    writer = open_connection(ConnectionConfig(path))
    try:
        writer.execute("CREATE TABLE t (value INTEGER)")
        writer.execute("INSERT INTO t VALUES (7)")
    finally:
        writer.close()

    reader = open_connection(
        ConnectionConfig(path, read_only=True, journal_mode=None)
    )
    try:
        actual = Path(
            reader.execute("PRAGMA database_list").fetchone()[2]
        ).resolve()
        assert actual == path.resolve()
        assert reader.execute("SELECT value FROM t").fetchone()[0] == 7
    finally:
        reader.close()


@pytest.mark.parametrize("mode", [None, "DELETE", "MEMORY", "TRUNCATE"])
def test_writable_file_requires_wal(tmp_path: Path, mode: str | None) -> None:
    with pytest.raises(ConnectionConfigurationError, match="WAL"):
        open_connection(
            ConnectionConfig(tmp_path / "lab.sqlite3", journal_mode=mode)
        )


def test_synchronous_full_is_applied(tmp_path: Path) -> None:
    path = tmp_path / "lab.sqlite3"
    connection = open_connection(ConnectionConfig(path, synchronous="FULL"))
    try:
        assert _pragma(connection, "synchronous") == 2
    finally:
        connection.close()

    reader = open_connection(
        ConnectionConfig(
            path,
            read_only=True,
            journal_mode=None,
            synchronous="FULL",
        )
    )
    try:
        assert _pragma(reader, "synchronous") == 2
    finally:
        reader.close()


def test_transaction_commits_and_rolls_back() -> None:
    connection = open_connection(
        ConnectionConfig(":memory:", journal_mode=None)
    )
    try:
        connection.execute("CREATE TABLE t (value INTEGER)")
        with transaction(connection):
            connection.execute("INSERT INTO t VALUES (1)")
        assert connection.execute("SELECT COUNT(*) FROM t").fetchone()[0] == 1

        with pytest.raises(RuntimeError):
            with transaction(connection):
                connection.execute("INSERT INTO t VALUES (2)")
                raise RuntimeError("rollback")
        assert connection.execute("SELECT COUNT(*) FROM t").fetchone()[0] == 1
    finally:
        connection.close()


def test_replace_cannot_bypass_ledger_append_only(tmp_path: Path) -> None:
    path = tmp_path / "lab.sqlite3"
    connection = open_connection(ConnectionConfig(path))
    try:
        apply_schema(connection)
        seeded = fx.seed_basic(connection)
        fx.insert_ledger_transaction(
            connection, "tx_append_only", fx.deposit_postings(),
            kind="deposit", ref_type="experiment",
            ref_id=seeded["experiment_id"],
        )
    finally:
        connection.close()

    connection = open_connection(ConnectionConfig(path))
    try:
        assert _pragma(connection, "recursive_triggers") == 1
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            connection.execute(
                "INSERT OR REPLACE INTO ledger_transactions "
                "SELECT * FROM ledger_transactions WHERE transaction_id = 'tx_append_only'"
            )
        assert connection.execute(
            "SELECT memo FROM ledger_transactions WHERE transaction_id = 'tx_append_only'"
        ).fetchone()[0] == ""
    finally:
        connection.close()


def test_replace_cannot_bypass_fill_or_event_append_only(tmp_path: Path) -> None:
    path = tmp_path / "lab.sqlite3"
    connection = open_connection(ConnectionConfig(path))
    try:
        apply_schema(connection)
        fx.seed_basic(connection)
        fx.insert_envelope(connection, "evt_bare_append_only", "connection_status")
    finally:
        connection.close()

    connection = open_connection(ConnectionConfig(path))
    try:
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            connection.execute(
                "INSERT OR REPLACE INTO simulated_fills "
                "SELECT * FROM simulated_fills WHERE fill_id = 'fill_fixture_001'"
            )
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            connection.execute(
                "INSERT OR REPLACE INTO market_events "
                "SELECT * FROM market_events WHERE event_id = 'evt_bare_append_only'"
            )
    finally:
        connection.close()


def _sqlite_direct_constructors(tree: ast.AST) -> bool:
    """Détecte connect/Connection, alias compris.

    Limites : ne détecte pas les accès dynamiques ``getattr(sqlite3, ...)``
    ni un module importé sous un nom calculé. Les tests couvrent les formes
    statiques courantes.
    """
    sqlite_names = {"sqlite3"}
    direct_names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "sqlite3":
                    sqlite_names.add(alias.asname or "sqlite3")
                elif alias.name == "sqlite3.dbapi2":
                    sqlite_names.add(alias.asname or "dbapi2")
        elif isinstance(node, ast.ImportFrom) and node.module in {
            "sqlite3", "sqlite3.dbapi2"
        }:
            for alias in node.names:
                if alias.name in {"connect", "Connection"}:
                    direct_names.add(alias.asname or alias.name)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Name) and func.id in direct_names:
            return True
        if isinstance(func, ast.Attribute) and func.attr in {
            "connect", "Connection"
        }:
            root = func.value
            while isinstance(root, ast.Attribute):
                root = root.value
            if isinstance(root, ast.Name) and root.id in sqlite_names:
                return True
    return False


def test_no_direct_sqlite_connection_in_src() -> None:
    root = Path(__file__).resolve().parents[2]
    roots = [root / "src"]
    if (root / "scripts").exists():
        roots.append(root / "scripts")
    allowed = {root / "src" / "polymarket_lab" / "storage" / "connection.py"}
    violations = []
    for base in roots:
        for path in sorted(base.rglob("*.py")):
            if path in allowed:
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            if _sqlite_direct_constructors(tree):
                violations.append(str(path.relative_to(root)))
    assert violations == []


@pytest.mark.parametrize(
    "source",
    [
        "import sqlite3\nsqlite3.connect(':memory:')",
        "import sqlite3 as s\ns.connect(':memory:')",
        "from sqlite3 import connect as c\nc(':memory:')",
        "import sqlite3\nsqlite3.Connection(':memory:')",
        "from sqlite3 import Connection\nConnection(':memory:')",
        "import sqlite3.dbapi2 as d\nd.connect(':memory:')",
        "import sqlite3.dbapi2 as d\nd.Connection(':memory:')",
    ],
)
def test_ast_detects_direct_sqlite_constructors(source: str) -> None:
    assert _sqlite_direct_constructors(ast.parse(source))
