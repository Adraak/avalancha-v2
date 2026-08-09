"""Pruebas del servicio de cierre mensual financiero."""

from __future__ import annotations

import tempfile
import unittest
from datetime import date
from pathlib import Path

from avalancha.models import CategoryBudget, EXPENSE, MonthlyBudget
from avalancha.storage import BudgetRepository
from core.models.monthly_closure import (
    MONTHLY_CLOSURE_CLOSED,
    MONTHLY_CLOSURE_OPEN,
    MONTHLY_CLOSURE_PENDING,
)
from services.monthly_closure_service import MonthlyClosureService


class MonthlyClosureServiceTest(unittest.TestCase):
    """Valida estados, checklist, persistencia y aislamiento."""

    def setUp(self) -> None:
        """Crea un perfil temporal de prueba."""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.data_dir = self.root / "personal"
        self.repository = BudgetRepository(self.data_dir)
        self.service = MonthlyClosureService(repository=self.repository)

    def tearDown(self) -> None:
        """Elimina archivos temporales."""
        self.temp_dir.cleanup()

    def test_obtener_o_crear_cierre(self) -> None:
        """Crea cierre mensual con estado inicial correcto."""
        closure = self.service.obtener_o_crear_cierre(2026, 6)
        loaded = self.repository.load_monthly_closures()

        self.assertEqual(closure.year, 2026)
        self.assertEqual(closure.month, 6)
        self.assertIn(
            closure.status,
            {MONTHLY_CLOSURE_OPEN, MONTHLY_CLOSURE_PENDING},
        )
        self.assertEqual(len(loaded), 1)
        self.assertEqual(loaded[0].label, "2026-06")

    def test_checklist_y_cierre(self) -> None:
        """Rechaza cierre incompleto y cierra con checklist completo."""
        with self.assertRaisesRegex(ValueError, "Faltan"):
            self.service.cerrar_mes(2026, 6)

        self.service.marcar_movimientos_revisados(2026, 6)
        self.service.marcar_cuentas_conciliadas(2026, 6)
        self.service.marcar_deudas_revisadas(2026, 6)
        self.service.marcar_presupuestos_revisados(2026, 6)
        self.service.marcar_reporte_generado(2026, 6)
        closure = self.service.cerrar_mes(2026, 6)

        self.assertEqual(closure.status, MONTHLY_CLOSURE_CLOSED)
        self.assertTrue(closure.checklist_completo)
        self.assertEqual(closure.faltantes(), [])
        self.assertTrue(self.service.esta_mes_cerrado(2026, 6))

    def test_reabrir_mes(self) -> None:
        """Reabre un mes cerrado para ajustes controlados."""
        self._marcar_checklist_completo(2026, 6)
        self.service.cerrar_mes(2026, 6)
        reopened = self.service.reabrir_mes(2026, 6)

        self.assertEqual(reopened.status, MONTHLY_CLOSURE_OPEN)
        self.assertIsNone(reopened.closed_at)
        self.assertFalse(self.service.esta_mes_cerrado(2026, 6))

    def test_obtener_meses_pendientes(self) -> None:
        """Detecta meses anteriores no cerrados."""
        self.repository.save(
            MonthlyBudget(
                year=2026,
                month=5,
                categories=[CategoryBudget("Comida", EXPENSE, 50_000)],
            ),
        )
        self.repository.save(
            MonthlyBudget(
                year=2026,
                month=6,
                categories=[CategoryBudget("Comida", EXPENSE, 50_000)],
            ),
        )
        self._marcar_checklist_completo(2026, 5)
        self.service.cerrar_mes(2026, 5)

        pending = self.service.obtener_meses_pendientes(
            reference_date=date(2026, 7, 1),
        )

        self.assertEqual([item.label for item in pending], ["2026-06"])
        self.assertEqual(pending[0].status, MONTHLY_CLOSURE_PENDING)

    def test_aislamiento_por_data_dir(self) -> None:
        """Mantiene cierres separados por perfil."""
        demo_dir = self.root / "demo"
        demo_repository = BudgetRepository(demo_dir)
        demo_service = MonthlyClosureService(repository=demo_repository)

        self._marcar_checklist_completo(2026, 6)
        self.service.cerrar_mes(2026, 6)
        demo_service.obtener_o_crear_cierre(2026, 7)

        self.assertTrue((self.data_dir / "monthly_closures.json").exists())
        self.assertTrue((demo_dir / "monthly_closures.json").exists())
        self.assertEqual(
            [item.label for item in self.repository.load_monthly_closures()],
            ["2026-06"],
        )
        self.assertEqual(
            [item.label for item in demo_repository.load_monthly_closures()],
            ["2026-07"],
        )

    def test_marca_reporte_generado_y_advertencia_mes_cerrado(self) -> None:
        """Marca reporte y advierte modificaciones sobre mes cerrado."""
        closure = self.service.marcar_reporte_generado(2026, 6, True)
        self.assertTrue(closure.report_generated)

        self.service.marcar_movimientos_revisados(2026, 6)
        self.service.marcar_cuentas_conciliadas(2026, 6)
        self.service.marcar_deudas_revisadas(2026, 6)
        self.service.marcar_presupuestos_revisados(2026, 6)
        self.service.cerrar_mes(2026, 6)

        self.assertIsNotNone(
            self.service.advertencia_modificacion_mes(2026, 6),
        )
        self.assertIsNotNone(
            self.service.advertencia_modificacion_fecha("15-06-2026"),
        )
        self.assertIsNone(
            self.service.advertencia_modificacion_fecha("15-07-2026"),
        )

    def _marcar_checklist_completo(self, year: int, month: int) -> None:
        """Marca todos los puntos requeridos para cerrar."""
        self.service.marcar_movimientos_revisados(year, month)
        self.service.marcar_cuentas_conciliadas(year, month)
        self.service.marcar_deudas_revisadas(year, month)
        self.service.marcar_presupuestos_revisados(year, month)
        self.service.marcar_reporte_generado(year, month)


if __name__ == "__main__":
    unittest.main()
