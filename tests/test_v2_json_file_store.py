"""Pruebas del almacén JSON atómico y de su uso en las fronteras productivas.

Etapa 22C: la escritura pasa por un temporal en la carpeta del destino y un
``os.replace``. El formato de los archivos no cambia.

Los fallos se inyectan sólo donde no pueden provocarse de forma determinista
(``os.replace``); el resto usa filesystem temporal real.
"""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Any, Callable

import pytest

from avalancha.storage import BudgetRepository
from core import json_file_store
from core.json_file_store import JsonFileStore
from services.budget_service import BudgetService
from services.category_service import CategoryService
from services.profile_service import ProfileService
from services.settings_service import SettingsService


FIXTURES_ROOT = Path(__file__).resolve().parent / "fixtures" / "schema_v1"
PROFILE_DATA_FILES = (
    "presupuesto_2026-03.json",
    "cuentas.json",
    "deudas.json",
    "debt_payments.json",
    "debt_snapshots.json",
    "monthly_closures.json",
    "categorias.json",
)
SAMPLE = {"texto": "áéí ñ €", "numeros": [3, 1, 2], "anidado": {"b": 1, "a": None}}


class ReplaceFailure(OSError):
    """Error inyectado para simular que os.replace no pudo completarse."""


class ReplaceRecorder:
    """Sustituye os.replace registrando cada intento y fallando si se pide."""

    def __init__(self, *, fail: bool) -> None:
        """Guarda la función real y el modo de operación."""
        self.fail = fail
        self.calls: list[tuple[Path, Path]] = []
        self._real = os.replace

    def __call__(self, source: Any, target: Any) -> None:
        """Registra el intento y lo ejecuta o lo hace fallar."""
        source_path, target_path = Path(source), Path(target)
        assert source_path.is_file()
        self.calls.append((source_path, target_path))
        if self.fail:
            raise ReplaceFailure("reemplazo bloqueado por la prueba")
        self._real(source, target)


def fixture_path(relative: str) -> Path:
    """Devuelve la ruta de un fixture schema_v1."""
    return FIXTURES_ROOT.joinpath(*relative.split("/"))


def load_json(path: Path) -> Any:
    """Carga un archivo JSON del filesystem."""
    return json.loads(path.read_text(encoding="utf-8"))


def leftovers(root: Path) -> list[str]:
    """Lista temporales de escritura que hayan quedado bajo una carpeta."""
    return sorted(
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file() and path.name.endswith(JsonFileStore.TEMP_SUFFIX)
    )


def assert_temporary_next_to_target(
    recorder: ReplaceRecorder,
    target: Path,
) -> None:
    """Comprueba que el único reemplazo usó un temporal junto al destino."""
    assert len(recorder.calls) == 1
    source, destination = recorder.calls[0]
    assert destination == target
    assert source.parent == target.parent
    assert source.name.startswith(f".{target.name}.")
    assert source.name.endswith(JsonFileStore.TEMP_SUFFIX)


def run_with_failing_replace(
    monkeypatch: pytest.MonkeyPatch,
    action: Callable[[], Any],
) -> ReplaceRecorder:
    """Ejecuta una acción con os.replace fallando y exige que se propague."""
    recorder = ReplaceRecorder(fail=True)
    with monkeypatch.context() as patch:
        patch.setattr(json_file_store.os, "replace", recorder)
        with pytest.raises(ReplaceFailure):
            action()
    return recorder


@pytest.fixture()
def store() -> JsonFileStore:
    """Entrega el almacén JSON productivo."""
    return JsonFileStore()


@pytest.fixture()
def data_dir(tmp_path: Path) -> Path:
    """Copia los fixtures financieros a una carpeta temporal de perfil."""
    target = tmp_path / "perfil_ficticio" / "datos"
    target.mkdir(parents=True)
    for name in PROFILE_DATA_FILES:
        shutil.copyfile(fixture_path(f"profile_data/{name}"), target / name)
    return target


def build_profile_service(root: Path) -> ProfileService:
    """Crea el servicio de perfiles sobre una raíz temporal aislada."""
    return ProfileService(
        profiles_root=root / "perfiles",
        legacy_data_dir=root / "legacy_data",
        legacy_reports_dir=root / "legacy_reports",
        legacy_config_dir=root / "legacy_config",
    )


