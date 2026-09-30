"""Pruebas del contrato base de manifests de respaldo por perfil."""

from __future__ import annotations

from dataclasses import replace

import pytest

from core.models.backup import (
    APP_NAME,
    BACKUP_TYPE_PROFILE,
    SCHEMA_VERSION,
    BackupFileEntry,
    BackupKeyPolicy,
    BackupManifest,
    InvalidBackupManifestError,
    UnsafeBackupPathError,
    UnsupportedBackupVersionError,
    normalize_backup_path,
)
from services.backup_manifest_service import BackupManifestService


VALID_HASH = "a" * 64
VALID_CREATED_AT = "2026-09-29T12:00:00"


def valid_entry(path: str = "profile/data/cuentas.json") -> BackupFileEntry:
    """Crea una entrada valida para pruebas."""
    return BackupFileEntry(
        path=path,
        size=123,
        sha256=VALID_HASH,
        role="financial_data",
    )


def valid_key_policy(
    protection: str = "dpapi",
    includes_reporte_key: bool = True,
) -> BackupKeyPolicy:
    """Crea una politica de clave valida."""
    return BackupKeyPolicy(
        includes_reporte_key=includes_reporte_key,
        protection=protection,
        portable_across_windows_users=False,
    )


def valid_manifest(
    files: tuple[BackupFileEntry, ...] | None = None,
) -> BackupManifest:
    """Crea un manifest valido para pruebas."""
    return BackupManifest(
        schema_version=SCHEMA_VERSION,
        app=APP_NAME,
        created_at=VALID_CREATED_AT,
        backup_type=BACKUP_TYPE_PROFILE,
        profile_id="personal",
        profile_name="Personal",
        key_policy=valid_key_policy(),
        files=(valid_entry(),) if files is None else files,
    )


def test_backup_file_entry_valid() -> None:
    """Acepta una entrada de archivo valida y normaliza el hash."""
    entry = BackupFileEntry(
        path="profile/data/cuentas.json",
        size=0,
        sha256="A" * 64,
        role="financial_data",
    )

    assert entry.path == "profile/data/cuentas.json"
    assert entry.sha256 == "a" * 64


def test_backup_file_entry_rejects_negative_size() -> None:
    """Rechaza tamaños negativos."""
    with pytest.raises(InvalidBackupManifestError):
        BackupFileEntry("profile/data/cuentas.json", -1, VALID_HASH, "settings")


@pytest.mark.parametrize("size", [True, False, "1"])
def test_backup_file_entry_rejects_non_integer_size(size: object) -> None:
    """Rechaza tamaños que no son enteros reales."""
    with pytest.raises(InvalidBackupManifestError):
        BackupFileEntry(
            "profile/data/cuentas.json",
            size,  # type: ignore[arg-type]
            VALID_HASH,
            "settings",
        )


@pytest.mark.parametrize("size", [0, 1])
def test_backup_file_entry_accepts_integer_size(size: int) -> None:
    """Acepta tamaños enteros reales no negativos."""
    entry = BackupFileEntry(
        "profile/data/cuentas.json",
        size,
        VALID_HASH,
        "settings",
    )

    assert entry.size == size


def test_backup_file_entry_rejects_invalid_sha256() -> None:
    """Rechaza hashes que no son SHA-256 hexadecimales."""
    with pytest.raises(InvalidBackupManifestError):
        BackupFileEntry("profile/data/cuentas.json", 1, "xyz", "settings")


def test_backup_file_entry_rejects_invalid_role() -> None:
    """Rechaza roles arbitrarios."""
    with pytest.raises(InvalidBackupManifestError):
        BackupFileEntry("profile/data/cuentas.json", 1, VALID_HASH, "otro")


def test_manifest_valid() -> None:
    """Acepta un manifest por perfil valido."""
    manifest = valid_manifest()

    assert manifest.schema_version == 1
    assert manifest.backup_type == "profile"
    assert manifest.files[0].role == "financial_data"


