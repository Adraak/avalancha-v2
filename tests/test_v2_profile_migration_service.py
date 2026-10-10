"""Pruebas de la orquestación y transacción de migraciones (Etapa 22F).

``ProfileMigrationTransaction`` confirma en bloque varias escrituras de un
mismo perfil: si una falla a mitad, las ya confirmadas vuelven a sus bytes
previos. ``ProfileMigrationService`` decide si un perfil necesita migrarse
y, si corresponde, transforma todo en memoria antes de escribir nada, con
los metadatos siempre al final. Con las versiones productivas actuales en
1, ambos deben no tener ningún efecto sobre un perfil normal.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest

from core.migrations import (
    DocumentType,
    MigrationExecutionError,
    MigrationStep,
    ProfileFormatMigrationRegistry,
    SchemaMigrationRegistry,
    MigrationEngine,
)
from core.profile_metadata import (
    APP_VERSION_KEY,
    CURRENT_PROFILE_FORMAT_VERSION,
    PROFILE_FORMAT_VERSION_KEY,
    PROFILE_METADATA_FILE_NAME,
    PROFILE_NAME_KEY,
    PROFILE_SLUG_KEY,
)
from core.schema_versioning import SCHEMA_VERSION_KEY, SchemaVersionPolicy
from core.versioned_json_store import VersionedJsonStore
from services.profile_metadata_service import ProfileMetadataService
from services.profile_migration_service import (
    ProfileMigrationPlan,
    ProfileMigrationService,
    ProfileMigrationTransaction,
)


class _FakeProfile:
    """Perfil mínimo que satisface ``ProfileLocation`` para estas pruebas."""

    def __init__(self, root: Path, slug: str = "hogar_ficticio") -> None:
        self.id = slug
        self.nombre = "Hogar Ficticio"
        self.raiz = root / "perfiles" / slug
        self.data_dir = self.raiz / "data"
        self.config_dir = self.raiz / "config"


def make_profile(tmp_path: Path, slug: str = "hogar_ficticio") -> _FakeProfile:
    profile = _FakeProfile(tmp_path, slug)
    profile.raiz.mkdir(parents=True)
    profile.data_dir.mkdir()
    profile.config_dir.mkdir()
    return profile


def dump_json(path: Path, document: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")


def metadata_document(
    slug: str,
    profile_format_version: int = CURRENT_PROFILE_FORMAT_VERSION,
    schema_version: int = 1,
) -> dict[str, Any]:
    return {
        SCHEMA_VERSION_KEY: schema_version,
        PROFILE_FORMAT_VERSION_KEY: profile_format_version,
        PROFILE_SLUG_KEY: slug,
        PROFILE_NAME_KEY: "Hogar Ficticio",
        APP_VERSION_KEY: "0.1.0",
    }


class ReplaceSpy:
    """Envuelve ``os.replace``: registra destinos y puede fallar en algunos."""

    def __init__(self) -> None:
        self.targets: list[str] = []
        self.fail_on: set[str] = set()
        self._real = os.replace

    def __call__(self, source: Any, target: Any) -> None:
        name = Path(target).name
        self.targets.append(name)
        if name in self.fail_on:
            raise OSError("reemplazo bloqueado por la prueba")
        self._real(source, target)


# ----------------------------------------------------------------------
# ProfileMigrationTransaction: secciones 19-21, 33-34.
# ----------------------------------------------------------------------


def test_transaction_commits_every_staged_write(tmp_path: Path) -> None:
    profile = make_profile(tmp_path)
    accounts = profile.data_dir / "cuentas.json"
    debts = profile.data_dir / "deudas.json"
    metadata = profile.raiz / PROFILE_METADATA_FILE_NAME
    dump_json(accounts, {SCHEMA_VERSION_KEY: 1, "value": "old"})
    dump_json(debts, {SCHEMA_VERSION_KEY: 1, "value": "old"})
    dump_json(metadata, metadata_document(profile.id))

    transaction = ProfileMigrationTransaction()
    transaction.stage(accounts, {SCHEMA_VERSION_KEY: 1, "value": "new"})
    transaction.stage(debts, {SCHEMA_VERSION_KEY: 1, "value": "new"})
    transaction.stage(metadata, metadata_document(profile.id))
    transaction.commit()

    assert json.loads(accounts.read_text())["value"] == "new"
    assert json.loads(debts.read_text())["value"] == "new"


def test_transaction_rolls_back_every_file_when_a_later_write_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    profile = make_profile(tmp_path)
    accounts = profile.data_dir / "cuentas.json"
    debts = profile.data_dir / "deudas.json"
    budget = profile.data_dir / "presupuesto_2026-03.json"
    metadata = profile.raiz / PROFILE_METADATA_FILE_NAME
    dump_json(accounts, {SCHEMA_VERSION_KEY: 1, "value": "old"})
    dump_json(debts, {SCHEMA_VERSION_KEY: 1, "value": "old"})
    dump_json(budget, {SCHEMA_VERSION_KEY: 1, "value": "old"})
    dump_json(metadata, metadata_document(profile.id))
    before = {
        path.name: path.read_bytes()
        for path in (accounts, debts, budget, metadata)
    }

    spy = ReplaceSpy()
    spy.fail_on.add("deudas.json")
    monkeypatch.setattr(os, "replace", spy)

    transaction = ProfileMigrationTransaction()
    transaction.stage(accounts, {SCHEMA_VERSION_KEY: 1, "value": "new"})
    transaction.stage(debts, {SCHEMA_VERSION_KEY: 1, "value": "new"})
    transaction.stage(budget, {SCHEMA_VERSION_KEY: 1, "value": "new"})
    transaction.stage(metadata, metadata_document(profile.id))

    with pytest.raises(OSError):
        transaction.commit()

    after = {
        path.name: path.read_bytes()
        for path in (accounts, debts, budget, metadata)
    }
    assert after == before
    # presupuesto y metadata nunca llegaron a intentarse: fallaron antes.
    assert "presupuesto_2026-03.json" not in spy.targets
    assert PROFILE_METADATA_FILE_NAME not in spy.targets


def test_transaction_removes_a_file_it_created_if_a_later_write_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    profile = make_profile(tmp_path)
    new_file = profile.data_dir / "categorias.json"
    existing = profile.data_dir / "cuentas.json"
    dump_json(existing, {SCHEMA_VERSION_KEY: 1, "value": "old"})
    assert not new_file.exists()

    spy = ReplaceSpy()
    spy.fail_on.add("cuentas.json")
    monkeypatch.setattr(os, "replace", spy)

    transaction = ProfileMigrationTransaction()
    transaction.stage(new_file, {SCHEMA_VERSION_KEY: 1, "value": "created"})
    transaction.stage(existing, {SCHEMA_VERSION_KEY: 1, "value": "new"})

    with pytest.raises(OSError):
        transaction.commit()

    assert not new_file.exists()
    assert json.loads(existing.read_text())["value"] == "old"


def test_transaction_rolls_back_if_a_middle_write_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Primero confirma A, falla en B: A debe volver exactamente a su bytes previo."""
    profile = make_profile(tmp_path)
    first = profile.data_dir / "cuentas.json"
    second = profile.data_dir / "deudas.json"
    dump_json(first, {SCHEMA_VERSION_KEY: 1, "value": "old"})
    dump_json(second, {SCHEMA_VERSION_KEY: 1, "value": "old"})
    first_before = first.read_bytes()

    spy = ReplaceSpy()
    spy.fail_on.add("deudas.json")
    monkeypatch.setattr(os, "replace", spy)

    transaction = ProfileMigrationTransaction()
    transaction.stage(first, {SCHEMA_VERSION_KEY: 1, "value": "new"})
    transaction.stage(second, {SCHEMA_VERSION_KEY: 1, "value": "new"})

    with pytest.raises(OSError):
        transaction.commit()

    assert "cuentas.json" in spy.targets
    assert first.read_bytes() == first_before


