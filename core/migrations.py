"""Motor puro de migraciones secuenciales N -> N+1 para documentos JSON.

Separa a propósito la transformación (este módulo) de la persistencia: no
conoce rutas, archivos ni perfiles. Sirve tanto para ``schema_version`` por
archivo como para ``profile_format_version``, cada uno con su propio
registro, para que un step de un dominio no pueda aplicarse por error al
otro.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable

from core.profile_metadata import PROFILE_FORMAT_VERSION_KEY
from core.schema_versioning import SCHEMA_VERSION_KEY


class MigrationError(Exception):
    """Error base del motor de migraciones.

    No hereda de ``ValueError`` a propósito: así ningún ``except ValueError``
    heredado puede absorber una cadena de migración incompleta o corrupta y
    seguir operando sobre el documento.
    """


class InvalidMigrationStepError(MigrationError):
    """Un step se registra con versiones que no forman un paso N -> N+1."""

    def __init__(self, from_version: object, to_version: object) -> None:
        """Registra las versiones declaradas, sin exponer el documento."""
        super().__init__(
            f"step inválido ({from_version} -> {to_version}); "
            "debe avanzar exactamente una versión positiva.",
        )
        self.from_version = from_version
        self.to_version = to_version


class DuplicateMigrationStepError(MigrationError):
    """Ya existe un step registrado para la misma versión de origen."""

    def __init__(self, from_version: int) -> None:
        """Registra la versión de origen duplicada."""
        super().__init__(
            f"ya existe un step registrado desde la versión {from_version}.",
        )
        self.from_version = from_version


class MissingMigrationStepError(MigrationError):
    """La cadena de migración tiene un hueco entre origen y destino."""

    def __init__(self, missing_from_version: int, target_version: int) -> None:
        """Registra desde dónde falta el siguiente step y el destino final."""
        super().__init__(
            f"falta un step registrado desde la versión "
            f"{missing_from_version} para alcanzar la versión "
            f"{target_version}.",
        )
        self.missing_from_version = missing_from_version
        self.target_version = target_version


class DowngradeNotSupportedError(MigrationError):
    """Se intentó migrar hacia una versión anterior a la de origen."""

    def __init__(self, from_version: int, target_version: int) -> None:
        """Registra el origen y el destino del downgrade rechazado."""
        super().__init__(
            f"no se admite downgrade de la versión {from_version} "
            f"a la versión {target_version}.",
        )
        self.from_version = from_version
        self.target_version = target_version


class MigrationVersionMismatchError(MigrationError):
    """La versión de entrada no está vinculada correctamente al documento.

    Cubre tanto argumentos ``from_version``/``target_version`` que no son un
    entero positivo real (``bool`` incluido) como un documento cuya versión
    declarada está ausente, es inválida, o no coincide con ``from_version``.
    El motor nunca migra confiando ciegamente en lo que dice el llamador.
    """

    def __init__(
        self,
        reason: str,
        expected_version: object = None,
        observed_version: object = None,
    ) -> None:
        """Registra la razón lógica y las versiones involucradas, sin el documento."""
        detail = ""
        if expected_version is not None or observed_version is not None:
            detail = f" (esperada {expected_version}, declarada {observed_version})"
        super().__init__(f"versión de migración inconsistente: {reason}{detail}.")
        self.reason = reason
        self.expected_version = expected_version
        self.observed_version = observed_version


class MigrationExecutionError(MigrationError):
    """Un step falló al ejecutarse o produjo un resultado inaceptable."""

    def __init__(self, from_version: int, to_version: int, reason: str) -> None:
        """Registra el paso afectado y una razón lógica, sin datos del documento."""
        super().__init__(
            f"el step {from_version} -> {to_version} no pudo completarse "
            f"({reason}).",
        )
        self.from_version = from_version
        self.to_version = to_version
        self.reason = reason


@dataclass(frozen=True, slots=True)
class MigrationStep:
    """Transforma un documento de una versión a la siguiente, una sola vez.

    ``migrate`` recibe una copia independiente del documento en la versión
    ``from_version`` y debe devolver un documento nuevo en la versión
    ``to_version``; no se le exige evitar mutar lo que recibe, porque el
    motor nunca reutiliza esa copia para otra cosa.
    """

    from_version: int
    to_version: int
    migrate: Callable[[dict[str, Any]], dict[str, Any]]

    def __post_init__(self) -> None:
        """Rechaza steps que no representen un único paso N -> N+1."""
        if (
            type(self.from_version) is not int
            or type(self.to_version) is not int
            or self.from_version <= 0
            or self.to_version != self.from_version + 1
        ):
            raise InvalidMigrationStepError(self.from_version, self.to_version)


class MigrationRegistry:
    """Registro de steps N -> N+1 para una única familia de documentos."""

    def __init__(self) -> None:
        """Inicializa el registro vacío."""
        self._steps: dict[int, MigrationStep] = {}

    def register(self, step: MigrationStep) -> None:
        """Agrega un step, rechazando un segundo step para el mismo origen."""
        if step.from_version in self._steps:
            raise DuplicateMigrationStepError(step.from_version)
        self._steps[step.from_version] = step

    def resolve_chain(
        self,
        from_version: int,
        target_version: int,
    ) -> list[MigrationStep]:
        """Devuelve, en orden, los steps necesarios para llegar al destino.

        Sin pasos si ya está en la versión destino. Nunca resuelve hacia
        atrás: lo rechaza explícitamente en vez de buscar una cadena inversa.
        """
        if target_version < from_version:
            raise DowngradeNotSupportedError(from_version, target_version)
        chain: list[MigrationStep] = []
        current = from_version
        while current < target_version:
            step = self._steps.get(current)
            if step is None:
                raise MissingMigrationStepError(current, target_version)
            chain.append(step)
            current = step.to_version
        return chain


class ProfileFormatMigrationRegistry(MigrationRegistry):
    """Registro de migraciones de ``profile_format_version``.

    Deliberadamente distinto de ``SchemaMigrationRegistry``: un step de
    formato global de perfil nunca debe poder registrarse ni resolverse
    como si fuera una migración de archivo.
    """


class DocumentType(str, Enum):
    """Identidad lógica estable de cada familia de documento persistente."""

    MONTHLY_BUDGET = "monthly_budget"
    ACCOUNTS = "accounts"
    DEBTS = "debts"
    DEBT_PAYMENTS = "debt_payments"
    DEBT_SNAPSHOTS = "debt_snapshots"
    MONTHLY_CLOSURES = "monthly_closures"
    CATEGORIES = "categories"
    SETTINGS = "settings"
    PROFILES_CATALOG = "profiles_catalog"
    ACTIVE_PROFILE = "active_profile"
    PROFILE_METADATA = "profile_metadata"


class SchemaMigrationRegistry:
    """Registros de ``schema_version`` separados por familia de documento.

    Cada familia puede necesitar una transformación distinta para la misma
    versión de origen, así que no comparten un único registro.
    """

    def __init__(self) -> None:
        """Inicializa sin registros por familia."""
        self._by_type: dict[DocumentType, MigrationRegistry] = {}

    def register(self, document_type: DocumentType, step: MigrationStep) -> None:
        """Agrega un step a la familia indicada, creando su registro si falta."""
        registry = self._by_type.setdefault(document_type, MigrationRegistry())
        registry.register(step)

    def for_document_type(self, document_type: DocumentType) -> MigrationRegistry:
        """Devuelve el registro de la familia, vacío si no tiene steps."""
        return self._by_type.get(document_type) or MigrationRegistry()


class MigrationEngine:
    """Ejecuta una cadena de migraciones sobre un documento, en memoria.

    No conoce archivos ni perfiles: sólo documentos, versiones y un
    registro que resuelve la cadena. ``version_key`` identifica el campo
    del documento que cada step debe dejar en ``to_version``.
    """

    def __init__(self, version_key: str) -> None:
        """Fija qué campo del documento declara la versión migrada."""
        self._version_key = version_key

    def migrate_document(
        self,
        document: dict[str, Any],
        from_version: int,
        target_version: int,
        registry: MigrationRegistry,
    ) -> dict[str, Any]:
        """Migra ``document`` de ``from_version`` a ``target_version``.

        Antes de resolver o ejecutar cualquier step, exige que ``document``
        declare exactamente ``from_version`` en ``version_key``: el motor
        nunca confía ciegamente en lo que dice el llamador. Un documento
        legacy sin la clave no se adivina aquí; quien integra el motor debe
        materializar una copia de trabajo con la versión efectiva antes de
        llamar (ver ``core.schema_versioning``/``SchemaVersionPolicy``).

        Sin pasos si ya coincide con el destino. Nunca migra hacia atrás.
        El documento recibido nunca se modifica: se compara contra una copia
        tomada antes de empezar y cualquier diferencia es un error del motor
        o de un step, no un efecto aceptable.
        """
        self._require_positive_int(from_version, "from_version")
        self._require_positive_int(target_version, "target_version")
        if not isinstance(document, dict):
            raise MigrationExecutionError(
                from_version,
                target_version,
                "el documento no es un objeto",
            )
        declared = self._declared_version(document)
        if declared != from_version:
            raise MigrationVersionMismatchError(
                "la versión declarada por el documento no coincide con "
                "from_version",
                expected_version=from_version,
                observed_version=declared,
            )
        original_snapshot = copy.deepcopy(document)
        if target_version < from_version:
            raise DowngradeNotSupportedError(from_version, target_version)
        if target_version == from_version:
            result = copy.deepcopy(document)
        else:
            chain = registry.resolve_chain(from_version, target_version)
            current = copy.deepcopy(document)
            for step in chain:
                current = self._apply_step(step, current)
            result = current
        if document != original_snapshot:
            raise MigrationExecutionError(
                from_version,
                target_version,
                "el documento original fue modificado",
            )
        return result

    @staticmethod
    def _require_positive_int(value: object, label: str) -> None:
        """Rechaza cualquier versión que no sea un entero positivo real."""
        if type(value) is not int or value <= 0:
            raise MigrationVersionMismatchError(
                f"{label} debe ser un entero positivo",
                observed_version=value,
            )

    def _declared_version(self, document: dict[str, Any]) -> int:
        """Devuelve la versión que el documento declara, o falla explícito."""
        if self._version_key not in document:
            raise MigrationVersionMismatchError(
                "el documento no declara la versión de entrada",
            )
        value = document[self._version_key]
        if type(value) is not int or value <= 0:
            raise MigrationVersionMismatchError(
                "la versión declarada no es un entero positivo",
                observed_version=value,
            )
        return value

    def _apply_step(
        self,
        step: MigrationStep,
        current: dict[str, Any],
    ) -> dict[str, Any]:
        """Ejecuta un único step y valida que su resultado sea aceptable."""
        step_input = copy.deepcopy(current)
        try:
            produced = step.migrate(step_input)
        except MigrationError:
            raise
        except Exception as error:
            raise MigrationExecutionError(
                step.from_version,
                step.to_version,
                "el step lanzó una excepción",
            ) from error
        if not isinstance(produced, dict):
            raise MigrationExecutionError(
                step.from_version,
                step.to_version,
                "el resultado no es un documento",
            )
        if produced.get(self._version_key) != step.to_version:
            raise MigrationExecutionError(
                step.from_version,
                step.to_version,
                "la versión resultante no es la declarada por el step",
            )
        return produced


SCHEMA_MIGRATION_ENGINE = MigrationEngine(SCHEMA_VERSION_KEY)
PROFILE_FORMAT_MIGRATION_ENGINE = MigrationEngine(PROFILE_FORMAT_VERSION_KEY)

# Registros productivos: vacíos porque CURRENT_SCHEMA_VERSION y
# CURRENT_PROFILE_FORMAT_VERSION son ambos 1. No insertar steps ficticios
# aquí; la capacidad del motor se demuestra con registros sintéticos de test.
PRODUCTION_SCHEMA_MIGRATIONS = SchemaMigrationRegistry()
PRODUCTION_PROFILE_FORMAT_MIGRATIONS = ProfileFormatMigrationRegistry()
