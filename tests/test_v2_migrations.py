"""Pruebas del motor puro de migraciones secuenciales (Etapa 22F).

``core.migrations`` no conoce archivos ni perfiles: transforma documentos
en memoria, paso a paso, N -> N+1, usando registros y versiones sintéticas.
Las versiones productivas (``CURRENT_SCHEMA_VERSION`` y
``CURRENT_PROFILE_FORMAT_VERSION``) siguen en 1 y no se tocan aquí.
"""

from __future__ import annotations

from typing import Any

import pytest

from core.migrations import (
    PROFILE_FORMAT_MIGRATION_ENGINE,
    PRODUCTION_PROFILE_FORMAT_MIGRATIONS,
    PRODUCTION_SCHEMA_MIGRATIONS,
    SCHEMA_MIGRATION_ENGINE,
    DocumentType,
    DowngradeNotSupportedError,
    DuplicateMigrationStepError,
    InvalidMigrationStepError,
    MigrationEngine,
    MigrationError,
    MigrationExecutionError,
    MigrationRegistry,
    MigrationStep,
    MigrationVersionMismatchError,
    MissingMigrationStepError,
    ProfileFormatMigrationRegistry,
    SchemaMigrationRegistry,
)
from core.profile_metadata import CURRENT_PROFILE_FORMAT_VERSION
from core.schema_versioning import CURRENT_SCHEMA_VERSION, SchemaVersionPolicy


def step(from_version: int, to_version: int, key: str = "value") -> MigrationStep:
    """Crea un step sintético que suma un campo marcador y fija la versión."""

    def migrate(document: dict[str, Any]) -> dict[str, Any]:
        return {**document, key: f"{key}_{to_version}", "version": to_version}

    return MigrationStep(from_version, to_version, migrate)


# ----------------------------------------------------------------------
# Registro: sección 28.
# ----------------------------------------------------------------------


def test_empty_registry_requires_step_for_any_advance() -> None:
    registry = MigrationRegistry()
    with pytest.raises(MissingMigrationStepError):
        registry.resolve_chain(1, 2)


def test_registry_accepts_step_one_to_two() -> None:
    registry = MigrationRegistry()
    one_two = step(1, 2)
    registry.register(one_two)
    assert registry.resolve_chain(1, 2) == [one_two]


def test_registry_accepts_step_two_to_three() -> None:
    registry = MigrationRegistry()
    registry.register(step(1, 2))
    two_three = step(2, 3)
    registry.register(two_three)
    assert registry.resolve_chain(2, 3) == [two_three]


def test_registry_rejects_duplicate_step_for_same_origin() -> None:
    registry = MigrationRegistry()
    registry.register(step(1, 2))
    with pytest.raises(DuplicateMigrationStepError):
        registry.register(step(1, 2))


def test_step_rejects_a_jump_registered_as_a_single_step() -> None:
    with pytest.raises(InvalidMigrationStepError):
        MigrationStep(1, 3, lambda document: document)


@pytest.mark.parametrize("from_version", [0, -1])
def test_step_rejects_non_positive_origin(from_version: int) -> None:
    with pytest.raises(InvalidMigrationStepError):
        MigrationStep(from_version, from_version + 1, lambda document: document)


@pytest.mark.parametrize("to_version", [0, -1, 1])
def test_step_rejects_non_advancing_destination(to_version: int) -> None:
    with pytest.raises(InvalidMigrationStepError):
        MigrationStep(1, to_version, lambda document: document)


def test_registry_detects_a_gap_between_one_and_three() -> None:
    registry = MigrationRegistry()
    registry.register(step(1, 2))
    # falta 2 -> 3
    with pytest.raises(MissingMigrationStepError):
        registry.resolve_chain(1, 3)


def test_registry_resolves_chain_one_to_two_to_three() -> None:
    registry = MigrationRegistry()
    one_two = step(1, 2)
    two_three = step(2, 3)
    registry.register(one_two)
    registry.register(two_three)
    assert registry.resolve_chain(1, 3) == [one_two, two_three]


