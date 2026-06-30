"""Servicio visual para preparar datos del Dashboard V2."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from avalancha.storage import BudgetRepository
from core.financial_metrics import FinancialMetrics
from services.financial_alert_service import (
    FinancialAlert,
    FinancialAlertService,
)


@dataclass(frozen=True, slots=True)
class DashboardCard:
    """Tarjeta de indicador lista para pintar en UI."""

    titulo: str
    monto: int
    estado: str


@dataclass(frozen=True, slots=True)
class ChartValue:
    """Valor simple para graficos de barras."""

    etiqueta: str
    monto: int
    porcentaje: float


@dataclass(frozen=True, slots=True)
class BudgetUsageValue:
    """Ejecucion visual de presupuesto por categoria."""

    categoria: str
    presupuesto: int
    gastado: int
    disponible: int
    porcentaje: float
    estado: str


@dataclass(frozen=True, slots=True)
class DashboardVisualData:
    """Agrupa todos los datos visuales del Dashboard."""

    tarjetas: list[DashboardCard]
    gastos_por_categoria: list[ChartValue]
    ingresos_vs_gastos: list[ChartValue]
    presupuestos: list[BudgetUsageValue]
    alertas: list[FinancialAlert]


class DashboardVisualService:
    """Prepara resumenes y estados visuales sin depender de PySide6."""

    def __init__(
        self,
        data_dir: str | Path = "data",
        repository: BudgetRepository | None = None,
        metrics: FinancialMetrics | None = None,
        alert_service: FinancialAlertService | None = None,
    ) -> None:
        """Inicializa el servicio con persistencia del perfil activo."""
        self.repository = repository or BudgetRepository(data_dir)
        self.metrics = metrics or FinancialMetrics()
        self.alert_service = alert_service or FinancialAlertService()

    def obtener_dashboard(
        self,
        year: int | None = None,
        month: int | None = None,
    ) -> DashboardVisualData:
        """Obtiene todos los bloques visuales del mes indicado."""
        current = date.today()
        year = year or current.year
        month = month or current.month
        budget = self.repository.load(year, month)
        accounts = self.repository.load_accounts()
        debts = self.repository.load_debts()
        payments = self.repository.debt_payment_totals(budget)
        indicators = self.metrics.resumen_financiero(
            movimientos=budget.transactions,
            categorias=budget.categories,
            recurrentes=budget.recurring_items,
            deudas=debts,
            cuentas=accounts,
            pagos_por_deuda=payments,
        )
        category_report = self.metrics.reporte_categorias(
            budget.transactions,
            budget.categories,
            budget.recurring_items,
        )

        return DashboardVisualData(
            tarjetas=self.obtener_tarjetas_dashboard(indicators),
            gastos_por_categoria=self.obtener_gastos_por_categoria(
                budget.transactions,
            ),
            ingresos_vs_gastos=self.obtener_ingresos_vs_gastos(indicators),
            presupuestos=self.obtener_presupuesto_vs_gasto(category_report),
            alertas=self.alert_service.generar_alertas(
                indicators,
                category_report,
            ),
        )

    def obtener_tarjetas_dashboard(
        self,
        indicadores: Any,
    ) -> list[DashboardCard]:
        """Construye tarjetas semanticas para indicadores principales."""
        return [
            DashboardCard(
                "Ingresos reales",
                indicadores.ingresos_reales,
                "Saludable" if indicadores.ingresos_reales > 0 else "Sin datos",
            ),
            DashboardCard(
                "Gastos reales",
                indicadores.gastos_reales,
                self._estado_gasto(
                    indicadores.gastos_reales,
                    indicadores.ingresos_reales,
                ),
            ),
            DashboardCard(
                "Flujo libre",
                indicadores.flujo_libre,
                "Saludable" if indicadores.flujo_libre >= 0 else "Crítico",
            ),
            DashboardCard(
                "Deuda actual",
                indicadores.deuda_actual,
                self._estado_deuda(
                    indicadores.deuda_actual,
                    indicadores.ingresos_reales,
                ),
            ),
            DashboardCard(
                "Patrimonio neto",
                indicadores.patrimonio_neto,
                "Saludable" if indicadores.patrimonio_neto >= 0 else "Negativo",
            ),
            DashboardCard(
                "Gastos imprevistos",
                indicadores.gastos_imprevistos,
                "Bajo control"
                if indicadores.gastos_imprevistos <= 100_000
                else "Atención",
            ),
        ]

    def obtener_gastos_por_categoria(
        self,
        movimientos: list[Any],
    ) -> list[ChartValue]:
        """Entrega gastos por categoria con porcentaje del gasto total."""
        totals = self.metrics.gastos_por_categoria(movimientos)
        total_general = sum(totals.values())
        rows = [
            ChartValue(
                etiqueta=category,
                monto=amount,
                porcentaje=(
                    round((amount / total_general) * 100, 1)
                    if total_general
                    else 0.0
                ),
            )
            for category, amount in totals.items()
            if amount > 0
        ]
        return sorted(rows, key=lambda item: (-item.monto, item.etiqueta))

    def obtener_ingresos_vs_gastos(self, indicadores: Any) -> list[ChartValue]:
        """Entrega barras comparativas de ingresos y gastos reales."""
        max_amount = max(indicadores.ingresos_reales, indicadores.gastos_reales)
        return [
            ChartValue(
                "Ingresos",
                indicadores.ingresos_reales,
                self._porcentaje_relativo(indicadores.ingresos_reales, max_amount),
            ),
            ChartValue(
                "Gastos",
                indicadores.gastos_reales,
                self._porcentaje_relativo(indicadores.gastos_reales, max_amount),
            ),
        ]

    def obtener_presupuesto_vs_gasto(
        self,
        reporte_categorias: list[dict[str, Any]],
    ) -> list[BudgetUsageValue]:
        """Entrega ejecucion de presupuesto con estado visual."""
        rows = []
        for item in reporte_categorias:
            budgeted = int(item.get("budgeted", 0))
            actual = int(item.get("actual", 0))
            if budgeted <= 0 and actual <= 0:
                continue
            percentage = float(item.get("usage", 0.0))
            state = self._estado_presupuesto(percentage, budgeted, actual)
            rows.append(
                BudgetUsageValue(
                    categoria=str(item.get("name", "")),
                    presupuesto=budgeted,
                    gastado=actual,
                    disponible=budgeted - actual,
                    porcentaje=percentage,
                    estado=state,
                ),
            )
        return sorted(rows, key=lambda item: (-item.porcentaje, item.categoria))

    def _estado_presupuesto(
        self,
        porcentaje: float,
        presupuesto: int,
        gastado: int,
    ) -> str:
        """Clasifica una ejecucion presupuestaria."""
        if presupuesto <= 0 and gastado > 0:
            return "Sin presupuesto"
        if porcentaje > 100:
            return "Excedido"
        if porcentaje > 90:
            return "Crítico"
        if porcentaje >= 70:
            return "Atención"
        return "Bajo control"

    def _estado_gasto(self, gastos: int, ingresos: int) -> str:
        """Clasifica gasto real contra ingreso real."""
        if ingresos <= 0 and gastos > 0:
            return "Crítico"
        if ingresos <= 0:
            return "Sin datos"
        if gastos > ingresos:
            return "Crítico"
        if gastos >= ingresos * 0.8:
            return "Atención"
        return "Bajo control"

    def _estado_deuda(self, deuda: int, ingresos: int) -> str:
        """Clasifica deuda total contra ingreso mensual."""
        if deuda <= 0:
            return "Sin deuda"
        if ingresos <= 0:
            return "Atención"
        if deuda > ingresos:
            return "Atención"
        return "Bajo control"

    @staticmethod
    def _porcentaje_relativo(amount: int, max_amount: int) -> float:
        """Calcula porcentaje relativo para graficos comparativos."""
        if max_amount <= 0:
            return 0.0
        return round((amount / max_amount) * 100, 1)
