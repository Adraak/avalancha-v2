"""Restauración segura, compensable con rollback, de un respaldo de perfil."""

from __future__ import annotations

import fnmatch
import hashlib
import json
import os
import shutil
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Literal
from uuid import uuid4

from cryptography.fernet import Fernet, InvalidToken

from avalancha.gestor_reportes import PREFIJO_DPAPI, ProveedorClaveLocal
from core.models.backup import (
    BackupError,
    BackupManifest,
    BackupKeyPolicy,
    CryptoKeyIncompatibleError,
    ProfileMismatchError,
    RestoreApplyError,
    RestorePreparationError,
    RestoreVerificationError,
    UnsafeBackupPathError,
    normalize_backup_path,
)
from core.profile_metadata import PROFILE_METADATA_FILE_NAME, ProfileMetadataPolicy
from core.schema_versioning import SchemaVersionError, SchemaVersionPolicy
from services.backup_manifest_service import BackupManifestService
from services.backup_service import (
    MANIFEST_ENTRY_NAME,
    MAX_SINGLE_FILE_SIZE,
    BackupValidator,
)
from services.profile_metadata_service import ProfileDocumentInventory
from services.profile_service import PerfilAplicacion
from services.settings_service import SettingsService


PROFILE_METADATA_LOGICAL_PATH = f"profile/{PROFILE_METADATA_FILE_NAME}"


_CHUNK_SIZE = 1024 * 1024

RestoreAction = Literal["WRITE", "DELETE"]
RestoreOutcome = Literal["APPLIED", "FAILED_ROLLBACK_OK", "FAILED_ROLLBACK_FAILED"]


@dataclass(frozen=True, slots=True)
class RestorePlanEntry:
    """Describe el efecto planificado sobre un único archivo administrado."""

    logical_path: str
    target: Path
    action: RestoreAction
    existed_before: bool
    previous_sha256: str | None = None
    previous_size: int | None = None
    snapshot_path: Path | None = None
    new_sha256: str | None = None
    new_size: int | None = None


@dataclass(frozen=True, slots=True)
class RestorePlan:
    """Plan tipado de restauración, construido sin efectos sobre el perfil."""

    profile_id: str
    profile_root: Path
    manifest: BackupManifest
    staging_dir: Path
    entries: tuple[RestorePlanEntry, ...]


@dataclass(frozen=True, slots=True)
class RestoreResult:
    """Resultado tipado de aplicar (o revertir) una restauración."""

    outcome: RestoreOutcome
    profile_id: str
    files_written: int
    files_deleted: int
    error: BackupError | None
    staging_dir: Path | None = None
    failed_rollback_paths: tuple[str, ...] = ()


class _Journal:
    """Bitácora write-ahead mínima: INTENT antes del efecto, APPLIED después.

    Un INTENT sin su APPLIED correspondiente se trata como "posiblemente
    aplicado" (ambiguo), nunca como "no ocurrió" — ver lectura en
    `read_applied_indices`.
    """

    def __init__(self, path: Path) -> None:
        """Abre (o crea) el archivo de journal en modo append."""
        self._path = path
        self._handle = path.open("a", encoding="utf-8")

    def intent(self, index: int) -> None:
        """Registra la intención de aplicar una entrada antes del efecto."""
        self._write({"phase": "INTENT", "index": index})

    def applied(self, index: int) -> None:
        """Registra que una entrada se aplicó por completo."""
        self._write({"phase": "APPLIED", "index": index})

    def _write(self, record: dict[str, object]) -> None:
        self._handle.write(json.dumps(record, sort_keys=True) + "\n")
        self._handle.flush()
        try:
            os.fsync(self._handle.fileno())
        except OSError:
            pass

    def close(self) -> None:
        """Cierra el archivo de journal."""
        self._handle.close()

    @staticmethod
    def read_applied_indices(path: Path) -> set[int]:
        """Determina de forma conservadora qué índices requieren revertirse."""
        if not path.exists():
            return set()
        indices: set[int] = set()
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                index = record.get("index")
                if isinstance(index, int) and record.get("phase") in (
                    "INTENT",
                    "APPLIED",
                ):
                    indices.add(index)
        return indices


