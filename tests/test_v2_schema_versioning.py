"""Pruebas del versionado explícito por archivo (Etapa 22D).

Contrato:

- un documento sin ``schema_version`` es el formato legacy y se lee como
  versión 1 implícita, sin reescribirse sólo por eso;
- ``schema_version = 1`` explícita es válida;
- una versión futura o inválida se rechaza antes de cualquier escritura;
- toda escritura legítima deja ``"schema_version": 1`` en la raíz.

Los fixtures de ``tests/fixtures/schema_v1`` representan deliberadamente el
formato legacy v1 implícito, NO el formato v1 explícito: no llevan la clave
y aquí se usan como punto de partida legacy. El formato explícito se
construye dentro de cada prueba.
"""

from __future__ import annotations

import json
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import pytest

from avalancha import __version__
from avalancha.models import MonthlyBudget
from avalancha.storage import BudgetRepository
from core import json_file_store
from core.json_file_store import JsonFileStore
from core.profile_metadata import (
    CURRENT_PROFILE_FORMAT_VERSION,
    PROFILE_METADATA_FILE_NAME,
)
from core.schema_versioning import (
    CURRENT_SCHEMA_VERSION,
    LEGACY_IMPLICIT_SCHEMA_VERSION,
    SCHEMA_VERSION_KEY,
    InvalidSchemaVersionError,
    SchemaVersionError,
    SchemaVersionPolicy,
    UnsupportedSchemaVersionError,
)
from core.versioned_json_store import VersionedJsonStore
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
INVALID_VERSIONS = ("1", 1.0, True, False, None, 0, -1)
INVALID_IDS = ("texto", "float", "true", "false", "null", "cero", "negativo")
FUTURE_VERSION = CURRENT_SCHEMA_VERSION + 1
SECRET = "SALDO-PRIVADO-987654321"


class ReplaceSpy:
    """Envuelve os.replace para contar reemplazos sin alterar su efecto."""

    def __init__(self) -> None:
        """Guarda la función real y la lista de destinos reemplazados."""
        self.targets: list[str] = []
        self._real = os.replace

    def __call__(self, source: Any, target: Any) -> None:
        """Registra el destino y ejecuta el reemplazo real."""
        self.targets.append(Path(target).name)
        self._real(source, target)


@dataclass(frozen=True)
class Workspace:
    """Árbol temporal con los diez archivos legacy y sus servicios."""

    root: Path

    @property
    def data_dir(self) -> Path:
        """Carpeta de datos financieros del perfil ficticio."""
        return self.root / "datos"

    @property
    def profiles_root(self) -> Path:
        """Carpeta del catálogo de perfiles."""
        return self.root / "perfiles"

    @property
    def config_dir(self) -> Path:
        """Carpeta de configuración del perfil ficticio."""
        return self.root / "configuracion"

    def repository(self) -> BudgetRepository:
        """Crea el repositorio financiero productivo."""
        return BudgetRepository(self.data_dir)

    def budget_service(self) -> BudgetService:
        """Crea el servicio de presupuestos del mes del fixture."""
        return BudgetService(data_dir=self.data_dir, year=2026, month=3)

    def category_service(self) -> CategoryService:
        """Crea el servicio de categorías."""
        return CategoryService(data_dir=self.data_dir)

    def settings_service(self) -> SettingsService:
        """Crea el servicio de configuración."""
        return SettingsService(
            config_dir=self.config_dir,
            reports_dir=self.root / "reportes_por_defecto",
            backup_dir=self.root / "respaldo_por_defecto",
        )

    def profile_service(self) -> ProfileService:
        """Crea el servicio de perfiles; su construcción ya lee el catálogo."""
        return ProfileService(
            profiles_root=self.profiles_root,
            legacy_data_dir=self.root / "legacy_data",
            legacy_reports_dir=self.root / "legacy_reports",
            legacy_config_dir=self.root / "legacy_config",
        )


@dataclass(frozen=True)
class Family:
    """Una familia de archivo versionado y sus operaciones legítimas."""

    name: str
    target: str
    read: Callable[[Workspace], Any]
    write: Callable[[Workspace], Any]

    def path(self, workspace: Workspace) -> Path:
        """Devuelve la ruta del archivo de la familia en el árbol temporal."""
        return workspace.root.joinpath(*self.target.split("/"))


def _resave(loader: str, saver: str) -> Callable[[Workspace], Any]:
    """Construye una escritura legítima: cargar y volver a guardar."""

    def action(workspace: Workspace) -> Any:
        repository = workspace.repository()
        return getattr(repository, saver)(getattr(repository, loader)())

    return action


def _save_settings(workspace: Workspace) -> Any:
    """Guarda la configuración cargada."""
    service = workspace.settings_service()
    return service.guardar_configuracion(service.cargar_configuracion())


FAMILIES = (
    Family(
        "presupuesto",
        "datos/presupuesto_2026-03.json",
        lambda w: w.repository().load(2026, 3),
        lambda w: w.repository().save(w.repository().load(2026, 3)),
    ),
    Family(
        "cuentas",
        "datos/cuentas.json",
        lambda w: w.repository().load_accounts(),
        _resave("load_accounts", "save_accounts"),
    ),
    Family(
        "deudas",
        "datos/deudas.json",
        lambda w: w.repository().load_debts(),
        _resave("load_debts", "save_debts"),
    ),
    Family(
        "debt_payments",
        "datos/debt_payments.json",
        lambda w: w.repository().load_debt_payments(),
        _resave("load_debt_payments", "save_debt_payments"),
    ),
    Family(
        "debt_snapshots",
        "datos/debt_snapshots.json",
        lambda w: w.repository().load_debt_snapshots(),
        _resave("load_debt_snapshots", "save_debt_snapshots"),
    ),
    Family(
        "monthly_closures",
        "datos/monthly_closures.json",
        lambda w: w.repository().load_monthly_closures(),
        _resave("load_monthly_closures", "save_monthly_closures"),
    ),
    Family(
        "categorias",
        "datos/categorias.json",
        lambda w: w.category_service().listar_categorias(),
        lambda w: w.category_service().crear_categoria(
            "Mascota ficticia",
            "gasto",
            "variable",
        ),
    ),
    Family(
        "settings",
        "configuracion/settings.json",
        lambda w: w.settings_service().cargar_configuracion(),
        _save_settings,
    ),
    Family(
        "perfiles",
        "perfiles/perfiles.json",
        lambda w: w.profile_service().listar_perfiles(),
        lambda w: w.profile_service().crear_perfil("Negocio Ficticio"),
    ),
    Family(
        "perfil_activo",
        "perfiles/perfil_activo.json",
        lambda w: w.profile_service().obtener_activo(),
        lambda w: w.profile_service().seleccionar_perfil("personal"),
    ),
)
FAMILY_IDS = [family.name for family in FAMILIES]


