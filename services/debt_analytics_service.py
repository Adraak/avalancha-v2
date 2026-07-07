"""Analisis temporal de deudas para Avalancha V2."""

from __future__ import annotations

from calendar import monthrange
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from avalancha.models import DebtPayment, DebtSnapshot
from avalancha.storage import BudgetRepository
from services.debt_service import DebtService


@dataclass(frozen=True)
class PuntoEvolucionDeuda:
    """Representa un punto historico de saldo de una deuda."""

    fecha: date
    deuda_id: str
    deuda: str
    saldo: int
    origen: str


@dataclass(frozen=True)
class PuntoDeudaTotal:
    """Representa el saldo total reconstruido para una fecha."""

    fecha: date
    saldo_total: int
    cantidad_deudas: int


@dataclass(frozen=True)
class PagoMensualDeuda:
    """Resume pagos de deuda agrupados por mes."""

    year: int
    month: int
    total_pagado: int
    cantidad_pagos: int
    desglose_por_deuda: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class ResumenTemporalDeuda:
    """Resume la situacion temporal de las deudas."""

    deuda_total_actual: int
    pagado_mes_actual: int
    variacion_deuda_mes: int
    tendencia: str


@dataclass(frozen=True)
class PagoRecienteDeuda:
    """Representa un pago reciente con contexto de deuda y cuenta."""

    fecha: date
    deuda_id: str
    deuda: str
    cuenta_id: str
    cuenta: str
    monto: int
    saldo_antes: int
    saldo_despues: int
    nota: str


