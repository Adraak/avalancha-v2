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
        self.assertIn("Deuda actual", card_titles)
        self.assertIn("Comida", expense_labels)
        self.assertEqual(data.ingresos_vs_gastos[0].etiqueta, "Ingresos")
        self.assertTrue(data.presupuestos)
        self.assertTrue(data.alertas)

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


if __name__ == "__main__":
    unittest.main()
