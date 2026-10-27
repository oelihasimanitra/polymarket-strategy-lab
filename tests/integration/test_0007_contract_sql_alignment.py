"""Tests de la migration 0007 : alignement contrats JSON / SQLite.

Toutes les bases sont en mémoire ou dans ``tmp_path``. Aucune base de travail
n'est créée ni modifiée.
"""

from __future__ import annotations

import importlib.util
import sqlite3
from pathlib import Path

import pytest

from labtest import sqlfixtures as fx
from labtest.contracts import SQL_SCHEMA_PATH

MIGRATIONS = SQL_SCHEMA_PATH.parent / "migrations"
MIGRATION_0004 = MIGRATIONS / "0004_consolidation.sql"
MIGRATION_0005 = MIGRATIONS / "0005_p0_foundations.sql"
MIGRATION_0006 = MIGRATIONS / "0006_p0_ledger.sql"
MIGRATION_0007 = MIGRATIONS / "0007_contract_sql_alignment.sql"
RUNNER_PATH = MIGRATIONS / "run_migration.py"
BASELINE_SQL = SQL_SCHEMA_PATH.read_text(encoding="utf-8")

EXPERIMENT_TABLES = (
    "experiments",
    "fee_schedules",
    "simulated_orders",
    "simulated_fills",
    "ledger_transactions",
    "ledger_postings",
    "settlement_conversions",
)


def load_runner():
    spec = importlib.util.spec_from_file_location("run_migration_0007", RUNNER_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _file_v6(tmp_path: Path) -> Path:
    path = tmp_path / "lab_6.db"
    connection = sqlite3.connect(path)
    try:
        connection.executescript(BASELINE_SQL)
        for migration in (MIGRATION_0004, MIGRATION_0005, MIGRATION_0006):
            connection.executescript(migration.read_text(encoding="utf-8"))
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 6
    finally:
        connection.close()
    return path


def _seed(path: Path) -> dict:
    connection = sqlite3.connect(path)
    connection.isolation_level = None
    try:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA recursive_triggers = ON")
        ids = fx.seed_basic(connection)
        connection.commit()
        return ids
    finally:
        connection.close()


def _rows(path: Path, table: str) -> list[tuple]:
    connection = sqlite3.connect(path)
    try:
        return [tuple(row) for row in connection.execute(f"SELECT * FROM {table}")]
    finally:
        connection.close()


def _counts(path: Path) -> dict[str, int]:
    connection = sqlite3.connect(path)
    try:
        return {
            table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in EXPERIMENT_TABLES
        }
    finally:
        connection.close()


def _schema_names(path: Path, object_type: str) -> set[str]:
    connection = sqlite3.connect(path)
    try:
        return {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = ?", (object_type,)
            )
        }
    finally:
        connection.close()


def _journal_and_version(path: Path) -> tuple[int, list[int]]:
    connection = sqlite3.connect(path)
    try:
        version = connection.execute("PRAGMA user_version").fetchone()[0]
        journal = [
            row[0]
            for row in connection.execute(
                "SELECT version FROM schema_migrations ORDER BY version"
            )
        ]
        return version, journal
    finally:
        connection.close()


