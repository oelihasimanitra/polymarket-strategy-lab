"""Applique une migration SQLite en vérifiant source, cible et journal.

Le script SQL d'une migration passe ``PRAGMA foreign_keys = OFF`` pour
reconstruire des tables. SQLite n'a pas de bloc ``finally`` : ce runner
restaure donc toujours ``foreign_keys=ON`` et ``recursive_triggers=ON`` sur sa
connexion, même après une erreur.

Une migration exécutée depuis la CLI exige une sauvegarde préalable. Le fichier
de sauvegarde est créé par l'API ``sqlite3.Connection.backup`` (cohérent avec
WAL) et restauré si l'application ou les vérifications post-migration échouent.
Une erreur survenue après le COMMIT interne de la migration ne peut pas être
annulée par ``rollback`` ; elle est traitée par restauration du fichier.

Usage :
    python schemas/migrations/run_migration.py --database data/lab.db
    python schemas/migrations/run_migration.py --database data/lab.db \
        --migration schemas/migrations/0005_p0_foundations.sql
"""

from __future__ import annotations

import argparse
import shutil
import sqlite3
import sys
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_SRC = _ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from polymarket_lab.storage.connection import (  # noqa: E402
    ConnectionConfig,
    _configure_connection,
    open_connection,
)

MIGRATIONS_DIR = Path(__file__).with_name("0004_consolidation.sql").parent

# version source -> (fichier, version cible, journal attendu, tables préservées)
MIGRATION_REGISTRY: dict[int, tuple[Path, int, tuple[int, ...], tuple[str, ...]]] = {
    3: (
        MIGRATIONS_DIR / "0004_consolidation.sql",
        4,
        (),
        ("market_events", "simulated_orders", "simulated_fills", "experiments"),
    ),
    4: (
        MIGRATIONS_DIR / "0005_p0_foundations.sql",
        5,
        (4,),
        ("market_events", "event_replacements", "data_manifests", "experiments"),
    ),
    5: (
        MIGRATIONS_DIR / "0006_p0_ledger.sql",
        6,
        (4, 5),
        ("ledger_transactions", "ledger_postings", "settlement_conversions"),
    ),
    6: (
        MIGRATIONS_DIR / "0007_contract_sql_alignment.sql",
        7,
        (4, 5, 6),
        (
            "experiments",
            "fee_schedules",
            "simulated_orders",
            "simulated_fills",
            "ledger_transactions",
            "ledger_postings",
            "settlement_conversions",
        ),
    ),
}

DEFAULT_SOURCE_VERSION = 3
DEFAULT_MIGRATION = MIGRATION_REGISTRY[DEFAULT_SOURCE_VERSION][0]


class MigrationError(RuntimeError):
    """La base ou la migration ne respecte pas les conditions attendues."""


def _migration_spec(migration: Path) -> tuple[int, int, tuple[int, ...], tuple[str, ...]]:
    for source, (path, target, journal, preserved) in MIGRATION_REGISTRY.items():
        if path.resolve() == migration.resolve():
            return source, target, journal, preserved
    known = ", ".join(str(path.name) for path, *_ in MIGRATION_REGISTRY.values())
    raise MigrationError(
        f"migration inconnue : {migration.name} ; migrations enregistrées : {known}"
    )


def _restore_migration_pragmas(connection: sqlite3.Connection) -> None:
    _configure_connection(
        connection,
        foreign_keys=True,
        recursive_triggers=True,
        busy_timeout_ms=5000,
        journal_mode=None,
        synchronous="NORMAL",
        read_only=False,
    )


def _table_counts(connection: sqlite3.Connection, tables: tuple[str, ...]) -> dict[str, int]:
    existing = {
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        )
    }
    return {
        table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        for table in tables
        if table in existing
    }


def _check_journal(
    connection: sqlite3.Connection,
    expected: tuple[int, ...],
    *,
    target: int,
) -> None:
    rows = [
        row[0]
        for row in connection.execute(
            "SELECT version FROM schema_migrations ORDER BY version"
        )
    ]
    if rows != list(expected) + [target]:
        raise MigrationError(
            f"journal attendu {list(expected) + [target]}, trouvé {rows}"
        )


def _preflight_end_time(
    connection: sqlite3.Connection,
    *,
    source: int,
    migration_name: str,
) -> None:
    """Préflight 0007 : signale le nombre de lignes incompatibles."""
    if source != 6:
        return
    count = connection.execute(
        "SELECT COUNT(*) FROM experiments "
        "WHERE period_type <> 'paper_live' AND end_time IS NULL"
    ).fetchone()[0]
    if count:
        raise MigrationError(
            f"{migration_name} : {count} expérience(s) non paper_live avec "
            "end_time NULL ; corriger explicitement les données avant migration"
        )