def fixture_path(relative: str) -> Path:
    """Devuelve la ruta de un fixture legacy schema_v1."""
    return FIXTURES_ROOT.joinpath(*relative.split("/"))


def load_json(path: Path) -> Any:
    """Carga un archivo JSON del filesystem."""
    return json.loads(path.read_text(encoding="utf-8"))


def dump_json(path: Path, document: Any) -> None:
    """Escribe un documento de prueba sin pasar por producción."""
    path.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")


def set_version(path: Path, version: object) -> None:
    """Declara una versión de esquema en un documento existente."""
    dump_json(path, {**load_json(path), SCHEMA_VERSION_KEY: version})


def files_snapshot(root: Path) -> dict[str, bytes]:
    """Captura el contenido de todos los archivos bajo una carpeta."""
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def tree_snapshot(root: Path) -> tuple[dict[str, bytes], frozenset[str]]:
    """Captura archivos y carpetas para detectar cualquier efecto en disco."""
    folders = frozenset(
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_dir()
    )
    return files_snapshot(root), folders


def version_keys(node: Any) -> int:
    """Cuenta cuántas veces aparece schema_version en un documento."""
    if isinstance(node, dict):
        return sum(
            (key == SCHEMA_VERSION_KEY) + version_keys(value)
            for key, value in node.items()
        )
    if isinstance(node, list):
        return sum(version_keys(item) for item in node)
    return 0


@pytest.fixture()
def workspace(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    request: pytest.FixtureRequest,
) -> Workspace:
    """Arma el árbol temporal con los diez archivos en formato legacy.

    Incluye la carpeta ``backups`` vacía que BudgetRepository crea al
    construirse, como en cualquier perfil ya abierto alguna vez.

    Desde la Etapa 22E la primera apertura de un perfil crea su
    ``profile_metadata.json``. Las pruebas parametrizadas por familia
    miden qué ocurre con los archivos versionados en aperturas
    posteriores, así que parten de perfiles que ya tienen metadatos;
    esa creación inicial se prueba en ``test_v2_profile_metadata.py``.
    """
    monkeypatch.chdir(tmp_path)
    space = Workspace(tmp_path)
    space.data_dir.mkdir()
    (space.data_dir / "backups").mkdir()
    for name in PROFILE_DATA_FILES:
        shutil.copyfile(
            fixture_path(f"profile_data/{name}"),
            space.data_dir / name,
        )
    space.profiles_root.mkdir()
    for name in ("perfiles.json", "perfil_activo.json"):
        shutil.copyfile(
            fixture_path(f"catalog/{name}"),
            space.profiles_root / name,
        )
    if "family" in request.fixturenames:
        for slug, name in (
            ("personal", "Personal"),
            ("hogar_ficticio", "Hogar Ficticio"),
        ):
            (space.profiles_root / slug).mkdir()
            dump_json(
                space.profiles_root / slug / PROFILE_METADATA_FILE_NAME,
                {
                    SCHEMA_VERSION_KEY: CURRENT_SCHEMA_VERSION,
                    "profile_format_version": CURRENT_PROFILE_FORMAT_VERSION,
                    "profile_slug": slug,
                    "profile_name": name,
                    "app_version": __version__,
                },
            )
    space.config_dir.mkdir()
    shutil.copyfile(
        fixture_path("profile_config/settings.json"),
        space.config_dir / "settings.json",
    )
    return space


@pytest.fixture()
def replace_spy(monkeypatch: pytest.MonkeyPatch) -> ReplaceSpy:
    """Cuenta los reemplazos atómicos ejecutados durante la prueba."""
    spy = ReplaceSpy()
    monkeypatch.setattr(json_file_store.os, "replace", spy)
    return spy


def assert_rejected_without_effects(
    workspace: Workspace,
    replace_spy: ReplaceSpy,
    action: Callable[[], Any],
    expected: type[SchemaVersionError],
) -> SchemaVersionError:
    """Exige que la acción falle sin dejar ningún efecto en el filesystem.

    Los reemplazos se cuentan desde este punto: la preparación de la
    prueba puede haber escrito legítimamente antes de la acción.
    """
    before = tree_snapshot(workspace.root)
    replaced_before = list(replace_spy.targets)

    with pytest.raises(SchemaVersionError) as excinfo:
        action()

    assert excinfo.type is expected
    assert tree_snapshot(workspace.root) == before
    assert replace_spy.targets == replaced_before
    return excinfo.value


def make_budget_without_ids(workspace: Workspace) -> Path:
    """Deja el presupuesto del fixture con una categoría sin budget_id."""
    path = workspace.data_dir / "presupuesto_2026-03.json"
    raw = load_json(path)
    del raw["categories"][1]["budget_id"]
    raw["campo_futuro_archivo"] = 7
    dump_json(path, raw)
    return path


def make_budget_with_unsynced_category(workspace: Workspace) -> Path:
    """Agrega al presupuesto una categoría que categorias.json no conoce."""
    path = workspace.data_dir / "presupuesto_2026-03.json"
    raw = load_json(path)
    extra = dict(raw["categories"][1])
    extra["name"] = "Mascota ficticia"
    extra["budget_id"] = "pre00000000000000000000000000099"
    raw["categories"].append(extra)
    dump_json(path, raw)
    return path


