"""Persistencia de los metadatos globales de cada perfil."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable, Protocol

from avalancha import __version__
from core.profile_metadata import (
    PROFILE_METADATA_FILE_NAME,
    InvalidProfileMetadataError,
    ProfileMetadata,
    ProfileMetadataPolicy,
    UnreadableProfileDocumentError,
)
from core.versioned_json_store import VersionedJsonStore
from services.settings_service import SettingsService


class ProfileLocation(Protocol):
    """Datos mínimos de un perfil que necesita este servicio."""

    id: str
    nombre: str
    raiz: Path
    data_dir: Path
    config_dir: Path


class ProfileDocumentInventory:
    """Única fuente de qué JSON ordinarios componen un perfil.

    Enumera los archivos versionados por esquema que deben revisarse antes
    de etiquetar el formato global. No incluye claves, reportes cifrados,
    copias históricas de ``data/backups``, temporales ni registros.
    """

    BUDGET_FILE_PATTERN = "presupuesto_????-??.json"
    DATA_FILE_NAMES = (
        "cuentas.json",
        "deudas.json",
        "debt_payments.json",
        "debt_snapshots.json",
        "monthly_closures.json",
        "categorias.json",
    )
    CONFIG_FILE_NAMES = (SettingsService.ARCHIVO_CONFIGURACION,)

    def existing_documents(self, profile: ProfileLocation) -> list[Path]:
        """Devuelve, en orden estable, los JSON del perfil que existen."""
        documents = sorted(profile.data_dir.glob(self.BUDGET_FILE_PATTERN))
        documents.extend(
            profile.data_dir / name for name in self.DATA_FILE_NAMES
        )
        documents.extend(
            profile.config_dir / name for name in self.CONFIG_FILE_NAMES
        )
        return [path for path in documents if path.is_file()]


class ProfileMetadataService:
    """Lee, valida y crea ``profile_metadata.json`` de un perfil."""

    def __init__(
        self,
        store: VersionedJsonStore | None = None,
        policy: ProfileMetadataPolicy | None = None,
        inventory: ProfileDocumentInventory | None = None,
        app_version: str | None = None,
    ) -> None:
        """Inicializa colaboradores y la versión de producto que escribe."""
        self._store = store or VersionedJsonStore()
        self._policy = policy or ProfileMetadataPolicy()
        self._inventory = inventory or ProfileDocumentInventory()
        self._app_version = app_version or __version__

    def metadata_path(self, profile: ProfileLocation) -> Path:
        """Devuelve la ruta de los metadatos dentro de la raíz del perfil."""
        return profile.raiz / PROFILE_METADATA_FILE_NAME

    def has_metadata(self, profile: ProfileLocation) -> bool:
        """Indica si el perfil ya tiene archivo de metadatos."""
        return self.metadata_path(profile).exists()

    def validate_existing(
        self,
        profile: ProfileLocation,
    ) -> ProfileMetadata | None:
        """Valida los metadatos presentes sin escribir nada.

        Devuelve ``None`` sólo si el archivo no existe. Un archivo corrupto
        no equivale a un perfil histórico sin metadatos: se rechaza.
        """
        path = self.metadata_path(profile)
        if not path.exists():
            return None
        try:
            document = self._store.read(path)
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise InvalidProfileMetadataError("documento", profile.id) from None
        return self._policy.parse(document, expected_slug=profile.id)

    def preflight_legacy_documents(self, profile: ProfileLocation) -> None:
        """Comprueba, sin modificar nada, que el perfil admite etiquetarse.

        Lee cada JSON ordinario existente: una versión de esquema futura o
        inválida se propaga como error de versionado, y un archivo ilegible
        impide determinar el formato del perfil.
        """
        self.validate_documents(
            self._inventory.existing_documents(profile),
            profile.id,
        )

    def validate_documents(
        self,
        documents: Iterable[Path],
        profile_slug: str,
    ) -> None:
        """Lee JSON versionados y falla ante el primero incompatible.

        Sirve también para revisar archivos que todavía no están dentro
        del perfil, como las fuentes de una copia histórica.
        """
        for path in documents:
            try:
                self._store.read(path)
            except (json.JSONDecodeError, UnicodeDecodeError):
                raise UnreadableProfileDocumentError(
                    path.name,
                    profile_slug,
                ) from None

    def ensure(self, profile: ProfileLocation) -> ProfileMetadata:
        """Valida los metadatos del perfil o los crea una sola vez.

        Con metadatos presentes es una operación de sólo lectura. Sin ellos,
        revisa primero los archivos del perfil y recién entonces escribe:
        un perfil con datos previos se etiqueta con el formato implícito
        histórico y uno sin datos nace con el formato actual.
        """
        existing = self.validate_existing(profile)
        if existing is not None:
            return existing
        self.preflight_legacy_documents(profile)
        has_documents = bool(self._inventory.existing_documents(profile))
        metadata = self._policy.build(
            profile_slug=profile.id,
            profile_name=profile.nombre,
            app_version=self._app_version,
            profile_format_version=(
                self._policy.LEGACY_IMPLICIT_VERSION
                if has_documents
                else self._policy.CURRENT_VERSION
            ),
        )
        profile.raiz.mkdir(parents=True, exist_ok=True)
        self._store.write(self.metadata_path(profile), metadata.to_document())
        return metadata

    def discard(self, profile: ProfileLocation) -> None:
        """Elimina metadatos recién creados por una operación que falló."""
        try:
            self.metadata_path(profile).unlink(missing_ok=True)
        except OSError:
            return
