"""Pruebas de los metadatos globales de perfil (Etapa 22E).

Cada perfil tiene un ``profile_metadata.json`` en su raíz con dos versiones
que significan cosas distintas:

- ``schema_version`` versiona la estructura de ese archivo JSON y la
  gestiona la infraestructura de 22D (``VersionedJsonStore``);
- ``profile_format_version`` versiona el perfil completo.

Un perfil histórico sin metadatos se asume de formato 1 implícito, pero sólo
se etiqueta después de comprobar que ninguno de sus archivos es incompatible.
Metadatos ausentes y metadatos corruptos son estados distintos: sólo la
ausencia permite esa creación inicial.
"""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Any, Callable

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from avalancha import __version__  # noqa: E402
from avalancha.storage import BudgetRepository  # noqa: E402
from core import json_file_store  # noqa: E402
from core.profile_metadata import (  # noqa: E402
    APP_VERSION_KEY,
    CURRENT_PROFILE_FORMAT_VERSION,
    LEGACY_IMPLICIT_PROFILE_FORMAT_VERSION,
    PROFILE_FORMAT_VERSION_KEY,
    PROFILE_METADATA_FILE_NAME,
    PROFILE_NAME_KEY,
    PROFILE_SLUG_KEY,
    InvalidProfileMetadataError,
    ProfileMetadata,
    ProfileMetadataError,
    ProfileMetadataPolicy,
    UnreadableProfileDocumentError,
    UnsupportedProfileFormatVersionError,
)
from core.schema_versioning import (  # noqa: E402
    CURRENT_SCHEMA_VERSION,
    SCHEMA_VERSION_KEY,
    InvalidSchemaVersionError,
    SchemaVersionError,
    UnsupportedSchemaVersionError,
)
from core.versioned_json_store import VersionedJsonStore  # noqa: E402
from services.backup_service import ProfileBackupService  # noqa: E402
from services.category_service import CategoryService  # noqa: E402
from services.demo_profile_service import DemoProfileService  # noqa: E402
from services.profile_metadata_service import (  # noqa: E402
    ProfileDocumentInventory,
    ProfileMetadataService,
)
from services.profile_service import (  # noqa: E402
    PERFIL_DEMO,
    PerfilAplicacion,
    ProfileService,
)
from services.settings_service import SettingsService  # noqa: E402
from ui_pyside6.main_window import MainWindow  # noqa: E402


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
INTERNAL_DOCUMENTS = (
    "data/presupuesto_2026-03.json",
    "data/presupuesto_2026-04.json",
    "data/cuentas.json",
    "data/deudas.json",
    "data/debt_payments.json",
    "data/debt_snapshots.json",
    "data/monthly_closures.json",
    "data/categorias.json",
    "config/settings.json",
)
INVALID_FORMAT_VERSIONS = (0, -1, "1", 1.0, True, False, None)
INVALID_FORMAT_IDS = ("cero", "negativo", "texto", "float", "true", "false", "null")
FUTURE_FORMAT = CURRENT_PROFILE_FORMAT_VERSION + 1
FUTURE_SCHEMA = CURRENT_SCHEMA_VERSION + 1
SECRET = "SALDO-PRIVADO-987654321"
HOGAR = "hogar_ficticio"
VALID_DOCUMENT = {
    PROFILE_FORMAT_VERSION_KEY: 1,
    PROFILE_SLUG_KEY: HOGAR,
    PROFILE_NAME_KEY: "Hogar Ficticio",
    APP_VERSION_KEY: "0.1.0",
}


class ReplaceSpy:
    """Envuelve os.replace: registra destinos y puede fallar en algunos."""

    def __init__(self) -> None:
        """Guarda la función real, los destinos y los nombres a bloquear."""
        self.targets: list[str] = []
        self.fail_on: set[str] = set()
        self._real = os.replace

    def __call__(self, source: Any, target: Any) -> None:
        """Registra el destino y ejecuta o bloquea el reemplazo."""
        name = Path(target).name
        self.targets.append(name)
        if name in self.fail_on:
            raise OSError("reemplazo bloqueado por la prueba")
        self._real(source, target)


def fixture_path(relative: str) -> Path:
    """Devuelve la ruta de un fixture legacy schema_v1."""
    return FIXTURES_ROOT.joinpath(*relative.split("/"))


def load_json(path: Path) -> Any:
    """Carga un archivo JSON del filesystem."""
    return json.loads(path.read_text(encoding="utf-8"))


