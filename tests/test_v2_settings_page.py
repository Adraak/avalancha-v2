"""Pruebas de la pagina de configuracion UI."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QLineEdit,
    QPushButton,
)

from core.models.configuracion import ConfiguracionAplicacion
from services.settings_service import SettingsService
from ui_pyside6.pages.settings_page import SettingsPage

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="session")
def app() -> QApplication:
    """Crea una unica QApplication para las pruebas de widgets."""
    return QApplication.instance() or QApplication(sys.argv)


@pytest.fixture()
def service(tmp_path: Path) -> SettingsService:
    """Entrega un SettingsService aislado por directorio temporal."""
    return SettingsService(
        tmp_path / "config",
        tmp_path / "reportes",
        tmp_path / "backup",
    )


@pytest.fixture()
def page(app: QApplication, service: SettingsService) -> SettingsPage:
    """Crea una pagina de configuracion lista para interactuar."""
    _ = app
    widget = SettingsPage(service)
    yield widget
    widget.deleteLater()


def test_settings_page_instantiation(page: SettingsPage) -> None:
    """Verifica que SettingsPage se pueda instanciar correctamente."""
    assert page is not None


def test_settings_page_load_initial_values(
    page: SettingsPage,
    service: SettingsService,
) -> None:
    """Verifica que SettingsPage cargue la configuracion inicial."""
    config = service.cargar_configuracion()

    assert page.reportes_input.text() == str(config.carpeta_reportes)
    assert page.respaldo_input.text() == str(config.carpeta_respaldo)
    assert page.moneda_combo.currentText() == "CLP"
    assert page.apariencia_combo.currentText() == "Claro"
    assert page.cifrado_check.isChecked()
    assert not page.sincronizacion_check.isChecked()
    assert page.estado_label.text() == "Configuración cargada."


def test_settings_page_has_required_controls(page: SettingsPage) -> None:
    """Verifica que SettingsPage tenga controles principales."""
    assert isinstance(page.moneda_combo, QComboBox)
    assert isinstance(page.apariencia_combo, QComboBox)
    assert isinstance(page.cifrado_check, QCheckBox)
    assert isinstance(page.sincronizacion_check, QCheckBox)
    assert isinstance(page.reportes_input, QLineEdit)
    assert isinstance(page.respaldo_input, QLineEdit)

    buttons = page.findChildren(QPushButton)
    save_button = next((b for b in buttons if b.text() == "Guardar"), None)
    cancel_button = next((b for b in buttons if b.text() == "Cancelar"), None)
    defaults_button = next(
        (b for b in buttons if b.text() == "Restaurar valores por defecto"),
        None,
    )

    assert save_button is not None
    assert cancel_button is not None
    assert defaults_button is not None


def test_settings_page_valid_modification_is_saved(
    page: SettingsPage,
    service: SettingsService,
    tmp_path: Path,
) -> None:
    """Guarda cambios validos mediante SettingsService."""
    reports = tmp_path / "reportes_configurados"
    backup = tmp_path / "backup_configurado"

    page.reportes_input.setText(str(reports))
    page.respaldo_input.setText(str(backup))
    page.moneda_combo.setCurrentText("USD")
    page.apariencia_combo.setCurrentText("Oscuro")
    page.cifrado_check.setChecked(False)
    page.sincronizacion_check.setChecked(True)

    page.save()
    loaded = service.cargar_configuracion()

    assert loaded.carpeta_reportes == reports
    assert loaded.carpeta_respaldo == backup
    assert loaded.moneda_principal == "USD"
    assert loaded.apariencia == "oscuro"
    assert not loaded.cifrado_reportes
    assert loaded.sincronizacion_habilitada
    assert page.estado_label.text() == "Configuración guardada."


def test_settings_page_rejects_invalid_currency(
    page: SettingsPage,
    service: SettingsService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Rechaza valores que SettingsService considera invalidos."""
    errors: list[str] = []
    monkeypatch.setattr(page, "_show_error", errors.append)
    page.moneda_combo.setEditable(True)
    page.moneda_combo.setCurrentText("BTC")

    page.save()

    assert errors == ["La moneda principal no esta soportada."]
    assert service.cargar_configuracion().moneda_principal == "CLP"