# ----------------------------------------------------------------------
# ProfileMigrationService: secciones 18, 22, 23, 43.
# ----------------------------------------------------------------------


def test_plan_reports_no_migration_needed_when_formats_match(tmp_path: Path) -> None:
    profile = make_profile(tmp_path)
    dump_json(
        profile.raiz / PROFILE_METADATA_FILE_NAME,
        metadata_document(profile.id, CURRENT_PROFILE_FORMAT_VERSION),
    )
    service = ProfileMigrationService()

    plan = service.plan(profile)

    assert plan == ProfileMigrationPlan(
        current_profile_format_version=CURRENT_PROFILE_FORMAT_VERSION,
        target_profile_format_version=CURRENT_PROFILE_FORMAT_VERSION,
        needs_profile_format_migration=False,
        metadata_schema_current_version=1,
        metadata_schema_target_version=1,
        needs_metadata_schema_migration=False,
        documents=(),
    )
    assert plan.needs_migration is False


def test_plan_reports_no_migration_when_metadata_is_absent(tmp_path: Path) -> None:
    profile = make_profile(tmp_path)
    service = ProfileMigrationService()

    plan = service.plan(profile)

    assert plan.needs_migration is False
    assert plan.current_profile_format_version is None


def test_current_format_version_causes_zero_effect_on_disk(tmp_path: Path) -> None:
    """Invariante crítico de 22F: con current == target no se toca nada."""
    profile = make_profile(tmp_path)
    metadata_path = profile.raiz / PROFILE_METADATA_FILE_NAME
    dump_json(metadata_path, metadata_document(profile.id))
    before = metadata_path.read_bytes()
    before_mtime = metadata_path.stat().st_mtime_ns

    service = ProfileMigrationService()
    result = service.migrate(profile)

    assert result is None
    assert metadata_path.read_bytes() == before
    assert metadata_path.stat().st_mtime_ns == before_mtime


