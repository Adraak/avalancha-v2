"""Línea base ejecutable de los formatos persistentes actuales (Etapa 22B).

"schema_v1" representa el formato persistente legacy existente antes de
incorporar versionado explícito. Los fixtures de ``tests/fixtures/schema_v1``
son sintéticos y documentan ese formato legacy: no declaran
``schema_version`` y deben seguir leyéndose como versión 1 implícita.

Desde la Etapa 22D toda escritura legítima agrega ``"schema_version": 1`` en
la raíz. Por eso los pocos tests de este módulo que observan un archivo
recién escrito esperan esa clave además del contenido del fixture; los
fixtures no la tienen ni deben tenerla. El formato explícitamente
versionado se prueba en ``tests/test_v2_schema_versioning.py``.

Los tests llamados ``test_legacy_characterization_*`` describen el
comportamiento actual, incluso cuando es peligroso. No son una expectativa
normativa: están para demostrar el cambio cuando una etapa posterior lo
corrija de forma deliberada.
"""

from __future__ import annotations

import json
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest

from avalancha import models
from avalancha.gestor_reportes import GestorReportes, ProveedorClaveLocal
from avalancha.models import (
    ACCOUNT_TYPES,
    DEBT_CATEGORIES,
    TRANSACTION_TYPES,
    CategoryBudget,
    CuentaFinanciera,
    Debt,
    DebtPayment,
    DebtSnapshot,
    MonthlyBudget,
    RecurringItem,
    Transaction,
    validate_amount,
)
from avalancha.reporte_mensual import ReporteEstructurado, SeccionReporte
from avalancha.storage import BudgetRepository
from core.models.backup import (
    BACKUP_FILE_ROLES,
    SCHEMA_VERSION,
    InvalidBackupManifestError,
    UnsupportedBackupVersionError,
)
from core.models import monthly_closure
from core.models.categoria import Categoria
from core.models.monthly_closure import (
    MONTHLY_CLOSURE_STATUSES,
    MonthlyClosure,
)
from services.backup_manifest_service import BackupManifestService
from services.budget_service import BudgetService
from services.category_service import CategoryService
from services.error_reporting_service import UserFacingError
from services.profile_service import ProfileService
from services.settings_service import SettingsService


FIXTURES_ROOT = Path(__file__).resolve().parent / "fixtures" / "schema_v1"
EXPECTED_FIXTURES = frozenset(
    {
        "backup_manifest/manifest.json",
        "catalog/perfil_activo.json",
        "catalog/perfiles.json",
        "profile_config/settings.json",
        "profile_data/categorias.json",
        "profile_data/cuentas.json",
        "profile_data/debt_payments.json",
        "profile_data/debt_snapshots.json",
        "profile_data/deudas.json",
        "profile_data/monthly_closures.json",
        "profile_data/presupuesto_2026-03.json",
        "report_payloads/report_document.json",
        "report_payloads/report_index.json",
    },
)
FORBIDDEN_SUFFIXES = frozenset(
    {".key", ".zip", ".avr", ".avridx", ".exe", ".enc", ".pem", ".db"},
)
FORBIDDEN_TEXT = (":\\", ":/", "Users", "AppData", "@", "\\\\")
AMOUNT_FIELDS = frozenset(
    {
        "amount",
        "budgeted_amount",
        "current_balance",
        "previous_month_balance",
        "current_monthly_payment",
        "minimum_payment",
        "credit_limit",
        "initial_balance",
        "registered_balance",
        "balance",
        "balance_before",
        "balance_after",
        "estimated_interest",
    },
)
NULLABLE_AMOUNT_FIELDS = frozenset({"real_balance", "previous_balance"})
DATE_FIELDS = frozenset(
    {"tx_date", "start_date", "end_date", "reconciliation_date"},
)
TIMESTAMP_FIELDS = frozenset(
    {"created_at", "updated_at", "closed_at", "fecha_creacion"},
)
ID_FIELDS = frozenset(
    {
        "transaction_id",
        "budget_id",
        "recurring_id",
        "debt_id",
        "account_id",
        "destination_account_id",
        "payment_id",
        "movement_id",
        "snapshot_id",
        "closure_id",
    },
)
DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")
TIMESTAMP_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$")
SYNTHETIC_ID_PATTERN = re.compile(r"^[a-z]{3}\d{29}$")
GENERATED_ID_PATTERN = re.compile(r"^[0-9a-f]{32}$")
FROZEN_TODAY = "2001-02-03"
FROZEN_NOW = "2001-02-03T04:05:06"
PROFILE_DATA_FILES = (
    "presupuesto_2026-03.json",
    "cuentas.json",
    "deudas.json",
    "debt_payments.json",
    "debt_snapshots.json",
    "monthly_closures.json",
    "categorias.json",
)


def fixture_path(relative: str) -> Path:
    """Devuelve la ruta de un fixture schema_v1."""
    return FIXTURES_ROOT.joinpath(*relative.split("/"))


def load_fixture(relative: str) -> Any:
    """Carga un fixture schema_v1 como estructura JSON."""
    return json.loads(fixture_path(relative).read_text(encoding="utf-8"))


def walk(node: Any):
    """Recorre pares clave/valor de una estructura JSON anidada."""
    if isinstance(node, dict):
        for key, value in node.items():
            yield key, value
            yield from walk(value)
    elif isinstance(node, list):
        for item in node:
            yield from walk(item)


def all_fixture_files() -> list[Path]:
    """Lista todos los archivos presentes en el directorio de fixtures."""
    return sorted(path for path in FIXTURES_ROOT.rglob("*") if path.is_file())


@pytest.fixture()
def data_dir(tmp_path: Path) -> Path:
    """Copia los fixtures financieros a una carpeta temporal de perfil."""
    target = tmp_path / "perfil_ficticio" / "data"
    target.mkdir(parents=True)
    for name in PROFILE_DATA_FILES:
        shutil.copyfile(fixture_path(f"profile_data/{name}"), target / name)
    return target


@pytest.fixture()
def repository(data_dir: Path) -> BudgetRepository:
    """Entrega el repositorio productivo sobre los fixtures copiados."""
    return BudgetRepository(data_dir)