def install_catalog(root: Path) -> Path:
    """Copia los fixtures de catálogo a la raíz temporal de perfiles."""
    profiles_root = root / "perfiles"
    profiles_root.mkdir(parents=True)
    for name in ("perfiles.json", "perfil_activo.json"):
        shutil.copyfile(fixture_path(f"catalog/{name}"), profiles_root / name)
    return profiles_root


def build_settings_service(root: Path) -> SettingsService:
    """Crea el servicio de configuración sobre carpetas temporales."""
    return SettingsService(
        config_dir=root / "configuracion",
        reports_dir=root / "reportes_por_defecto",
        backup_dir=root / "respaldo_por_defecto",
    )


def write_legacy_budget_without_ids(data_dir: Path) -> Path:
    """Escribe un presupuesto con una categoría sin budget_id."""
    raw = load_json(fixture_path("profile_data/presupuesto_2026-03.json"))
    del raw["categories"][0]["budget_id"]
    raw["campo_futuro_archivo"] = 7
    data_dir.mkdir(parents=True, exist_ok=True)
    path = data_dir / "presupuesto_2026-03.json"
    path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Almacén: lectura
# ---------------------------------------------------------------------------


def test_store_read_returns_stored_structure(
    store: JsonFileStore,
    tmp_path: Path,
) -> None:
    """La lectura devuelve la estructura JSON guardada."""
    path = tmp_path / "documento.json"
    path.write_text(json.dumps(SAMPLE, ensure_ascii=False), encoding="utf-8")

    assert store.read(path) == SAMPLE
    assert store.read(str(path)) == SAMPLE


@pytest.mark.parametrize("content", ("[1, 2]", '"texto"', "null", "7"))
def test_store_read_does_not_judge_the_root_type(
    store: JsonFileStore,
    tmp_path: Path,
    content: str,
) -> None:
    """El almacén entrega cualquier raíz JSON; validarla es del servicio."""
    path = tmp_path / "documento.json"
    path.write_text(content, encoding="utf-8")

    assert store.read(path) == json.loads(content)


def test_store_read_invalid_json_keeps_current_exception(
    store: JsonFileStore,
    tmp_path: Path,
) -> None:
    """Un JSON inválido sigue produciendo JSONDecodeError."""
    path = tmp_path / "documento.json"
    path.write_text('{"x": [', encoding="utf-8")

    with pytest.raises(ValueError) as excinfo:
        store.read(path)

    assert excinfo.type is json.JSONDecodeError


def test_store_read_missing_file_keeps_current_exception(
    store: JsonFileStore,
    tmp_path: Path,
) -> None:
    """Leer un archivo inexistente sigue produciendo FileNotFoundError."""
    with pytest.raises(FileNotFoundError):
        store.read(tmp_path / "inexistente.json")


# ---------------------------------------------------------------------------
# Almacén: escritura exitosa
# ---------------------------------------------------------------------------


def test_store_write_creates_valid_json(
    store: JsonFileStore,
    tmp_path: Path,
) -> None:
    """Escribir crea un JSON válido con el formato histórico."""
    path = tmp_path / "documento.json"

    returned = store.write(path, SAMPLE)

    assert returned == path
    assert load_json(path) == SAMPLE
    text = path.read_text(encoding="utf-8")
    assert text.endswith("}\n")
    assert "áéí ñ €" in text
    assert '\n  "anidado": {\n    "a": null,' in text
    assert list(json.loads(text)) == sorted(SAMPLE)
    assert sorted(item.name for item in tmp_path.iterdir()) == ["documento.json"]


def test_store_write_replaces_existing_file(
    store: JsonFileStore,
    tmp_path: Path,
) -> None:
    """Escribir sobre un archivo existente lo reemplaza por completo."""
    path = tmp_path / "documento.json"
    path.write_text(json.dumps({"anterior": "x" * 500}), encoding="utf-8")

    store.write(path, SAMPLE)

    assert load_json(path) == SAMPLE
    assert leftovers(tmp_path) == []


def test_store_write_round_trips_schema_v1_fixture(
    store: JsonFileStore,
    tmp_path: Path,
) -> None:
    """El almacén no altera la estructura de un documento schema_v1."""
    fixture = load_json(fixture_path("profile_data/presupuesto_2026-03.json"))
    path = tmp_path / "presupuesto_2026-03.json"

    store.write(path, fixture)

    assert store.read(path) == fixture


