"""Servicio para serializar y validar manifests de respaldo."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from core.models.backup import (
    APP_NAME,
    BACKUP_TYPE_PROFILE,
    CURRENT_BACKUP_SCHEMA_VERSION,
    BackupFileEntry,
    BackupKeyPolicy,
    BackupManifest,
    InvalidBackupManifestError,
)


class BackupManifestService:
    """Opera sobre manifests suministrados explicitamente por consumidores."""

    def build_profile_manifest(
        self,
        *,
        created_at: str,
        profile_id: str,
        profile_name: str,
        key_policy: BackupKeyPolicy,
        files: list[BackupFileEntry],
        app_version: str,
        profile_format_version: int,
    ) -> BackupManifest:
        """Construye un manifest de respaldo por perfil en la version actual.

        Todo respaldo nuevo usa ``CURRENT_BACKUP_SCHEMA_VERSION`` (2): la
        version 1 solo se reconoce al leer respaldos historicos existentes,
        nunca se vuelve a producir.
        """
        return BackupManifest(
            schema_version=CURRENT_BACKUP_SCHEMA_VERSION,
            app=APP_NAME,
            created_at=created_at,
            backup_type=BACKUP_TYPE_PROFILE,
            profile_id=profile_id,
            profile_name=profile_name,
            key_policy=key_policy,
            files=tuple(files),
            app_version=app_version,
            profile_format_version=profile_format_version,
        )

    def to_json(self, manifest: BackupManifest) -> str:
        """Serializa un manifest de forma deterministica."""
        return json.dumps(
            manifest.to_dict(),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ) + "\n"

    def from_json(self, content: str) -> BackupManifest:
        """Deserializa y valida un manifest desde texto JSON."""
        try:
            data: Any = json.loads(content)
        except json.JSONDecodeError as exc:
            raise InvalidBackupManifestError(
                "El JSON del manifest de respaldo esta corrupto.",
            ) from exc
        return BackupManifest.from_dict(data)

    def save_json(self, manifest: BackupManifest, path: str | Path) -> Path:
        """Guarda un manifest en una ruta suministrada explicitamente."""
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(self.to_json(manifest), encoding="utf-8")
        return target

    def load_json(self, path: str | Path) -> BackupManifest:
        """Carga un manifest desde una ruta suministrada explicitamente."""
        return self.from_json(Path(path).read_text(encoding="utf-8"))