@pytest.fixture()
def frozen_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fija los defaults de fecha que producción aplica al cargar."""
    monkeypatch.setattr(models, "today_iso", lambda: FROZEN_TODAY)
    monkeypatch.setattr(models, "now_iso", lambda: FROZEN_NOW)
    monkeypatch.setattr(monthly_closure, "now_iso", lambda: FROZEN_NOW)


def build_profile_service(root: Path) -> ProfileService:
    """Crea el servicio de perfiles sobre una raíz temporal aislada."""
    return ProfileService(
        profiles_root=root / "perfiles",
        legacy_data_dir=root / "legacy_data",
        legacy_reports_dir=root / "legacy_reports",
        legacy_config_dir=root / "legacy_config",
    )


def install_catalog(root: Path, *names: str) -> Path:
    """Copia los fixtures de catálogo indicados a la raíz de perfiles."""
    profiles_root = root / "perfiles"
    profiles_root.mkdir(parents=True, exist_ok=True)
    for name in names:
        shutil.copyfile(fixture_path(f"catalog/{name}"), profiles_root / name)
    return profiles_root


def build_settings_service(root: Path) -> SettingsService:
    """Crea el servicio de configuración sobre carpetas temporales."""
    return SettingsService(
        config_dir=root / "configuracion",
        reports_dir=root / "reportes_por_defecto",
        backup_dir=root / "respaldo_por_defecto",
    )


def build_report_manager(root: Path) -> GestorReportes:
    """Crea un gestor de reportes con una clave efímera de prueba."""
    return GestorReportes(
        root / "reportes_cifrados",
        ProveedorClaveLocal(root / "clave_efimera" / "reporte.key"),
    )


def synthetic_report() -> ReporteEstructurado:
    """Devuelve la estructura sintética usada para el fixture de reporte."""
    return ReporteEstructurado(
        encabezado=["Reporte ficticio", "Periodo 2026-03"],
        secciones=[
            SeccionReporte(
                titulo="Resumen de ejemplo",
                lineas=["Ingresos: $ 1.200.000", "Gastos: $ 75.000"],
            ),
            SeccionReporte(titulo="Seccion vacia de ejemplo", lineas=[]),
        ],
    )


# ---------------------------------------------------------------------------
# Inventario y privacidad de los fixtures
# ---------------------------------------------------------------------------


def test_schema_v1_inventory_contains_only_expected_fixtures() -> None:
    """El directorio schema_v1 contiene exactamente los fixtures previstos."""
    found = {
        path.relative_to(FIXTURES_ROOT).as_posix()
        for path in all_fixture_files()
    }

    assert found == EXPECTED_FIXTURES


def test_schema_v1_fixtures_are_plain_json_without_binary_artifacts() -> None:
    """Sólo hay JSON de texto: ni claves, ni ZIP, ni reportes cifrados."""
    for path in all_fixture_files():
        assert path.suffix == ".json"
        assert path.suffix not in FORBIDDEN_SUFFIXES
        raw = path.read_bytes()
        assert b"\x00" not in raw
        assert isinstance(json.loads(raw.decode("utf-8")), (dict, list))


def test_schema_v1_fixtures_use_only_neutral_synthetic_text() -> None:
    """Los fixtures no incluyen rutas del equipo, correos ni unidades."""
    for path in all_fixture_files():
        text = path.read_text(encoding="utf-8")
        for forbidden in FORBIDDEN_TEXT:
            assert forbidden not in text, (path.name, forbidden)


def test_schema_v1_financial_fixtures_have_no_explicit_schema_version() -> None:
    """El formato legacy no declara versión salvo donde ya existe hoy."""
    for relative in sorted(EXPECTED_FIXTURES):
        keys = {key for key, _ in walk(load_fixture(relative))}
        if relative == "backup_manifest/manifest.json":
            assert "schema_version" in keys
            continue
        assert "schema_version" not in keys, relative
        if relative.startswith("report_payloads/"):
            assert "version" in keys
        else:
            assert "version" not in keys, relative


def test_schema_v1_amounts_are_integers() -> None:
    """Todos los montos escritos hoy son enteros en CLP."""
    seen = set()
    for name in PROFILE_DATA_FILES:
        for key, value in walk(load_fixture(f"profile_data/{name}")):
            if key in AMOUNT_FIELDS:
                assert type(value) is int, (name, key, value)
                seen.add(key)
            elif key in NULLABLE_AMOUNT_FIELDS:
                assert value is None or type(value) is int, (name, key)
                seen.add(key)

    assert seen == AMOUNT_FIELDS | NULLABLE_AMOUNT_FIELDS


def test_schema_v1_dates_and_timestamps_keep_current_format() -> None:
    """Fechas en YYYY-MM-DD y marcas ISO a segundos, sin zona horaria."""
    seen = set()
    for relative in sorted(EXPECTED_FIXTURES):
        for key, value in walk(load_fixture(relative)):
            if value is None:
                continue
            if key in DATE_FIELDS:
                assert DATE_PATTERN.fullmatch(value), (relative, key, value)
                seen.add(key)
            elif key in TIMESTAMP_FIELDS:
                assert TIMESTAMP_PATTERN.fullmatch(value), (relative, key)
                datetime.fromisoformat(value)
                seen.add(key)

    assert seen == DATE_FIELDS | TIMESTAMP_FIELDS


def test_schema_v1_ids_are_fixed_and_synthetic() -> None:
    """Los identificadores de los fixtures son fijos y reconocibles."""
    seen = set()
    for name in PROFILE_DATA_FILES:
        for key, value in walk(load_fixture(f"profile_data/{name}")):
            if key in ID_FIELDS and value is not None:
                assert SYNTHETIC_ID_PATTERN.fullmatch(value), (name, key)
                seen.add(key)

    assert seen == ID_FIELDS


# ---------------------------------------------------------------------------
# Formato actual: presupuesto mensual
# ---------------------------------------------------------------------------


def test_schema_v1_budget_fixture_loads_and_round_trips() -> None:
    """El presupuesto mensual sobrevive modelo y serialización sin cambios."""
    fixture = load_fixture("profile_data/presupuesto_2026-03.json")

    budget = MonthlyBudget.from_dict(fixture)

    assert budget.label == "2026-03"
    assert budget.to_dict() == fixture


def test_schema_v1_budget_written_field_names() -> None:
    """Documenta los nombres de campo que el presupuesto escribe hoy."""
    fixture = load_fixture("profile_data/presupuesto_2026-03.json")

    assert set(fixture) == {
        "year",
        "month",
        "categories",
        "transactions",
        "recurring_items",
        "created_at",
        "updated_at",
    }
    for item in fixture["categories"]:
        assert set(item) == {
            "name",
            "transaction_type",
            "budgeted_amount",
            "is_fixed",
            "alert_threshold",
            "budget_id",
            "currency",
            "start_date",
            "end_date",
            "active",
            "notes",
        }
    for item in fixture["transactions"]:
        assert set(item) == {
            "transaction_type",
            "category",
            "amount",
            "tx_date",
            "description",
            "payment_method",
            "transaction_id",
            "recurring_id",
            "is_unexpected",
            "debt_id",
            "account_id",
            "destination_account_id",
        }
    for item in fixture["recurring_items"]:
        assert set(item) == {
            "transaction_type",
            "category",
            "amount",
            "description",
            "day_of_month",
            "payment_method",
            "active",
            "recurring_id",
            "debt_id",
            "account_id",
        }


def test_schema_v1_budget_loads_through_repository(
    repository: BudgetRepository,
) -> None:
    """El repositorio productivo lee el fixture con su nombre de archivo."""
    fixture = load_fixture("profile_data/presupuesto_2026-03.json")

    assert repository.list_months() == ["2026-03"]
    assert repository.load(2026, 3).to_dict() == fixture


def test_schema_v1_budget_explicit_ids_are_stable_across_loads(
    repository: BudgetRepository,
) -> None:
    """Un ID presente en el archivo no cambia entre cargas."""
    first = repository.load(2026, 3)
    second = repository.load(2026, 3)

    assert [item.transaction_id for item in first.transactions] == [
        item.transaction_id for item in second.transactions
    ]
    assert [item.budget_id for item in first.categories] == [
        item.budget_id for item in second.categories
    ]
    assert [item.recurring_id for item in first.recurring_items] == [
        item.recurring_id for item in second.recurring_items
    ]


def test_schema_v1_budget_covers_every_current_transaction_type() -> None:
    """Los cuatro tipos de movimiento vigentes cargan correctamente."""
    fixture = load_fixture("profile_data/presupuesto_2026-03.json")

    types = {item["transaction_type"] for item in fixture["transactions"]}

    assert types == TRANSACTION_TYPES == {
        "gasto",
        "ingreso",
        "transferencia",
        "pago_deuda",
    }


# ---------------------------------------------------------------------------
# Formato actual: archivos globales del perfil
# ---------------------------------------------------------------------------


def test_schema_v1_accounts_fixture_round_trips(
    repository: BudgetRepository,
) -> None:
    """Las cuentas sobreviven carga y serialización sin cambios."""
    fixture = load_fixture("profile_data/cuentas.json")

    accounts = repository.load_accounts()

    assert set(fixture) == {"accounts"}
    assert [item.to_dict() for item in accounts] == fixture["accounts"]
    for item in fixture["accounts"]:
        assert set(item) == {
            "name",
            "account_type",
            "initial_balance",
            "real_balance",
            "registered_balance",
            "reconciliation_date",
            "reconciliation_status",
            "reconciliation_notes",
            "active",
            "account_id",
        }
        assert item["account_type"] in ACCOUNT_TYPES


def test_schema_v1_debts_fixture_round_trips(
    repository: BudgetRepository,
) -> None:
    """Las deudas sobreviven carga y serialización sin cambios."""
    fixture = load_fixture("profile_data/deudas.json")

    debts = repository.load_debts()

    assert set(fixture) == {"debts"}
    assert [item.to_dict() for item in debts] == fixture["debts"]
    for item in fixture["debts"]:
        assert set(item) == {
            "name",
            "category",
            "current_balance",
            "previous_month_balance",
            "current_monthly_payment",
            "minimum_payment",
            "monthly_interest_rate",
            "credit_limit",
            "start_date",
            "updated_at",
            "active",
            "debt_id",
        }
        assert item["category"] in DEBT_CATEGORIES
    rates = [item["monthly_interest_rate"] for item in fixture["debts"]]
    assert rates == [2.1, None]


def test_schema_v1_debt_payments_fixture_round_trips(
    repository: BudgetRepository,
) -> None:
    """Los pagos de deuda sobreviven carga y serialización sin cambios."""
    fixture = load_fixture("profile_data/debt_payments.json")

    payments = repository.load_debt_payments()

    assert set(fixture) == {"debt_payments"}
    assert [item.to_dict() for item in payments] == fixture["debt_payments"]
    for item in fixture["debt_payments"]:
        assert set(item) == {
            "debt_id",
            "account_id",
            "tx_date",
            "amount",
            "balance_before",
            "balance_after",
            "movement_id",
            "payment_type",
            "estimated_interest",
            "note",
            "payment_id",
            "created_at",
        }


def test_schema_v1_debt_snapshots_fixture_round_trips(
    repository: BudgetRepository,
) -> None:
    """Los snapshots de deuda sobreviven carga y serialización sin cambios."""
    fixture = load_fixture("profile_data/debt_snapshots.json")

    snapshots = repository.load_debt_snapshots()

    assert set(fixture) == {"debt_snapshots"}
    assert [item.to_dict() for item in snapshots] == fixture["debt_snapshots"]
    for item in fixture["debt_snapshots"]:
        assert set(item) == {
            "debt_id",
            "tx_date",
            "balance",
            "source",
            "movement_id",
            "previous_balance",
            "note",
            "snapshot_id",
            "created_at",
        }
    sources = {item["source"] for item in fixture["debt_snapshots"]}
    assert sources == {"manual", "pago"}


def test_schema_v1_monthly_closures_fixture_round_trips(
    repository: BudgetRepository,
) -> None:
    """Los cierres mensuales sobreviven carga y serialización sin cambios."""
    fixture = load_fixture("profile_data/monthly_closures.json")

    closures = repository.load_monthly_closures()

    assert set(fixture) == {"monthly_closures"}
    assert [item.to_dict() for item in closures] == fixture["monthly_closures"]
    for item in fixture["monthly_closures"]:
        assert set(item) == {
            "year",
            "month",
            "status",
            "closed_at",
            "report_generated",
            "movements_reviewed",
            "accounts_reconciled",
            "debts_reviewed",
            "budgets_reviewed",
            "notes",
            "closure_id",
            "id",
            "created_at",
            "updated_at",
        }
        assert item["status"] in MONTHLY_CLOSURE_STATUSES


def test_schema_v1_cross_references_use_existing_ids() -> None:
    """Las referencias entre archivos apuntan a IDs presentes en fixtures."""
    budget = load_fixture("profile_data/presupuesto_2026-03.json")
    account_ids = {
        item["account_id"]
        for item in load_fixture("profile_data/cuentas.json")["accounts"]
    }
    debt_ids = {
        item["debt_id"]
        for item in load_fixture("profile_data/deudas.json")["debts"]
    }
    movement_ids = {item["transaction_id"] for item in budget["transactions"]}

    for item in budget["transactions"]:
        assert item["account_id"] in account_ids
        if item["destination_account_id"] is not None:
            assert item["destination_account_id"] in account_ids
        if item["debt_id"] is not None:
            assert item["debt_id"] in debt_ids
    payments = load_fixture("profile_data/debt_payments.json")
    for item in payments["debt_payments"]:
        assert item["debt_id"] in debt_ids
        assert item["account_id"] in account_ids
        assert item["movement_id"] in movement_ids


# ---------------------------------------------------------------------------
# Formato actual: categorías
# ---------------------------------------------------------------------------


def test_schema_v1_categories_fixture_round_trips() -> None:
    """Las categorías sobreviven modelo y serialización sin cambios."""
    fixture = load_fixture("profile_data/categorias.json")

    assert set(fixture) == {"categories"}
    for item in fixture["categories"]:
        assert set(item) == {
            "id",
            "nombre",
            "tipo",
            "clase",
            "activa",
            "color_key",
            "created_at",
            "updated_at",
        }
        assert Categoria.from_dict(item).to_dict() == item
    assert {item["tipo"] for item in fixture["categories"]} == {
        "ingreso",
        "gasto",
        "ambos",
    }
    assert {item["clase"] for item in fixture["categories"]} == {
        "fija",
        "variable",
    }


def test_schema_v1_categories_load_through_service_without_rewrite(
    data_dir: Path,
) -> None:
    """Con categorías ya sincronizadas el servicio lee sin alterar el archivo."""
    fixture = load_fixture("profile_data/categorias.json")
    path = data_dir / "categorias.json"
    before = path.read_bytes()

    categories = CategoryService(data_dir=data_dir).listar_categorias()

    assert {item.id for item in categories} == {
        item["id"] for item in fixture["categories"]
    }
    assert path.read_bytes() == before


# ---------------------------------------------------------------------------
# Formato actual: configuración
# ---------------------------------------------------------------------------


def test_schema_v1_settings_fixture_round_trips(tmp_path: Path) -> None:
    """La configuración actual sobrevive carga y serialización."""
    fixture = load_fixture("profile_config/settings.json")
    service = build_settings_service(tmp_path)
    service.config_dir.mkdir(parents=True)
    shutil.copyfile(
        fixture_path("profile_config/settings.json"),
        service.settings_path,
    )

    config = service.cargar_configuracion()

    assert set(fixture) == {
        "carpeta_reportes",
        "moneda_principal",
        "apariencia",
        "cifrado_reportes",
        "carpeta_respaldo",
        "sincronizacion_habilitada",
    }
    assert config.to_dict() == fixture


def test_schema_v1_settings_saved_file_matches_fixture(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Guardar escribe los campos del fixture más la versión de esquema."""
    monkeypatch.chdir(tmp_path)
    fixture = load_fixture("profile_config/settings.json")
    service = build_settings_service(tmp_path)

    service.guardar_configuracion(dict(fixture))

    written = json.loads(service.settings_path.read_text(encoding="utf-8"))
    assert written == {**fixture, "schema_version": 1}


