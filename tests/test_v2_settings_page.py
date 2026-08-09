from PySide6.QtWidgets import QApplication
import sys
from ui_pyside6.pages.settings_page import SettingsPage
from services.settings_service import SettingsService

def test_settings_page_instantiation(tmp_path) -> None:
    """Test that SettingsPage can be instantiated correctly."""
    if not QApplication.instance():
        QApplication(sys.argv)

    config_dir = tmp_path / "config"
    reports_dir = tmp_path / "reportes"
    backup_dir = tmp_path / "backup"

    service = SettingsService(str(config_dir), str(reports_dir), str(backup_dir))
    page = SettingsPage(service)

    assert page is not None
    page.deleteLater()