def test_store_write_syncs_and_closes_temporary_before_replace(
    store: JsonFileStore,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """El temporal se sincroniza, se cierra y recién entonces reemplaza."""
    path = tmp_path / "documento.json"
    events: list[str] = []
    real_fsync = os.fsync
    recorder = ReplaceRecorder(fail=False)

    def fsync(descriptor: int) -> None:
        events.append("fsync")
        real_fsync(descriptor)

    def replace(source: Any, target: Any) -> None:
        events.append("replace")
        assert load_json(Path(source)) == SAMPLE
        os.rename(source, f"{source}.cerrado")
        os.rename(f"{source}.cerrado", source)
        recorder(source, target)

    with monkeypatch.context() as patch:
        patch.setattr(json_file_store.os, "fsync", fsync)
        patch.setattr(json_file_store.os, "replace", replace)
        store.write(path, SAMPLE)

    assert events == ["fsync", "replace"]
    assert_temporary_next_to_target(recorder, path)
    assert load_json(path) == SAMPLE
    assert leftovers(tmp_path) == []


# ---------------------------------------------------------------------------
# Almacén: garantías ante fallo
# ---------------------------------------------------------------------------


def test_store_serialization_failure_keeps_previous_bytes(
    store: JsonFileStore,
    tmp_path: Path,
) -> None:
    """Si la serialización falla, el destino previo queda byte a byte igual."""
    path = tmp_path / "documento.json"
    store.write(path, SAMPLE)
    before = path.read_bytes()

    with pytest.raises(TypeError):
        store.write(path, {"valido": 1, "no_serializable": object()})

    assert path.read_bytes() == before
    assert sorted(item.name for item in tmp_path.iterdir()) == ["documento.json"]


def test_store_serialization_failure_does_not_create_target(
    store: JsonFileStore,
    tmp_path: Path,
) -> None:
    """Si la serialización falla y no había destino, sigue sin existir."""
    path = tmp_path / "documento.json"

    with pytest.raises(TypeError):
        store.write(path, {"no_serializable": object()})

    assert not path.exists()
    assert list(tmp_path.iterdir()) == []


def test_store_replace_failure_keeps_previous_bytes(
    store: JsonFileStore,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Si os.replace falla, el destino previo queda intacto y sin temporal."""
    path = tmp_path / "documento.json"
    store.write(path, {"anterior": True})
    before = path.read_bytes()

    recorder = run_with_failing_replace(
        monkeypatch,
        lambda: store.write(path, SAMPLE),
    )

    assert_temporary_next_to_target(recorder, path)
    assert path.read_bytes() == before
    assert sorted(item.name for item in tmp_path.iterdir()) == ["documento.json"]


def test_store_replace_failure_does_not_create_target(
    store: JsonFileStore,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Si os.replace falla y no había destino, sigue sin existir."""
    path = tmp_path / "documento.json"

    recorder = run_with_failing_replace(
        monkeypatch,
        lambda: store.write(path, SAMPLE),
    )

    assert_temporary_next_to_target(recorder, path)
    assert not path.exists()
    assert list(tmp_path.iterdir()) == []


def test_store_write_does_not_create_missing_parent(
    store: JsonFileStore,
    tmp_path: Path,
) -> None:
    """Crear la carpeta sigue siendo decisión de cada servicio."""
    path = tmp_path / "carpeta_ausente" / "documento.json"

    with pytest.raises(FileNotFoundError):
        store.write(path, SAMPLE)

    assert not path.parent.exists()


def test_store_recovers_after_a_failed_write(
    store: JsonFileStore,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Tras un fallo, la siguiente escritura funciona sin intervención."""
    path = tmp_path / "documento.json"
    store.write(path, {"anterior": True})
    run_with_failing_replace(monkeypatch, lambda: store.write(path, SAMPLE))

    store.write(path, SAMPLE)

    assert load_json(path) == SAMPLE
    assert leftovers(tmp_path) == []


# ---------------------------------------------------------------------------
# Integración: BudgetRepository
# ---------------------------------------------------------------------------


REPOSITORY_WRITERS = (
    ("presupuesto_2026-03.json", lambda repo: repo.save(repo.load(2026, 3))),
    ("cuentas.json", lambda repo: repo.save_accounts(repo.load_accounts()[:1])),
    ("deudas.json", lambda repo: repo.save_debts(repo.load_debts()[:1])),
    (
        "debt_payments.json",
        lambda repo: repo.save_debt_payments([]),
    ),
    (
        "debt_snapshots.json",
        lambda repo: repo.save_debt_snapshots(repo.load_debt_snapshots()[:1]),
    ),
    (
        "monthly_closures.json",
        lambda repo: repo.save_monthly_closures(
            repo.load_monthly_closures()[:1],
        ),
    ),
)


@pytest.mark.parametrize(
    ("file_name", "writer"),
    REPOSITORY_WRITERS,
    ids=[name for name, _ in REPOSITORY_WRITERS],
)
def test_repository_write_is_atomic_when_replace_fails(
    data_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
    file_name: str,
    writer: Callable[[BudgetRepository], Any],
) -> None:
    """Cada guardado del repositorio conserva el archivo si el reemplazo falla."""
    repository = BudgetRepository(data_dir)
    target = data_dir / file_name
    before = target.read_bytes()

    recorder = run_with_failing_replace(monkeypatch, lambda: writer(repository))

    assert_temporary_next_to_target(recorder, target)
    assert target.read_bytes() == before
    assert leftovers(data_dir) == []


@pytest.mark.parametrize(
    ("file_name", "writer"),
    REPOSITORY_WRITERS,
    ids=[name for name, _ in REPOSITORY_WRITERS],
)
def test_repository_write_goes_through_temporary_next_to_target(
    data_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
    file_name: str,
    writer: Callable[[BudgetRepository], Any],
) -> None:
    """Cada guardado exitoso reemplaza el destino desde un temporal vecino."""
    repository = BudgetRepository(data_dir)
    target = data_dir / file_name
    before = target.read_bytes()
    recorder = ReplaceRecorder(fail=False)

    with monkeypatch.context() as patch:
        patch.setattr(json_file_store.os, "replace", recorder)
        writer(repository)

    assert_temporary_next_to_target(recorder, target)
    assert target.read_bytes() != before
    assert isinstance(load_json(target), dict)
    assert leftovers(data_dir) == []


def test_repository_failed_first_write_does_not_create_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Un primer guardado fallido no deja archivo ni temporal."""
    repository = BudgetRepository(tmp_path / "datos_nuevos")

    run_with_failing_replace(monkeypatch, lambda: repository.save_debts([]))

    assert not repository.debts_path.exists()
    assert leftovers(repository.data_dir) == []


def test_repository_keeps_historical_backup_copy_before_writing(
    data_dir: Path,
) -> None:
    """El respaldo previo histórico sigue creándose antes de cada guardado."""
    repository = BudgetRepository(data_dir)
    before = repository.accounts_path.read_bytes()

    repository.save_accounts(repository.load_accounts()[:1])

    copies = list(repository.backup_dir.glob("cuentas.backup_*.json"))
    assert len(copies) == 1
    assert copies[0].read_bytes() == before
    assert leftovers(data_dir) == []


def test_repository_save_keeps_schema_v1_structure(data_dir: Path) -> None:
    """Guardar lo cargado reproduce la estructura de los fixtures schema_v1."""
    repository = BudgetRepository(data_dir)

    repository.save_accounts(repository.load_accounts())
    repository.save_debts(repository.load_debts())
    repository.save_debt_payments(repository.load_debt_payments())
    repository.save_debt_snapshots(repository.load_debt_snapshots())
    repository.save_monthly_closures(repository.load_monthly_closures())
    repository.save(repository.load(2026, 3))

    for name in (
        "cuentas.json",
        "deudas.json",
        "debt_payments.json",
        "debt_snapshots.json",
        "monthly_closures.json",
    ):
        expected = load_json(fixture_path(f"profile_data/{name}"))
        assert load_json(data_dir / name) == expected
    expected = load_json(fixture_path("profile_data/presupuesto_2026-03.json"))
    written = load_json(data_dir / "presupuesto_2026-03.json")
    assert {**written, "updated_at": None} == {**expected, "updated_at": None}


# ---------------------------------------------------------------------------
# Integración: BudgetService (reescritura legacy de budget_id)
# ---------------------------------------------------------------------------


def test_budget_service_legacy_rewrite_is_atomic_when_replace_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Si el reemplazo falla, el presupuesto legacy queda sin tocar."""
    data_dir = tmp_path / "datos_legacy"
    target = write_legacy_budget_without_ids(data_dir)
    before = target.read_bytes()
    service = BudgetService(data_dir=data_dir, year=2026, month=3)

    recorder = run_with_failing_replace(monkeypatch, service.obtener_presupuestos)

    assert_temporary_next_to_target(recorder, target)
    assert target.read_bytes() == before
    assert leftovers(data_dir) == []


def test_budget_service_legacy_rewrite_goes_through_temporary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """La reescritura legacy reemplaza el destino desde un temporal vecino."""
    data_dir = tmp_path / "datos_legacy"
    target = write_legacy_budget_without_ids(data_dir)
    service = BudgetService(data_dir=data_dir, year=2026, month=3)
    recorder = ReplaceRecorder(fail=False)

    with monkeypatch.context() as patch:
        patch.setattr(json_file_store.os, "replace", recorder)
        service.obtener_presupuestos()

    assert_temporary_next_to_target(recorder, target)
    written = load_json(target)
    assert all(item.get("budget_id") for item in written["categories"])
    assert written["campo_futuro_archivo"] == 7
    assert leftovers(data_dir) == []


def test_budget_service_read_with_ids_does_not_write(
    data_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Un presupuesto con todos sus ID se lee sin ninguna escritura."""
    target = data_dir / "presupuesto_2026-03.json"
    before = target.read_bytes()
    service = BudgetService(data_dir=data_dir, year=2026, month=3)
    recorder = ReplaceRecorder(fail=True)

    with monkeypatch.context() as patch:
        patch.setattr(json_file_store.os, "replace", recorder)
        service.obtener_presupuestos()

    assert recorder.calls == []
    assert target.read_bytes() == before


# ---------------------------------------------------------------------------
# Integración: CategoryService
# ---------------------------------------------------------------------------


def test_category_service_creation_on_read_is_atomic_when_replace_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Si falla el reemplazo al crear categorias.json, no queda archivo."""
    service = CategoryService(data_dir=tmp_path / "datos_nuevos")

    recorder = run_with_failing_replace(monkeypatch, service.listar_categorias)

    assert_temporary_next_to_target(recorder, service.categories_path)
    assert not service.categories_path.exists()
    assert leftovers(service.data_dir) == []


def test_category_service_still_creates_missing_file_on_read(
    tmp_path: Path,
) -> None:
    """Sin archivo, leer categorías lo sigue creando con las categorías base."""
    service = CategoryService(data_dir=tmp_path / "datos_nuevos")

    categories = service.listar_categorias()

    written = load_json(service.categories_path)
    assert set(written) == {"categories"}
    assert len(written["categories"]) == len(categories) > 0
    assert leftovers(service.data_dir) == []


def test_category_service_save_is_atomic_when_replace_fails(
    data_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Si falla el reemplazo al crear una categoría, el archivo queda igual."""
    service = CategoryService(data_dir=data_dir)
    before = service.categories_path.read_bytes()

    recorder = run_with_failing_replace(
        monkeypatch,
        lambda: service.crear_categoria("Mascota ficticia", "gasto", "variable"),
    )

    assert_temporary_next_to_target(recorder, service.categories_path)
    assert service.categories_path.read_bytes() == before
    assert leftovers(data_dir) == []


def test_category_service_synchronized_read_does_not_write(
    data_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Con categorías ya sincronizadas, leer no dispara ninguna escritura."""
    service = CategoryService(data_dir=data_dir)
    before = service.categories_path.read_bytes()
    recorder = ReplaceRecorder(fail=True)

    with monkeypatch.context() as patch:
        patch.setattr(json_file_store.os, "replace", recorder)
        service.listar_categorias()

    assert recorder.calls == []
    assert service.categories_path.read_bytes() == before


# ---------------------------------------------------------------------------
# Integración: SettingsService
# ---------------------------------------------------------------------------


def test_settings_service_save_is_atomic_when_replace_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Si falla el reemplazo al guardar, settings.json queda intacto."""
    monkeypatch.chdir(tmp_path)
    service = build_settings_service(tmp_path)
    fixture = load_json(fixture_path("profile_config/settings.json"))
    service.guardar_configuracion(dict(fixture))
    before = service.settings_path.read_bytes()

    recorder = run_with_failing_replace(
        monkeypatch,
        lambda: service.guardar_configuracion(
            {**fixture, "moneda_principal": "USD"},
        ),
    )

    assert_temporary_next_to_target(recorder, service.settings_path)
    assert service.settings_path.read_bytes() == before
    assert service.cargar_configuracion().moneda_principal == "CLP"
    assert leftovers(service.config_dir) == []


def test_settings_service_failed_first_save_does_not_create_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Un primer guardado fallido no deja settings.json ni temporal."""
    monkeypatch.chdir(tmp_path)
    service = build_settings_service(tmp_path)
    fixture = load_json(fixture_path("profile_config/settings.json"))

    run_with_failing_replace(
        monkeypatch,
        lambda: service.guardar_configuracion(dict(fixture)),
    )

    assert not service.settings_path.exists()
    assert leftovers(service.config_dir) == []


def test_settings_service_save_keeps_the_six_current_fields(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Guardar sigue escribiendo exactamente los campos del fixture."""
    monkeypatch.chdir(tmp_path)
    service = build_settings_service(tmp_path)
    fixture = load_json(fixture_path("profile_config/settings.json"))

    service.guardar_configuracion(dict(fixture))

    assert load_json(service.settings_path) == fixture
    assert leftovers(service.config_dir) == []


# ---------------------------------------------------------------------------
# Integración: ProfileService
# ---------------------------------------------------------------------------


def test_profile_service_selection_is_atomic_when_replace_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Si falla el reemplazo al seleccionar, el perfil activo no cambia."""
    install_catalog(tmp_path)
    service = build_profile_service(tmp_path)
    before = service.active_path.read_bytes()

    recorder = run_with_failing_replace(
        monkeypatch,
        lambda: service.seleccionar_perfil("personal"),
    )

    assert_temporary_next_to_target(recorder, service.active_path)
    assert service.active_path.read_bytes() == before
    assert service.obtener_activo().id == "hogar_ficticio"
    assert leftovers(service.profiles_root) == []


def test_profile_service_registry_write_is_atomic_when_replace_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Si falla el reemplazo al crear un perfil, el catálogo queda intacto."""
    install_catalog(tmp_path)
    service = build_profile_service(tmp_path)
    before = service.registry_path.read_bytes()

    recorder = run_with_failing_replace(
        monkeypatch,
        lambda: service.crear_perfil("Negocio Ficticio"),
    )

    assert_temporary_next_to_target(recorder, service.registry_path)
    assert service.registry_path.read_bytes() == before
    assert [item.id for item in service.listar_perfiles()] == [
        "hogar_ficticio",
        "personal",
    ]
    assert leftovers(service.profiles_root) == []


def test_profile_service_failed_bootstrap_does_not_create_catalog(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Si falla el reemplazo en el primer arranque, no queda catálogo."""
    recorder = run_with_failing_replace(
        monkeypatch,
        lambda: build_profile_service(tmp_path),
    )

    profiles_root = tmp_path / "perfiles"
    assert_temporary_next_to_target(recorder, profiles_root / "perfiles.json")
    assert not (profiles_root / "perfiles.json").exists()
    assert not (profiles_root / "perfil_activo.json").exists()
    assert leftovers(profiles_root) == []


def test_profile_service_writes_keep_current_catalog_structure(
    tmp_path: Path,
) -> None:
    """Seleccionar y crear perfiles conserva la estructura actual."""
    install_catalog(tmp_path)
    service = build_profile_service(tmp_path)

    service.seleccionar_perfil("personal")
    created = service.crear_perfil("Negocio Ficticio")

    assert load_json(service.active_path) == {"slug": "personal"}
    assert load_json(service.registry_path) == {
        "perfiles": [
            {"nombre": "Hogar Ficticio", "slug": "hogar_ficticio"},
            {"nombre": "Negocio Ficticio", "slug": created.id},
            {"nombre": "Personal", "slug": "personal"},
        ],
    }
    assert leftovers(service.profiles_root) == []
