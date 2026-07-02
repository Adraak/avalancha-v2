"""Pruebas del servicio visual de Dashboard."""

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
    Transaction,
)
from avalancha.storage import BudgetRepository
from services.dashboard_visual_service import DashboardVisualService


class DashboardVisualServiceTest(unittest.TestCase):
    """Valida datos visuales preparados para el Dashboard."""

    def setUp(self) -> None:
        """Crea un perfil temporal con datos ficticios."""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.data_dir = Path(self.temp_dir.name)
        self.repository = BudgetRepository(self.data_dir)
        budget = MonthlyBudget(
            year=2026,
            month=6,
            categories=[
                CategoryBudget("Sueldo", INCOME, 0, True),
                CategoryBudget("Comida", EXPENSE, 100_000, False),
                CategoryBudget("Transporte", EXPENSE, 50_000, False),
            ],
            transactions=[
                Transaction(
                    INCOME,
                    "Sueldo",
                    200_000,
                    "2026-06-01",
                    "Ingreso prueba",
                ),
                Transaction(
                    EXPENSE,
                    "Comida",
                    120_000,
                    "2026-06-02",
                    "Compra prueba",
                    is_unexpected=True,
                ),
                Transaction(
                    EXPENSE,
                    "Transporte",
                    20_000,
                    "2026-06-03",
                    "Bus prueba",
                ),
            ],
        )
        self.repository.save(budget)
        self.repository.save_accounts(
            [
                CuentaFinanciera(
                    account_id="cuenta-1",
                    name="Cuenta prueba",
                    account_type="debito",
                    real_balance=50_000,
                ),
            ],
        )
        self.repository.save_debts(
            [
                Debt(
                    debt_id="deuda-1",
                    name="Deuda prueba",
                    category="credito_consumo",
                    current_balance=300_000,
                    previous_month_balance=350_000,
                    current_monthly_payment=50_000,
                ),
            ],
        )
        self.service = DashboardVisualService(
            data_dir=self.data_dir,
            repository=self.repository,
        )

    def tearDown(self) -> None:
        """Elimina archivos temporales."""
        self.temp_dir.cleanup()

    def test_obtener_dashboard_entrega_tarjetas_y_graficos(self) -> None:
        """Genera tarjetas, barras y alertas desde datos persistidos."""
        data = self.service.obtener_dashboard(2026, 6)

        card_titles = {card.titulo for card in data.tarjetas}
        expense_labels = {item.etiqueta for item in data.gastos_por_categoria}

        self.assertIn("Flujo libre", card_titles)
        self.assertIn("Deuda total", card_titles)
        self.assertIn("Imprevistos", card_titles)
        self.assertIn("Comida", expense_labels)
        self.assertEqual(data.ingresos_vs_gastos[0].etiqueta, "Ingresos")
        self.assertEqual(
            [item.etiqueta for item in data.ingresos_vs_gastos],
            ["Ingresos", "Gastos", "Flujo libre"],
        )
        self.assertEqual(data.imprevistos.total, 120_000)
        self.assertEqual(data.imprevistos.cantidad, 1)
        self.assertTrue(data.presupuestos)
        self.assertTrue(data.alertas)

    def test_metricas_de_imprevistos(self) -> None:
        """Calcula total, cantidad, porcentaje y categoria principal."""
        data = self.service.obtener_dashboard(2026, 6)
        unexpected_card = next(
            card
            for card in data.tarjetas
            if card.titulo == "Imprevistos"
        )

        self.assertEqual(data.imprevistos.total, 120_000)
        self.assertEqual(data.imprevistos.cantidad, 1)
        self.assertEqual(data.imprevistos.porcentaje, 85.7)
        self.assertEqual(data.imprevistos.categoria_principal, "Comida")
        self.assertEqual(data.imprevistos.estado, "Crítico")
        self.assertEqual(unexpected_card.monto, 120_000)
        self.assertEqual(unexpected_card.estado, "Crítico")
        self.assertIn("1 eventos", unexpected_card.detalle)

    def test_gastos_por_clase_prioriza_imprevisto(self) -> None:
        """Agrupa gastos por clase sin duplicar movimientos."""
        budget = self.repository.load(2026, 6)
        budget.transactions.append(
            Transaction(
                EXPENSE,
                "Transporte",
                10_000,
                "2026-06-04",
                "Pago recurrente inesperado",
                recurring_id="rec-transporte",
                is_unexpected=True,
            ),
        )
        self.repository.save(budget)

        data = self.service.obtener_dashboard(2026, 6)
        by_class = {item.etiqueta: item.monto for item in data.gastos_por_clase}

        self.assertEqual(by_class["Imprevisto"], 130_000)
        self.assertEqual(by_class["Normal"], 20_000)
        self.assertEqual(by_class["Recurrente"], 0)

    def test_evolucion_flujo_usa_historial_disponible(self) -> None:
        """Entrega puntos de evolucion si existen al menos dos meses."""
        self.repository.save(MonthlyBudget.empty(2026, 4))
        self.repository.save(
            MonthlyBudget(
                year=2026,
                month=5,
                transactions=[
                    Transaction(
                        INCOME,
                        "Sueldo",
                        200_000,
                        "2026-05-01",
                        "Ingreso mes anterior",
                    ),
                    Transaction(
                        EXPENSE,
                        "Comida",
                        80_000,
                        "2026-05-02",
                        "Gasto mes anterior",
                    ),
                ],
            ),
        )

        data = self.service.obtener_dashboard(2026, 6)

        self.assertEqual(
            [point.mes for point in data.evolucion_flujo],
            ["2026-05", "2026-06"],
        )

    def test_evolucion_flujo_sin_historial_devuelve_vacio(self) -> None:
        """No fuerza grafico si aun no existe historial suficiente."""
        data = self.service.obtener_dashboard(2026, 6)

        self.assertEqual(data.evolucion_flujo, [])

    def test_flujo_negativo_se_clasifica_critico(self) -> None:
        """Clasifica tarjeta de flujo libre negativo como critica."""
        data = self.service.obtener_dashboard(2026, 6)
        flujo = next(
            card for card in data.tarjetas if card.titulo == "Flujo libre"
        )

        self.assertEqual(flujo.estado, "Saludable")

        budget = self.repository.load(2026, 6)
        budget.transactions.append(
            Transaction(
                EXPENSE,
                "Comida",
                200_000,
                "2026-06-04",
                "Gasto extra",
            ),
        )
        self.repository.save(budget)

        data = self.service.obtener_dashboard(2026, 6)
        flujo = next(
            card for card in data.tarjetas if card.titulo == "Flujo libre"
        )

        self.assertEqual(flujo.estado, "Crítico")

    def test_presupuesto_sobre_90_es_critico(self) -> None:
        """Clasifica uso de presupuesto mayor a 90 como critico."""
        data = self.service.obtener_dashboard(2026, 6)
        comida = next(
            item for item in data.presupuestos if item.categoria == "Comida"
        )

        self.assertEqual(comida.estado, "Excedido")

        variable = self.service.obtener_presupuesto_variable_vs_gasto(
            [
                {
                    "name": "Salud",
                    "budgeted": 100_000,
                    "actual": 95_000,
                    "usage": 95.0,
                    "is_fixed": False,
                },
            ],
        )

        self.assertEqual(variable[0].estado, "Crítico")

    def test_separa_presupuesto_variable_de_pagos_fijos(self) -> None:
        """No mezcla obligaciones fijas con presupuestos variables."""
        budget = self.repository.load(2026, 6)
        budget.categories.extend(
            [
                CategoryBudget("Arriendo", EXPENSE, 100_000, False),
                CategoryBudget("Spotify", EXPENSE, 50_000, True),
                CategoryBudget("Internet", EXPENSE, 80_000, True),
                CategoryBudget("Tarjeta de crédito Demo", EXPENSE, 30_000, True),
            ],
        )
        budget.transactions.extend(
            [
                Transaction(
                    EXPENSE,
                    "Arriendo",
                    100_000,
                    "2026-06-05",
                    "Arriendo mensual",
                ),
                Transaction(
                    EXPENSE,
                    "Internet",
                    40_000,
                    "2026-06-06",
                    "Pago parcial internet",
                ),
                Transaction(
                    EXPENSE,
                    "Tarjeta de crédito Demo",
                    30_000,
                    "2026-06-07",
                    "Pago tarjeta demo",
                ),
            ],
        )
        self.repository.save(budget)

        data = self.service.obtener_dashboard(2026, 6)
        variable_names = {item.categoria for item in data.presupuestos}
        fixed_by_name = {
            item.nombre: item for item in data.pagos_fijos.items
        }

        self.assertIn("Comida", variable_names)
        self.assertNotIn("Arriendo", variable_names)
        self.assertEqual(fixed_by_name["Arriendo"].estado, "Pagado")
        self.assertEqual(fixed_by_name["Arriendo"].monto_pendiente, 0)
        self.assertEqual(fixed_by_name["Internet"].estado, "Parcial")
        self.assertEqual(fixed_by_name["Internet"].monto_pendiente, 40_000)
        self.assertEqual(fixed_by_name["Spotify"].estado, "Pendiente")
        self.assertEqual(fixed_by_name["Spotify"].monto_pendiente, 50_000)
        self.assertIn("Pago tarjeta de crédito Demo", fixed_by_name)
        self.assertEqual(
            fixed_by_name["Pago tarjeta de crédito Demo"].estado,
            "Pagado",
        )
        self.assertNotIn("Tarjeta de crédito Demo", fixed_by_name)
        self.assertEqual(data.pagos_fijos.total_fijo_esperado, 260_000)
        self.assertEqual(data.pagos_fijos.total_fijo_pagado, 170_000)
        self.assertEqual(data.pagos_fijos.total_fijo_pendiente, 90_000)
        self.assertFalse(
            any(
                "Arriendo" in alert.mensaje
                and alert.titulo == "Presupuesto excedido"
                for alert in data.alertas
            ),
        )

    def test_perfiles_temporales_no_se_mezclan(self) -> None:
        """Comprueba que dos data_dir entregan datos distintos."""
        with tempfile.TemporaryDirectory() as other_dir:
            other_path = Path(other_dir)
            other_repository = BudgetRepository(other_path)
            other_repository.save(
                MonthlyBudget(
                    year=2026,
                    month=6,
                    transactions=[
                        Transaction(
                            INCOME,
                            "Sueldo",
                            900_000,
                            "2026-06-01",
                            "Ingreso otro perfil",
                        ),
                        Transaction(
                            EXPENSE,
                            "Comida",
                            10_000,
                            "2026-06-02",
                            "Imprevisto otro perfil",
                            is_unexpected=True,
                        ),
                    ],
                ),
            )
            other_service = DashboardVisualService(
                data_dir=other_path,
                repository=other_repository,
            )

            current_data = self.service.obtener_dashboard(2026, 6)
            other_data = other_service.obtener_dashboard(2026, 6)
            current_income = next(
                item
                for item in current_data.ingresos_vs_gastos
                if item.etiqueta == "Ingresos"
            )
            other_income = next(
                item
                for item in other_data.ingresos_vs_gastos
                if item.etiqueta == "Ingresos"
            )

            self.assertNotEqual(current_income.monto, other_income.monto)
            self.assertNotEqual(
                current_data.imprevistos.total,
                other_data.imprevistos.total,
            )


if __name__ == "__main__":
    unittest.main()
