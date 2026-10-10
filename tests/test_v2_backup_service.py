"""Pruebas de creación real de respaldos ZIP por perfil (Etapa 18C)."""

from __future__ import annotations

import os
import zipfile
from datetime import datetime
from pathlib import Path

import pytest

from core.models.backup import (
    BackupAlreadyExistsError,
    BackupFileEntry,
    BackupKeyPolicy,
    BackupManifest,
    BackupValidationError,
    BackupWriteError,
    UnsafeBackupPathError,
)
from services.backup_manifest_service import BackupManifestService
from services.backup_service import (
    MANIFEST_ENTRY_NAME,
    BackupValidator,
    ProfileBackupService,
)
from services.profile_metadata_service import ProfileMetadataService
from services.profile_service import PerfilAplicacion
from services.settings_service import SettingsService


FIXED_NOW = datetime(2026, 9, 29, 12, 0, 0)
DPAPI_PREFIX = b"AVALANCHA-DPAPI-1\n"


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


def write_financial_file(profile: PerfilAplicacion, name: str, content: str = "{}") -> Path:
    """Escribe un archivo financiero sintético bajo data/ del perfil."""
    path = profile.data_dir / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


class TestCreacionBasica:
    """Cubre escenarios 1-10 de la lista de tests del contrato 18C."""

    def test_backup_minimo_valido(self, tmp_path: Path) -> None:
        """Crea un respaldo con un único archivo financiero."""
        profile = build_profile(tmp_path)
        write_financial_file(profile, "cuentas.json", '{"cuentas": []}')
        settings_service = build_settings_service(profile, tmp_path / "backups")
        service = ProfileBackupService()

        result = service.crear_backup(profile, settings_service, now=FIXED_NOW)

        assert result.zip_path.exists()
        by_path = {entry.path: entry for entry in result.manifest.files}
        assert set(by_path) == {
            "profile/data/cuentas.json",
            "profile/profile_metadata.json",
        }
        assert by_path["profile/data/cuentas.json"].role == "financial_data"
        assert by_path["profile/profile_metadata.json"].role == "profile_metadata"

    def test_varios_archivos_financieros_incluidos(self, tmp_path: Path) -> None:
        """Incluye varios archivos financieros, incluso en subcarpetas."""
        profile = build_profile(tmp_path)
        write_financial_file(profile, "cuentas.json")
        write_financial_file(profile, "deudas.json")
        write_financial_file(profile, "presupuesto_2026-09.json")
        write_financial_file(profile, "backups/cuentas.backup_20260101T000000.json")
        settings_service = build_settings_service(profile, tmp_path / "backups")
        service = ProfileBackupService()

        result = service.crear_backup(profile, settings_service, now=FIXED_NOW)

        paths = {entry.path for entry in result.manifest.files}
        assert paths == {
            "profile/data/cuentas.json",
            "profile/data/deudas.json",
            "profile/data/presupuesto_2026-09.json",
            "profile/data/backups/cuentas.backup_20260101T000000.json",
            "profile/profile_metadata.json",
        }
        financial_entries = [
            entry for entry in result.manifest.files if entry.path != "profile/profile_metadata.json"
        ]
        assert all(entry.role == "financial_data" for entry in financial_entries)

    def test_settings_incluido_cuando_existe(self, tmp_path: Path) -> None:
        """Incluye settings.json con rol settings cuando fue persistido."""
        profile = build_profile(tmp_path)
        write_financial_file(profile, "cuentas.json")
        settings_service = build_settings_service(
            profile,
            tmp_path / "backups",
            persist=True,
        )
        service = ProfileBackupService()

        result = service.crear_backup(profile, settings_service, now=FIXED_NOW)

        settings_entries = [
            entry
            for entry in result.manifest.files
            if entry.path == "profile/config/settings.json"
        ]
        assert len(settings_entries) == 1
        assert settings_entries[0].role == "settings"

    def test_reporte_key_incluido_cuando_existe(self, tmp_path: Path) -> None:
        """Incluye reporte.key con rol crypto_key cuando existe."""
        profile = build_profile(tmp_path)
        write_financial_file(profile, "cuentas.json")
        profile.key_path.write_bytes(b"clave-sintetica-no-real")
        settings_service = build_settings_service(profile, tmp_path / "backups")
        service = ProfileBackupService()

        result = service.crear_backup(profile, settings_service, now=FIXED_NOW)

        key_entries = [
            entry
            for entry in result.manifest.files
            if entry.path == "profile/config/reporte.key"
        ]
        assert len(key_entries) == 1
        assert key_entries[0].role == "crypto_key"
        assert result.manifest.key_policy.includes_reporte_key is True

    def test_reporte_key_ausente(self, tmp_path: Path) -> None:
        """No incluye reporte.key y marca la política como ausente."""
        profile = build_profile(tmp_path)
        write_financial_file(profile, "cuentas.json")
        settings_service = build_settings_service(profile, tmp_path / "backups")
        service = ProfileBackupService()

        result = service.crear_backup(profile, settings_service, now=FIXED_NOW)

        assert all(
            entry.role != "crypto_key" for entry in result.manifest.files
        )
        assert result.manifest.key_policy.includes_reporte_key is False
        assert result.manifest.key_policy.protection == "missing"

    def test_avr_incluidos(self, tmp_path: Path) -> None:
        """Incluye reportes .avr con rol encrypted_report."""
        profile = build_profile(tmp_path)
        write_financial_file(profile, "cuentas.json")
        (profile.reports_dir / "R2026-09.avr").write_bytes(b"contenido-cifrado")
        settings_service = build_settings_service(profile, tmp_path / "backups")
        service = ProfileBackupService()

        result = service.crear_backup(profile, settings_service, now=FIXED_NOW)

        avr_entries = [
            entry
            for entry in result.manifest.files
            if entry.path == "profile/reportes/R2026-09.avr"
        ]
        assert len(avr_entries) == 1
        assert avr_entries[0].role == "encrypted_report"

    def test_index_avridx_incluido(self, tmp_path: Path) -> None:
        """Incluye index.avridx con rol report_index."""
        profile = build_profile(tmp_path)
        write_financial_file(profile, "cuentas.json")
        (profile.reports_dir / "index.avridx").write_bytes(b"indice-cifrado")
        settings_service = build_settings_service(profile, tmp_path / "backups")
        service = ProfileBackupService()

        result = service.crear_backup(profile, settings_service, now=FIXED_NOW)

        index_entries = [
            entry
            for entry in result.manifest.files
            if entry.path == "profile/reportes/index.avridx"
        ]
        assert len(index_entries) == 1
        assert index_entries[0].role == "report_index"

    def test_archivo_fuera_del_perfil_rechazado(self, tmp_path: Path) -> None:
        """Rechaza un symlink de datos que escapa de la raíz del perfil."""
        profile = build_profile(tmp_path)
        write_financial_file(profile, "cuentas.json")
        externo = tmp_path / "externo.json"
        externo.write_text("{}", encoding="utf-8")
        enlace = profile.data_dir / "enlace.json"
        try:
            os.symlink(externo, enlace)
        except OSError:
            pytest.skip("El entorno no permite crear symlinks sin privilegios.")
        settings_service = build_settings_service(profile, tmp_path / "backups")
        service = ProfileBackupService()

        with pytest.raises(UnsafeBackupPathError):
            service.crear_backup(profile, settings_service, now=FIXED_NOW)

    def test_exclusiones_respetadas(self, tmp_path: Path) -> None:
        """No incluye archivos fuera de data/config/reportes del perfil."""
        profile = build_profile(tmp_path)
        write_financial_file(profile, "cuentas.json")
        (profile.raiz / "logs").mkdir()
        (profile.raiz / "logs" / "trace.log").write_text("log", encoding="utf-8")
        (profile.raiz / "__pycache__").mkdir()
        (profile.raiz / "__pycache__" / "modulo.pyc").write_bytes(b"\x00")
        settings_service = build_settings_service(profile, tmp_path / "backups")
        service = ProfileBackupService()

        result = service.crear_backup(profile, settings_service, now=FIXED_NOW)

        assert {entry.path for entry in result.manifest.files} == {
            "profile/data/cuentas.json",
            "profile/profile_metadata.json",
        }
        assert not any("logs" in entry.path for entry in result.manifest.files)
        assert not any(
            "__pycache__" in entry.path for entry in result.manifest.files
        )

    def test_inventario_determinista(self, tmp_path: Path) -> None:
        """El orden y contenido del inventario es estable entre corridas."""
        profile = build_profile(tmp_path)
        write_financial_file(profile, "cuentas.json")
        write_financial_file(profile, "deudas.json")
        write_financial_file(profile, "categorias.json")
        service = ProfileBackupService()

        settings_a = build_settings_service(profile, tmp_path / "backups_a")
        resultado_a = service.crear_backup(profile, settings_a, now=FIXED_NOW)
        settings_b = build_settings_service(profile, tmp_path / "backups_b")
        resultado_b = service.crear_backup(profile, settings_b, now=FIXED_NOW)

        paths_a = [entry.path for entry in resultado_a.manifest.files]
        paths_b = [entry.path for entry in resultado_b.manifest.files]
        assert paths_a == paths_b
        data_paths = [path for path in paths_a if path.startswith("profile/data/")]
        assert data_paths == sorted(data_paths)


