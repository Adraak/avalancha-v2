"""Pruebas del servicio de presupuestos V2."""

from __future__ import annotations

import tempfile
import unittest
from datetime import date
from pathlib import Path

from avalancha.models import CuentaFinanciera, MonthlyBudget
from avalancha.storage import BudgetRepository
from services.budget_service import BudgetService
from services.movement_service import MovementService


class BudgetServiceTest(unittest.TestCase):
    """Valida CRUD, ejecucion e integracion con movimientos."""

    def setUp(self) -> None:
        """Crea un repositorio temporal para las pruebas."""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.data_dir = Path(self.temp_dir.name)
        self.repository = BudgetRepository(self.data_dir)
        self.repository.save(MonthlyBudget(year=2026, month=6))
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
        self.movement_service = MovementService(
            data_dir=self.data_dir,
            year=2026,
            month=6,
            repository=self.repository,
        )
        self.service = BudgetService(
            data_dir=self.data_dir,
            year=2026,
            month=6,
            repository=self.repository,
            movement_service=self.movement_service,
        )

    def tearDown(self) -> None:
        """Elimina archivos temporales de la prueba."""
        self.temp_dir.cleanup()

    def test_crear_presupuesto(self) -> None:
        """Crea un presupuesto con ID estable."""
        presupuesto = self.service.crear_presupuesto(
            self._datos(categoria="Comida", monto_mensual=100_000),
        )

        self.assertTrue(presupuesto.id)
        loaded = self.service.obtener_presupuesto_por_id(presupuesto.id)
        self.assertEqual(loaded.categoria, "Comida")
        self.assertEqual(loaded.monto_mensual, 100_000)

    def test_editar_presupuesto(self) -> None:
        """Edita monto, categoria y observaciones."""
        presupuesto = self.service.crear_presupuesto(
            self._datos(categoria="Comida", monto_mensual=100_000),
        )

        updated = self.service.editar_presupuesto(
            presupuesto.id,
            self._datos(
                categoria="Supermercado",
                monto_mensual=120_000,
                observaciones="Ajuste",
            ),
        )

        self.assertEqual(updated.id, presupuesto.id)
        self.assertEqual(updated.categoria, "Supermercado")
        self.assertEqual(updated.monto_mensual, 120_000)
        self.assertEqual(updated.observaciones, "Ajuste")

    def test_eliminar_presupuesto(self) -> None:
        """Elimina un presupuesto persistido."""
        presupuesto = self.service.crear_presupuesto(
            self._datos(categoria="Comida", monto_mensual=100_000),
        )

        self.service.eliminar_presupuesto(presupuesto.id)

        self.assertEqual(self.service.obtener_presupuestos(), [])

    def test_activar_desactivar_presupuesto(self) -> None:
        """Cambia el estado activo de un presupuesto."""
        presupuesto = self.service.crear_presupuesto(
            self._datos(categoria="Comida", monto_mensual=100_000),
        )

        inactive = self.service.desactivar_presupuesto(presupuesto.id)
        active = self.service.activar_presupuesto(presupuesto.id)

        self.assertFalse(inactive.activo)
        self.assertTrue(active.activo)

    def test_validaciones(self) -> None:
        """Rechaza campos obligatorios e inconsistencias."""
        with self.assertRaisesRegex(ValueError, "nombre"):
            self.service.crear_presupuesto(
                self._datos(nombre="", categoria="Comida"),
            )

        with self.assertRaisesRegex(ValueError, "categoria"):
            self.service.crear_presupuesto(
                self._datos(nombre="Comida", categoria=""),
            )

        with self.assertRaisesRegex(ValueError, "mayor que cero"):
            self.service.crear_presupuesto(
                self._datos(categoria="Comida", monto_mensual=0),
            )

        with self.assertRaisesRegex(ValueError, "moneda"):
            self.service.crear_presupuesto(
                self._datos(categoria="Comida", moneda=""),
            )

        with self.assertRaisesRegex(ValueError, "termino"):
            self.service.crear_presupuesto(
                self._datos(
                    categoria="Comida",
                    fecha_inicio=date(2026, 6, 10),
                    fecha_termino=date(2026, 6, 1),
                ),
            )

    def test_detecta_duplicado_activo_por_categoria(self) -> None:
        """Impide duplicados activos para la misma categoria y periodo."""
        self.service.crear_presupuesto(
            self._datos(categoria="Comida", monto_mensual=100_000),
        )

        with self.assertRaisesRegex(ValueError, "presupuesto activo"):
            self.service.crear_presupuesto(
                self._datos(categoria="Comida", monto_mensual=120_000),
            )

    def test_calcular_ejecucion_desde_movimientos(self) -> None:
        """Calcula gastado, disponible y porcentaje desde movimientos."""
        presupuesto = self.service.crear_presupuesto(
            self._datos(categoria="Comida", monto_mensual=100_000),
        )
        self.movement_service.crear_movimiento(
            fecha="10-06-2026",
            tipo="gasto",
            categoria="Comida",
            cuenta_id="cuenta-1",
            monto=40_000,
            descripcion="Supermercado",
        )

        ejecucion = self.service.calcular_ejecucion(presupuesto.id)

        self.assertEqual(ejecucion.monto_presupuestado, 100_000)
        self.assertEqual(ejecucion.monto_gastado, 40_000)
        self.assertEqual(ejecucion.saldo_disponible, 60_000)
        self.assertEqual(ejecucion.porcentaje_utilizado, 40.0)
        self.assertEqual(ejecucion.estado_visual, "verde")

    def test_detectar_sobrepresupuesto(self) -> None:
        """Marca rojo cuando el gasto supera el presupuesto."""
        presupuesto = self.service.crear_presupuesto(
            self._datos(categoria="Comida", monto_mensual=10_000),
        )
        self.movement_service.crear_movimiento(
            fecha="10-06-2026",
            tipo="gasto",
            categoria="Comida",
            cuenta_id="cuenta-1",
            monto=12_000,
            descripcion="Supermercado",
        )

        ejecucion = self.service.calcular_ejecucion(presupuesto.id)

        self.assertEqual(ejecucion.porcentaje_utilizado, 120.0)
        self.assertEqual(ejecucion.estado_visual, "rojo")

    def test_presupuesto_sobre_90_por_ciento_es_rojo(self) -> None:
        """Marca rojo cuando el uso supera el 90 por ciento."""
        presupuesto = self.service.crear_presupuesto(
            self._datos(categoria="Comida", monto_mensual=100_000),
        )
        self.movement_service.crear_movimiento(
            fecha="10-06-2026",
            tipo="gasto",
            categoria="Comida",
            cuenta_id="cuenta-1",
            monto=95_000,
            descripcion="Supermercado",
        )

        ejecucion = self.service.calcular_ejecucion(presupuesto.id)

        self.assertEqual(ejecucion.porcentaje_utilizado, 95.0)
        self.assertEqual(ejecucion.estado_visual, "rojo")

    def test_calcular_ejecucion_general(self) -> None:
        """Devuelve filas integradas para la tabla de UI."""
        self.service.crear_presupuesto(
            self._datos(categoria="Comida", monto_mensual=100_000),
        )

        rows = self.service.calcular_ejecucion_general()

        self.assertEqual(len(rows), 1)
        self.assertIn("presupuesto", rows[0])
        self.assertIn("ejecucion", rows[0])

    @staticmethod
    def _datos(
        nombre: str = "Presupuesto comida",
        categoria: str = "Comida",
        monto_mensual: int = 100_000,
        moneda: str = "CLP",
        fecha_inicio: date = date(2026, 6, 1),
        fecha_termino: date | None = None,
        activo: bool = True,
        observaciones: str = "",
    ) -> dict[str, object]:
        """Crea un diccionario de datos para el servicio."""
        return {
            "nombre": nombre,
            "categoria": categoria,
            "monto_mensual": monto_mensual,
            "moneda": moneda,
            "fecha_inicio": fecha_inicio,
            "fecha_termino": fecha_termino,
            "activo": activo,
            "observaciones": observaciones,
        }


if __name__ == "__main__":
    unittest.main()
