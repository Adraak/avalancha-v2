"""Pruebas del backup/restore versionado mínimo pre-1.0 (Etapa 22G).

Cubre la coherencia de backup/restore con tres ejes de versión distintos:

- ``schema_version`` del MANIFEST de backup (este módulo, 22G);
- ``schema_version`` de cada archivo financiero/settings (22D);
- ``schema_version``/``profile_format_version`` de ``profile_metadata.json``
  (22E).

Todas las pruebas de rechazo verifican que el árbol destino quede
byte-idéntico: el invariante crítico de 22G es que ningún backup futuro o
incompatible puede llegar a modificar el perfil destino antes de ser
rechazado.
"""

from __future__ import annotations

import hashlib
import json
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest

from core.models.backup import (
    BackupError,
    RestorePreparationError,
    UnsupportedBackupVersionError,
)
from core.profile_metadata import (
    APP_VERSION_KEY,
    CURRENT_PROFILE_FORMAT_VERSION,
    PROFILE_FORMAT_VERSION_KEY,
    PROFILE_NAME_KEY,
    PROFILE_SLUG_KEY,
    ProfileMetadataError,
)
from core.schema_versioning import CURRENT_SCHEMA_VERSION, SCHEMA_VERSION_KEY
from services.backup_service import MANIFEST_ENTRY_NAME, ProfileBackupService
from services.profile_metadata_service import ProfileMetadataService
from services.profile_restore_service import ProfileRestoreService
from services.profile_service import PerfilAplicacion
from services.settings_service import SettingsService


FIXED_NOW = datetime(2026, 9, 29, 12, 0, 0)
METADATA_LOGICAL_PATH = "profile/profile_metadata.json"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def build_profile(
    tmp_path: Path,
    suffix: str,
    profile_id: str = "personal",
    nombre: str = "Personal",
) -> PerfilAplicacion:
    """Crea un perfil sintético con sus tres carpetas base y su metadata."""
    raiz = tmp_path / "perfiles" / f"{profile_id}_{suffix}"
    profile = PerfilAplicacion(id=profile_id, nombre=nombre, raiz=raiz)
    profile.data_dir.mkdir(parents=True)
    profile.config_dir.mkdir(parents=True)
    profile.reports_dir.mkdir(parents=True)
    ProfileMetadataService().ensure(profile)
    return profile


def build_settings_service(profile: PerfilAplicacion, backup_dir: Path) -> SettingsService:
    """Crea un SettingsService apuntando al perfil y carpeta de respaldo dados."""
    return SettingsService(
        config_dir=profile.config_dir,
        reports_dir=profile.reports_dir,
        backup_dir=backup_dir,
    )


def write_financial_file(profile: PerfilAplicacion, name: str, content: str = "{}") -> Path:
    """Escribe un archivo financiero sintético bajo data/ del perfil."""
    path = profile.data_dir / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def crear_backup(origen: PerfilAplicacion, backup_dir: Path):
    """Crea un backup real del perfil origen usando ProfileBackupService."""
    settings_service = build_settings_service(origen, backup_dir)
    return ProfileBackupService().crear_backup(origen, settings_service, now=FIXED_NOW)


def tree_snapshot(root: Path) -> dict[str, bytes]:
    """Captura bytes de cada archivo bajo root, para comparar antes/después."""
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def metadata_document(
    slug: str,
    profile_format_version: int,
    schema_version: int = 1,
) -> dict[str, Any]:
    return {
        SCHEMA_VERSION_KEY: schema_version,
        PROFILE_FORMAT_VERSION_KEY: profile_format_version,
        PROFILE_SLUG_KEY: slug,
        PROFILE_NAME_KEY: "Personal",
        APP_VERSION_KEY: "0.1.0",
    }


def _entry(path: str, content: bytes, role: str) -> dict[str, Any]:
    return {
        "path": path,
        "size": len(content),
        "sha256": hashlib.sha256(content).hexdigest(),
        "role": role,
    }