class TestManifestYValidacion:
    """Cubre escenarios 11-22 (manifest, hash, size, roles, validación)."""

    def test_manifest_correcto(self, tmp_path: Path) -> None:
        """El manifest publicado cumple el contrato base de 18B."""
        profile = build_profile(tmp_path, profile_id="personal", nombre="Personal")
        write_financial_file(profile, "cuentas.json")
        settings_service = build_settings_service(profile, tmp_path / "backups")
        service = ProfileBackupService()

        result = service.crear_backup(profile, settings_service, now=FIXED_NOW)

        assert result.manifest.schema_version == 2
        assert result.manifest.app == "Avalancha V2"
        assert result.manifest.backup_type == "profile"
        assert result.manifest.profile_id == "personal"
        assert result.manifest.profile_name == "Personal"
        assert result.manifest.created_at == FIXED_NOW.isoformat(timespec="seconds")
        assert result.manifest.app_version
        assert result.manifest.profile_format_version == 1

    def test_sha_y_size_corresponden_a_bytes_reales(self, tmp_path: Path) -> None:
        """El SHA-256 y tamaño del manifest corresponden a los bytes en el ZIP."""
        profile = build_profile(tmp_path)
        write_financial_file(profile, "cuentas.json", '{"cuentas": [1, 2, 3]}')
        settings_service = build_settings_service(profile, tmp_path / "backups")
        service = ProfileBackupService()

        result = service.crear_backup(profile, settings_service, now=FIXED_NOW)

        with zipfile.ZipFile(result.zip_path) as archive:
            for entry in result.manifest.files:
                data = archive.read(entry.path)
                assert len(data) == entry.size
                assert __import__("hashlib").sha256(data).hexdigest() == entry.sha256

    def test_zip_abre_y_entradas_exactas(self, tmp_path: Path) -> None:
        """El ZIP abre y contiene exactamente las entradas del manifest."""
        profile = build_profile(tmp_path)
        write_financial_file(profile, "cuentas.json")
        profile.key_path.write_bytes(b"clave")
        settings_service = build_settings_service(
            profile,
            tmp_path / "backups",
            persist=True,
        )
        service = ProfileBackupService()

        result = service.crear_backup(profile, settings_service, now=FIXED_NOW)

        assert zipfile.is_zipfile(result.zip_path)
        with zipfile.ZipFile(result.zip_path) as archive:
            expected = {entry.path for entry in result.manifest.files}
            expected.add(MANIFEST_ENTRY_NAME)
            assert set(archive.namelist()) == expected

    def test_manifest_parsea_desde_el_zip(self, tmp_path: Path) -> None:
        """manifest.json dentro del ZIP se deserializa correctamente."""
        profile = build_profile(tmp_path)
        write_financial_file(profile, "cuentas.json")
        settings_service = build_settings_service(profile, tmp_path / "backups")
        service = ProfileBackupService()

        result = service.crear_backup(profile, settings_service, now=FIXED_NOW)

        with zipfile.ZipFile(result.zip_path) as archive:
            texto = archive.read(MANIFEST_ENTRY_NAME).decode("utf-8")
        manifest = BackupManifestService().from_json(texto)
        assert manifest.to_dict() == result.manifest.to_dict()

    def test_hash_corrupto_detectado(self, tmp_path: Path) -> None:
        """La validación detecta un hash que no corresponde a los bytes."""
        zip_path = tmp_path / "corrupto.zip"
        manifest = _build_manual_manifest()
        with zipfile.ZipFile(zip_path, "w") as archive:
            archive.writestr("profile/data/cuentas.json", "contenido-modificado")
            archive.writestr(
                MANIFEST_ENTRY_NAME,
                BackupManifestService().to_json(manifest),
            )
        validator = BackupValidator()

        resultado = validator.validar_backup(zip_path, expected_profile_id="personal")

        assert resultado.valid is False
        assert isinstance(resultado.error, BackupValidationError)

    def test_archivo_extra_detectado(self, tmp_path: Path) -> None:
        """La validación detecta un archivo adicional no declarado."""
        zip_path = tmp_path / "con_extra.zip"
        manifest = _build_manual_manifest()
        with zipfile.ZipFile(zip_path, "w") as archive:
            archive.writestr("profile/data/cuentas.json", "contenido")
            archive.writestr("profile/data/extra.json", "{}")
            archive.writestr(
                MANIFEST_ENTRY_NAME,
                BackupManifestService().to_json(manifest),
            )
        validator = BackupValidator()

        resultado = validator.validar_backup(zip_path, expected_profile_id="personal")

        assert resultado.valid is False
        assert isinstance(resultado.error, BackupValidationError)

    def test_archivo_faltante_detectado(self, tmp_path: Path) -> None:
        """La validación detecta que falta un archivo declarado en el manifest."""
        zip_path = tmp_path / "incompleto.zip"
        manifest = _build_manual_manifest()
        with zipfile.ZipFile(zip_path, "w") as archive:
            archive.writestr(
                MANIFEST_ENTRY_NAME,
                BackupManifestService().to_json(manifest),
            )
        validator = BackupValidator()

        resultado = validator.validar_backup(zip_path, expected_profile_id="personal")

        assert resultado.valid is False
        assert isinstance(resultado.error, BackupValidationError)

    def test_zip_corrupto_detectado(self, tmp_path: Path) -> None:
        """La validación detecta que el archivo no es un ZIP válido."""
        zip_path = tmp_path / "no_es_zip.zip"
        zip_path.write_bytes(b"esto no es un zip")
        validator = BackupValidator()

        resultado = validator.validar_backup(zip_path, expected_profile_id="personal")

        assert resultado.valid is False
        assert isinstance(resultado.error, BackupValidationError)