# ---------------------------------------------------------------------------
# Política central
# ---------------------------------------------------------------------------


def test_current_schema_version_is_the_single_source_of_truth() -> None:
    """La versión actual vive en una sola constante y hoy vale 1."""
    assert CURRENT_SCHEMA_VERSION == 1
    assert type(CURRENT_SCHEMA_VERSION) is int
    assert SchemaVersionPolicy.CURRENT_VERSION is CURRENT_SCHEMA_VERSION
    assert LEGACY_IMPLICIT_SCHEMA_VERSION == 1
    assert SCHEMA_VERSION_KEY == "schema_version"


@pytest.mark.parametrize(
    "document",
    ({}, {"accounts": []}, {"slug": "personal"}),
    ids=("vacio", "cuentas", "perfil_activo"),
)
def test_policy_missing_key_is_legacy_version_one(
    document: dict[str, Any],
) -> None:
    """Un documento sin la clave es legacy y vale como versión 1."""
    policy = SchemaVersionPolicy()

    assert policy.effective_version(document) == 1
    policy.validate(document)


def test_policy_explicit_version_one_is_valid() -> None:
    """La versión 1 explícita es válida."""
    policy = SchemaVersionPolicy()

    assert policy.effective_version({"schema_version": 1}) == 1
    policy.validate({"schema_version": 1, "accounts": []})


@pytest.mark.parametrize("version", (2, 3, 999))
def test_policy_future_version_is_unsupported(version: int) -> None:
    """Una versión mayor que la actual se rechaza como no soportada."""
    policy = SchemaVersionPolicy()

    with pytest.raises(UnsupportedSchemaVersionError) as excinfo:
        policy.effective_version({"schema_version": version})

    assert excinfo.value.observed_version == version
    assert excinfo.value.supported_version == CURRENT_SCHEMA_VERSION
    with pytest.raises(UnsupportedSchemaVersionError):
        policy.validate({"schema_version": version})


@pytest.mark.parametrize("version", INVALID_VERSIONS, ids=INVALID_IDS)
def test_policy_invalid_version_is_rejected(version: object) -> None:
    """Texto, flotante, booleano, null, cero y negativo son inválidos."""
    policy = SchemaVersionPolicy()

    with pytest.raises(InvalidSchemaVersionError) as excinfo:
        policy.effective_version({"schema_version": version})

    assert excinfo.value.observed_type == type(version).__name__
    with pytest.raises(InvalidSchemaVersionError):
        policy.validate({"schema_version": version})


def test_policy_distinguishes_missing_key_from_null() -> None:
    """Clave ausente y clave con null no son equivalentes."""
    policy = SchemaVersionPolicy()

    assert policy.effective_version({}) == 1
    with pytest.raises(InvalidSchemaVersionError):
        policy.effective_version({"schema_version": None})


def test_policy_rejects_booleans_even_though_they_are_integers() -> None:
    """True es instancia de int en Python y aun así se rechaza."""
    assert isinstance(True, int)
    policy = SchemaVersionPolicy()

    for value in (True, False):
        with pytest.raises(InvalidSchemaVersionError) as excinfo:
            policy.effective_version({"schema_version": value})
        assert excinfo.value.observed_type == "bool"
        assert excinfo.value.observed_version is None


@pytest.mark.parametrize("root", ([], [1, 2], "texto", 7, None))
def test_policy_leaves_non_object_roots_to_each_service(root: object) -> None:
    """Una raíz que no es objeto no declara versión y no se juzga aquí."""
    SchemaVersionPolicy().validate(root)


def test_policy_prepare_for_write_adds_current_version() -> None:
    """Preparar para escritura agrega la versión actual en la raíz."""
    document = {"accounts": [{"name": "Cuenta ficticia"}], "otro": None}

    prepared = SchemaVersionPolicy().prepare_for_write(document)

    assert prepared == {
        "accounts": [{"name": "Cuenta ficticia"}],
        "otro": None,
        "schema_version": CURRENT_SCHEMA_VERSION,
    }
    assert version_keys(prepared) == 1


def test_policy_prepare_for_write_does_not_mutate_input() -> None:
    """El documento recibido queda igual; se devuelve una copia."""
    document = {"slug": "personal"}

    prepared = SchemaVersionPolicy().prepare_for_write(document)

    assert document == {"slug": "personal"}
    assert prepared is not document
    assert prepared == {"slug": "personal", "schema_version": 1}


def test_policy_prepare_for_write_keeps_explicit_version_one() -> None:
    """Un documento ya versionado conserva una única versión 1."""
    prepared = SchemaVersionPolicy().prepare_for_write(
        {"schema_version": 1, "debts": []},
    )

    assert prepared == {"schema_version": 1, "debts": []}


@pytest.mark.parametrize("version", (2, 999, "1", 1.0, True, None, 0, -1))
def test_policy_prepare_for_write_cannot_relabel_other_versions(
    version: object,
) -> None:
    """No se puede reetiquetar como v1 un documento de otra versión."""
    with pytest.raises(SchemaVersionError):
        SchemaVersionPolicy().prepare_for_write({"schema_version": version})


def test_policy_prepare_for_write_requires_an_object_root() -> None:
    """Sólo un objeto JSON puede llevar versión en la raíz."""
    with pytest.raises(TypeError):
        SchemaVersionPolicy().prepare_for_write([1, 2])  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Errores de dominio
# ---------------------------------------------------------------------------


def test_version_errors_are_domain_errors_not_value_errors() -> None:
    """Los errores de versión no pueden absorberse como ValueError."""
    assert issubclass(UnsupportedSchemaVersionError, SchemaVersionError)
    assert issubclass(InvalidSchemaVersionError, SchemaVersionError)
    assert not issubclass(SchemaVersionError, ValueError)
    assert not issubclass(UnsupportedSchemaVersionError, InvalidSchemaVersionError)
    assert not issubclass(InvalidSchemaVersionError, UnsupportedSchemaVersionError)


