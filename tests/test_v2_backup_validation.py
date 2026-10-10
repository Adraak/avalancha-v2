"""Pruebas adversariales de validación read-only de backups ZIP (Etapa 18D)."""

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
    BackupValidationError,
    InvalidBackupManifestError,
    ProfileMismatchError,
    UnsafeBackupPathError,
    UnsupportedBackupVersionError,
)
from services.backup_service import (
    MANIFEST_ENTRY_NAME,
    BackupValidator,
    ProfileBackupService,
)
from services.profile_metadata_service import ProfileMetadataService
from services.profile_service import PerfilAplicacion
from services.settings_service import SettingsService


FIXED_NOW = datetime(2026, 9, 29, 12, 0, 0)
VALID_HASH = "a" * 64


def build_profile(
    tmp_path: Path,
    profile_id: str = "personal",
    nombre: str = "Personal",
) -> PerfilAplicacion:
    """Crea un perfil sintético con sus tres carpetas base y su metadata."""
    raiz = tmp_path / "perfiles" / profile_id
    profile = PerfilAplicacion(id=profile_id, nombre=nombre, raiz=raiz)
    profile.data_dir.mkdir(parents=True)
    profile.config_dir.mkdir(parents=True)
    profile.reports_dir.mkdir(parents=True)
    ProfileMetadataService().ensure(profile)
    return profile


def build_settings_service(
    profile: PerfilAplicacion,
    backup_dir: Path,
    *,
    persist: bool = False,
) -> SettingsService:
    """Crea un SettingsService apuntando al perfil y carpeta de respaldo dados."""
    service = SettingsService(
        config_dir=profile.config_dir,
        reports_dir=profile.reports_dir,
        backup_dir=backup_dir,
    )
    if persist:
        service.guardar_configuracion(service.obtener_configuracion_por_defecto())
    return service