def test_registry_resolves_partial_chain_from_two_to_three() -> None:
    registry = MigrationRegistry()
    registry.register(step(1, 2))
    two_three = step(2, 3)
    registry.register(two_three)
    assert registry.resolve_chain(2, 3) == [two_three]


def test_registry_from_equals_target_resolves_to_no_steps() -> None:
    registry = MigrationRegistry()
    registry.register(step(1, 2))
    assert registry.resolve_chain(2, 2) == []


def test_registry_rejects_downgrade() -> None:
    registry = MigrationRegistry()
    registry.register(step(1, 2))
    registry.register(step(2, 3))
    with pytest.raises(DowngradeNotSupportedError):
        registry.resolve_chain(3, 2)


def test_registry_reports_the_missing_step_precisely() -> None:
    registry = MigrationRegistry()
    registry.register(step(1, 2))
    registry.register(step(3, 4))
    with pytest.raises(MissingMigrationStepError) as excinfo:
        registry.resolve_chain(1, 4)
    assert excinfo.value.missing_from_version == 2
    assert excinfo.value.target_version == 4


# ----------------------------------------------------------------------
# Motor: sección 29.
# ----------------------------------------------------------------------


def test_engine_migrates_one_to_three_executing_each_step_once() -> None:
    registry = MigrationRegistry()
    calls: list[int] = []

    def make_step(from_version: int, to_version: int) -> MigrationStep:
        def migrate(document: dict[str, Any]) -> dict[str, Any]:
            calls.append(from_version)
            return {**document, "version": to_version}

        return MigrationStep(from_version, to_version, migrate)

    registry.register(make_step(1, 2))
    registry.register(make_step(2, 3))
    engine = MigrationEngine("version")
    document = {"version": 1, "value": "abc"}

    result = engine.migrate_document(document, 1, 3, registry)

    assert calls == [1, 2]
    assert result["version"] == 3
    assert document == {"version": 1, "value": "abc"}


def test_engine_does_not_mutate_the_original_document() -> None:
    registry = MigrationRegistry()
    registry.register(step(1, 2))
    engine = MigrationEngine("version")
    document = {"version": 1, "value": "abc"}
    frozen_copy = dict(document)

    engine.migrate_document(document, 1, 2, registry)

    assert document == frozen_copy


def test_engine_second_migration_to_the_same_version_needs_no_steps() -> None:
    registry = MigrationRegistry()
    calls: list[int] = []

    def migrate(document: dict[str, Any]) -> dict[str, Any]:
        calls.append(1)
        return {**document, "version": 2}

    registry.register(MigrationStep(1, 2, migrate))
    engine = MigrationEngine("version")
    once = engine.migrate_document({"version": 1}, 1, 2, registry)
    assert calls == [1]

    twice = engine.migrate_document(once, 2, 2, registry)

    assert calls == [1]
    assert twice == once


def test_engine_rejects_downgrade() -> None:
    registry = MigrationRegistry()
    engine = MigrationEngine("version")
    with pytest.raises(DowngradeNotSupportedError):
        engine.migrate_document({"version": 2}, 2, 1, registry)


# ----------------------------------------------------------------------
# Steps defectuosos: sección 30.
# ----------------------------------------------------------------------


def test_engine_rejects_step_returning_none() -> None:
    registry = MigrationRegistry()
    registry.register(MigrationStep(1, 2, lambda document: None))
    engine = MigrationEngine("version")
    with pytest.raises(MigrationExecutionError):
        engine.migrate_document({"version": 1}, 1, 2, registry)


def test_engine_rejects_step_returning_a_list() -> None:
    registry = MigrationRegistry()
    registry.register(MigrationStep(1, 2, lambda document: [document]))
    engine = MigrationEngine("version")
    with pytest.raises(MigrationExecutionError):
        engine.migrate_document({"version": 1}, 1, 2, registry)


