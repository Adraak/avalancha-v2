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

from avalancha import __version__ as AVALANCHA_VERSION
from core.models.backup import (
    BackupAlreadyExistsError,
    BackupError,
    BackupFileEntry,
    BackupKeyPolicy,
    BackupManifest,
    BackupValidationError,
    BackupWriteError,
    ProfileMismatchError,
    UnsafeBackupPathError,
    normalize_backup_path,
)
from core.profile_metadata import PROFILE_METADATA_FILE_NAME
from services.backup_manifest_service import BackupManifestService
from services.profile_metadata_service import ProfileMetadataService
from services.profile_service import PerfilAplicacion
from services.settings_service import SettingsService


MANIFEST_ENTRY_NAME = "manifest.json"
_DPAPI_PREFIX = b"AVALANCHA-DPAPI-1\n"
_CHUNK_SIZE = 1024 * 1024
_SAFE_NAME_PATTERN = re.compile(r"[^A-Za-z0-9_-]+")

# Límites defensivos mínimos contra ZIPs adversariales (zip-bomb). Calibrados
# con amplio margen para los backups reales de Avalancha (JSON financiero y
# reportes cifrados, del orden de KB-MB), nunca para restringir backups
# legítimos.
MAX_BACKUP_ENTRIES = 5000
MAX_SINGLE_FILE_SIZE = 200 * 1024 * 1024
MAX_TOTAL_UNCOMPRESSED_SIZE = 500 * 1024 * 1024

# Máscara/valor de S_IFLNK para detectar, de forma best-effort, entradas ZIP
# marcadas como symlink Unix vía ZipInfo.external_attr (bits altos = st_mode).
_UNIX_MODE_MASK = 0o170000
_UNIX_SYMLINK_MODE = 0o120000


@dataclass(frozen=True, slots=True)
class BackupCreationResult:
    """Describe el resultado de crear un respaldo ZIP de un perfil."""

    zip_path: Path
    manifest: BackupManifest


@dataclass(frozen=True, slots=True)
class BackupValidationResult:
    """Resultado tipado y de solo lectura de validar un respaldo existente."""

    valid: bool
    zip_path: Path
    profile_id: str | None = None
    file_count: int | None = None
    schema_version: int | None = None
    error: BackupError | None = None


