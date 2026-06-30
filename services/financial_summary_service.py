"""Servicio base para calcular resumenes financieros."""

from __future__ import annotations

from typing import Any

from core.financial_metrics import FinancialMetrics
from core.models.resumen_mensual import ResumenMensual


class FinancialSummaryService:
    """Calcula indicadores mensuales sin depender de la interfaz grafica."""

    def __init__(self, metrics: FinancialMetrics | None = None) -> None:
        """Inicializa el servicio con un motor de calculos puros."""
        self.metrics = metrics or FinancialMetrics()

    def crear_resumen(
        self,
        mes: str,
        movimientos: list[Any],
        deudas: list[Any],
        categorias: list[Any] | None = None,
        recurrentes: list[Any] | None = None,
        cuentas: list[Any] | None = None,
        pagos_por_deuda: dict[str, int] | None = None,
    ) -> ResumenMensual:
        """Construye un resumen mensual con ingresos, gastos y deudas."""
        categorias = categorias or []
        recurrentes = recurrentes or []
        cuentas = cuentas or []
        calculado = self.metrics.resumen_financiero(
            movimientos=movimientos,
            categorias=categorias,
            recurrentes=recurrentes,
            deudas=deudas,
            cuentas=cuentas,
            pagos_por_deuda=pagos_por_deuda,
        )

        return ResumenMensual(
            mes=mes,
            ingresos_reales=calculado.ingresos_reales,
            gastos_reales=calculado.gastos_reales,
            flujo_libre=calculado.flujo_libre,
            deuda_total=calculado.deuda_actual,
            patrimonio_neto=calculado.patrimonio_neto,
            gastos_imprevistos=calculado.gastos_imprevistos,
            categorias=self.metrics.gastos_por_categoria(movimientos),
        )

    def calcular_indicadores_mensuales(
        self,
        movimientos: list[Any],
        categorias: list[Any],
        recurrentes: list[Any],
        deudas: list[Any],
        cuentas: list[Any],
        pagos_por_deuda: dict[str, int] | None = None,
    ) -> Any:
        """Calcula indicadores completos para reportes y dashboard."""
        return self.metrics.resumen_financiero(
            movimientos=movimientos,
            categorias=categorias,
            recurrentes=recurrentes,
            deudas=deudas,
            cuentas=cuentas,
            pagos_por_deuda=pagos_por_deuda,
        )

    def calcular_ingresos(self, movimientos: list[Any]) -> int:
        """Suma los movimientos de tipo ingreso."""
        return self.metrics.ingresos_reales(movimientos)

    def calcular_gastos(self, movimientos: list[Any]) -> int:
        """Suma los movimientos de tipo gasto."""
        return self.metrics.gastos_reales(movimientos)

    def calcular_deuda_total(
        self,
        deudas: list[Any],
        pagos_por_deuda: dict[str, int] | None = None,
    ) -> int:
        """Suma el saldo actual de las deudas activas."""
        return self.metrics.deuda_actual(deudas, pagos_por_deuda)

    def calcular_gastos_imprevistos(
        self,
        movimientos: list[Any],
    ) -> int:
        """Suma los gastos marcados como imprevistos."""
        return self.metrics.gastos_imprevistos(movimientos)

    def calcular_gastos_por_categoria(
        self,
        movimientos: list[Any],
    ) -> dict[str, int]:
        """Agrupa los gastos por categoria."""
        return self.metrics.gastos_por_categoria(movimientos)
