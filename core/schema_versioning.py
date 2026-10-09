"""Política de versionado explícito de documentos JSON persistentes."""

from __future__ import annotations

from typing import Any


CURRENT_SCHEMA_VERSION = 1
LEGACY_IMPLICIT_SCHEMA_VERSION = 1
SCHEMA_VERSION_KEY = "schema_version"


class SchemaVersionError(Exception):
    """Error base de versionado de un documento persistente.

    No hereda de ``ValueError`` a propósito: así ningún ``except ValueError``
    heredado puede tratar un documento de versión incompatible como un dato
    simplemente inválido y seguir operando sobre el perfil.
    """

    def __init__(self, message: str) -> None:
        """Guarda el mensaje y deja sin asignar el nombre del documento."""
        super().__init__(message)
        self.document_name: str | None = None

    def __str__(self) -> str:
        """Devuelve el mensaje, con el nombre del documento si se conoce."""
        message = super().__str__()
        if self.document_name:
            return f"{self.document_name}: {message}"
        return message


class UnsupportedSchemaVersionError(SchemaVersionError):
    """Indica una versión posterior a la que esta aplicación sabe leer."""

    def __init__(self, observed_version: int, supported_version: int) -> None:
        """Registra la versión encontrada y la máxima soportada."""
        super().__init__(
            f"schema_version {observed_version} no está soportada; "
            f"la versión máxima soportada es {supported_version}.",
        )
        self.observed_version = observed_version
        self.supported_version = supported_version


class InvalidSchemaVersionError(SchemaVersionError):
    """Indica un ``schema_version`` que no es un entero positivo.

    Sólo conserva el tipo recibido y, cuando es un entero, su valor: nunca
    el contenido de un texto ni de una estructura.
    """

    def __init__(self, observed_value: object) -> None:
        """Registra el tipo recibido sin conservar contenido arbitrario."""
        self.observed_type = type(observed_value).__name__
        self.observed_version = (
            observed_value if type(observed_value) is int else None
        )
        detail = (
            f"valor {self.observed_version}"
            if self.observed_version is not None
            else f"tipo {self.observed_type}"
        )
        super().__init__(
            f"schema_version inválida ({detail}); "
            "debe ser un entero mayor que cero.",
        )


class SchemaVersionPolicy:
    """Decide qué versiones de documento se aceptan y cuál se escribe.

    Trabaja sólo sobre documentos JSON con raíz objeto y no conoce archivos
    ni agregados de negocio.
    """

    CURRENT_VERSION = CURRENT_SCHEMA_VERSION

    def effective_version(self, document: dict[str, Any]) -> int:
        """Devuelve la versión del documento o falla si no es aceptable.

        Un documento sin ``schema_version`` es el formato previo al
        versionado explícito y se interpreta como versión 1.
        """
        if SCHEMA_VERSION_KEY not in document:
            return LEGACY_IMPLICIT_SCHEMA_VERSION
        version = document[SCHEMA_VERSION_KEY]
        if type(version) is not int or version <= 0:
            raise InvalidSchemaVersionError(version)
        if version > self.CURRENT_VERSION:
            raise UnsupportedSchemaVersionError(version, self.CURRENT_VERSION)
        return version

    def validate(self, document: Any) -> None:
        """Rechaza un documento de versión futura o inválida.

        Una raíz que no es objeto no puede declarar versión: se deja pasar
        para que cada servicio conserve su comportamiento actual ante ella.
        """
        if isinstance(document, dict):
            self.effective_version(document)

    def prepare_for_write(self, document: dict[str, Any]) -> dict[str, Any]:
        """Devuelve una copia del documento marcada con la versión actual.

        No modifica el documento recibido y se niega a reetiquetar uno que
        declare una versión futura o inválida.
        """
        if not isinstance(document, dict):
            raise TypeError("El documento versionado debe ser un objeto JSON.")
        self.effective_version(document)
        return {**document, SCHEMA_VERSION_KEY: self.CURRENT_VERSION}
