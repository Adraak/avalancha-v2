"""Pruebas de gestion formal de categorias V2."""

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
    Transaction,
)
from avalancha.storage import BudgetRepository
from services.budget_service import BudgetService
from services.category_service import CategoryService
from services.dashboard_visual_service import DashboardVisualService
from services.financial_alert_service import FinancialAlertService
from services.movement_service import MovementService


class CategoryServiceTest(unittest.TestCase):
    """Valida CRUD, aislamiento e integracion de categorias."""

    def setUp(self) -> None:
        """Crea datos temporales por prueba."""
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
        self.service = CategoryService(
            data_dir=self.data_dir,
            repository=self.repository,
        )

    def tearDown(self) -> None:
        """Elimina archivos temporales."""
        self.temp_dir.cleanup()

    def test_crear_categoria_valida(self) -> None:
        """Crea una categoria activa con tipo y clase."""
        categoria = self.service.crear_categoria(
            "Proyecto casa",
            "gasto",
            "variable",
        )

        loaded = self.service.obtener_categoria(categoria.id)

        self.assertEqual(loaded.nombre, "Proyecto casa")
        self.assertEqual(loaded.tipo, "gasto")
        self.assertEqual(loaded.clase, "variable")
        self.assertTrue(loaded.activa)

    def test_rechaza_nombre_vacio_tipo_y_clase_invalidos(self) -> None:
        """Valida campos obligatorios y dominios permitidos."""
        with self.assertRaisesRegex(ValueError, "nombre"):
            self.service.crear_categoria("", "gasto", "variable")
        with self.assertRaisesRegex(ValueError, "tipo"):
            self.service.crear_categoria("Prueba", "malo", "variable")
        with self.assertRaisesRegex(ValueError, "clase"):
            self.service.crear_categoria("Prueba", "gasto", "mala")

    def test_evitar_duplicado_activo_por_nombre_y_tipo(self) -> None:
        """Impide duplicar categorias activas equivalentes."""
        self.service.crear_categoria("Proyecto casa", "gasto", "variable")

        with self.assertRaisesRegex(ValueError, "Ya existe"):
            self.service.crear_categoria("proyecto casa", "gasto", "fija")

    def test_editar_tipo_clase_y_nombre(self) -> None:
        """Permite editar campos de una categoria existente."""
        categoria = self.service.crear_categoria(
            "Proyecto casa",
            "gasto",
            "variable",
        )

        updated = self.service.editar_categoria(
            categoria.id,
            nombre="Proyecto hogar",
            tipo="ambos",
            clase="fija",
        )

        self.assertEqual(updated.nombre, "Proyecto hogar")
        self.assertEqual(updated.tipo, "ambos")
        self.assertEqual(updated.clase, "fija")

    def test_desactivar_y_listar_activas(self) -> None:
        """Oculta categorias inactivas desde listados activos."""
        categoria = self.service.crear_categoria(
            "Proyecto casa",
            "gasto",
            "variable",
        )

        self.service.desactivar_categoria(categoria.id)
        nombres = {item.nombre for item in self.service.listar_activas()}

        self.assertNotIn("Proyecto casa", nombres)

    def test_listar_por_tipo_incluye_ambos(self) -> None:
        """Incluye categorias ambos para ingreso y gasto."""
        self.service.crear_categoria("Reembolso hogar", "ambos", "variable")

        gastos = self.service.nombres_por_tipo("gasto")
        ingresos = self.service.nombres_por_tipo("ingreso")

        self.assertIn("Reembolso hogar", gastos)
        self.assertIn("Reembolso hogar", ingresos)

    def test_aislamiento_personal_demo_por_data_dir(self) -> None:
        """Evita mezclar categorias entre carpetas de perfil."""
        other_temp = tempfile.TemporaryDirectory()
        self.addCleanup(other_temp.cleanup)
        other_dir = Path(other_temp.name)
        personal = CategoryService(self.data_dir)
        demo = CategoryService(other_dir)

        personal.crear_categoria("Categoria personal", "gasto", "variable")
        demo.crear_categoria("Categoria demo", "gasto", "variable")

        self.assertIsNone(demo.obtener_por_nombre("Categoria personal"))
        self.assertIsNone(personal.obtener_por_nombre("Categoria demo"))

    def test_no_elimina_categoria_con_movimientos_asociados(self) -> None:
        """Detecta historial asociado antes de eliminar fisicamente."""
        budget = self.repository.load(2026, 6)
        budget.transactions.append(
            Transaction(
                transaction_type=EXPENSE,
                category="Comida",
                amount=10_000,
                tx_date="2026-06-10",
                account_id="cuenta-1",
            ),
        )
        self.repository.save(budget)
        categoria = self.service.obtener_por_nombre("Comida", "gasto")

        self.assertIsNotNone(categoria)
        self.assertFalse(self.service.puede_eliminar_categoria(categoria.id))

    def test_movimiento_usa_categoria_activa_por_tipo(self) -> None:
        """Permite crear movimientos solo con categoria activa compatible."""
        self.service.crear_categoria("Proyecto casa", "gasto", "variable")
        movement_service = MovementService(
            data_dir=self.data_dir,
            year=2026,
            month=6,
            repository=self.repository,
            category_service=self.service,
        )

        movement = movement_service.crear_movimiento(
            fecha=date(2026, 6, 10),
            tipo="gasto",
            categoria="Proyecto casa",
            cuenta_id="cuenta-1",
            monto=20_000,
        )

        self.assertEqual(movement.categoria, "Proyecto casa")

    def test_movimiento_ingreso_no_usa_categoria_solo_gasto(self) -> None:
        """Rechaza categoria de gasto en movimiento de ingreso."""
        movement_service = MovementService(
            data_dir=self.data_dir,
            year=2026,
            month=6,
            repository=self.repository,
            category_service=self.service,
        )

        with self.assertRaisesRegex(ValueError, "categoria"):
            movement_service.crear_movimiento(
                fecha=date(2026, 6, 10),
                tipo="ingreso",
                categoria="Comida",
                cuenta_id="cuenta-1",
                monto=20_000,
            )

    def test_categoria_inactiva_no_aparece_para_movimiento_nuevo(self) -> None:
        """Oculta categorias inactivas de formularios nuevos."""
        categoria = self.service.crear_categoria(
            "Temporal",
            "gasto",
            "variable",
        )
        self.service.desactivar_categoria(categoria.id)
        movement_service = MovementService(
            data_dir=self.data_dir,
            year=2026,
            month=6,
            repository=self.repository,
            category_service=self.service,
        )

        self.assertNotIn("Temporal", movement_service.obtener_categorias("gasto"))
        self.assertIn(
            "Temporal",
            movement_service.obtener_categorias(
                "gasto",
                incluir_categoria="Temporal",
            ),
        )

    def test_presupuesto_rechaza_categoria_solo_ingreso(self) -> None:
        """No permite crear presupuesto con categoria solo ingreso."""
        budget_service = BudgetService(
            data_dir=self.data_dir,
            year=2026,
            month=6,
            repository=self.repository,
            category_service=self.service,
        )

        with self.assertRaisesRegex(ValueError, "categoria"):
            budget_service.crear_presupuesto(
                {
                    "nombre": "Presupuesto sueldo",
                    "categoria": "Sueldo",
                    "monto_mensual": 100_000,
                    "moneda": "CLP",
                    "fecha_inicio": date(2026, 6, 1),
                },
            )

    def test_presupuesto_permite_categoria_gasto_activa(self) -> None:
        """Permite presupuestar categorias de gasto."""
        budget_service = BudgetService(
            data_dir=self.data_dir,
            year=2026,
            month=6,
            repository=self.repository,
            category_service=self.service,
        )

        presupuesto = budget_service.crear_presupuesto(
            {
                "nombre": "Presupuesto comida",
                "categoria": "Comida",
                "monto_mensual": 100_000,
                "moneda": "CLP",
                "fecha_inicio": date(2026, 6, 1),
            },
        )

        self.assertEqual(presupuesto.categoria, "Comida")

    def test_resumen_visual_usa_clase_formal(self) -> None:
        """Clasifica categorias fijas y variables desde modelo formal."""
        fixed = self.service.crear_categoria("Colegio", "gasto", "fija")
        variable = self.service.crear_categoria("Hobbies", "gasto", "variable")
        self.assertTrue(self.service.es_categoria_fija(fixed.nombre))
        self.assertFalse(self.service.es_categoria_fija(variable.nombre))
        budget = MonthlyBudget(
            year=2026,
            month=6,
            categories=[
                CategoryBudget("Colegio", EXPENSE, 200_000, False),
                CategoryBudget("Hobbies", EXPENSE, 80_000, True),
            ],
        )
        self.repository.save(budget)
        dashboard = DashboardVisualService(
            data_dir=self.data_dir,
            repository=self.repository,
            category_service=self.service,
        )

        data = dashboard.obtener_dashboard(2026, 6)
        fixed_names = {item.categoria for item in data.pagos_fijos.items}
        variable_names = {item.categoria for item in data.presupuestos}

        self.assertIn("Colegio", fixed_names)
        self.assertIn("Hobbies", variable_names)

    def test_resumen_visual_fallback_antiguo_sigue_funcionando(self) -> None:
        """Mantiene fallback por string si no existe categoria formal."""
        budget = MonthlyBudget(
            year=2026,
            month=6,
            categories=[
                CategoryBudget("Arriendo antiguo", EXPENSE, 300_000, True),
            ],
        )
        self.repository.save(budget)
        dashboard = DashboardVisualService(
            data_dir=self.data_dir,
            repository=self.repository,
        )

        data = dashboard.obtener_dashboard(2026, 6)

        self.assertIn(
            "Arriendo antiguo",
            {item.categoria for item in data.pagos_fijos.items},
        )

    def test_alerta_ignora_fija_y_detecta_variable_excedida(self) -> None:
        """Evita falso critico en fijas y alerta variables excedidas."""
        self.service.crear_categoria("Colegio", "gasto", "fija")
        self.service.crear_categoria("Hobbies", "gasto", "variable")
        alert_service = FinancialAlertService(self.service)
        indicators = type(
            "Indicadores",
            (),
            {
                "flujo_libre": 100_000,
                "gastos_reales": 100_000,
                "ingresos_reales": 300_000,
                "deuda_actual": 0,
                "gastos_imprevistos": 0,
            },
        )()

        alertas = alert_service.generar_alertas(
            indicators,
            [
                {"name": "Colegio", "status": "sobrepasado", "usage": 120.0},
                {"name": "Hobbies", "status": "sobrepasado", "usage": 120.0},
            ],
        )

        mensajes = " ".join(alerta.mensaje for alerta in alertas)
        self.assertIn("Hobbies", mensajes)
        self.assertNotIn("Colegio", mensajes)


if __name__ == "__main__":
    unittest.main()
