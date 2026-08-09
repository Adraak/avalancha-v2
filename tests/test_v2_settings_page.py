"""Pruebas de la pagina de configuracion UI."""

from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

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