def test_schema_v1_settings_missing_file_uses_current_defaults(
    tmp_path: Path,
) -> None:
    """Sin archivo se devuelven los defaults del perfil sin crear nada."""
    service = build_settings_service(tmp_path)

    config = service.cargar_configuracion()

    assert config.to_dict() == {
        "carpeta_reportes": str(service.reports_dir),
        "moneda_principal": "CLP",
        "apariencia": "claro",
        "cifrado_reportes": True,
        "carpeta_respaldo": str(service.backup_dir),
        "sincronizacion_habilitada": False,
    }
    assert not service.settings_path.exists()


@pytest.mark.parametrize("apariencia", ("oscuro", "sistema"))
def test_schema_v1_settings_historical_appearance_still_loads(
    tmp_path: Path,
    apariencia: str,
) -> None:
    """Las preferencias históricas de apariencia se cargan sin modificarse."""
    data = load_fixture("profile_config/settings.json")
    data["apariencia"] = apariencia
    service = build_settings_service(tmp_path)
    service.config_dir.mkdir(parents=True)
    service.settings_path.write_text(json.dumps(data), encoding="utf-8")

    config = service.cargar_configuracion()

    assert config.apariencia == apariencia
    assert apariencia in SettingsService.APARIENCIAS_PERMITIDAS


def test_legacy_characterization_settings_empty_values_fall_back_to_defaults(
    tmp_path: Path,
) -> None:
    """Hoy los valores vacíos se sustituyen por defaults al cargar."""
    service = build_settings_service(tmp_path)
    service.config_dir.mkdir(parents=True)
    service.settings_path.write_text(
        json.dumps(
            {
                "carpeta_reportes": "",
                "moneda_principal": "",
                "apariencia": "",
                "carpeta_respaldo": "",
            },
        ),
        encoding="utf-8",
    )

    config = service.cargar_configuracion()

    assert config.carpeta_reportes == service.reports_dir
    assert config.carpeta_respaldo == service.backup_dir
    assert config.moneda_principal == "CLP"
    assert config.apariencia == "claro"
    assert config.cifrado_reportes is True
    assert config.sincronizacion_habilitada is False


