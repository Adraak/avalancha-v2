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
            from core.models.conciliacion import Conciliacion
            from core.models.deuda import Deuda
            from core.models.movimiento import Movimiento
            from core.models.perfil_financiero import PerfilFinanciero
            from core.models.presupuesto import Presupuesto
            from core.models.resumen_mensual import ResumenMensual
            from services.account_service import AccountService
            from services.budget_service import BudgetService
            from services.demo_profile_service import DemoProfileService
            from services.financial_summary_service import FinancialSummaryService
            from services.movement_service import MovementService
            from services.profile_service import ProfileService
            from services.reconciliation_service import ReconciliationService
            from services.report_service import ReportService

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
            AccountService()
            BudgetService()
            FinancialSummaryService()
            MovementService()
            ReconciliationService()
            temp_dir = tempfile.TemporaryDirectory()
            root = Path(temp_dir.name)
            profile_service = ProfileService(
                profiles_root=root / "perfiles",
                legacy_data_dir=root / "legacy_data",
                legacy_reports_dir=root / "legacy_reports",
                legacy_config_dir=root / "legacy_config",
            )
            DemoProfileService(profile_service)
            ReportService(
                data_dir=root / "data",
                reports_dir=root / "reportes",
                key_path=root / "config" / "reporte.key",
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


if __name__ == "__main__":
    unittest.main()
