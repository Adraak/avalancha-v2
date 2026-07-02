"""Servicio visual para preparar datos del Dashboard V2."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any
import unicodedata

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
    detalle: str = ""


@dataclass(frozen=True, slots=True)
class ChartValue:
    """Valor simple para graficos de barras."""

    etiqueta: str
    monto: int
    porcentaje: float


@dataclass(frozen=True, slots=True)
class EvolutionPoint:
    """Punto mensual para graficos de evolucion financiera."""

    mes: str
    monto: int


@dataclass(frozen=True, slots=True)
class UnexpectedExpenseSummary:
    """Resumen de gastos imprevistos listo para analisis visual."""

    total: int
    cantidad: int
    porcentaje: float
    categoria_principal: str
    estado: str


@dataclass(frozen=True, slots=True)
class BudgetUsageValue:
    """Ejecucion visual de presupuesto por categoria."""

    categoria: str
    presupuesto: int
    gastado: int
    disponible: int
    porcentaje: float
    estado: str
    tipo: str = "variable"


@dataclass(frozen=True, slots=True)
class FixedPaymentValue:
    """Pago fijo mensual preparado para presentar cumplimiento."""

    nombre: str
    monto_esperado: int
    monto_pagado: int
    monto_pendiente: int
    estado: str
    porcentaje_pagado: float
    categoria: str
    descripcion: str = ""


@dataclass(frozen=True, slots=True)
class FixedPaymentsSummary:
    """Resumen de pagos fijos del mes."""

    items: list[FixedPaymentValue]
    total_fijo_esperado: int
    total_fijo_pagado: int
    total_fijo_pendiente: int
    cantidad_pagada: int
    cantidad_pendiente: int


@dataclass(frozen=True, slots=True)
class DashboardVisualData:
    """Agrupa todos los datos visuales del Dashboard."""

    tarjetas: list[DashboardCard]
    gastos_por_categoria: list[ChartValue]
    ingresos_vs_gastos: list[ChartValue]
    evolucion_flujo: list[EvolutionPoint]
    gastos_por_clase: list[ChartValue]
    presupuestos: list[BudgetUsageValue]
    pagos_fijos: FixedPaymentsSummary
    imprevistos: UnexpectedExpenseSummary
    alertas: list[FinancialAlert]


class DashboardVisualService:
    """Prepara resumenes y estados visuales sin depender de PySide6."""

    CATEGORIAS_FIJAS_INICIALES = {
        "arriendo",
        "chatgpt",
        "chat gpt",
        "spotify",
        "internet",
        "servicios",
        "fondo solidario",
        "tarjeta de credito",
        "dante",
    }

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
        unexpected_summary = self.obtener_resumen_imprevistos(
            budget.transactions,
        )

        return DashboardVisualData(
            tarjetas=self.obtener_tarjetas_dashboard(
                indicators,
                unexpected_summary,
            ),
            gastos_por_categoria=self.obtener_gastos_por_categoria(
                budget.transactions,
            ),
            ingresos_vs_gastos=self.obtener_ingresos_vs_gastos(indicators),
            evolucion_flujo=self.obtener_evolucion_flujo(year, month),
            gastos_por_clase=self.obtener_gastos_por_clase(
                budget.transactions,
            ),
            presupuestos=self.obtener_presupuesto_variable_vs_gasto(
                category_report,
            ),
            pagos_fijos=self.obtener_pagos_fijos_del_mes(
                category_report,
                budget.recurring_items,
            ),
            imprevistos=unexpected_summary,
            alertas=self.alert_service.generar_alertas(
                indicators,
                self._reporte_variable(category_report),
            ),
        )

    def obtener_tarjetas_dashboard(
        self,
        indicadores: Any,
        imprevistos: UnexpectedExpenseSummary | None = None,
    ) -> list[DashboardCard]:
        """Construye tarjetas semanticas para indicadores principales."""
        resumen_imprevistos = imprevistos or UnexpectedExpenseSummary(
            total=indicadores.gastos_imprevistos,
            cantidad=0,
            porcentaje=0.0,
            categoria_principal="Sin datos",
            estado=self._estado_imprevistos(
                indicadores.gastos_imprevistos,
                indicadores.gastos_reales,
            ),
        )
        return [
            DashboardCard(
                "Ingresos del mes",
                indicadores.ingresos_reales,
                "Saludable" if indicadores.ingresos_reales > 0 else "Sin datos",
            ),
            DashboardCard(
                "Gastos del mes",
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
                "Deuda total",
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
                "Imprevistos",
                resumen_imprevistos.total,
                resumen_imprevistos.estado,
                self._detalle_imprevistos(resumen_imprevistos),
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
        max_amount = max(
            abs(indicadores.ingresos_reales),
            abs(indicadores.gastos_reales),
            abs(indicadores.flujo_libre),
        )
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
            ChartValue(
                "Flujo libre",
                indicadores.flujo_libre,
                self._porcentaje_relativo(abs(indicadores.flujo_libre), max_amount),
            ),
        ]

    def obtener_evolucion_flujo(
        self,
        year: int,
        month: int,
    ) -> list[EvolutionPoint]:
        """Entrega los ultimos seis meses de flujo libre disponible."""
        current_label = f"{year:04d}-{month:02d}"
        labels = [
            label
            for label in sorted(self.repository.list_months())
            if label <= current_label
            and self._mes_tiene_movimientos(label)
        ][-6:]
        if len(labels) < 2:
            return []

        points = []
        accounts = self.repository.load_accounts()
        debts = self.repository.load_debts()
        for label in labels:
            item_year, item_month = (int(part) for part in label.split("-"))
            budget = self.repository.load(item_year, item_month)
            payments = self.repository.debt_payment_totals(budget)
            indicators = self.metrics.resumen_financiero(
                movimientos=budget.transactions,
                categorias=budget.categories,
                recurrentes=budget.recurring_items,
                deudas=debts,
                cuentas=accounts,
                pagos_por_deuda=payments,
            )
            points.append(EvolutionPoint(label, indicators.flujo_libre))
        return points

    def obtener_resumen_imprevistos(
        self,
        movimientos: list[Any],
    ) -> UnexpectedExpenseSummary:
        """Calcula total, cantidad y peso relativo de imprevistos."""
        gastos = [item for item in movimientos if self._es_gasto(item)]
        imprevistos = [
            item
            for item in gastos
            if bool(getattr(item, "is_unexpected", False))
        ]
        total_gastos = sum(int(getattr(item, "amount", 0)) for item in gastos)
        total_imprevistos = sum(
            int(getattr(item, "amount", 0)) for item in imprevistos
        )
        porcentaje = (
            round((total_imprevistos / total_gastos) * 100, 1)
            if total_gastos
            else 0.0
        )
        categorias = self.metrics.gastos_por_categoria(imprevistos)
        categoria_principal = "Sin datos"
        if categorias:
            categoria_principal = max(
                categorias.items(),
                key=lambda item: (item[1], item[0]),
            )[0]
        return UnexpectedExpenseSummary(
            total=total_imprevistos,
            cantidad=len(imprevistos),
            porcentaje=porcentaje,
            categoria_principal=categoria_principal,
            estado=self._estado_imprevistos(total_imprevistos, total_gastos),
        )

    def obtener_gastos_por_clase(
        self,
        movimientos: list[Any],
    ) -> list[ChartValue]:
        """Entrega gasto real agrupado por clase financiera."""
        clases = {"Normal": 0, "Recurrente": 0, "Imprevisto": 0}
        for movimiento in movimientos:
            if not self._es_gasto(movimiento):
                continue
            clase = self._clase_movimiento(movimiento)
            clases[clase] += int(getattr(movimiento, "amount", 0))

        total = sum(clases.values())
        return [
            ChartValue(
                etiqueta=clase,
                monto=monto,
                porcentaje=(
                    round((monto / total) * 100, 1) if total else 0.0
                ),
            )
            for clase, monto in clases.items()
        ]

    def obtener_presupuesto_vs_gasto(
        self,
        reporte_categorias: list[dict[str, Any]],
    ) -> list[BudgetUsageValue]:
        """Mantiene compatibilidad devolviendo solo presupuesto variable."""
        return self.obtener_presupuesto_variable_vs_gasto(reporte_categorias)

    def obtener_presupuesto_variable_vs_gasto(
        self,
        reporte_categorias: list[dict[str, Any]],
    ) -> list[BudgetUsageValue]:
        """Entrega ejecucion de presupuesto solo para categorias variables."""
        rows = []
        for item in self._reporte_variable(reporte_categorias):
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
                    tipo="variable",
                ),
            )
        return sorted(rows, key=lambda item: (-item.porcentaje, item.categoria))

    def obtener_pagos_fijos_del_mes(
        self,
        reporte_categorias: list[dict[str, Any]],
        recurrentes: list[Any] | None = None,
    ) -> FixedPaymentsSummary:
        """Entrega cumplimiento mensual de obligaciones fijas."""
        montos_recurrentes = self._montos_recurrentes_por_categoria(
            recurrentes or [],
        )
        descripciones = self._descripciones_recurrentes_por_categoria(
            recurrentes or [],
        )
        items: list[FixedPaymentValue] = []

        for item in self._reporte_fijo(reporte_categorias):
            categoria = str(item.get("name", "")).strip()
            nombre_visible = self._nombre_visible_pago_fijo(categoria)
            presupuestado = int(item.get("budgeted", 0) or 0)
            esperado = presupuestado or montos_recurrentes.get(categoria, 0)
            pagado = int(item.get("actual", 0) or 0)
            if esperado <= 0 and pagado <= 0:
                continue
            porcentaje = round((pagado / esperado) * 100, 1) if esperado else 0.0
            items.append(
                FixedPaymentValue(
                    nombre=nombre_visible,
                    monto_esperado=esperado,
                    monto_pagado=pagado,
                    monto_pendiente=max(esperado - pagado, 0),
                    estado=self._estado_pago_fijo(pagado, esperado),
                    porcentaje_pagado=porcentaje,
                    categoria=categoria,
                    descripcion=descripciones.get(categoria, ""),
                ),
            )

        items.sort(key=lambda value: (value.estado == "Pagado", value.nombre))
        total_esperado = sum(item.monto_esperado for item in items)
        total_pagado = sum(item.monto_pagado for item in items)
        total_pendiente = sum(
            max(item.monto_esperado - item.monto_pagado, 0)
            for item in items
        )
        return FixedPaymentsSummary(
            items=items,
            total_fijo_esperado=total_esperado,
            total_fijo_pagado=total_pagado,
            total_fijo_pendiente=total_pendiente,
            cantidad_pagada=sum(1 for item in items if item.estado == "Pagado"),
            cantidad_pendiente=sum(
                1 for item in items if item.estado != "Pagado"
            ),
        )

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
        if porcentaje >= 90:
            return "Crítico"
        if porcentaje >= 70:
            return "Atención"
        return "Bajo control"

    @staticmethod
    def _estado_pago_fijo(pagado: int, esperado: int) -> str:
        """Clasifica cumplimiento de un pago fijo mensual."""
        if esperado <= 0 and pagado > 0:
            return "Pagado"
        if esperado > 0 and pagado >= esperado:
            return "Pagado"
        if pagado > 0:
            return "Parcial"
        return "Pendiente"

    @staticmethod
    def _nombre_visible_pago_fijo(categoria: str) -> str:
        """Devuelve una etiqueta clara para obligaciones fijas."""
        normalized = DashboardVisualService._normalizar_clave_categoria(
            categoria,
        )
        if normalized in {"tarjeta demo", "tarjeta de credito demo"}:
            return "Pago tarjeta de crédito Demo"
        return categoria

    @staticmethod
    def _reporte_variable(
        reporte_categorias: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Filtra categorias variables desde el reporte financiero."""
        return [
            item
            for item in reporte_categorias
            if not DashboardVisualService._es_categoria_fija(item)
        ]

    @staticmethod
    def _reporte_fijo(
        reporte_categorias: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Filtra categorias fijas desde el reporte financiero."""
        return [
            item
            for item in reporte_categorias
            if DashboardVisualService._es_categoria_fija(item)
        ]

    @staticmethod
    def _es_categoria_fija(item: dict[str, Any]) -> bool:
        """Determina si una categoria es fija por modelo o regla inicial."""
        if bool(item.get("is_fixed", False)):
            return True
        name = DashboardVisualService._normalizar_clave_categoria(
            str(item.get("name", "")),
        )
        return name in DashboardVisualService.CATEGORIAS_FIJAS_INICIALES

    @staticmethod
    def _normalizar_clave_categoria(value: str) -> str:
        """Normaliza nombres para comparar reglas iniciales."""
        normalized = unicodedata.normalize("NFD", value.strip().casefold())
        return "".join(
            char
            for char in normalized
            if unicodedata.category(char) != "Mn"
        )

    def _montos_recurrentes_por_categoria(
        self,
        recurrentes: list[Any],
    ) -> dict[str, int]:
        """Suma montos recurrentes activos por categoria."""
        totals: dict[str, int] = {}
        for recurrente in recurrentes:
            if not self._es_recurrente_gasto_activo(recurrente):
                continue
            categoria = str(getattr(recurrente, "category", "")).strip()
            if not categoria:
                continue
            totals[categoria] = totals.get(categoria, 0) + int(
                getattr(recurrente, "amount", 0) or 0,
            )
        return totals

    def _descripciones_recurrentes_por_categoria(
        self,
        recurrentes: list[Any],
    ) -> dict[str, str]:
        """Conserva una descripcion sugerida por categoria fija."""
        descriptions: dict[str, str] = {}
        for recurrente in recurrentes:
            if not self._es_recurrente_gasto_activo(recurrente):
                continue
            categoria = str(getattr(recurrente, "category", "")).strip()
            descripcion = str(getattr(recurrente, "description", "")).strip()
            if categoria and descripcion and categoria not in descriptions:
                descriptions[categoria] = descripcion
        return descriptions

    @staticmethod
    def _es_recurrente_gasto_activo(recurrente: Any) -> bool:
        """Indica si un recurrente activo representa un gasto fijo."""
        return (
            str(getattr(recurrente, "transaction_type", "")).lower() == "gasto"
            and bool(getattr(recurrente, "active", True))
        )

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
    def _estado_imprevistos(imprevistos: int, gastos: int) -> str:
        """Clasifica el peso de imprevistos sobre el gasto mensual."""
        if imprevistos <= 0 or gastos <= 0:
            return "Bajo control"
        porcentaje = (imprevistos / gastos) * 100
        if porcentaje > 35:
            return "Crítico"
        if porcentaje > 20:
            return "Atención"
        return "Bajo control"

    @staticmethod
    def _detalle_imprevistos(
        resumen: UnexpectedExpenseSummary,
    ) -> str:
        """Construye texto breve para tarjeta de imprevistos."""
        if resumen.cantidad <= 0:
            return "Bajo control | 0 eventos"
        return (
            f"{resumen.cantidad} eventos | "
            f"{resumen.porcentaje:.1f}% del gasto | "
            f"{resumen.categoria_principal}"
        )

    @staticmethod
    def _es_gasto(movimiento: Any) -> bool:
        """Indica si el movimiento corresponde a un gasto."""
        return str(getattr(movimiento, "transaction_type", "")).lower() == "gasto"

    @staticmethod
    def _clase_movimiento(movimiento: Any) -> str:
        """Clasifica un movimiento priorizando imprevisto sobre recurrente."""
        if bool(getattr(movimiento, "is_unexpected", False)):
            return "Imprevisto"
        if getattr(movimiento, "recurring_id", None):
            return "Recurrente"
        return "Normal"

    def _mes_tiene_movimientos(self, label: str) -> bool:
        """Indica si un mes tiene movimientos registrados."""
        try:
            year, month = (int(part) for part in label.split("-"))
            budget = self.repository.load(year, month)
        except (OSError, ValueError):
            return False
        return bool(budget.transactions)

    @staticmethod
    def _porcentaje_relativo(amount: int, max_amount: int) -> float:
        """Calcula porcentaje relativo para graficos comparativos."""
        if max_amount <= 0:
            return 0.0
        return round((amount / max_amount) * 100, 1)
