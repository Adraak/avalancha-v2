"""Pruebas de trazabilidad formal de deuda en Avalancha V2."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from avalancha.models import (
    CategoryBudget,
    CuentaFinanciera,
    Debt,
    EXPENSE,
    INCOME,
    MonthlyBudget,
)
from avalancha.storage import BudgetRepository
from services.debt_service import DebtService
from services.movement_service import MovementService


class DebtTraceabilityTest(unittest.TestCase):
    """Valida pagos formales, snapshots y auditoria de saldos."""

    def setUp(self) -> None:
        """Crea un perfil temporal con cuenta, deuda y presupuesto."""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.repository = BudgetRepository(self.root / "data")
        self.repository.save(
            MonthlyBudget(
                year=2026,
                month=6,
                categories=[
                    CategoryBudget("Sueldo", INCOME, 0, True),
                    CategoryBudget("Comida", EXPENSE, 100_000, False),
                ],
            )
        )
        self.repository.save_accounts(
            [
                CuentaFinanciera(
                    account_id="cuenta-origen",
                    name="Cuenta corriente",
                    account_type="cuenta_corriente",
                    initial_balance=200_000,
                )
            ]
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
                    monthly_interest_rate=2,
                ),
                Debt(
                    debt_id="deuda-consumo",
                    name="Credito consumo",
                    category="credito_consumo",
                    current_balance=500_000,
                    previous_month_balance=520_000,
                    current_monthly_payment=50_000,
                    minimum_payment=20_000,
                ),
            ]
        )
        self.movement_service = MovementService(
            data_dir=self.repository.data_dir,
            year=2026,
            month=6,
            repository=self.repository,
        )
        self.debt_service = DebtService(
            data_dir=self.repository.data_dir,
            repository=self.repository,
        )

    def tearDown(self) -> None:
        """Elimina datos temporales de prueba."""
        self.temp_dir.cleanup()

    def test_crear_pago_deuda_persiste_pago_formal_y_snapshot(self) -> None:
        """Un pago guarda saldo anterior, posterior y cuenta origen."""
        movimiento = self.movement_service.crear_pago_deuda(
            "10-06-2026",
            "cuenta-origen",
            "deuda-tarjeta",
            30_000,
            "Pago mensual tarjeta",
        )

        payments = self.repository.load_debt_payments()
        snapshots = self.repository.load_debt_snapshots()

        self.assertEqual(len(payments), 1)
        self.assertEqual(payments[0].movement_id, movimiento.id)
        self.assertEqual(payments[0].debt_id, "deuda-tarjeta")
        self.assertEqual(payments[0].account_id, "cuenta-origen")
        self.assertEqual(payments[0].amount, 30_000)
        self.assertEqual(payments[0].balance_before, 120_000)
        self.assertEqual(payments[0].balance_after, 90_000)
        self.assertEqual(payments[0].estimated_interest, 1_800)
        self.assertEqual(payments[0].note, "Pago mensual tarjeta")
        self.assertEqual(len(snapshots), 1)
        self.assertEqual(snapshots[0].source, "pago")
        self.assertEqual(snapshots[0].previous_balance, 120_000)
        self.assertEqual(snapshots[0].balance, 90_000)

    def test_editar_pago_deuda_actualiza_pago_activo_y_audita_reversa(
        self,
    ) -> None:
        """Editar un pago reemplaza la traza activa y deja auditoria."""
        pago = self.movement_service.crear_pago_deuda(
            "10-06-2026",
            "cuenta-origen",
            "deuda-tarjeta",
            30_000,
        )
        self.movement_service.editar_movimiento(
            pago.id,
            "11-06-2026",
            "pago_deuda",
            "",
            "cuenta-origen",
            50_000,
            "Pago corregido",
            deuda_id="deuda-tarjeta",
        )

        payments = self.debt_service.obtener_pagos_deuda("deuda-tarjeta")
        snapshots = self.debt_service.obtener_snapshots_deuda("deuda-tarjeta")
        debt = self.debt_service.obtener_deuda_por_id("deuda-tarjeta")

        self.assertEqual(debt.current_balance, 70_000)
        self.assertEqual(len(payments), 1)
        self.assertEqual(payments[0].movement_id, pago.id)
        self.assertEqual(payments[0].amount, 50_000)
        self.assertEqual(payments[0].balance_before, 120_000)
        self.assertEqual(payments[0].balance_after, 70_000)
        self.assertEqual(
            [snapshot.source for snapshot in snapshots],
            ["pago", "reversa", "pago"],
        )
        self.assertEqual(snapshots[-1].balance, 70_000)

    def test_eliminar_pago_deuda_remueve_pago_activo_y_conserva_auditoria(
        self,
    ) -> None:
        """Eliminar un pago revierte saldo y deja snapshot de reversa."""
        pago = self.movement_service.crear_pago_deuda(
            "10-06-2026",
            "cuenta-origen",
            "deuda-tarjeta",
            30_000,
        )

        self.movement_service.eliminar_movimiento(pago.id)

        payments = self.debt_service.obtener_pagos_deuda("deuda-tarjeta")
        snapshots = self.debt_service.obtener_snapshots_deuda("deuda-tarjeta")
        debt = self.debt_service.obtener_deuda_por_id("deuda-tarjeta")

        self.assertEqual(payments, [])
        self.assertEqual(debt.current_balance, 120_000)
        self.assertEqual(
            [snapshot.source for snapshot in snapshots],
            ["pago", "reversa"],
        )
        self.assertEqual(snapshots[-1].previous_balance, 90_000)
        self.assertEqual(snapshots[-1].balance, 120_000)

    def test_consultas_deuda_filtran_pagos_y_snapshots(self) -> None:
        """DebtService devuelve trazas de una deuda sin mezclar otras."""
        self.movement_service.crear_pago_deuda(
            "10-06-2026",
            "cuenta-origen",
            "deuda-tarjeta",
            30_000,
        )
        self.movement_service.crear_pago_deuda(
            "12-06-2026",
            "cuenta-origen",
            "deuda-consumo",
            50_000,
        )

        pagos_tarjeta = self.debt_service.obtener_pagos_deuda(
            "deuda-tarjeta"
        )
        snapshots_tarjeta = self.debt_service.obtener_snapshots_deuda(
            "deuda-tarjeta"
        )

        self.assertEqual(len(self.debt_service.obtener_pagos_deuda()), 2)
        self.assertEqual(
            [payment.debt_id for payment in pagos_tarjeta],
            ["deuda-tarjeta"],
        )
        self.assertEqual(
            [snapshot.debt_id for snapshot in snapshots_tarjeta],
            ["deuda-tarjeta"],
        )

    def test_trazabilidad_personal_y_demo_no_se_mezclan(self) -> None:
        """Pagos y snapshots quedan aislados por data_dir de perfil."""
        personal = self._crear_contexto_perfil(
            self.root / "personal" / "data",
            "personal",
            120_000,
        )
        demo = self._crear_contexto_perfil(
            self.root / "demo" / "data",
            "demo",
            300_000,
        )

        personal["movements"].crear_pago_deuda(
            "10-06-2026",
            "cuenta-personal",
            "deuda-personal",
            30_000,
            "Pago personal",
        )
        demo["movements"].crear_pago_deuda(
            "12-06-2026",
            "cuenta-demo",
            "deuda-demo",
            50_000,
            "Pago demo",
        )

        personal_payments = personal["debts"].obtener_pagos_deuda()
        personal_snapshots = personal["debts"].obtener_snapshots_deuda()
        demo_payments = demo["debts"].obtener_pagos_deuda()
        demo_snapshots = demo["debts"].obtener_snapshots_deuda()

        self.assertEqual(
            [payment.debt_id for payment in personal_payments],
            ["deuda-personal"],
        )
        self.assertEqual(
            [snapshot.debt_id for snapshot in personal_snapshots],
            ["deuda-personal"],
        )
        self.assertEqual(
            [payment.debt_id for payment in demo_payments],
            ["deuda-demo"],
        )
        self.assertEqual(
            [snapshot.debt_id for snapshot in demo_snapshots],
            ["deuda-demo"],
        )
        self.assertNotIn(
            "deuda-demo",
            {payment.debt_id for payment in personal_payments},
        )
        self.assertNotIn(
            "deuda-personal",
            {payment.debt_id for payment in demo_payments},
        )
        self.assertTrue(personal["repository"].debt_payments_path.exists())
        self.assertTrue(personal["repository"].debt_snapshots_path.exists())
        self.assertTrue(demo["repository"].debt_payments_path.exists())
        self.assertTrue(demo["repository"].debt_snapshots_path.exists())
        self.assertNotEqual(
            personal["repository"].debt_payments_path,
            demo["repository"].debt_payments_path,
        )
        self.assertNotEqual(
            personal["repository"].debt_snapshots_path,
            demo["repository"].debt_snapshots_path,
        )
        self.assertEqual(
            personal["repository"].debt_payments_path.parent,
            self.root / "personal" / "data",
        )
        self.assertEqual(
            demo["repository"].debt_snapshots_path.parent,
            self.root / "demo" / "data",
        )

    @staticmethod
    def _crear_contexto_perfil(
        data_dir: Path,
        suffix: str,
        balance: int,
    ) -> dict[str, object]:
        """Crea servicios aislados para un perfil temporal."""
        repository = BudgetRepository(data_dir)
        repository.save(
            MonthlyBudget(
                year=2026,
                month=6,
                categories=[
                    CategoryBudget("Sueldo", INCOME, 0, True),
                    CategoryBudget("Comida", EXPENSE, 100_000, False),
                ],
            )
        )
        repository.save_accounts(
            [
                CuentaFinanciera(
                    account_id=f"cuenta-{suffix}",
                    name=f"Cuenta {suffix}",
                    account_type="cuenta_corriente",
                    initial_balance=500_000,
                )
            ]
        )
        repository.save_debts(
            [
                Debt(
                    debt_id=f"deuda-{suffix}",
                    name=f"Deuda {suffix}",
                    category="tarjeta_credito",
                    current_balance=balance,
                    previous_month_balance=balance,
                    current_monthly_payment=30_000,
                    minimum_payment=10_000,
                )
            ]
        )
        movement_service = MovementService(
            data_dir=data_dir,
            year=2026,
            month=6,
            repository=repository,
        )
        debt_service = DebtService(
            data_dir=data_dir,
            repository=repository,
        )
        return {
            "repository": repository,
            "movements": movement_service,
            "debts": debt_service,
        }


if __name__ == "__main__":
    unittest.main()
