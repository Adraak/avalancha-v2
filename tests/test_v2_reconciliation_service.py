"""Pruebas del servicio de conciliacion V2."""

from __future__ import annotations

import tempfile
import unittest
from datetime import date
from pathlib import Path

from avalancha.models import (
    CategoryBudget,
    CuentaFinanciera,
    EXPENSE,
    INCOME,
    MonthlyBudget,
)
from avalancha.storage import BudgetRepository
from services.movement_service import MovementService
from services.reconciliation_service import ReconciliationService


class ReconciliationServiceTest(unittest.TestCase):
    """Valida CRUD, estados y diferencias de conciliacion."""

    def setUp(self) -> None:
        """Crea datos temporales de cuenta y movimientos."""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.data_dir = Path(self.temp_dir.name)
        self.repository = BudgetRepository(self.data_dir)
        budget = MonthlyBudget(
            year=2026,
            month=6,
            categories=[
                CategoryBudget("Sueldo", INCOME, 0, True),
                CategoryBudget("Comida", EXPENSE, 0, False),
            ],
        )
        self.repository.save(budget)
        self.repository.save_accounts(
            [
                CuentaFinanciera(
                    account_id="cuenta-1",
                    name="Cuenta debito",
                    account_type="debito",
                    initial_balance=0,
                    real_balance=None,
                ),
                CuentaFinanciera(
                    account_id="cuenta-2",
                    name="Efectivo",
                    account_type="efectivo",
                    initial_balance=0,
                    real_balance=None,
                ),
            ],
        )
        self.movement_service = MovementService(
            data_dir=self.data_dir,
            year=2026,
            month=6,
            repository=self.repository,
        )
        self.movement_service.crear_movimiento(
            fecha="01-06-2026",
            tipo="ingreso",
            categoria="Sueldo",
            cuenta_id="cuenta-1",
            monto=100_000,
            descripcion="Ingreso",
        )
        self.movement_service.crear_movimiento(
            fecha="02-06-2026",
            tipo="gasto",
            categoria="Comida",
            cuenta_id="cuenta-1",
            monto=20_000,
            descripcion="Compra",
        )
        self.service = ReconciliationService(
            data_dir=self.data_dir,
            year=2026,
            month=6,
            repository=self.repository,
            movement_service=self.movement_service,
        )

    def tearDown(self) -> None:
        """Elimina archivos temporales."""
        self.temp_dir.cleanup()

    def test_crear_conciliacion(self) -> None:
        """Crea una conciliacion cuadrada."""
        item = self.service.crear_conciliacion(
            self._datos("cuenta-1", 80_000),
        )

        self.assertEqual(item.saldo_registrado, 80_000)
        self.assertEqual(item.saldo_real, 80_000)
        self.assertEqual(item.diferencia, 0)
        self.assertEqual(item.estado, "Cuadrada")

    def test_editar_conciliacion(self) -> None:
        """Edita saldo real y observaciones."""
        self.service.crear_conciliacion(self._datos("cuenta-1", 80_000))

        item = self.service.editar_conciliacion(
            "cuenta-1",
            self._datos("cuenta-1", 75_000, observaciones="Falta gasto"),
        )

        self.assertEqual(item.diferencia, -5_000)
        self.assertEqual(item.estado, "Con diferencia")
        self.assertEqual(item.observaciones, "Falta gasto")

    def test_eliminar_conciliacion(self) -> None:
        """Elimina datos de conciliacion sin eliminar la cuenta."""
        self.service.crear_conciliacion(self._datos("cuenta-1", 80_000))

        self.service.eliminar_conciliacion("cuenta-1")
        item = self.service.obtener_conciliacion_por_cuenta("cuenta-1")

        self.assertIsNone(item.saldo_real)
        self.assertEqual(item.estado, "Pendiente")

    def test_calcular_diferencia(self) -> None:
        """Calcula diferencia sin persistir conciliacion."""
        difference = self.service.calcular_diferencia("cuenta-1", 75_000)

        self.assertEqual(difference, -5_000)

    def test_detecta_cuenta_con_diferencia(self) -> None:
        """Identifica cuentas con diferencia distinta de cero."""
        self.service.crear_conciliacion(self._datos("cuenta-1", 75_000))
        self.service.crear_conciliacion(self._datos("cuenta-2", 0))

        items = self.service.obtener_cuentas_con_diferencia()

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].cuenta_id, "cuenta-1")

    def test_marcar_como_revisada(self) -> None:
        """Persiste el estado revisada."""
        self.service.crear_conciliacion(self._datos("cuenta-1", 75_000))

        reviewed = self.service.marcar_como_revisada("cuenta-1")
        loaded = self.service.obtener_conciliacion_por_id("cuenta-1")

        self.assertEqual(reviewed.estado, "Revisada")
        self.assertEqual(loaded.estado, "Revisada")

    def test_validaciones(self) -> None:
        """Rechaza cuenta, saldo y fecha invalidos."""
        with self.assertRaisesRegex(ValueError, "cuenta"):
            self.service.crear_conciliacion(self._datos("", 80_000))

        with self.assertRaisesRegex(ValueError, "cuenta"):
            self.service.crear_conciliacion(
                self._datos("cuenta-inexistente", 80_000),
            )

        with self.assertRaisesRegex(ValueError, "saldo real"):
            self.service.crear_conciliacion(
                self._datos("cuenta-1", "malo"),
            )

        with self.assertRaisesRegex(ValueError, "fecha"):
            self.service.crear_conciliacion(
                self._datos("cuenta-1", 80_000, fecha="2026/06/01"),
            )

    def test_rechaza_duplicado_misma_cuenta_y_fecha(self) -> None:
        """Rechaza conciliacion duplicada para cuenta y fecha."""
        self.service.crear_conciliacion(self._datos("cuenta-1", 80_000))

        with self.assertRaisesRegex(ValueError, "Ya existe"):
            self.service.crear_conciliacion(self._datos("cuenta-1", 80_000))

    @staticmethod
    def _datos(
        cuenta_id: str,
        saldo_real: int | str,
        fecha: date | str = date(2026, 6, 30),
        estado: str = "Pendiente",
        observaciones: str = "",
    ) -> dict[str, object]:
        """Crea datos de conciliacion para pruebas."""
        return {
            "cuenta_id": cuenta_id,
            "saldo_real": saldo_real,
            "fecha_conciliacion": fecha,
            "estado": estado,
            "observaciones": observaciones,
        }


if __name__ == "__main__":
    unittest.main()