def test_0007_runner_success_preserves_rows_and_resets_defaults(
    tmp_path: Path,
) -> None:
    path = _file_v6(tmp_path)
    ids = _seed(path)
    connection = sqlite3.connect(path)
    connection.isolation_level = None
    try:
        connection.execute("PRAGMA foreign_keys = ON")
        fx.insert_fee_schedule(
            connection, "fee_legacy", schema_version="1.1.0"
        )
        fx.insert_fee_schedule(
            connection, "fee_legacy_successor", schema_version="1.1.0"
        )
        connection.execute(
            "UPDATE fee_schedules SET supersedes_fee_schedule_id = 'fee_legacy' "
            "WHERE fee_schedule_id = 'fee_legacy_successor'"
        )
        fx.insert_experiment(
            connection,
            ids["strategy_id"],
            ids["strategy_version"],
            experiment_id="exp_legacy",
            schema_version="1.1.0",
            period_type="research",
            start_time=fx.TS0,
            end_time=fx.TS1,
            data_manifest_id=ids["manifest_id"],
        )
        fx.insert_experiment(
            connection,
            ids["strategy_id"],
            ids["strategy_version"],
            experiment_id="exp_live_legacy",
            schema_version="1.1.0",
            period_type="paper_live",
            start_time=fx.TS0,
            end_time=None,
            data_manifest_id=None,
        )
        connection.commit()
    finally:
        connection.close()
    before_counts = _counts(path)
    before_experiments = _rows(path, "experiments")
    before_fees = _rows(path, "fee_schedules")
    before_triggers = _schema_names(path, "trigger")
    before_views = _schema_names(path, "view")
    before_indexes = _schema_names(path, "index")

    runner = load_runner()
    backup = runner.apply_migration(path)
    assert backup.exists()

    assert _journal_and_version(path) == (7, [4, 5, 6, 7])
    assert _counts(path) == before_counts
    assert _rows(path, "experiments") == before_experiments
    assert _rows(path, "fee_schedules") == before_fees
    assert _schema_names(path, "trigger") == before_triggers
    assert _schema_names(path, "view") == before_views
    assert _schema_names(path, "index") == before_indexes

    connection = sqlite3.connect(path)
    try:
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
        # Les lignes historiques conservent leur version d'origine.
        assert connection.execute(
            "SELECT schema_version FROM experiments WHERE experiment_id = 'exp_legacy'"
        ).fetchone()[0] == "1.1.0"
        assert connection.execute(
            "SELECT schema_version FROM fee_schedules WHERE fee_schedule_id = 'fee_legacy'"
        ).fetchone()[0] == "1.1.0"
        assert connection.execute(
            "SELECT supersedes_fee_schedule_id FROM fee_schedules "
            "WHERE fee_schedule_id = 'fee_legacy_successor'"
        ).fetchone()[0] == "fee_legacy"
        assert connection.execute(
            "SELECT end_time FROM experiments WHERE experiment_id = 'exp_live_legacy'"
        ).fetchone()[0] is None
        # Les nouveaux inserts utilisent le défaut aligné sur le contrat.
        fx.insert_fee_schedule(connection, "fee_after_0007")
        fx.insert_experiment(
            connection,
            before_experiments[0][2],  # strategy_id
            before_experiments[0][3],  # strategy_version
            experiment_id="exp_after_0007",
            period_type="validation",
            start_time=fx.TS0,
            end_time=fx.TS1,
            data_manifest_id=before_experiments[0][11],
        )
        connection.commit()
        assert connection.execute(
            "SELECT schema_version FROM experiments WHERE experiment_id = 'exp_after_0007'"
        ).fetchone()[0] == "1.2.0"
        assert connection.execute(
            "SELECT schema_version FROM fee_schedules WHERE fee_schedule_id = 'fee_after_0007'"
        ).fetchone()[0] == "1.2.0"
        triggers = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'trigger'"
            )
        }
        assert {
            "trg_experiments_config_hash",
            "trg_experiments_config_v2",
            "trg_experiments_immutable_update",
            "trg_fee_schedules_custom_formula_insert",
            "trg_orders_unit_insert",
            "trg_ledger_postings_unit_insert",
        } <= triggers
        views = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'view'"
            )
        }
        assert {
            "v_experiment_cash",
            "v_experiment_positions",
            "v_order_execution",
            "v_negative_cash",
        } <= views
    finally:
        connection.close()


@pytest.mark.parametrize("period_type", ["research", "validation", "final_test"])
def test_0007_preflight_refuses_null_end_with_count(
    tmp_path: Path, period_type: str
) -> None:
    path = _file_v6(tmp_path)
    ids = _seed(path)
    connection = sqlite3.connect(path)
    connection.isolation_level = None
    try:
        connection.execute("PRAGMA foreign_keys = ON")
        if period_type == "final_test":
            fx.insert_manifest(connection, "manifest_recorded", source_class="recorded")
            manifest_id = "manifest_recorded"
        else:
            manifest_id = ids["manifest_id"]
        fx.insert_experiment(
            connection,
            ids["strategy_id"],
            ids["strategy_version"],
            experiment_id=f"exp_bad_{period_type}",
            period_type=period_type,
            start_time=fx.TS0,
            end_time=None,
            data_manifest_id=manifest_id,
        )
        connection.commit()
    finally:
        connection.close()

    before = _counts(path)
    runner = load_runner()
    with pytest.raises(runner.MigrationError, match=r"1 expérience.*end_time NULL"):
        runner.apply_migration(path)

    assert _journal_and_version(path) == (6, [4, 5, 6])
    assert _counts(path) == before
    assert list(tmp_path.glob("lab_6.db.bak.*"))
    connection = sqlite3.connect(path)
    try:
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
        assert connection.execute(
            "SELECT COUNT(*) FROM experiments WHERE end_time IS NULL"
        ).fetchone()[0] == 1
    finally:
        connection.close()


