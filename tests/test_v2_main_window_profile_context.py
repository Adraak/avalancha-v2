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
from ui_pyside6.pages.dashboard_page import DashboardPage  # noqa: E402
from ui_pyside6.pages.debts_page import DebtsPage  # noqa: E402
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

    def test_cambio_movimientos_refresca_vistas_financieras(self) -> None:
        """La senal de Movimientos recarga paginas financieras afectadas."""
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
            dashboard_page = self._find_page(window, DashboardPage)
            accounts_page = self._find_accounts_page(window)
            debts_page = self._find_page(window, DebtsPage)
            refreshed: list[str] = []

            self._count_refresh(dashboard_page, refreshed, "dashboard")
            self._count_refresh(accounts_page, refreshed, "accounts")
            self._count_refresh(debts_page, refreshed, "debts")

            movements_page.movements_changed.emit("created")

            self.assertIn("dashboard", refreshed)
            self.assertIn("accounts", refreshed)
            self.assertIn("debts", refreshed)
            window.close()

    def test_navegar_a_deudas_refresca_la_tabla(self) -> None:
        """Entrar a Deudas vuelve a pedir datos al servicio."""
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
            debts_page = self._find_page(window, DebtsPage)
            refreshed: list[str] = []
            self._count_refresh(debts_page, refreshed, "debts")

            window._select_section(self._find_page_index(window, DebtsPage))

            self.assertEqual(refreshed, ["debts"])
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

    @staticmethod
    def _find_page(window: MainWindow, page_type: type) -> object:
        """Busca una pagina por tipo dentro del stack principal."""
        for index in range(window.stack.count()):
            widget = window.stack.widget(index)
            if isinstance(widget, page_type):
                return widget
        raise AssertionError(f"No se encontro la pagina {page_type.__name__}.")

    @staticmethod
    def _find_page_index(window: MainWindow, page_type: type) -> int:
        """Busca el indice de una pagina por tipo."""
        for index in range(window.stack.count()):
            if isinstance(window.stack.widget(index), page_type):
                return index
        raise AssertionError(f"No se encontro la pagina {page_type.__name__}.")

    @staticmethod
    def _count_refresh(page: object, calls: list[str], label: str) -> None:
        """Reemplaza refresh por un contador que conserva el metodo original."""
        original = getattr(page, "refresh")

        def counted_refresh() -> None:
            calls.append(label)
            original()

        setattr(page, "refresh", counted_refresh)


if __name__ == "__main__":
    unittest.main()