def test_migrate_runs_registered_step_and_updates_metadata_last(
    tmp_path: Path,
) -> None:
    profile = make_profile(tmp_path)
    metadata_path = profile.raiz / PROFILE_METADATA_FILE_NAME
    dump_json(metadata_path, metadata_document(profile.id, 1))

    registry = ProfileFormatMigrationRegistry()
    registry.register(
        MigrationStep(
            1,
            2,
            lambda document: {**document, PROFILE_FORMAT_VERSION_KEY: 2},
        ),
    )
    service = ProfileMigrationService(
        profile_format_registry=registry,
        target_format_version=2,
    )

    result = service.migrate(profile)

    assert result[PROFILE_FORMAT_VERSION_KEY] == 2
    on_disk = json.loads(metadata_path.read_text())
    assert on_disk[PROFILE_FORMAT_VERSION_KEY] == 2
    assert on_disk[PROFILE_SLUG_KEY] == profile.id


def test_migrate_does_not_update_metadata_when_the_step_fails(
    tmp_path: Path,
) -> None:
    profile = make_profile(tmp_path)
    metadata_path = profile.raiz / PROFILE_METADATA_FILE_NAME
    original = metadata_document(profile.id, 1)
    dump_json(metadata_path, original)
    before = metadata_path.read_bytes()

    def failing(document: dict[str, Any]) -> dict[str, Any]:
        raise RuntimeError("transformación de migración falló")

    registry = ProfileFormatMigrationRegistry()
    registry.register(MigrationStep(1, 2, failing))
    service = ProfileMigrationService(
        profile_format_registry=registry,
        target_format_version=2,
    )

    with pytest.raises(MigrationExecutionError):
        service.migrate(profile)

    assert metadata_path.read_bytes() == before


def test_migrate_raises_when_no_step_bridges_to_target(tmp_path: Path) -> None:
    profile = make_profile(tmp_path)
    dump_json(
        profile.raiz / PROFILE_METADATA_FILE_NAME,
        metadata_document(profile.id, 1),
    )
    service = ProfileMigrationService(
        profile_format_registry=ProfileFormatMigrationRegistry(),
        target_format_version=2,
    )

    with pytest.raises(Exception):
        service.migrate(profile)


# ----------------------------------------------------------------------
# Orquestador multiarchivo REAL: secciones 27-31 de la reparación.
# Todo pasa por ProfileMigrationService.migrate(profile); ningún test
# instancia ProfileMigrationTransaction manualmente.
# ----------------------------------------------------------------------


def _store_with_synthetic_current_schema(version: int) -> VersionedJsonStore:
    """Permite que el store escriba un schema_version sintético en tests.

    ``VersionedJsonStore.write`` siempre revalida contra el techo productivo
    real (``CURRENT_SCHEMA_VERSION`` = 1): no se toca esa constante ni el
    módulo de 22D, sólo se inyecta una ``SchemaVersionPolicy`` de instancia
    con un techo distinto, como permite el propio constructor del store.
    """
    policy = SchemaVersionPolicy()
    policy.CURRENT_VERSION = version
    return VersionedJsonStore(policy=policy)