def test_unsupported_error_reports_observed_and_supported_versions() -> None:
    """El error de versión futura expone ambas versiones."""
    error = UnsupportedSchemaVersionError(7, 1)

    assert error.observed_version == 7
    assert error.supported_version == 1
    assert "7" in str(error)
    assert "1" in str(error)
    assert error.document_name is None


def test_invalid_error_keeps_integer_value_but_never_content() -> None:
    """El error inválido guarda enteros, pero no texto ni estructuras."""
    numeric = InvalidSchemaVersionError(-3)
    textual = InvalidSchemaVersionError(SECRET)
    structured = InvalidSchemaVersionError({"saldo": SECRET})

    assert numeric.observed_version == -3
    assert numeric.observed_type == "int"
    assert textual.observed_version is None
    assert textual.observed_type == "str"
    assert structured.observed_type == "dict"
    for error in (textual, structured):
        assert SECRET not in str(error)
        assert SECRET not in repr(error)
        assert SECRET not in repr(error.args)
        assert SECRET not in repr(vars(error))


def test_store_errors_name_the_file_without_path_or_content(
    tmp_path: Path,
) -> None:
    """El error identifica el archivo por nombre, sin ruta ni contenido."""
    path = tmp_path / "carpeta_privada" / "cuentas.json"
    path.parent.mkdir()
    dump_json(path, {"schema_version": 2, "accounts": [{"name": SECRET}]})

    with pytest.raises(UnsupportedSchemaVersionError) as excinfo:
        VersionedJsonStore().read(path)

    error = excinfo.value
    assert error.document_name == "cuentas.json"
    assert str(error).startswith("cuentas.json: ")
    for text in (str(error), repr(error), repr(error.args), repr(vars(error))):
        assert SECRET not in text
        assert "carpeta_privada" not in text
        assert str(tmp_path) not in text


# ---------------------------------------------------------------------------
# Almacén versionado
# ---------------------------------------------------------------------------


def test_versioned_store_reads_legacy_and_explicit_documents(
    tmp_path: Path,
) -> None:
    """Lee documentos legacy y v1 explícitos sin transformarlos."""
    store = VersionedJsonStore()
    legacy = tmp_path / "legacy.json"
    explicit = tmp_path / "explicito.json"
    dump_json(legacy, {"debts": []})
    dump_json(explicit, {"schema_version": 1, "debts": []})

    assert store.read(legacy) == {"debts": []}
    assert store.read(explicit) == {"schema_version": 1, "debts": []}


def test_versioned_store_write_adds_version_through_atomic_store(
    tmp_path: Path,
    replace_spy: ReplaceSpy,
) -> None:
    """Escribe con versión actual usando el reemplazo atómico."""
    path = tmp_path / "deudas.json"
    document = {"debts": []}

    VersionedJsonStore().write(path, document)

    assert load_json(path) == {"debts": [], "schema_version": 1}
    assert document == {"debts": []}
    assert replace_spy.targets == ["deudas.json"]
    assert sorted(item.name for item in tmp_path.iterdir()) == ["deudas.json"]


def test_versioned_store_uses_the_plain_json_store(tmp_path: Path) -> None:
    """La versión se agrega fuera de JsonFileStore, que sigue neutral."""
    path = tmp_path / "documento.json"

    JsonFileStore().write(path, {"debts": []})

    assert load_json(path) == {"debts": []}


@pytest.mark.parametrize("version", (2, "1", None, 0), ids=("futura", "texto", "null", "cero"))
def test_versioned_store_refuses_to_replace_incompatible_file(
    tmp_path: Path,
    replace_spy: ReplaceSpy,
    version: object,
) -> None:
    """No reemplaza un archivo existente de versión futura o inválida."""
    path = tmp_path / "deudas.json"
    dump_json(path, {"schema_version": version, "debts": [{"name": "X"}]})
    before = path.read_bytes()

    with pytest.raises(SchemaVersionError):
        VersionedJsonStore().write(path, {"debts": []})
    with pytest.raises(SchemaVersionError):
        VersionedJsonStore().check_existing(path)

    assert path.read_bytes() == before
    assert replace_spy.targets == []
    assert sorted(item.name for item in tmp_path.iterdir()) == ["deudas.json"]


def test_versioned_store_check_existing_accepts_missing_and_legacy(
    tmp_path: Path,
) -> None:
    """La verificación previa acepta destino ausente, legacy y v1."""
    store = VersionedJsonStore()
    legacy = tmp_path / "legacy.json"
    dump_json(legacy, {"debts": []})

    store.check_existing(tmp_path / "ausente.json")
    store.check_existing(legacy)
    set_version(legacy, 1)
    store.check_existing(legacy)


def test_legacy_characterization_unreadable_existing_file_is_still_replaced(
    tmp_path: Path,
) -> None:
    """Hoy un archivo que no es JSON legible se sigue reemplazando al guardar.

    No declara versión que proteger; endurecer este caso corresponde a 22H.
    """
    path = tmp_path / "deudas.json"
    path.write_text('{"debts": [', encoding="utf-8")

    VersionedJsonStore().write(path, {"debts": []})

    assert load_json(path) == {"debts": [], "schema_version": 1}


# ---------------------------------------------------------------------------
# Las diez familias: lectura
# ---------------------------------------------------------------------------


def test_the_ten_versioned_families_are_covered() -> None:
    """La tabla de familias cubre exactamente los diez archivos del alcance."""
    assert sorted(Path(family.target).name for family in FAMILIES) == sorted(
        (
            "presupuesto_2026-03.json",
            "cuentas.json",
            "deudas.json",
            "debt_payments.json",
            "debt_snapshots.json",
            "monthly_closures.json",
            "categorias.json",
            "settings.json",
            "perfiles.json",
            "perfil_activo.json",
        ),
    )