def build_raw_zip(
    zip_path: Path,
    *,
    schema_version: int,
    profile_id: str = "personal",
    app_version: str | None = "0.1.0",
    profile_format_version: int | None = 1,
    file_contents: dict[str, tuple[bytes, str]],
    manifest_overrides: dict[str, Any] | None = None,
    skip_entry_for: str | None = None,
) -> None:
    """Construye un ZIP a mano con un manifest crudo, sin pasar por el builder.

    ``file_contents`` mapea ruta lógica -> (bytes, role). ``skip_entry_for``
    omite la entrada del manifest para esa ruta (pero el archivo puede
    seguir presente/ausente en el ZIP según lo que haya en file_contents).
    """
    files_meta = [
        _entry(path, content, role)
        for path, (content, role) in file_contents.items()
        if path != skip_entry_for
    ]
    manifest: dict[str, Any] = {
        "schema_version": schema_version,
        "app": "Avalancha V2",
        "created_at": FIXED_NOW.isoformat(timespec="seconds"),
        "backup_type": "profile",
        "profile_id": profile_id,
        "profile_name": "Personal",
        "key_policy": {
            "includes_reporte_key": False,
            "protection": "missing",
            "portable_across_windows_users": False,
        },
        "files": files_meta,
    }
    if schema_version >= 2:
        if app_version is not None:
            manifest["app_version"] = app_version
        if profile_format_version is not None:
            manifest["profile_format_version"] = profile_format_version
    if manifest_overrides:
        manifest.update(manifest_overrides)

    with zipfile.ZipFile(zip_path, "w") as archive:
        for path, (content, _role) in file_contents.items():
            archive.writestr(path, content)
        archive.writestr(MANIFEST_ENTRY_NAME, json.dumps(manifest))


# ---------------------------------------------------------------------------
# 22: backup v2
# ---------------------------------------------------------------------------


def test_backup_v2_contains_expected_fields(tmp_path: Path) -> None:
    origen = build_profile(tmp_path, "origen")
    write_financial_file(origen, "cuentas.json")
    creado = crear_backup(origen, tmp_path / "backups")

    manifest = creado.manifest
    assert manifest.schema_version == 2
    assert manifest.app_version
    assert manifest.profile_format_version == CURRENT_PROFILE_FORMAT_VERSION

    by_path = {entry.path: entry for entry in manifest.files}
    assert METADATA_LOGICAL_PATH in by_path
    assert by_path[METADATA_LOGICAL_PATH].role == "profile_metadata"

    with zipfile.ZipFile(creado.zip_path) as archive:
        real_bytes = archive.read(METADATA_LOGICAL_PATH)
    assert hashlib.sha256(real_bytes).hexdigest() == by_path[METADATA_LOGICAL_PATH].sha256
    assert len(real_bytes) == by_path[METADATA_LOGICAL_PATH].size


# ---------------------------------------------------------------------------
# 23: roundtrip v2
# ---------------------------------------------------------------------------


def test_roundtrip_v2_recovers_documents_and_metadata(tmp_path: Path) -> None:
    origen = build_profile(tmp_path, "origen")
    write_financial_file(origen, "cuentas.json", '{"cuentas": ["a"]}')
    write_financial_file(origen, "deudas.json", '{"deudas": ["b"]}')
    creado = crear_backup(origen, tmp_path / "backups")
    original_metadata = (origen.raiz / "profile_metadata.json").read_bytes()

    destino = build_profile(tmp_path, "destino")
    write_financial_file(destino, "cuentas.json", '{"cuentas": ["viejo"]}')

    service = ProfileRestoreService()
    resultado = service.restaurar(creado.zip_path, destino)

    assert resultado.outcome == "APPLIED"
    assert (destino.data_dir / "cuentas.json").read_text() == '{"cuentas": ["a"]}'
    assert (destino.data_dir / "deudas.json").read_text() == '{"deudas": ["b"]}'
    assert (destino.raiz / "profile_metadata.json").read_bytes() == original_metadata
    # El perfil restaurado sigue siendo válido para 22E.
    ProfileMetadataService().validate_existing(destino)


# ---------------------------------------------------------------------------
# 24: legacy v1 sin profile_metadata
# ---------------------------------------------------------------------------