def test_manifest_rejects_unsupported_schema_version() -> None:
    """Rechaza versiones de schema no soportadas."""
    with pytest.raises(UnsupportedBackupVersionError):
        replace(valid_manifest(), schema_version=2)


def test_manifest_rejects_wrong_app() -> None:
    """Rechaza manifests de otra aplicacion."""
    with pytest.raises(InvalidBackupManifestError):
        replace(valid_manifest(), app="Otra App")


def test_manifest_rejects_wrong_backup_type() -> None:
    """Rechaza tipos de backup fuera de profile."""
    with pytest.raises(InvalidBackupManifestError):
        replace(valid_manifest(), backup_type="global")


def test_manifest_rejects_empty_profile_id() -> None:
    """Rechaza perfiles sin identificador."""
    with pytest.raises(InvalidBackupManifestError):
        replace(valid_manifest(), profile_id=" ")


def test_manifest_json_round_trip() -> None:
    """Serializa y deserializa sin perder datos."""
    service = BackupManifestService()
    manifest = valid_manifest(
        (
            valid_entry("profile/data/cuentas.json"),
            BackupFileEntry(
                "profile/config/settings.json",
                42,
                "b" * 64,
                "settings",
            ),
        ),
    )

    loaded = service.from_json(service.to_json(manifest))

    assert loaded == manifest


def test_manifest_rejects_corrupt_json() -> None:
    """Rechaza JSON corrupto."""
    with pytest.raises(InvalidBackupManifestError):
        BackupManifestService().from_json("{")


def test_manifest_rejects_files_that_are_not_list() -> None:
    """Rechaza files cuando no es lista."""
    data = valid_manifest().to_dict()
    data["files"] = {}

    with pytest.raises(InvalidBackupManifestError):
        BackupManifest.from_dict(data)


def test_manifest_rejects_invalid_file_entry() -> None:
    """Propaga errores de entradas invalidas."""
    data = valid_manifest().to_dict()
    data["files"] = [{"path": "", "size": 1, "sha256": VALID_HASH, "role": "settings"}]

    with pytest.raises(UnsafeBackupPathError):
        BackupManifest.from_dict(data)


@pytest.mark.parametrize(
    "path",
    [
        "../archivo",
        "../../archivo",
        "profile/../archivo",
    ],
)
def test_path_rejects_traversal(path: str) -> None:
    """Rechaza traversal explicito."""
    with pytest.raises(UnsafeBackupPathError):
        normalize_backup_path(path)


def test_path_rejects_posix_absolute_path() -> None:
    """Rechaza rutas absolutas POSIX."""
    with pytest.raises(UnsafeBackupPathError):
        normalize_backup_path("/archivo")


@pytest.mark.parametrize("path", ["C:\\archivo", "C:/archivo"])
def test_path_rejects_windows_absolute_path(path: str) -> None:
    """Rechaza rutas absolutas con unidad Windows."""
    with pytest.raises(UnsafeBackupPathError):
        normalize_backup_path(path)


@pytest.mark.parametrize("path", ["C:archivo", "C:..\\archivo"])
def test_path_rejects_windows_drive_relative_path(path: str) -> None:
    """Rechaza rutas relativas a una unidad de Windows."""
    with pytest.raises(UnsafeBackupPathError):
        normalize_backup_path(path)


def test_path_rejects_unc_path() -> None:
    """Rechaza rutas UNC."""
    with pytest.raises(UnsafeBackupPathError):
        normalize_backup_path("\\\\servidor\\archivo")


def test_path_rejects_empty_path() -> None:
    """Rechaza rutas vacias."""
    with pytest.raises(UnsafeBackupPathError):
        normalize_backup_path(" ")


def test_path_rejects_dot_component() -> None:
    """Rechaza componentes punto sin normalizarlos silenciosamente."""
    with pytest.raises(UnsafeBackupPathError):
        normalize_backup_path("profile/./archivo")