@pytest.mark.parametrize("family", FAMILIES, ids=FAMILY_IDS)
def test_legacy_file_without_version_loads_and_is_not_rewritten(
    workspace: Workspace,
    replace_spy: ReplaceSpy,
    family: Family,
) -> None:
    """Leer un archivo legacy no lo reescribe sólo para versionarlo."""
    before = files_snapshot(workspace.root)
    assert SCHEMA_VERSION_KEY not in load_json(family.path(workspace))

    family.read(workspace)

    assert files_snapshot(workspace.root) == before
    assert replace_spy.targets == []


@pytest.mark.parametrize("family", FAMILIES, ids=FAMILY_IDS)
def test_explicit_version_one_loads_and_is_not_rewritten(
    workspace: Workspace,
    replace_spy: ReplaceSpy,
    family: Family,
) -> None:
    """Un archivo con schema_version 1 explícita se lee sin escribir."""
    set_version(family.path(workspace), CURRENT_SCHEMA_VERSION)
    before = files_snapshot(workspace.root)

    family.read(workspace)

    assert files_snapshot(workspace.root) == before
    assert replace_spy.targets == []


@pytest.mark.parametrize("family", FAMILIES, ids=FAMILY_IDS)
def test_legacy_and_explicit_files_load_the_same_content(
    workspace: Workspace,
    family: Family,
) -> None:
    """La versión explícita no cambia lo que la lectura entrega."""
    legacy = repr(family.read(workspace))

    set_version(family.path(workspace), CURRENT_SCHEMA_VERSION)

    assert repr(family.read(workspace)) == legacy


# ---------------------------------------------------------------------------
# Las diez familias: escritura legítima
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("family", FAMILIES, ids=FAMILY_IDS)
def test_legitimate_write_adds_schema_version_to_legacy_file(
    workspace: Workspace,
    replace_spy: ReplaceSpy,
    family: Family,
) -> None:
    """Una escritura legítima deja schema_version 1 sólo en la raíz."""
    target = family.path(workspace)
    legacy_keys = set(load_json(target))

    family.write(workspace)

    written = load_json(target)
    assert written[SCHEMA_VERSION_KEY] == CURRENT_SCHEMA_VERSION
    assert type(written[SCHEMA_VERSION_KEY]) is int
    assert set(written) == legacy_keys | {SCHEMA_VERSION_KEY}
    assert version_keys(written) == 1
    assert target.name in replace_spy.targets


@pytest.mark.parametrize("family", FAMILIES, ids=FAMILY_IDS)
def test_legitimate_write_keeps_explicit_version_one(
    workspace: Workspace,
    family: Family,
) -> None:
    """Reescribir un archivo ya versionado conserva una única versión 1."""
    target = family.path(workspace)
    set_version(target, CURRENT_SCHEMA_VERSION)

    family.write(workspace)

    written = load_json(target)
    assert written[SCHEMA_VERSION_KEY] == CURRENT_SCHEMA_VERSION
    assert version_keys(written) == 1


def test_settings_write_keeps_its_six_fields_plus_version(
    workspace: Workspace,
) -> None:
    """settings.json conserva sus seis campos y agrega la versión."""
    fixture = load_json(fixture_path("profile_config/settings.json"))

    _save_settings(workspace)

    assert load_json(workspace.config_dir / "settings.json") == {
        **fixture,
        "schema_version": 1,
    }


def test_budget_write_versions_only_the_root(workspace: Workspace) -> None:
    """El presupuesto lleva versión en la raíz, no en sus elementos."""
    repository = workspace.repository()

    repository.save(repository.load(2026, 3))

    written = load_json(workspace.data_dir / "presupuesto_2026-03.json")
    assert written[SCHEMA_VERSION_KEY] == 1
    for collection in ("categories", "transactions", "recurring_items"):
        assert written[collection]
        for item in written[collection]:
            assert SCHEMA_VERSION_KEY not in item


def test_new_files_are_born_with_schema_version(tmp_path: Path) -> None:
    """Un archivo creado desde cero nace con schema_version 1."""
    repository = BudgetRepository(tmp_path / "datos_nuevos")

    repository.save(MonthlyBudget.empty(2026, 4))
    repository.save_accounts([])
    repository.save_debts([])
    repository.save_debt_payments([])
    repository.save_debt_snapshots([])
    repository.save_monthly_closures([])

    written = sorted(repository.data_dir.glob("*.json"))
    assert len(written) == 6
    for path in written:
        assert load_json(path)[SCHEMA_VERSION_KEY] == CURRENT_SCHEMA_VERSION


# ---------------------------------------------------------------------------
# Las diez familias: rechazo fail-closed
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("operation", ("read", "write"))
@pytest.mark.parametrize("family", FAMILIES, ids=FAMILY_IDS)
def test_future_version_is_rejected_without_any_write(
    workspace: Workspace,
    replace_spy: ReplaceSpy,
    family: Family,
    operation: str,
) -> None:
    """Una versión futura aborta lectura y escritura sin tocar el disco."""
    set_version(family.path(workspace), FUTURE_VERSION)

    error = assert_rejected_without_effects(
        workspace,
        replace_spy,
        lambda: getattr(family, operation)(workspace),
        UnsupportedSchemaVersionError,
    )

    assert isinstance(error, UnsupportedSchemaVersionError)
    assert error.observed_version == FUTURE_VERSION
    assert error.supported_version == CURRENT_SCHEMA_VERSION
    assert error.document_name == Path(family.target).name


@pytest.mark.parametrize("version", INVALID_VERSIONS, ids=INVALID_IDS)
@pytest.mark.parametrize("family", FAMILIES, ids=FAMILY_IDS)
def test_invalid_version_is_rejected_without_any_write(
    workspace: Workspace,
    replace_spy: ReplaceSpy,
    family: Family,
    version: object,
) -> None:
    """Una versión inválida aborta la lectura sin tocar el disco."""
    set_version(family.path(workspace), version)

    error = assert_rejected_without_effects(
        workspace,
        replace_spy,
        lambda: family.read(workspace),
        InvalidSchemaVersionError,
    )

    assert error.document_name == Path(family.target).name