def test_legacy_characterization_settings_unknown_values_load_unvalidated(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Hoy un valor no soportado se carga sin error y sólo falla al guardar."""
    monkeypatch.chdir(tmp_path)
    data = load_fixture("profile_config/settings.json")
    data["apariencia"] = "sepia"
    data["moneda_principal"] = "xyz"
    service = build_settings_service(tmp_path)
    service.config_dir.mkdir(parents=True)
    service.settings_path.write_text(json.dumps(data), encoding="utf-8")

    config = service.cargar_configuracion()

    assert config.apariencia == "sepia"
    assert config.moneda_principal == "XYZ"
    with pytest.raises(ValueError):
        service.guardar_configuracion(config)


def test_legacy_characterization_settings_unknown_field_is_currently_dropped(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Hoy un campo desconocido de settings.json se pierde al guardar."""
    monkeypatch.chdir(tmp_path)
    data = load_fixture("profile_config/settings.json")
    data["campo_futuro"] = "valor"
    service = build_settings_service(tmp_path)
    service.config_dir.mkdir(parents=True)
    service.settings_path.write_text(json.dumps(data), encoding="utf-8")

    service.guardar_configuracion(service.cargar_configuracion())

    written = json.loads(service.settings_path.read_text(encoding="utf-8"))
    assert "campo_futuro" not in written


# ---------------------------------------------------------------------------
# Formato actual: catálogo de perfiles
# ---------------------------------------------------------------------------


def test_schema_v1_catalog_fixture_field_names() -> None:
    """Documenta la estructura actual del catálogo y del perfil activo."""
    catalog = load_fixture("catalog/perfiles.json")
    active = load_fixture("catalog/perfil_activo.json")

    assert set(catalog) == {"perfiles"}
    for item in catalog["perfiles"]:
        assert set(item) == {"slug", "nombre"}
    assert set(active) == {"slug"}
    assert active["slug"] in {item["slug"] for item in catalog["perfiles"]}
    assert "personal" in {item["slug"] for item in catalog["perfiles"]}


def test_schema_v1_catalog_fixture_loads_through_profile_service(
    tmp_path: Path,
) -> None:
    """El servicio lee el catálogo actual sin reescribirlo."""
    fixture = load_fixture("catalog/perfiles.json")
    profiles_root = install_catalog(
        tmp_path,
        "perfiles.json",
        "perfil_activo.json",
    )

    service = build_profile_service(tmp_path)

    listed = [(item.id, item.nombre) for item in service.listar_perfiles()]
    assert listed == [
        ("hogar_ficticio", "Hogar Ficticio"),
        ("personal", "Personal"),
    ]
    assert service.obtener_activo().id == "hogar_ficticio"
    registry = json.loads(
        (profiles_root / "perfiles.json").read_text(encoding="utf-8"),
    )
    assert registry == fixture


def test_legacy_characterization_missing_catalog_only_registers_personal(
    tmp_path: Path,
) -> None:
    """Hoy un catálogo inexistente se recrea sólo con el perfil personal.

    La carpeta de otro perfil sigue en disco, pero deja de estar listada.
    """
    orphan = tmp_path / "perfiles" / "hogar_ficticio" / "data"
    orphan.mkdir(parents=True)

    service = build_profile_service(tmp_path)

    assert [item.id for item in service.listar_perfiles()] == ["personal"]
    assert service.obtener_activo().id == "personal"
    assert orphan.is_dir()
    registry = json.loads(service.registry_path.read_text(encoding="utf-8"))
    assert registry == {
        "perfiles": [{"nombre": "Personal", "slug": "personal"}],
        "schema_version": 1,
    }
    assert json.loads(service.active_path.read_text(encoding="utf-8")) == {
        "slug": "personal",
        "schema_version": 1,
    }


def test_legacy_characterization_corrupt_catalog_raises_json_error(
    tmp_path: Path,
) -> None:
    """Hoy un catálogo corrupto impide construir el servicio de perfiles."""
    profiles_root = install_catalog(tmp_path, "perfil_activo.json")
    (profiles_root / "perfiles.json").write_text(
        '{"perfiles": [',
        encoding="utf-8",
    )

    with pytest.raises(ValueError) as excinfo:
        build_profile_service(tmp_path)

    assert excinfo.type is json.JSONDecodeError


def test_legacy_characterization_active_profile_with_unknown_slug_fails(
    tmp_path: Path,
) -> None:
    """Hoy un perfil activo inexistente no se corrige: consultar falla."""
    profiles_root = install_catalog(tmp_path, "perfiles.json")
    (profiles_root / "perfil_activo.json").write_text(
        json.dumps({"slug": "perfil_inexistente"}),
        encoding="utf-8",
    )

    service = build_profile_service(tmp_path)

    with pytest.raises(UserFacingError):
        service.obtener_activo()
    assert all(not item.activo for item in service.listar_perfiles())
    assert json.loads(service.active_path.read_text(encoding="utf-8")) == {
        "slug": "perfil_inexistente",
    }


# ---------------------------------------------------------------------------
# Manifest de respaldo schema_version 1
# ---------------------------------------------------------------------------


def test_schema_v1_backup_manifest_fixture_round_trips() -> None:
    """El manifest versión 1 se lee y serializa sin cambios."""
    fixture = load_fixture("backup_manifest/manifest.json")
    service = BackupManifestService()

    manifest = service.from_json(
        fixture_path("backup_manifest/manifest.json").read_text(
            encoding="utf-8",
        ),
    )

    assert manifest.schema_version == SCHEMA_VERSION == 1
    assert manifest.to_dict() == fixture
    assert json.loads(service.to_json(manifest)) == fixture


def test_schema_v1_backup_manifest_structural_fields() -> None:
    """Documenta los campos estructurales actuales del manifest."""
    fixture = load_fixture("backup_manifest/manifest.json")

    assert set(fixture) == {
        "schema_version",
        "app",
        "created_at",
        "backup_type",
        "profile_id",
        "profile_name",
        "key_policy",
        "files",
    }
    assert fixture["app"] == "Avalancha V2"
    assert fixture["backup_type"] == "profile"
    assert set(fixture["key_policy"]) == {
        "includes_reporte_key",
        "protection",
        "portable_across_windows_users",
    }
    for item in fixture["files"]:
        assert set(item) == {"path", "size", "sha256", "role"}
        assert item["path"].startswith("profile/")
    # El fixture es un manifest v1 histórico: sus roles son un subconjunto
    # de los roles soportados hoy (que desde 22G incluyen profile_metadata,
    # inexistente en el contrato v1 original).
    assert {item["role"] for item in fixture["files"]}.issubset(BACKUP_FILE_ROLES)


def test_legacy_characterization_manifest_has_no_product_or_data_version() -> None:
    """Hoy el manifest no registra versión de producto ni de datos."""
    fixture = load_fixture("backup_manifest/manifest.json")

    for absent in ("app_version", "data_version", "profile_format_version"):
        assert absent not in fixture


@pytest.mark.parametrize("version", (0, "1", 1.0, True, None))
def test_schema_v1_backup_manifest_rejects_invalid_version(
    version: object,
) -> None:
    """Un tipo/valor de schema_version no entero-positivo se rechaza.

    Desde 22G, 2 es una versión soportada del manifest (ver test de
    versión futura, abajo), pero exige los campos nuevos de la versión 2;
    el fixture v1 no los tiene, así que se cubre aparte.
    """
    data = load_fixture("backup_manifest/manifest.json")
    data["schema_version"] = version

    with pytest.raises(InvalidBackupManifestError):
        BackupManifestService().from_json(json.dumps(data))


def test_schema_v1_backup_manifest_rejects_future_version() -> None:
    """Una versión por encima del techo soportado se rechaza como futura."""
    data = load_fixture("backup_manifest/manifest.json")
    data["schema_version"] = 999

    with pytest.raises(UnsupportedBackupVersionError):
        BackupManifestService().from_json(json.dumps(data))


def test_schema_v1_backup_manifest_v2_without_new_fields_is_invalid() -> None:
    """La versión 2 exige app_version y profile_format_version."""
    data = load_fixture("backup_manifest/manifest.json")
    data["schema_version"] = 2

    with pytest.raises(InvalidBackupManifestError):
        BackupManifestService().from_json(json.dumps(data))


def test_schema_v1_backup_manifest_rejects_missing_version() -> None:
    """Un manifest sin schema_version se rechaza hoy."""
    data = load_fixture("backup_manifest/manifest.json")
    del data["schema_version"]

    with pytest.raises(InvalidBackupManifestError):
        BackupManifestService().from_json(json.dumps(data))


# ---------------------------------------------------------------------------
# Estructura lógica de reporte e índice version 1 (previa al cifrado)
# ---------------------------------------------------------------------------


def test_schema_v1_report_document_matches_production_structure(
    tmp_path: Path,
) -> None:
    """El documento de reporte que se cifra hoy coincide con el fixture."""
    fixture = load_fixture("report_payloads/report_document.json")
    manager = build_report_manager(tmp_path)

    document = manager.generar_reporte(
        synthetic_report(),
        "2026-03",
        datetime(2026, 3, 31, 20, 0, 0),
    )

    assert set(document) == set(fixture) == {
        "version",
        "id",
        "mes",
        "fecha_creacion",
        "encabezado",
        "secciones",
    }
    assert GENERATED_ID_PATTERN.fullmatch(document["id"])
    assert {**document, "id": fixture["id"]} == fixture
    assert fixture["version"] == GestorReportes.VERSION == 1
    for section in fixture["secciones"]:
        assert set(section) == {"titulo", "lineas"}


def test_schema_v1_report_document_survives_encryption_round_trip(
    tmp_path: Path,
) -> None:
    """El payload del fixture se cifra y descifra sin alterarse."""
    fixture = load_fixture("report_payloads/report_document.json")
    manager = build_report_manager(tmp_path)

    encrypted = manager.cifrar_reporte(manager.serializar_reporte(fixture))

    assert manager.descifrar_reporte(encrypted) == fixture


def test_schema_v1_report_index_matches_production_structure(
    tmp_path: Path,
) -> None:
    """El índice de reportes que se cifra hoy coincide con el fixture."""
    fixture = load_fixture("report_payloads/report_index.json")
    manager = build_report_manager(tmp_path)

    entry = manager.guardar_reporte(
        synthetic_report(),
        "2026-03",
        datetime(2026, 3, 31, 20, 0, 0),
    )
    index = json.loads(
        manager.cifrador.decrypt(manager.ruta_indice.read_bytes()).decode(
            "utf-8",
        ),
    )

    assert set(index) == set(fixture) == {"version", "reportes"}
    assert index["version"] == fixture["version"] == 1
    assert len(index["reportes"]) == len(fixture["reportes"]) == 1
    written = index["reportes"][0]
    expected = fixture["reportes"][0]
    assert set(written) == set(expected) == {
        "id",
        "nombre",
        "mes",
        "fecha_creacion",
        "ruta",
        "hash",
    }
    assert written == entry
    assert re.fullmatch(r"[0-9a-f]{64}", written["hash"])
    assert re.fullmatch(r"[0-9a-f]{64}", expected["hash"])
    assert {**written, "id": expected["id"], "hash": expected["hash"]} == (
        expected
    )


@pytest.mark.parametrize("version", (99, None))
def test_legacy_characterization_report_version_is_not_validated_on_read(
    tmp_path: Path,
    version: int | None,
) -> None:
    """Hoy un reporte con versión desconocida o ausente se abre igual."""
    payload = load_fixture("report_payloads/report_document.json")
    if version is None:
        del payload["version"]
    else:
        payload["version"] = version
    manager = build_report_manager(tmp_path)

    opened = manager.descifrar_reporte(
        manager.cifrar_reporte(manager.serializar_reporte(payload)),
    )

    assert opened == payload


# ---------------------------------------------------------------------------
# Caracterización legacy: campos opcionales y defaults
# ---------------------------------------------------------------------------


def test_legacy_characterization_transaction_without_optional_fields(
    frozen_clock: None,
) -> None:
    """Hoy un movimiento mínimo se completa con defaults implícitos."""
    transaction = Transaction.from_dict(
        {
            "transaction_type": "gasto",
            "category": "Comida ficticia",
            "amount": 1000,
        },
    )

    data = transaction.to_dict()
    assert GENERATED_ID_PATTERN.fullmatch(data.pop("transaction_id"))
    assert data == {
        "transaction_type": "gasto",
        "category": "Comida ficticia",
        "amount": 1000,
        "tx_date": FROZEN_TODAY,
        "description": "",
        "payment_method": "No especificado",
        "recurring_id": None,
        "is_unexpected": False,
        "debt_id": None,
        "account_id": None,
        "destination_account_id": None,
    }


def test_legacy_characterization_budget_without_optional_fields(
    frozen_clock: None,
) -> None:
    """Hoy un presupuesto con sólo año y mes carga vacío y con marcas nuevas."""
    budget = MonthlyBudget.from_dict({"year": 2026, "month": 3})

    assert budget.to_dict() == {
        "year": 2026,
        "month": 3,
        "categories": [],
        "transactions": [],
        "recurring_items": [],
        "created_at": FROZEN_NOW,
        "updated_at": FROZEN_NOW,
    }


def test_legacy_characterization_category_budget_without_optional_fields(
    frozen_clock: None,
) -> None:
    """Hoy una categoría presupuestada mínima recibe defaults implícitos."""
    data = CategoryBudget.from_dict({"name": "Comida ficticia"}).to_dict()

    assert GENERATED_ID_PATTERN.fullmatch(data.pop("budget_id"))
    assert data == {
        "name": "Comida ficticia",
        "transaction_type": "gasto",
        "budgeted_amount": 0,
        "is_fixed": False,
        "alert_threshold": 80,
        "currency": "CLP",
        "start_date": FROZEN_TODAY,
        "end_date": None,
        "active": True,
        "notes": "",
    }


def test_legacy_characterization_account_without_optional_fields(
    frozen_clock: None,
) -> None:
    """Hoy una cuenta con sólo nombre recibe tipo, saldos y fecha implícitos."""
    data = CuentaFinanciera.from_dict({"name": "Cuenta ficticia"}).to_dict()

    assert GENERATED_ID_PATTERN.fullmatch(data.pop("account_id"))
    assert data == {
        "name": "Cuenta ficticia",
        "account_type": "otro",
        "initial_balance": 0,
        "real_balance": None,
        "registered_balance": 0,
        "reconciliation_date": FROZEN_TODAY,
        "reconciliation_status": "Pendiente",
        "reconciliation_notes": "",
        "active": True,
    }


def test_legacy_characterization_debt_without_optional_fields(
    frozen_clock: None,
) -> None:
    """Hoy una deuda con sólo nombre recibe categoría, saldos y fechas."""
    data = Debt.from_dict({"name": "Deuda ficticia"}).to_dict()

    assert GENERATED_ID_PATTERN.fullmatch(data.pop("debt_id"))
    assert data == {
        "name": "Deuda ficticia",
        "category": "otra",
        "current_balance": 0,
        "previous_month_balance": 0,
        "current_monthly_payment": 0,
        "minimum_payment": 0,
        "monthly_interest_rate": None,
        "credit_limit": 0,
        "start_date": FROZEN_TODAY,
        "updated_at": FROZEN_NOW,
        "active": True,
    }


def test_legacy_characterization_closure_without_optional_fields(
    frozen_clock: None,
) -> None:
    """Hoy un cierre con sólo año y mes queda abierto y sin revisar."""
    data = MonthlyClosure.from_dict({"year": 2026, "month": 3}).to_dict()

    closure_id = data.pop("closure_id")
    assert GENERATED_ID_PATTERN.fullmatch(closure_id)
    assert data.pop("id") == closure_id
    assert data == {
        "year": 2026,
        "month": 3,
        "status": "abierto",
        "closed_at": None,
        "report_generated": False,
        "movements_reviewed": False,
        "accounts_reconciled": False,
        "debts_reviewed": False,
        "budgets_reviewed": False,
        "notes": "",
        "created_at": FROZEN_NOW,
        "updated_at": FROZEN_NOW,
    }


def test_legacy_characterization_missing_files_load_as_empty(
    tmp_path: Path,
) -> None:
    """Hoy un archivo inexistente equivale a una colección vacía."""
    repository = BudgetRepository(tmp_path / "data_vacia")

    assert repository.load_accounts() == []
    assert repository.load_debts() == []
    assert repository.load_debt_payments() == []
    assert repository.load_debt_snapshots() == []
    assert repository.load_monthly_closures() == []
    assert repository.list_months() == []
    starter = repository.load(2026, 3)
    assert starter.transactions == []
    assert len(starter.categories) == 10
    assert not repository.budget_path(2026, 3).exists()


def test_legacy_characterization_missing_categories_file_is_created_on_read(
    tmp_path: Path,
) -> None:
    """Hoy leer categorías sin archivo lo crea con las categorías base."""
    service = CategoryService(data_dir=tmp_path / "data_vacia")
    assert not service.categories_path.exists()

    categories = service.listar_categorias()

    assert categories
    assert service.categories_path.exists()


# ---------------------------------------------------------------------------
# Caracterización legacy: alias históricos
# ---------------------------------------------------------------------------


def test_legacy_characterization_transaction_account_id_aliases() -> None:
    """Hoy se aceptan cuenta_id y cuenta_destino_id como alias de lectura."""
    transaction = Transaction.from_dict(
        {
            "transaction_type": "transferencia",
            "amount": 500,
            "tx_date": "2026-03-10",
            "cuenta_id": "acc_origen",
            "cuenta_destino_id": "acc_destino",
        },
    )

    data = transaction.to_dict()
    assert data["account_id"] == "acc_origen"
    assert data["destination_account_id"] == "acc_destino"
    assert "cuenta_id" not in data
    assert "cuenta_destino_id" not in data


def test_legacy_characterization_recurring_account_id_alias() -> None:
    """Hoy un recurrente acepta cuenta_id como alias de lectura."""
    recurring = RecurringItem.from_dict(
        {
            "transaction_type": "gasto",
            "category": "Transporte ficticio",
            "amount": 100,
            "description": "Abono de ejemplo",
            "cuenta_id": "acc_origen",
        },
    )

    assert recurring.account_id == "acc_origen"
    assert "cuenta_id" not in recurring.to_dict()


def test_legacy_characterization_account_id_and_type_aliases() -> None:
    """Hoy una cuenta acepta los alias históricos id y type."""
    account = CuentaFinanciera.from_dict(
        {
            "name": "Cuenta ficticia",
            "id": "acc_historica",
            "type": "ahorro",
            "reconciliation_date": "2026-03-01",
        },
    )

    data = account.to_dict()
    assert data["account_id"] == "acc_historica"
    assert data["account_type"] == "ahorro"
    assert "id" not in data
    assert "type" not in data


def test_legacy_characterization_account_initial_balance_falls_back() -> None:
    """Hoy sin initial_balance se reutiliza registered_balance como inicial."""
    account = CuentaFinanciera.from_dict(
        {
            "name": "Cuenta ficticia",
            "registered_balance": 7000,
            "reconciliation_date": "2026-03-01",
        },
    )

    assert account.initial_balance == 7000
    assert account.registered_balance == 7000


def test_legacy_characterization_debt_type_and_balance_aliases() -> None:
    """Hoy una deuda acepta los alias históricos debt_type e initial_balance."""
    debt = Debt.from_dict(
        {
            "name": "Deuda ficticia",
            "debt_type": "deuda_familiar",
            "initial_balance": 9000,
            "start_date": "2026-03-01",
        },
    )

    data = debt.to_dict()
    assert data["category"] == "deuda_familiar"
    assert data["current_balance"] == 9000
    assert "debt_type" not in data
    assert "initial_balance" not in data


def test_legacy_characterization_closure_id_alias_and_duplicate_id() -> None:
    """Hoy un cierre acepta id como alias y escribe id y closure_id."""
    closure = MonthlyClosure.from_dict(
        {"year": 2026, "month": 3, "id": "cie_historico"},
    )

    data = closure.to_dict()
    assert data["closure_id"] == "cie_historico"
    assert data["id"] == "cie_historico"


@pytest.mark.parametrize(
    ("legacy", "current"),
    (("tarjeta", "tarjeta_credito"), ("credito", "credito_consumo")),
)
def test_legacy_characterization_debt_category_mapping(
    legacy: str,
    current: str,
) -> None:
    """Hoy las categorías históricas de deuda se traducen al cargar."""
    debt = Debt.from_dict(
        {"name": "Deuda ficticia", "category": legacy, "start_date": "2026-03-01"},
    )

    assert debt.category == current
    assert debt.to_dict()["category"] == current


# ---------------------------------------------------------------------------
# Caracterización legacy: identificadores y fechas generados al cargar
# ---------------------------------------------------------------------------


def test_legacy_characterization_missing_transaction_id_is_regenerated() -> None:
    """Hoy un movimiento sin transaction_id recibe uno distinto en cada carga."""
    raw = {
        "transaction_type": "gasto",
        "category": "Comida ficticia",
        "amount": 1000,
        "tx_date": "2026-03-05",
    }

    first = Transaction.from_dict(raw).transaction_id
    second = Transaction.from_dict(raw).transaction_id

    assert GENERATED_ID_PATTERN.fullmatch(first)
    assert GENERATED_ID_PATTERN.fullmatch(second)
    assert first != second


def test_legacy_characterization_missing_account_id_is_regenerated() -> None:
    """Hoy una cuenta sin account_id recibe uno distinto en cada carga."""
    raw = {"name": "Cuenta ficticia", "reconciliation_date": "2026-03-01"}

    first = CuentaFinanciera.from_dict(raw).account_id
    second = CuentaFinanciera.from_dict(raw).account_id

    assert GENERATED_ID_PATTERN.fullmatch(first)
    assert first != second


def test_legacy_characterization_missing_debt_id_is_regenerated() -> None:
    """Hoy una deuda sin debt_id recibe uno distinto en cada carga."""
    raw = {"name": "Deuda ficticia", "start_date": "2026-03-01"}

    first = Debt.from_dict(raw).debt_id
    second = Debt.from_dict(raw).debt_id

    assert GENERATED_ID_PATTERN.fullmatch(first)
    assert first != second


def test_legacy_characterization_missing_ids_change_between_repository_loads(
    tmp_path: Path,
) -> None:
    """Hoy un archivo sin IDs entrega identificadores distintos por lectura."""
    repository = BudgetRepository(tmp_path / "data_sin_ids")
    repository.accounts_path.write_text(
        json.dumps(
            {
                "accounts": [
                    {
                        "name": "Cuenta ficticia",
                        "reconciliation_date": "2026-03-01",
                    },
                ],
            },
        ),
        encoding="utf-8",
    )

    first = repository.load_accounts()[0].account_id
    second = repository.load_accounts()[0].account_id

    assert first != second


def test_legacy_characterization_missing_dates_default_to_load_day(
    frozen_clock: None,
) -> None:
    """Hoy una fecha ausente se reemplaza por el día en que se carga."""
    transaction = Transaction.from_dict(
        {"transaction_type": "ingreso", "category": "Sueldo", "amount": 1},
    )
    category = CategoryBudget.from_dict({"name": "Comida ficticia"})
    debt = Debt.from_dict({"name": "Deuda ficticia"})
    account = CuentaFinanciera.from_dict({"name": "Cuenta ficticia"})
    payment = DebtPayment.from_dict(
        {
            "debt_id": "deb_x",
            "account_id": "acc_x",
            "tx_date": "2026-03-15",
            "amount": 10,
            "balance_before": 20,
            "balance_after": 10,
        },
    )
    snapshot = DebtSnapshot.from_dict(
        {"debt_id": "deb_x", "tx_date": "2026-03-15", "balance": 10},
    )

    assert transaction.tx_date == FROZEN_TODAY
    assert category.start_date == FROZEN_TODAY
    assert debt.start_date == FROZEN_TODAY
    assert debt.updated_at == FROZEN_NOW
    assert account.reconciliation_date == FROZEN_TODAY
    assert payment.created_at == FROZEN_NOW
    assert snapshot.created_at == FROZEN_NOW
    assert snapshot.source == "manual"
    assert payment.payment_type == "pago"


# ---------------------------------------------------------------------------
# Caracterización legacy: degradaciones y pérdidas silenciosas
# ---------------------------------------------------------------------------


def test_legacy_characterization_unknown_debt_category_becomes_otra() -> None:
    """Hoy una categoría de deuda desconocida se degrada a "otra" sin aviso."""
    debt = Debt.from_dict(
        {
            "name": "Deuda ficticia",
            "category": "categoria_futura",
            "start_date": "2026-03-01",
        },
    )

    assert debt.category == "otra"
    assert debt.to_dict()["category"] == "otra"


@pytest.mark.parametrize(
    ("model", "raw"),
    (
        (
            Transaction,
            {"transaction_type": "gasto", "category": "C", "amount": 1},
        ),
        (CategoryBudget, {"name": "C"}),
        (
            RecurringItem,
            {
                "transaction_type": "gasto",
                "category": "C",
                "amount": 1,
                "description": "D",
            },
        ),
        (Debt, {"name": "D"}),
        (CuentaFinanciera, {"name": "A"}),
        (
            DebtPayment,
            {
                "debt_id": "d",
                "account_id": "a",
                "tx_date": "2026-03-15",
                "amount": 1,
                "balance_before": 2,
                "balance_after": 1,
            },
        ),
        (
            DebtSnapshot,
            {"debt_id": "d", "tx_date": "2026-03-15", "balance": 1},
        ),
        (MonthlyClosure, {"year": 2026, "month": 3}),
        (
            Categoria,
            {"id": "c", "nombre": "C", "tipo": "gasto", "clase": "fija"},
        ),
    ),
)
def test_legacy_characterization_unknown_field_is_currently_dropped(
    model: Any,
    raw: dict[str, Any],
) -> None:
    """Hoy un campo desconocido desaparece tras modelar y serializar."""
    loaded = model.from_dict({**raw, "campo_futuro": "valor"})

    assert "campo_futuro" not in loaded.to_dict()


def test_legacy_characterization_unknown_field_is_lost_when_file_is_saved(
    repository: BudgetRepository,
) -> None:
    """Hoy guardar un archivo elimina los campos que el modelo no conoce."""
    raw = load_fixture("profile_data/cuentas.json")
    raw["campo_futuro_archivo"] = 1
    raw["accounts"][0]["campo_futuro"] = "valor"
    repository.accounts_path.write_text(json.dumps(raw), encoding="utf-8")

    repository.save_accounts(repository.load_accounts())

    written = json.loads(repository.accounts_path.read_text(encoding="utf-8"))
    assert written == {
        **load_fixture("profile_data/cuentas.json"),
        "schema_version": 1,
    }


@pytest.mark.parametrize(
    ("raw", "current"),
    (
        (1500, 1500),
        ("1500", 1500),
        ("1.500", 1500),
        ("1,500", 1500),
        (" 1.500.000 ", 1500000),
        (1500.0, 15000),
        ("1500.0", 15000),
        (12.5, 125),
        ("12,5", 125),
    ),
)
def test_legacy_characterization_validate_amount_strips_separators(
    raw: object,
    current: int,
) -> None:
    """Hoy validate_amount elimina puntos y comas sin interpretar decimales.

    Un valor con decimales queda multiplicado: 1500.0 se lee como 15000.
    """
    assert validate_amount(raw) == current


def test_legacy_characterization_decimal_amount_in_file_is_reinterpreted() -> None:
    """Hoy un monto decimal en el JSON se carga como otro monto entero."""
    transaction = Transaction.from_dict(
        {
            "transaction_type": "gasto",
            "category": "Comida ficticia",
            "amount": 1500.0,
            "tx_date": "2026-03-05",
        },
    )

    assert transaction.amount == 15000
    assert type(transaction.amount) is int


def test_legacy_characterization_text_fields_are_normalized_on_load() -> None:
    """Hoy los textos se recortan y los tipos se pasan a minúsculas."""
    transaction = Transaction.from_dict(
        {
            "transaction_type": "  GASTO ",
            "category": "  Comida ficticia  ",
            "amount": 1,
            "tx_date": "2026-03-05",
            "payment_method": "   ",
        },
    )

    assert transaction.transaction_type == "gasto"
    assert transaction.category == "Comida ficticia"
    assert transaction.payment_method == "No especificado"


# ---------------------------------------------------------------------------
# Errores actuales (sin errores de dominio todavía)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("file_name", "loader"),
    (
        ("cuentas.json", "load_accounts"),
        ("deudas.json", "load_debts"),
        ("debt_payments.json", "load_debt_payments"),
        ("debt_snapshots.json", "load_debt_snapshots"),
        ("monthly_closures.json", "load_monthly_closures"),
    ),
)
def test_legacy_characterization_invalid_json_raises_json_decode_error(
    repository: BudgetRepository,
    file_name: str,
    loader: str,
) -> None:
    """Hoy un JSON truncado produce JSONDecodeError sin error de dominio."""
    (repository.data_dir / file_name).write_text('{"x": [', encoding="utf-8")

    with pytest.raises(ValueError) as excinfo:
        getattr(repository, loader)()

    assert excinfo.type is json.JSONDecodeError


