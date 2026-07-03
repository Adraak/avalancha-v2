"""Pruebas de contexto de perfil en la ventana principal V2."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from services.demo_profile_service import DemoProfileService  # noqa: E402
from services.profile_service import ProfileService  # noqa: E402
from ui_pyside6.main_window import MainWindow  # noqa: E402
from ui_pyside6.pages.accounts_page import AccountsPage  # noqa: E402
from ui_pyside6.pages.movement_dialog import MovementDialog  # noqa: E402
from ui_pyside6.pages.movement_page import MovementsPage  # noqa: E402


class MainWindowProfileContextTest(unittest.TestCase):
    """Valida que la UI use servicios del perfil activo."""

    @classmethod
    def setUpClass(cls) -> None:
        """Asegura una aplicacion Qt para construir widgets."""
        cls.app = QApplication.instance() or QApplication([])

    def test_movimientos_demo_muestra_cuentas_demo(self) -> None:
        """El combo de cuentas usa cuentas del perfil Demo activo."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            profile_service = ProfileService(
                profiles_root=root / "perfiles",
                legacy_data_dir=root / "legacy_data",
                legacy_reports_dir=root / "legacy_reports",
                legacy_config_dir=root / "legacy_config",
            )
            demo_service = DemoProfileService(profile_service)
            demo_service.abrir_demo()

            window = MainWindow(profile_service, demo_service)
            movements_page = self._find_movements_page(window)
            dialog = MovementDialog(movements_page.service)
            account_names = [
                dialog.account_input.itemText(index)
                for index in range(dialog.account_input.count())
            ]

            self.assertEqual(movements_page.service.year, 2026)
            self.assertEqual(movements_page.service.month, 6)
            self.assertIn("Cuenta corriente Demo Avalancha", account_names)
            self.assertIn("Tarjeta de crédito Demo Avalancha", account_names)

            dialog.close()
            window.close()

    def test_cuentas_puede_abrir_movimientos_filtrados(self) -> None:
        """La ventana filtra Movimientos desde una cuenta seleccionada."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            profile_service = ProfileService(
                profiles_root=root / "perfiles",
                legacy_data_dir=root / "legacy_data",
                legacy_reports_dir=root / "legacy_reports",
                legacy_config_dir=root / "legacy_config",
            )
            demo_service = DemoProfileService(profile_service)
            demo_service.abrir_demo()
            window = MainWindow(profile_service, demo_service)
            accounts_page = self._find_accounts_page(window)
            movements_page = self._find_movements_page(window)
            account = accounts_page.service.obtener_cuentas_activas()[0]

            window._open_account_movements(account.account_id, account.name)

            self.assertEqual(window.stack.currentWidget(), movements_page)
            self.assertEqual(movements_page._account_filter_id, account.account_id)
            self.assertIn(account.name, movements_page.filter_label.text())
            self.assertFalse(movements_page.clear_filter_button.isHidden())
            window.close()

    def test_cuentas_emite_solicitud_de_ver_movimientos(self) -> None:
        """El boton de Cuentas emite la cuenta seleccionada."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            profile_service = ProfileService(
                profiles_root=root / "perfiles",
                legacy_data_dir=root / "legacy_data",
                legacy_reports_dir=root / "legacy_reports",
                legacy_config_dir=root / "legacy_config",
            )
            demo_service = DemoProfileService(profile_service)
            demo_service.abrir_demo()
            window = MainWindow(profile_service, demo_service)
            accounts_page = self._find_accounts_page(window)
            selected = []

            accounts_page.movements_requested.connect(
                lambda account_id, name: selected.append((account_id, name)),
            )
            accounts_page.table.selectRow(0)
            accounts_page.view_selected_movements()

            self.assertEqual(len(selected), 1)
            self.assertTrue(selected[0][0])
            self.assertTrue(selected[0][1])
            window.close()

    @staticmethod
    def _find_movements_page(window: MainWindow) -> MovementsPage:
        """Busca la pagina Movimientos dentro del stack principal."""
        for index in range(window.stack.count()):
            widget = window.stack.widget(index)
            if isinstance(widget, MovementsPage):
                return widget
        raise AssertionError("No se encontro la pagina de movimientos.")

    @staticmethod
    def _find_accounts_page(window: MainWindow) -> AccountsPage:
        """Busca la pagina Cuentas dentro del stack principal."""
        for index in range(window.stack.count()):
            widget = window.stack.widget(index)
            if isinstance(widget, AccountsPage):
                return widget
        raise AssertionError("No se encontro la pagina de cuentas.")


if __name__ == "__main__":
    unittest.main()