def test_path_rejects_mixed_separator_traversal() -> None:
    """Rechaza traversal mezclando separadores."""
    with pytest.raises(UnsafeBackupPathError):
        normalize_backup_path("profile\\data\\..\\archivo")


def test_path_rejects_repeated_separators() -> None:
    """Rechaza separadores repetidos que crean componentes ambiguos."""
    with pytest.raises(UnsafeBackupPathError):
        normalize_backup_path("profile//data/cuentas.json")


def test_path_rejects_trailing_space_component() -> None:
    """Rechaza componentes con espacio terminal."""
    with pytest.raises(UnsafeBackupPathError):
        normalize_backup_path("profile/data/file ")


def test_path_rejects_trailing_dot_component() -> None:
    """Rechaza componentes con punto terminal."""
    with pytest.raises(UnsafeBackupPathError):
        normalize_backup_path("profile/data/file.")


def test_path_rejects_alternate_data_stream_colon() -> None:
    """Rechaza dos puntos para evitar Alternate Data Streams."""
    with pytest.raises(UnsafeBackupPathError):
        normalize_backup_path("profile/data/file.txt:stream")


@pytest.mark.parametrize("path", ["CON", "profile/data/nul.json"])
def test_path_rejects_windows_reserved_names(path: str) -> None:
    """Rechaza nombres reservados de Windows, incluso con extension."""
    with pytest.raises(UnsafeBackupPathError):
        normalize_backup_path(path)


def test_path_accepts_internal_spaces() -> None:
    """Acepta espacios internos normales en nombres relativos."""
    assert (
        normalize_backup_path("profile/reportes/Informe mensual.avr")
        == "profile/reportes/Informe mensual.avr"
    )


def test_path_accepts_normal_relative_path() -> None:
    """Acepta paths relativos normales."""
    assert (
        normalize_backup_path("profile/config/reporte.key")
        == "profile/config/reporte.key"
    )


def test_manifest_rejects_exact_duplicate_path() -> None:
    """Rechaza duplicados exactos."""
    with pytest.raises(InvalidBackupManifestError):
        valid_manifest((valid_entry(), valid_entry()))


def test_manifest_rejects_windows_equivalent_duplicate_path() -> None:
    """Rechaza duplicados equivalentes en Windows por separador y casing."""
    with pytest.raises(InvalidBackupManifestError):
        valid_manifest(
            (
                valid_entry("profile/data/cuentas.json"),
                valid_entry("PROFILE\\DATA\\CUENTAS.JSON"),
            ),
        )


def test_key_policy_accepts_dpapi() -> None:
    """Acepta politica DPAPI contractual sin invocar DPAPI."""
    policy = valid_key_policy("dpapi")

    assert policy.protection == "dpapi"
    assert not policy.portable_across_windows_users


def test_key_policy_accepts_plain() -> None:
    """Acepta politica de clave plana heredada."""
    policy = valid_key_policy("plain")

    assert policy.protection == "plain"


def test_key_policy_accepts_missing() -> None:
    """Acepta politica cuando no se incluye reporte.key."""
    policy = valid_key_policy("missing", includes_reporte_key=False)

    assert policy.protection == "missing"
    assert not policy.includes_reporte_key


@pytest.mark.parametrize(
    ("protection", "includes_reporte_key"),
    [
        ("dpapi", False),
        ("plain", False),
        ("missing", True),
    ],
)
def test_key_policy_rejects_incoherent_contract(
    protection: str,
    includes_reporte_key: bool,
) -> None:
    """Rechaza combinaciones incoherentes de reporte.key."""
    with pytest.raises(InvalidBackupManifestError):
        valid_key_policy(protection, includes_reporte_key)


def test_key_policy_rejects_invalid_protection() -> None:
    """Rechaza protecciones no soportadas."""
    with pytest.raises(InvalidBackupManifestError):
        valid_key_policy("rot13")