def _multidoc_services(target_schema: int = 2, target_format: int = 2) -> ProfileMigrationService:
    schema_registry = SchemaMigrationRegistry()
    for document_type in (
        DocumentType.MONTHLY_BUDGET,
        DocumentType.ACCOUNTS,
        DocumentType.DEBTS,
        DocumentType.PROFILE_METADATA,
    ):
        schema_registry.register(
            document_type,
            MigrationStep(
                1,
                2,
                lambda d: {**d, SCHEMA_VERSION_KEY: 2, "value": "new"},
            ),
        )
    format_registry = ProfileFormatMigrationRegistry()
    format_registry.register(
        MigrationStep(1, 2, lambda d: {**d, PROFILE_FORMAT_VERSION_KEY: 2}),
    )
    return ProfileMigrationService(
        store=_store_with_synthetic_current_schema(target_schema),
        schema_registry=schema_registry,
        profile_format_registry=format_registry,
        target_schema_version=target_schema,
        target_format_version=target_format,
    )


def _make_full_profile(tmp_path: Path) -> tuple[Any, dict[str, Path]]:
    profile = make_profile(tmp_path)
    paths = {
        "budget": profile.data_dir / "presupuesto_2026-03.json",
        "accounts": profile.data_dir / "cuentas.json",
        "debts": profile.data_dir / "deudas.json",
        "metadata": profile.raiz / PROFILE_METADATA_FILE_NAME,
    }
    dump_json(paths["budget"], {SCHEMA_VERSION_KEY: 1, "value": "old"})
    dump_json(paths["accounts"], {SCHEMA_VERSION_KEY: 1, "value": "old"})
    dump_json(paths["debts"], {SCHEMA_VERSION_KEY: 1, "value": "old"})
    dump_json(paths["metadata"], metadata_document(profile.id, 1))
    return profile, paths


def test_orchestrator_success_migrates_every_document_and_metadata_last(
    tmp_path: Path,
) -> None:
    profile, paths = _make_full_profile(tmp_path)
    service = _multidoc_services()

    result = service.migrate(profile)

    assert json.loads(paths["budget"].read_text())["value"] == "new"
    assert json.loads(paths["accounts"].read_text())["value"] == "new"
    assert json.loads(paths["debts"].read_text())["value"] == "new"
    on_disk_metadata = json.loads(paths["metadata"].read_text())
    assert on_disk_metadata[PROFILE_FORMAT_VERSION_KEY] == 2
    assert result[PROFILE_FORMAT_VERSION_KEY] == 2


def test_orchestrator_failing_transformation_leaves_everything_untouched(
    tmp_path: Path,
) -> None:
    profile, paths = _make_full_profile(tmp_path)
    before = {name: path.read_bytes() for name, path in paths.items()}

    schema_registry = SchemaMigrationRegistry()
    schema_registry.register(DocumentType.MONTHLY_BUDGET, MigrationStep(1, 2, lambda d: {**d, SCHEMA_VERSION_KEY: 2}))
    schema_registry.register(DocumentType.ACCOUNTS, MigrationStep(1, 2, lambda d: {**d, SCHEMA_VERSION_KEY: 2}))

    def failing(document: dict[str, Any]) -> dict[str, Any]:
        raise RuntimeError("transformación de deudas falló")

    schema_registry.register(DocumentType.DEBTS, MigrationStep(1, 2, failing))
    schema_registry.register(
        DocumentType.PROFILE_METADATA,
        MigrationStep(1, 2, lambda d: {**d, SCHEMA_VERSION_KEY: 2}),
    )
    service = ProfileMigrationService(
        store=_store_with_synthetic_current_schema(2),
        schema_registry=schema_registry,
        target_schema_version=2,
    )

    with pytest.raises(MigrationExecutionError):
        service.migrate(profile)

    after = {name: path.read_bytes() for name, path in paths.items()}
    assert after == before


def test_orchestrator_fails_before_any_write_on_a_gap(tmp_path: Path) -> None:
    """Un documento requiere 1->3 pero sólo existe 1->2: plan()/migrate() fallan antes de escribir."""
    profile, paths = _make_full_profile(tmp_path)
    before = {name: path.read_bytes() for name, path in paths.items()}

    schema_registry = SchemaMigrationRegistry()
    schema_registry.register(DocumentType.ACCOUNTS, MigrationStep(1, 2, lambda d: {**d, SCHEMA_VERSION_KEY: 2}))
    # falta 2->3 para deudas y presupuesto: target=3 crea un hueco.
    service = ProfileMigrationService(schema_registry=schema_registry, target_schema_version=3)

    with pytest.raises(Exception):
        service.plan(profile)
    with pytest.raises(Exception):
        service.migrate(profile)

    after = {name: path.read_bytes() for name, path in paths.items()}
    assert after == before