def test_legacy_characterization_invalid_budget_json_raises_json_decode_error(
    repository: BudgetRepository,
) -> None:
    """Hoy un presupuesto truncado produce JSONDecodeError."""
    repository.budget_path(2026, 3).write_text('{"year": 2026,', encoding="utf-8")

    with pytest.raises(ValueError) as excinfo:
        repository.load(2026, 3)

    assert excinfo.type is json.JSONDecodeError


def test_legacy_characterization_invalid_categories_json_raises_json_error(
    data_dir: Path,
) -> None:
    """Hoy un categorias.json truncado produce JSONDecodeError."""
    (data_dir / "categorias.json").write_text("{", encoding="utf-8")

    with pytest.raises(ValueError) as excinfo:
        CategoryService(data_dir=data_dir).listar_categorias()

    assert excinfo.type is json.JSONDecodeError


def test_legacy_characterization_invalid_settings_json_raises_json_error(
    tmp_path: Path,
) -> None:
    """Hoy un settings.json truncado produce JSONDecodeError."""
    service = build_settings_service(tmp_path)
    service.config_dir.mkdir(parents=True)
    service.settings_path.write_text("{", encoding="utf-8")

    with pytest.raises(ValueError) as excinfo:
        service.cargar_configuracion()

    assert excinfo.type is json.JSONDecodeError