def test_engine_wraps_an_exception_raised_by_a_step() -> None:
    def failing(document: dict[str, Any]) -> dict[str, Any]:
        raise RuntimeError("boom")

    registry = MigrationRegistry()
    registry.register(MigrationStep(1, 2, failing))
    engine = MigrationEngine("version")
    with pytest.raises(MigrationExecutionError) as excinfo:
        engine.migrate_document({"version": 1}, 1, 2, registry)
    assert isinstance(excinfo.value.__cause__, RuntimeError)


def test_engine_rejects_step_returning_a_stale_version() -> None:
    registry = MigrationRegistry()
    registry.register(MigrationStep(1, 2, lambda document: {**document, "version": 1}))
    engine = MigrationEngine("version")
    with pytest.raises(MigrationExecutionError):
        engine.migrate_document({"version": 1}, 1, 2, registry)


def test_engine_rejects_step_jumping_a_version() -> None:
    registry = MigrationRegistry()
    registry.register(MigrationStep(1, 2, lambda document: {**document, "version": 3}))
    engine = MigrationEngine("version")
    with pytest.raises(MigrationExecutionError):
        engine.migrate_document({"version": 1}, 1, 2, registry)


def test_engine_rejects_step_that_drops_the_version_key() -> None:
    def migrate(document: dict[str, Any]) -> dict[str, Any]:
        result = dict(document)
        result.pop("version", None)
        return result

    registry = MigrationRegistry()
    registry.register(MigrationStep(1, 2, migrate))
    engine = MigrationEngine("version")
    with pytest.raises(MigrationExecutionError):
        engine.migrate_document({"version": 1}, 1, 2, registry)


def test_engine_rejects_document_that_is_not_an_object() -> None:
    registry = MigrationRegistry()
    engine = MigrationEngine("version")
    with pytest.raises(MigrationExecutionError):
        engine.migrate_document([], 1, 1, registry)  # type: ignore[arg-type]


# ----------------------------------------------------------------------
# Error en step intermedio: sección 31.
# ----------------------------------------------------------------------


def test_engine_a_failing_second_step_leaves_no_trace_and_input_intact() -> None:
    calls: list[int] = []

    def pass_step(document: dict[str, Any]) -> dict[str, Any]:
        calls.append(1)
        return {**document, "version": 2}

    def fail_step(document: dict[str, Any]) -> dict[str, Any]:
        calls.append(2)
        raise RuntimeError("falla a mitad de la cadena")

    registry = MigrationRegistry()
    registry.register(MigrationStep(1, 2, pass_step))
    registry.register(MigrationStep(2, 3, fail_step))
    engine = MigrationEngine("version")
    document = {"version": 1, "value": "abc"}
    frozen_copy = dict(document)

    with pytest.raises(MigrationExecutionError):
        engine.migrate_document(document, 1, 3, registry)

    assert calls == [1, 2]
    assert document == frozen_copy


# ----------------------------------------------------------------------
# Motor de profile_format: sección 32.
# ----------------------------------------------------------------------


def test_profile_format_registry_is_a_distinct_type() -> None:
    registry = ProfileFormatMigrationRegistry()
    assert isinstance(registry, MigrationRegistry)
    assert not isinstance(MigrationRegistry(), ProfileFormatMigrationRegistry)


def test_profile_format_engine_resolves_sequence_and_rejects_gap_future_downgrade() -> None:
    registry = ProfileFormatMigrationRegistry()
    registry.register(
        MigrationStep(
            1,
            2,
            lambda document: {**document, "profile_format_version": 2},
        ),
    )
    engine = MigrationEngine("profile_format_version")
    metadata = {"profile_format_version": 1, "profile_slug": "hogar"}

    migrated = engine.migrate_document(metadata, 1, 2, registry)
    assert migrated["profile_format_version"] == 2

    with pytest.raises(MissingMigrationStepError):
        registry.resolve_chain(1, 3)

    with pytest.raises(DowngradeNotSupportedError):
        engine.migrate_document({"profile_format_version": 2}, 2, 1, registry)