def test_settings_page_rejects_invalid_backup_path(
    page: SettingsPage,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Maneja ruta de respaldo invalida sin guardar cambios."""
    invalid_backup = tmp_path / "backup.txt"
    invalid_backup.write_text("contenido", encoding="utf-8")
    errors: list[str] = []
    monkeypatch.setattr(page, "_show_error", errors.append)

    page.respaldo_input.setText(str(invalid_backup))
    page.save()

    assert errors == ["La carpeta de respaldo no es valida."]


def test_settings_page_keeps_profiles_isolated(
    app: QApplication,
    tmp_path: Path,
) -> None:
    """Verifica aislamiento por perfil desde la UI."""
    _ = app
    personal = SettingsService(
        tmp_path / "personal" / "config",
        tmp_path / "personal" / "reportes",
        tmp_path / "personal" / "backup",
    )
    demo = SettingsService(
        tmp_path / "demo" / "config",
        tmp_path / "demo" / "reportes",
        tmp_path / "demo" / "backup",
    )
    personal_page = SettingsPage(personal)
    demo_page = SettingsPage(demo)

    personal_page.moneda_combo.setCurrentText("CLP")
    personal_page.apariencia_combo.setCurrentText("Claro")
    personal_page.reportes_input.setText(str(tmp_path / "personal_reports"))
    personal_page.respaldo_input.setText(str(tmp_path / "personal_backup"))
    personal_page.save()

    demo_page.moneda_combo.setCurrentText("EUR")
    demo_page.apariencia_combo.setCurrentText("Oscuro")
    demo_page.reportes_input.setText(str(tmp_path / "demo_reports"))
    demo_page.respaldo_input.setText(str(tmp_path / "demo_backup"))
    demo_page.save()

    assert personal.cargar_configuracion().moneda_principal == "CLP"
    assert demo.cargar_configuracion().moneda_principal == "EUR"
    assert (
        personal.cargar_configuracion().carpeta_reportes
        != demo.cargar_configuracion().carpeta_reportes
    )

    personal_page.deleteLater()
    demo_page.deleteLater()


def test_settings_page_does_not_import_storage_directly() -> None:
    """Verifica que la UI no acceda directamente a almacenamiento."""
    page_source = Path("ui_pyside6/pages/settings_page.py").read_text(
        encoding="utf-8",
    )

    assert "BudgetRepository" not in page_source
    assert "avalancha.storage" not in page_source
    assert "json." not in page_source


def test_settings_page_handles_service_error(
    app: QApplication,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Muestra error comprensible si falla el servicio."""
    _ = app
    service = FailingSettingsService()
    page = SettingsPage(service)  # type: ignore[arg-type]
    errors: list[str] = []
    monkeypatch.setattr(page, "_show_error", errors.append)

    page.save()

    assert errors == ["Falla controlada del servicio."]
    assert service.saved_payload is not None
    page.deleteLater()


def test_settings_page_preserves_unmodified_values(
    page: SettingsPage,
    service: SettingsService,
) -> None:
    """Conserva valores que el usuario no modifico."""
    original = service.cargar_configuracion()
    page.moneda_combo.setCurrentText("EUR")

    page.save()
    loaded = service.cargar_configuracion()

    assert loaded.moneda_principal == "EUR"
    assert loaded.carpeta_reportes == original.carpeta_reportes
    assert loaded.carpeta_respaldo == original.carpeta_respaldo
    assert loaded.apariencia == original.apariencia
    assert loaded.cifrado_reportes == original.cifrado_reportes
    assert (
        loaded.sincronizacion_habilitada
        == original.sincronizacion_habilitada
    )


class FailingSettingsService:
    """Doble de prueba que simula una falla al guardar."""

    MONEDAS_PERMITIDAS = SettingsService.MONEDAS_PERMITIDAS
    APARIENCIAS_PERMITIDAS = SettingsService.APARIENCIAS_PERMITIDAS

    def __init__(self) -> None:
        """Inicializa estado de observacion para la prueba."""
        self.saved_payload: dict[str, object] | None = None

    def cargar_configuracion(self) -> ConfiguracionAplicacion:
        """Entrega configuracion base para cargar la pagina."""
        return ConfiguracionAplicacion(
            carpeta_reportes=Path("reportes"),
            carpeta_respaldo=Path("backup"),
        )

    def guardar_configuracion(
        self,
        datos: dict[str, object] | ConfiguracionAplicacion,
    ) -> ConfiguracionAplicacion:
        """Registra los datos y simula error de servicio."""
        self.saved_payload = dict(datos) if isinstance(datos, dict) else {}
        raise RuntimeError("Falla controlada del servicio.")

    def restaurar_valores_por_defecto(self) -> ConfiguracionAplicacion:
        """Simula restauracion no usada por esta prueba."""
        raise RuntimeError("Falla controlada del servicio.")