def write_financial_file(
    profile: PerfilAplicacion,
    name: str,
    content: str = "{}",
) -> Path:
    """Escribe un archivo financiero sintético bajo data/ del perfil."""
    path = profile.data_dir / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def raw_manifest_dict(
    *,
    schema_version: int = 1,
    app: str = "Avalancha V2",
    backup_type: str = "profile",
    profile_id: str = "personal",
    profile_name: str = "Personal",
    created_at: str = "2026-09-29T12:00:00",
    key_policy: dict[str, Any] | None = None,
    files: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Construye un dict de manifest crudo, editable por los tests adversariales."""
    return {
        "schema_version": schema_version,
        "app": app,
        "created_at": created_at,
        "backup_type": backup_type,
        "profile_id": profile_id,
        "profile_name": profile_name,
        "key_policy": key_policy
        if key_policy is not None
        else {
            "includes_reporte_key": False,
            "protection": "missing",
            "portable_across_windows_users": False,
        },
        "files": files
        if files is not None
        else [
            {
                "path": "profile/data/cuentas.json",
                "size": len(b"contenido"),
                "sha256": hashlib.sha256(b"contenido").hexdigest(),
                "role": "financial_data",
            },
        ],
    }


def build_zip_from_raw_manifest(
    zip_path: Path,
    manifest_dict: dict[str, Any] | None,
    file_contents: dict[str, bytes] | None = None,
    *,
    manifest_json: str | None = None,
) -> None:
    """Construye un ZIP a mano a partir de un manifest crudo (sin validar)."""
    contents = (
        file_contents
        if file_contents is not None
        else {"profile/data/cuentas.json": b"contenido"}
    )
    if manifest_json is not None:
        text = manifest_json
    else:
        text = json.dumps(manifest_dict)
    with zipfile.ZipFile(zip_path, "w") as archive:
        for name, data in contents.items():
            archive.writestr(name, data)
        archive.writestr(MANIFEST_ENTRY_NAME, text)


# ---------------------------------------------------------------------------
# 1. Backup válido aceptado
# ---------------------------------------------------------------------------


def test_backup_valido_es_aceptado(tmp_path: Path) -> None:
    """Un respaldo producido por ProfileBackupService valida como correcto."""
    profile = build_profile(tmp_path)
    write_financial_file(profile, "cuentas.json")
    settings_service = build_settings_service(profile, tmp_path / "backups")
    creado = ProfileBackupService().crear_backup(
        profile,
        settings_service,
        now=FIXED_NOW,
    )

    resultado = BackupValidator().validar_backup(
        creado.zip_path,
        expected_profile_id=profile.id,
    )

    assert resultado.valid is True
    assert resultado.error is None
    assert resultado.profile_id == profile.id
    assert resultado.file_count == len(creado.manifest.files)
    assert resultado.schema_version == 2


# ---------------------------------------------------------------------------
# 2-3. ZIP corrupto / truncado
# ---------------------------------------------------------------------------


def test_bytes_que_no_son_zip_rechazados(tmp_path: Path) -> None:
    """Un archivo que no es un ZIP en absoluto se rechaza sin traceback crudo."""
    zip_path = tmp_path / "no_es_zip.bin"
    zip_path.write_bytes(b"esto definitivamente no es un zip valido")

    resultado = BackupValidator().validar_backup(zip_path)

    assert resultado.valid is False
    assert isinstance(resultado.error, BackupValidationError)


def test_zip_truncado_rechazado(tmp_path: Path) -> None:
    """Un ZIP real truncado a la mitad se rechaza de forma segura."""
    profile = build_profile(tmp_path)
    write_financial_file(profile, "cuentas.json")
    settings_service = build_settings_service(profile, tmp_path / "backups")
    creado = ProfileBackupService().crear_backup(
        profile,
        settings_service,
        now=FIXED_NOW,
    )
    original = creado.zip_path.read_bytes()
    truncado = tmp_path / "truncado.zip"
    truncado.write_bytes(original[: len(original) // 2])

    resultado = BackupValidator().validar_backup(truncado)

    assert resultado.valid is False
    assert isinstance(resultado.error, BackupValidationError)


def test_crc_corrupto_detectado_deterministicamente(tmp_path: Path) -> None:
    """Corromper un byte de una entrada STORED produce un fallo de CRC detectable."""
    zip_path = tmp_path / "crc_malo.zip"
    marker = b"CONTENIDO-UNICO-PARA-CORROMPER-0123456789"
    manifest = raw_manifest_dict(
        files=[
            {
                "path": "profile/data/cuentas.json",
                "size": len(marker),
                "sha256": hashlib.sha256(marker).hexdigest(),
                "role": "financial_data",
            },
        ],
    )
    with zipfile.ZipFile(
        zip_path,
        "w",
        compression=zipfile.ZIP_STORED,
    ) as archive:
        archive.writestr("profile/data/cuentas.json", marker)
        archive.writestr(MANIFEST_ENTRY_NAME, json.dumps(manifest))

    raw = bytearray(zip_path.read_bytes())
    offset = raw.find(marker)
    assert offset != -1
    raw[offset] ^= 0xFF
    zip_path.write_bytes(bytes(raw))

    resultado = BackupValidator().validar_backup(zip_path)

    assert resultado.valid is False
    assert isinstance(resultado.error, BackupError)


# ---------------------------------------------------------------------------
# 4-7. Manifest ausente / inválido / duplicado
# ---------------------------------------------------------------------------


def test_manifest_ausente_rechazado(tmp_path: Path) -> None:
    """Un ZIP sin manifest.json se rechaza."""
    zip_path = tmp_path / "sin_manifest.zip"
    with zipfile.ZipFile(zip_path, "w") as archive:
        archive.writestr("profile/data/cuentas.json", "contenido")

    resultado = BackupValidator().validar_backup(zip_path)

    assert resultado.valid is False
    assert isinstance(resultado.error, BackupValidationError)


def test_manifest_json_corrupto_rechazado(tmp_path: Path) -> None:
    """Un manifest.json con JSON sintácticamente inválido se rechaza."""
    zip_path = tmp_path / "manifest_corrupto.zip"
    with zipfile.ZipFile(zip_path, "w") as archive:
        archive.writestr(MANIFEST_ENTRY_NAME, "{ esto no es json valido ")

    resultado = BackupValidator().validar_backup(zip_path)

    assert resultado.valid is False
    assert isinstance(resultado.error, InvalidBackupManifestError)


def test_manifest_vacio_rechazado(tmp_path: Path) -> None:
    """Un manifest.json vacío se rechaza."""
    zip_path = tmp_path / "manifest_vacio.zip"
    with zipfile.ZipFile(zip_path, "w") as archive:
        archive.writestr(MANIFEST_ENTRY_NAME, "")

    resultado = BackupValidator().validar_backup(zip_path)

    assert resultado.valid is False
    assert isinstance(resultado.error, InvalidBackupManifestError)


def test_manifest_no_object_rechazado(tmp_path: Path) -> None:
    """Un manifest.json que no es un objeto JSON (es una lista) se rechaza."""
    zip_path = tmp_path / "manifest_array.zip"
    with zipfile.ZipFile(zip_path, "w") as archive:
        archive.writestr(MANIFEST_ENTRY_NAME, "[1, 2, 3]")

    resultado = BackupValidator().validar_backup(zip_path)

    assert resultado.valid is False
    assert isinstance(resultado.error, InvalidBackupManifestError)


def test_manifest_duplicado_rechazado(tmp_path: Path) -> None:
    """Dos entradas manifest.json físicas en el mismo ZIP se rechazan."""
    zip_path = tmp_path / "manifest_duplicado.zip"
    manifest = raw_manifest_dict()
    with zipfile.ZipFile(zip_path, "w") as archive:
        archive.writestr("profile/data/cuentas.json", "contenido")
        archive.writestr(MANIFEST_ENTRY_NAME, json.dumps(manifest))
        archive.writestr(MANIFEST_ENTRY_NAME, json.dumps(manifest))

    resultado = BackupValidator().validar_backup(zip_path)

    assert resultado.valid is False
    assert isinstance(resultado.error, BackupValidationError)


# ---------------------------------------------------------------------------
# 8-9. Archivo extra / faltante, sobre un backup real válido
# ---------------------------------------------------------------------------


def test_archivo_extra_sobre_backup_valido_real(tmp_path: Path) -> None:
    """Agregar un archivo no declarado a un backup real válido lo invalida."""
    profile = build_profile(tmp_path)
    write_financial_file(profile, "cuentas.json")
    settings_service = build_settings_service(profile, tmp_path / "backups")
    creado = ProfileBackupService().crear_backup(
        profile,
        settings_service,
        now=FIXED_NOW,
    )

    mutado = tmp_path / "mutado_extra.zip"
    with zipfile.ZipFile(creado.zip_path) as origen, zipfile.ZipFile(
        mutado,
        "w",
    ) as destino:
        for name in origen.namelist():
            destino.writestr(name, origen.read(name))
        destino.writestr("profile/data/evil.json", '{"malicioso": true}')
        destino.writestr("notes.txt", "nota irrelevante")

    resultado = BackupValidator().validar_backup(
        mutado,
        expected_profile_id=profile.id,
    )

    assert resultado.valid is False
    assert isinstance(resultado.error, BackupValidationError)

    original_sigue_valido = BackupValidator().validar_backup(
        creado.zip_path,
        expected_profile_id=profile.id,
    )
    assert original_sigue_valido.valid is True


def test_archivo_faltante_sobre_backup_valido_real(tmp_path: Path) -> None:
    """Quitar un archivo declarado de un backup real válido lo invalida."""
    profile = build_profile(tmp_path)
    write_financial_file(profile, "cuentas.json")
    write_financial_file(profile, "deudas.json")
    settings_service = build_settings_service(profile, tmp_path / "backups")
    creado = ProfileBackupService().crear_backup(
        profile,
        settings_service,
        now=FIXED_NOW,
    )

    mutado = tmp_path / "mutado_falta.zip"
    with zipfile.ZipFile(creado.zip_path) as origen, zipfile.ZipFile(
        mutado,
        "w",
    ) as destino:
        for name in origen.namelist():
            if name == "profile/data/deudas.json":
                continue
            destino.writestr(name, origen.read(name))

    resultado = BackupValidator().validar_backup(
        mutado,
        expected_profile_id=profile.id,
    )

    assert resultado.valid is False
    assert isinstance(resultado.error, BackupValidationError)


# ---------------------------------------------------------------------------
# 10-12. Hash / size alterados
# ---------------------------------------------------------------------------


def test_hash_alterado_caso_a_bytes_modificados(tmp_path: Path) -> None:
    """Bytes modificados en el ZIP, manifest intacto: se rechaza por hash."""
    content_real = b"contenido-original-1234"
    content_corrupto = b"contenido-original-5678"
    assert len(content_real) == len(content_corrupto)
    zip_path = tmp_path / "hash_caso_a.zip"
    manifest = raw_manifest_dict(
        files=[
            {
                "path": "profile/data/cuentas.json",
                "size": len(content_real),
                "sha256": hashlib.sha256(content_real).hexdigest(),
                "role": "financial_data",
            },
        ],
    )
    build_zip_from_raw_manifest(
        zip_path,
        manifest,
        file_contents={"profile/data/cuentas.json": content_corrupto},
    )

    resultado = BackupValidator().validar_backup(zip_path)

    assert resultado.valid is False
    assert isinstance(resultado.error, BackupValidationError)


def test_hash_alterado_caso_b_manifest_modificado(tmp_path: Path) -> None:
    """SHA-256 incorrecto en el manifest, bytes intactos: se rechaza por hash."""
    content_real = b"contenido-intacto-en-el-zip"
    zip_path = tmp_path / "hash_caso_b.zip"
    manifest = raw_manifest_dict(
        files=[
            {
                "path": "profile/data/cuentas.json",
                "size": len(content_real),
                "sha256": "f" * 64,
                "role": "financial_data",
            },
        ],
    )
    build_zip_from_raw_manifest(
        zip_path,
        manifest,
        file_contents={"profile/data/cuentas.json": content_real},
    )

    resultado = BackupValidator().validar_backup(zip_path)

    assert resultado.valid is False
    assert isinstance(resultado.error, BackupValidationError)


def test_size_alterado_menor_rechazado(tmp_path: Path) -> None:
    """Un size declarado menor al real se rechaza."""
    content = b"contenido-real-de-prueba"
    zip_path = tmp_path / "size_menor.zip"
    manifest = raw_manifest_dict(
        files=[
            {
                "path": "profile/data/cuentas.json",
                "size": len(content) - 1,
                "sha256": hashlib.sha256(content).hexdigest(),
                "role": "financial_data",
            },
        ],
    )
    build_zip_from_raw_manifest(
        zip_path,
        manifest,
        file_contents={"profile/data/cuentas.json": content},
    )

    resultado = BackupValidator().validar_backup(zip_path)

    assert resultado.valid is False
    assert isinstance(resultado.error, BackupValidationError)


def test_size_alterado_mayor_rechazado(tmp_path: Path) -> None:
    """Un size declarado mayor al real se rechaza."""
    content = b"contenido-real-de-prueba"
    zip_path = tmp_path / "size_mayor.zip"
    manifest = raw_manifest_dict(
        files=[
            {
                "path": "profile/data/cuentas.json",
                "size": len(content) + 1,
                "sha256": hashlib.sha256(content).hexdigest(),
                "role": "financial_data",
            },
        ],
    )
    build_zip_from_raw_manifest(
        zip_path,
        manifest,
        file_contents={"profile/data/cuentas.json": content},
    )

    resultado = BackupValidator().validar_backup(zip_path)

    assert resultado.valid is False
    assert isinstance(resultado.error, BackupValidationError)


# ---------------------------------------------------------------------------
# 13. Paths peligrosos (reutilizando BackupFileEntry / normalize_backup_path)
# ---------------------------------------------------------------------------

DANGEROUS_PATHS = [
    "../archivo",
    "../../archivo",
    "/archivo",
    "C:/archivo",
    "C:\\archivo",
    "C:archivo",
    "\\\\server\\share\\archivo",
    "profile/./archivo",
    "profile/data/file.",
    "profile/data/file ",
    "profile/data/file.txt:stream",
    "CON",
    "NUL.txt",
]


@pytest.mark.parametrize("dangerous_path", DANGEROUS_PATHS)
def test_paths_peligrosos_rechazados(tmp_path: Path, dangerous_path: str) -> None:
    """Cada forma peligrosa de path se rechaza reutilizando BackupFileEntry."""
    zip_path = tmp_path / "peligroso.zip"
    manifest = raw_manifest_dict(
        files=[
            {
                "path": dangerous_path,
                "size": 1,
                "sha256": VALID_HASH,
                "role": "financial_data",
            },
        ],
    )
    build_zip_from_raw_manifest(zip_path, manifest, file_contents={})

    resultado = BackupValidator().validar_backup(zip_path)

    assert resultado.valid is False
    assert isinstance(resultado.error, UnsafeBackupPathError)


# ---------------------------------------------------------------------------
# 14-15. Discrepancia de casing manifest vs ZIP / entradas duplicadas
# ---------------------------------------------------------------------------


def test_path_manifest_vs_zip_con_distinto_casing_rechazado(tmp_path: Path) -> None:
    """Manifest declara minúsculas, ZIP solo tiene la variante en mayúsculas."""
    zip_path = tmp_path / "casing.zip"
    manifest = raw_manifest_dict()
    with zipfile.ZipFile(zip_path, "w") as archive:
        archive.writestr("PROFILE/DATA/CUENTAS.JSON", "contenido")
        archive.writestr(MANIFEST_ENTRY_NAME, json.dumps(manifest))

    resultado = BackupValidator().validar_backup(zip_path)

    assert resultado.valid is False
    assert isinstance(resultado.error, BackupValidationError)


def test_entrada_duplicada_exacta_rechazada(tmp_path: Path) -> None:
    """Dos entradas ZIP físicas con el mismo nombre exacto se rechazan."""
    zip_path = tmp_path / "dup_exacta.zip"
    manifest = raw_manifest_dict()
    with zipfile.ZipFile(zip_path, "w") as archive:
        archive.writestr("profile/data/cuentas.json", "contenido")
        archive.writestr("profile/data/cuentas.json", "contenido")
        archive.writestr(MANIFEST_ENTRY_NAME, json.dumps(manifest))

    resultado = BackupValidator().validar_backup(zip_path)

    assert resultado.valid is False
    assert isinstance(resultado.error, BackupValidationError)


def test_entrada_duplicada_case_insensitive_rechazada(tmp_path: Path) -> None:
    """Dos entradas que solo difieren en mayúsculas/minúsculas se rechazan."""
    zip_path = tmp_path / "dup_case.zip"
    manifest = raw_manifest_dict()
    with zipfile.ZipFile(zip_path, "w") as archive:
        archive.writestr("profile/data/cuentas.json", "contenido")
        archive.writestr("PROFILE/DATA/CUENTAS.JSON", "contenido")
        archive.writestr(MANIFEST_ENTRY_NAME, json.dumps(manifest))

    resultado = BackupValidator().validar_backup(zip_path)

    assert resultado.valid is False
    assert isinstance(resultado.error, BackupValidationError)


# ---------------------------------------------------------------------------
# 16. Entradas de directorio
# ---------------------------------------------------------------------------


def test_entrada_de_directorio_rechazada(tmp_path: Path) -> None:
    """Una entrada ZIP de directorio explícita se rechaza de forma determinista."""
    zip_path = tmp_path / "con_dir.zip"
    manifest = raw_manifest_dict()
    with zipfile.ZipFile(zip_path, "w") as archive:
        archive.writestr("profile/data/cuentas.json", "contenido")
        archive.writestr("profile/data/", "")
        archive.writestr(MANIFEST_ENTRY_NAME, json.dumps(manifest))

    resultado = BackupValidator().validar_backup(zip_path)

    assert resultado.valid is False
    assert isinstance(resultado.error, BackupValidationError)


# ---------------------------------------------------------------------------
# 17-18. Schema version / app / backup_type / profile mismatch / key_policy / role
# ---------------------------------------------------------------------------


def test_schema_version_incompatible_rechazado(tmp_path: Path) -> None:
    """Un schema_version futuro se rechaza sin migrar automáticamente.

    Desde 22G, 1 y 2 son versiones soportadas del manifest; la frontera de
    incompatibilidad real es cualquier valor por encima del techo actual.
    """
    zip_path = tmp_path / "schema_malo.zip"
    build_zip_from_raw_manifest(zip_path, raw_manifest_dict(schema_version=999))

    resultado = BackupValidator().validar_backup(zip_path)

    assert resultado.valid is False
    assert isinstance(resultado.error, UnsupportedBackupVersionError)


def test_app_incorrecta_rechazada(tmp_path: Path) -> None:
    """Un campo app distinto de 'Avalancha V2' se rechaza."""
    zip_path = tmp_path / "app_mala.zip"
    build_zip_from_raw_manifest(zip_path, raw_manifest_dict(app="Otra App"))

    resultado = BackupValidator().validar_backup(zip_path)

    assert resultado.valid is False
    assert isinstance(resultado.error, InvalidBackupManifestError)


def test_backup_type_incorrecto_rechazado(tmp_path: Path) -> None:
    """Un backup_type distinto de 'profile' se rechaza."""
    zip_path = tmp_path / "tipo_malo.zip"
    build_zip_from_raw_manifest(zip_path, raw_manifest_dict(backup_type="global"))

    resultado = BackupValidator().validar_backup(zip_path)

    assert resultado.valid is False
    assert isinstance(resultado.error, InvalidBackupManifestError)


def test_profile_id_mismatch_rechazado(tmp_path: Path) -> None:
    """Un profile_id distinto del esperado se rechaza con error tipado."""
    zip_path = tmp_path / "perfil_malo.zip"
    build_zip_from_raw_manifest(
        zip_path,
        raw_manifest_dict(profile_id="perfil_a"),
    )

    resultado = BackupValidator().validar_backup(
        zip_path,
        expected_profile_id="perfil_b",
    )

    assert resultado.valid is False
    assert isinstance(resultado.error, ProfileMismatchError)


def test_profile_id_sin_expectativa_no_se_rechaza_por_mismatch(
    tmp_path: Path,
) -> None:
    """Sin expected_profile_id, cualquier profile_id coherente es válido."""
    zip_path = tmp_path / "perfil_libre.zip"
    build_zip_from_raw_manifest(
        zip_path,
        raw_manifest_dict(profile_id="cualquier_perfil"),
    )

    resultado = BackupValidator().validar_backup(zip_path)

    assert resultado.valid is True
    assert resultado.profile_id == "cualquier_perfil"


def test_key_policy_invalido_rechazado(tmp_path: Path) -> None:
    """Un key_policy con protección fuera del contrato se rechaza."""
    zip_path = tmp_path / "key_policy_mala.zip"
    manifest = raw_manifest_dict(
        key_policy={
            "includes_reporte_key": True,
            "protection": "rot13",
            "portable_across_windows_users": False,
        },
    )
    build_zip_from_raw_manifest(zip_path, manifest)

    resultado = BackupValidator().validar_backup(zip_path)

    assert resultado.valid is False
    assert isinstance(resultado.error, InvalidBackupManifestError)


def test_role_invalido_rechazado(tmp_path: Path) -> None:
    """Un role fuera de BACKUP_FILE_ROLES se rechaza."""
    zip_path = tmp_path / "role_malo.zip"
    manifest = raw_manifest_dict(
        files=[
            {
                "path": "profile/data/cuentas.json",
                "size": len(b"contenido"),
                "sha256": hashlib.sha256(b"contenido").hexdigest(),
                "role": "rol_inventado",
            },
        ],
    )
    build_zip_from_raw_manifest(
        zip_path,
        manifest,
        file_contents={"profile/data/cuentas.json": b"contenido"},
    )

    resultado = BackupValidator().validar_backup(zip_path)

    assert resultado.valid is False
    assert isinstance(resultado.error, InvalidBackupManifestError)


# ---------------------------------------------------------------------------
# 19-20. Read-only: ZIP, perfil y ausencia de extracción
# ---------------------------------------------------------------------------


def test_validacion_es_completamente_read_only(tmp_path: Path) -> None:
    """Validar un backup no modifica el ZIP, el perfil, ni extrae archivos."""
    profile = build_profile(tmp_path)
    write_financial_file(profile, "cuentas.json")
    profile.key_path.write_bytes(b"clave-sintetica-no-real")
    settings_service = build_settings_service(
        profile,
        tmp_path / "backups",
        persist=True,
    )
    creado = ProfileBackupService().crear_backup(
        profile,
        settings_service,
        now=FIXED_NOW,
    )

    zip_bytes_antes = creado.zip_path.read_bytes()
    zip_mtime_antes = creado.zip_path.stat().st_mtime_ns
    settings_bytes_antes = (profile.config_dir / "settings.json").read_bytes()
    key_bytes_antes = profile.key_path.read_bytes()
    data_files_antes = sorted(p.name for p in profile.data_dir.iterdir())
    backup_dir_listado_antes = sorted(
        p.name for p in creado.zip_path.parent.iterdir()
    )

    resultado = BackupValidator().validar_backup(
        creado.zip_path,
        expected_profile_id=profile.id,
    )

    assert resultado.valid is True
    assert creado.zip_path.read_bytes() == zip_bytes_antes
    assert creado.zip_path.stat().st_mtime_ns == zip_mtime_antes
    assert (profile.config_dir / "settings.json").read_bytes() == (
        settings_bytes_antes
    )
    assert profile.key_path.read_bytes() == key_bytes_antes
    assert sorted(p.name for p in profile.data_dir.iterdir()) == data_files_antes
    assert (
        sorted(p.name for p in creado.zip_path.parent.iterdir())
        == backup_dir_listado_antes
    )


# ---------------------------------------------------------------------------
# 21. Symlink dentro del ZIP (best-effort, vía external_attr)
# ---------------------------------------------------------------------------


def test_entrada_symlink_rechazada(tmp_path: Path) -> None:
    """Una entrada marcada como symlink Unix vía external_attr se rechaza."""
    zip_path = tmp_path / "con_symlink.zip"
    manifest = raw_manifest_dict()
    with zipfile.ZipFile(zip_path, "w") as archive:
        archive.writestr("profile/data/cuentas.json", "contenido")
        link_info = zipfile.ZipInfo("profile/data/enlace")
        link_info.external_attr = 0o120777 << 16
        archive.writestr(link_info, "/etc/passwd")
        archive.writestr(MANIFEST_ENTRY_NAME, json.dumps(manifest))

    resultado = BackupValidator().validar_backup(zip_path)

    assert resultado.valid is False
    assert isinstance(resultado.error, BackupValidationError)


def test_entrada_normal_no_se_marca_falsamente_como_symlink(
    tmp_path: Path,
) -> None:
    """Un backup real (external_attr=0 por defecto) nunca activa el falso positivo."""
    profile = build_profile(tmp_path)
    write_financial_file(profile, "cuentas.json")
    settings_service = build_settings_service(profile, tmp_path / "backups")
    creado = ProfileBackupService().crear_backup(
        profile,
        settings_service,
        now=FIXED_NOW,
    )

    resultado = BackupValidator().validar_backup(
        creado.zip_path,
        expected_profile_id=profile.id,
    )

    assert resultado.valid is True


# ---------------------------------------------------------------------------
# 22. ZIP bomb / límites defensivos mínimos
# ---------------------------------------------------------------------------


def test_limite_de_entradas_rechaza_zip_con_demasiadas_entradas(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Un ZIP con más entradas que el límite configurado se rechaza."""
    monkeypatch.setattr("services.backup_service.MAX_BACKUP_ENTRIES", 3)
    zip_path = tmp_path / "muchas_entradas.zip"
    with zipfile.ZipFile(zip_path, "w") as archive:
        for index in range(5):
            archive.writestr(f"relleno_{index}.txt", "x")

    resultado = BackupValidator().validar_backup(zip_path)

    assert resultado.valid is False
    assert isinstance(resultado.error, BackupValidationError)


def test_limite_de_tamano_individual_rechaza_entrada_declarada_grande(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Una entrada cuyo tamaño declarado excede el límite se rechaza sin leerla."""
    monkeypatch.setattr("services.backup_service.MAX_SINGLE_FILE_SIZE", 10)
    zip_path = tmp_path / "entrada_grande.zip"
    with zipfile.ZipFile(zip_path, "w") as archive:
        archive.writestr(
            "profile/data/cuentas.json",
            "contenido-mas-largo-que-el-limite-configurado",
        )

    resultado = BackupValidator().validar_backup(zip_path)

    assert resultado.valid is False
    assert isinstance(resultado.error, BackupValidationError)


def test_limite_de_tamano_total_rechaza_suma_excesiva(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """La suma de tamaños declarados por encima del límite total se rechaza."""
    monkeypatch.setattr("services.backup_service.MAX_TOTAL_UNCOMPRESSED_SIZE", 20)
    zip_path = tmp_path / "suma_excesiva.zip"
    with zipfile.ZipFile(zip_path, "w") as archive:
        archive.writestr("a.txt", "0123456789")
        archive.writestr("b.txt", "0123456789")
        archive.writestr("c.txt", "0123456789")

    resultado = BackupValidator().validar_backup(zip_path)

    assert resultado.valid is False
    assert isinstance(resultado.error, BackupValidationError)


def test_limites_no_afectan_un_backup_normal(tmp_path: Path) -> None:
    """Con los límites de producción, un backup real normal sigue siendo válido."""
    profile = build_profile(tmp_path)
    write_financial_file(profile, "cuentas.json")
    write_financial_file(profile, "deudas.json")
    settings_service = build_settings_service(profile, tmp_path / "backups")
    creado = ProfileBackupService().crear_backup(
        profile,
        settings_service,
        now=FIXED_NOW,
    )

    resultado = BackupValidator().validar_backup(
        creado.zip_path,
        expected_profile_id=profile.id,
    )

    assert resultado.valid is True


def test_lector_acotado_detiene_descompresion_real_mas_alla_del_limite(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """_leer_acotado corta por bytes REALES descomprimidos, no por el header.

    El header y los bytes reales coinciden aquí a propósito (ambos
    honestamente por encima del límite): esto demuestra que el lector nunca
    consulta `ZipInfo.file_size` dentro de su bucle, por lo que la misma
    protección funcionaría igual si un ZIP adversarial mintiera en ese
    campo declarando un tamaño pequeño.
    """
    monkeypatch.setattr("services.backup_service.MAX_SINGLE_FILE_SIZE", 100)
    zip_path = tmp_path / "bounded_read.zip"
    contenido_real = b"0" * 5000
    with zipfile.ZipFile(
        zip_path,
        "w",
        compression=zipfile.ZIP_DEFLATED,
    ) as archive:
        archive.writestr("grande.bin", contenido_real)

    validator = BackupValidator()
    with zipfile.ZipFile(zip_path, "r") as archive:
        with pytest.raises(BackupValidationError):
            validator._leer_acotado(archive, "grande.bin")