def test_legacy_characterization_non_object_json_raises_attribute_error(
    repository: BudgetRepository,
) -> None:
    """Hoy un JSON válido que no es objeto falla con AttributeError."""
    repository.accounts_path.write_text("[]", encoding="utf-8")

    with pytest.raises(AttributeError):
        repository.load_accounts()


@pytest.mark.parametrize(
    ("model", "raw", "missing"),
    (
        (Transaction, {"category": "C", "amount": 1}, "transaction_type"),
        (Transaction, {"transaction_type": "gasto", "category": "C"}, "amount"),
        (
            RecurringItem,
            {"transaction_type": "gasto", "category": "C", "amount": 1},
            "description",
        ),
        (CategoryBudget, {"budgeted_amount": 1}, "name"),
        (Debt, {"category": "otra"}, "name"),
        (CuentaFinanciera, {"account_type": "otro"}, "name"),
        (
            DebtPayment,
            {
                "account_id": "a",
                "tx_date": "2026-03-15",
                "amount": 1,
                "balance_before": 2,
                "balance_after": 1,
            },
            "debt_id",
        ),
        (DebtSnapshot, {"debt_id": "d", "tx_date": "2026-03-15"}, "balance"),
        (MonthlyBudget, {"month": 3}, "year"),
        (MonthlyClosure, {"year": 2026}, "month"),
    ),
)
def test_legacy_characterization_missing_required_field_raises_key_error(
    model: Any,
    raw: dict[str, Any],
    missing: str,
) -> None:
    """Hoy un campo obligatorio ausente produce KeyError con su nombre."""
    with pytest.raises(KeyError) as excinfo:
        model.from_dict(raw)

    assert excinfo.value.args == (missing,)