@pytest.mark.parametrize("family", FAMILIES, ids=FAMILY_IDS)
def test_invalid_version_blocks_legitimate_write(
    workspace: Workspace,
    replace_spy: ReplaceSpy,
    family: Family,
) -> None:
    """Una versión inválida también aborta la escritura legítima."""
    set_version(family.path(workspace), "1")

    assert_rejected_without_effects(
        workspace,
        replace_spy,
        lambda: family.write(workspace),
        InvalidSchemaVersionError,
    )


# ---------------------------------------------------------------------------
# BudgetRepository: sin respaldo previo ni escritura colateral
# ---------------------------------------------------------------------------


DIRECT_SAVERS = (
    ("presupuesto_2026-03.json", lambda r: r.save(MonthlyBudget.empty(2026, 3))),
    ("cuentas.json", lambda r: r.save_accounts([])),
    ("deudas.json", lambda r: r.save_debts([])),
    ("debt_payments.json", lambda r: r.save_debt_payments([])),
    ("debt_snapshots.json", lambda r: r.save_debt_snapshots([])),
    ("monthly_closures.json", lambda r: r.save_monthly_closures([])),
)


@pytest.mark.parametrize("version", (FUTURE_VERSION, None), ids=("futura", "invalida"))
@pytest.mark.parametrize(
    ("file_name", "saver"),
    DIRECT_SAVERS,
    ids=[name for name, _ in DIRECT_SAVERS],
)
def test_repository_save_over_incompatible_file_makes_no_backup(
    workspace: Workspace,
    replace_spy: ReplaceSpy,
    file_name: str,
    saver: Callable[[BudgetRepository], Any],
    version: object,
) -> None:
    """Guardar sin leer antes tampoco respalda ni pisa un archivo incompatible."""
    repository = workspace.repository()
    set_version(workspace.data_dir / file_name, version)
    expected = (
        UnsupportedSchemaVersionError
        if version == FUTURE_VERSION
        else InvalidSchemaVersionError
    )

    assert_rejected_without_effects(
        workspace,
        replace_spy,
        lambda: saver(repository),
        expected,
    )

    assert list(repository.backup_dir.iterdir()) == []


def test_repository_historical_backup_still_happens_for_legacy_file(
    workspace: Workspace,
) -> None:
    """El respaldo previo histórico sigue ocurriendo en un guardado válido."""
    repository = workspace.repository()
    before = repository.accounts_path.read_bytes()

    repository.save_accounts(repository.load_accounts())

    copies = list(repository.backup_dir.glob("cuentas.backup_*.json"))
    assert len(copies) == 1
    assert copies[0].read_bytes() == before
    assert SCHEMA_VERSION_KEY not in load_json(copies[0])


def test_repository_totals_reject_a_future_month(
    workspace: Workspace,
    replace_spy: ReplaceSpy,
) -> None:
    """El recorrido de todos los meses también se detiene ante uno futuro."""
    set_version(workspace.data_dir / "presupuesto_2026-03.json", FUTURE_VERSION)

    assert_rejected_without_effects(
        workspace,
        replace_spy,
        lambda: workspace.repository().debt_payment_totals(),
        UnsupportedSchemaVersionError,
    )


# ---------------------------------------------------------------------------
# BudgetService: reescritura legacy de budget_id
# ---------------------------------------------------------------------------


def test_budget_service_legacy_rewrite_adds_schema_version(
    workspace: Workspace,
    replace_spy: ReplaceSpy,
) -> None:
    """La reescritura por budget_id faltante agrega schema_version 1."""
    path = make_budget_without_ids(workspace)
    raw = load_json(path)

    workspace.budget_service().obtener_presupuestos()

    written = load_json(path)
    assert written[SCHEMA_VERSION_KEY] == CURRENT_SCHEMA_VERSION
    assert version_keys(written) == 1
    assert all(item["budget_id"] for item in written["categories"])
    assert written["campo_futuro_archivo"] == 7
    assert written["transactions"] == raw["transactions"]
    assert written["recurring_items"] == raw["recurring_items"]
    assert written["updated_at"] == raw["updated_at"]
    assert replace_spy.targets == ["presupuesto_2026-03.json"]


def test_budget_service_second_read_after_rewrite_does_not_write(
    workspace: Workspace,
    replace_spy: ReplaceSpy,
) -> None:
    """Tras la reescritura versionada, la segunda lectura no escribe."""
    path = make_budget_without_ids(workspace)
    service = workspace.budget_service()
    first = [item.id for item in service.obtener_presupuestos()]
    after_first = path.read_bytes()

    second = [item.id for item in service.obtener_presupuestos()]

    assert second == first
    assert path.read_bytes() == after_first
    assert replace_spy.targets == ["presupuesto_2026-03.json"]


def test_budget_service_does_not_rewrite_only_to_add_version(
    workspace: Workspace,
    replace_spy: ReplaceSpy,
) -> None:
    """Con todos los budget_id presentes no se escribe para versionar."""
    path = workspace.data_dir / "presupuesto_2026-03.json"
    before = files_snapshot(workspace.root)

    workspace.budget_service().obtener_presupuestos()

    assert files_snapshot(workspace.root) == before
    assert SCHEMA_VERSION_KEY not in load_json(path)
    assert replace_spy.targets == []


