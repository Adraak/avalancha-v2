"""Pruebas transversales de coherencia financiera de Avalancha V2."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from avalancha.models import (
    CategoryBudget,
    CuentaFinanciera,
    DEBT_PAYMENT,
    Debt,
    EXPENSE,
    INCOME,
    MonthlyBudget,
    Transaction,
)
from avalancha.storage import BudgetRepository
from services.account_service import AccountService
from services.budget_service import BudgetService
from services.dashboard_visual_service import DashboardVisualService
from services.debt_service import DebtService
from services.movement_service import MovementService
from services.reconciliation_service import ReconciliationService
from services.report_service import ReportService


class FinancialCoherenceTest(unittest.TestCase):
    """Valida reglas oficiales entre servicios financieros."""

    def setUp(self) -> None:
        """Prepara un repositorio temporal con cuentas, deuda y presupuesto."""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.data_dir = self.root / "data"
        self.repository = BudgetRepository(self.data_dir)
        self._guardar_presupuesto(2026, 6)
        self.repository.save_accounts(
            [
                CuentaFinanciera(
                    account_id="cuenta-origen",
                    name="Cuenta origen",
                    account_type="cuenta_corriente",
                    initial_balance=100_000,
                    real_balance=720_000,
                ),
                CuentaFinanciera(
                    account_id="cuenta-destino",
                    name="Cuenta destino",
                    account_type="ahorro",
                    initial_balance=50_000,
                    real_balance=230_000,
                ),
            ],
        )
        self.repository.save_debts(
            [
                Debt(
                    debt_id="deuda-tarjeta",
                    name="Tarjeta prueba",
                    category="tarjeta_credito",
                    current_balance=300_000,
                    previous_month_balance=350_000,
                    current_monthly_payment=50_000,
                    minimum_payment=20_000,
                    active=True,
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
        """Elimina los archivos temporales de prueba."""
        self.temp_dir.cleanup()

    def test_metricas_transversales_excluyen_movimientos_no_reales(
        self,
    ) -> None:
        """Valida ingresos, gastos, presupuesto, imprevistos y deuda."""
        self._crear_escenario_junio()

        dashboard = DashboardVisualService(
            data_dir=self.data_dir,
            repository=self.repository,
        ).obtener_dashboard(2026, 6)
        cards = {item.titulo: item.monto for item in dashboard.tarjetas}
        categorias = {
            item.etiqueta: item.monto for item in dashboard.gastos_por_categoria
        }
        clases = {item.etiqueta: item.monto for item in dashboard.gastos_por_clase}
        budget_service = BudgetService(
            data_dir=self.data_dir,
            year=2026,
            month=6,
            repository=self.repository,
            movement_service=self.movement_service,
        )
        ejecuciones = {
            item["presupuesto"].categoria: item["ejecucion"].monto_gastado
            for item in budget_service.calcular_ejecucion_general()
        }

        self.assertEqual(cards["Ingresos del mes"], 1_000_000)
        self.assertEqual(cards["Gastos del mes"], 110_000)
        self.assertEqual(cards["Flujo libre"], 890_000)
        self.assertEqual(cards["Imprevistos"], 30_000)
        self.assertEqual(cards["Deuda total"], 250_000)
        self.assertEqual(categorias, {"Comida": 80_000, "Salud": 30_000})
        self.assertEqual(clases["Normal"], 80_000)
        self.assertEqual(clases["Imprevisto"], 30_000)
        self.assertEqual(ejecuciones["Comida"], 80_000)
        self.assertEqual(ejecuciones["Salud"], 30_000)
        self.assertEqual(
            self.repository.debt_payment_totals(
                self.repository.load(2026, 6),
            ),
            {},
        )
        self.assertEqual(
            DebtService(
                data_dir=self.data_dir,
                repository=self.repository,
            ).obtener_deuda_por_id("deuda-tarjeta").current_balance,
            250_000,
        )

    def test_reporte_imprevistos_solo_considera_gastos_reales(self) -> None:
        """Ignora ingreso legacy marcado como imprevisto en el reporte."""
        self._crear_escenario_junio()
        budget = self.repository.load(2026, 6)
        budget.transactions.append(
            Transaction(
                transaction_type=INCOME,
                category="Sueldo",
                amount=10_000,
                tx_date="2026-06-06",
                description="Ingreso legacy imprevisto",
                account_id="cuenta-origen",
                is_unexpected=True,
            ),
        )
        self.repository.save(budget)

        report = ReportService(
            data_dir=self.data_dir,
            reports_dir=self.root / "reportes",
            key_path=self.root / "config" / "reportes.key",
            repository=self.repository,
        ).generar_reporte_mensual(6, 2026)

        self.assertIn("Movimientos imprevistos: 1", report.contenido)
        self.assertIn("Consulta salud", report.contenido)
        self.assertNotIn("Ingreso legacy imprevisto |", report.contenido)
        self.assertIn("TRANSFERENCIAS INTERNAS", report.contenido)
        self.assertIn("PAGOS DE DEUDA", report.contenido)

    def test_conciliacion_y_cuentas_coinciden_en_multimes(self) -> None:
        """Conciliacion usa el mismo saldo registrado acumulado de Cuentas."""
        self._crear_escenario_junio()
        self._guardar_presupuesto(2026, 7)
        MovementService(
            data_dir=self.data_dir,
            year=2026,
            month=7,
            repository=self.repository,
        ).crear_movimiento(
            "01-07-2026",
            "gasto",
            "Comida",
            "cuenta-origen",
            40_000,
            "Compra julio",
        )
        MovementService(
            data_dir=self.data_dir,
            year=2026,
            month=7,
            repository=self.repository,
        ).crear_transferencia(
            "02-07-2026",
            "cuenta-destino",
            "cuenta-origen",
            20_000,
            "Devolucion ahorro",
        )
        account_service = AccountService(
            data_dir=self.data_dir,
            year=2026,
            month=7,
            repository=self.repository,
        )
        reconciliation_service = ReconciliationService(
            data_dir=self.data_dir,
            year=2026,
            month=7,
            account_service=account_service,
            repository=self.repository,
        )

        cuenta = account_service.obtener_cuenta_por_id("cuenta-origen")
        conciliacion = reconciliation_service.obtener_conciliacion_por_cuenta(
            "cuenta-origen",
        )
        cuadrada = reconciliation_service.crear_conciliacion(
            {
                "cuenta_id": "cuenta-origen",
                "saldo_real": 720_000,
                "fecha_conciliacion": "31-07-2026",
            },
        )

        self.assertEqual(cuenta.registered_balance, 720_000)
        self.assertEqual(conciliacion.saldo_registrado, cuenta.registered_balance)
        self.assertEqual(cuadrada.saldo_registrado, cuenta.registered_balance)
        self.assertEqual(cuadrada.diferencia, 0)

    def test_debt_payment_totals_solo_compatibilidad_legacy(self) -> None:
        """Solo gastos antiguos con debt_id entran al total legacy."""
        budget = MonthlyBudget(
            year=2026,
            month=8,
            categories=[
                CategoryBudget("Tarjeta antigua", EXPENSE, 0, True),
            ],
            transactions=[
                Transaction(
                    transaction_type=EXPENSE,
                    category="Tarjeta antigua",
                    amount=25_000,
                    tx_date="2026-08-01",
                    description="Pago legacy",
                    account_id="cuenta-origen",
                    debt_id="deuda-tarjeta",
                ),
                Transaction(
                    transaction_type=DEBT_PAYMENT,
                    category="",
                    amount=99_000,
                    tx_date="2026-08-02",
                    description="Pago nuevo",
                    account_id="cuenta-origen",
                    debt_id="deuda-tarjeta",
                ),
            ],
        )

        self.assertEqual(
            self.repository.debt_payment_totals(budget),
            {"deuda-tarjeta": 25_000},
        )

    def _guardar_presupuesto(self, year: int, month: int) -> None:
        """Guarda categorias base para el mes indicado."""
        self.repository.save(
            MonthlyBudget(
                year=year,
                month=month,
                categories=[
                    CategoryBudget(
                        "Sueldo",
                        INCOME,
                        0,
                        True,
                        start_date=f"{year:04d}-{month:02d}-01",
                    ),
                    CategoryBudget(
                        "Comida",
                        EXPENSE,
                        100_000,
                        False,
                        start_date=f"{year:04d}-{month:02d}-01",
                    ),
                    CategoryBudget(
                        "Salud",
                        EXPENSE,
                        50_000,
                        False,
                        start_date=f"{year:04d}-{month:02d}-01",
                    ),
                ],
            ),
        )

    def _crear_escenario_junio(self) -> None:
        """Crea el escenario oficial de coherencia para junio."""
        self.movement_service.crear_movimiento(
            "01-06-2026",
            "ingreso",
            "Sueldo",
            "cuenta-origen",
            1_000_000,
            "Remuneracion",
        )
        self.movement_service.crear_movimiento(
            "02-06-2026",
            "gasto",
            "Comida",
            "cuenta-origen",
            80_000,
            "Supermercado",
        )
        self.movement_service.crear_movimiento(
            "03-06-2026",
            "gasto",
            "Salud",
            "cuenta-origen",
            30_000,
            "Consulta salud",
            imprevisto=True,
        )
        self.movement_service.crear_transferencia(
            "04-06-2026",
            "cuenta-origen",
            "cuenta-destino",
            200_000,
            "Traspaso ahorro",
        )
        self.movement_service.crear_pago_deuda(
            "05-06-2026",
            "cuenta-origen",
            "deuda-tarjeta",
            50_000,
            "Pago tarjeta",
        )


if __name__ == "__main__":
    unittest.main()
