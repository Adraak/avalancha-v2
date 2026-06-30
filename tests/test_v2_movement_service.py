"""Pruebas del servicio CRUD de movimientos V2."""

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


class MovementServiceTest(unittest.TestCase):
    """Valida CRUD, busqueda e integracion con almacenamiento."""

    def setUp(self) -> None:
        """Crea un repositorio temporal con categorias y cuentas."""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.data_dir = Path(self.temp_dir.name)
        self.repository = BudgetRepository(self.data_dir)
        budget = MonthlyBudget(
            year=2026,
            month=6,
            categories=[
                CategoryBudget("Sueldo", INCOME, 0, True),
                CategoryBudget("Comida", EXPENSE, 0, False),
                CategoryBudget("Transporte", EXPENSE, 0, False),
            ],
        )
        self.repository.save(budget)
        self.repository.save_accounts(
            [
                CuentaFinanciera(
                    account_id="cuenta-1",
                    name="Cuenta debito",
                    account_type="debito",
                    real_balance=100_000,
                ),
            ],
        )
        self.service = MovementService(
            data_dir=self.data_dir,
            year=2026,
            month=6,
        )

    def tearDown(self) -> None:
        """Elimina el directorio temporal de la prueba."""
        self.temp_dir.cleanup()

    def test_crear_movimiento(self) -> None:
        """Crea un movimiento y verifica su persistencia."""
        movement = self.service.crear_movimiento(
            fecha=date(2026, 6, 10),
            tipo="gasto",
            categoria="Comida",
            cuenta_id="cuenta-1",
            monto=12_000,
            descripcion="Almuerzo",
        )

        loaded = self.repository.load(2026, 6)
        self.assertEqual(len(loaded.transactions), 1)
        self.assertEqual(loaded.transactions[0].transaction_id, movement.id)
        self.assertEqual(loaded.transactions[0].amount, 12_000)

    def test_editar_movimiento(self) -> None:
        """Edita un movimiento existente."""
        movement = self.service.crear_movimiento(
            "10-06-2026",
            "gasto",
            "Comida",
            "cuenta-1",
            "12000",
            "Almuerzo",
        )

        updated = self.service.editar_movimiento(
            movement.id,
            "11-06-2026",
            "gasto",
            "Transporte",
            "cuenta-1",
            "15000",
            "Taxi",
        )

        self.assertEqual(updated.categoria, "Transporte")
        self.assertEqual(updated.monto, 15_000)
        loaded = self.repository.load(2026, 6)
        self.assertEqual(len(loaded.transactions), 1)
        self.assertEqual(loaded.transactions[0].category, "Transporte")

    def test_eliminar_movimiento(self) -> None:
        """Elimina un movimiento existente."""
        movement = self.service.crear_movimiento(
            "10-06-2026",
            "gasto",
            "Comida",
            "cuenta-1",
            12_000,
        )

        self.service.eliminar_movimiento(movement.id)

        self.assertEqual(self.service.obtener_movimientos(), [])

    def test_buscar_movimientos(self) -> None:
        """Busca movimientos por descripcion y cuenta."""
        self.service.crear_movimiento(
            "10-06-2026",
            "gasto",
            "Comida",
            "cuenta-1",
            12_000,
            "Supermercado",
        )
        self.service.crear_movimiento(
            "11-06-2026",
            "gasto",
            "Transporte",
            "cuenta-1",
            5_000,
            "Bus",
        )

        result = self.service.buscar_movimientos("super")

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].descripcion, "Supermercado")

    def test_validaciones(self) -> None:
        """Rechaza datos incompletos o inconsistentes."""
        with self.assertRaisesRegex(ValueError, "mayor que cero"):
            self.service.crear_movimiento(
                "10-06-2026",
                "gasto",
                "Comida",
                "cuenta-1",
                -1,
            )

        with self.assertRaisesRegex(ValueError, "categoria"):
            self.service.crear_movimiento(
                "10-06-2026",
                "gasto",
                "No existe",
                "cuenta-1",
                1000,
            )

        with self.assertRaisesRegex(ValueError, "cuenta"):
            self.service.crear_movimiento(
                "10-06-2026",
                "gasto",
                "Comida",
                "cuenta-no-existe",
                1000,
            )

        with self.assertRaisesRegex(ValueError, "fecha"):
            self.service.crear_movimiento(
                "2026/06/10",
                "gasto",
                "Comida",
                "cuenta-1",
                1000,
            )


if __name__ == "__main__":
    unittest.main()

