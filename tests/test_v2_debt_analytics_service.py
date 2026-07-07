"""Pruebas del analisis temporal de deudas V2."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from avalancha.models import (
    CuentaFinanciera,
    Debt,
    DebtPayment,
    DebtSnapshot,
)
from avalancha.storage import BudgetRepository
from services.debt_analytics_service import DebtAnalyticsService
from services.debt_service import DebtService


class DebtAnalyticsServiceTest(unittest.TestCase):
    """Valida calculos temporales basados en trazas reales."""

    def setUp(self) -> None:
        """Crea repositorio temporal para pruebas de analitica."""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.data_dir = Path(self.temp_dir.name) / "data"
        self.repository = BudgetRepository(self.data_dir)
        self.repository.save_accounts(
            [
                CuentaFinanciera(
                    account_id="cuenta-uno",
                    name="Cuenta uno",
                    account_type="cuenta_corriente",
                ),
                CuentaFinanciera(
                    account_id="cuenta-dos",
                    name="Cuenta dos",
                    account_type="cuenta_corriente",
                ),
            ]
        )
        self.repository.save_debts(
            [
                Debt(
                    debt_id="deuda-uno",
                    name="Tarjeta uno",
                    category="tarjeta_credito",
                    current_balance=800_000,
                    previous_month_balance=1_000_000,
                    current_monthly_payment=100_000,
                    minimum_payment=50_000,
                ),
                Debt(
                    debt_id="deuda-dos",
                    name="Credito dos",
                    category="credito_consumo",
                    current_balance=400_000,
                    previous_month_balance=500_000,
                    current_monthly_payment=100_000,
                    minimum_payment=50_000,
                ),
            ]
        )
        self.debt_service = DebtService(
            data_dir=self.data_dir,
            repository=self.repository,
        )
        self.service = DebtAnalyticsService(
            data_dir=self.data_dir,
            repository=self.repository,
            debt_service=self.debt_service,
        )

    def tearDown(self) -> None:
        """Elimina archivos temporales de prueba."""
        self.temp_dir.cleanup()

    def test_obtener_pagos_mensuales_agrupa_totales_y_cantidad(self) -> None:
        """Agrupa pagos reales por mes y permite filtrar por anio."""
        self.repository.save_debt_payments(
            [
                self._payment("deuda-uno", "2026-06-05", 100_000),
                self._payment("deuda-dos", "2026-06-20", 50_000),
                self._payment("deuda-uno", "2026-07-01", 75_000),
            ]
        )

        monthly = self.service.obtener_pagos_mensuales()
        filtered = self.service.obtener_pagos_mensuales(year=2026)

        self.assertEqual(len(monthly), 2)
        self.assertEqual(len(filtered), 2)
        self.assertEqual(monthly[0].year, 2026)
        self.assertEqual(monthly[0].month, 6)
        self.assertEqual(monthly[0].total_pagado, 150_000)
        self.assertEqual(monthly[0].cantidad_pagos, 2)
        self.assertEqual(
            monthly[0].desglose_por_deuda,
            {"deuda-dos": 50_000, "deuda-uno": 100_000},
        )
        self.assertEqual(monthly[1].total_pagado, 75_000)

    def test_obtener_evolucion_deuda_filtra_y_ordena_snapshots(self) -> None:
        """Devuelve evolucion por deuda ordenada por fecha."""
        self.repository.save_debt_snapshots(
            [
                self._snapshot("deuda-uno", "2026-07-05", 800_000),
                self._snapshot("deuda-uno", "2026-06-05", 900_000),
                self._snapshot("deuda-dos", "2026-06-05", 450_000),
            ]
        )

        points = self.service.obtener_evolucion_deuda("deuda-uno")

        self.assertEqual([point.fecha.isoformat() for point in points], [
            "2026-06-05",
            "2026-07-05",
        ])
        self.assertEqual([point.saldo for point in points], [900_000, 800_000])
        self.assertEqual(points[0].deuda, "Tarjeta uno")
        self.assertEqual(points[0].origen, "pago")

    def test_obtener_deuda_total_en_tiempo_reconstruye_varias_deudas(
        self,
    ) -> None:
        """Reconstruye deuda total cuando existen snapshots suficientes."""
        self.repository.save_debt_snapshots(
            [
                self._snapshot("deuda-uno", "2026-06-01", 1_000_000),
                self._snapshot("deuda-dos", "2026-06-01", 500_000),
                self._snapshot("deuda-uno", "2026-07-01", 800_000),
                self._snapshot("deuda-dos", "2026-07-01", 400_000),
            ]
        )

        points = self.service.obtener_deuda_total_en_tiempo()

        self.assertEqual([point.fecha.isoformat() for point in points], [
            "2026-06-01",
            "2026-07-01",
        ])
        self.assertEqual([point.saldo_total for point in points], [
            1_500_000,
            1_200_000,
        ])
        self.assertEqual(points[0].cantidad_deudas, 2)

    def test_deuda_total_sin_datos_suficientes_devuelve_lista_vacia(
        self,
    ) -> None:
        """No inventa una curva con un unico snapshot."""
        self.repository.save_debt_snapshots(
            [self._snapshot("deuda-uno", "2026-06-01", 1_000_000)]
        )

        self.assertEqual(self.service.obtener_deuda_total_en_tiempo(), [])

    def test_resumen_temporal_detecta_tendencia_bajando(self) -> None:
        """Clasifica deuda a la baja frente al mes anterior comparable."""
        self.repository.save_debt_payments(
            [
                self._payment("deuda-uno", "2026-07-05", 200_000),
                self._payment("deuda-dos", "2026-07-05", 100_000),
            ]
        )
        self.repository.save_debt_snapshots(
            [
                self._snapshot("deuda-uno", "2026-06-30", 1_000_000),
                self._snapshot("deuda-dos", "2026-06-30", 500_000),
                self._snapshot("deuda-uno", "2026-07-05", 800_000),
                self._snapshot("deuda-dos", "2026-07-05", 400_000),
            ]
        )

        summary = self.service.obtener_resumen_temporal_deudas(2026, 7)

        self.assertEqual(summary.deuda_total_actual, 1_200_000)
        self.assertEqual(summary.pagado_mes_actual, 300_000)
        self.assertEqual(summary.variacion_deuda_mes, 300_000)
        self.assertEqual(summary.tendencia, "bajando")

    def test_resumen_temporal_detecta_subiendo_y_sin_datos(self) -> None:
        """Clasifica alza o ausencia de comparacion real."""
        self.repository.save_debt_snapshots(
            [
                self._snapshot("deuda-uno", "2026-06-30", 800_000),
                self._snapshot("deuda-dos", "2026-06-30", 400_000),
                self._snapshot("deuda-uno", "2026-07-05", 1_000_000),
                self._snapshot("deuda-dos", "2026-07-05", 500_000),
            ]
        )

        subida = self.service.obtener_resumen_temporal_deudas(2026, 7)

        self.repository.save_debt_snapshots([])
        sin_datos = self.service.obtener_resumen_temporal_deudas(2026, 7)

        self.assertEqual(subida.variacion_deuda_mes, -300_000)
        self.assertEqual(subida.tendencia, "subiendo")
        self.assertEqual(sin_datos.variacion_deuda_mes, 0)
        self.assertEqual(sin_datos.tendencia, "sin_datos")

    def test_obtener_pagos_recientes_respeta_orden_y_limite(self) -> None:
        """Devuelve pagos recientes con deuda, cuenta, monto y saldos."""
        self.repository.save_debt_payments(
            [
                self._payment("deuda-uno", "2026-06-01", 50_000),
                self._payment(
                    "deuda-dos",
                    "2026-07-02",
                    70_000,
                    account_id="cuenta-dos",
                ),
                self._payment("deuda-uno", "2026-07-03", 80_000),
            ]
        )

        recent = self.service.obtener_pagos_recientes(limit=2)

        self.assertEqual(len(recent), 2)
        self.assertEqual([payment.fecha.isoformat() for payment in recent], [
            "2026-07-03",
            "2026-07-02",
        ])
        self.assertEqual(recent[0].deuda, "Tarjeta uno")
        self.assertEqual(recent[1].cuenta, "Cuenta dos")
        self.assertEqual(recent[0].monto, 80_000)
        self.assertEqual(recent[0].saldo_antes, 1_000_000)
        self.assertEqual(recent[0].saldo_despues, 920_000)

    def test_analitica_personal_y_demo_quedan_aisladas(self) -> None:
        """Cada instancia analiza solo su data_dir de perfil."""
        with tempfile.TemporaryDirectory() as root:
            personal = self._crear_servicio_aislado(
                Path(root) / "personal" / "data",
                "personal",
                10_000,
            )
            demo = self._crear_servicio_aislado(
                Path(root) / "demo" / "data",
                "demo",
                90_000,
            )

            personal_total = personal.obtener_pagos_mensuales()[0].total_pagado
            demo_total = demo.obtener_pagos_mensuales()[0].total_pagado

            self.assertEqual(personal_total, 10_000)
            self.assertEqual(demo_total, 90_000)
            self.assertNotEqual(personal_total, demo_total)

    @staticmethod
    def _payment(
        debt_id: str,
        tx_date: str,
        amount: int,
        account_id: str = "cuenta-uno",
    ) -> DebtPayment:
        """Crea pago de deuda ficticio para pruebas."""
        return DebtPayment(
            payment_id=f"pago-{debt_id}-{tx_date}-{amount}",
            debt_id=debt_id,
            account_id=account_id,
            tx_date=tx_date,
            amount=amount,
            balance_before=1_000_000,
            balance_after=1_000_000 - amount,
            note="Pago de prueba",
        )

    @staticmethod
    def _snapshot(
        debt_id: str,
        tx_date: str,
        balance: int,
    ) -> DebtSnapshot:
        """Crea snapshot de deuda ficticio para pruebas."""
        return DebtSnapshot(
            snapshot_id=f"snapshot-{debt_id}-{tx_date}-{balance}",
            debt_id=debt_id,
            tx_date=tx_date,
            balance=balance,
            previous_balance=balance + 10_000,
            source="pago",
        )

    @staticmethod
    def _crear_servicio_aislado(
        data_dir: Path,
        suffix: str,
        amount: int,
    ) -> DebtAnalyticsService:
        """Crea servicio temporal aislado por perfil."""
        repository = BudgetRepository(data_dir)
        repository.save_debts(
            [
                Debt(
                    debt_id=f"deuda-{suffix}",
                    name=f"Deuda {suffix}",
                    category="otra",
                    current_balance=100_000,
                    current_monthly_payment=10_000,
                    minimum_payment=5_000,
                )
            ]
        )
        repository.save_accounts(
            [
                CuentaFinanciera(
                    account_id=f"cuenta-{suffix}",
                    name=f"Cuenta {suffix}",
                    account_type="cuenta_corriente",
                )
            ]
        )
        repository.save_debt_payments(
            [
                DebtPayment(
                    debt_id=f"deuda-{suffix}",
                    account_id=f"cuenta-{suffix}",
                    tx_date="2026-06-05",
                    amount=amount,
                    balance_before=100_000,
                    balance_after=100_000 - amount,
                )
            ]
        )
        return DebtAnalyticsService(data_dir=data_dir, repository=repository)


if __name__ == "__main__":
    unittest.main()