def test_legacy_v1_restore_without_metadata_is_still_allowed(tmp_path: Path) -> None:
    destino = build_profile(tmp_path, "destino")
    before_metadata = (destino.raiz / "profile_metadata.json").read_bytes()
    zip_path = tmp_path / "legacy_v1.zip"
    build_raw_zip(
        zip_path,
        schema_version=1,
        file_contents={
            "profile/data/cuentas.json": (b'{"cuentas": ["legacy"]}', "financial_data"),
        },
    )

    resultado = ProfileRestoreService().restaurar(zip_path, destino)

    assert resultado.outcome == "APPLIED"
    assert (destino.data_dir / "cuentas.json").read_text() == '{"cuentas": ["legacy"]}'
    # La metadata preexistente del perfil nunca se tocó: un backup v1 nunca
    # debe destruir profile_metadata.json, aunque no la declare.
    assert (destino.raiz / "profile_metadata.json").read_bytes() == before_metadata


# ---------------------------------------------------------------------------
# 25: manifest futuro
# ---------------------------------------------------------------------------


def test_manifest_futuro_rechazado_antes_de_mutar(tmp_path: Path) -> None:
    destino = build_profile(tmp_path, "destino")
    write_financial_file(destino, "cuentas.json", '{"cuentas": ["actual"]}')
    before = tree_snapshot(destino.raiz)

    zip_path = tmp_path / "futuro.zip"
    build_raw_zip(
        zip_path,
        schema_version=999,
        file_contents={
            "profile/data/cuentas.json": (b'{"cuentas": ["nuevo"]}', "financial_data"),
        },
    )

    with pytest.raises(UnsupportedBackupVersionError):
        ProfileRestoreService().restaurar(zip_path, destino)

    assert tree_snapshot(destino.raiz) == before


# ---------------------------------------------------------------------------
# 26: profile_format_version futuro
# ---------------------------------------------------------------------------


def test_profile_format_futuro_rechazado_antes_de_mutar(tmp_path: Path) -> None:
    destino = build_profile(tmp_path, "destino")
    write_financial_file(destino, "cuentas.json", '{"cuentas": ["actual"]}')
    before = tree_snapshot(destino.raiz)

    future_format = CURRENT_PROFILE_FORMAT_VERSION + 1
    metadata_bytes = json.dumps(
        metadata_document(destino.id, profile_format_version=future_format),
    ).encode("utf-8")
    zip_path = tmp_path / "formato_futuro.zip"
    build_raw_zip(
        zip_path,
        schema_version=2,
        profile_format_version=future_format,
        file_contents={
            "profile/data/cuentas.json": (b'{"cuentas": ["nuevo"]}', "financial_data"),
            METADATA_LOGICAL_PATH: (metadata_bytes, "profile_metadata"),
        },
    )

    with pytest.raises(ProfileMetadataError):
        ProfileRestoreService().restaurar(zip_path, destino)

    assert tree_snapshot(destino.raiz) == before


# ---------------------------------------------------------------------------
# 27: schema futuro interno
# ---------------------------------------------------------------------------


def test_schema_futuro_interno_rechazado_antes_de_mutar(tmp_path: Path) -> None:
    destino = build_profile(tmp_path, "destino")
    write_financial_file(destino, "cuentas.json", '{"cuentas": ["actual"]}')
    before = tree_snapshot(destino.raiz)

    future_schema = CURRENT_SCHEMA_VERSION + 1
    cuentas_bytes = json.dumps(
        {SCHEMA_VERSION_KEY: future_schema, "cuentas": ["futuro"]},
    ).encode("utf-8")
    metadata_bytes = json.dumps(
        metadata_document(destino.id, profile_format_version=1),
    ).encode("utf-8")
    zip_path = tmp_path / "schema_interno_futuro.zip"
    build_raw_zip(
        zip_path,
        schema_version=2,
        file_contents={
            "profile/data/cuentas.json": (cuentas_bytes, "financial_data"),
            METADATA_LOGICAL_PATH: (metadata_bytes, "profile_metadata"),
        },
    )

    with pytest.raises(BackupError):
        ProfileRestoreService().restaurar(zip_path, destino)

    assert tree_snapshot(destino.raiz) == before


# ---------------------------------------------------------------------------
# 28: manifest/metadata mismatch
# ---------------------------------------------------------------------------


