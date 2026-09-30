"""Modelos puros para el contrato de respaldos por perfil."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import PurePosixPath
from typing import Any


APP_NAME = "Avalancha V2"
BACKUP_TYPE_PROFILE = "profile"
SCHEMA_VERSION = 1
BACKUP_FILE_ROLES = frozenset(
    {
        "financial_data",
        "settings",
        "crypto_key",
        "encrypted_report",
        "report_index",
    },
)
KEY_PROTECTIONS = frozenset({"dpapi", "plain", "missing"})
SHA256_PATTERN = re.compile(r"^[0-9a-fA-F]{64}$")
WINDOWS_DRIVE_PATTERN = re.compile(r"^[a-zA-Z]:[\\/]")
WINDOWS_DRIVE_RELATIVE_PATTERN = re.compile(r"^[a-zA-Z]:")
WINDOWS_RESERVED_NAMES = frozenset(
    {"CON", "PRN", "AUX", "NUL"}
    | {f"COM{index}" for index in range(1, 10)}
    | {f"LPT{index}" for index in range(1, 10)}
)


class BackupError(ValueError):
    """Error base del contrato de respaldos."""


class InvalidBackupManifestError(BackupError):
    """Indica que el manifest no cumple el contrato estructural."""


class UnsupportedBackupVersionError(InvalidBackupManifestError):
    """Indica que la version de schema no esta soportada."""


class UnsafeBackupPathError(InvalidBackupManifestError):
    """Indica que una ruta del respaldo no es relativa y segura."""


@dataclass(frozen=True, slots=True)
class BackupFileEntry:
    """Describe un archivo incluido en un respaldo por perfil."""

    path: str
    size: int
    sha256: str
    role: str

    def __post_init__(self) -> None:
        """Valida y normaliza la entrada del archivo."""
        object.__setattr__(self, "path", normalize_backup_path(self.path))
        if (
            not isinstance(self.size, int)
            or isinstance(self.size, bool)
            or self.size < 0
        ):
            raise InvalidBackupManifestError(
                "El tamaño del archivo de respaldo no es valido.",
            )
        if not isinstance(self.sha256, str) or not SHA256_PATTERN.fullmatch(
            self.sha256,
        ):
            raise InvalidBackupManifestError(
                "El hash SHA-256 del archivo de respaldo no es valido.",
            )
        if self.role not in BACKUP_FILE_ROLES:
            raise InvalidBackupManifestError(
                "El rol del archivo de respaldo no esta soportado.",
            )
        object.__setattr__(self, "sha256", self.sha256.lower())

    @property
    def logical_key(self) -> str:
        """Devuelve una clave de comparacion compatible con Windows."""
        return self.path.casefold()

    def to_dict(self) -> dict[str, Any]:
        """Convierte la entrada a datos serializables."""
        return {
            "path": self.path,
            "size": self.size,
            "sha256": self.sha256,
            "role": self.role,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "BackupFileEntry":
        """Construye una entrada desde datos crudos del manifest."""
        if not isinstance(data, dict):
            raise InvalidBackupManifestError(
                "La entrada de archivo del manifest no es valida.",
            )
        return cls(
            path=_required_str(data, "path", "La ruta del archivo no es valida."),
            size=data.get("size"),  # type: ignore[arg-type]
            sha256=_required_str(
                data,
                "sha256",
                "El hash SHA-256 del archivo no es valido.",
            ),
            role=_required_str(data, "role", "El rol del archivo no es valido."),
        )


@dataclass(frozen=True, slots=True)
class BackupKeyPolicy:
    """Describe la portabilidad esperada de reporte.key."""

    includes_reporte_key: bool
    protection: str
    portable_across_windows_users: bool

    def __post_init__(self) -> None:
        """Valida los valores cerrados de la politica de clave."""
        if not isinstance(self.includes_reporte_key, bool):
            raise InvalidBackupManifestError(
                "La politica de clave debe indicar si incluye reporte.key.",
            )
        if self.protection not in KEY_PROTECTIONS:
            raise InvalidBackupManifestError(
                "La proteccion de reporte.key no esta soportada.",
            )
        if self.protection == "missing" and self.includes_reporte_key:
            raise InvalidBackupManifestError(
                "La politica de reporte.key no es coherente.",
            )
        if self.protection in {"dpapi", "plain"} and not self.includes_reporte_key:
            raise InvalidBackupManifestError(
                "La politica de reporte.key no es coherente.",
            )
        if not isinstance(self.portable_across_windows_users, bool):
            raise InvalidBackupManifestError(
                "La politica de portabilidad de reporte.key no es valida.",
            )

    def to_dict(self) -> dict[str, Any]:
        """Convierte la politica de clave a datos serializables."""
        return {
            "includes_reporte_key": self.includes_reporte_key,
            "protection": self.protection,
            "portable_across_windows_users": (
                self.portable_across_windows_users
            ),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "BackupKeyPolicy":
        """Construye la politica de clave desde datos crudos."""
        if not isinstance(data, dict):
            raise InvalidBackupManifestError(
                "La politica de clave del manifest no es valida.",
            )
        return cls(
            includes_reporte_key=_required_bool(
                data,
                "includes_reporte_key",
                "La politica de clave debe indicar si incluye reporte.key.",
            ),
            protection=_required_str(
                data,
                "protection",
                "La proteccion de reporte.key no es valida.",
            ),
            portable_across_windows_users=_required_bool(
                data,
                "portable_across_windows_users",
                "La politica de portabilidad de reporte.key no es valida.",
            ),
        )


@dataclass(frozen=True, slots=True)
class BackupManifest:
    """Contrato serializable de un respaldo local por perfil."""

    schema_version: int
    app: str
    created_at: str
    backup_type: str
    profile_id: str
    profile_name: str
    key_policy: BackupKeyPolicy
    files: tuple[BackupFileEntry, ...]

    def __post_init__(self) -> None:
        """Valida la estructura completa del manifest."""
        if (
            not isinstance(self.schema_version, int)
            or isinstance(self.schema_version, bool)
            or self.schema_version != SCHEMA_VERSION
        ):
            raise UnsupportedBackupVersionError(
                "La version del manifest de respaldo no esta soportada.",
            )
        if self.app != APP_NAME:
            raise InvalidBackupManifestError(
                "La aplicacion del manifest de respaldo no es valida.",
            )
        if not isinstance(self.created_at, str):
            raise InvalidBackupManifestError(
                "La fecha de creacion del manifest no es valida.",
            )
        _validate_iso_datetime(self.created_at)
        if self.backup_type != BACKUP_TYPE_PROFILE:
            raise InvalidBackupManifestError(
                "El tipo de respaldo no esta soportado.",
            )
        if not isinstance(self.profile_id, str) or not self.profile_id.strip():
            raise InvalidBackupManifestError(
                "El identificador de perfil es obligatorio.",
            )
        if not isinstance(self.profile_name, str):
            raise InvalidBackupManifestError(
                "El nombre de perfil del manifest no es valido.",
            )
        if not isinstance(self.key_policy, BackupKeyPolicy):
            raise InvalidBackupManifestError(
                "La politica de clave del manifest no es valida.",
            )
        if not isinstance(self.files, tuple):
            object.__setattr__(self, "files", tuple(self.files))
        if not self.files:
            raise InvalidBackupManifestError(
                "El manifest debe contener al menos un archivo.",
            )
        _validate_unique_file_paths(self.files)

    def to_dict(self) -> dict[str, Any]:
        """Convierte el manifest a datos serializables deterministas."""
        return {
            "schema_version": self.schema_version,
            "app": self.app,
            "created_at": self.created_at,
            "backup_type": self.backup_type,
            "profile_id": self.profile_id,
            "profile_name": self.profile_name,
            "key_policy": self.key_policy.to_dict(),
            "files": [item.to_dict() for item in self.files],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "BackupManifest":
        """Construye y valida un manifest desde datos crudos."""
        if not isinstance(data, dict):
            raise InvalidBackupManifestError(
                "El manifest de respaldo no es un objeto valido.",
            )
        files_data = data.get("files")
        if not isinstance(files_data, list):
            raise InvalidBackupManifestError(
                "La lista de archivos del manifest no es valida.",
            )
        return cls(
            schema_version=data.get("schema_version"),  # type: ignore[arg-type]
            app=_required_str(data, "app", "La aplicacion del manifest no es valida."),
            created_at=_required_str(
                data,
                "created_at",
                "La fecha de creacion del manifest no es valida.",
            ),
            backup_type=_required_str(
                data,
                "backup_type",
                "El tipo de respaldo no es valido.",
            ),
            profile_id=_required_str(
                data,
                "profile_id",
                "El identificador de perfil no es valido.",
            ),
            profile_name=_required_str(
                data,
                "profile_name",
                "El nombre de perfil no es valido.",
            ),
            key_policy=BackupKeyPolicy.from_dict(data.get("key_policy", {})),
            files=tuple(BackupFileEntry.from_dict(item) for item in files_data),
        )


def normalize_backup_path(path: str) -> str:
    """Normaliza y valida una ruta logica dentro del respaldo."""
    if not isinstance(path, str):
        raise UnsafeBackupPathError("La ruta del respaldo no es valida.")
    raw_path = path
    if not raw_path:
        raise UnsafeBackupPathError("La ruta del respaldo no puede estar vacia.")
    if raw_path.startswith(("/", "\\")):
        raise UnsafeBackupPathError("La ruta del respaldo debe ser relativa.")
    if raw_path.startswith("//") or raw_path.startswith("\\\\"):
        raise UnsafeBackupPathError("La ruta UNC no esta permitida.")
    if (
        WINDOWS_DRIVE_PATTERN.match(raw_path)
        or WINDOWS_DRIVE_RELATIVE_PATTERN.match(raw_path)
    ):
        raise UnsafeBackupPathError("La ruta con unidad no esta permitida.")
    if ":" in raw_path:
        raise UnsafeBackupPathError(
            "La ruta del respaldo no puede contener dos puntos.",
        )

    normalized = raw_path.replace("\\", "/")
    raw_parts = normalized.split("/")
    if any(part in ("", ".", "..") for part in raw_parts):
        raise UnsafeBackupPathError(
            "La ruta del respaldo contiene componentes inseguros.",
        )
    for part in raw_parts:
        _validate_windows_component(part)
    parts = PurePosixPath(normalized).parts
    return "/".join(parts)


def _validate_windows_component(component: str) -> None:
    """Rechaza componentes ambiguos o reservados en Windows."""
    if component.endswith((" ", ".")):
        raise UnsafeBackupPathError(
            "La ruta del respaldo contiene componentes ambiguos.",
        )
    reserved_base = component.split(".", 1)[0].casefold().upper()
    if reserved_base in WINDOWS_RESERVED_NAMES:
        raise UnsafeBackupPathError(
            "La ruta del respaldo contiene un nombre reservado de Windows.",
        )


def _validate_iso_datetime(value: str) -> None:
    """Valida un timestamp ISO-8601 sin imponer zona horaria."""
    try:
        datetime.fromisoformat(value)
    except ValueError as exc:
        raise InvalidBackupManifestError(
            "La fecha de creacion del manifest no es valida.",
        ) from exc


def _validate_unique_file_paths(entries: tuple[BackupFileEntry, ...]) -> None:
    """Evita duplicados usando equivalencia de destino Windows."""
    seen: set[str] = set()
    for entry in entries:
        key = entry.logical_key
        if key in seen:
            raise InvalidBackupManifestError(
                "El manifest contiene rutas de archivo duplicadas.",
            )
        seen.add(key)


def _required_str(
    data: dict[str, Any],
    field: str,
    message: str,
) -> str:
    """Obtiene un campo string obligatorio sin conversiones silenciosas."""
    value = data.get(field)
    if not isinstance(value, str):
        raise InvalidBackupManifestError(message)
    return value


def _required_bool(
    data: dict[str, Any],
    field: str,
    message: str,
) -> bool:
    """Obtiene un campo booleano obligatorio sin conversiones silenciosas."""
    value = data.get(field)
    if not isinstance(value, bool):
        raise InvalidBackupManifestError(message)
    return value
