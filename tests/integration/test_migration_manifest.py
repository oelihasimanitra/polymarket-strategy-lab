"""Vérifie la baseline SHA-256 des migrations SQLite.

Cette baseline est auto-référentielle au sens où elle est un fichier du dépôt
qui décrit d'autres fichiers du dépôt. Elle détecte une modification d'une
migration sans mise à jour du manifeste. Elle ne prouve ni l'authenticité ni
l'historique Git : un acteur qui modifie la migration, le manifeste, ce test
et son empreinte épinglée peut produire un état cohérent. La preuve
d'historique exige un commit Git de référence conservé par le propriétaire.

Le manifeste n'est pas un fichier ``.sql`` et n'est pas enregistré dans le
runner de migration. Il n'est donc jamais appliqué comme une migration.
"""

from __future__ import annotations

import hashlib
import runpy
import shutil
from pathlib import Path

import pytest

from labtest.contracts import SQL_SCHEMA_PATH

MIGRATIONS_DIR = SQL_SCHEMA_PATH.parent / "migrations"
MANIFEST = MIGRATIONS_DIR / "SHA256SUMS"
RUNNER = MIGRATIONS_DIR / "run_migration.py"

EXPECTED_MIGRATIONS = (
    "0004_consolidation.sql",
    "0005_p0_foundations.sql",
    "0006_p0_ledger.sql",
    "0007_contract_sql_alignment.sql",
)

#: Empreinte du manifeste revu. Toute modification du manifeste exige de
#: mettre à jour cette constante après revue explicite. Ce n'est pas une
#: signature externe : le test et le manifeste restent dans le même dépôt.
EXPECTED_MANIFEST_SHA256 = (
    "cce06aa3063a36416c92ecea7e4bc43a5c867989615bca7f65c3cbef5ed72fcd"
)


def _parse_manifest(path: Path = MANIFEST) -> dict[str, str]:
    entries: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) != 2:
            raise AssertionError(f"ligne de manifeste invalide : {line!r}")
        digest, name = parts
        if name in entries:
            raise AssertionError(f"migration dupliquée dans le manifeste : {name}")
        entries[name] = digest
    return entries


def _hash_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _manifest_header() -> dict[str, str]:
    header: dict[str, str] = {}
    for line in MANIFEST.read_text(encoding="utf-8").splitlines():
        if not line.startswith("#"):
            continue
        text = line.removeprefix("#").strip()
        if ":" not in text:
            continue
        key, value = text.split(":", 1)
        header[key.strip()] = value.strip()
    return header


def test_manifest_declares_explicit_format_scope_and_coverage() -> None:
    header = _manifest_header()
    assert header["format"] == "sha256sum-v1"
    assert header["scope"] == "schemas/migrations/*.sql"
    assert tuple(header["covered"].split()) == EXPECTED_MIGRATIONS


def test_manifest_matches_declared_migrations() -> None:
    entries = _parse_manifest()
    assert tuple(entries) == EXPECTED_MIGRATIONS
    for name, expected in entries.items():
        path = MIGRATIONS_DIR / name
        assert path.is_file(), name
        assert _hash_file(path) == expected, f"{name}: hash différent"


def test_manifest_covers_all_migrations_and_no_other_sql() -> None:
    entries = _parse_manifest()
    files = {path.name for path in MIGRATIONS_DIR.glob("*.sql")}
    assert files == set(EXPECTED_MIGRATIONS)
    assert set(entries) == files


def test_manifest_digests_are_canonical_sha256() -> None:
    for name, digest in _parse_manifest().items():
        assert len(digest) == 64, name
        assert digest == digest.lower(), name
        assert all(character in "0123456789abcdef" for character in digest), name


def test_manifest_is_not_itself_a_migration() -> None:
    entries = _parse_manifest()
    assert MANIFEST.suffix != ".sql"
    assert MANIFEST.name not in entries
    assert not any(name.endswith("SHA256SUMS") for name in entries)


def test_runner_registry_does_not_contain_manifest() -> None:
    namespace = runpy.run_path(str(RUNNER))
    registered = {
        Path(path).name
        for path, *_ in namespace["MIGRATION_REGISTRY"].values()
    }
    assert MANIFEST.name not in registered
    assert registered == set(EXPECTED_MIGRATIONS)


def test_manifest_itself_matches_reviewed_baseline() -> None:
    assert _hash_file(MANIFEST) == EXPECTED_MANIFEST_SHA256


def test_modified_migration_is_detected_without_manifest_update(
    tmp_path: Path,
) -> None:
    copy = tmp_path / "migrations"
    shutil.copytree(MIGRATIONS_DIR, copy)
    entries = _parse_manifest(copy / "SHA256SUMS")
    target = copy / "0005_p0_foundations.sql"
    target.write_bytes(target.read_bytes() + b"\n-- modification non revue\n")
    assert _hash_file(target) != entries["0005_p0_foundations.sql"]


def test_unlisted_migration_is_detected_on_a_copy(tmp_path: Path) -> None:
    copy = tmp_path / "migrations"
    shutil.copytree(MIGRATIONS_DIR, copy)
    (copy / "0008_unreviewed.sql").write_text("-- unreviewed\n", encoding="utf-8")
    actual = {path.name for path in copy.glob("*.sql")}
    assert actual != set(EXPECTED_MIGRATIONS)
    assert set(_parse_manifest(copy / "SHA256SUMS")) != actual


def test_manifest_entry_without_file_is_detected(tmp_path: Path) -> None:
    copy = tmp_path / "migrations"
    shutil.copytree(MIGRATIONS_DIR, copy)
    manifest = copy / "SHA256SUMS"
    manifest.write_text(
        manifest.read_text(encoding="utf-8")
        + f"{'0' * 64}  0008_unreviewed.sql\n",
        encoding="utf-8",
    )
    entries = _parse_manifest(manifest)
    assert set(entries) != set(EXPECTED_MIGRATIONS)


def test_invalid_manifest_line_is_rejected(tmp_path: Path) -> None:
    manifest = tmp_path / "SHA256SUMS"
    manifest.write_text("not-a-valid-line\n", encoding="utf-8")
    with pytest.raises(AssertionError):
        _parse_manifest(manifest)