class BackupValidator:
    """Valida, sin efectos secundarios, un respaldo ZIP ya existente.

    No extrae, no restaura ni modifica el ZIP ni el perfil: solo lee y
    verifica. Es la única implementación de validación; ProfileBackupService
    la reutiliza para su propia verificación post-creación en vez de
    duplicar la lógica.
    """

    def __init__(
        self,
        manifest_service: BackupManifestService | None = None,
    ) -> None:
        """Inicializa el validador con su colaborador de manifest."""
        self._manifest_service = manifest_service or BackupManifestService()

    def validar_backup(
        self,
        zip_path: Path,
        *,
        expected_profile_id: str | None = None,
    ) -> BackupValidationResult:
        """Valida de forma íntegra y read-only un respaldo ZIP existente."""
        try:
            manifest = self._validar_desde_cero(
                zip_path,
                expected_profile_id=expected_profile_id,
            )
        except BackupError as exc:
            return BackupValidationResult(
                valid=False,
                zip_path=zip_path,
                error=exc,
            )
        return BackupValidationResult(
            valid=True,
            zip_path=zip_path,
            profile_id=manifest.profile_id,
            file_count=len(manifest.files),
            schema_version=manifest.schema_version,
        )

    def _validar_desde_cero(
        self,
        zip_path: Path,
        *,
        expected_profile_id: str | None,
    ) -> BackupManifest:
        """Reconstruye y verifica el manifest únicamente desde bytes del ZIP.

        Todo chequeo de metadatos (conteo de entradas, tamaños declarados,
        duplicados, directorios, symlinks) ocurre antes de descomprimir nada,
        para no darle a un ZIP adversarial la oportunidad de agotar memoria
        antes de ser rechazado.
        """
        try:
            with zipfile.ZipFile(zip_path, "r") as archive:
                infolist = archive.infolist()
                if len(infolist) > MAX_BACKUP_ENTRIES:
                    raise BackupValidationError(
                        "El respaldo tiene más entradas de las permitidas.",
                    )

                total_declared_size = 0
                for info in infolist:
                    if info.file_size > MAX_SINGLE_FILE_SIZE:
                        raise BackupValidationError(
                            f"La entrada {info.filename} excede el tamaño"
                            " permitido para un respaldo.",
                        )
                    total_declared_size += info.file_size
                if total_declared_size > MAX_TOTAL_UNCOMPRESSED_SIZE:
                    raise BackupValidationError(
                        "El respaldo excede el tamaño total descomprimido"
                        " permitido.",
                    )

                names = archive.namelist()
                if len(names) != len(set(names)):
                    raise BackupValidationError(
                        "El respaldo contiene entradas ZIP duplicadas.",
                    )
                if any(name.endswith("/") for name in names):
                    raise BackupValidationError(
                        "El respaldo contiene entradas de directorio no"
                        " permitidas.",
                    )
                for info in infolist:
                    if self._es_entrada_symlink(info):
                        raise BackupValidationError(
                            "El respaldo contiene un enlace simbólico no"
                            " permitido.",
                        )

                if MANIFEST_ENTRY_NAME not in names:
                    raise BackupValidationError(
                        "El respaldo no contiene manifest.json.",
                    )
                manifest_bytes = self._leer_acotado(
                    archive,
                    MANIFEST_ENTRY_NAME,
                )
                try:
                    manifest_text = manifest_bytes.decode("utf-8")
                except UnicodeDecodeError as exc:
                    raise BackupValidationError(
                        "El manifest.json del respaldo no es texto válido.",
                    ) from exc
                persisted = self._manifest_service.from_json(manifest_text)

                if (
                    expected_profile_id is not None
                    and persisted.profile_id != expected_profile_id
                ):
                    raise ProfileMismatchError(
                        "El respaldo no corresponde al perfil esperado.",
                    )

                expected_names = {entry.path for entry in persisted.files}
                expected_names.add(MANIFEST_ENTRY_NAME)
                if set(names) != expected_names:
                    raise BackupValidationError(
                        "El contenido del respaldo no coincide con el"
                        " manifest.",
                    )

                for entry in persisted.files:
                    info = archive.getinfo(entry.path)
                    if info.file_size != entry.size:
                        raise BackupValidationError(
                            f"El tamaño de {entry.path} no coincide con el"
                            " manifest.",
                        )
                    data = self._leer_acotado(archive, entry.path)
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
        return persisted

    @staticmethod
    def _leer_acotado(archive: zipfile.ZipFile, name: str) -> bytes:
        """Lee una entrada descomprimiendo en streaming con tope real.

        A diferencia de comparar contra el tamaño declarado en la cabecera
        (que un ZIP adversarial puede falsear), este tope se aplica sobre los
        bytes efectivamente producidos por la descompresión, deteniéndola en
        cuanto se supera el límite.
        """
        chunks: list[bytes] = []
        total = 0
        with archive.open(name) as handle:
            while True:
                chunk = handle.read(_CHUNK_SIZE)
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_SINGLE_FILE_SIZE:
                    raise BackupValidationError(
                        f"La entrada {name} excede el tamaño descomprimido"
                        " permitido para un respaldo.",
                    )
                chunks.append(chunk)
        return b"".join(chunks)

    @staticmethod
    def _es_entrada_symlink(info: zipfile.ZipInfo) -> bool:
        """Detecta, de forma best-effort, entradas marcadas como symlink Unix."""
        unix_mode = info.external_attr >> 16
        return (unix_mode & _UNIX_MODE_MASK) == _UNIX_SYMLINK_MODE


class ProfileBackupService:
    """Crea respaldos ZIP reales, verificados, de un perfil financiero."""

    def __init__(
        self,
        manifest_service: BackupManifestService | None = None,
        metadata_service: ProfileMetadataService | None = None,
    ) -> None:
        """Inicializa el servicio con sus colaboradores de manifest y metadata."""
        self._manifest_service = manifest_service or BackupManifestService()
        self._validator = BackupValidator(self._manifest_service)
        self._metadata_service = metadata_service or ProfileMetadataService()

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

        metadata = self._metadata_service.validate_existing(profile)
        if metadata is None:
            raise BackupValidationError(
                "El perfil no tiene metadata; no puede respaldarse con el"
                " contrato de respaldo actual.",
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
                profile_format_version=metadata.profile_format_version,
            )
            resultado = self._validator.validar_backup(
                tmp_path,
                expected_profile_id=profile.id,
            )
            if not resultado.valid:
                raise resultado.error
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

        metadata_path = profile.raiz / PROFILE_METADATA_FILE_NAME
        if metadata_path.is_file():
            self._verificar_dentro_de_raiz(metadata_path.resolve(), profile_root)
            inventory.append(
                (
                    normalize_backup_path("profile/profile_metadata.json"),
                    metadata_path,
                    "profile_metadata",
                ),
            )

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
        profile_format_version: int,
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
                    app_version=AVALANCHA_VERSION,
                    profile_format_version=profile_format_version,
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