@pytest.mark.parametrize(
    ("version", "expected"),
    (
        (FUTURE_VERSION, UnsupportedSchemaVersionError),
        (999, UnsupportedSchemaVersionError),
        ("1", InvalidSchemaVersionError),
        (True, InvalidSchemaVersionError),
        (None, InvalidSchemaVersionError),
        (0, InvalidSchemaVersionError),
    ),
    ids=("futura", "muy_futura", "texto", "booleano", "null", "cero"),
)
def test_budget_service_blocks_before_generating_missing_ids(
    workspace: Workspace,
    replace_spy: ReplaceSpy,
    version: object,
    expected: type[SchemaVersionError],
) -> None:
    """Con versión incompatible no se generan ni persisten budget_id."""
    path = make_budget_without_ids(workspace)
    set_version(path, version)
    service = workspace.budget_service()

    assert_rejected_without_effects(
        workspace,
        replace_spy,
        service.obtener_presupuestos,
        expected,
    )

    assert "budget_id" not in load_json(path)["categories"][1]


# ---------------------------------------------------------------------------
# CategoryService: creación y sincronización al leer
# ---------------------------------------------------------------------------


def test_category_service_creates_missing_file_with_schema_version(
    tmp_path: Path,
) -> None:
    """categorias.json creado al leer nace con schema_version 1."""
    service = CategoryService(data_dir=tmp_path / "datos_nuevos")

    service.listar_categorias()

    written = load_json(service.categories_path)
    assert written[SCHEMA_VERSION_KEY] == CURRENT_SCHEMA_VERSION
    assert written["categories"]


def test_category_service_sync_write_adds_schema_version(
    workspace: Workspace,
    replace_spy: ReplaceSpy,
) -> None:
    """La sincronización desde presupuestos guarda con schema_version 1."""
    make_budget_with_unsynced_category(workspace)

    categories = workspace.category_service().listar_categorias()

    written = load_json(workspace.data_dir / "categorias.json")
    assert "Mascota ficticia" in {item.nombre for item in categories}
    assert written[SCHEMA_VERSION_KEY] == CURRENT_SCHEMA_VERSION
    assert replace_spy.targets == ["categorias.json"]


@pytest.mark.parametrize(
    ("version", "expected"),
    ((FUTURE_VERSION, UnsupportedSchemaVersionError), (None, InvalidSchemaVersionError)),
    ids=("futura", "invalida"),
)
def test_category_service_blocks_before_synchronizing(
    workspace: Workspace,
    replace_spy: ReplaceSpy,
    version: object,
    expected: type[SchemaVersionError],
) -> None:
    """Con categorias.json incompatible no se sincroniza ni se escribe."""
    make_budget_with_unsynced_category(workspace)
    set_version(workspace.data_dir / "categorias.json", version)
    service = workspace.category_service()

    assert_rejected_without_effects(
        workspace,
        replace_spy,
        service.listar_categorias,
        expected,
    )


def test_category_service_does_not_skip_a_future_budget_when_synchronizing(
    workspace: Workspace,
    replace_spy: ReplaceSpy,
) -> None:
    """Un presupuesto futuro detiene la sincronización en vez de ignorarse."""
    make_budget_with_unsynced_category(workspace)
    set_version(workspace.data_dir / "presupuesto_2026-03.json", FUTURE_VERSION)
    service = workspace.category_service()

    assert_rejected_without_effects(
        workspace,
        replace_spy,
        service.listar_categorias,
        UnsupportedSchemaVersionError,
    )


def test_category_service_does_not_create_file_next_to_a_future_budget(
    workspace: Workspace,
    replace_spy: ReplaceSpy,
) -> None:
    """Sin categorias.json y con un presupuesto futuro, no se crea nada."""
    (workspace.data_dir / "categorias.json").unlink()
    set_version(workspace.data_dir / "presupuesto_2026-03.json", FUTURE_VERSION)
    service = workspace.category_service()

    assert_rejected_without_effects(
        workspace,
        replace_spy,
        service.listar_categorias,
        UnsupportedSchemaVersionError,
    )

    assert not service.categories_path.exists()


# ---------------------------------------------------------------------------
# SettingsService
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("version", "expected"),
    ((FUTURE_VERSION, UnsupportedSchemaVersionError), ("1", InvalidSchemaVersionError)),
    ids=("futura", "invalida"),
)
def test_settings_service_save_over_incompatible_file_creates_nothing(
    workspace: Workspace,
    replace_spy: ReplaceSpy,
    version: object,
    expected: type[SchemaVersionError],
) -> None:
    """Guardar sobre settings.json incompatible no crea carpetas ni escribe."""
    set_version(workspace.config_dir / "settings.json", version)
    service = workspace.settings_service()
    datos = {
        **load_json(fixture_path("profile_config/settings.json")),
        "carpeta_reportes": "reportes_nuevos",
        "carpeta_respaldo": "respaldo_nuevo",
    }

    assert_rejected_without_effects(
        workspace,
        replace_spy,
        lambda: service.guardar_configuracion(datos),
        expected,
    )

    assert not (workspace.root / "reportes_nuevos").exists()
    assert not (workspace.root / "respaldo_nuevo").exists()


def test_settings_service_keeps_legacy_appearance_and_defaults(
    workspace: Workspace,
) -> None:
    """Las preferencias históricas siguen cargando con archivo versionado."""
    path = workspace.config_dir / "settings.json"
    dump_json(path, {"schema_version": 1, "apariencia": "oscuro"})

    config = workspace.settings_service().cargar_configuracion()

    assert config.apariencia == "oscuro"
    assert config.moneda_principal == "CLP"
    assert config.cifrado_reportes is True


# ---------------------------------------------------------------------------
# ProfileService: validación previa a cualquier mutación de arranque
# ---------------------------------------------------------------------------


def test_profile_service_bootstrap_files_are_born_with_schema_version(
    tmp_path: Path,
) -> None:
    """En el primer arranque catálogo y perfil activo nacen versionados."""
    service = Workspace(tmp_path).profile_service()

    assert load_json(service.registry_path) == {
        "perfiles": [{"nombre": "Personal", "slug": "personal"}],
        "schema_version": 1,
    }
    assert load_json(service.active_path) == {
        "schema_version": 1,
        "slug": "personal",
    }


