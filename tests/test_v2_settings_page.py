"""Pruebas de la pagina de configuracion UI."""

from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication, QPushButton, QComboBox

from services.settings_service import SettingsService
from ui_pyside6.pages.settings_page import SettingsPage


def test_settings_page_instantiation(tmp_path) -> None:
    """Verifica que SettingsPage se pueda instanciar correctamente."""
    if QApplication.instance() is None:
        _ = QApplication(sys.argv)

    config_dir = tmp_path / "config"
    reports_dir = tmp_path / "reportes"
    backup_dir = tmp_path / "backup"

    service = SettingsService(str(config_dir), str(reports_dir), str(backup_dir))
    page = SettingsPage(service)

    assert page is not None
    page.deleteLater()


def test_settings_page_load_initial_values(tmp_path) -> None:
    """Verifica que SettingsPage cargue la configuracion inicial."""
    if QApplication.instance() is None:
        _ = QApplication(sys.argv)

    config_dir = tmp_path / "config"
    reports_dir = tmp_path / "reportes"
    backup_dir = tmp_path / "backup"

    service = SettingsService(str(config_dir), str(reports_dir), str(backup_dir))
    page = SettingsPage(service)

    assert page.moneda_combo.currentText() != ""
    assert page.apariencia_combo.currentText() != ""
    assert page.estado_label.text() == "Configuración cargada."

    page.deleteLater()


def test_settings_page_has_required_controls(tmp_path) -> None:
    """Verifica que SettingsPage tenga controles principales."""
    if QApplication.instance() is None:
        _ = QApplication(sys.argv)

    config_dir = tmp_path / "config"
    reports_dir = tmp_path / "reportes"
    backup_dir = tmp_path / "backup"

    service = SettingsService(str(config_dir), str(reports_dir), str(backup_dir))
    page = SettingsPage(service)

    # Verificar que los controles principales existen
    assert isinstance(page.moneda_combo, QComboBox)
    assert isinstance(page.apariencia_combo, QComboBox)
    assert isinstance(page.cifrado_check, type(page.cifrado_check))
    assert isinstance(page.sincronizacion_check, type(page.sincronizacion_check))
    assert isinstance(page.reportes_input, type(page.reportes_input))
    assert isinstance(page.respaldo_input, type(page.respaldo_input))

    # Verificar que los botones existen
    # No se puede usar findChild con texto en este caso porque los botones no tienen nombre
    buttons = page.findChildren(QPushButton)
    save_button = next((b for b in buttons if b.text() == "Guardar"), None)
    cancel_button = next((b for b in buttons if b.text() == "Cancelar"), None)
    defaults_button = next((b for b in buttons if b.text() == "Restaurar valores por defecto"), None)

    assert save_button is not None
    assert cancel_button is not None
    assert defaults_button is not None

    page.deleteLater()