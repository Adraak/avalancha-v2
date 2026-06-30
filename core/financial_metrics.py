"""Calculos financieros puros para Avalancha V2."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


class MovimientoLike(Protocol):
    """Contrato minimo para leer un movimiento financiero."""

    transaction_type: str
    category: str
    amount: int
    is_unexpected: bool
    recurring_id: str | None
    debt_id: str | None
    account_id: str | None


class CategoriaLike(Protocol):
    """Contrato minimo para leer una categoria presupuestada."""

    name: str
    transaction_type: str
    budgeted_amount: int
    is_fixed: bool
    alert_threshold: int


class RecurrenteLike(Protocol):
    """Contrato minimo para leer una regla recurrente."""

    transaction_type: str
    category: str
    amount: int
    active: bool
    recurring_id: str


class DeudaLike(Protocol):
    """Contrato minimo para leer una deuda."""

    debt_id: str
    category: str
    current_balance: int
    previous_month_balance: int
    current_monthly_payment: int
    monthly_interest_rate: float | int | str | None
    active: bool


class CuentaLike(Protocol):
    """Contrato minimo para leer una cuenta financiera."""

    account_id: str
    account_type: str
    initial_balance: int
    real_balance: int | None
    registered_balance: int
    active: bool
    reconciliation_date: str | None


@dataclass(slots=True)
class ResumenFinancieroCalculado:
    """Agrupa los indicadores principales calculados para un mes."""

    ingresos_reales: int
    gastos_reales: int
    flujo_libre: int
    resultado_esperado: int
    deuda_actual: int
    variacion_deuda: int
    pago_mensual_deuda: int
    interes_mensual_estimado: int
    amortizacion_neta: int
    patrimonio_neto: int
    activos_liquidos: int
    pasivos_totales: int
    gastos_imprevistos: int
    principales_gastos: list[dict[str, Any]]
    categorias_sobrepasadas: list[str]
    categorias_sin_presupuesto: list[str]


class FinancialMetrics:
    """Calcula indicadores financieros sin depender de UI ni persistencia."""

    @staticmethod
    def ingresos_reales(movimientos: list[MovimientoLike]) -> int:
        """Suma todos los ingresos reales del mes."""
        return sum(
            item.amount
            for item in movimientos
            if item.transaction_type == "ingreso"
        )

    @staticmethod
    def gastos_reales(movimientos: list[MovimientoLike]) -> int:
        """Suma todos los gastos reales del mes."""
        return sum(
            item.amount
            for item in movimientos
            if item.transaction_type == "gasto"
        )

    def flujo_libre(self, movimientos: list[MovimientoLike]) -> int:
        """Calcula ingresos menos gastos reales."""
        return self.ingresos_reales(movimientos) - self.gastos_reales(
            movimientos,
        )

    def gastos_imprevistos(self, movimientos: list[MovimientoLike]) -> int:
        """Suma gastos marcados como imprevistos."""
        return sum(
            item.amount
            for item in movimientos
            if item.transaction_type == "gasto" and item.is_unexpected
        )

    def gastos_por_categoria(
        self,
        movimientos: list[MovimientoLike],
    ) -> dict[str, int]:
        """Agrupa gastos reales por categoria."""
        totales: dict[str, int] = {}
        for item in movimientos:
            if item.transaction_type != "gasto":
                continue
            totales[item.category] = totales.get(item.category, 0) + item.amount
        return totales

    def principales_gastos(
        self,
        movimientos: list[MovimientoLike],
        limite: int = 5,
    ) -> list[dict[str, Any]]:
        """Devuelve las categorias de gasto con mayor monto real."""
        ranking = [
            {"categoria": categoria, "monto": monto}
            for categoria, monto in self.gastos_por_categoria(
                movimientos,
            ).items()
            if monto > 0
        ]
        ranking.sort(
            key=lambda item: (-item["monto"], item["categoria"].lower()),
        )
        return ranking[:max(limite, 0)]

    def recurrentes_pendientes(
        self,
        movimientos: list[MovimientoLike],
        recurrentes: list[RecurrenteLike],
    ) -> int:
        """Calcula gastos recurrentes activos aun no registrados."""
        ids_registrados = {
            item.recurring_id for item in movimientos if item.recurring_id
        }
        return sum(
            item.amount
            for item in recurrentes
            if (
                item.active
                and item.transaction_type == "gasto"
                and item.recurring_id not in ids_registrados
            )
        )

    def resultado_esperado(
        self,
        movimientos: list[MovimientoLike],
        recurrentes: list[RecurrenteLike],
    ) -> int:
        """Calcula el resultado esperado al cierre del mes."""
        return (
            self.ingresos_reales(movimientos)
            - self.gastos_reales(movimientos)
            - self.recurrentes_pendientes(movimientos, recurrentes)
        )

    def categorias_sobrepasadas(
        self,
        movimientos: list[MovimientoLike],
        categorias: list[CategoriaLike],
        recurrentes: list[RecurrenteLike],
    ) -> list[str]:
        """Lista categorias variables que superaron su presupuesto."""
        return [
            fila["name"]
            for fila in self.reporte_categorias(
                movimientos,
                categorias,
                recurrentes,
            )
            if fila["status"] == "sobrepasado"
        ]

    def categorias_sin_presupuesto(
        self,
        movimientos: list[MovimientoLike],
        categorias: list[CategoriaLike],
        recurrentes: list[RecurrenteLike],
    ) -> list[str]:
        """Lista categorias con gasto real y presupuesto cero."""
        return [
            fila["name"]
            for fila in self.reporte_categorias(
                movimientos,
                categorias,
                recurrentes,
            )
            if fila["status"] == "sin presupuesto"
        ]

    def reporte_categorias(
        self,
        movimientos: list[MovimientoLike],
        categorias: list[CategoriaLike],
        recurrentes: list[RecurrenteLike],
    ) -> list[dict[str, Any]]:
        """Calcula estado presupuesto versus real por categoria."""
        reales = self.gastos_por_categoria(movimientos)
        categorias_recurrentes = {
            item.category
            for item in recurrentes
            if item.transaction_type == "gasto" and item.active
        }
        filas = []
        for categoria in sorted(
            categorias,
            key=lambda item: (item.transaction_type, item.name.lower()),
        ):
            if categoria.transaction_type != "gasto":
                continue
            real = reales.get(categoria.name, 0)
            presupuesto = categoria.budgeted_amount
            uso = round((real / presupuesto) * 100, 1) if presupuesto else 0.0
            tiene_recurrente = categoria.name in categorias_recurrentes
            control_fijo = categoria.is_fixed or tiene_recurrente
            estado = self._estado_categoria(
                real,
                presupuesto,
                uso,
                categoria.alert_threshold,
                control_fijo,
                tiene_recurrente,
            )
            filas.append(
                {
                    "name": categoria.name,
                    "budgeted": presupuesto,
                    "actual": real,
                    "remaining": presupuesto - real,
                    "usage": uso,
                    "status": estado,
                    "is_fixed": control_fijo,
                }
            )
        return filas

    @staticmethod
    def _estado_categoria(
        real: int,
        presupuesto: int,
        uso: float,
        alerta: int,
        control_fijo: bool,
        tiene_recurrente: bool,
    ) -> str:
        """Determina el estado de una categoria de gasto."""
        if control_fijo:
            if presupuesto <= 0 and real > 0:
                return "sin presupuesto"
            if presupuesto <= 0:
                return "ok"
            if real == 0 and tiene_recurrente:
                return "programado"
            if real == 0:
                return "pendiente"
            if real == presupuesto:
                return "pagado"
            if real > presupuesto:
                return "sobrepasado"
            return "diferencia"
        if presupuesto and real > presupuesto:
            return "sobrepasado"
        if presupuesto and uso >= alerta:
            return "alerta"
        if not presupuesto and real > 0:
            return "sin presupuesto"
        return "ok"

    def deuda_actual(
        self,
        deudas: list[DeudaLike],
        pagos_por_deuda: dict[str, int] | None = None,
    ) -> int:
        """Calcula deuda activa descontando pagos vinculados."""
        pagos = pagos_por_deuda or {}
        return sum(
            max(deuda.current_balance - pagos.get(deuda.debt_id, 0), 0)
            for deuda in deudas
            if deuda.active
        )

    def variacion_deuda(
        self,
        deudas: list[DeudaLike],
        pagos_por_deuda: dict[str, int] | None = None,
    ) -> int:
        """Calcula saldo anterior menos deuda actual."""
        anterior = sum(
            deuda.previous_month_balance
            for deuda in deudas
            if deuda.active
        )
        return anterior - self.deuda_actual(deudas, pagos_por_deuda)

    def pago_mensual_deuda(self, deudas: list[DeudaLike]) -> int:
        """Suma pagos mensuales planificados de deudas activas."""
        return sum(
            deuda.current_monthly_payment
            for deuda in deudas
            if deuda.active
        )

    def interes_mensual_estimado(
        self,
        deudas: list[DeudaLike],
        pagos_por_deuda: dict[str, int] | None = None,
    ) -> int:
        """Estima intereses mensuales de deudas activas."""
        pagos = pagos_por_deuda or {}
        total = 0
        for deuda in deudas:
            if not deuda.active:
                continue
            tasa = self._normalizar_tasa_mensual(deuda.monthly_interest_rate)
            saldo = max(deuda.current_balance - pagos.get(deuda.debt_id, 0), 0)
            total += round(saldo * tasa)
        return total

    def amortizacion_neta(
        self,
        deudas: list[DeudaLike],
        pagos_por_deuda: dict[str, int] | None = None,
    ) -> int:
        """Calcula pago mensual menos intereses estimados."""
        return self.pago_mensual_deuda(
            deudas,
        ) - self.interes_mensual_estimado(deudas, pagos_por_deuda)

    def activos_liquidos(self, cuentas: list[CuentaLike]) -> int:
        """Suma saldos reales positivos en cuentas no crediticias."""
        return sum(
            cuenta.real_balance
            for cuenta in cuentas
            if (
                cuenta.active
                and cuenta.account_type != "tarjeta_credito"
                and cuenta.real_balance is not None
                and cuenta.real_balance > 0
            )
        )

    def pasivos_totales(
        self,
        deudas: list[DeudaLike],
        pagos_por_deuda: dict[str, int] | None = None,
    ) -> int:
        """Devuelve el total de pasivos financieros activos."""
        return self.deuda_actual(deudas, pagos_por_deuda)

    def patrimonio_neto(
        self,
        cuentas: list[CuentaLike],
        deudas: list[DeudaLike],
        pagos_por_deuda: dict[str, int] | None = None,
    ) -> int:
        """Calcula activos liquidos menos pasivos totales."""
        return self.activos_liquidos(cuentas) - self.pasivos_totales(
            deudas,
            pagos_por_deuda,
        )

    def resumen_financiero(
        self,
        movimientos: list[MovimientoLike],
        categorias: list[CategoriaLike],
        recurrentes: list[RecurrenteLike],
        deudas: list[DeudaLike],
        cuentas: list[CuentaLike],
        pagos_por_deuda: dict[str, int] | None = None,
    ) -> ResumenFinancieroCalculado:
        """Calcula el conjunto principal de indicadores del mes."""
        deuda = self.deuda_actual(deudas, pagos_por_deuda)
        activos = self.activos_liquidos(cuentas)
        pasivos = self.pasivos_totales(deudas, pagos_por_deuda)
        return ResumenFinancieroCalculado(
            ingresos_reales=self.ingresos_reales(movimientos),
            gastos_reales=self.gastos_reales(movimientos),
            flujo_libre=self.flujo_libre(movimientos),
            resultado_esperado=self.resultado_esperado(
                movimientos,
                recurrentes,
            ),
            deuda_actual=deuda,
            variacion_deuda=self.variacion_deuda(deudas, pagos_por_deuda),
            pago_mensual_deuda=self.pago_mensual_deuda(deudas),
            interes_mensual_estimado=self.interes_mensual_estimado(
                deudas,
                pagos_por_deuda,
            ),
            amortizacion_neta=self.amortizacion_neta(
                deudas,
                pagos_por_deuda,
            ),
            patrimonio_neto=activos - pasivos,
            activos_liquidos=activos,
            pasivos_totales=pasivos,
            gastos_imprevistos=self.gastos_imprevistos(movimientos),
            principales_gastos=self.principales_gastos(movimientos),
            categorias_sobrepasadas=self.categorias_sobrepasadas(
                movimientos,
                categorias,
                recurrentes,
            ),
            categorias_sin_presupuesto=self.categorias_sin_presupuesto(
                movimientos,
                categorias,
                recurrentes,
            ),
        )

    @staticmethod
    def _normalizar_tasa_mensual(tasa: float | int | str | None) -> float:
        """Normaliza una tasa mensual a valor decimal."""
        if tasa in ("", None):
            return 0.0
        try:
            valor = float(tasa)
        except (TypeError, ValueError):
            return 0.0
        if valor <= 0:
            return 0.0
        if valor > 1:
            return valor / 100
        return valor