def test_profile_format_metadata_only_updates_after_full_success(tmp_path) -> None:
    """La capa pura no escribe nada: sólo demuestra el contrato en memoria."""
    registry = ProfileFormatMigrationRegistry()

    def fail_on_second(document: dict[str, Any]) -> dict[str, Any]:
        raise RuntimeError("falla antes de completar la migración")

    registry.register(
        MigrationStep(
            1,
            2,
            lambda document: {**document, "profile_format_version": 2},
        ),
    )
    registry.register(MigrationStep(2, 3, fail_on_second))
    engine = MigrationEngine("profile_format_version")
    metadata = {"profile_format_version": 1, "profile_slug": "hogar"}

    with pytest.raises(MigrationExecutionError):
        engine.migrate_document(metadata, 1, 3, registry)

    assert metadata == {"profile_format_version": 1, "profile_slug": "hogar"}


# ----------------------------------------------------------------------
# Tipos de documento e inventario productivo: secciones 14-15.
# ----------------------------------------------------------------------


def test_document_type_covers_every_productive_family() -> None:
    expected = {
        "monthly_budget",
        "accounts",
        "debts",
        "debt_payments",
        "debt_snapshots",
        "monthly_closures",
        "categories",
        "settings",
        "profiles_catalog",
        "active_profile",
        "profile_metadata",
    }
    assert {member.value for member in DocumentType} == expected


def test_schema_migration_registry_keeps_families_isolated() -> None:
    registry = SchemaMigrationRegistry()
    registry.register(DocumentType.ACCOUNTS, step(1, 2))

    assert registry.for_document_type(DocumentType.ACCOUNTS).resolve_chain(1, 2)
    # deudas no tiene steps registrados: ningún step de cuentas se le aplica.
    assert registry.for_document_type(DocumentType.DEBTS).resolve_chain(1, 1) == []
    with pytest.raises(MissingMigrationStepError):
        registry.for_document_type(DocumentType.DEBTS).resolve_chain(1, 2)


# ----------------------------------------------------------------------
# Registros productivos: cero efecto mientras current == 1.
# ----------------------------------------------------------------------


def test_production_registries_are_empty() -> None:
    for document_type in DocumentType:
        registry = PRODUCTION_SCHEMA_MIGRATIONS.for_document_type(document_type)
        assert registry.resolve_chain(
            CURRENT_SCHEMA_VERSION,
            CURRENT_SCHEMA_VERSION,
        ) == []
    assert PRODUCTION_PROFILE_FORMAT_MIGRATIONS.resolve_chain(
        CURRENT_PROFILE_FORMAT_VERSION,
        CURRENT_PROFILE_FORMAT_VERSION,
    ) == []


def test_production_engines_use_the_expected_version_keys() -> None:
    document = {"schema_version": CURRENT_SCHEMA_VERSION, "value": "abc"}
    result = SCHEMA_MIGRATION_ENGINE.migrate_document(
        document,
        CURRENT_SCHEMA_VERSION,
        CURRENT_SCHEMA_VERSION,
        PRODUCTION_SCHEMA_MIGRATIONS.for_document_type(DocumentType.ACCOUNTS),
    )
    assert result == document

    metadata = {
        "profile_format_version": CURRENT_PROFILE_FORMAT_VERSION,
        "profile_slug": "hogar",
    }
    result = PROFILE_FORMAT_MIGRATION_ENGINE.migrate_document(
        metadata,
        CURRENT_PROFILE_FORMAT_VERSION,
        CURRENT_PROFILE_FORMAT_VERSION,
        PRODUCTION_PROFILE_FORMAT_MIGRATIONS,
    )
    assert result == metadata


def test_migration_errors_are_not_value_errors() -> None:
    for error_type in (
        MigrationError,
        InvalidMigrationStepError,
        DuplicateMigrationStepError,
        MissingMigrationStepError,
        DowngradeNotSupportedError,
        MigrationExecutionError,
        MigrationVersionMismatchError,
    ):
        assert not issubclass(error_type, ValueError)