class ProfileRestoreService:
    """Restaura un respaldo ZIP validado sobre un perfil, con rollback."""

    def __init__(
        self,
        validator: BackupValidator | None = None,
        manifest_service: BackupManifestService | None = None,
    ) -> None:
        """Inicializa el servicio con sus colaboradores de validación."""
        self._manifest_service = manifest_service or BackupManifestService()
        self._validator = validator or BackupValidator(self._manifest_service)

    # ------------------------------------------------------------------
    # API pública
    # ------------------------------------------------------------------

    def restaurar(
        self,
        zip_path: Path,
        profile: PerfilAplicacion,
    ) -> RestoreResult:
        """Conveniencia: prepara y aplica una restauración en un solo paso."""
        plan = self.preparar(zip_path, profile)
        return self.aplicar(plan)

    def preparar(
        self,
        zip_path: Path,
        profile: PerfilAplicacion,
    ) -> RestorePlan:
        """Valida, materializa en staging y construye el plan sin tocar el perfil.

        El ZIP se valida dos veces: una vez al inicio, y una segunda vez
        inmediatamente antes de abrir el archivo para materializarlo en
        staging. Esta segunda pasada reutiliza `BackupValidator.validar_backup`
        completo (límites agregados, duplicados, directorios, symlinks,
        extras/faltantes) para reducir la ventana entre la primera validación
        y el uso real del archivo. Ventana residual documentada: ambas
        llamadas abren el archivo por separado (la API de validación no
        expone un handle reutilizable ni el manifest ya parseado), por lo
        que un reemplazo exactamente entre la segunda validación y la
        apertura de staging —una ventana ya mínima— seguiría siendo
        teóricamente posible; la comparación de hash/size por archivo que ya
        hace el staging sigue actuando como última línea de defensa para esa
        ventana.
        """
        resultado = self._validator.validar_backup(
            zip_path,
            expected_profile_id=profile.id,
        )
        if not resultado.valid:
            assert resultado.error is not None
            raise resultado.error

        profile_root = profile.raiz.resolve()
        staging_dir = (
            profile.raiz.parent
            / f".avalancha_restore_staging_{profile.id}_{uuid4().hex}"
        )
        staging_new = staging_dir / "new"
        staging_rollback = staging_dir / "rollback"
        staging_new.mkdir(parents=True)
        staging_rollback.mkdir(parents=True)

        try:
            resultado_previo_a_staging = self._validator.validar_backup(
                zip_path,
                expected_profile_id=profile.id,
            )
            if not resultado_previo_a_staging.valid:
                assert resultado_previo_a_staging.error is not None
                raise resultado_previo_a_staging.error

            with zipfile.ZipFile(zip_path, "r") as archive:
                manifest_text = self._validator._leer_acotado(
                    archive,
                    MANIFEST_ENTRY_NAME,
                ).decode("utf-8")
                manifest = self._manifest_service.from_json(manifest_text)
                if manifest.profile_id != profile.id:
                    raise ProfileMismatchError(
                        "El respaldo no corresponde al perfil esperado.",
                    )

                self._validar_invariantes_criptograficas(manifest)

                roles = {entry.role for entry in manifest.files}
                tiene_reportes = bool(
                    roles & {"encrypted_report", "report_index"},
                )
                if tiene_reportes and not manifest.key_policy.includes_reporte_key:
                    raise RestorePreparationError(
                        "El respaldo declara reportes cifrados sin"
                        " reporte.key: no puede restaurarse de forma segura.",
                    )

                key_candidate_bytes: bytes | None = None
                for entry in manifest.files:
                    destino_staging = self._ruta_staging(staging_new, entry.path)
                    destino_staging.parent.mkdir(parents=True, exist_ok=True)
                    size, digest = self._copiar_acotado_a_disco(
                        archive,
                        entry.path,
                        destino_staging,
                    )
                    if size != entry.size or digest != entry.sha256:
                        raise RestorePreparationError(
                            f"El contenido de {entry.path} cambió entre la"
                            " validación y la preparación del respaldo.",
                        )
                    if entry.role == "crypto_key":
                        key_candidate_bytes = destino_staging.read_bytes()

            if manifest.key_policy.includes_reporte_key:
                clave = self._validar_clave_candidata(
                    manifest.key_policy,
                    key_candidate_bytes,
                )
                if tiene_reportes:
                    self._validar_reportes_descifrables(
                        manifest,
                        staging_new,
                        clave,
                    )

            self._validar_version_y_metadata(manifest, profile, staging_new)

            entries = self._construir_entries(
                manifest,
                profile,
                profile_root,
                staging_new,
                staging_rollback,
            )
        except BaseException:
            shutil.rmtree(staging_dir, ignore_errors=True)
            raise

        return RestorePlan(
            profile_id=profile.id,
            profile_root=profile_root,
            manifest=manifest,
            staging_dir=staging_dir,
            entries=tuple(entries),
        )

    def aplicar(self, plan: RestorePlan) -> RestoreResult:
        """Aplica un RestorePlan ya preparado, con journal y rollback."""
        journal_path = plan.staging_dir / "journal.jsonl"
        journal = _Journal(journal_path)
        created_dirs: set[Path] = set()
        escritos = 0
        eliminados = 0

        try:
            ordenadas = self._ordenar_entries(plan.entries)
            for index, entry in ordenadas:
                self._verificar_toctou(entry, plan.profile_root)
                if entry.action == "WRITE" and not entry.target.parent.exists():
                    created_dirs.update(
                        self._directorios_faltantes(
                            entry.target.parent,
                            plan.profile_root,
                        ),
                    )
                journal.intent(index)
                self._aplicar_entrada(entry, plan)
                journal.applied(index)
                if entry.action == "WRITE":
                    escritos += 1
                else:
                    eliminados += 1
            journal.close()
            self._verificar_post_aplicacion(plan)
        except BackupError as exc:
            journal.close()
            return self._fallar_con_rollback(
                plan,
                journal_path,
                exc,
                created_dirs,
            )
        except OSError as exc:
            journal.close()
            envuelto = RestoreApplyError(
                f"Fallo de E/S durante la restauración: {exc}",
            )
            return self._fallar_con_rollback(
                plan,
                journal_path,
                envuelto,
                created_dirs,
            )

        self._limpiar_directorios_creados(created_dirs)
        shutil.rmtree(plan.staging_dir, ignore_errors=True)
        return RestoreResult(
            outcome="APPLIED",
            profile_id=plan.profile_id,
            files_written=escritos,
            files_deleted=eliminados,
            error=None,
        )

    @staticmethod
    def _limpiar_directorios_creados(created_dirs: set[Path]) -> None:
        """Elimina, de más profundo a menos, los directorios vacíos creados.

        Usa exclusivamente `rmdir()` (nunca `rmtree`): si un directorio no
        está vacío (por ejemplo, porque contiene el archivo que sí debía
        quedar ahí, o algo externo inesperado), la eliminación falla y se
        ignora sin tocar su contenido.
        """
        for directorio in sorted(
            created_dirs,
            key=lambda path: len(path.parts),
            reverse=True,
        ):
            try:
                directorio.rmdir()
            except OSError:
                pass

    # ------------------------------------------------------------------
    # Preparación: staging, clave candidata, reportes
    # ------------------------------------------------------------------

    @staticmethod
    def _copiar_acotado_a_disco(
        archive: zipfile.ZipFile,
        name: str,
        destino: Path,
    ) -> tuple[int, str]:
        """Copia una entrada del ZIP a disco en streaming, acotado y hasheado."""
        digest = hashlib.sha256()
        size = 0
        with archive.open(name) as origin, destino.open("wb") as target:
            while True:
                chunk = origin.read(_CHUNK_SIZE)
                if not chunk:
                    break
                size += len(chunk)
                if size > MAX_SINGLE_FILE_SIZE:
                    raise RestorePreparationError(
                        f"La entrada {name} excede el tamaño permitido para"
                        " un respaldo.",
                    )
                digest.update(chunk)
                target.write(chunk)
        return size, digest.hexdigest()

    @staticmethod
    def _validar_invariantes_criptograficas(
        manifest: BackupManifest,
    ) -> None:
        """Valida coherencia entre rutas, roles y política criptográfica."""
        key_path = "profile/config/reporte.key"
        index_path = "profile/reportes/index.avridx"
        declared = {entry.path: entry for entry in manifest.files}
        key_entry = declared.get(key_path)

        if manifest.key_policy.includes_reporte_key:
            if key_entry is None:
                raise RestorePreparationError(
                    "La política del respaldo declara reporte.key, pero el"
                    " archivo no está presente en el manifest.",
                )
        elif key_entry is not None:
            raise RestorePreparationError(
                "El manifest contiene reporte.key aunque la política declara"
                " que la clave está ausente.",
            )

        for entry in manifest.files:
            path = entry.path

            if path == key_path:
                if entry.role != "crypto_key":
                    raise RestorePreparationError(
                        "profile/config/reporte.key debe usar el rol crypto_key.",
                    )
                continue

            if path == index_path:
                if entry.role != "report_index":
                    raise RestorePreparationError(
                        "profile/reportes/index.avridx debe usar el rol"
                        " report_index.",
                    )
                if not manifest.key_policy.includes_reporte_key:
                    raise RestorePreparationError(
                        "El índice de reportes no puede restaurarse sin"
                        " reporte.key.",
                    )
                continue

            if path.startswith("profile/reportes/") and path.endswith(".avr"):
                if entry.role != "encrypted_report":
                    raise RestorePreparationError(
                        "Los archivos .avr deben usar el rol encrypted_report.",
                    )
                if not manifest.key_policy.includes_reporte_key:
                    raise RestorePreparationError(
                        "Los reportes cifrados no pueden restaurarse sin"
                        " reporte.key.",
                    )
                continue

            if entry.role in {"crypto_key", "encrypted_report", "report_index"}:
                raise RestorePreparationError(
                    "Un rol criptográfico aparece asociado a una ruta que no"
                    " corresponde a la unidad criptográfica.",
                )

    def _validar_version_y_metadata(
        self,
        manifest: BackupManifest,
        profile: PerfilAplicacion,
        staging_new: Path,
    ) -> None:
        """Valida, antes de tocar el destino, todo lo versionado del respaldo.

        Cubre tres ejes distintos, cada uno con su propia infraestructura ya
        aprobada, sin crear una política paralela:

        - ``schema_version`` del MANIFEST (22G): ya lo valida
          ``BackupManifest.__post_init__`` al construirse (futuro -> error
          antes de llegar aquí).
        - ``schema_version`` de cada archivo financiero/settings (22D): vía
          ``SchemaVersionPolicy``, releyendo la copia en staging, nunca el
          destino.
        - ``schema_version``/``profile_format_version`` de
          ``profile_metadata.json`` (22E), y su coherencia con el
          ``profile_format_version`` declarado por el manifest (22G): vía
          ``ProfileMetadataPolicy``, también sobre la copia en staging.

        Un respaldo v1 histórico no declara ``profile_format_version`` ni
        incluye necesariamente ``profile_metadata.json``: no se le exige
        retroactivamente.
        """
        declared = {entry.path: entry for entry in manifest.files}

        for entry in manifest.files:
            if not self._requiere_preflight_de_schema(entry.path, entry.role):
                continue
            staged_path = self._ruta_staging(staging_new, entry.path)
            try:
                document = json.loads(
                    staged_path.read_bytes().decode("utf-8"),
                )
            except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                raise RestorePreparationError(
                    f"{entry.path} no es JSON legible; no puede"
                    " restaurarse.",
                ) from exc
            try:
                SchemaVersionPolicy().validate(document)
            except SchemaVersionError as exc:
                raise RestorePreparationError(
                    f"{entry.path} declara una versión de esquema"
                    " incompatible; la restauración se rechaza por"
                    " completo antes de modificar el perfil destino.",
                ) from exc

        if manifest.schema_version < 2:
            return

        metadata_entry = declared.get(PROFILE_METADATA_LOGICAL_PATH)
        if metadata_entry is None:
            raise RestorePreparationError(
                "El respaldo declara el formato de manifest actual pero no"
                " incluye profile_metadata.json: no puede restaurarse.",
            )
        if metadata_entry.role != "profile_metadata":
            raise RestorePreparationError(
                f"{PROFILE_METADATA_LOGICAL_PATH} debe usar el rol"
                " profile_metadata.",
            )

        staged_metadata_path = self._ruta_staging(
            staging_new,
            PROFILE_METADATA_LOGICAL_PATH,
        )
        try:
            metadata_document = json.loads(
                staged_metadata_path.read_bytes().decode("utf-8"),
            )
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise RestorePreparationError(
                "profile_metadata.json del respaldo no es JSON legible; no"
                " puede restaurarse.",
            ) from exc

        metadata = ProfileMetadataPolicy().parse(
            metadata_document,
            expected_slug=profile.id,
        )
        if metadata.profile_format_version != manifest.profile_format_version:
            raise RestorePreparationError(
                "El profile_format_version del manifest no coincide con el"
                " de profile_metadata.json: el respaldo es inválido.",
            )

    @staticmethod
    def _requiere_preflight_de_schema(logical_path: str, role: str) -> bool:
        """Indica si un archivo del respaldo debe validar su schema_version.

        Reutiliza exactamente las familias de ``ProfileDocumentInventory``
        (22E): presupuestos, cuentas, deudas, pagos, snapshots, cierres,
        categorías y settings. Deliberadamente fuera: historial_mensual,
        reportes .avr, el índice de reportes y reporte.key.
        """
        name = Path(logical_path).name
        if role == "financial_data":
            return (
                fnmatch.fnmatch(name, ProfileDocumentInventory.BUDGET_FILE_PATTERN)
                or name in ProfileDocumentInventory.DATA_FILE_NAMES
            )
        if role == "settings":
            return name in ProfileDocumentInventory.CONFIG_FILE_NAMES
        return False

    @staticmethod
    def _validar_clave_candidata(
        key_policy: BackupKeyPolicy,
        key_bytes: bytes | None,
    ) -> bytes:
        """Valida, de forma puramente read-only, la clave candidata del backup."""
        if key_bytes is None:
            raise RestorePreparationError(
                "El respaldo declara reporte.key pero no se encontró en"
                " el manifest.",
            )
        if key_policy.protection == "dpapi":
            if not key_bytes.startswith(PREFIJO_DPAPI):
                raise CryptoKeyIncompatibleError(
                    "La clave no tiene el formato DPAPI declarado por el"
                    " respaldo.",
                )
            try:
                return ProveedorClaveLocal._desproteger_con_dpapi(
                    key_bytes[len(PREFIJO_DPAPI):],
                )
            except ValueError as exc:
                raise CryptoKeyIncompatibleError(
                    "La clave protegida con DPAPI no es compatible con el"
                    " usuario actual de Windows.",
                ) from exc
        candidata = key_bytes.strip()
        try:
            Fernet(candidata)
        except (TypeError, ValueError) as exc:
            raise CryptoKeyIncompatibleError(
                "El contenido de reporte.key no representa una clave"
                " Fernet válida.",
            ) from exc
        return candidata

    @staticmethod
    def _validar_reportes_descifrables(
        manifest: BackupManifest,
        staging_new: Path,
        clave: bytes,
    ) -> None:
        """Confirma que los reportes y el índice son descifrables, sin exponerlos."""
        cifrador = Fernet(clave)
        for entry in manifest.files:
            if entry.role not in ("encrypted_report", "report_index"):
                continue
            staged_path = ProfileRestoreService._ruta_staging(
                staging_new,
                entry.path,
            )
            contenido = staged_path.read_bytes()
            try:
                plano = cifrador.decrypt(contenido)
            except InvalidToken as exc:
                raise CryptoKeyIncompatibleError(
                    f"{entry.path} no es descifrable con la clave candidata"
                    " del respaldo.",
                ) from exc
            try:
                datos = json.loads(plano.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise CryptoKeyIncompatibleError(
                    f"{entry.path} tiene contenido inconsistente tras"
                    " descifrarse.",
                ) from exc
            finally:
                plano = b""
            if entry.role == "encrypted_report":
                valido = isinstance(datos, dict) and "secciones" in datos
            else:
                valido = isinstance(datos, dict) and isinstance(
                    datos.get("reportes"),
                    list,
                )
            if not valido:
                raise CryptoKeyIncompatibleError(
                    f"{entry.path} tiene contenido inconsistente tras"
                    " descifrarse.",
                )
            datos = None

    # ------------------------------------------------------------------
    # Descubrimiento del scope administrado actual + construcción del plan
    # ------------------------------------------------------------------

    def _construir_entries(
        self,
        manifest: BackupManifest,
        profile: PerfilAplicacion,
        profile_root: Path,
        staging_new: Path,
        staging_rollback: Path,
    ) -> list[RestorePlanEntry]:
        """Construye las entradas WRITE/DELETE, con snapshot de lo existente."""
        administrados_actuales = self._descubrir_administrados(
            profile,
            profile_root,
        )
        declarados = {entry.path: entry for entry in manifest.files}
        entries: list[RestorePlanEntry] = []

        for logical_path, entry in declarados.items():
            target = self._ruta_destino(profile, logical_path)
            self._verificar_containment(target, profile_root)
            existed_before = target.exists()
            previous_sha256 = previous_size = None
            snapshot_path = None
            if existed_before:
                snapshot_path = self._ruta_staging(
                    staging_rollback,
                    logical_path,
                )
                previous_size, previous_sha256 = self._snapshot_archivo(
                    target,
                    snapshot_path,
                )
            entries.append(
                RestorePlanEntry(
                    logical_path=logical_path,
                    target=target,
                    action="WRITE",
                    existed_before=existed_before,
                    previous_sha256=previous_sha256,
                    previous_size=previous_size,
                    snapshot_path=snapshot_path,
                    new_sha256=entry.sha256,
                    new_size=entry.size,
                ),
            )

        preservar_unidad_criptografica = not manifest.key_policy.includes_reporte_key

        for logical_path, target in administrados_actuales.items():
            if logical_path in declarados:
                continue
            if preservar_unidad_criptografica and self._es_ruta_criptografica(
                logical_path,
            ):
                # Modo A: el backup no incluye reporte.key (y por tanto
                # tampoco reportes, ya bloqueado antes). La unidad
                # criptográfica actual del perfil no participa en esta
                # restauración: no se snapshotea, no se marca para DELETE,
                # no entra en el journal — queda completamente intacta.
                continue
            self._verificar_containment(target, profile_root)
            snapshot_path = self._ruta_staging(staging_rollback, logical_path)
            previous_size, previous_sha256 = self._snapshot_archivo(
                target,
                snapshot_path,
            )
            entries.append(
                RestorePlanEntry(
                    logical_path=logical_path,
                    target=target,
                    action="DELETE",
                    existed_before=True,
                    previous_sha256=previous_sha256,
                    previous_size=previous_size,
                    snapshot_path=snapshot_path,
                ),
            )

        return entries

    def _descubrir_administrados(
        self,
        profile: PerfilAplicacion,
        profile_root: Path,
    ) -> dict[str, Path]:
        """Descubre, con las mismas reglas de 18C, los archivos administrados."""
        found: dict[str, Path] = {}

        data_root = profile.data_dir
        if data_root.is_dir():
            data_root_resolved = data_root.resolve()
            for source in self._iter_files_sorted(data_root_resolved):
                self._verificar_containment(source, profile_root)
                rel = source.relative_to(data_root_resolved).as_posix()
                found[normalize_backup_path(f"profile/data/{rel}")] = source

        settings_path = profile.config_dir / SettingsService.ARCHIVO_CONFIGURACION
        if settings_path.is_file():
            self._verificar_containment(settings_path, profile_root)
            found["profile/config/settings.json"] = settings_path

        key_path = profile.key_path
        if key_path.is_file():
            self._verificar_containment(key_path, profile_root)
            found["profile/config/reporte.key"] = key_path

        reports_root = profile.reports_dir
        if reports_root.is_dir():
            reports_root_resolved = reports_root.resolve()
            for source in self._iter_files_sorted(reports_root_resolved):
                rel = source.relative_to(reports_root_resolved).as_posix()
                if rel != "index.avridx" and source.suffix != ".avr":
                    continue
                self._verificar_containment(source, profile_root)
                found[normalize_backup_path(f"profile/reportes/{rel}")] = source

        return found

    @staticmethod
    def _iter_files_sorted(root: Path) -> list[Path]:
        """Lista archivos de un árbol en orden estable (ver nota de seguridad).

        `followlinks=False` no detecta junctions/reparse points de Windows
        (confirmado empíricamente en la auditoría de 18C): la protección
        real contra escapes viene de `_verificar_containment`, aplicada a
        cada candidato antes de usarlo.
        """
        collected: list[Path] = []
        for dirpath, _dirnames, filenames in os.walk(root, followlinks=False):
            current = Path(dirpath)
            for filename in filenames:
                collected.append(current / filename)
        collected.sort(key=lambda path: path.relative_to(root).as_posix())
        return collected

    @staticmethod
    def _verificar_containment(target: Path, profile_root: Path) -> None:
        """Valida que target y su padre permanezcan dentro de profile_root.

        Repetida inmediatamente antes de cada efecto (ver `_verificar_toctou`)
        para cerrar la ventana entre descubrimiento/plan y aplicación.
        """
        parent_resolved = target.parent.resolve()
        if not parent_resolved.is_relative_to(profile_root):
            raise UnsafeBackupPathError(
                f"La carpeta de {target.name} sale de la carpeta autorizada"
                " del perfil.",
            )
        if target.exists():
            if not target.resolve().is_relative_to(profile_root):
                raise UnsafeBackupPathError(
                    f"{target.name} sale de la carpeta autorizada del"
                    " perfil.",
                )

    @staticmethod
    def _ruta_destino(profile: PerfilAplicacion, logical_path: str) -> Path:
        """Traduce una ruta lógica del manifest a una ruta real del perfil."""
        if logical_path == PROFILE_METADATA_LOGICAL_PATH:
            return profile.raiz / PROFILE_METADATA_FILE_NAME
        if logical_path == "profile/config/settings.json":
            return profile.config_dir / "settings.json"
        if logical_path == "profile/config/reporte.key":
            return profile.key_path
        if logical_path.startswith("profile/data/"):
            rest = logical_path[len("profile/data/"):]
            return profile.data_dir.joinpath(*rest.split("/"))
        if logical_path.startswith("profile/reportes/"):
            rest = logical_path[len("profile/reportes/"):]
            return profile.reports_dir.joinpath(*rest.split("/"))
        raise RestorePreparationError(
            f"La ruta {logical_path} no pertenece al scope administrado.",
        )

    @staticmethod
    def _ruta_staging(staging_root: Path, logical_path: str) -> Path:
        """Traduce una ruta lógica a su ubicación física dentro de staging."""
        return staging_root.joinpath(*logical_path.split("/"))

    @staticmethod
    def _snapshot_archivo(source: Path, destino: Path) -> tuple[int, str]:
        """Copia source a destino en streaming, devolviendo size y sha256."""
        destino.parent.mkdir(parents=True, exist_ok=True)
        digest = hashlib.sha256()
        size = 0
        with source.open("rb") as origin, destino.open("wb") as target:
            for chunk in iter(lambda: origin.read(_CHUNK_SIZE), b""):
                size += len(chunk)
                digest.update(chunk)
                target.write(chunk)
        return size, digest.hexdigest()

    @staticmethod
    def _hash_archivo(path: Path) -> tuple[int, str]:
        """Calcula size y sha256 reales de un archivo existente, sin copiarlo."""
        digest = hashlib.sha256()
        size = 0
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(_CHUNK_SIZE), b""):
                size += len(chunk)
                digest.update(chunk)
        return size, digest.hexdigest()

    @staticmethod
    def _directorios_faltantes(path: Path, raiz: Path) -> list[Path]:
        """Lista, de más profundo a menos, los directorios aún no creados."""
        faltantes: list[Path] = []
        actual = path
        while actual != raiz and not actual.exists():
            faltantes.append(actual)
            actual = actual.parent
        return faltantes

    @staticmethod
    def _es_ruta_criptografica(logical_path: str) -> bool:
        """Indica si una ruta lógica pertenece a la unidad criptográfica."""
        return logical_path == "profile/config/reporte.key" or (
            logical_path.startswith("profile/reportes/")
        )

    # ------------------------------------------------------------------
    # Aplicación: orden, TOCTOU, efectos, permisos
    # ------------------------------------------------------------------

    @staticmethod
    def _ordenar_entries(
        entries: tuple[RestorePlanEntry, ...],
    ) -> list[tuple[int, RestorePlanEntry]]:
        """Ordena: datos/settings primero, unidad criptográfica, deletes al final."""
        datos: list[tuple[int, RestorePlanEntry]] = []
        cripto: list[tuple[int, RestorePlanEntry]] = []
        eliminaciones: list[tuple[int, RestorePlanEntry]] = []
        for index, entry in enumerate(entries):
            if entry.action == "DELETE":
                eliminaciones.append((index, entry))
            elif ProfileRestoreService._es_ruta_criptografica(entry.logical_path):
                cripto.append((index, entry))
            else:
                datos.append((index, entry))
        return datos + cripto + eliminaciones

    def _verificar_toctou(
        self,
        entry: RestorePlanEntry,
        profile_root: Path,
    ) -> None:
        """Revalida containment y ausencia/coherencia justo antes del efecto."""
        self._verificar_containment(entry.target, profile_root)
        if entry.existed_before:
            if not entry.target.exists():
                raise RestoreApplyError(
                    f"{entry.logical_path} desapareció antes de aplicar la"
                    " restauración.",
                )
            size, digest = self._hash_archivo(entry.target)
            if size != entry.previous_size or digest != entry.previous_sha256:
                raise RestoreApplyError(
                    f"{entry.logical_path} cambió antes de aplicar la"
                    " restauración (modificación concurrente detectada).",
                )
        elif entry.target.exists():
            raise RestoreApplyError(
                f"{entry.logical_path} apareció inesperadamente antes de"
                " escribir la restauración.",
            )

    def _aplicar_entrada(self, entry: RestorePlanEntry, plan: RestorePlan) -> None:
        """Ejecuta el efecto real (WRITE o DELETE) de una entrada del plan."""
        if entry.action == "WRITE":
            origen = self._ruta_staging(
                plan.staging_dir / "new",
                entry.logical_path,
            )
            entry.target.parent.mkdir(parents=True, exist_ok=True)
            if entry.existed_before:
                self._quitar_solo_lectura(entry.target)
            os.replace(origen, entry.target)
            if entry.target.suffix == ".avr":
                self._marcar_solo_lectura(entry.target)
        else:
            self._quitar_solo_lectura(entry.target)
            entry.target.unlink()

    @staticmethod
    def _quitar_solo_lectura(path: Path) -> None:
        """Permite escritura sobre un archivo que pudiera estar protegido."""
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass

    @staticmethod
    def _marcar_solo_lectura(path: Path) -> None:
        """Restaura la postura de solo lectura que usa GestorReportes para .avr."""
        try:
            os.chmod(path, 0o400)
        except OSError:
            pass

    # ------------------------------------------------------------------
    # Verificación post-aplicación / post-rollback
    # ------------------------------------------------------------------

    def _verificar_post_aplicacion(self, plan: RestorePlan) -> None:
        """Confirma, releyendo desde disco, que el estado aplicado es correcto."""
        for entry in plan.entries:
            self._verificar_containment(entry.target, plan.profile_root)
            if entry.action == "WRITE":
                if not entry.target.exists():
                    raise RestoreVerificationError(
                        f"{entry.logical_path} no existe tras la"
                        " restauración.",
                    )
                size, digest = self._hash_archivo(entry.target)
                if size != entry.new_size or digest != entry.new_sha256:
                    raise RestoreVerificationError(
                        f"{entry.logical_path} no coincide con el manifest"
                        " tras la restauración.",
                    )
            elif entry.target.exists():
                raise RestoreVerificationError(
                    f"{entry.logical_path} debía eliminarse y sigue"
                    " presente.",
                )

    def _verificar_post_rollback(
        self,
        plan: RestorePlan,
        applied_indices: set[int],
        created_dirs: set[Path],
    ) -> None:
        """Confirma que las entradas revertidas quedaron en su estado previo.

        Solo se verifican las entradas que realmente se intentaron aplicar
        (`applied_indices`): una entrada en la que el TOCTOU abortó antes de
        tocar nada puede legítimamente diferir de su snapshot original (un
        cambio externo que decidimos no sobrescribir), y eso no es una falla
        de rollback — nunca se aplicó ningún efecto sobre ella.

        También confirma que ningún directorio creado por esta restauración
        sobrevive: si uno no pudo eliminarse (por ejemplo, porque algo
        externo depositó un archivo inesperado dentro), el perfil no volvió
        exactamente a su estado previo — eso se reporta como fallo de
        verificación, nunca se vacía ni se borra recursivamente su contenido.
        """
        for index in applied_indices:
            entry = plan.entries[index]
            self._verificar_containment(entry.target, plan.profile_root)
            if entry.existed_before:
                if not entry.target.exists():
                    raise RestoreVerificationError(
                        f"{entry.logical_path} no se recuperó correctamente"
                        " tras el rollback.",
                    )
                size, digest = self._hash_archivo(entry.target)
                if size != entry.previous_size or digest != entry.previous_sha256:
                    raise RestoreVerificationError(
                        f"{entry.logical_path} no coincide con el estado"
                        " previo tras el rollback.",
                    )
            elif entry.target.exists():
                raise RestoreVerificationError(
                    f"{entry.logical_path} no debía existir y el rollback"
                    " no lo eliminó.",
                )
        for directorio in created_dirs:
            if directorio.exists():
                raise RestoreVerificationError(
                    f"El directorio {directorio} fue creado por la"
                    " restauración y no pudo eliminarse tras el rollback.",
                )

    # ------------------------------------------------------------------
    # Rollback
    # ------------------------------------------------------------------

    def _fallar_con_rollback(
        self,
        plan: RestorePlan,
        journal_path: Path,
        error: BackupError,
        created_dirs: set[Path],
    ) -> RestoreResult:
        """Revierte lo aplicado hasta ahora y reporta el resultado tipado."""
        applied_indices = _Journal.read_applied_indices(journal_path)
        ok, failed_paths = self._rollback(plan, applied_indices)
        self._limpiar_directorios_creados(created_dirs)
        if ok:
            try:
                self._verificar_post_rollback(plan, applied_indices, created_dirs)
            except BackupError:
                ok = False

        if ok:
            shutil.rmtree(plan.staging_dir, ignore_errors=True)
            return RestoreResult(
                outcome="FAILED_ROLLBACK_OK",
                profile_id=plan.profile_id,
                files_written=0,
                files_deleted=0,
                error=error,
            )
        return RestoreResult(
            outcome="FAILED_ROLLBACK_FAILED",
            profile_id=plan.profile_id,
            files_written=0,
            files_deleted=0,
            error=error,
            staging_dir=plan.staging_dir,
            failed_rollback_paths=tuple(failed_paths),
        )

    def _rollback(
        self,
        plan: RestorePlan,
        applied_indices: set[int],
    ) -> tuple[bool, list[str]]:
        """Revierte, en orden inverso, toda entrada marcada como aplicada."""
        failed: list[str] = []
        for index in sorted(applied_indices, reverse=True):
            entry = plan.entries[index]
            try:
                self._revertir_entrada(entry)
            except OSError:
                failed.append(entry.logical_path)
        return (not failed, failed)

    def _revertir_entrada(self, entry: RestorePlanEntry) -> None:
        """Deshace exactamente el efecto de una entrada, desde su snapshot."""
        if entry.action == "WRITE":
            if entry.existed_before:
                assert entry.snapshot_path is not None
                entry.target.parent.mkdir(parents=True, exist_ok=True)
                self._quitar_solo_lectura(entry.target)
                os.replace(entry.snapshot_path, entry.target)
                if entry.target.suffix == ".avr":
                    self._marcar_solo_lectura(entry.target)
            elif entry.target.exists():
                self._quitar_solo_lectura(entry.target)
                entry.target.unlink(missing_ok=True)
        else:
            assert entry.snapshot_path is not None
            entry.target.parent.mkdir(parents=True, exist_ok=True)
            os.replace(entry.snapshot_path, entry.target)
            if entry.target.suffix == ".avr":
                self._marcar_solo_lectura(entry.target)