def test_orchestrator_write_failure_rolls_back_everything(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    profile, paths = _make_full_profile(tmp_path)
    before = {name: path.read_bytes() for name, path in paths.items()}

    spy = ReplaceSpy()
    spy.fail_on.add("deudas.json")
    monkeypatch.setattr(os, "replace", spy)
    service = _multidoc_services()

    with pytest.raises(OSError):
        service.migrate(profile)

    after = {name: path.read_bytes() for name, path in paths.items()}
    assert after == before
    assert PROFILE_METADATA_FILE_NAME not in spy.targets
    # cero temporales residuales de rollback.
    assert list(profile.raiz.rglob("*.rollback")) == []
    assert list(profile.raiz.rglob("*.tmp")) == []


def test_orchestrator_metadata_is_staged_and_written_last(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """La garantía reside en el orquestador, no en disciplina de un test."""
    profile, paths = _make_full_profile(tmp_path)
    spy = ReplaceSpy()
    monkeypatch.setattr(os, "replace", spy)
    service = _multidoc_services()

    service.migrate(profile)

    assert len(spy.targets) == 4
    assert spy.targets[-1] == PROFILE_METADATA_FILE_NAME
    assert set(spy.targets[:-1]) == {
        "presupuesto_2026-03.json",
        "cuentas.json",
        "deudas.json",
    }


def test_orchestrator_does_not_touch_documents_already_at_target(
    tmp_path: Path,
) -> None:
    """Evitar churn: lo que ya está en destino no se reescribe ni se stagea."""
    profile = make_profile(tmp_path)
    accounts = profile.data_dir / "cuentas.json"
    debts = profile.data_dir / "deudas.json"
    metadata_path = profile.raiz / PROFILE_METADATA_FILE_NAME
    dump_json(accounts, {SCHEMA_VERSION_KEY: 2, "value": "ya migrado"})
    dump_json(debts, {SCHEMA_VERSION_KEY: 1, "value": "old"})
    # metadata ya en destino (schema=2): no debe necesitar step tampoco.
    dump_json(metadata_path, metadata_document(profile.id, 1, schema_version=2))
    accounts_before = accounts.read_bytes()
    accounts_mtime = accounts.stat().st_mtime_ns

    schema_registry = SchemaMigrationRegistry()
    schema_registry.register(DocumentType.DEBTS, MigrationStep(1, 2, lambda d: {**d, SCHEMA_VERSION_KEY: 2}))
    synthetic_store = _store_with_synthetic_current_schema(2)
    service = ProfileMigrationService(
        metadata_service=ProfileMetadataService(store=synthetic_store),
        store=synthetic_store,
        schema_registry=schema_registry,
        target_schema_version=2,
    )

    service.migrate(profile)

    assert accounts.read_bytes() == accounts_before
    assert accounts.stat().st_mtime_ns == accounts_mtime
    assert json.loads(debts.read_text())[SCHEMA_VERSION_KEY] == 2


def test_profile_format_and_schema_axes_are_independent_through_the_orchestrator(
    tmp_path: Path,
) -> None:
    """Migrar un eje no toca el otro, demostrado end-to-end vía el orquestador."""
    profile = make_profile(tmp_path)
    metadata_path = profile.raiz / PROFILE_METADATA_FILE_NAME

    # Escenario 1: sólo existe step de profile_format.
    dump_json(metadata_path, metadata_document(profile.id, 1))
    format_registry = ProfileFormatMigrationRegistry()
    format_registry.register(MigrationStep(1, 2, lambda d: {**d, PROFILE_FORMAT_VERSION_KEY: 2}))
    service = ProfileMigrationService(
        profile_format_registry=format_registry,
        target_format_version=2,
    )
    service.migrate(profile)
    on_disk = json.loads(metadata_path.read_text())
    assert on_disk[PROFILE_FORMAT_VERSION_KEY] == 2
    assert on_disk[SCHEMA_VERSION_KEY] == 1

    # Escenario 2 (perfil nuevo): sólo existe step de schema del propio metadata.
    other_profile = make_profile(tmp_path, slug="otro_ficticio")
    other_metadata = other_profile.raiz / PROFILE_METADATA_FILE_NAME
    dump_json(other_metadata, metadata_document(other_profile.id, 1))
    schema_registry = SchemaMigrationRegistry()
    schema_registry.register(
        DocumentType.PROFILE_METADATA,
        MigrationStep(1, 2, lambda d: {**d, SCHEMA_VERSION_KEY: 2}),
    )
    service_2 = ProfileMigrationService(
        store=_store_with_synthetic_current_schema(2),
        schema_registry=schema_registry,
        target_schema_version=2,
    )
    service_2.migrate(other_profile)
    on_disk_2 = json.loads(other_metadata.read_text())
    assert on_disk_2[SCHEMA_VERSION_KEY] == 2
    assert on_disk_2[PROFILE_FORMAT_VERSION_KEY] == 1


def test_plan_exposes_discovered_documents_and_axes(tmp_path: Path) -> None:
    profile, paths = _make_full_profile(tmp_path)
    service = _multidoc_services()

    plan = service.plan(profile)

    discovered_types = {item.document_type for item in plan.documents}
    assert discovered_types == {
        DocumentType.MONTHLY_BUDGET,
        DocumentType.ACCOUNTS,
        DocumentType.DEBTS,
    }
    assert all(item.needs_migration for item in plan.documents)
    assert plan.needs_profile_format_migration is True
    assert plan.current_profile_format_version == 1
    assert plan.target_profile_format_version == 2
    assert plan.needs_migration is True


def test_plan_never_includes_catalog_or_active_profile(tmp_path: Path) -> None:
    """profiles_catalog y active_profile son globales: no pertenecen al plan de UN perfil."""
    profile, _ = _make_full_profile(tmp_path)
    service = _multidoc_services()

    plan = service.plan(profile)

    discovered_types = {item.document_type for item in plan.documents}
    assert DocumentType.PROFILES_CATALOG not in discovered_types
    assert DocumentType.ACTIVE_PROFILE not in discovered_types


def test_plan_is_read_only_even_when_migration_is_needed(tmp_path: Path) -> None:
    profile, paths = _make_full_profile(tmp_path)
    before = {name: path.read_bytes() for name, path in paths.items()}
    before_mtimes = {name: path.stat().st_mtime_ns for name, path in paths.items()}
    service = _multidoc_services()

    service.plan(profile)

    after = {name: path.read_bytes() for name, path in paths.items()}
    after_mtimes = {name: path.stat().st_mtime_ns for name, path in paths.items()}
    assert after == before
    assert after_mtimes == before_mtimes


# ----------------------------------------------------------------------
# migrate_file: sección 21 de la reparación — no es un atajo de escritura.
# ----------------------------------------------------------------------


def test_migrate_file_runs_the_registered_step_for_its_document_type(
    tmp_path: Path,
) -> None:
    """Demuestra el mecanismo con un destino sintético (2), nunca productivo."""
    path = tmp_path / "cuentas.json"
    dump_json(path, {SCHEMA_VERSION_KEY: 1, "value": "old"})
    schema_registry = SchemaMigrationRegistry()
    schema_registry.register(
        DocumentType.ACCOUNTS,
        MigrationStep(
            1,
            2,
            lambda document: {**document, SCHEMA_VERSION_KEY: 2, "value": "new"},
        ),
    )
    service = ProfileMigrationService(
        schema_registry=schema_registry,
        schema_engine=MigrationEngine(SCHEMA_VERSION_KEY),
        target_schema_version=2,
    )

    result = service.migrate_file(DocumentType.ACCOUNTS, path)

    assert result == {SCHEMA_VERSION_KEY: 2, "value": "new"}
    # migrate_file no persiste: el archivo en disco no cambia.
    assert json.loads(path.read_text())["value"] == "old"


def test_migrate_file_does_not_apply_a_step_registered_for_another_family(
    tmp_path: Path,
) -> None:
    path = tmp_path / "deudas.json"
    dump_json(path, {SCHEMA_VERSION_KEY: 1, "value": "old"})
    schema_registry = SchemaMigrationRegistry()
    schema_registry.register(DocumentType.ACCOUNTS, MigrationStep(1, 2, lambda d: {**d, SCHEMA_VERSION_KEY: 2}))
    service = ProfileMigrationService(schema_registry=schema_registry)

    # deudas (DEBTS) no tiene step propio: con current=1 no hay nada que migrar.
    result = service.migrate_file(DocumentType.DEBTS, path)

    assert result[SCHEMA_VERSION_KEY] == 1


def test_migrate_file_still_fails_closed_on_a_future_file(tmp_path: Path) -> None:
    from core.schema_versioning import CURRENT_SCHEMA_VERSION, UnsupportedSchemaVersionError

    path = tmp_path / "cuentas.json"
    dump_json(path, {SCHEMA_VERSION_KEY: CURRENT_SCHEMA_VERSION + 1, "value": "x"})
    service = ProfileMigrationService()

    with pytest.raises(UnsupportedSchemaVersionError):
        service.migrate_file(DocumentType.ACCOUNTS, path)
