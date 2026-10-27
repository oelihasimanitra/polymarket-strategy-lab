"""Registre des schémas contractuels approuvés pour la production.

Le registre est une donnée système, pas un objet fourni par l'appelant. Les
entrées sont immuables et exposées via une vue en lecture seule. Le writer
relit le registre et le fichier à chaque écriture : une modification du schéma
sur disque sans mise à jour de l'approbation est refusée.

Cette barrière protège contre les modifications accidentelles et les erreurs
de configuration. Elle ne protège pas contre du code arbitraire exécuté dans
le même processus, qui peut réassigner des globals ou contourner des attributs
privés avec ``object.__setattr__``.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any

from .immutability import canonical_json, freeze_json

__all__ = [
    "APPROVED_CONTRACTS",
    "ApprovedContract",
    "ContractHashMismatchError",
    "ContractNotRegisteredError",
    "ContractRegistryError",
    "ContractSchemaMalformedError",
    "ContractSchemaMismatchError",
    "ContractSchemaMissingError",
    "ContractSchemaUnreadableError",
    "ContractVersionMismatchError",
    "load_approved_schema",
    "schema_fingerprint",
    "verify_approved_schema",
]

ROOT = Path(__file__).resolve().parents[3]


class ContractRegistryError(RuntimeError):
    """Le registre ou le schéma approuvé ne peut pas être utilisé."""


class ContractNotRegisteredError(ContractRegistryError):
    """Le nom demandé n'est pas un contrat approuvé."""


class ContractSchemaMissingError(ContractRegistryError):
    """Le fichier de schéma approuvé est absent."""


class ContractSchemaUnreadableError(ContractRegistryError):
    """Le fichier de schéma approuvé existe mais ne peut pas être lu."""


class ContractSchemaMalformedError(ContractRegistryError):
    """Le fichier de schéma approuvé n'est pas un objet JSON valide."""


class ContractHashMismatchError(ContractRegistryError):
    """Le SHA-256 du fichier ne correspond pas au registre."""


class ContractVersionMismatchError(ContractRegistryError):
    """La version const du schéma ne correspond pas au registre."""


class ContractSchemaMismatchError(ContractRegistryError):
    """Un schéma fourni n'est pas exactement le schéma approuvé."""


@dataclass(frozen=True)
class ApprovedContract:
    name: str
    version: str
    schema_sha256: str
    relative_path: str

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("ApprovedContract.name doit être non vide")
        if not self.version:
            raise ValueError("ApprovedContract.version doit être non vide")
        digest = self.schema_sha256
        if (
            not isinstance(digest, str)
            or len(digest) != 64
            or any(character not in "0123456789abcdef" for character in digest)
        ):
            raise ValueError("ApprovedContract.schema_sha256 doit être un SHA-256 hexadécimal")
        path = Path(self.relative_path)
        if path.is_absolute() or ".." in path.parts:
            raise ValueError("ApprovedContract.relative_path doit rester dans le dépôt")


#: Donnée système privée. Le writer ne consulte pas la vue publique exposée
#: ci-dessous, afin qu'une réassignation accidentelle de ce nom ne modifie pas
#: l'approbation utilisée à l'écriture.
_APPROVED_CONTRACTS: tuple[ApprovedContract, ...] = (
    ApprovedContract(
        name="experiment",
        version="1.2.0",
        schema_sha256="6d20ab724f2b0521f95c5ab4032db1d14a3a14233ea9a3a90a124743de93fe85",
        relative_path="contracts/experiment.schema.json",
    ),
    ApprovedContract(
        name="fee_schedule",
        version="1.2.0",
        schema_sha256="92bd9a17040e7655fdb34c793d693a7ac718dd2f76211fe84224bb0098ee9918",
        relative_path="contracts/fee_schedule.schema.json",
    ),
)

#: Vue publique en lecture seule. Une affectation lève ``TypeError``.
APPROVED_CONTRACTS: Mapping[str, ApprovedContract] = MappingProxyType(
    {entry.name: entry for entry in _APPROVED_CONTRACTS}
)


def _approved(name: str) -> ApprovedContract:
    for entry in _APPROVED_CONTRACTS:
        if entry.name == name:
            return entry
    raise ContractNotRegisteredError(
        f"contrat non enregistré pour la production : {name!r}"
    )


def _resolve_root(root: Path | None) -> Path:
    # Ne pas lier ROOT comme valeur par défaut : les tests doivent pouvoir
    # pointer une copie temporaire sans modifier le dépôt.
    return ROOT if root is None else Path(root)


def load_approved_schema(
    name: str,
    *,
    root: Path | None = None,
) -> tuple[Mapping[str, Any], ApprovedContract]:
    """Charge, vérifie et gèle le schéma approuvé.

    Le hash est calculé sur les octets exacts du fichier. Le JSON est ensuite
    analysé, sa version est comparée au registre, puis l'objet est gelé
    récursivement avant d'être retourné.
    """
    approval = _approved(name)
    path = _resolve_root(root) / approval.relative_path
    try:
        raw = path.read_bytes()
    except FileNotFoundError as exc:
        raise ContractSchemaMissingError(
            f"schéma approuvé introuvable : {path}"
        ) from exc
    except OSError as exc:
        raise ContractSchemaUnreadableError(
            f"schéma approuvé illisible : {path}: {exc}"
        ) from exc

    digest = hashlib.sha256(raw).hexdigest()
    if digest != approval.schema_sha256:
        raise ContractHashMismatchError(
            f"{name}: SHA-256 {digest} différent du registre "
            f"{approval.schema_sha256}"
        )

    try:
        schema = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ContractSchemaMalformedError(
            f"{name}: schéma approuvé illisible : {exc}"
        ) from exc
    if not isinstance(schema, dict):
        raise ContractSchemaMalformedError(
            f"{name}: le schéma approuvé doit être un objet JSON"
        )

    properties = schema.get("properties")
    version_node = (
        properties.get("schema_version")
        if isinstance(properties, dict)
        else None
    )
    if not isinstance(version_node, dict):
        raise ContractSchemaMalformedError(
            f"{name}: properties.schema_version doit être un objet"
        )
    version = version_node.get("const")
    if not isinstance(version, str):
        raise ContractSchemaMalformedError(
            f"{name}: properties.schema_version.const doit être une chaîne"
        )
    if version != approval.version:
        raise ContractVersionMismatchError(
            f"{name}: version {version!r} différente du registre "
            f"{approval.version!r}"
        )

    frozen = freeze_json(schema)
    assert isinstance(frozen, Mapping)
    return frozen, approval


def schema_fingerprint(schema: Mapping[str, Any]) -> str:
    """Empreinte canonique d'un schéma déjà chargé (diagnostic)."""
    return hashlib.sha256(canonical_json(schema).encode("utf-8")).hexdigest()


def verify_approved_schema(
    name: str,
    schema: Any,
    *,
    root: Path | None = None,
) -> None:
    """Vérifie qu'un objet schéma est exactement le schéma approuvé actuel."""
    official, approval = load_approved_schema(name, root=root)
    if not isinstance(schema, Mapping):
        raise ContractSchemaMismatchError(
            f"{name}: le schéma fourni n'est pas un objet JSON"
        )
    if freeze_json(schema) != official:
        raise ContractSchemaMismatchError(
            f"{name}: le schéma fourni n'est pas le schéma approuvé "
            f"({approval.relative_path})"
        )
