"""Servicio de creación real de respaldos ZIP por perfil."""

from __future__ import annotations

import hashlib
import os
import re
import tempfile
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from core.models.backup import (
    BackupAlreadyExistsError,
    BackupFileEntry,
    BackupKeyPolicy,
    BackupManifest,
    BackupValidationError,
    BackupWriteError,
    UnsafeBackupPathError,
    normalize_backup_path,
)
from services.backup_manifest_service import BackupManifestService
from services.profile_service import PerfilAplicacion
from services.settings_service import SettingsService


MANIFEST_ENTRY_NAME = "manifest.json"
_DPAPI_PREFIX = b"AVALANCHA-DPAPI-1\n"
_CHUNK_SIZE = 1024 * 1024
_SAFE_NAME_PATTERN = re.compile(r"[^A-Za-z0-9_-]+")


@dataclass(frozen=True, slots=True)
class BackupCreationResult:
    """Describe el resultado de crear un respaldo ZIP de un perfil."""

    zip_path: Path
    manifest: BackupManifest


class ProfileBackupService:
    """Crea respaldos ZIP reales, verificados, de un perfil financiero."""

    def __init__(
        self,
        manifest_service: BackupManifestService | None = None,
    ) -> None:
        """Inicializa el servicio con su colaborador de manifest."""
        self._manifest_service = manifest_service or BackupManifestService()

    def crear_backup(
        self,
        profile: PerfilAplicacion,
        settings_service: SettingsService,
        *,
        now: datetime | None = None,
    ) -> BackupCreationResult:
        """Crea, valida y publica un respaldo ZIP del perfil suministrado."""
        moment = now or datetime.now()
        backup_dir = self._resolver_carpeta_respaldo(profile, settings_service)
        final_path = backup_dir / self._nombre_zip(profile.id, moment)
        if final_path.exists():
            raise BackupAlreadyExistsError(
                f"Ya existe un respaldo publicado en {final_path}.",
            )

        inventory = self._inventariar(profile)
        created_at = moment.isoformat(timespec="seconds")
        key_policy = self._clasificar_clave(profile)

        try:
            backup_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise BackupWriteError(
                "No fue posible preparar la carpeta de respaldo.",
            ) from exc

        try:
            descriptor, tmp_name = tempfile.mkstemp(
                prefix=".tmp_avalancha_backup_",
                suffix=".zip",
                dir=backup_dir,
            )
            os.close(descriptor)
        except OSError as exc:
            raise BackupWriteError(
                "No fue posible crear el archivo temporal de respaldo.",
            ) from exc
        tmp_path = Path(tmp_name)

        try:
            manifest = self._escribir_zip(
                tmp_path,
                inventory,
                created_at=created_at,
                profile=profile,
                key_policy=key_policy,
            )
            self._validar_zip(tmp_path, manifest, profile.id)
            if final_path.exists():
                raise BackupAlreadyExistsError(
                    f"Ya existe un respaldo publicado en {final_path}.",
                )
            try:
                os.rename(tmp_path, final_path)
            except FileExistsError as exc:
                raise BackupAlreadyExistsError(
                    f"Ya existe un respaldo publicado en {final_path}.",
                ) from exc
        except BaseException:
            tmp_path.unlink(missing_ok=True)
            raise

        return BackupCreationResult(zip_path=final_path, manifest=manifest)

    def _resolver_carpeta_respaldo(
        self,
        profile: PerfilAplicacion,
        settings_service: SettingsService,
    ) -> Path:
        """Resuelve la carpeta de respaldo configurada para el perfil."""
        configuracion = settings_service.cargar_configuracion()
        backup_dir = configuracion.carpeta_respaldo
        if backup_dir is None or not str(backup_dir).strip():
            raise BackupWriteError(
                "La carpeta de respaldo configurada no es válida.",
            )
        if backup_dir.exists() and not backup_dir.is_dir():
            raise BackupWriteError(
                "La carpeta de respaldo configurada no es un directorio.",
            )
        candidate = backup_dir.resolve()
        data_root = profile.data_dir.resolve()
        reports_root = profile.reports_dir.resolve()
        if candidate.is_relative_to(data_root) or candidate.is_relative_to(
            reports_root,
        ):
            raise BackupWriteError(
                "La carpeta de respaldo no puede estar dentro de los datos"
                " del perfil.",
            )
        return backup_dir

    def _inventariar(
        self,
        profile: PerfilAplicacion,
    ) -> list[tuple[str, Path, str]]:
        """Descubre de forma determinista los archivos permitidos del perfil."""
        profile_root = profile.raiz.resolve()
        inventory: list[tuple[str, Path, str]] = []

        data_root = profile.data_dir
        if data_root.is_dir():
            data_root_resolved = data_root.resolve()
            for source in self._iter_files_sorted(data_root_resolved):
                self._verificar_dentro_de_raiz(source, profile_root)
                rel = source.relative_to(data_root_resolved).as_posix()
                inventory.append(
                    (
                        normalize_backup_path(f"profile/data/{rel}"),
                        source,
                        "financial_data",
                    ),
                )

        settings_path = profile.config_dir / SettingsService.ARCHIVO_CONFIGURACION
        if settings_path.is_file():
            self._verificar_dentro_de_raiz(settings_path.resolve(), profile_root)
            inventory.append(
                (
                    normalize_backup_path("profile/config/settings.json"),
                    settings_path,
                    "settings",
                ),
            )

        key_path = profile.key_path
        if key_path.is_file():
            self._verificar_dentro_de_raiz(key_path.resolve(), profile_root)
            inventory.append(
                (
                    normalize_backup_path("profile/config/reporte.key"),
                    key_path,
                    "crypto_key",
                ),
            )

        reports_root = profile.reports_dir
        if reports_root.is_dir():
            reports_root_resolved = reports_root.resolve()
            for source in self._iter_files_sorted(reports_root_resolved):
                rel = source.relative_to(reports_root_resolved).as_posix()
                if rel == "index.avridx":
                    role = "report_index"
                elif source.suffix == ".avr":
                    role = "encrypted_report"
                else:
                    continue
                self._verificar_dentro_de_raiz(source, profile_root)
                inventory.append(
                    (
                        normalize_backup_path(f"profile/reportes/{rel}"),
                        source,
                        role,
                    ),
                )

        if not inventory:
            raise BackupValidationError(
                "El perfil no tiene archivos para respaldar.",
            )
        return inventory

    @staticmethod
    def _iter_files_sorted(root: Path) -> list[Path]:
        """Lista archivos de un árbol sin seguir symlinks, en orden estable."""
        collected: list[Path] = []
        for dirpath, _dirnames, filenames in os.walk(root, followlinks=False):
            current = Path(dirpath)
            for filename in filenames:
                collected.append(current / filename)
        collected.sort(key=lambda path: path.relative_to(root).as_posix())
        return collected

    @staticmethod
    def _verificar_dentro_de_raiz(source: Path, root: Path) -> None:
        """Rechaza archivos cuyo destino real escape de la raíz del perfil."""
        resolved = source.resolve()
        if not resolved.is_relative_to(root):
            raise UnsafeBackupPathError(
                "Un archivo del perfil sale de la carpeta autorizada del"
                " perfil.",
            )

    @staticmethod
    def _clasificar_clave(profile: PerfilAplicacion) -> BackupKeyPolicy:
        """Clasifica reporte.key por formato, sin descifrar ni usar DPAPI."""
        key_path = profile.key_path
        if not key_path.is_file():
            return BackupKeyPolicy(
                includes_reporte_key=False,
                protection="missing",
                portable_across_windows_users=False,
            )
        with key_path.open("rb") as handle:
            header = handle.read(len(_DPAPI_PREFIX))
        if header == _DPAPI_PREFIX:
            return BackupKeyPolicy(
                includes_reporte_key=True,
                protection="dpapi",
                portable_across_windows_users=False,
            )
        return BackupKeyPolicy(
            includes_reporte_key=True,
            protection="plain",
            portable_across_windows_users=True,
        )

    @staticmethod
    def _nombre_zip(profile_id: str, moment: datetime) -> str:
        """Genera un nombre de archivo ZIP legible y seguro en Windows."""
        timestamp = moment.strftime("%Y%m%dT%H%M%S")
        safe_profile = _SAFE_NAME_PATTERN.sub("_", profile_id).strip("_")
        return f"Avalancha_{safe_profile or 'perfil'}_{timestamp}.zip"

    def _escribir_zip(
        self,
        tmp_path: Path,
        inventory: list[tuple[str, Path, str]],
        *,
        created_at: str,
        profile: PerfilAplicacion,
        key_policy: BackupKeyPolicy,
    ) -> BackupManifest:
        """Escribe el ZIP temporal calculando hashes desde los bytes reales."""
        file_entries: list[BackupFileEntry] = []
        try:
            with zipfile.ZipFile(
                tmp_path,
                "w",
                compression=zipfile.ZIP_DEFLATED,
            ) as archive:
                for logical_path, source, role in inventory:
                    size, digest = self._copy_into_zip(
                        archive,
                        source,
                        logical_path,
                    )
                    file_entries.append(
                        BackupFileEntry(
                            path=logical_path,
                            size=size,
                            sha256=digest,
                            role=role,
                        ),
                    )
                manifest = self._manifest_service.build_profile_manifest(
                    created_at=created_at,
                    profile_id=profile.id,
                    profile_name=profile.nombre,
                    key_policy=key_policy,
                    files=file_entries,
                )
                archive.writestr(
                    MANIFEST_ENTRY_NAME,
                    self._manifest_service.to_json(manifest),
                )
        except OSError as exc:
            raise BackupWriteError(
                "No fue posible escribir el respaldo ZIP.",
            ) from exc
        return manifest

    @staticmethod
    def _copy_into_zip(
        archive: zipfile.ZipFile,
        source: Path,
        logical_path: str,
    ) -> tuple[int, str]:
        """Copia un archivo real al ZIP calculando tamaño y hash en streaming."""
        stat_before = source.stat()
        digest = hashlib.sha256()
        size = 0
        with source.open("rb") as origin, archive.open(logical_path, "w") as target:
            for chunk in iter(lambda: origin.read(_CHUNK_SIZE), b""):
                digest.update(chunk)
                size += len(chunk)
                target.write(chunk)
        stat_after = source.stat()
        if (
            stat_before.st_size != stat_after.st_size
            or stat_before.st_mtime_ns != stat_after.st_mtime_ns
        ):
            raise BackupWriteError(
                f"El archivo {source} cambió durante la creación del"
                " respaldo.",
            )
        return size, digest.hexdigest()

    def _validar_zip(
        self,
        zip_path: Path,
        manifest: BackupManifest,
        profile_id: str,
    ) -> None:
        """Reabre y valida íntegramente el ZIP antes de publicarlo."""
        try:
            with zipfile.ZipFile(zip_path, "r") as archive:
                bad_file = archive.testzip()
                if bad_file is not None:
                    raise BackupValidationError(
                        f"El respaldo ZIP está corrupto en {bad_file}.",
                    )
                names = archive.namelist()
                if MANIFEST_ENTRY_NAME not in names:
                    raise BackupValidationError(
                        "El respaldo no contiene manifest.json.",
                    )
                manifest_bytes = archive.read(MANIFEST_ENTRY_NAME)
                try:
                    manifest_text = manifest_bytes.decode("utf-8")
                except UnicodeDecodeError as exc:
                    raise BackupValidationError(
                        "El manifest.json del respaldo no es texto válido.",
                    ) from exc
                persisted = self._manifest_service.from_json(manifest_text)
                if persisted.to_dict() != manifest.to_dict():
                    raise BackupValidationError(
                        "El manifest publicado no coincide con el manifest"
                        " generado.",
                    )
                if persisted.profile_id != profile_id:
                    raise BackupValidationError(
                        "El respaldo no corresponde al perfil solicitado.",
                    )
                expected_names = {entry.path for entry in persisted.files}
                expected_names.add(MANIFEST_ENTRY_NAME)
                if set(names) != expected_names:
                    raise BackupValidationError(
                        "El contenido del respaldo no coincide con el"
                        " manifest.",
                    )
                for entry in persisted.files:
                    data = archive.read(entry.path)
                    if len(data) != entry.size:
                        raise BackupValidationError(
                            f"El tamaño de {entry.path} no coincide con el"
                            " manifest.",
                        )
                    digest = hashlib.sha256(data).hexdigest()
                    if digest != entry.sha256:
                        raise BackupValidationError(
                            f"El hash de {entry.path} no coincide con el"
                            " manifest.",
                        )
        except zipfile.BadZipFile as exc:
            raise BackupValidationError("El respaldo ZIP está corrupto.") from exc