def test_manifest_metadata_mismatch_rechazado(tmp_path: Path) -> None:
    destino = build_profile(tmp_path, "destino")
    before = tree_snapshot(destino.raiz)

    # El manifest declara 1, pero profile_metadata.json dentro del ZIP
    # declara 2: inconsistencia que invalida el respaldo por completo,
    # sin importar si además 2 resulta futuro para la versión actual.
    metadata_bytes = json.dumps(
        metadata_document(destino.id, profile_format_version=2),
    ).encode("utf-8")
    zip_path = tmp_path / "mismatch.zip"
    build_raw_zip(
        zip_path,
        schema_version=2,
        profile_format_version=1,
        file_contents={
            "profile/data/cuentas.json": (b'{"cuentas": []}', "financial_data"),
            METADATA_LOGICAL_PATH: (metadata_bytes, "profile_metadata"),
        },
    )

    with pytest.raises(Exception):
        ProfileRestoreService().restaurar(zip_path, destino)

    assert tree_snapshot(destino.raiz) == before


# ---------------------------------------------------------------------------
# 29: metadata faltante en v2
# ---------------------------------------------------------------------------


def test_metadata_faltante_en_v2_rechazada(tmp_path: Path) -> None:
    destino = build_profile(tmp_path, "destino")
    before = tree_snapshot(destino.raiz)

    zip_path = tmp_path / "sin_metadata.zip"
    build_raw_zip(
        zip_path,
        schema_version=2,
        file_contents={
            "profile/data/cuentas.json": (b'{"cuentas": []}', "financial_data"),
        },
    )

    with pytest.raises(RestorePreparationError):
        ProfileRestoreService().restaurar(zip_path, destino)

    assert tree_snapshot(destino.raiz) == before


# ---------------------------------------------------------------------------
# 30: metadata corrupta
# ---------------------------------------------------------------------------


def test_metadata_corrupta_rechazada(tmp_path: Path) -> None:
    destino = build_profile(tmp_path, "destino")
    before = tree_snapshot(destino.raiz)

    zip_path = tmp_path / "metadata_corrupta.zip"
    build_raw_zip(
        zip_path,
        schema_version=2,
        file_contents={
            "profile/data/cuentas.json": (b'{"cuentas": []}', "financial_data"),
            METADATA_LOGICAL_PATH: (b"{esto no es json", "profile_metadata"),
        },
    )

    with pytest.raises(RestorePreparationError):
        ProfileRestoreService().restaurar(zip_path, destino)

    assert tree_snapshot(destino.raiz) == before


# ---------------------------------------------------------------------------
# 31: legacy documento implícito sin schema_version
# ---------------------------------------------------------------------------


def test_legacy_documento_implicito_sin_schema_version_se_restaura(
    tmp_path: Path,
) -> None:
    destino = build_profile(tmp_path, "destino")
    zip_path = tmp_path / "legacy_implicito.zip"
    build_raw_zip(
        zip_path,
        schema_version=1,
        file_contents={
            # sin "schema_version": documento legacy, efectivamente v1.
            "profile/data/cuentas.json": (b'{"cuentas": ["sin-version"]}', "financial_data"),
        },
    )

    resultado = ProfileRestoreService().restaurar(zip_path, destino)

    assert resultado.outcome == "APPLIED"
    restored = json.loads((destino.data_dir / "cuentas.json").read_text())
    assert SCHEMA_VERSION_KEY not in restored
    assert restored["cuentas"] == ["sin-version"]


# ---------------------------------------------------------------------------
# 32: app_version distinta no bloquea
# ---------------------------------------------------------------------------


def test_app_version_distinta_no_bloquea_restore(tmp_path: Path) -> None:
    destino = build_profile(tmp_path, "destino")
    metadata_bytes = json.dumps(
        metadata_document(destino.id, profile_format_version=1),
    ).encode("utf-8")
    zip_path = tmp_path / "app_version_distinta.zip"
    build_raw_zip(
        zip_path,
        schema_version=2,
        app_version="99.99.99-sintetica",
        file_contents={
            "profile/data/cuentas.json": (b'{"cuentas": []}', "financial_data"),
            METADATA_LOGICAL_PATH: (metadata_bytes, "profile_metadata"),
        },
    )

    resultado = ProfileRestoreService().restaurar(zip_path, destino)

    assert resultado.outcome == "APPLIED"