def test_0007_sql_preflight_aborts_without_runner() -> None:
    connection = sqlite3.connect(":memory:")
    connection.isolation_level = None
    try:
        connection.executescript(BASELINE_SQL)
        for migration in (MIGRATION_0004, MIGRATION_0005, MIGRATION_0006):
            connection.executescript(migration.read_text(encoding="utf-8"))
        connection.execute("PRAGMA foreign_keys = ON")
        ids = fx.seed_basic(connection)
        fx.insert_experiment(
            connection,
            ids["strategy_id"],
            ids["strategy_version"],
            experiment_id="exp_bad_direct",
            period_type="research",
            start_time=fx.TS0,
            end_time=None,
            data_manifest_id=ids["manifest_id"],
        )
        connection.commit()
        with pytest.raises(sqlite3.IntegrityError, match="bad = 0"):
            connection.executescript(MIGRATION_0007.read_text(encoding="utf-8"))
        connection.rollback()
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 6
        assert connection.execute(
            "SELECT COUNT(*) FROM experiments WHERE experiment_id = 'exp_bad_direct'"
        ).fetchone()[0] == 1
    finally:
        connection.close()


def test_0007_post_commit_failure_restores_v6(
    tmp_path: Path, monkeypatch
) -> None:
    path = _file_v6(tmp_path)
    _seed(path)
    before_counts = _counts(path)
    before_experiments = _rows(path, "experiments")
    runner = load_runner()
    original = runner.apply_migration_on_connection

    def wrapper(connection, migration):
        original(connection, migration)
        raise RuntimeError("injected post-commit failure")

    monkeypatch.setattr(runner, "apply_migration_on_connection", wrapper)
    with pytest.raises(RuntimeError, match="injected post-commit failure"):
        runner.apply_migration(path)

    assert _journal_and_version(path) == (6, [4, 5, 6])
    assert _counts(path) == before_counts
    assert _rows(path, "experiments") == before_experiments
    assert list(tmp_path.glob("lab_6.db.bak.*"))


def test_0007_enforces_end_time_by_period_type(db_v7, seeded_v7) -> None:
    db_v7.commit()
    fx.insert_manifest(db_v7, "manifest_recorded", source_class="recorded")
    db_v7.commit()
    seeded = dict(seeded_v7)
    seeded["manifest_id"] = "manifest_recorded"

    for period_type in ("research", "validation", "final_test"):
        with pytest.raises(sqlite3.IntegrityError, match="end_time IS NOT NULL"):
            fx.insert_experiment(
                db_v7,
                seeded["strategy_id"],
                seeded["strategy_version"],
                experiment_id=f"exp_bad_{period_type}",
                period_type=period_type,
                start_time=fx.TS0,
                end_time=None,
                data_manifest_id="manifest_recorded",
            )
        db_v7.rollback()

    fx.insert_experiment(
        db_v7,
        seeded["strategy_id"],
        seeded["strategy_version"],
        experiment_id="exp_paper_live",
        period_type="paper_live",
        start_time=fx.TS0,
        end_time=None,
        data_manifest_id=None,
    )
    db_v7.commit()
    assert db_v7.execute(
        "SELECT schema_version FROM experiments WHERE experiment_id = 'exp_paper_live'"
    ).fetchone()[0] == "1.2.0"


def test_0007_preserves_strict_and_chronology_checks(db_v7, seeded_v7) -> None:
    db_v7.commit()
    with pytest.raises(sqlite3.IntegrityError, match="end_time > start_time"):
        fx.insert_experiment(
            db_v7,
            seeded_v7["strategy_id"],
            seeded_v7["strategy_version"],
            experiment_id="exp_equal",
            period_type="research",
            start_time=fx.TS0,
            end_time=fx.TS0,
            data_manifest_id=seeded_v7["manifest_id"],
        )
    db_v7.rollback()
    with pytest.raises(sqlite3.IntegrityError, match="end_time > start_time"):
        fx.insert_experiment(
            db_v7,
            seeded_v7["strategy_id"],
            seeded_v7["strategy_version"],
            experiment_id="exp_reversed",
            period_type="research",
            start_time=fx.TS1,
            end_time=fx.TS0,
            data_manifest_id=seeded_v7["manifest_id"],
        )
    db_v7.rollback()
