"""Pruebas de equivalencia entre logica heredada y nucleo V2."""

from __future__ import annotations

import unittest

from avalancha.finanzas import (
    AnalizadorResumen,
    GestorConciliacion,
    GestorDeudas,
)
from avalancha.models import (
    CategoryBudget,
    CuentaFinanciera,
    Debt,
    EXPENSE,
    INCOME,
    MonthlyBudget,
    RecurringItem,
    Transaction,
)
from core.financial_metrics import FinancialMetrics
from services.reconciliation_service import ReconciliationService


class FinancialEquivalenceTest(unittest.TestCase):
    """Compara resultados nuevos contra la logica heredada."""

    def setUp(self) -> None:
        """Prepara un presupuesto con ingresos, gastos, deuda y cuentas."""
        self.metrics = FinancialMetrics()
        self.budget = MonthlyBudget(
            year=2026,
            month=6,
            categories=[
                CategoryBudget("Sueldo", INCOME, 1_500_000, True),
                CategoryBudget("Arriendo", EXPENSE, 650_000, True),
                CategoryBudget("Comida", EXPENSE, 100_000, False, 80),
                CategoryBudget("Servicios", EXPENSE, 0, False, 80),
                CategoryBudget("Ocio", EXPENSE, 50_000, False, 80),
                CategoryBudget("Tarjeta", EXPENSE, 200_000, True),
                CategoryBudget("Chat GPT", EXPENSE, 20_000, True),
            ],
            recurring_items=[
                RecurringItem(
                    recurring_id="rec-arriendo",
                    transaction_type=EXPENSE,
                    category="Arriendo",
                    amount=650_000,
                    description="Arriendo",
                    account_id="cuenta-debito",
                ),
                RecurringItem(
                    recurring_id="rec-chatgpt",
                    transaction_type=EXPENSE,
                    category="Chat GPT",
                    amount=20_000,
                    description="Suscripcion",
                    account_id="cuenta-debito",
                ),
            ],
            transactions=[
                Transaction(
                    transaction_type=INCOME,
                    category="Sueldo",
                    amount=1_500_000,
                    tx_date="2026-06-05",
                    description="Sueldo",
                    account_id="cuenta-debito",
                ),
                Transaction(
                    transaction_type=EXPENSE,
                    category="Arriendo",
                    amount=650_000,
                    tx_date="2026-06-01",
                    description="Arriendo",
                    recurring_id="rec-arriendo",
                    account_id="cuenta-debito",
                ),
                Transaction(
                    transaction_type=EXPENSE,
                    category="Comida",
                    amount=120_000,
                    tx_date="2026-06-10",
                    description="Supermercado",
                    account_id="cuenta-debito",
                ),
                Transaction(
                    transaction_type=EXPENSE,
                    category="Servicios",
                    amount=10_000,
                    tx_date="2026-06-12",
                    description="Gasto no previsto",
                    is_unexpected=True,
                    account_id="cuenta-debito",
                ),
                Transaction(
                    transaction_type=EXPENSE,
                    category="Ocio",
                    amount=45_000,
                    tx_date="2026-06-14",
                    description="Salida",
                    account_id="cuenta-debito",
                ),
                Transaction(
                    transaction_type=EXPENSE,
                    category="Tarjeta",
                    amount=200_000,
                    tx_date="2026-06-15",
                    description="Pago tarjeta",
                    debt_id="deuda-tarjeta",
                    account_id="cuenta-debito",
                ),
            ],
        )
        self.debts = [
            Debt(
                debt_id="deuda-tarjeta",
                name="Tarjeta prueba",
                category="tarjeta_credito",
                current_balance=1_000_000,
                previous_month_balance=1_250_000,
                current_monthly_payment=200_000,
                minimum_payment=100_000,
                monthly_interest_rate=2.5,
                active=True,
            ),
            Debt(
                debt_id="deuda-consumo",
                name="Credito consumo",
                category="credito_consumo",
                current_balance=500_000,
                previous_month_balance=550_000,
                current_monthly_payment=50_000,
                minimum_payment=50_000,
                active=True,
            ),
        ]
        self.payment_totals = {"deuda-tarjeta": 200_000}
        self.accounts = [
            CuentaFinanciera(
                account_id="cuenta-debito",
                name="Cuenta debito",
                account_type="debito",
                initial_balance=100_000,
                real_balance=600_000,
                reconciliation_date="2026-06-20",
            ),
            CuentaFinanciera(
                account_id="cuenta-credito",
                name="Tarjeta",
                account_type="tarjeta_credito",
                initial_balance=300_000,
                real_balance=300_000,
                reconciliation_date="2026-06-19",
            ),
        ]

    def test_flow_expected_result_and_unexpected_expenses_match(self) -> None:
        """Compara flujo libre, resultado esperado e imprevistos."""
        analizador = AnalizadorResumen(self.budget, self.accounts)
        esperado = self.budget.totals()

        self.assertEqual(
            self.metrics.ingresos_reales(self.budget.transactions),
            esperado["income"],
        )
        self.assertEqual(
            self.metrics.gastos_reales(self.budget.transactions),
            esperado["expenses"],
        )
        self.assertEqual(
            self.metrics.flujo_libre(self.budget.transactions),
            esperado["balance"],
        )
        self.assertEqual(
            self.metrics.resultado_esperado(
                self.budget.transactions,
                self.budget.recurring_items,
            ),
            analizador.calcular_resultado_esperado_fin_mes(),
        )
        self.assertEqual(
            self.metrics.gastos_imprevistos(self.budget.transactions),
            self.budget.expense_breakdown()["unexpected"],
        )

    def test_debt_patrimony_and_amortization_match(self) -> None:
        """Compara deuda, variacion, intereses, amortizacion y patrimonio."""
        gestor = GestorDeudas(self.debts, self.payment_totals)
        activos = self.metrics.activos_liquidos(self.accounts)

        self.assertEqual(
            self.metrics.deuda_actual(self.debts, self.payment_totals),
            gestor.deuda_total_actual(),
        )
        self.assertEqual(
            self.metrics.variacion_deuda(self.debts, self.payment_totals),
            gestor.variacion_mensual_deuda(),
        )
        self.assertEqual(
            self.metrics.pago_mensual_deuda(self.debts),
            gestor.calcular_pago_mensual_total(),
        )
        self.assertEqual(
            self.metrics.interes_mensual_estimado(
                self.debts,
                self.payment_totals,
            ),
            gestor.calcular_interes_mensual_estimado(),
        )
        self.assertEqual(
            self.metrics.amortizacion_neta(self.debts, self.payment_totals),
            gestor.calcular_amortizacion_neta(),
        )
        self.assertEqual(
            self.metrics.patrimonio_neto(
                self.accounts,
                self.debts,
                self.payment_totals,
            ),
            gestor.patrimonio_neto(assets=activos),
        )

    def test_reconciliation_match(self) -> None:
        """Compara conciliacion nueva contra conciliacion heredada."""
        gestor = GestorConciliacion(self.accounts)
        gestor.recalcular_saldos_registrados(self.budget)
        resumen_heredado = gestor.obtener_resumen()
        resumen_nuevo = ReconciliationService().resumen_conciliacion(
            self.accounts,
        )

        self.assertEqual(resumen_nuevo, resumen_heredado)

    def test_categories_and_top_expenses_match(self) -> None:
        """Compara reporte de categorias y ranking de gastos."""
        analizador = AnalizadorResumen(self.budget, self.accounts)
        reporte_heredado = self.budget.category_report()
        reporte_nuevo = self.metrics.reporte_categorias(
            self.budget.transactions,
            self.budget.categories,
            self.budget.recurring_items,
        )

        self.assertEqual(reporte_nuevo, reporte_heredado)
        self.assertEqual(
            self.metrics.principales_gastos(self.budget.transactions),
            analizador.obtener_ranking_gastos(),
        )
        self.assertEqual(
            self.metrics.categorias_sobrepasadas(
                self.budget.transactions,
                self.budget.categories,
                self.budget.recurring_items,
            ),
            ["Comida"],
        )
        self.assertEqual(
            self.metrics.categorias_sin_presupuesto(
                self.budget.transactions,
                self.budget.categories,
                self.budget.recurring_items,
            ),
            ["Servicios"],
        )


if __name__ == "__main__":
    unittest.main()

