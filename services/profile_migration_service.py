"""Orquestación y transacción de migraciones de un perfil en disco.

Separa lo puro (``core.migrations``, que sólo transforma documentos en
memoria) de lo que toca el filesystem: descubrir qué documentos del perfil
existen, leerlos, pedir al motor que los transforme uno por uno y recién
entonces persistir todos los resultados como un único bloque, con los
metadatos globales del perfil siempre al final.

``profiles_catalog`` (``perfiles.json``) y ``active_profile``
(``perfil_activo.json``) son identidades válidas de ``DocumentType`` para el
motor, pero no forman parte de la migración de UN perfil: viven en la raíz
de ``profiles_root``, son compartidas entre todos los perfiles, y una
transacción de migración scoped a un perfil no debe tocarlas. Quedan fuera
de ``_discover_profile_documents`` a propósito.
"""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from core.migrations import (
    PROFILE_FORMAT_MIGRATION_ENGINE,
    PRODUCTION_PROFILE_FORMAT_MIGRATIONS,
    PRODUCTION_SCHEMA_MIGRATIONS,
    SCHEMA_MIGRATION_ENGINE,
    DocumentType,
    MigrationEngine,
    MigrationRegistry,
    ProfileFormatMigrationRegistry,
    SchemaMigrationRegistry,
)
from core.profile_metadata import CURRENT_PROFILE_FORMAT_VERSION
from core.schema_versioning import CURRENT_SCHEMA_VERSION, SCHEMA_VERSION_KEY
from core.versioned_json_store import VersionedJsonStore
from services.profile_metadata_service import (
    ProfileDocumentInventory,
    ProfileLocation,
    ProfileMetadataService,
)


# Mapa estable nombre-de-archivo -> DocumentType, construido sobre los
# mismos literales que ya usa el inventario de 22E para no mantener una
# segunda lista que pueda divergir de la primera.
_DATA_DOCUMENT_TYPES = (
    DocumentType.ACCOUNTS,
    DocumentType.DEBTS,
    DocumentType.DEBT_PAYMENTS,
    DocumentType.DEBT_SNAPSHOTS,
    DocumentType.MONTHLY_CLOSURES,
    DocumentType.CATEGORIES,
)
_DOCUMENT_TYPE_BY_NAME: dict[str, DocumentType] = dict(
    zip(ProfileDocumentInventory.DATA_FILE_NAMES, _DATA_DOCUMENT_TYPES),
)
for _config_name in ProfileDocumentInventory.CONFIG_FILE_NAMES:
    _DOCUMENT_TYPE_BY_NAME[_config_name] = DocumentType.SETTINGS


def _document_type_for(path: Path) -> DocumentType | None:
    """Identifica la familia lógica de un archivo del inventario de 22E."""
    if path.match(ProfileDocumentInventory.BUDGET_FILE_PATTERN):
        return DocumentType.MONTHLY_BUDGET
    return _DOCUMENT_TYPE_BY_NAME.get(path.name)


def _prepare_for_engine(
    document: dict[str, Any],
    version_key: str,
    effective_version: int,
) -> dict[str, Any]:
    """Devuelve el documento listo para el motor, sin mutar el original.

    Si la clave de versión está ausente (legacy), la materializa en una
    copia de trabajo con la versión efectiva ya calculada; nunca escribe esa
    copia a disco ni toca la fuente.
    """
    if version_key in document:
        return document
    return {**document, version_key: effective_version}


def _effective_version_of_validated_document(
    document: dict[str, Any],
    version_key: str,
) -> int:
    """Extrae la versión de un documento ya aceptado por ``store.read``.

    No vuelve a aplicar el techo productivo de ``SchemaVersionPolicy``: ese
    control ya ocurrió con la política que el store tenga inyectada (la
    productiva real, o una sintética de test). Repetirlo aquí con una
    política nueva reintroduciría el techo real y rechazaría documentos que
    el store ya aceptó legítimamente. Legacy sin la clave sigue siendo v1.
    """
    if version_key not in document:
        return 1
    return document[version_key]


@dataclass(frozen=True, slots=True)
class DocumentMigrationPlan:
    """Describe si un documento del perfil necesita migrar su schema."""

    document_type: DocumentType
    path: Path
    current_schema_version: int
    target_schema_version: int
    needs_migration: bool