def test_legacy_characterization_category_missing_fields_raise_value_error() -> None:
    """Hoy una categoría sin id produce ValueError genérico."""
    with pytest.raises(ValueError) as excinfo:
        Categoria.from_dict({"nombre": "C", "tipo": "gasto", "clase": "fija"})

    assert excinfo.type is ValueError


def test_legacy_characterization_unknown_transaction_type_raises_value_error() -> None:
    """Hoy un tipo de movimiento desconocido produce ValueError genérico."""
    with pytest.raises(ValueError) as excinfo:
        Transaction.from_dict(
            {
                "transaction_type": "tipo_futuro",
                "category": "C",
                "amount": 1,
                "tx_date": "2026-03-05",
            },
        )

    assert excinfo.type is ValueError


def test_legacy_characterization_unknown_account_type_raises_value_error() -> None:
    """Hoy un tipo de cuenta desconocido produce ValueError genérico."""
    with pytest.raises(ValueError) as excinfo:
        CuentaFinanciera.from_dict(
            {
                "name": "Cuenta ficticia",
                "account_type": "tipo_futuro",
                "reconciliation_date": "2026-03-01",
            },
        )

    assert excinfo.type is ValueError


def test_legacy_characterization_unknown_closure_status_raises_value_error() -> None:
    """Hoy un estado de cierre desconocido produce ValueError genérico."""
    with pytest.raises(ValueError) as excinfo:
        MonthlyClosure.from_dict(
            {"year": 2026, "month": 3, "status": "estado_futuro"},
        )

    assert excinfo.type is ValueError