class TestPublicacionYFallos:
    """Cubre escenarios 23-34: overwrite, temporales, fallos y aislamiento."""

    def test_backup_existente_no_sobrescrito(self, tmp_path: Path) -> None:
        """Un segundo respaldo con el mismo nombre falla sin sobrescribir."""
        profile = build_profile(tmp_path)
        write_financial_file(profile, "cuentas.json")
        settings_service = build_settings_service(profile, tmp_path / "backups")
        service = ProfileBackupService()

        primero = service.crear_backup(profile, settings_service, now=FIXED_NOW)
        contenido_original = primero.zip_path.read_bytes()

        with pytest.raises(BackupAlreadyExistsError):
            service.crear_backup(profile, settings_service, now=FIXED_NOW)

        assert primero.zip_path.read_bytes() == contenido_original

    def test_temporal_eliminado_ante_fallo_de_escritura(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Si falla la escritura del ZIP, no queda temporal ni ZIP final."""
        profile = build_profile(tmp_path)
        write_financial_file(profile, "cuentas.json")
        backup_dir = tmp_path / "backups"
        settings_service = build_settings_service(profile, backup_dir)
        service = ProfileBackupService()

        def _falla(*_args: object, **_kwargs: object) -> None:
            raise OSError("fallo simulado de escritura")

        monkeypatch.setattr(service, "_copy_into_zip", _falla)

        with pytest.raises(BackupWriteError):
            service.crear_backup(profile, settings_service, now=FIXED_NOW)

        restantes = list(backup_dir.iterdir()) if backup_dir.exists() else []
        assert restantes == []

    def test_origen_intacto_tras_backup(self, tmp_path: Path) -> None:
        """Los archivos fuente no se modifican durante la creación."""
        profile = build_profile(tmp_path)
        origen = write_financial_file(profile, "cuentas.json", '{"a": 1}')
        contenido_previo = origen.read_bytes()
        settings_service = build_settings_service(profile, tmp_path / "backups")
        service = ProfileBackupService()

        service.crear_backup(profile, settings_service, now=FIXED_NOW)

        assert origen.read_bytes() == contenido_previo

    def test_fallo_de_escritura_no_publica_zip(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Un fallo durante la escritura nunca deja un ZIP final publicado."""
        profile = build_profile(tmp_path)
        write_financial_file(profile, "cuentas.json")
        backup_dir = tmp_path / "backups"
        settings_service = build_settings_service(profile, backup_dir)
        service = ProfileBackupService()

        def _falla(*_args: object, **_kwargs: object) -> None:
            raise OSError("fallo simulado")

        monkeypatch.setattr(service, "_copy_into_zip", _falla)

        with pytest.raises(BackupWriteError):
            service.crear_backup(profile, settings_service, now=FIXED_NOW)

        zips = list(backup_dir.glob("*.zip")) if backup_dir.exists() else []
        assert zips == []

    def test_profile_id_correcto_en_manifest(self, tmp_path: Path) -> None:
        """El profile_id del manifest corresponde al perfil suministrado."""
        profile = build_profile(tmp_path, profile_id="demo_avalancha", nombre="Demo")
        write_financial_file(profile, "cuentas.json")
        settings_service = build_settings_service(profile, tmp_path / "backups")
        service = ProfileBackupService()

        result = service.crear_backup(profile, settings_service, now=FIXED_NOW)

        assert result.manifest.profile_id == "demo_avalancha"

    def test_carpeta_respaldo_configurada_es_utilizada(self, tmp_path: Path) -> None:
        """El ZIP final se publica dentro de la carpeta_respaldo configurada."""
        profile = build_profile(tmp_path)
        write_financial_file(profile, "cuentas.json")
        backup_dir = tmp_path / "mi_carpeta_de_respaldo"
        settings_service = build_settings_service(profile, backup_dir)
        service = ProfileBackupService()

        result = service.crear_backup(profile, settings_service, now=FIXED_NOW)

        assert result.zip_path.parent == backup_dir

    def test_manifest_sin_rutas_absolutas(self, tmp_path: Path) -> None:
        """Ninguna ruta del manifest es absoluta; todas usan prefijo profile/."""
        profile = build_profile(tmp_path)
        write_financial_file(profile, "cuentas.json")
        profile.key_path.write_bytes(b"clave")
        settings_service = build_settings_service(
            profile,
            tmp_path / "backups",
            persist=True,
        )
        service = ProfileBackupService()

        result = service.crear_backup(profile, settings_service, now=FIXED_NOW)

        for entry in result.manifest.files:
            assert not Path(entry.path).is_absolute()
            assert entry.path.startswith("profile/")

    def test_aislamiento_entre_perfiles(self, tmp_path: Path) -> None:
        """El respaldo de un perfil nunca incluye archivos de otro perfil."""
        perfil_a = build_profile(tmp_path, profile_id="personal", nombre="Personal")
        perfil_b = build_profile(tmp_path, profile_id="demo_avalancha", nombre="Demo")
        write_financial_file(perfil_a, "cuentas.json", '{"perfil": "a"}')
        write_financial_file(perfil_b, "cuentas.json", '{"perfil": "b"}')
        write_financial_file(perfil_b, "deudas.json", '{"perfil": "b"}')
        service = ProfileBackupService()

        settings_a = build_settings_service(perfil_a, tmp_path / "backups_a")
        resultado_a = service.crear_backup(perfil_a, settings_a, now=FIXED_NOW)

        assert {entry.path for entry in resultado_a.manifest.files} == {
            "profile/data/cuentas.json",
            "profile/profile_metadata.json",
        }
        assert resultado_a.manifest.profile_id == "personal"
        with zipfile.ZipFile(resultado_a.zip_path) as archive:
            data = archive.read("profile/data/cuentas.json")
        assert data == b'{"perfil": "a"}'

    def test_key_policy_missing_sintetica(self, tmp_path: Path) -> None:
        """La política de clave es 'missing' cuando reporte.key no existe."""
        profile = build_profile(tmp_path)
        write_financial_file(profile, "cuentas.json")
        settings_service = build_settings_service(profile, tmp_path / "backups")
        service = ProfileBackupService()

        result = service.crear_backup(profile, settings_service, now=FIXED_NOW)

        assert result.manifest.key_policy == BackupKeyPolicy(
            includes_reporte_key=False,
            protection="missing",
            portable_across_windows_users=False,
        )

    def test_key_policy_dpapi_sintetica(self, tmp_path: Path) -> None:
        """La política de clave es 'dpapi' al reconocer el prefijo real."""
        profile = build_profile(tmp_path)
        write_financial_file(profile, "cuentas.json")
        profile.key_path.write_bytes(DPAPI_PREFIX + b"contenido-protegido-sintetico")
        settings_service = build_settings_service(profile, tmp_path / "backups")
        service = ProfileBackupService()

        result = service.crear_backup(profile, settings_service, now=FIXED_NOW)

        assert result.manifest.key_policy.protection == "dpapi"
        assert result.manifest.key_policy.portable_across_windows_users is False

    def test_nombre_zip_valido_en_windows(self, tmp_path: Path) -> None:
        """El nombre del ZIP no contiene caracteres inválidos en Windows."""
        profile = build_profile(tmp_path)
        write_financial_file(profile, "cuentas.json")
        settings_service = build_settings_service(profile, tmp_path / "backups")
        service = ProfileBackupService()

        result = service.crear_backup(profile, settings_service, now=FIXED_NOW)

        invalid_chars = set('<>:"/\\|?*')
        assert not invalid_chars.intersection(result.zip_path.name)
        assert result.zip_path.name.startswith("Avalancha_personal_")

    def test_cambio_de_archivo_durante_creacion_detectado(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Detecta y falla de forma segura si un archivo cambia al leerlo."""
        profile = build_profile(tmp_path)
        write_financial_file(profile, "cuentas.json", "contenido-original")
        backup_dir = tmp_path / "backups"
        settings_service = build_settings_service(profile, backup_dir)
        service = ProfileBackupService()

        class _FakeStat:
            """Expone solo los atributos que el servicio realmente lee."""

            def __init__(self, st_size: int, st_mtime_ns: int) -> None:
                self.st_size = st_size
                self.st_mtime_ns = st_mtime_ns

        original_stat = Path.stat
        calls: list[int] = []

        def fake_stat(self: Path, *args: object, **kwargs: object) -> object:
            result = original_stat(self, *args, **kwargs)
            if self.name == "cuentas.json":
                calls.append(1)
                if len(calls) == 2:
                    return _FakeStat(result.st_size + 1, result.st_mtime_ns + 1)
            return result

        monkeypatch.setattr(Path, "stat", fake_stat)

        with pytest.raises(BackupWriteError):
            service.crear_backup(profile, settings_service, now=FIXED_NOW)

        zips = list(backup_dir.glob("*.zip")) if backup_dir.exists() else []
        assert zips == []
        restantes = [
            path
            for path in (backup_dir.iterdir() if backup_dir.exists() else [])
        ]
        assert restantes == []

    def test_carpeta_respaldo_dentro_de_datos_rechazada(
        self,
        tmp_path: Path,
    ) -> None:
        """Rechaza una carpeta_respaldo anidada dentro de data/ del perfil."""
        profile = build_profile(tmp_path)
        write_financial_file(profile, "cuentas.json")
        backup_dir = profile.data_dir / "respaldos_internos"
        settings_service = build_settings_service(profile, backup_dir)
        service = ProfileBackupService()

        with pytest.raises(BackupWriteError):
            service.crear_backup(profile, settings_service, now=FIXED_NOW)


def _build_manual_manifest() -> BackupManifest:
    """Construye un manifest minimo coherente para probar _validar_zip."""
    return BackupManifestService().build_profile_manifest(
        created_at=FIXED_NOW.isoformat(timespec="seconds"),
        profile_id="personal",
        profile_name="Personal",
        key_policy=BackupKeyPolicy(
            includes_reporte_key=False,
            protection="missing",
            portable_across_windows_users=False,
        ),
        files=[
            BackupFileEntry(
                path="profile/data/cuentas.json",
                size=len("contenido"),
                sha256=__import__("hashlib").sha256(b"contenido").hexdigest(),
                role="financial_data",
            ),
        ],
        app_version="0.1.0",
        profile_format_version=1,
    )