@dataclass(frozen=True, slots=True)
class ProfileMigrationPlan:
    """Describe, sin tocar el filesystem, qué migraría un perfil y por qué.

    ``documents`` enumera cada archivo descubierto del perfil (sin incluir
    los globales del sistema) junto con su versión efectiva y si necesita
    migrar. Los metadatos tienen dos ejes independientes: el ``schema`` del
    propio archivo ``profile_metadata.json`` y el ``profile_format`` del
    perfil completo.
    """

    current_profile_format_version: int | None
    target_profile_format_version: int
    needs_profile_format_migration: bool
    metadata_schema_current_version: int | None
    metadata_schema_target_version: int
    needs_metadata_schema_migration: bool
    documents: tuple[DocumentMigrationPlan, ...]

    @property
    def needs_migration(self) -> bool:
        """Indica si cualquier eje o documento necesita migrar."""
        return (
            self.needs_profile_format_migration
            or self.needs_metadata_schema_migration
            or any(item.needs_migration for item in self.documents)
        )


class ProfileMigrationTransaction:
    """Confirma en bloque varias escrituras JSON de un mismo perfil.

    Cada escritura individual ya es atómica (``VersionedJsonStore`` escribe
    a un temporal y reemplaza con ``os.replace``). Esta transacción añade la
    garantía de todo-o-nada entre *varios* archivos: si un reemplazo falla a
    mitad del lote, los que ya se habían confirmado se restauran a sus bytes
    previos, también mediante reemplazo atómico.

    Esta garantía cubre fallos controlados (una excepción durante un
    ``os.replace``, por ejemplo). No cubre una caída abrupta del proceso o
    del equipo a mitad del lote, ni un segundo fallo durante la propia
    restauración: si el reemplazo de rollback de un archivo también falla,
    ese archivo puntual puede quedar con el contenido nuevo en vez del
    original, y la excepción de rollback se descarta en silencio para no
    ocultar la excepción original del commit. Ambas limitaciones quedan
    registradas como deuda explícita para 22H/23; resolverlas requeriría un
    journal durable que esta etapa decide no introducir.
    """

    def __init__(self, store: VersionedJsonStore | None = None) -> None:
        """Inicializa el almacén de documentos y la lista de escrituras."""
        self._store = store or VersionedJsonStore()
        self._writes: list[tuple[Path, dict[str, Any]]] = []

    def stage(self, path: Path, document: dict[str, Any]) -> None:
        """Agrega una escritura al lote, en el orden en que se confirmará.

        No escribe nada todavía: sólo registra la intención. Quien orquesta
        la migración debe agregar los metadatos globales al final.
        """
        self._writes.append((path, document))

    def commit(self) -> None:
        """Confirma todas las escrituras o restaura el estado previo.

        Toma el respaldo de cada destino antes de reemplazar el primero,
        para no depender de que los reemplazos ya hechos sigan siendo
        reversibles después de que uno posterior falle.
        """
        backups = [
            (path, path.read_bytes() if path.exists() else None)
            for path, _ in self._writes
        ]
        committed: list[Path] = []
        try:
            for path, document in self._writes:
                self._store.write(path, document)
                committed.append(path)
        except BaseException:
            self._rollback(backups, committed)
            raise

    @staticmethod
    def _rollback(
        backups: list[tuple[Path, bytes | None]],
        committed: list[Path],
    ) -> None:
        """Restaura cada archivo ya confirmado a sus bytes previos."""
        committed_set = set(committed)
        for path, original in backups:
            if path in committed_set:
                ProfileMigrationTransaction._restore(path, original)

    @staticmethod
    def _restore(path: Path, original: bytes | None) -> None:
        """Repone el contenido anterior de forma atómica, o lo elimina.

        Si el propio reemplazo de restauración falla, la excepción se
        descarta para no ocultar la excepción original del commit; ese
        archivo puntual queda en un estado que esta transacción no puede
        garantizar (ver limitación documentada en la clase).
        """
        if original is None:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                return
            return
        descriptor, temp_name = tempfile.mkstemp(
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".rollback",
        )
        temporary = Path(temp_name)
        try:
            with os.fdopen(descriptor, "wb") as file:
                file.write(original)
                file.flush()
                os.fsync(file.fileno())
            os.replace(temporary, path)
        except OSError:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass


