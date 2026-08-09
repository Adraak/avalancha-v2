"""Pruebas de arquitectura para separar nucleo e interfaz."""

from __future__ import annotations

import subprocess
import sys
import textwrap
import unittest
from pathlib import Path


class V2ArchitectureTest(unittest.TestCase):
    """Verifica que el nucleo V2 no cargue librerias de interfaz."""

    def test_core_services_import_without_ui_frameworks(self) -> None:
        """Importa modelos y servicios en un proceso limpio sin UI."""
        project_root = Path(__file__).resolve().parents[1]
        script = textwrap.dedent(
            """
            import sys
            import tempfile
            from datetime import date
            from pathlib import Path

            from core.models.cuenta import Cuenta
            from core.models.categoria import Categoria
            from core.models.conciliacion import Conciliacion
            from core.models.configuracion import ConfiguracionAplicacion
            from core.models.deuda import Deuda
            from core.models.monthly_closure import MonthlyClosure
            from core.models.movimiento import Movimiento
            from core.models.perfil_financiero import PerfilFinanciero
            from core.models.presupuesto import Presupuesto
            from core.models.resumen_mensual import ResumenMensual
            from services.account_service import AccountService
            from services.budget_service import BudgetService
            from services.category_service import CategoryService
            from services.dashboard_visual_service import DashboardVisualService
            from services.demo_profile_service import DemoProfileService
            from services.debt_analytics_service import DebtAnalyticsService
            from services.debt_service import DebtService
            from services.financial_alert_service import FinancialAlertService
            from services.financial_summary_service import FinancialSummaryService
            from services.movement_service import MovementService
            from services.monthly_closure_service import MonthlyClosureService
            from services.profile_service import ProfileService
            from services.reconciliation_service import ReconciliationService
            from services.report_service import ReportService
            from services.settings_service import SettingsService

            Movimiento(
                id="mov-1",
                fecha=date(2026, 6, 1),
                tipo="gasto",
                categoria="Comida",
                descripcion="Compra",
                monto=1000,
                cuenta_id="cuenta-1",
                medio_pago="Debito",
            )
            Cuenta(id="cuenta-1", nombre="Cuenta prueba", tipo="debito")
            Categoria(
                id="cat-prueba",
                nombre="Categoria prueba",
                tipo="gasto",
                clase="variable",
            )
            Conciliacion(
                id="conciliacion-1",
                cuenta_id="cuenta-1",
                saldo_real=1000,
                saldo_registrado=1000,
                fecha_conciliacion=date(2026, 6, 1),
            )
            Deuda(
                id="deuda-1",
                nombre="Tarjeta prueba",
                categoria="tarjeta_credito",
                saldo_actual=100000,
                saldo_mes_anterior=120000,
                pago_mensual_actual=20000,
            )
            PerfilFinanciero(
                id="perfil-1",
                nombre="Perfil prueba",
                ruta_datos="data/perfiles/prueba",
            )
            Presupuesto(id="presupuesto-1", mes="2026-06")
            ResumenMensual(mes="2026-06")
            MonthlyClosure(year=2026, month=6)
            ConfiguracionAplicacion(
                carpeta_reportes=Path("reportes"),
                carpeta_respaldo=Path("backup"),
            )
            temp_dir = tempfile.TemporaryDirectory()
            root = Path(temp_dir.name)
            AccountService()
            BudgetService()
            CategoryService(data_dir=root / "data")
            DashboardVisualService(data_dir=root / "data")
            FinancialAlertService()
            FinancialSummaryService()
            MovementService()
            MonthlyClosureService(data_dir=root / "data")
            ReconciliationService()
            profile_service = ProfileService(
                profiles_root=root / "perfiles",
                legacy_data_dir=root / "legacy_data",
                legacy_reports_dir=root / "legacy_reports",
                legacy_config_dir=root / "legacy_config",
            )
            DemoProfileService(profile_service)
            DebtService(data_dir=root / "data")
            DebtAnalyticsService(data_dir=root / "data")
            ReportService(
                data_dir=root / "data",
                reports_dir=root / "reportes",
                key_path=root / "config" / "reporte.key",
            )
            SettingsService(
                config_dir=root / "config",
                reports_dir=root / "reportes",
                backup_dir=root / "backup",
            )
            temp_dir.cleanup()

            modulos_prohibidos = [
                nombre
                for nombre in sys.modules
                if nombre == "tkinter"
                or nombre.startswith("tkinter.")
                or nombre == "PySide6"
                or nombre.startswith("PySide6.")
            ]
            if modulos_prohibidos:
                raise SystemExit(
                    "Modulos de UI cargados: "
                    + ", ".join(sorted(modulos_prohibidos))
                )
            """
        )

        result = subprocess.run(
            [sys.executable, "-c", script],
            cwd=project_root,
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)

    def test_dashboard_ui_no_importa_storage_directo(self) -> None:
        """Evita que el Dashboard acceda directo a almacenamiento."""
        project_root = Path(__file__).resolve().parents[1]
        dashboard = (
            project_root / "ui_pyside6" / "pages" / "dashboard_page.py"
        ).read_text(encoding="utf-8")

        self.assertNotIn("BudgetRepository", dashboard)
        self.assertNotIn("avalancha.storage", dashboard)
        self.assertNotIn("json.", dashboard)

    def test_dashboard_ui_usa_color_system(self) -> None:
        """Confirma que colores visuales vienen del sistema central."""
        project_root = Path(__file__).resolve().parents[1]
        dashboard = (
            project_root / "ui_pyside6" / "pages" / "dashboard_page.py"
        ).read_text(encoding="utf-8")

        self.assertIn("ui_pyside6.color_system", dashboard)

    def test_monthly_closure_ui_no_importa_storage_directo(self) -> None:
        """Evita que Cierre mensual acceda directo a almacenamiento."""
        project_root = Path(__file__).resolve().parents[1]
        closure_page = (
            project_root / "ui_pyside6" / "pages" / "monthly_closure_page.py"
        ).read_text(encoding="utf-8")

        self.assertNotIn("BudgetRepository", closure_page)
        self.assertNotIn("avalancha.storage", closure_page)
        self.assertNotIn("json.", closure_page)

    def test_categories_ui_no_importa_storage_directo(self) -> None:
        """Evita que Categorias acceda directo a almacenamiento."""
        project_root = Path(__file__).resolve().parents[1]
        categories_page = (
            project_root / "ui_pyside6" / "pages" / "categories_page.py"
        ).read_text(encoding="utf-8")

        self.assertNotIn("BudgetRepository", categories_page)
        self.assertNotIn("avalancha.storage", categories_page)
        self.assertNotIn("json.", categories_page)

    def test_categories_ui_textos_finales(self) -> None:
        """Verifica textos visibles de Categorias en espanol."""
        project_root = Path(__file__).resolve().parents[1]
        main_window = (
            project_root / "ui_pyside6" / "main_window.py"
        ).read_text(encoding="utf-8")
        categories_page = (
            project_root / "ui_pyside6" / "pages" / "categories_page.py"
        ).read_text(encoding="utf-8")
        category_dialog = (
            project_root / "ui_pyside6" / "pages" / "category_dialog.py"
        ).read_text(encoding="utf-8")

        self.assertIn('"Categorías"', main_window)
        self.assertIn("Sección activa", main_window)
        self.assertIn('"Categorías"', categories_page)
        self.assertIn('"Automático"', categories_page)
        self.assertIn('"Guardar"', category_dialog)
        self.assertIn('"Cancelar"', category_dialog)
        self.assertNotIn('form.addRow("Color"', category_dialog)

    def test_dashboard_alertas_usan_texto_limpio(self) -> None:
        """Evita marcadores visuales problemáticos en alertas."""
        project_root = Path(__file__).resolve().parents[1]
        dashboard = (
            project_root / "ui_pyside6" / "pages" / "dashboard_page.py"
        ).read_text(encoding="utf-8")

        self.assertIn("_alert_title_text", dashboard)
        old_detail_text = "Detalle " + "abajo"
        self.assertNotIn(old_detail_text, dashboard)
        self.assertNotIn("{[", dashboard)
        self.assertNotIn("[{", dashboard)


if __name__ == "__main__":
    unittest.main()
