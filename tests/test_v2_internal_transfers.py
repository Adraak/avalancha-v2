"""Pruebas de transferencias internas en Avalancha V2."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from avalancha.models import (
    CategoryBudget,
    CuentaFinanciera,
    EXPENSE,
    INCOME,
    MonthlyBudget,
)
from avalancha.storage import BudgetRepository
from services.account_service import AccountService
from services.budget_service import BudgetService
from services.dashboard_visual_service import DashboardVisualService
from services.financial_alert_service import FinancialAlertService
from services.movement_service import MovementService
from services.reconciliation_service import ReconciliationService
from services.report_service import ReportService


class InternalTransfersTest(unittest.TestCase):
    """Valida que transferir entre cuentas no altere finanzas reales."""

    def setUp(self) -> None:
        """Crea un perfil temporal con dos cuentas y presupuesto base."""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.data_dir = self.root / "data"
        self.repository = BudgetRepository(self.data_dir)
        self.repository.save(
            MonthlyBudget(
                year=2026,
                month=6,
                categories=[
                    CategoryBudget("Sueldo", INCOME, 0, True),
                    CategoryBudget("Comida", EXPENSE, 100_000, False),
                ],
            ),
        )
        self.repository.save_accounts(
            [
                CuentaFinanciera(
                    account_id="origen",
                    name="Cuenta origen",
                    account_type="debito",
                    initial_balance=100_000,
                    real_balance=70_000,
                ),
                CuentaFinanciera(
                    account_id="destino",
                    name="Cuenta destino",
                    account_type="ahorro",
                    initial_balance=10_000,
                    real_balance=40_000,
                ),
                CuentaFinanciera(
                    account_id="tercero",
                    name="Cuenta sin relacion",
                    account_type="efectivo",
                    initial_balance=0,
                    real_balance=0,
                ),
            ],
        )
        self.movement_service = MovementService(
            data_dir=self.data_dir,
            year=2026,
            month=6,
            repository=self.repository,
        )

    def tearDown(self) -> None:
        """Elimina datos temporales de prueba."""
        self.temp_dir.cleanup()

    def test_crear_transferencia_valida(self) -> None:
        """Crea una transferencia sin categoria ni imprevisto."""
        movimiento = self.movement_service.crear_transferencia(
            fecha="10-06-2026",
            cuenta_origen_id="origen",
            cuenta_destino_id="destino",
            monto=30_000,
            descripcion="Traspaso a ahorro",
        )

        loaded = self.repository.load(2026, 6)

        self.assertEqual(movimiento.tipo, "transferencia")
        self.assertEqual(movimiento.categoria, "")
        self.assertFalse(movimiento.imprevisto)
        self.assertEqual(movimiento.clase, "Transferencia")
        self.assertEqual(movimiento.cuenta_destino_id, "destino")
        self.assertEqual(loaded.transactions[0].transaction_type, "transferencia")
        self.assertEqual(loaded.transactions[0].destination_account_id, "destino")

    def test_crear_movimiento_despacha_transferencia(self) -> None:
        """Permite crear transferencia desde la API general."""
        movimiento = self.movement_service.crear_movimiento(
            fecha="10-06-2026",
            tipo="transferencia",
            cuenta_id="origen",
            cuenta_destino_id="destino",
            monto="30000",
            descripcion="Traspaso",
        )

        self.assertTrue(movimiento.es_transferencia)
        self.assertEqual(self.movement_service.obtener_movimientos()[0].id, movimiento.id)

    def test_filtra_transferencias_por_origen_y_destino(self) -> None:
        """Incluye transferencias al filtrar por origen o destino."""
        transferencia = self.movement_service.crear_transferencia(
            "10-06-2026",
            "origen",
            "destino",
            30_000,
        )
        gasto = self.movement_service.crear_movimiento(
            "11-06-2026",
            "gasto",
            "Comida",
            "origen",
            5_000,
        )

        origen = self.movement_service.obtener_movimientos_por_cuenta("origen")
        destino = self.movement_service.obtener_movimientos_por_cuenta("destino")
        tercero = self.movement_service.obtener_movimientos_por_cuenta("tercero")

        self.assertEqual({item.id for item in origen}, {transferencia.id, gasto.id})
        self.assertEqual([item.id for item in destino], [transferencia.id])
        self.assertEqual(tercero, [])

    def test_validaciones_transferencia(self) -> None:
        """Rechaza transferencias incompletas o inconsistentes."""
        with self.assertRaisesRegex(ValueError, "mayor que cero"):
            self.movement_service.crear_transferencia(
                "10-06-2026",
                "origen",
                "destino",
                0,
            )
        with self.assertRaisesRegex(ValueError, "cuenta"):
            self.movement_service.crear_transferencia(
                "10-06-2026",
                "",
                "destino",
                10_000,
            )
        with self.assertRaisesRegex(ValueError, "destino"):
            self.movement_service.crear_transferencia(
                "10-06-2026",
                "origen",
                "",
                10_000,
            )
        with self.assertRaisesRegex(ValueError, "distintas"):
            self.movement_service.crear_transferencia(
                "10-06-2026",
                "origen",
                "origen",
                10_000,
            )
        with self.assertRaisesRegex(ValueError, "destino"):
            self.movement_service.crear_transferencia(
                "10-06-2026",
                "origen",
                "cuenta-otro-perfil",
                10_000,
            )
        with self.assertRaisesRegex(ValueError, "imprevisto"):
            self.movement_service.crear_movimiento(
                "10-06-2026",
                "transferencia",
                "",
                "origen",
                10_000,
                imprevisto=True,
                cuenta_destino_id="destino",
            )

    def test_conciliacion_descuenta_origen_y_suma_destino(self) -> None:
        """Calcula saldos registrados con transferencia interna."""
        self.movement_service.crear_transferencia(
            "10-06-2026",
            "origen",
            "destino",
            30_000,
        )
        service = ReconciliationService(
            data_dir=self.data_dir,
            year=2026,
            month=6,
            repository=self.repository,
            movement_service=self.movement_service,
        )
        origen = service.obtener_conciliacion_por_cuenta("origen")
        destino = service.obtener_conciliacion_por_cuenta("destino")

        self.assertEqual(origen.saldo_registrado, 70_000)
        self.assertEqual(destino.saldo_registrado, 40_000)
        self.assertEqual(
            origen.saldo_registrado + destino.saldo_registrado,
            110_000,
        )

    def test_cuentas_acumulan_transferencias_de_todos_los_meses(self) -> None:
        """Cuentas muestra saldo actual sin depender del mes activo."""
        self.movement_service.crear_transferencia(
            "10-06-2026",
            "origen",
            "destino",
            30_000,
        )
        self.repository.save(
            MonthlyBudget(
                year=2026,
                month=7,
                categories=[
                    CategoryBudget("Sueldo", INCOME, 0, True),
                    CategoryBudget("Comida", EXPENSE, 100_000, False),
                ],
            ),
        )
        MovementService(
            data_dir=self.data_dir,
            year=2026,
            month=7,
            repository=self.repository,
        ).crear_transferencia(
            "05-07-2026",
            "destino",
            "origen",
            10_000,
        )

        junio = AccountService(
            data_dir=self.data_dir,
            year=2026,
            month=6,
            repository=self.repository,
        )
        julio = AccountService(
            data_dir=self.data_dir,
            year=2026,
            month=7,
            repository=self.repository,
        )

        self.assertEqual(
            junio.obtener_cuenta_por_id("origen").registered_balance,
            80_000,
        )
        self.assertEqual(
            junio.obtener_cuenta_por_id("destino").registered_balance,
            30_000,
        )
        self.assertEqual(
            julio.obtener_cuenta_por_id("origen").registered_balance,
            80_000,
        )
        self.assertEqual(
            julio.obtener_cuenta_por_id("destino").registered_balance,
            30_000,
        )

    def test_dashboard_excluye_transferencia_de_totales(self) -> None:
        """No altera ingresos, gastos, flujo, clases ni categorias."""
        self.movement_service.crear_movimiento(
            "01-06-2026",
            "ingreso",
            "Sueldo",
            "origen",
            200_000,
        )
        self.movement_service.crear_movimiento(
            "02-06-2026",
            "gasto",
            "Comida",
            "origen",
            50_000,
        )
        self.movement_service.crear_transferencia(
            "03-06-2026",
            "origen",
            "destino",
            30_000,
        )

        data = DashboardVisualService(
            data_dir=self.data_dir,
            repository=self.repository,
        ).obtener_dashboard(2026, 6)
        cards = {item.titulo: item.monto for item in data.tarjetas}
        category_totals = {
            item.etiqueta: item.monto for item in data.gastos_por_categoria
        }
        class_totals = {item.etiqueta: item.monto for item in data.gastos_por_clase}

        self.assertEqual(cards["Ingresos del mes"], 200_000)
        self.assertEqual(cards["Gastos del mes"], 50_000)
        self.assertEqual(cards["Flujo libre"], 150_000)
        self.assertEqual(cards["Imprevistos"], 0)
        self.assertEqual(category_totals, {"Comida": 50_000})
        self.assertEqual(class_totals["Normal"], 50_000)
        self.assertEqual(class_totals["Imprevisto"], 0)

    def test_presupuesto_y_alertas_ignoran_transferencia(self) -> None:
        """No consume presupuesto ni genera alerta por gasto."""
        transfer = self.movement_service.crear_transferencia(
            "10-06-2026",
            "origen",
            "destino",
            30_000,
        )
        budget_service = BudgetService(
            data_dir=self.data_dir,
            year=2026,
            month=6,
            repository=self.repository,
            movement_service=self.movement_service,
        )
        presupuesto = next(
            item
            for item in budget_service.obtener_presupuestos()
            if item.categoria == "Comida"
        )
        ejecucion = budget_service.calcular_ejecucion(presupuesto.id)
        alertas = FinancialAlertService().generar_alertas(
            indicadores=type(
                "Indicadores",
                (),
                {
                    "flujo_libre": 0,
                    "gastos_reales": 0,
                    "ingresos_reales": 0,
                    "deuda_actual": 0,
                    "gastos_imprevistos": 0,
                },
            )(),
            categorias=[],
        )

        self.assertTrue(transfer.es_transferencia)
        self.assertEqual(ejecucion.monto_gastado, 0)
        self.assertEqual(ejecucion.porcentaje_utilizado, 0.0)
        self.assertEqual(alertas[0].nivel, "info")
        self.assertTrue(alertas[0].titulo.startswith("Sin alertas"))

    def test_reporte_lista_transferencia_separada(self) -> None:
        """Reporta transferencias sin alterar ingresos ni gastos."""
        self.movement_service.crear_movimiento(
            "01-06-2026",
            "ingreso",
            "Sueldo",
            "origen",
            200_000,
        )
        self.movement_service.crear_transferencia(
            "03-06-2026",
            "origen",
            "destino",
            30_000,
            "Ahorro mensual",
        )

        report = ReportService(
            data_dir=self.data_dir,
            reports_dir=self.root / "reportes",
            key_path=self.root / "config" / "reporte.key",
            repository=self.repository,
        ).generar_reporte_mensual(6, 2026)

        self.assertIn("Ingresos reales: $ 200.000", report.contenido)
        self.assertIn("Gastos reales: $ 0", report.contenido)
        self.assertIn("TRANSFERENCIAS INTERNAS", report.contenido)
        self.assertIn("Cuenta origen → Cuenta destino", report.contenido)
        self.assertIn("Ahorro mensual", report.contenido)

    def test_ui_expone_transferencia_y_filtro_sin_storage_directo(self) -> None:
        """Verifica estructura UI sin acceder directo a storage."""
        dialog = Path("ui_pyside6/pages/movement_dialog.py").read_text(
            encoding="utf-8",
        )
        page = Path("ui_pyside6/pages/movement_page.py").read_text(
            encoding="utf-8",
        )

        self.assertIn("Transferencia interna", dialog)
        self.assertIn("destination_account_input", dialog)
        self.assertIn("category_label.setVisible", dialog)
        self.assertIn("filtrar_por_cuenta", page)
        self.assertIn("cuenta_destino_id", page)
        self.assertIn("→", page)
        self.assertNotIn("BudgetRepository", dialog)
        self.assertNotIn("avalancha.storage", dialog)
        self.assertNotIn("BudgetRepository", page)
        self.assertNotIn("avalancha.storage", page)


if __name__ == "__main__":
    unittest.main()