class ProfileMigrationService:
    """Coordina productivamente la migración completa de un perfil.

    Descubre los documentos reales del perfil (reutilizando el inventario
    de 22E), determina su versión efectiva, resuelve las cadenas de
    migración necesarias y transforma todo en memoria antes de escribir
    nada. Sólo entonces stagea los documentos y, al final, los metadatos
    globales, y confirma todo con un único ``commit`` transaccional.

    Con ``CURRENT_SCHEMA_VERSION`` y ``CURRENT_PROFILE_FORMAT_VERSION`` en
    1, ningún perfil productivo necesita migrarse todavía: ``plan`` lo
    detecta y ``migrate`` devuelve sin leer nada más que lo necesario para
    saberlo, sin escribir ni crear nada.
    """

    def __init__(
        self,
        metadata_service: ProfileMetadataService | None = None,
        store: VersionedJsonStore | None = None,
        inventory: ProfileDocumentInventory | None = None,
        profile_format_registry: ProfileFormatMigrationRegistry | None = None,
        profile_format_engine: MigrationEngine | None = None,
        schema_registry: SchemaMigrationRegistry | None = None,
        schema_engine: MigrationEngine | None = None,
        target_format_version: int = CURRENT_PROFILE_FORMAT_VERSION,
        target_schema_version: int = CURRENT_SCHEMA_VERSION,
    ) -> None:
        """Permite sustituir cada colaborador en pruebas con registros sintéticos."""
        self._metadata_service = metadata_service or ProfileMetadataService()
        self._store = store or VersionedJsonStore()
        self._inventory = inventory or ProfileDocumentInventory()
        self._profile_format_registry = (
            profile_format_registry or PRODUCTION_PROFILE_FORMAT_MIGRATIONS
        )
        self._profile_format_engine = (
            profile_format_engine or PROFILE_FORMAT_MIGRATION_ENGINE
        )
        self._schema_registry = schema_registry or PRODUCTION_SCHEMA_MIGRATIONS
        self._schema_engine = schema_engine or SCHEMA_MIGRATION_ENGINE
        self._target_format_version = target_format_version
        self._target_schema_version = target_schema_version

    def plan(self, profile: ProfileLocation) -> ProfileMigrationPlan:
        """Determina qué migraría el perfil, sin modificar nada.

        Falla antes de cualquier efecto si un documento es futuro o
        ilegible (ya lo hace ``VersionedJsonStore.read``) o si falta un
        step en alguna cadena requerida (``resolve_chain`` lo exige aquí,
        durante la planificación, no durante la escritura).
        """
        metadata = self._metadata_service.validate_existing(profile)
        if metadata is None:
            return ProfileMigrationPlan(
                current_profile_format_version=None,
                target_profile_format_version=self._target_format_version,
                needs_profile_format_migration=False,
                metadata_schema_current_version=None,
                metadata_schema_target_version=self._target_schema_version,
                needs_metadata_schema_migration=False,
                documents=(),
            )
        metadata_path = self._metadata_service.metadata_path(profile)
        raw_metadata = self._store.read(metadata_path)
        metadata_schema_current = _effective_version_of_validated_document(
            raw_metadata,
            SCHEMA_VERSION_KEY,
        )
        needs_metadata_schema = (
            metadata_schema_current != self._target_schema_version
        )
        if needs_metadata_schema:
            self._schema_registry.for_document_type(
                DocumentType.PROFILE_METADATA,
            ).resolve_chain(metadata_schema_current, self._target_schema_version)
        needs_format = (
            metadata.profile_format_version != self._target_format_version
        )
        if needs_format:
            self._profile_format_registry.resolve_chain(
                metadata.profile_format_version,
                self._target_format_version,
            )
        documents = tuple(
            self._plan_document(document_type, path)
            for document_type, path in self._discover_profile_documents(profile)
        )
        return ProfileMigrationPlan(
            current_profile_format_version=metadata.profile_format_version,
            target_profile_format_version=self._target_format_version,
            needs_profile_format_migration=needs_format,
            metadata_schema_current_version=metadata_schema_current,
            metadata_schema_target_version=self._target_schema_version,
            needs_metadata_schema_migration=needs_metadata_schema,
            documents=documents,
        )

    def migrate(self, profile: ProfileLocation) -> dict[str, Any] | None:
        """Migra el perfil completo si corresponde, de forma atómica.

        Lee y transforma todo en memoria (documentos y metadatos) antes de
        escribir nada. Los documentos que no necesitan migrar nunca se
        tocan, para no generar churn. Los metadatos se stagean siempre al
        final, garantizado por este método y no por disciplina del caller.
        Si no hace falta ninguna migración, no toca el filesystem y
        devuelve ``None``.
        """
        plan = self.plan(profile)
        if not plan.needs_migration:
            return None
        prepared_documents: list[tuple[Path, dict[str, Any]]] = []
        for document_plan in plan.documents:
            if not document_plan.needs_migration:
                continue
            raw = self._store.read(document_plan.path)
            working = _prepare_for_engine(
                raw,
                SCHEMA_VERSION_KEY,
                document_plan.current_schema_version,
            )
            migrated = self._schema_engine.migrate_document(
                working,
                document_plan.current_schema_version,
                document_plan.target_schema_version,
                self._schema_registry.for_document_type(
                    document_plan.document_type,
                ),
            )
            prepared_documents.append((document_plan.path, migrated))

        metadata_path = self._metadata_service.metadata_path(profile)
        metadata_document = self._store.read(metadata_path)
        if plan.needs_metadata_schema_migration:
            working_metadata = _prepare_for_engine(
                metadata_document,
                SCHEMA_VERSION_KEY,
                plan.metadata_schema_current_version,
            )
            metadata_document = self._schema_engine.migrate_document(
                working_metadata,
                plan.metadata_schema_current_version,
                plan.metadata_schema_target_version,
                self._schema_registry.for_document_type(
                    DocumentType.PROFILE_METADATA,
                ),
            )
        if plan.needs_profile_format_migration:
            metadata_document = self._profile_format_engine.migrate_document(
                metadata_document,
                plan.current_profile_format_version,
                plan.target_profile_format_version,
                self._profile_format_registry,
            )

        transaction = ProfileMigrationTransaction(self._store)
        for path, document in prepared_documents:
            transaction.stage(path, document)
        transaction.stage(metadata_path, metadata_document)
        transaction.commit()
        return metadata_document

    def migrate_file(self, document_type: DocumentType, path: Path) -> dict[str, Any]:
        """Migra en memoria un documento de archivo a la versión vigente.

        Expone la capacidad del motor por archivo, sin persistir nada: no
        es un atajo de escritura individual. ``ProfileMigrationService``
        nunca lo usa dentro de ``migrate`` para no romper la preparación
        completa en memoria antes de escribir.
        """
        document = self._store.read(path)
        from_version = _effective_version_of_validated_document(
            document,
            SCHEMA_VERSION_KEY,
        )
        working = _prepare_for_engine(document, SCHEMA_VERSION_KEY, from_version)
        registry = self._schema_registry.for_document_type(document_type)
        return self._schema_engine.migrate_document(
            working,
            from_version,
            self._target_schema_version,
            registry,
        )

    def _plan_document(
        self,
        document_type: DocumentType,
        path: Path,
    ) -> DocumentMigrationPlan:
        """Calcula el plan de un documento sin transformarlo todavía."""
        raw = self._store.read(path)
        current = _effective_version_of_validated_document(raw, SCHEMA_VERSION_KEY)
        needs = current != self._target_schema_version
        if needs:
            self._schema_registry.for_document_type(document_type).resolve_chain(
                current,
                self._target_schema_version,
            )
        return DocumentMigrationPlan(
            document_type=document_type,
            path=path,
            current_schema_version=current,
            target_schema_version=self._target_schema_version,
            needs_migration=needs,
        )

    def _discover_profile_documents(
        self,
        profile: ProfileLocation,
    ) -> list[tuple[DocumentType, Path]]:
        """Enumera, en orden estable, los documentos propios del perfil.

        Deliberadamente no incluye ``profiles_catalog`` ni
        ``active_profile``: son globales al sistema, no al perfil.
        """
        discovered: list[tuple[DocumentType, Path]] = []
        for path in self._inventory.existing_documents(profile):
            document_type = _document_type_for(path)
            if document_type is not None:
                discovered.append((document_type, path))
        return discovered