# ----------------------------------------------------------------------
# Reparación focal: vincular from_version con la versión real del
# documento (sección 7 de la misión de reparación).
# ----------------------------------------------------------------------


def test_mismatch_a_document_declares_two_but_caller_says_one() -> None:
    registry = MigrationRegistry()
    calls: list[int] = []

    def make_step(from_version: int, to_version: int) -> MigrationStep:
        def migrate(document: dict[str, Any]) -> dict[str, Any]:
            calls.append(from_version)
            return {**document, "version": to_version}

        return MigrationStep(from_version, to_version, migrate)

    registry.register(make_step(1, 2))
    registry.register(make_step(2, 3))
    engine = MigrationEngine("version")
    document = {"version": 2, "value": "ya migrado"}

    with pytest.raises(MigrationVersionMismatchError) as excinfo:
        engine.migrate_document(document, 1, 3, registry)

    assert calls == []
    assert excinfo.value.expected_version == 1
    assert excinfo.value.observed_version == 2
    assert document == {"version": 2, "value": "ya migrado"}


def test_mismatch_b_document_declares_one_but_caller_says_two() -> None:
    engine = MigrationEngine("version")
    registry = MigrationRegistry()
    registry.register(MigrationStep(2, 3, lambda d: {**d, "version": 3}))

    with pytest.raises(MigrationVersionMismatchError):
        engine.migrate_document({"version": 1}, 2, 3, registry)


def test_mismatch_c_document_declares_a_bool_as_version() -> None:
    engine = MigrationEngine("version")
    registry = MigrationRegistry()

    with pytest.raises(MigrationVersionMismatchError):
        engine.migrate_document({"version": True}, 1, 1, registry)


def test_mismatch_d_document_without_version_key_entering_the_engine_directly() -> None:
    engine = MigrationEngine("version")
    registry = MigrationRegistry()

    with pytest.raises(MigrationVersionMismatchError):
        engine.migrate_document({"value": "sin version"}, 1, 1, registry)


def test_mismatch_e_legacy_document_via_schema_version_policy_integration() -> None:
    """La traducción legacy-ausente -> v1 sigue perteneciendo a 22D.

    La capa integradora materializa una copia de trabajo con la versión
    efectiva antes de entrar al engine; el motor no adivina nada.
    """
    legacy_document = {"value": "sin version declarada"}
    effective = SchemaVersionPolicy().effective_version(legacy_document)
    assert effective == 1
    working_copy = {**legacy_document, "schema_version": effective}

    engine = MigrationEngine("schema_version")
    registry = MigrationRegistry()
    registry.register(MigrationStep(1, 2, lambda d: {**d, "schema_version": 2}))

    result = engine.migrate_document(working_copy, effective, 2, registry)

    assert result["schema_version"] == 2
    # el documento legacy original nunca fue tocado.
    assert legacy_document == {"value": "sin version declarada"}


def test_mismatch_f_from_version_as_bool_is_rejected() -> None:
    engine = MigrationEngine("version")
    registry = MigrationRegistry()

    with pytest.raises(MigrationVersionMismatchError):
        engine.migrate_document({"version": 1}, True, 2, registry)


def test_mismatch_g_target_version_as_bool_is_rejected() -> None:
    engine = MigrationEngine("version")
    registry = MigrationRegistry()

    with pytest.raises(MigrationVersionMismatchError):
        engine.migrate_document({"version": 1}, 1, True, registry)


def test_mismatch_leaves_the_document_entirely_untouched() -> None:
    engine = MigrationEngine("version")
    registry = MigrationRegistry()
    document = {"version": 5, "value": "abc"}
    frozen_copy = dict(document)

    with pytest.raises(MigrationVersionMismatchError):
        engine.migrate_document(document, 1, 2, registry)

    assert document == frozen_copy