def test_file_entry_from_dict_rejects_none_path() -> None:
    """Rechaza path None sin convertirlo a texto."""
    data = {
        "path": None,
        "size": 1,
        "sha256": VALID_HASH,
        "role": "settings",
    }

    with pytest.raises(InvalidBackupManifestError):
        BackupFileEntry.from_dict(data)


def test_file_entry_from_dict_rejects_numeric_path() -> None:
    """Rechaza path numerico sin convertirlo a texto."""
    data = {
        "path": 123,
        "size": 1,
        "sha256": VALID_HASH,
        "role": "settings",
    }

    with pytest.raises(InvalidBackupManifestError):
        BackupFileEntry.from_dict(data)


def test_file_entry_from_dict_rejects_non_string_sha256() -> None:
    """Rechaza sha256 no string."""
    data = {
        "path": "profile/config/settings.json",
        "size": 1,
        "sha256": None,
        "role": "settings",
    }

    with pytest.raises(InvalidBackupManifestError):
        BackupFileEntry.from_dict(data)


def test_file_entry_from_dict_rejects_non_string_role() -> None:
    """Rechaza role no string."""
    data = {
        "path": "profile/config/settings.json",
        "size": 1,
        "sha256": VALID_HASH,
        "role": 123,
    }

    with pytest.raises(InvalidBackupManifestError):
        BackupFileEntry.from_dict(data)


def test_manifest_from_dict_rejects_non_string_profile_id() -> None:
    """Rechaza profile_id no string."""
    data = valid_manifest().to_dict()
    data["profile_id"] = 123

    with pytest.raises(InvalidBackupManifestError):
        BackupManifest.from_dict(data)


def test_key_policy_from_dict_rejects_non_string_protection() -> None:
    """Rechaza protection no string."""
    data = valid_key_policy().to_dict()
    data["protection"] = None

    with pytest.raises(InvalidBackupManifestError):
        BackupKeyPolicy.from_dict(data)


@pytest.mark.parametrize(
    "field",
    [
        "includes_reporte_key",
        "portable_across_windows_users",
        "protection",
    ],
)
def test_key_policy_from_dict_rejects_missing_required_fields(field: str) -> None:
    """Rechaza politicas de clave con campos obligatorios ausentes."""
    data = valid_key_policy().to_dict()
    data.pop(field)

    with pytest.raises(InvalidBackupManifestError):
        BackupKeyPolicy.from_dict(data)


@pytest.mark.parametrize("value", [0, 1, "true", "false", None, []])
def test_key_policy_from_dict_rejects_non_bool_includes_flag(
    value: object,
) -> None:
    """Rechaza includes_reporte_key no booleano real."""
    data = valid_key_policy().to_dict()
    data["includes_reporte_key"] = value

    with pytest.raises(InvalidBackupManifestError):
        BackupKeyPolicy.from_dict(data)


@pytest.mark.parametrize("value", [0, 1, "true", "false", None, []])
def test_key_policy_from_dict_rejects_non_bool_portability_flag(
    value: object,
) -> None:
    """Rechaza portable_across_windows_users no booleano real."""
    data = valid_key_policy().to_dict()
    data["portable_across_windows_users"] = value

    with pytest.raises(InvalidBackupManifestError):
        BackupKeyPolicy.from_dict(data)


def test_manifest_rejects_empty_files_list() -> None:
    """Un manifest sin archivos no es valido para respaldos por perfil."""
    with pytest.raises(InvalidBackupManifestError):
        valid_manifest(())


def test_manifest_service_save_and_load_explicit_path(tmp_path) -> None:
    """El servicio opera solo sobre rutas entregadas por el consumidor."""
    service = BackupManifestService()
    target = tmp_path / "manifest.json"
    manifest = valid_manifest()

    service.save_json(manifest, target)
    loaded = service.load_json(target)

    assert loaded == manifest