def test_legacy_characterization_unknown_snapshot_source_raises_value_error() -> None:
    """Hoy un origen de snapshot desconocido produce ValueError genérico."""
    with pytest.raises(ValueError) as excinfo:
        DebtSnapshot.from_dict(
            {
                "debt_id": "d",
                "tx_date": "2026-03-15",
                "balance": 1,
                "source": "origen_futuro",
            },
        )

    assert excinfo.type is ValueError


def test_legacy_characterization_one_unknown_value_blocks_the_whole_file(
    repository: BudgetRepository,
) -> None:
    """Hoy una sola cuenta con tipo desconocido impide cargar todas."""
    raw = load_fixture("profile_data/cuentas.json")
    raw["accounts"][1]["account_type"] = "tipo_futuro"
    repository.accounts_path.write_text(json.dumps(raw), encoding="utf-8")

    with pytest.raises(ValueError) as excinfo:
        repository.load_accounts()

    assert excinfo.type is ValueError


# ---------------------------------------------------------------------------
# Caracterización legacy: BudgetService reescribe presupuestos al leer
# ---------------------------------------------------------------------------


def write_legacy_budget_without_ids(data_dir: Path) -> tuple[Path, dict[str, Any]]:
    """Escribe un presupuesto legacy con categorías sin budget_id utilizable.

    Parte del fixture actual y deja una categoría sin la clave, otra con la
    clave vacía y la tercera con su ID original. Agrega campos desconocidos
    para observar qué ocurre con ellos.
    """
    raw = load_fixture("profile_data/presupuesto_2026-03.json")
    by_name = {item["name"]: item for item in raw["categories"]}
    del by_name["Comida ficticia"]["budget_id"]
    by_name["Sueldo ficticio"]["budget_id"] = ""
    by_name["Comida ficticia"]["campo_futuro_categoria"] = "valor"
    raw["campo_futuro_archivo"] = 7
    data_dir.mkdir(parents=True, exist_ok=True)
    path = data_dir / "presupuesto_2026-03.json"
    path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
    return path, raw


def read_budgets(data_dir: Path) -> dict[str, str]:
    """Lee presupuestos por la ruta pública y devuelve sus IDs por nombre."""
    service = BudgetService(data_dir=data_dir, year=2026, month=3)
    return {item.nombre: item.id for item in service.obtener_presupuestos()}


def test_legacy_characterization_budget_service_persists_missing_budget_ids_on_read(
    tmp_path: Path,
) -> None:
    """Hoy leer un presupuesto sin budget_id lo completa y regraba en disco.

    La reescritura edita el JSON crudo: sólo agrega los ID que faltan y deja
    intacto todo lo demás, incluidos los campos que el modelo no conoce.
    """
    data_dir = tmp_path / "data_legacy"
    path, raw = write_legacy_budget_without_ids(data_dir)
    initial_bytes = path.read_bytes()

    listed = read_budgets(data_dir)

    assert path.read_bytes() != initial_bytes
    written = json.loads(path.read_text(encoding="utf-8"))
    written_by_name = {item["name"]: item for item in written["categories"]}
    raw_by_name = {item["name"]: item for item in raw["categories"]}
    generated = {
        name: written_by_name[name]["budget_id"]
        for name in ("Comida ficticia", "Sueldo ficticio")
    }
    for budget_id in generated.values():
        assert GENERATED_ID_PATTERN.fullmatch(budget_id)
    assert len(set(generated.values())) == 2
    assert written_by_name["Transporte ficticio"] == (
        raw_by_name["Transporte ficticio"]
    )
    for name in generated:
        assert {**written_by_name[name], "budget_id": None} == {
            **raw_by_name[name],
            "budget_id": None,
        }
    assert [item["name"] for item in written["categories"]] == [
        item["name"] for item in raw["categories"]
    ]
    assert written_by_name["Comida ficticia"]["campo_futuro_categoria"] == (
        "valor"
    )
    assert written["campo_futuro_archivo"] == 7
    assert written["updated_at"] == raw["updated_at"]
    assert written["created_at"] == raw["created_at"]
    assert written["transactions"] == raw["transactions"]
    assert written["recurring_items"] == raw["recurring_items"]
    assert set(written) == set(raw) | {"schema_version"}
    assert written["schema_version"] == 1
    assert listed == {
        "Comida ficticia": generated["Comida ficticia"],
        "Transporte ficticio": raw_by_name["Transporte ficticio"]["budget_id"],
    }


def test_legacy_characterization_budget_service_second_read_is_idempotent(
    tmp_path: Path,
) -> None:
    """Hoy la segunda lectura conserva los ID generados y no vuelve a escribir."""
    data_dir = tmp_path / "data_legacy"
    path, _ = write_legacy_budget_without_ids(data_dir)

    first_listed = read_budgets(data_dir)
    first_bytes = path.read_bytes()
    first_ids = [
        item["budget_id"]
        for item in json.loads(first_bytes.decode("utf-8"))["categories"]
    ]

    second_listed = read_budgets(data_dir)
    second_bytes = path.read_bytes()
    second_ids = [
        item["budget_id"]
        for item in json.loads(second_bytes.decode("utf-8"))["categories"]
    ]

    assert all(first_ids)
    assert second_ids == first_ids
    assert second_listed == first_listed
    assert second_bytes == first_bytes


def test_legacy_characterization_budget_service_does_not_rewrite_when_ids_exist(
    data_dir: Path,
) -> None:
    """Hoy un presupuesto con todos sus budget_id se lee sin tocar el archivo."""
    fixture = load_fixture("profile_data/presupuesto_2026-03.json")
    path = data_dir / "presupuesto_2026-03.json"
    initial_bytes = path.read_bytes()

    listed = read_budgets(data_dir)

    assert path.read_bytes() == initial_bytes
    assert listed == {
        item["name"]: item["budget_id"]
        for item in fixture["categories"]
        if item["transaction_type"] == "gasto"
    }
