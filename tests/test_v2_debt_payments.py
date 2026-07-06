"""Pruebas de pagos correctos de deudas en Avalancha V2."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from PySide6.QtWidgets import QApplication

from avalancha.models import (
    CategoryBudget,
    CuentaFinanciera,
    Debt,
    EXPENSE,
    INCOME,
    MonthlyBudget,
)
from avalancha.storage import BudgetRepository
from core.models.movimiento import Movimiento
from services.account_service import AccountService
from services.budget_service import BudgetService
from services.dashboard_visual_service import DashboardVisualService
from services.debt_service import DebtService
from services.financial_alert_service import FinancialAlertService
from services.movement_service import MovementService
from services.reconciliation_service import ReconciliationService
from services.report_service import ReportService
from ui_pyside6.pages.movement_dialog import MovementDialog


class DebtPayoffTest(unittest.TestCase):
    """Valida que pagar deuda no duplique gasto ni presupuesto."""

    def setUp(self) -> None:
        """Crea un perfil temporal con cuentas, deuda y presupuesto."""
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
                    CategoryBudget(
                        "Comida",
                        EXPENSE,
                        100_000,
                        False,
                        start_date="2026-06-01",
                    ),
                ],
            ),
        )
        self.repository.save_accounts(
            [
                CuentaFinanciera(
                    account_id="cuenta-origen",
                    name="Cuenta corriente",
                    account_type="cuenta_corriente",
                    initial_balance=200_000,
                    real_balance=150_000,
                ),
                CuentaFinanciera(
                    account_id="cuenta-otra",
                    name="Cuenta ahorro",
                    account_type="ahorro",
                    initial_balance=50_000,
                    real_balance=50_000,
                ),
            ],
        )
        self.repository.save_debts(
            [
                Debt(
                    debt_id="deuda-tarjeta",
                    name="Tarjeta de credito",
                    category="tarjeta_credito",
                    current_balance=120_000,
                    previous_month_balance=150_000,
                    current_monthly_payment=30_000,
                    minimum_payment=10_000,
                    active=True,
                ),
                Debt(
                    debt_id="deuda-inactiva",
                    name="Deuda inactiva",
                    category="otra",
                    current_balance=20_000,
                    previous_month_balance=20_000,
                    current_monthly_payment=5_000,
                    minimum_payment=1_000,
                    active=False,
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

    def test_crear_pago_deuda_valido_reduce_deuda(self) -> None:
        """Crea pago de deuda y reduce el saldo de la deuda."""
        movimiento = self.movement_service.crear_pago_deuda(
            fecha="10-06-2026",
            cuenta_origen_id="cuenta-origen",
            deuda_id="deuda-tarjeta",
            monto=30_000,
            descripcion="Pago tarjeta",
        )
        debt = DebtService(
            data_dir=self.data_dir,
            repository=self.repository,
        ).obtener_deuda_por_id("deuda-tarjeta")

        self.assertEqual(movimiento.tipo, "pago_deuda")
        self.assertEqual(movimiento.categoria, "")
        self.assertEqual(movimiento.deuda_id, "deuda-tarjeta")
        self.assertEqual(movimiento.clase, "Pago de deuda")
        self.assertFalse(movimiento.imprevisto)
        self.assertEqual(debt.current_balance, 90_000)
        self.assertEqual(
            self.repository.load(2026, 6).transactions[0].transaction_type,
            "pago_deuda",
        )

    def test_validaciones_pago_deuda(self) -> None:
        """Rechaza pagos incompletos, invalidos o inseguros."""
        cases = [
            {
                "kwargs": {
                    "fecha": "10-06-2026",
                    "cuenta_origen_id": "cuenta-origen",
                    "deuda_id": "deuda-tarjeta",
                    "monto": 0,
                },
                "message": "mayor que cero",
            },
            {
                "kwargs": {
                    "fecha": "10-06-2026",
                    "cuenta_origen_id": "",
                    "deuda_id": "deuda-tarjeta",
                    "monto": 10_000,
                },
                "message": "cuenta",
            },
            {
                "kwargs": {
                    "fecha": "10-06-2026",
                    "cuenta_origen_id": "cuenta-origen",
                    "deuda_id": "",
                    "monto": 10_000,
                },
                "message": "deuda",
            },
            {
                "kwargs": {
                    "fecha": "10-06-2026",
                    "cuenta_origen_id": "cuenta-inexistente",
                    "deuda_id": "deuda-tarjeta",
                    "monto": 10_000,
                },
                "message": "cuenta",
            },
            {
                "kwargs": {
                    "fecha": "10-06-2026",
                    "cuenta_origen_id": "cuenta-origen",
                    "deuda_id": "deuda-inexistente",
                    "monto": 10_000,
                },
                "message": "deuda",
            },
            {
                "kwargs": {
                    "fecha": "10-06-2026",
                    "cuenta_origen_id": "cuenta-origen",
                    "deuda_id": "deuda-inactiva",
                    "monto": 10_000,
                },
                "message": "deuda",
            },
            {
                "kwargs": {
                    "fecha": "10-06-2026",
                    "cuenta_origen_id": "cuenta-origen",
                    "deuda_id": "deuda-tarjeta",
                    "monto": 200_000,
                },
                "message": "superar",
            },
        ]
        for case in cases:
            with self.subTest(case=case["message"]):
                with self.assertRaisesRegex(ValueError, case["message"]):
                    self.movement_service.crear_pago_deuda(**case["kwargs"])

        with self.assertRaisesRegex(ValueError, "imprevisto"):
            self.movement_service.crear_pago_deuda(
                "10-06-2026",
                "cuenta-origen",
                "deuda-tarjeta",
                10_000,
                imprevisto=True,
            )
        with self.assertRaisesRegex(ValueError, "imprevisto"):
            self.movement_service.crear_movimiento(
                "10-06-2026",
                "pago_deuda",
                "",
                "cuenta-origen",
                10_000,
                imprevisto=True,
                deuda_id="deuda-tarjeta",
            )

    def test_pago_deuda_no_deja_operacion_parcial_si_falla(self) -> None:
        """No persiste movimiento ni saldo si el pago supera el saldo."""
        with self.assertRaisesRegex(ValueError, "superar"):
            self.movement_service.crear_pago_deuda(
                "10-06-2026",
                "cuenta-origen",
                "deuda-tarjeta",
                999_999,
            )

        self.assertEqual(self.repository.load(2026, 6).transactions, [])
        self.assertEqual(
            DebtService(
                data_dir=self.data_dir,
                repository=self.repository,
            ).obtener_deuda_por_id("deuda-tarjeta").current_balance,
            120_000,
        )

    def test_editar_y_eliminar_pago_ajusta_deuda(self) -> None:
        """Editar o eliminar un pago actualiza el saldo de deuda."""
        pago = self.movement_service.crear_pago_deuda(
            "10-06-2026",
            "cuenta-origen",
            "deuda-tarjeta",
            30_000,
        )
        editado = self.movement_service.editar_movimiento(
            pago.id,
            "11-06-2026",
            "pago_deuda",
            "",
            "cuenta-origen",
            50_000,
            deuda_id="deuda-tarjeta",
        )
        debt_service = DebtService(
            data_dir=self.data_dir,
            repository=self.repository,
        )
        self.assertEqual(editado.monto, 50_000)
        self.assertEqual(
            debt_service.obtener_deuda_por_id("deuda-tarjeta").current_balance,
            70_000,
        )

        self.movement_service.eliminar_movimiento(pago.id)

        self.assertEqual(
            debt_service.obtener_deuda_por_id("deuda-tarjeta").current_balance,
            120_000,
        )

    def test_conciliacion_descuenta_cuenta_origen(self) -> None:
        """El saldo registrado baja en la cuenta que paga la deuda."""
        self.movement_service.crear_pago_deuda(
            "10-06-2026",
            "cuenta-origen",
            "deuda-tarjeta",
            30_000,
        )
        service = ReconciliationService(
            data_dir=self.data_dir,
            year=2026,
            month=6,
            repository=self.repository,
            movement_service=self.movement_service,
        )
        origen = service.obtener_conciliacion_por_cuenta("cuenta-origen")
        otra = service.obtener_conciliacion_por_cuenta("cuenta-otra")

        self.assertEqual(origen.saldo_registrado, 170_000)
        self.assertEqual(otra.saldo_registrado, 50_000)

    def test_cuentas_recalculan_saldo_tras_pago_deuda(self) -> None:
        """AccountService expone saldo registrado actualizado por pago."""
        self.movement_service.crear_pago_deuda(
            "10-06-2026",
            "cuenta-origen",
            "deuda-tarjeta",
            30_000,
        )
        service = AccountService(
            data_dir=self.data_dir,
            year=2026,
            month=6,
            repository=self.repository,
        )

        origen = service.obtener_cuenta_por_id("cuenta-origen")
        otra = service.obtener_cuenta_por_id("cuenta-otra")

        self.assertEqual(origen.registered_balance, 170_000)
        self.assertEqual(otra.registered_balance, 50_000)

    def test_cuentas_muestran_saldo_actual_no_solo_periodo(self) -> None:
        """Cambiar periodo no altera el saldo actual acumulado de cuenta."""
        self.movement_service.crear_pago_deuda(
            "10-06-2026",
            "cuenta-origen",
            "deuda-tarjeta",
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
        ).crear_movimiento(
            "01-07-2026",
            "gasto",
            "Comida",
            "cuenta-origen",
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
            junio.obtener_cuenta_por_id("cuenta-origen").registered_balance,
            160_000,
        )
        self.assertEqual(
            julio.obtener_cuenta_por_id("cuenta-origen").registered_balance,
            160_000,
        )

    def test_dashboard_presupuesto_y_alertas_ignoran_pago_deuda(self) -> None:
        """No aumenta gasto, presupuesto, clase ni imprevisto."""
        self.movement_service.crear_movimiento(
            "01-06-2026",
            "ingreso",
            "Sueldo",
            "cuenta-origen",
            200_000,
        )
        self.movement_service.crear_movimiento(
            "02-06-2026",
            "gasto",
            "Comida",
            "cuenta-origen",
            50_000,
        )
        self.movement_service.crear_pago_deuda(
            "03-06-2026",
            "cuenta-origen",
            "deuda-tarjeta",
            30_000,
        )

        dashboard = DashboardVisualService(
            data_dir=self.data_dir,
            repository=self.repository,
        ).obtener_dashboard(2026, 6)
        cards = {item.titulo: item.monto for item in dashboard.tarjetas}
        categories = {
            item.etiqueta: item.monto for item in dashboard.gastos_por_categoria
        }
        classes = {item.etiqueta: item.monto for item in dashboard.gastos_por_clase}
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
                    "flujo_libre": 150_000,
                    "gastos_reales": 50_000,
                    "ingresos_reales": 200_000,
                    "deuda_actual": 90_000,
                    "gastos_imprevistos": 0,
                },
            )(),
            categorias=[],
        )

        self.assertEqual(cards["Ingresos del mes"], 200_000)
        self.assertEqual(cards["Gastos del mes"], 50_000)
        self.assertEqual(cards["Flujo libre"], 150_000)
        self.assertEqual(cards["Deuda total"], 90_000)
        self.assertEqual(cards["Imprevistos"], 0)
        self.assertEqual(categories, {"Comida": 50_000})
        self.assertEqual(classes["Normal"], 50_000)
        self.assertEqual(classes["Imprevisto"], 0)
        self.assertEqual(ejecucion.monto_gastado, 50_000)
        self.assertEqual(self.repository.debt_payment_totals(), {})
        self.assertEqual(alertas[0].nivel, "info")

    def test_reporte_separa_pagos_de_deuda(self) -> None:
        """Reporta pagos de deuda sin alterar gastos reales."""
        self.movement_service.crear_movimiento(
            "01-06-2026",
            "ingreso",
            "Sueldo",
            "cuenta-origen",
            200_000,
        )
        self.movement_service.crear_pago_deuda(
            "03-06-2026",
            "cuenta-origen",
            "deuda-tarjeta",
            30_000,
            "Pago mensual tarjeta",
        )

        report = ReportService(
            data_dir=self.data_dir,
            reports_dir=self.root / "reportes",
            key_path=self.root / "config" / "reporte.key",
            repository=self.repository,
        ).generar_reporte_mensual(6, 2026)

        self.assertIn("Gastos reales: $ 0", report.contenido)
        self.assertIn("PAGOS DE DEUDA", report.contenido)
        self.assertIn("Cuenta corriente -> Tarjeta de credito", report.contenido)
        self.assertIn("Pago mensual tarjeta", report.contenido)
        self.assertIn("Sin transferencias internas.", report.contenido)

    def test_aislamiento_personal_demo_por_data_dir(self) -> None:
        """Un pago en un perfil no afecta otro directorio de datos."""
        other_repository = BudgetRepository(self.root / "demo" / "data")
        other_repository.save(
            MonthlyBudget(
                year=2026,
                month=6,
                categories=[
                    CategoryBudget("Sueldo", INCOME, 0, True),
                    CategoryBudget("Comida", EXPENSE, 100_000, False),
                ],
            ),
        )
        other_repository.save_accounts(
            [
                CuentaFinanciera(
                    account_id="cuenta-origen",
                    name="Cuenta demo",
                    account_type="cuenta_corriente",
                    initial_balance=100_000,
                ),
            ],
        )
        other_repository.save_debts(
            [
                Debt(
                    debt_id="deuda-tarjeta",
                    name="Tarjeta demo",
                    category="tarjeta_credito",
                    current_balance=300_000,
                    previous_month_balance=300_000,
                    current_monthly_payment=30_000,
                    minimum_payment=10_000,
                ),
            ],
        )

        self.movement_service.crear_pago_deuda(
            "10-06-2026",
            "cuenta-origen",
            "deuda-tarjeta",
            30_000,
        )

        self.assertEqual(
            other_repository.load_debts()[0].current_balance,
            300_000,
        )
        self.assertEqual(other_repository.load(2026, 6).transactions, [])

    def test_ui_expone_pago_deuda_sin_storage_directo(self) -> None:
        """Verifica formulario de pago sin acceso directo a storage."""
        dialog = Path("ui_pyside6/pages/movement_dialog.py").read_text(
            encoding="utf-8",
        )
        page = Path("ui_pyside6/pages/movement_page.py").read_text(
            encoding="utf-8",
        )

        self.assertIn("Pago de deuda", dialog)
        self.assertIn("debt_input", dialog)
        self.assertIn("category_label.setVisible", dialog)
        self.assertIn("destination_account_label.setVisible", dialog)
        self.assertIn("Pago deuda:", page)
        self.assertNotIn("BudgetRepository", dialog)
        self.assertNotIn("avalancha.storage", dialog)
        self.assertNotIn("BudgetRepository", page)
        self.assertNotIn("avalancha.storage", page)

    def test_helpers_formato_monto_clp(self) -> None:
        """Formatea y parsea montos con separador chileno."""
        self.assertEqual(MovementDialog._format_clp_amount("5000"), "5.000")
        self.assertEqual(MovementDialog._format_clp_amount("50000"), "50.000")
        self.assertEqual(
            MovementDialog._format_clp_amount("500000"),
            "500.000",
        )
        self.assertEqual(
            MovementDialog._format_clp_amount("5000000"),
            "5.000.000",
        )
        self.assertEqual(
            MovementDialog._format_clp_amount("50000000"),
            "50.000.000",
        )
        self.assertEqual(
            MovementDialog._format_clp_amount("5.000000"),
            "5.000.000",
        )
        self.assertEqual(
            MovementDialog._format_clp_amount("50.00000"),
            "5.000.000",
        )
        self.assertEqual(
            MovementDialog._format_clp_amount("1240000"),
            "1.240.000",
        )
        self.assertEqual(MovementDialog._parse_clp_amount("50.000"), 50_000)
        self.assertEqual(
            MovementDialog._parse_clp_amount("5.000.000"),
            5_000_000,
        )
        self.assertEqual(
            MovementDialog._parse_clp_amount("1.240.000"),
            1_240_000,
        )
        with self.assertRaisesRegex(ValueError, "monto"):
            MovementDialog._parse_clp_amount("")
        for invalid in ("abc", "$50000", "50,000", "50.000,5", "12.34"):
            with self.subTest(invalid=invalid):
                with self.assertRaisesRegex(ValueError, "monto"):
                    MovementDialog._parse_clp_amount(invalid)

    def test_dialogo_formatea_monto_progresivo_por_tipo(self) -> None:
        """Al escribir 5000000 en cada tipo termina en 5.000.000."""
        self._ensure_qapplication()
        for tipo in ("ingreso", "gasto", "transferencia", "pago_deuda"):
            with self.subTest(tipo=tipo):
                dialog = MovementDialog(self.movement_service)
                type_index = dialog.type_input.findData(tipo)
                dialog.type_input.setCurrentIndex(type_index)
                dialog.amount_input.clear()

                for char in "5000000":
                    dialog.amount_input.insert(char)

                self.assertEqual(dialog.amount_input.text(), "5.000.000")
                self.assertEqual(dialog.obtener_datos()["monto"], 5_000_000)
                self.assertNotEqual(dialog.amount_input.text(), "5.000000")

                dialog.close()

    def test_dialogo_formatea_monto_existente_y_entrega_entero(self) -> None:
        """El dialogo abre con puntos y entrega entero limpio al guardar."""
        self._ensure_qapplication()
        for tipo in ("ingreso", "gasto", "transferencia", "pago_deuda"):
            with self.subTest(tipo=tipo):
                movement = Movimiento(
                    id=f"mov-{tipo}",
                    fecha=self.movement_service._normalizar_fecha("10-06-2026"),
                    tipo=tipo,
                    categoria=(
                        ""
                        if tipo in {"transferencia", "pago_deuda"}
                        else "Comida"
                    ),
                    descripcion="Movimiento existente",
                    monto=50_000,
                    cuenta_id="cuenta-origen",
                    medio_pago="Transferencia",
                    cuenta_destino_id=(
                        "cuenta-otra" if tipo == "transferencia" else None
                    ),
                    deuda_id=(
                        "deuda-tarjeta" if tipo == "pago_deuda" else None
                    ),
                )
                dialog = MovementDialog(self.movement_service, movement)

                self.assertEqual(dialog.amount_input.text(), "50.000")
                dialog.amount_input.setText("1240000")
                self.assertEqual(dialog.amount_input.text(), "1.240.000")
                self.assertEqual(dialog.obtener_datos()["monto"], 1_240_000)

                dialog.close()

    @staticmethod
    def _ensure_qapplication() -> QApplication:
        """Crea QApplication para pruebas livianas de dialogo."""
        app = QApplication.instance()
        if app is None:
            app = QApplication([])
        return app


if __name__ == "__main__":
    unittest.main()