def apply_migration_on_connection(
    connection: sqlite3.Connection,
    migration: str | Path = DEFAULT_MIGRATION,
) -> None:
    """Applique la migration et garantit les pragmas de sécurité au retour.

    ``foreign_keys`` est temporairement désactivé pour reconstruire les tables ;
    ``recursive_triggers`` reste actif. En cas d'échec, la transaction est
    annulée avant de restaurer ``foreign_keys=ON`` et
    ``recursive_triggers=ON``.
    """
    migration_path = Path(migration)
    source, target, journal_before, preserved_tables = _migration_spec(migration_path)
    sql = migration_path.read_text(encoding="utf-8")

    if connection.in_transaction:
        raise MigrationError(
            "migration refusée : une transaction est déjà ouverte sur la connexion"
        )

    try:
        _configure_connection(
            connection,
            foreign_keys=False,
            recursive_triggers=True,
            busy_timeout_ms=5000,
            journal_mode=None,
            synchronous="NORMAL",
            read_only=False,
        )
        actual_source = connection.execute("PRAGMA user_version").fetchone()[0]
        if actual_source != source:
            raise MigrationError(
                f"migration {migration_path.name} attend user_version={source}, "
                f"trouvé {actual_source}"
            )
        _preflight_end_time(
            connection,
            source=source,
            migration_name=migration_path.name,
        )
        before_counts = _table_counts(connection, preserved_tables)
        connection.executescript(sql)
        actual_target = connection.execute("PRAGMA user_version").fetchone()[0]
        if actual_target != target:
            raise MigrationError(
                f"migration {migration_path.name} attend user_version={target}, "
                f"trouvé {actual_target}"
            )
        _check_journal(connection, journal_before, target=target)
        after_counts = _table_counts(connection, preserved_tables)
        if after_counts != before_counts:
            raise MigrationError(
                f"comptages modifiés par {migration_path.name} : "
                f"avant={before_counts}, après={after_counts}"
            )
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
        if integrity != "ok":
            raise MigrationError(f"integrity_check après migration : {integrity}")
        fk_errors = connection.execute("PRAGMA foreign_key_check").fetchall()
        if fk_errors:
            raise MigrationError(
                f"foreign_key_check après migration : {fk_errors!r}"
            )
    except BaseException as original:
        try:
            connection.rollback()
        except BaseException:
            pass
        try:
            _restore_migration_pragmas(connection)
        except BaseException as restore_error:
            raise MigrationError(
                f"échec de restauration après erreur de migration : {restore_error}"
            ) from original
        raise
    else:
        try:
            _restore_migration_pragmas(connection)
        except BaseException as restore_error:
            raise MigrationError(
                f"échec de restauration après migration : {restore_error}"
            ) from restore_error


def _backup_database(path: Path) -> Path:
    timestamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    base = path.with_name(f"{path.name}.bak.{timestamp}")
    backup_path = base
    suffix = 1
    while backup_path.exists():
        backup_path = path.with_name(f"{base.name}.{suffix}")
        suffix += 1
    source = sqlite3.connect(path)
    try:
        target = sqlite3.connect(backup_path)
        try:
            source.backup(target)
            integrity = target.execute("PRAGMA integrity_check").fetchone()[0]
            if integrity != "ok":
                raise MigrationError(f"sauvegarde incohérente : {integrity}")
        finally:
            target.close()
    except BaseException:
        if backup_path.exists():
            backup_path.unlink()
        raise
    finally:
        source.close()
    return backup_path


def _restore_backup(path: Path, backup_path: Path) -> None:
    for suffix in ("-wal", "-shm"):
        companion = Path(str(path) + suffix)
        if companion.exists():
            companion.unlink()
    shutil.copy2(backup_path, path)


def apply_migration(
    database: str | Path,
    migration: str | Path | None = None,
) -> Path:
    """Ouvre la base, sauvegarde, applique la migration, puis ferme.

    Retourne le chemin de la sauvegarde. Si la migration échoue, la base est
    restaurée depuis cette sauvegarde. Aucun fichier vide n'est créé.
    """
    path = Path(database)
    if not path.exists():
        raise MigrationError(f"base introuvable : {path}")
    if path.stat().st_size == 0:
        raise MigrationError(f"base vide refusée : {path}")
    if migration is None:
        source = sqlite3.connect(path)
        try:
            version = source.execute("PRAGMA user_version").fetchone()[0]
        finally:
            source.close()
        try:
            migration_path = MIGRATION_REGISTRY[version][0]
        except KeyError as error:
            raise MigrationError(
                f"aucune migration enregistrée depuis user_version={version}"
            ) from error
    else:
        migration_path = Path(migration)

    backup_path = _backup_database(path)
    connection = open_connection(ConnectionConfig(path))
    try:
        apply_migration_on_connection(connection, migration_path)
    except BaseException as original:
        connection.close()
        try:
            _restore_backup(path, backup_path)
        except BaseException as restore_error:
            raise MigrationError(
                f"échec de restauration de la sauvegarde : {restore_error}"
            ) from original
        raise
    else:
        connection.close()
    return backup_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Applique la migration suivante avec sauvegarde et restauration des FK."
    )
    parser.add_argument("--database", required=True, type=Path)
    parser.add_argument("--migration", type=Path, default=None)
    args = parser.parse_args(argv)

    backup = apply_migration(args.database, args.migration)
    print(f"Migration appliquée : {args.database}")
    print(f"Sauvegarde : {backup}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