@pytest.mark.parametrize(
    ("version", "expected"),
    ((FUTURE_VERSION, UnsupportedSchemaVersionError), (True, InvalidSchemaVersionError)),
    ids=("futura", "invalida"),
)
def test_profile_service_future_registry_blocks_before_creating_active_profile(
    workspace: Workspace,
    replace_spy: ReplaceSpy,
    version: object,
    expected: type[SchemaVersionError],
) -> None:
    """Con catálogo incompatible no se crea perfil_activo ni carpetas."""
    (workspace.profiles_root / "perfil_activo.json").unlink()
    set_version(workspace.profiles_root / "perfiles.json", version)

    assert_rejected_without_effects(
        workspace,
        replace_spy,
        workspace.profile_service,
        expected,
    )

    assert not (workspace.profiles_root / "perfil_activo.json").exists()
    assert not (workspace.profiles_root / "personal").exists()


@pytest.mark.parametrize(
    ("version", "expected"),
    ((FUTURE_VERSION, UnsupportedSchemaVersionError), (None, InvalidSchemaVersionError)),
    ids=("futura", "invalida"),
)
def test_profile_service_future_active_file_blocks_before_creating_registry(
    workspace: Workspace,
    replace_spy: ReplaceSpy,
    version: object,
    expected: type[SchemaVersionError],
) -> None:
    """Con perfil activo incompatible no se crea ni modifica el catálogo."""
    (workspace.profiles_root / "perfiles.json").unlink()
    set_version(workspace.profiles_root / "perfil_activo.json", version)

    assert_rejected_without_effects(
        workspace,
        replace_spy,
        workspace.profile_service,
        expected,
    )

    assert not (workspace.profiles_root / "perfiles.json").exists()
    assert not (workspace.profiles_root / "personal").exists()


def test_profile_service_future_active_file_blocks_before_registering_personal(
    workspace: Workspace,
    replace_spy: ReplaceSpy,
) -> None:
    """Un catálogo legacy sin "personal" no se completa si el activo es futuro."""
    registry = workspace.profiles_root / "perfiles.json"
    dump_json(
        registry,
        {"perfiles": [{"nombre": "Hogar Ficticio", "slug": "hogar_ficticio"}]},
    )
    set_version(workspace.profiles_root / "perfil_activo.json", FUTURE_VERSION)

    assert_rejected_without_effects(
        workspace,
        replace_spy,
        workspace.profile_service,
        UnsupportedSchemaVersionError,
    )

    assert load_json(registry) == {
        "perfiles": [{"nombre": "Hogar Ficticio", "slug": "hogar_ficticio"}],
    }


def test_profile_service_future_registry_blocks_before_copying_legacy_data(
    workspace: Workspace,
    replace_spy: ReplaceSpy,
) -> None:
    """Con catálogo futuro no se copian datos planos históricos."""
    legacy_data = workspace.root / "legacy_data"
    legacy_data.mkdir()
    shutil.copyfile(
        fixture_path("profile_data/cuentas.json"),
        legacy_data / "cuentas.json",
    )
    shutil.copyfile(
        fixture_path("profile_data/presupuesto_2026-03.json"),
        legacy_data / "presupuesto_2026-03.json",
    )
    set_version(workspace.profiles_root / "perfiles.json", FUTURE_VERSION)

    assert_rejected_without_effects(
        workspace,
        replace_spy,
        workspace.profile_service,
        UnsupportedSchemaVersionError,
    )

    assert not (workspace.profiles_root / "personal").exists()


@pytest.mark.parametrize(
    ("file_name", "action"),
    (
        ("perfiles.json", lambda s: s.crear_perfil("Negocio Ficticio")),
        ("perfiles.json", lambda s: s.seleccionar_perfil("personal")),
        ("perfiles.json", lambda s: s.asegurar_demo_registrado()),
        ("perfil_activo.json", lambda s: s.seleccionar_perfil("personal")),
        ("perfil_activo.json", lambda s: s.crear_perfil("Negocio Ficticio")),
    ),
    ids=(
        "catalogo_crear",
        "catalogo_seleccionar",
        "catalogo_demo",
        "activo_seleccionar",
        "activo_crear",
    ),
)
def test_profile_service_running_instance_blocks_mutations_on_future_file(
    workspace: Workspace,
    replace_spy: ReplaceSpy,
    file_name: str,
    action: Callable[[ProfileService], Any],
) -> None:
    """Un servicio ya construido tampoco muta si el archivo se vuelve futuro."""
    service = workspace.profile_service()
    set_version(workspace.profiles_root / file_name, FUTURE_VERSION)

    assert_rejected_without_effects(
        workspace,
        replace_spy,
        lambda: action(service),
        UnsupportedSchemaVersionError,
    )


def test_profile_service_working_period_does_not_hide_a_future_month(
    workspace: Workspace,
    replace_spy: ReplaceSpy,
) -> None:
    """El cálculo del periodo de trabajo no trata un mes futuro como vacío."""
    service = workspace.profile_service()
    data_dir = service.obtener_perfil("personal").data_dir
    shutil.copyfile(
        fixture_path("profile_data/presupuesto_2026-03.json"),
        data_dir / "presupuesto_2026-03.json",
    )
    BudgetRepository(data_dir)
    set_version(data_dir / "presupuesto_2026-03.json", FUTURE_VERSION)

    assert_rejected_without_effects(
        workspace,
        replace_spy,
        lambda: service.obtener_periodo_trabajo("personal"),
        UnsupportedSchemaVersionError,
    )


def test_profile_service_keeps_current_errors_unrelated_to_versioning(
    workspace: Workspace,
) -> None:
    """Un catálogo corrupto sigue produciendo el error JSON actual."""
    (workspace.profiles_root / "perfiles.json").write_text(
        '{"perfiles": [',
        encoding="utf-8",
    )

    with pytest.raises(ValueError) as excinfo:
        workspace.profile_service()

    assert excinfo.type is json.JSONDecodeError