class DebtAnalyticsService:
    """Calcula tendencias de deudas usando pagos y snapshots reales."""

    STABLE_TOLERANCE = 1_000

    def __init__(
        self,
        data_dir: str | Path = "data",
        repository: BudgetRepository | None = None,
        debt_service: DebtService | None = None,
    ) -> None:
        """Inicializa dependencias de analisis sin conocer la interfaz."""
        self.repository = repository or BudgetRepository(data_dir)
        self.debt_service = debt_service or DebtService(
            data_dir=data_dir,
            repository=self.repository,
        )

    def obtener_evolucion_deuda(
        self,
        debt_id: str | None = None,
    ) -> list[PuntoEvolucionDeuda]:
        """Devuelve puntos historicos de saldo por deuda desde snapshots."""
        debt_names = self._mapa_deudas()
        points = [
            PuntoEvolucionDeuda(
                fecha=self._parse_date(snapshot.tx_date),
                deuda_id=snapshot.debt_id,
                deuda=debt_names.get(snapshot.debt_id, "Deuda sin nombre"),
                saldo=snapshot.balance,
                origen=snapshot.source,
            )
            for snapshot in self.debt_service.obtener_snapshots_deuda(debt_id)
        ]
        return sorted(
            points,
            key=lambda point: (point.fecha, point.deuda.casefold()),
        )

    def obtener_deuda_total_en_tiempo(self) -> list[PuntoDeudaTotal]:
        """Reconstruye deuda total por fecha usando snapshots disponibles."""
        snapshots = self.debt_service.obtener_snapshots_deuda()
        if len(snapshots) < 2:
            return []

        grouped = self._agrupar_snapshots_por_fecha(snapshots)
        latest_by_debt: dict[str, int] = {}
        points: list[PuntoDeudaTotal] = []

        for tx_date in sorted(grouped):
            for snapshot in grouped[tx_date]:
                latest_by_debt[snapshot.debt_id] = snapshot.balance
            if not latest_by_debt:
                continue
            points.append(
                PuntoDeudaTotal(
                    fecha=tx_date,
                    saldo_total=sum(latest_by_debt.values()),
                    cantidad_deudas=len(latest_by_debt),
                )
            )
        return points

    def obtener_pagos_mensuales(
        self,
        year: int | None = None,
    ) -> list[PagoMensualDeuda]:
        """Agrupa pagos reales de deuda por mes calendario."""
        grouped: dict[tuple[int, int], list[DebtPayment]] = defaultdict(list)
        for payment in self.debt_service.obtener_pagos_deuda():
            tx_date = self._parse_date(payment.tx_date)
            if year is not None and tx_date.year != year:
                continue
            grouped[(tx_date.year, tx_date.month)].append(payment)

        results: list[PagoMensualDeuda] = []
        for (tx_year, tx_month), payments in sorted(grouped.items()):
            by_debt: dict[str, int] = defaultdict(int)
            for payment in payments:
                by_debt[payment.debt_id] += payment.amount
            results.append(
                PagoMensualDeuda(
                    year=tx_year,
                    month=tx_month,
                    total_pagado=sum(payment.amount for payment in payments),
                    cantidad_pagos=len(payments),
                    desglose_por_deuda=dict(sorted(by_debt.items())),
                )
            )
        return results

    def obtener_resumen_temporal_deudas(
        self,
        year: int | None = None,
        month: int | None = None,
    ) -> ResumenTemporalDeuda:
        """Calcula resumen actual y tendencia frente a dato comparable."""
        target = self._resolve_target_month(year, month)
        current_total = sum(
            debt.current_balance
            for debt in self.debt_service.obtener_deudas_activas()
        )
        paid_month = self._calcular_pagado_mes(target.year, target.month)
        previous_total, comparable_total = self._obtener_totales_comparables(
            target.year,
            target.month,
        )

        if previous_total is None or comparable_total is None:
            return ResumenTemporalDeuda(
                deuda_total_actual=current_total,
                pagado_mes_actual=paid_month,
                variacion_deuda_mes=0,
                tendencia="sin_datos",
            )

        variation = previous_total - comparable_total
        return ResumenTemporalDeuda(
            deuda_total_actual=current_total,
            pagado_mes_actual=paid_month,
            variacion_deuda_mes=variation,
            tendencia=self._clasificar_tendencia(variation),
        )

    def obtener_pagos_recientes(
        self,
        limit: int = 10,
    ) -> list[PagoRecienteDeuda]:
        """Devuelve pagos recientes ordenados desde el mas nuevo."""
        if limit <= 0:
            return []

        debt_names = self._mapa_deudas()
        account_names = self._mapa_cuentas()
        payments = sorted(
            self.debt_service.obtener_pagos_deuda(),
            key=lambda item: (item.tx_date, item.created_at, item.payment_id),
            reverse=True,
        )
        return [
            PagoRecienteDeuda(
                fecha=self._parse_date(payment.tx_date),
                deuda_id=payment.debt_id,
                deuda=debt_names.get(payment.debt_id, "Deuda sin nombre"),
                cuenta_id=payment.account_id,
                cuenta=account_names.get(payment.account_id, "Cuenta sin nombre"),
                monto=payment.amount,
                saldo_antes=payment.balance_before,
                saldo_despues=payment.balance_after,
                nota=payment.note,
            )
            for payment in payments[:limit]
        ]

    def _calcular_pagado_mes(self, year: int, month: int) -> int:
        """Suma pagos reales registrados en el mes solicitado."""
        total = 0
        for payment in self.debt_service.obtener_pagos_deuda():
            tx_date = self._parse_date(payment.tx_date)
            if tx_date.year == year and tx_date.month == month:
                total += payment.amount
        return total

    def _obtener_totales_comparables(
        self,
        year: int,
        month: int,
    ) -> tuple[int | None, int | None]:
        """Obtiene total anterior y total del mes para comparar tendencia."""
        points = self.obtener_deuda_total_en_tiempo()
        if len(points) < 2:
            return None, None

        month_start = date(year, month, 1)
        month_end = self._month_end(year, month)
        previous_points = [
            point for point in points if point.fecha < month_start
        ]
        month_points = [
            point
            for point in points
            if month_start <= point.fecha <= month_end
        ]
        if not previous_points or not month_points:
            return None, None

        previous_total = previous_points[-1].saldo_total
        comparable_total = month_points[-1].saldo_total
        return previous_total, comparable_total

    def _mapa_deudas(self) -> dict[str, str]:
        """Devuelve nombres de deudas por identificador."""
        return {
            debt.debt_id: debt.name
            for debt in self.debt_service.obtener_deudas()
        }

    def _mapa_cuentas(self) -> dict[str, str]:
        """Devuelve nombres de cuentas por identificador."""
        return {
            account.account_id: account.name
            for account in self.repository.load_accounts()
        }

    @staticmethod
    def _agrupar_snapshots_por_fecha(
        snapshots: list[DebtSnapshot],
    ) -> dict[date, list[DebtSnapshot]]:
        """Agrupa snapshots por fecha efectiva de transaccion."""
        grouped: dict[date, list[DebtSnapshot]] = defaultdict(list)
        for snapshot in snapshots:
            grouped[date.fromisoformat(snapshot.tx_date)].append(snapshot)
        return grouped

    @staticmethod
    def _resolve_target_month(
        year: int | None,
        month: int | None,
    ) -> date:
        """Resuelve mes objetivo usando la fecha actual si faltan datos."""
        today = date.today()
        resolved_year = year or today.year
        resolved_month = month or today.month
        if not 1 <= resolved_month <= 12:
            raise ValueError("El mes debe estar entre 1 y 12.")
        return date(resolved_year, resolved_month, 1)

    @staticmethod
    def _clasificar_tendencia(variation: int) -> str:
        """Clasifica la tendencia segun variacion de deuda."""
        if abs(variation) <= DebtAnalyticsService.STABLE_TOLERANCE:
            return "estable"
        if variation > 0:
            return "bajando"
        return "subiendo"

    @staticmethod
    def _month_end(year: int, month: int) -> date:
        """Devuelve ultimo dia del mes indicado."""
        return date(year, month, monthrange(year, month)[1])

    @staticmethod
    def _parse_date(value: str) -> date:
        """Convierte fecha ISO a date."""
        return date.fromisoformat(value)