def dump_json(path: Path, document: Any) -> None:
    """Escribe un documento de prueba sin pasar por producción."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")


def set_key(path: Path, key: str, value: object) -> None:
    """Asigna una clave en la raíz de un documento existente."""
    dump_json(path, {**load_json(path), key: value})


def tree_snapshot(root: Path) -> tuple[dict[str, bytes], frozenset[str]]:
    """Captura archivos y carpetas para detectar cualquier efecto en disco."""
    files = {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }
    folders = frozenset(
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_dir()
    )
    return files, folders


def profile_at(root: Path, slug: str = HOGAR, name: str = "Hogar Ficticio") -> PerfilAplicacion:
    """Describe un perfil ubicado bajo la raíz temporal de perfiles."""
    return PerfilAplicacion(id=slug, nombre=name, raiz=root / "perfiles" / slug)


def make_profile_folders(profile: PerfilAplicacion) -> None:
    """Crea las carpetas internas de un perfil, vacías."""
    for folder in (profile.data_dir, profile.reports_dir, profile.config_dir):
        folder.mkdir(parents=True, exist_ok=True)
    (profile.data_dir / "backups").mkdir(exist_ok=True)


def make_legacy_profile(root: Path, slug: str = HOGAR, name: str = "Hogar Ficticio") -> PerfilAplicacion:
    """Crea un perfil histórico con datos legacy y sin metadatos."""
    profile = profile_at(root, slug, name)
    make_profile_folders(profile)
    for file_name in PROFILE_DATA_FILES:
        shutil.copyfile(
            fixture_path(f"profile_data/{file_name}"),
            profile.data_dir / file_name,
        )
    shutil.copyfile(
        fixture_path("profile_data/presupuesto_2026-03.json"),
        profile.data_dir / "presupuesto_2026-04.json",
    )
    set_key(profile.data_dir / "presupuesto_2026-04.json", "month", 4)
    shutil.copyfile(
        fixture_path("profile_config/settings.json"),
        profile.config_dir / "settings.json",
    )
    return profile


def install_catalog(root: Path) -> Path:
    """Instala el catálogo legacy: personal y hogar, con hogar activo."""
    profiles_root = root / "perfiles"
    profiles_root.mkdir(parents=True, exist_ok=True)
    for name in ("perfiles.json", "perfil_activo.json"):
        shutil.copyfile(fixture_path(f"catalog/{name}"), profiles_root / name)
    return profiles_root


def build_profile_service(root: Path) -> ProfileService:
    """Crea el servicio de perfiles sobre la raíz temporal."""
    return ProfileService(
        profiles_root=root / "perfiles",
        legacy_data_dir=root / "legacy_data",
        legacy_reports_dir=root / "legacy_reports",
        legacy_config_dir=root / "legacy_config",
    )


def metadata_file(root: Path, slug: str = HOGAR) -> Path:
    """Devuelve la ruta de metadatos de un perfil de la raíz temporal."""
    return root / "perfiles" / slug / PROFILE_METADATA_FILE_NAME


def write_metadata(root: Path, slug: str = HOGAR, **overrides: object) -> Path:
    """Escribe metadatos explícitos para un perfil, con cambios opcionales."""
    document = {
        SCHEMA_VERSION_KEY: CURRENT_SCHEMA_VERSION,
        **VALID_DOCUMENT,
        PROFILE_SLUG_KEY: slug,
        **overrides,
    }
    path = metadata_file(root, slug)
    dump_json(path, document)
    return path


def assert_fails_without_effects(
    root: Path,
    spy: ReplaceSpy,
    action: Callable[[], Any],
    expected: type[Exception],
) -> Exception:
    """Exige que la acción falle sin dejar ningún efecto en el filesystem."""
    before = tree_snapshot(root)
    replaced_before = list(spy.targets)

    with pytest.raises(Exception) as excinfo:
        action()

    assert excinfo.type is expected
    assert tree_snapshot(root) == before
    assert spy.targets == replaced_before
    return excinfo.value


@pytest.fixture(scope="session")
def app() -> QApplication:
    """Crea una QApplication única para la prueba de arranque."""
    return QApplication.instance() or QApplication([])


@pytest.fixture()
def spy(monkeypatch: pytest.MonkeyPatch) -> ReplaceSpy:
    """Registra los reemplazos atómicos ejecutados durante la prueba."""
    replace_spy = ReplaceSpy()
    monkeypatch.setattr(json_file_store.os, "replace", replace_spy)
    return replace_spy


@pytest.fixture()
def legacy_root(tmp_path: Path) -> Path:
    """Raíz con catálogo legacy, perfil hogar con datos y personal vacío."""
    install_catalog(tmp_path)
    make_legacy_profile(tmp_path)
    make_profile_folders(profile_at(tmp_path, "personal", "Personal"))
    return tmp_path


# ---------------------------------------------------------------------------
# Constantes y conceptos
# ---------------------------------------------------------------------------


def test_profile_format_constants_are_the_single_source_of_truth() -> None:
    """El formato global vive en constantes propias y hoy vale 1."""
    assert CURRENT_PROFILE_FORMAT_VERSION == 1
    assert LEGACY_IMPLICIT_PROFILE_FORMAT_VERSION == 1
    assert type(CURRENT_PROFILE_FORMAT_VERSION) is int
    assert ProfileMetadataPolicy.CURRENT_VERSION is CURRENT_PROFILE_FORMAT_VERSION
    assert (
        ProfileMetadataPolicy.LEGACY_IMPLICIT_VERSION
        is LEGACY_IMPLICIT_PROFILE_FORMAT_VERSION
    )
    assert PROFILE_METADATA_FILE_NAME == "profile_metadata.json"


def test_profile_format_version_and_schema_version_are_distinct_concepts() -> None:
    """El modelo conoce el formato del perfil; el esquema lo agrega el almacén."""
    metadata = ProfileMetadata(HOGAR, "Hogar Ficticio", "0.1.0")

    document = metadata.to_document()

    assert PROFILE_FORMAT_VERSION_KEY != SCHEMA_VERSION_KEY
    assert SCHEMA_VERSION_KEY not in document
    assert document == VALID_DOCUMENT


# ---------------------------------------------------------------------------
# Política: metadatos válidos
# ---------------------------------------------------------------------------


def test_policy_parses_valid_metadata() -> None:
    """Un documento completo y coherente se interpreta sin cambios."""
    metadata = ProfileMetadataPolicy().parse(
        {SCHEMA_VERSION_KEY: 1, **VALID_DOCUMENT},
        expected_slug=HOGAR,
    )

    assert metadata == ProfileMetadata(
        profile_slug=HOGAR,
        profile_name="Hogar Ficticio",
        app_version="0.1.0",
        profile_format_version=1,
    )
    assert metadata.to_document() == VALID_DOCUMENT


def test_policy_parse_does_not_mutate_the_document() -> None:
    """Interpretar metadatos no altera el documento recibido."""
    document = dict(VALID_DOCUMENT)

    ProfileMetadataPolicy().parse(document, expected_slug=HOGAR)

    assert document == VALID_DOCUMENT


def test_policy_builds_current_format_by_default() -> None:
    """Sin formato explícito se construyen metadatos del formato actual."""
    metadata = ProfileMetadataPolicy().build(HOGAR, "Hogar Ficticio", "0.1.0")

    assert metadata.profile_format_version == CURRENT_PROFILE_FORMAT_VERSION
    assert metadata.to_document() == VALID_DOCUMENT


@pytest.mark.parametrize("version", (FUTURE_FORMAT, 999, 0, -1, "1", True, 1.0))
def test_policy_cannot_build_metadata_for_other_formats(version: object) -> None:
    """No se pueden construir metadatos de un formato futuro o inválido."""
    with pytest.raises(ProfileMetadataError):
        ProfileMetadataPolicy().build(
            HOGAR,
            "Hogar Ficticio",
            "0.1.0",
            profile_format_version=version,  # type: ignore[arg-type]
        )


# ---------------------------------------------------------------------------
# Política: formato futuro e inválido
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("version", (FUTURE_FORMAT, 3, 999))
def test_policy_future_format_is_unsupported(version: int) -> None:
    """Un formato global mayor que el actual se rechaza como no soportado."""
    with pytest.raises(UnsupportedProfileFormatVersionError) as excinfo:
        ProfileMetadataPolicy().parse(
            {**VALID_DOCUMENT, PROFILE_FORMAT_VERSION_KEY: version},
            expected_slug=HOGAR,
        )

    assert excinfo.value.observed_version == version
    assert excinfo.value.supported_version == CURRENT_PROFILE_FORMAT_VERSION
    assert excinfo.value.profile_slug == HOGAR


@pytest.mark.parametrize("version", INVALID_FORMAT_VERSIONS, ids=INVALID_FORMAT_IDS)
def test_policy_invalid_format_version_is_rejected(version: object) -> None:
    """Cero, negativo, texto, flotante, booleano y null son inválidos."""
    with pytest.raises(InvalidProfileMetadataError) as excinfo:
        ProfileMetadataPolicy().parse(
            {**VALID_DOCUMENT, PROFILE_FORMAT_VERSION_KEY: version},
            expected_slug=HOGAR,
        )

    assert excinfo.value.field == PROFILE_FORMAT_VERSION_KEY


def test_policy_requires_profile_format_version_in_existing_metadata() -> None:
    """En un archivo de metadatos el formato global es obligatorio.

    El formato implícito sólo aplica a perfiles sin archivo de metadatos.
    """
    document = dict(VALID_DOCUMENT)
    del document[PROFILE_FORMAT_VERSION_KEY]

    with pytest.raises(InvalidProfileMetadataError) as excinfo:
        ProfileMetadataPolicy().parse(document, expected_slug=HOGAR)

    assert excinfo.value.field == PROFILE_FORMAT_VERSION_KEY


@pytest.mark.parametrize(
    ("key", "value"),
    (
        (PROFILE_SLUG_KEY, ""),
        (PROFILE_SLUG_KEY, "   "),
        (PROFILE_SLUG_KEY, 7),
        (PROFILE_SLUG_KEY, None),
        (PROFILE_SLUG_KEY, "otro_perfil"),
        (PROFILE_NAME_KEY, ""),
        (PROFILE_NAME_KEY, "   "),
        (PROFILE_NAME_KEY, ["Hogar"]),
        (PROFILE_NAME_KEY, None),
        (APP_VERSION_KEY, ""),
        (APP_VERSION_KEY, "  "),
        (APP_VERSION_KEY, 1),
        (APP_VERSION_KEY, None),
    ),
)
def test_policy_rejects_invalid_text_fields(key: str, value: object) -> None:
    """Slug, nombre y versión de producto deben ser textos no vacíos."""
    with pytest.raises(InvalidProfileMetadataError) as excinfo:
        ProfileMetadataPolicy().parse(
            {**VALID_DOCUMENT, key: value},
            expected_slug=HOGAR,
        )

    assert excinfo.value.field == key
    assert excinfo.value.profile_slug == HOGAR


@pytest.mark.parametrize("key", (PROFILE_SLUG_KEY, PROFILE_NAME_KEY, APP_VERSION_KEY))
def test_policy_rejects_missing_text_fields(key: str) -> None:
    """La ausencia de slug, nombre o versión de producto es inválida."""
    document = dict(VALID_DOCUMENT)
    del document[key]

    with pytest.raises(InvalidProfileMetadataError) as excinfo:
        ProfileMetadataPolicy().parse(document, expected_slug=HOGAR)

    assert excinfo.value.field == key


def test_policy_slug_mismatch_is_not_corrected() -> None:
    """Un slug distinto del esperado es un error, no algo que reparar."""
    document = {**VALID_DOCUMENT, PROFILE_SLUG_KEY: "personal"}

    with pytest.raises(InvalidProfileMetadataError) as excinfo:
        ProfileMetadataPolicy().parse(document, expected_slug=HOGAR)

    assert excinfo.value.field == PROFILE_SLUG_KEY
    assert document[PROFILE_SLUG_KEY] == "personal"


@pytest.mark.parametrize("root", ([], [VALID_DOCUMENT], "texto", 7, None))
def test_policy_rejects_non_object_metadata(root: object) -> None:
    """Los metadatos deben ser un objeto JSON."""
    with pytest.raises(InvalidProfileMetadataError) as excinfo:
        ProfileMetadataPolicy().parse(root, expected_slug=HOGAR)

    assert excinfo.value.field == "documento"


def test_policy_future_format_takes_precedence_over_other_fields() -> None:
    """Con formato futuro no se juzga el resto de una estructura desconocida."""
    with pytest.raises(UnsupportedProfileFormatVersionError):
        ProfileMetadataPolicy().parse(
            {PROFILE_FORMAT_VERSION_KEY: FUTURE_FORMAT, "estructura": "nueva"},
            expected_slug=HOGAR,
        )


# ---------------------------------------------------------------------------
# Errores de dominio
# ---------------------------------------------------------------------------


def test_profile_metadata_errors_are_not_value_errors() -> None:
    """Ningún error de formato de perfil puede absorberse como ValueError."""
    for error_type in (
        ProfileMetadataError,
        UnsupportedProfileFormatVersionError,
        InvalidProfileMetadataError,
        UnreadableProfileDocumentError,
    ):
        assert issubclass(error_type, ProfileMetadataError)
        assert not issubclass(error_type, ValueError)
    assert not issubclass(ProfileMetadataError, SchemaVersionError)


def test_profile_metadata_errors_identify_profile_without_content() -> None:
    """Los errores nombran el perfil y el campo, nunca el valor recibido."""
    with pytest.raises(InvalidProfileMetadataError) as excinfo:
        ProfileMetadataPolicy().parse(
            {**VALID_DOCUMENT, PROFILE_NAME_KEY: {"saldo": SECRET}},
            expected_slug=HOGAR,
        )
    invalid = excinfo.value
    unsupported = UnsupportedProfileFormatVersionError(7, 1, HOGAR)
    unreadable = UnreadableProfileDocumentError("cuentas.json", HOGAR)

    assert str(invalid).startswith(f"perfil {HOGAR}: ")
    assert PROFILE_NAME_KEY in str(invalid)
    assert unsupported.observed_version == 7
    assert unsupported.supported_version == 1
    assert unreadable.document_name == "cuentas.json"
    for error in (invalid, unsupported, unreadable):
        assert error.profile_slug == HOGAR
        for text in (str(error), repr(error), repr(error.args), repr(vars(error))):
            assert SECRET not in text


# ---------------------------------------------------------------------------
# Inventario de archivos del perfil
# ---------------------------------------------------------------------------


def test_inventory_lists_exactly_the_existing_versioned_documents(
    tmp_path: Path,
) -> None:
    """El inventario enumera sólo los JSON ordinarios presentes del perfil."""
    profile = make_legacy_profile(tmp_path)
    (profile.data_dir / "backups" / "cuentas.backup_20260301T000000.json").write_text(
        "{}",
        encoding="utf-8",
    )
    (profile.data_dir / ".cuentas.json.abc123.tmp").write_text("{", encoding="utf-8")
    (profile.data_dir / "historial_mensual.json").write_text("{}", encoding="utf-8")
    (profile.data_dir / "otro.json").write_text("{}", encoding="utf-8")
    (profile.config_dir / "reporte.key").write_bytes(b"no-es-una-clave")
    (profile.reports_dir / "R2026-03.avr").write_bytes(b"cifrado-ficticio")
    (profile.reports_dir / "index.avridx").write_bytes(b"cifrado-ficticio")

    found = [
        path.relative_to(profile.raiz).as_posix()
        for path in ProfileDocumentInventory().existing_documents(profile)
    ]

    assert sorted(found) == sorted(INTERNAL_DOCUMENTS)


def test_inventory_of_an_empty_or_missing_profile_is_empty(tmp_path: Path) -> None:
    """Un perfil sin carpetas ni archivos no tiene nada que revisar."""
    missing = profile_at(tmp_path, "ausente", "Ausente")
    empty = profile_at(tmp_path, "vacio", "Vacío")
    make_profile_folders(empty)

    assert ProfileDocumentInventory().existing_documents(missing) == []
    assert ProfileDocumentInventory().existing_documents(empty) == []


def test_inventory_matches_the_files_production_services_use(
    tmp_path: Path,
) -> None:
    """El inventario coincide con las rutas reales de los servicios activos."""
    profile = profile_at(tmp_path)
    make_profile_folders(profile)
    repository = BudgetRepository(profile.data_dir)
    inventory = ProfileDocumentInventory()

    expected_data = {
        repository.accounts_path.name,
        repository.debts_path.name,
        repository.debt_payments_path.name,
        repository.debt_snapshots_path.name,
        repository.monthly_closures_path.name,
        CategoryService(data_dir=profile.data_dir).categories_path.name,
    }

    assert set(inventory.DATA_FILE_NAMES) == expected_data
    assert inventory.CONFIG_FILE_NAMES == (SettingsService.ARCHIVO_CONFIGURACION,)
    assert repository.budget_path(2026, 3).match(inventory.BUDGET_FILE_PATTERN)
    assert profile.config_dir.name == "config"


# ---------------------------------------------------------------------------
# Servicio: creación para perfil histórico y perfil nuevo
# ---------------------------------------------------------------------------


def test_service_creates_metadata_once_for_legacy_profile(
    tmp_path: Path,
    spy: ReplaceSpy,
) -> None:
    """Un perfil histórico válido recibe sus metadatos mediante el almacén."""
    profile = make_legacy_profile(tmp_path)
    service = ProfileMetadataService()

    metadata = service.ensure(profile)

    assert metadata.profile_format_version == (
        LEGACY_IMPLICIT_PROFILE_FORMAT_VERSION
    )
    assert load_json(service.metadata_path(profile)) == {
        "schema_version": 1,
        "profile_format_version": 1,
        "profile_slug": HOGAR,
        "profile_name": "Hogar Ficticio",
        "app_version": __version__,
    }
    assert service.metadata_path(profile) == metadata_file(tmp_path)
    assert spy.targets == [PROFILE_METADATA_FILE_NAME]


def test_service_second_open_is_read_only(tmp_path: Path, spy: ReplaceSpy) -> None:
    """Abrir de nuevo el perfil valida los metadatos sin reescribirlos."""
    profile = make_legacy_profile(tmp_path)
    first = ProfileMetadataService().ensure(profile)
    before = tree_snapshot(tmp_path)

    second = ProfileMetadataService().ensure(profile)

    assert second == first
    assert tree_snapshot(tmp_path) == before
    assert spy.targets == [PROFILE_METADATA_FILE_NAME]


def test_service_creates_current_format_for_profile_without_data(
    tmp_path: Path,
) -> None:
    """Un perfil sin datos nace con el formato actual y crea su carpeta."""
    profile = profile_at(tmp_path, "nuevo_ficticio", "Nuevo Ficticio")
    service = ProfileMetadataService()

    metadata = service.ensure(profile)

    assert metadata.profile_format_version == CURRENT_PROFILE_FORMAT_VERSION
    assert service.has_metadata(profile)
    assert load_json(service.metadata_path(profile))[PROFILE_NAME_KEY] == (
        "Nuevo Ficticio"
    )


def test_service_app_version_comes_from_the_product_version(
    tmp_path: Path,
) -> None:
    """La versión de producto proviene de la fuente oficial, no de un literal."""
    default_profile = profile_at(tmp_path, "uno", "Uno")
    custom_profile = profile_at(tmp_path, "dos", "Dos")

    ProfileMetadataService().ensure(default_profile)
    ProfileMetadataService(app_version="9.8.7").ensure(custom_profile)

    assert load_json(metadata_file(tmp_path, "uno"))[APP_VERSION_KEY] == __version__
    assert load_json(metadata_file(tmp_path, "dos"))[APP_VERSION_KEY] == "9.8.7"


def test_service_does_not_rewrite_metadata_to_update_app_version(
    tmp_path: Path,
    spy: ReplaceSpy,
) -> None:
    """Abrir con otra versión de producto no actualiza los metadatos."""
    profile = make_legacy_profile(tmp_path)
    ProfileMetadataService(app_version="0.0.1").ensure(profile)
    before = metadata_file(tmp_path).read_bytes()

    metadata = ProfileMetadataService(app_version="9.8.7").ensure(profile)

    assert metadata.app_version == "0.0.1"
    assert metadata_file(tmp_path).read_bytes() == before
    assert spy.targets == [PROFILE_METADATA_FILE_NAME]


def test_metadata_contains_no_paths_or_private_information(tmp_path: Path) -> None:
    """Los metadatos sólo tienen identidad y versiones: sin rutas ni datos."""
    profile = make_legacy_profile(tmp_path)
    ProfileMetadataService().ensure(profile)

    text = metadata_file(tmp_path).read_text(encoding="utf-8")
    document = json.loads(text)

    assert set(document) == {
        SCHEMA_VERSION_KEY,
        PROFILE_FORMAT_VERSION_KEY,
        PROFILE_SLUG_KEY,
        PROFILE_NAME_KEY,
        APP_VERSION_KEY,
    }
    for forbidden in (str(tmp_path), tmp_path.name, "\\", ":/", "@"):
        assert forbidden not in text
    for forbidden in (os.environ.get("USERNAME"), os.environ.get("COMPUTERNAME")):
        if forbidden:
            assert forbidden not in text


def test_metadata_is_self_sufficient_to_recover_slug_and_name(
    tmp_path: Path,
) -> None:
    """Sin perfiles.json, cada carpeta permite recuperar slug y nombre."""
    install_catalog(tmp_path)
    make_legacy_profile(tmp_path)
    service = build_profile_service(tmp_path)
    service.obtener_activo()
    (tmp_path / "perfiles" / "perfiles.json").unlink()
    (tmp_path / "perfiles" / "perfil_activo.json").unlink()

    recovered = {}
    for folder in sorted((tmp_path / "perfiles").iterdir()):
        document = VersionedJsonStore().read(folder / PROFILE_METADATA_FILE_NAME)
        metadata = ProfileMetadataPolicy().parse(document, expected_slug=folder.name)
        recovered[metadata.profile_slug] = metadata.profile_name

    assert recovered == {HOGAR: "Hogar Ficticio", "personal": "Personal"}


# ---------------------------------------------------------------------------
# Servicio: revisión previa de los archivos del perfil
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("document", INTERNAL_DOCUMENTS)
def test_service_does_not_label_profile_with_future_internal_file(
    tmp_path: Path,
    spy: ReplaceSpy,
    document: str,
) -> None:
    """Un archivo interno de esquema futuro impide crear los metadatos."""
    profile = make_legacy_profile(tmp_path)
    set_key(profile.raiz.joinpath(*document.split("/")), SCHEMA_VERSION_KEY, FUTURE_SCHEMA)

    error = assert_fails_without_effects(
        tmp_path,
        spy,
        lambda: ProfileMetadataService().ensure(profile),
        UnsupportedSchemaVersionError,
    )

    assert error.document_name == Path(document).name  # type: ignore[attr-defined]
    assert not metadata_file(tmp_path).exists()


@pytest.mark.parametrize("version", ("1", True, None, 0), ids=("texto", "booleano", "null", "cero"))
@pytest.mark.parametrize("document", INTERNAL_DOCUMENTS)
def test_service_does_not_label_profile_with_invalid_internal_file(
    tmp_path: Path,
    spy: ReplaceSpy,
    document: str,
    version: object,
) -> None:
    """Un archivo interno de esquema inválido impide crear los metadatos."""
    profile = make_legacy_profile(tmp_path)
    set_key(profile.raiz.joinpath(*document.split("/")), SCHEMA_VERSION_KEY, version)

    assert_fails_without_effects(
        tmp_path,
        spy,
        lambda: ProfileMetadataService().ensure(profile),
        InvalidSchemaVersionError,
    )

    assert not metadata_file(tmp_path).exists()


@pytest.mark.parametrize("document", INTERNAL_DOCUMENTS)
def test_service_does_not_label_profile_with_corrupt_internal_file(
    tmp_path: Path,
    spy: ReplaceSpy,
    document: str,
) -> None:
    """Un archivo interno con JSON corrupto impide crear los metadatos."""
    profile = make_legacy_profile(tmp_path)
    profile.raiz.joinpath(*document.split("/")).write_text(
        '{"dato": [',
        encoding="utf-8",
    )

    error = assert_fails_without_effects(
        tmp_path,
        spy,
        lambda: ProfileMetadataService().ensure(profile),
        UnreadableProfileDocumentError,
    )

    assert error.document_name == Path(document).name  # type: ignore[attr-defined]
    assert error.profile_slug == HOGAR  # type: ignore[attr-defined]
    assert not metadata_file(tmp_path).exists()


def test_service_does_not_label_profile_with_mixed_schema_versions(
    tmp_path: Path,
    spy: ReplaceSpy,
) -> None:
    """Con cuentas v1 y deudas v2 no se crea metadata global v1."""
    profile = make_legacy_profile(tmp_path)
    set_key(profile.data_dir / "cuentas.json", SCHEMA_VERSION_KEY, 1)
    set_key(profile.data_dir / "deudas.json", SCHEMA_VERSION_KEY, 2)

    assert_fails_without_effects(
        tmp_path,
        spy,
        lambda: ProfileMetadataService().ensure(profile),
        UnsupportedSchemaVersionError,
    )

    assert not metadata_file(tmp_path).exists()


def test_service_labels_profile_with_explicit_and_legacy_files(
    tmp_path: Path,
) -> None:
    """Archivos v1 explícitos y legacy sin versión conviven en un perfil v1."""
    profile = make_legacy_profile(tmp_path)
    set_key(profile.data_dir / "cuentas.json", SCHEMA_VERSION_KEY, 1)
    set_key(profile.config_dir / "settings.json", SCHEMA_VERSION_KEY, 1)

    ProfileMetadataService().ensure(profile)

    assert metadata_file(tmp_path).exists()


def test_service_preflight_ignores_files_outside_the_inventory(
    tmp_path: Path,
) -> None:
    """Copias históricas, temporales y archivos ajenos no bloquean."""
    profile = make_legacy_profile(tmp_path)
    dump_json(
        profile.data_dir / "backups" / "cuentas.backup_20260301T000000.json",
        {"schema_version": 99},
    )
    (profile.data_dir / ".cuentas.json.abc123.tmp").write_text("{", encoding="utf-8")
    dump_json(profile.data_dir / "historial_mensual.json", {"schema_version": 99})
    (profile.reports_dir / "index.avridx").write_bytes(b"cifrado-ficticio")

    ProfileMetadataService().ensure(profile)

    assert metadata_file(tmp_path).exists()


def test_service_preflight_does_not_modify_any_file(tmp_path: Path) -> None:
    """La revisión previa es de sólo lectura."""
    profile = make_legacy_profile(tmp_path)
    before = tree_snapshot(tmp_path)

    ProfileMetadataService().preflight_legacy_documents(profile)

    assert tree_snapshot(tmp_path) == before


# ---------------------------------------------------------------------------
# Servicio: metadatos existentes incompatibles
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("version", (FUTURE_FORMAT, 999))
def test_service_future_profile_format_fails_closed(
    tmp_path: Path,
    spy: ReplaceSpy,
    version: int,
) -> None:
    """Un formato global futuro no se abre ni se modifica."""
    profile = make_legacy_profile(tmp_path)
    write_metadata(tmp_path, **{PROFILE_FORMAT_VERSION_KEY: version})

    error = assert_fails_without_effects(
        tmp_path,
        spy,
        lambda: ProfileMetadataService().ensure(profile),
        UnsupportedProfileFormatVersionError,
    )

    assert error.observed_version == version  # type: ignore[attr-defined]
    assert error.supported_version == CURRENT_PROFILE_FORMAT_VERSION  # type: ignore[attr-defined]


INVALID_METADATA_CASES = (
    ("sin_formato", {PROFILE_FORMAT_VERSION_KEY: ...}),
    ("formato_cero", {PROFILE_FORMAT_VERSION_KEY: 0}),
    ("formato_negativo", {PROFILE_FORMAT_VERSION_KEY: -1}),
    ("formato_texto", {PROFILE_FORMAT_VERSION_KEY: "1"}),
    ("formato_float", {PROFILE_FORMAT_VERSION_KEY: 1.0}),
    ("formato_true", {PROFILE_FORMAT_VERSION_KEY: True}),
    ("formato_false", {PROFILE_FORMAT_VERSION_KEY: False}),
    ("formato_null", {PROFILE_FORMAT_VERSION_KEY: None}),
    ("sin_slug", {PROFILE_SLUG_KEY: ...}),
    ("slug_vacio", {PROFILE_SLUG_KEY: ""}),
    ("slug_distinto", {PROFILE_SLUG_KEY: "personal"}),
    ("sin_nombre", {PROFILE_NAME_KEY: ...}),
    ("nombre_vacio", {PROFILE_NAME_KEY: ""}),
    ("sin_app_version", {APP_VERSION_KEY: ...}),
    ("app_version_vacia", {APP_VERSION_KEY: ""}),
)


@pytest.mark.parametrize(
    "changes",
    [changes for _, changes in INVALID_METADATA_CASES],
    ids=[name for name, _ in INVALID_METADATA_CASES],
)
def test_service_invalid_metadata_fails_closed(
    tmp_path: Path,
    spy: ReplaceSpy,
    changes: dict[str, object],
) -> None:
    """Metadatos incompletos o incoherentes no se aceptan ni se reparan."""
    profile = make_legacy_profile(tmp_path)
    document = {SCHEMA_VERSION_KEY: CURRENT_SCHEMA_VERSION, **VALID_DOCUMENT}
    for key, value in changes.items():
        if value is ...:
            del document[key]
        else:
            document[key] = value
    dump_json(metadata_file(tmp_path), document)

    error = assert_fails_without_effects(
        tmp_path,
        spy,
        lambda: ProfileMetadataService().ensure(profile),
        InvalidProfileMetadataError,
    )

    assert error.field == next(iter(changes))  # type: ignore[attr-defined]


@pytest.mark.parametrize(
    ("version", "expected"),
    (
        (FUTURE_SCHEMA, UnsupportedSchemaVersionError),
        ("1", InvalidSchemaVersionError),
        (None, InvalidSchemaVersionError),
    ),
    ids=("futura", "texto", "null"),
)
def test_service_metadata_schema_version_uses_the_22d_policy(
    tmp_path: Path,
    spy: ReplaceSpy,
    version: object,
    expected: type[SchemaVersionError],
) -> None:
    """El schema_version del propio archivo lo valida la política de 22D."""
    profile = make_legacy_profile(tmp_path)
    write_metadata(tmp_path, **{SCHEMA_VERSION_KEY: version})

    error = assert_fails_without_effects(
        tmp_path,
        spy,
        lambda: ProfileMetadataService().ensure(profile),
        expected,
    )

    assert error.document_name == PROFILE_METADATA_FILE_NAME  # type: ignore[attr-defined]


def test_service_metadata_without_schema_version_is_implicit_schema_one(
    tmp_path: Path,
    spy: ReplaceSpy,
) -> None:
    """Sin schema_version el archivo vale como esquema 1, igual que en 22D."""
    profile = make_legacy_profile(tmp_path)
    dump_json(metadata_file(tmp_path), VALID_DOCUMENT)

    metadata = ProfileMetadataService().ensure(profile)

    assert metadata.profile_slug == HOGAR
    assert spy.targets == []


@pytest.mark.parametrize("content", ('{"profile_slug": ', "", "no es json"))
def test_service_corrupt_metadata_is_not_treated_as_missing(
    tmp_path: Path,
    spy: ReplaceSpy,
    content: str,
) -> None:
    """Metadatos corruptos fallan: no se reconstruyen ni se sobrescriben."""
    profile = make_legacy_profile(tmp_path)
    metadata_file(tmp_path).write_text(content, encoding="utf-8")

    error = assert_fails_without_effects(
        tmp_path,
        spy,
        lambda: ProfileMetadataService().ensure(profile),
        InvalidProfileMetadataError,
    )

    assert error.field == "documento"  # type: ignore[attr-defined]
    assert error.__cause__ is None
    assert metadata_file(tmp_path).read_text(encoding="utf-8") == content


def test_service_failed_replace_leaves_no_partial_metadata(
    tmp_path: Path,
    spy: ReplaceSpy,
) -> None:
    """Si falla el reemplazo no quedan metadatos parciales ni temporales."""
    profile = make_legacy_profile(tmp_path)
    spy.fail_on.add(PROFILE_METADATA_FILE_NAME)

    assert_fails_without_effects(
        tmp_path,
        ReplaceSpy(),
        lambda: ProfileMetadataService().ensure(profile),
        OSError,
    )

    assert not metadata_file(tmp_path).exists()
    assert spy.targets == [PROFILE_METADATA_FILE_NAME]


# ---------------------------------------------------------------------------
# ProfileService: perfil histórico y perfil activo
# ---------------------------------------------------------------------------


def test_profile_service_creates_metadata_once_for_legacy_active_profile(
    legacy_root: Path,
    spy: ReplaceSpy,
) -> None:
    """Abrir el perfil activo histórico crea sus metadatos una sola vez."""
    service = build_profile_service(legacy_root)
    assert not metadata_file(legacy_root).exists()

    active = service.obtener_activo()

    assert active.id == HOGAR
    assert load_json(metadata_file(legacy_root)) == {
        "schema_version": 1,
        "profile_format_version": LEGACY_IMPLICIT_PROFILE_FORMAT_VERSION,
        "profile_slug": HOGAR,
        "profile_name": "Hogar Ficticio",
        "app_version": __version__,
    }
    assert spy.targets.count(PROFILE_METADATA_FILE_NAME) == 2


def test_profile_service_second_open_keeps_metadata_bytes(
    legacy_root: Path,
    spy: ReplaceSpy,
) -> None:
    """Una segunda apertura, incluso con otro servicio, es de sólo lectura."""
    build_profile_service(legacy_root).obtener_activo()
    before = tree_snapshot(legacy_root)
    replaced = list(spy.targets)

    service = build_profile_service(legacy_root)
    service.obtener_activo()
    service.obtener_perfil("personal")
    service.obtener_periodo_trabajo(HOGAR)

    assert tree_snapshot(legacy_root) == before
    assert spy.targets == replaced


def test_profile_service_listing_does_not_open_profiles(
    legacy_root: Path,
) -> None:
    """Listar perfiles no crea metadatos ni depende de su validez."""
    service = build_profile_service(legacy_root)
    write_metadata(legacy_root, **{PROFILE_FORMAT_VERSION_KEY: FUTURE_FORMAT})
    before = tree_snapshot(legacy_root)

    listed = [item.id for item in service.listar_perfiles()]

    assert listed == [HOGAR, "personal"]
    assert tree_snapshot(legacy_root) == before


@pytest.mark.parametrize(
    ("document", "version", "expected"),
    (
        ("data/deudas.json", FUTURE_SCHEMA, UnsupportedSchemaVersionError),
        ("data/presupuesto_2026-04.json", FUTURE_SCHEMA, UnsupportedSchemaVersionError),
        ("config/settings.json", FUTURE_SCHEMA, UnsupportedSchemaVersionError),
        ("data/cuentas.json", "1", InvalidSchemaVersionError),
        ("data/categorias.json", None, InvalidSchemaVersionError),
    ),
    ids=("deudas_futura", "mes_futuro", "settings_futuro", "cuentas_invalida", "categorias_invalida"),
)
def test_profile_service_does_not_open_legacy_profile_with_incompatible_file(
    legacy_root: Path,
    spy: ReplaceSpy,
    document: str,
    version: object,
    expected: type[Exception],
) -> None:
    """Un perfil histórico con un archivo incompatible no queda operativo."""
    service = build_profile_service(legacy_root)
    target = legacy_root / "perfiles" / HOGAR
    set_key(target.joinpath(*document.split("/")), SCHEMA_VERSION_KEY, version)

    assert_fails_without_effects(legacy_root, spy, service.obtener_activo, expected)

    assert not metadata_file(legacy_root).exists()


def test_profile_service_active_profile_with_future_format_is_not_operational(
    legacy_root: Path,
    spy: ReplaceSpy,
) -> None:
    """Con formato global futuro el perfil activo no se abre ni se cambia."""
    service = build_profile_service(legacy_root)
    write_metadata(legacy_root, **{PROFILE_FORMAT_VERSION_KEY: FUTURE_FORMAT})
    active_before = (legacy_root / "perfiles" / "perfil_activo.json").read_bytes()

    for action in (
        service.obtener_activo,
        service.obtener_ruta_activa,
        lambda: service.obtener_perfil(HOGAR),
        lambda: service.seleccionar_perfil(HOGAR),
        lambda: service.obtener_periodo_trabajo(),
        lambda: service.obtener_periodo_trabajo(HOGAR),
    ):
        assert_fails_without_effects(
            legacy_root,
            spy,
            action,
            UnsupportedProfileFormatVersionError,
        )

    assert (legacy_root / "perfiles" / "perfil_activo.json").read_bytes() == (
        active_before
    )
    assert load_json(legacy_root / "perfiles" / "perfil_activo.json") == {
        "slug": HOGAR,
    }


def test_profile_service_other_profiles_remain_usable(legacy_root: Path) -> None:
    """Un perfil incompatible no impide abrir ni seleccionar otro válido."""
    service = build_profile_service(legacy_root)
    write_metadata(legacy_root, **{PROFILE_FORMAT_VERSION_KEY: FUTURE_FORMAT})

    selected = service.seleccionar_perfil("personal")

    assert selected.id == "personal"
    assert service.obtener_activo().id == "personal"


@pytest.mark.parametrize("content", ('{"profile_slug": ', ""))
def test_profile_service_corrupt_metadata_blocks_the_profile(
    legacy_root: Path,
    spy: ReplaceSpy,
    content: str,
) -> None:
    """Metadatos corruptos bloquean el perfil sin reconstruirse."""
    service = build_profile_service(legacy_root)
    metadata_file(legacy_root).write_text(content, encoding="utf-8")

    assert_fails_without_effects(
        legacy_root,
        spy,
        service.obtener_activo,
        InvalidProfileMetadataError,
    )


def test_profile_service_slug_mismatch_blocks_the_profile(
    legacy_root: Path,
    spy: ReplaceSpy,
) -> None:
    """Metadatos de otro perfil en la carpeta bloquean sin corregirse."""
    service = build_profile_service(legacy_root)
    dump_json(
        metadata_file(legacy_root),
        {SCHEMA_VERSION_KEY: 1, **VALID_DOCUMENT, PROFILE_SLUG_KEY: "personal"},
    )

    error = assert_fails_without_effects(
        legacy_root,
        spy,
        service.obtener_activo,
        InvalidProfileMetadataError,
    )

    assert error.field == PROFILE_SLUG_KEY  # type: ignore[attr-defined]
    assert error.profile_slug == HOGAR  # type: ignore[attr-defined]


@pytest.mark.parametrize("catalog_file", ("perfiles.json", "perfil_activo.json"))
def test_profile_service_catalog_gate_runs_before_the_metadata_gate(
    legacy_root: Path,
    spy: ReplaceSpy,
    catalog_file: str,
) -> None:
    """Un catálogo o perfil activo futuro se detecta antes que los metadatos."""
    service = build_profile_service(legacy_root)
    write_metadata(legacy_root, **{PROFILE_FORMAT_VERSION_KEY: FUTURE_FORMAT})
    set_key(legacy_root / "perfiles" / catalog_file, SCHEMA_VERSION_KEY, FUTURE_SCHEMA)

    for action in (
        service.obtener_activo,
        lambda: service.seleccionar_perfil(HOGAR),
        lambda: service.crear_perfil("Negocio Ficticio"),
        lambda: build_profile_service(legacy_root),
    ):
        error = assert_fails_without_effects(
            legacy_root,
            spy,
            action,
            UnsupportedSchemaVersionError,
        )
        assert error.document_name == catalog_file  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# ProfileService: arranque y perfil personal
# ---------------------------------------------------------------------------


def test_profile_service_first_start_creates_personal_with_metadata(
    tmp_path: Path,
    spy: ReplaceSpy,
) -> None:
    """En el primer arranque el perfil personal nace con metadatos."""
    service = build_profile_service(tmp_path)

    assert load_json(metadata_file(tmp_path, "personal")) == {
        "schema_version": 1,
        "profile_format_version": CURRENT_PROFILE_FORMAT_VERSION,
        "profile_slug": "personal",
        "profile_name": "Personal",
        "app_version": __version__,
    }
    assert spy.targets == [
        PROFILE_METADATA_FILE_NAME,
        "perfiles.json",
        "perfil_activo.json",
    ]
    assert service.obtener_activo().id == "personal"


LEGACY_FLAT_FILES = (
    "legacy_data/presupuesto_2026-03.json",
    "legacy_data/presupuesto_2026-04.json",
    "legacy_data/cuentas.json",
    "legacy_data/deudas.json",
    "legacy_data/historial_mensual.json",
    "legacy_reports/R2026-03.avr",
    "legacy_reports/index.avridx",
    "legacy_config/reporte.key",
)
LEGACY_VERSIONED_SOURCES = (
    "presupuesto_2026-03.json",
    "presupuesto_2026-04.json",
    "cuentas.json",
    "deudas.json",
)
LEGACY_SOURCE_PROBLEMS = (
    (
        "futura",
        lambda path: set_key(path, SCHEMA_VERSION_KEY, FUTURE_SCHEMA),
        UnsupportedSchemaVersionError,
    ),
    (
        "invalida",
        lambda path: set_key(path, SCHEMA_VERSION_KEY, "1"),
        InvalidSchemaVersionError,
    ),
    (
        "corrupta",
        lambda path: path.write_text('{"dato": [', encoding="utf-8"),
        UnreadableProfileDocumentError,
    ),
)


def make_legacy_flat_sources(root: Path) -> None:
    """Crea las carpetas planas históricas con todo lo que se copiaría.

    El historial mensual, los reportes y la clave llevan contenido que no
    es un JSON versionado válido: quedan fuera de la revisión de esquema.
    """
    legacy_data = root / "legacy_data"
    legacy_data.mkdir()
    for name in ("presupuesto_2026-03.json", "cuentas.json", "deudas.json"):
        shutil.copyfile(fixture_path(f"profile_data/{name}"), legacy_data / name)
    shutil.copyfile(
        fixture_path("profile_data/presupuesto_2026-03.json"),
        legacy_data / "presupuesto_2026-04.json",
    )
    set_key(legacy_data / "presupuesto_2026-04.json", "month", 4)
    (legacy_data / "historial_mensual.json").write_text(
        '{"schema_version": 99, "meses": [',
        encoding="utf-8",
    )
    (root / "legacy_reports").mkdir()
    (root / "legacy_reports" / "R2026-03.avr").write_bytes(b"reporte-ficticio")
    (root / "legacy_reports" / "index.avridx").write_bytes(b"indice-ficticio")
    (root / "legacy_config").mkdir()
    (root / "legacy_config" / "reporte.key").write_bytes(b"clave-ficticia")


def copied_targets(root: Path) -> dict[str, Path]:
    """Relaciona cada fuente plana con su destino en el perfil personal."""
    personal = root / "perfiles" / "personal"
    folders = {
        "legacy_data": personal / "data",
        "legacy_reports": personal / "reportes",
        "legacy_config": personal / "config",
    }
    return {
        relative: folders[relative.split("/")[0]] / relative.split("/")[1]
        for relative in LEGACY_FLAT_FILES
    }


def test_profile_service_valid_legacy_flat_data_is_copied_then_labeled(
    tmp_path: Path,
) -> None:
    """Con fuentes válidas la copia histórica se hace completa y se etiqueta."""
    make_legacy_flat_sources(tmp_path)
    sources_before = {
        relative: (tmp_path / relative).read_bytes()
        for relative in LEGACY_FLAT_FILES
    }

    service = build_profile_service(tmp_path)

    for relative, target in copied_targets(tmp_path).items():
        assert target.read_bytes() == sources_before[relative], relative
        assert (tmp_path / relative).read_bytes() == sources_before[relative]
    assert load_json(metadata_file(tmp_path, "personal")) == {
        "schema_version": 1,
        "profile_format_version": LEGACY_IMPLICIT_PROFILE_FORMAT_VERSION,
        "profile_slug": "personal",
        "profile_name": "Personal",
        "app_version": __version__,
    }
    assert load_json(service.registry_path) == {
        "perfiles": [{"nombre": "Personal", "slug": "personal"}],
        "schema_version": 1,
    }
    assert load_json(service.active_path) == {
        "schema_version": 1,
        "slug": "personal",
    }
    assert service.obtener_activo().id == "personal"


def test_profile_service_legacy_copy_is_not_repeated_on_next_start(
    tmp_path: Path,
    spy: ReplaceSpy,
) -> None:
    """Tras un bootstrap completo, el siguiente arranque no copia ni escribe."""
    make_legacy_flat_sources(tmp_path)
    build_profile_service(tmp_path)
    before = tree_snapshot(tmp_path)
    replaced = list(spy.targets)

    build_profile_service(tmp_path).obtener_activo()

    assert tree_snapshot(tmp_path) == before
    assert spy.targets == replaced


@pytest.mark.parametrize(
    ("mutate", "expected"),
    [(mutate, expected) for _, mutate, expected in LEGACY_SOURCE_PROBLEMS],
    ids=[name for name, _, _ in LEGACY_SOURCE_PROBLEMS],
)
@pytest.mark.parametrize("source_name", LEGACY_VERSIONED_SOURCES)
def test_profile_service_incompatible_legacy_source_blocks_before_any_copy(
    tmp_path: Path,
    spy: ReplaceSpy,
    source_name: str,
    mutate: Callable[[Path], Any],
    expected: type[Exception],
) -> None:
    """Una fuente plana futura, inválida o corrupta aborta sin copiar nada.

    El árbol completo queda idéntico: ni copias, ni metadatos, ni catálogo,
    ni perfil activo, ni carpetas del perfil, y las fuentes no se tocan.
    """
    make_legacy_flat_sources(tmp_path)
    mutate(tmp_path / "legacy_data" / source_name)

    error = assert_fails_without_effects(
        tmp_path,
        spy,
        lambda: build_profile_service(tmp_path),
        expected,
    )

    assert error.document_name == source_name  # type: ignore[attr-defined]
    assert not (tmp_path / "perfiles").exists()


def test_profile_service_validates_every_legacy_source_before_copying_any(
    tmp_path: Path,
    spy: ReplaceSpy,
) -> None:
    """Con presupuesto y cuentas válidos y deudas futura no se copia ninguno.

    Tampoco se copian los reportes cifrados ni la clave, que no se revisan
    pero forman parte del mismo plan de copia.
    """
    make_legacy_flat_sources(tmp_path)
    set_key(tmp_path / "legacy_data" / "deudas.json", SCHEMA_VERSION_KEY, FUTURE_SCHEMA)

    assert_fails_without_effects(
        tmp_path,
        spy,
        lambda: build_profile_service(tmp_path),
        UnsupportedSchemaVersionError,
    )

    for target in copied_targets(tmp_path).values():
        assert not target.exists()


@pytest.mark.parametrize(
    ("mutate", "expected"),
    [(mutate, expected) for _, mutate, expected in LEGACY_SOURCE_PROBLEMS],
    ids=[name for name, _, _ in LEGACY_SOURCE_PROBLEMS],
)
def test_profile_service_incompatible_legacy_source_keeps_registered_profile_intact(
    tmp_path: Path,
    spy: ReplaceSpy,
    mutate: Callable[[Path], Any],
    expected: type[Exception],
) -> None:
    """Con "personal" ya registrado tampoco cambian catálogo ni perfil activo."""
    install_catalog(tmp_path)
    make_profile_folders(profile_at(tmp_path, "personal", "Personal"))
    make_legacy_flat_sources(tmp_path)
    mutate(tmp_path / "legacy_data" / "deudas.json")
    catalog_before = (tmp_path / "perfiles" / "perfiles.json").read_bytes()
    active_before = (tmp_path / "perfiles" / "perfil_activo.json").read_bytes()

    assert_fails_without_effects(
        tmp_path,
        spy,
        lambda: build_profile_service(tmp_path),
        expected,
    )

    assert (tmp_path / "perfiles" / "perfiles.json").read_bytes() == catalog_before
    assert (tmp_path / "perfiles" / "perfil_activo.json").read_bytes() == (
        active_before
    )
    assert not metadata_file(tmp_path, "personal").exists()


def test_profile_service_incompatible_existing_file_blocks_before_legacy_copy(
    tmp_path: Path,
    spy: ReplaceSpy,
) -> None:
    """Un archivo incompatible ya presente en el perfil impide la copia."""
    personal = profile_at(tmp_path, "personal", "Personal")
    make_profile_folders(personal)
    shutil.copyfile(
        fixture_path("profile_data/categorias.json"),
        personal.data_dir / "categorias.json",
    )
    set_key(personal.data_dir / "categorias.json", SCHEMA_VERSION_KEY, FUTURE_SCHEMA)
    make_legacy_flat_sources(tmp_path)

    assert_fails_without_effects(
        tmp_path,
        spy,
        lambda: build_profile_service(tmp_path),
        UnsupportedSchemaVersionError,
    )


def test_profile_service_legacy_sources_are_ignored_when_profile_has_budgets(
    tmp_path: Path,
) -> None:
    """Con presupuestos propios no hay copia de datos, ni revisión de fuentes.

    Se conserva la regla histórica: sólo se copian datos planos a un perfil
    personal sin presupuestos.
    """
    personal = make_legacy_profile(tmp_path, "personal", "Personal")
    own_debts = (personal.data_dir / "deudas.json").read_bytes()
    make_legacy_flat_sources(tmp_path)
    set_key(tmp_path / "legacy_data" / "deudas.json", SCHEMA_VERSION_KEY, FUTURE_SCHEMA)

    build_profile_service(tmp_path)

    assert (personal.data_dir / "deudas.json").read_bytes() == own_debts
    assert not (personal.data_dir / "historial_mensual.json").exists()
    assert (personal.reports_dir / "R2026-03.avr").exists()
    assert personal.key_path.exists()
    assert metadata_file(tmp_path, "personal").exists()


@pytest.mark.parametrize(
    ("changes", "expected"),
    (
        ({PROFILE_FORMAT_VERSION_KEY: FUTURE_FORMAT}, UnsupportedProfileFormatVersionError),
        ({PROFILE_FORMAT_VERSION_KEY: "1"}, InvalidProfileMetadataError),
        ({PROFILE_SLUG_KEY: HOGAR}, InvalidProfileMetadataError),
        ({SCHEMA_VERSION_KEY: FUTURE_SCHEMA}, UnsupportedSchemaVersionError),
    ),
    ids=("formato_futuro", "formato_invalido", "slug_distinto", "esquema_futuro"),
)
def test_profile_service_startup_validates_personal_metadata_before_mutating(
    tmp_path: Path,
    spy: ReplaceSpy,
    changes: dict[str, object],
    expected: type[Exception],
) -> None:
    """Con metadatos incompatibles de "personal" el arranque no muta nada.

    El catálogo legacy no registra "personal" y existen datos planos
    históricos: sin la validación previa se registraría y se copiarían.
    """
    profiles_root = tmp_path / "perfiles"
    dump_json(
        profiles_root / "perfiles.json",
        {"perfiles": [{"nombre": "Hogar Ficticio", "slug": HOGAR}]},
    )
    write_metadata(tmp_path, "personal", profile_name="Personal", **changes)
    legacy_data = tmp_path / "legacy_data"
    legacy_data.mkdir()
    shutil.copyfile(
        fixture_path("profile_data/presupuesto_2026-03.json"),
        legacy_data / "presupuesto_2026-03.json",
    )

    assert_fails_without_effects(
        tmp_path,
        spy,
        lambda: build_profile_service(tmp_path),
        expected,
    )

    assert not (profiles_root / "perfil_activo.json").exists()
    assert not (profiles_root / "personal" / "data").exists()


def test_profile_service_startup_does_not_label_personal_with_future_file(
    tmp_path: Path,
    spy: ReplaceSpy,
) -> None:
    """Un "personal" histórico con un archivo futuro no se etiqueta al arrancar."""
    install_catalog(tmp_path)
    personal = make_legacy_profile(tmp_path, "personal", "Personal")
    set_key(personal.data_dir / "deudas.json", SCHEMA_VERSION_KEY, FUTURE_SCHEMA)

    assert_fails_without_effects(
        tmp_path,
        spy,
        lambda: build_profile_service(tmp_path),
        UnsupportedSchemaVersionError,
    )

    assert not metadata_file(tmp_path, "personal").exists()


def test_profile_service_startup_rolls_back_personal_when_registry_fails(
    tmp_path: Path,
    spy: ReplaceSpy,
) -> None:
    """Si falla el registro en el primer arranque no queda un perfil a medias."""
    spy.fail_on.add("perfiles.json")

    with pytest.raises(OSError):
        build_profile_service(tmp_path)

    profiles_root = tmp_path / "perfiles"
    assert spy.targets == [PROFILE_METADATA_FILE_NAME, "perfiles.json"]
    assert not (profiles_root / "perfiles.json").exists()
    assert not (profiles_root / "personal").exists()
    assert list(profiles_root.rglob("*.tmp")) == []


# ---------------------------------------------------------------------------
# ProfileService: perfil nuevo
# ---------------------------------------------------------------------------


def test_profile_service_new_profile_is_born_with_metadata(
    legacy_root: Path,
    spy: ReplaceSpy,
) -> None:
    """Un perfil nuevo tiene metadatos antes de quedar registrado."""
    service = build_profile_service(legacy_root)
    replaced = len(spy.targets)

    created = service.crear_perfil("Negocio Ficticio")

    assert load_json(metadata_file(legacy_root, created.id)) == {
        "schema_version": 1,
        "profile_format_version": CURRENT_PROFILE_FORMAT_VERSION,
        "profile_slug": created.id,
        "profile_name": "Negocio Ficticio",
        "app_version": __version__,
    }
    assert spy.targets[replaced : replaced + 2] == [
        PROFILE_METADATA_FILE_NAME,
        "perfiles.json",
    ]
    assert created.id in {item.id for item in service.listar_perfiles()}
    assert service.obtener_perfil(created.id).nombre == "Negocio Ficticio"


def test_profile_service_new_profile_is_not_registered_if_metadata_fails(
    legacy_root: Path,
    spy: ReplaceSpy,
) -> None:
    """Si fallan los metadatos no se registra el perfil ni queda su carpeta."""
    service = build_profile_service(legacy_root)
    registry_before = service.registry_path.read_bytes()
    spy.fail_on.add(PROFILE_METADATA_FILE_NAME)

    with pytest.raises(OSError):
        service.crear_perfil("Negocio Ficticio")

    assert service.registry_path.read_bytes() == registry_before
    assert not (legacy_root / "perfiles" / "negocio_ficticio").exists()
    assert list((legacy_root / "perfiles").rglob("*.tmp")) == []
    assert "perfiles.json" not in spy.targets


def test_profile_service_new_profile_is_rolled_back_if_registry_fails(
    legacy_root: Path,
    spy: ReplaceSpy,
) -> None:
    """Si falla el registro se retiran metadatos y carpetas recién creados."""
    service = build_profile_service(legacy_root)
    registry_before = service.registry_path.read_bytes()
    spy.fail_on.add("perfiles.json")

    with pytest.raises(OSError):
        service.crear_perfil("Negocio Ficticio")

    assert service.registry_path.read_bytes() == registry_before
    assert not (legacy_root / "perfiles" / "negocio_ficticio").exists()
    assert [item.id for item in service.listar_perfiles()] == [HOGAR, "personal"]


def test_profile_service_failed_creation_never_deletes_preexisting_folder(
    legacy_root: Path,
    spy: ReplaceSpy,
) -> None:
    """Una carpeta previa con datos se conserva aunque el registro falle."""
    orphan = make_legacy_profile(legacy_root, "negocio_ficticio", "Negocio Ficticio")
    files_before = tree_snapshot(orphan.raiz)[0]
    service = build_profile_service(legacy_root)
    spy.fail_on.add("perfiles.json")

    with pytest.raises(OSError):
        service.crear_perfil("Negocio Ficticio")

    assert tree_snapshot(orphan.raiz)[0] == files_before
    assert not metadata_file(legacy_root, "negocio_ficticio").exists()


def test_profile_service_new_profile_respects_existing_incompatible_metadata(
    legacy_root: Path,
    spy: ReplaceSpy,
) -> None:
    """Una carpeta previa con metadatos futuros no se registra ni se pisa."""
    write_metadata(
        legacy_root,
        "negocio_ficticio",
        profile_name="Negocio Ficticio",
        **{PROFILE_FORMAT_VERSION_KEY: FUTURE_FORMAT},
    )
    service = build_profile_service(legacy_root)

    assert_fails_without_effects(
        legacy_root,
        spy,
        lambda: service.crear_perfil("Negocio Ficticio"),
        UnsupportedProfileFormatVersionError,
    )


def test_profile_service_demo_profile_gets_metadata(legacy_root: Path) -> None:
    """El perfil demo se registra con sus metadatos."""
    service = build_profile_service(legacy_root)

    demo = DemoProfileService(service).abrir_demo()

    assert demo.id == PERFIL_DEMO
    assert load_json(metadata_file(legacy_root, PERFIL_DEMO)) == {
        "schema_version": 1,
        "profile_format_version": CURRENT_PROFILE_FORMAT_VERSION,
        "profile_slug": PERFIL_DEMO,
        "profile_name": "Demo Avalancha",
        "app_version": __version__,
    }


def test_profile_service_has_no_rename_operation() -> None:
    """No existe renombrado de perfiles: el nombre nace del catálogo."""
    public = {name for name in vars(ProfileService) if not name.startswith("_")}

    assert public == {
        "listar_perfiles",
        "obtener_activo",
        "obtener_perfil",
        "crear_perfil",
        "seleccionar_perfil",
        "obtener_ruta_activa",
        "obtener_periodo_trabajo",
        "asegurar_demo_registrado",
    }


# ---------------------------------------------------------------------------
# Arranque de la aplicación y alcance del respaldo
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("content", "expected"),
    (
        ({**VALID_DOCUMENT, PROFILE_FORMAT_VERSION_KEY: FUTURE_FORMAT}, UnsupportedProfileFormatVersionError),
        ({**VALID_DOCUMENT, PROFILE_NAME_KEY: ""}, InvalidProfileMetadataError),
        (None, InvalidProfileMetadataError),
    ),
    ids=("futuro", "invalido", "corrupto"),
)
def test_main_window_does_not_start_on_incompatible_active_profile(
    app: QApplication,
    legacy_root: Path,
    spy: ReplaceSpy,
    content: dict[str, object] | None,
    expected: type[Exception],
) -> None:
    """La ventana principal no se construye ni escribe sobre ese perfil."""
    _ = app
    service = build_profile_service(legacy_root)
    demo_service = DemoProfileService(service)
    if content is None:
        metadata_file(legacy_root).write_text("{", encoding="utf-8")
    else:
        dump_json(metadata_file(legacy_root), content)

    assert_fails_without_effects(
        legacy_root,
        spy,
        lambda: MainWindow(service, demo_service),
        expected,
    )


def test_resolved_22g_backup_now_includes_profile_metadata(
    legacy_root: Path,
) -> None:
    """Desde la Etapa 22G, el respaldo de perfil incluye profile_metadata.json.

    Cerraba una deuda caracterizada en 22E: el inventario del respaldo
    cubría data, settings, clave y reportes, pero no la raíz del perfil.
    """
    profile = build_profile_service(legacy_root).obtener_activo()
    assert metadata_file(legacy_root).exists()

    logical_paths = [path for path, _, _ in ProfileBackupService()._inventariar(profile)]

    assert logical_paths
    assert any(PROFILE_METADATA_FILE_NAME in path for path in logical_paths)
