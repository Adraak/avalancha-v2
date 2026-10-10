"""Modelo y reglas puras de los metadatos globales de un perfil.

``profile_format_version`` versiona el perfil completo: el conjunto de
archivos que lo componen y cómo se relacionan. Es un concepto distinto de
``schema_version``, que versiona la estructura de un único archivo JSON y
se gestiona en ``core.schema_versioning``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


CURRENT_PROFILE_FORMAT_VERSION = 1
LEGACY_IMPLICIT_PROFILE_FORMAT_VERSION = 1
PROFILE_METADATA_FILE_NAME = "profile_metadata.json"
PROFILE_FORMAT_VERSION_KEY = "profile_format_version"
PROFILE_SLUG_KEY = "profile_slug"
PROFILE_NAME_KEY = "profile_name"
APP_VERSION_KEY = "app_version"


class ProfileMetadataError(Exception):
    """Error base del formato global de un perfil.

    No hereda de ``ValueError`` para que ningún ``except ValueError``
    heredado trate un perfil incompatible como un dato simplemente inválido.
    Sólo identifica el perfil por su slug lógico: nunca rutas ni contenido.
    """

    def __init__(self, message: str, profile_slug: str | None = None) -> None:
        """Guarda el mensaje y el slug lógico del perfil afectado."""
        super().__init__(message)
        self.profile_slug = profile_slug

    def __str__(self) -> str:
        """Devuelve el mensaje, con el slug del perfil si se conoce."""
        message = super().__str__()
        if self.profile_slug:
            return f"perfil {self.profile_slug}: {message}"
        return message


class UnsupportedProfileFormatVersionError(ProfileMetadataError):
    """Indica un perfil escrito con un formato global posterior al soportado."""

    def __init__(
        self,
        observed_version: int,
        supported_version: int,
        profile_slug: str | None = None,
    ) -> None:
        """Registra el formato encontrado y el máximo soportado."""
        super().__init__(
            f"profile_format_version {observed_version} no está soportada; "
            f"la versión máxima soportada es {supported_version}.",
            profile_slug,
        )
        self.observed_version = observed_version
        self.supported_version = supported_version


class InvalidProfileMetadataError(ProfileMetadataError):
    """Indica metadatos de perfil ilegibles, incompletos o incoherentes.

    Conserva el nombre lógico del campo que falló, nunca su valor.
    """

    def __init__(self, field: str, profile_slug: str | None = None) -> None:
        """Registra qué campo de los metadatos no es aceptable."""
        super().__init__(
            f"los metadatos del perfil no son válidos (campo: {field}).",
            profile_slug,
        )
        self.field = field


class UnreadableProfileDocumentError(ProfileMetadataError):
    """Indica que un archivo del perfil impide etiquetar su formato global."""

    def __init__(
        self,
        document_name: str,
        profile_slug: str | None = None,
    ) -> None:
        """Registra el nombre del archivo que no pudo interpretarse."""
        super().__init__(
            f"el archivo {document_name} no es JSON legible; "
            "no se puede determinar el formato del perfil.",
            profile_slug,
        )
        self.document_name = document_name


@dataclass(frozen=True, slots=True)
class ProfileMetadata:
    """Identidad y formato global de un perfil, sin datos financieros."""

    profile_slug: str
    profile_name: str
    app_version: str
    profile_format_version: int = CURRENT_PROFILE_FORMAT_VERSION

    def to_document(self) -> dict[str, Any]:
        """Convierte los metadatos al documento JSON que se persiste."""
        return {
            PROFILE_FORMAT_VERSION_KEY: self.profile_format_version,
            PROFILE_SLUG_KEY: self.profile_slug,
            PROFILE_NAME_KEY: self.profile_name,
            APP_VERSION_KEY: self.app_version,
        }


class ProfileMetadataPolicy:
    """Valida y construye metadatos de perfil sin tocar el filesystem."""

    CURRENT_VERSION = CURRENT_PROFILE_FORMAT_VERSION
    LEGACY_IMPLICIT_VERSION = LEGACY_IMPLICIT_PROFILE_FORMAT_VERSION

    def build(
        self,
        profile_slug: str,
        profile_name: str,
        app_version: str,
        profile_format_version: int | None = None,
    ) -> ProfileMetadata:
        """Construye metadatos válidos para escribir.

        Sin formato explícito usa el actual. Sólo acepta formatos que esta
        aplicación sabe leer, de modo que no puede etiquetar uno futuro.
        """
        document = {
            PROFILE_FORMAT_VERSION_KEY: (
                self.CURRENT_VERSION
                if profile_format_version is None
                else profile_format_version
            ),
            PROFILE_SLUG_KEY: profile_slug,
            PROFILE_NAME_KEY: profile_name,
            APP_VERSION_KEY: app_version,
        }
        return self.parse(document, expected_slug=profile_slug)

    def parse(self, document: Any, expected_slug: str) -> ProfileMetadata:
        """Interpreta un documento de metadatos o falla sin corregirlo.

        El formato global se valida primero: si es futuro, el resto de la
        estructura puede haber cambiado y no corresponde juzgarla.
        """
        if not isinstance(document, dict):
            raise InvalidProfileMetadataError("documento", expected_slug)
        version = self._format_version(document, expected_slug)
        slug = self._text(document, PROFILE_SLUG_KEY, expected_slug)
        if slug != expected_slug:
            raise InvalidProfileMetadataError(PROFILE_SLUG_KEY, expected_slug)
        return ProfileMetadata(
            profile_slug=slug,
            profile_name=self._text(document, PROFILE_NAME_KEY, expected_slug),
            app_version=self._text(document, APP_VERSION_KEY, expected_slug),
            profile_format_version=version,
        )

    def _format_version(self, document: dict[str, Any], slug: str) -> int:
        """Valida ``profile_format_version``, obligatorio en metadatos."""
        if PROFILE_FORMAT_VERSION_KEY not in document:
            raise InvalidProfileMetadataError(PROFILE_FORMAT_VERSION_KEY, slug)
        version = document[PROFILE_FORMAT_VERSION_KEY]
        if type(version) is not int or version <= 0:
            raise InvalidProfileMetadataError(PROFILE_FORMAT_VERSION_KEY, slug)
        if version > self.CURRENT_VERSION:
            raise UnsupportedProfileFormatVersionError(
                version,
                self.CURRENT_VERSION,
                slug,
            )
        return version

    @staticmethod
    def _text(document: dict[str, Any], key: str, slug: str) -> str:
        """Exige un texto no vacío en el campo indicado."""
        value = document.get(key)
        if type(value) is not str or not value.strip():
            raise InvalidProfileMetadataError(key, slug)
        return value
