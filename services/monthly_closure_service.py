"""Servicio de cierre mensual financiero."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

from avalancha.models import validate_month
from avalancha.storage import BudgetRepository
from core.models.monthly_closure import (
    MONTHLY_CLOSURE_CLOSED,
    MONTHLY_CLOSURE_OPEN,
    MONTHLY_CLOSURE_PENDING,
    MonthlyClosure,
)


class MonthlyClosureService:
    """Administra estados y checklist de cierre mensual por perfil."""

    WARNING_CLOSED_MONTH = (
        "Este mes esta cerrado. Modificarlo puede alterar reportes y "
        "metricas ya revisadas."
    )

    def __init__(
        self,
        data_dir: str | Path = "data",
        repository: BudgetRepository | None = None,
    ) -> None:
        """Inicializa el servicio usando el repositorio del perfil."""
        self.repository = repository or BudgetRepository(data_dir)

    def obtener_estado_mes(self, year: int, month: int) -> str:
        """Devuelve estado operativo del mes."""
        closure = self._find_closure(year, month)
        if closure is not None:
            return closure.status
        return self._estado_inicial(year, month)

    def obtener_cierre(self, year: int, month: int) -> MonthlyClosure:
        """Obtiene cierre existente o uno temporal sin persistirlo."""
        closure = self._find_closure(year, month)
        if closure is not None:
            return closure
        return MonthlyClosure(
            year=year,
            month=month,
            status=self._estado_inicial(year, month),
        )

    def obtener_o_crear_cierre(self, year: int, month: int) -> MonthlyClosure:
        """Obtiene o crea el cierre del mes solicitado."""
        validate_month(year, month)
        closures = self.repository.load_monthly_closures()
        for closure in closures:
            if closure.year == year and closure.month == month:
                return closure

        closure = MonthlyClosure(
            year=year,
            month=month,
            status=self._estado_inicial(year, month),
        )
        closures.append(closure)
        self._save(closures)
        return closure

    def marcar_movimientos_revisados(
        self,
        year: int,
        month: int,
        value: bool = True,
    ) -> MonthlyClosure:
        """Marca revision de movimientos."""
        return self._update_flag(year, month, "movements_reviewed", value)

    def marcar_cuentas_conciliadas(
        self,
        year: int,
        month: int,
        value: bool = True,
    ) -> MonthlyClosure:
        """Marca conciliacion de cuentas."""
        return self._update_flag(year, month, "accounts_reconciled", value)

    def marcar_deudas_revisadas(
        self,
        year: int,
        month: int,
        value: bool = True,
    ) -> MonthlyClosure:
        """Marca revision de deudas."""
        return self._update_flag(year, month, "debts_reviewed", value)

    def marcar_presupuestos_revisados(
        self,
        year: int,
        month: int,
        value: bool = True,
    ) -> MonthlyClosure:
        """Marca revision de presupuestos."""
        return self._update_flag(year, month, "budgets_reviewed", value)

    def marcar_reporte_generado(
        self,
        year: int,
        month: int,
        value: bool = True,
    ) -> MonthlyClosure:
        """Marca reporte mensual generado."""
        return self._update_flag(year, month, "report_generated", value)

    def cerrar_mes(self, year: int, month: int) -> MonthlyClosure:
        """Cierra el mes si el checklist esta completo."""
        closures = self.repository.load_monthly_closures()
        index, closure = self._get_or_create_in_list(closures, year, month)
        missing = closure.faltantes()
        if missing:
            raise ValueError(
                "No se puede cerrar el mes. Faltan: "
                + ", ".join(missing)
                + "."
            )
        closure.close()
        closures[index] = closure
        self._save(closures)
        return closure

    def reabrir_mes(self, year: int, month: int) -> MonthlyClosure:
        """Reabre el mes para permitir ajustes controlados."""
        closures = self.repository.load_monthly_closures()
        index, closure = self._get_or_create_in_list(closures, year, month)
        closure.reopen()
        closures[index] = closure
        self._save(closures)
        return closure

    def esta_mes_cerrado(self, year: int, month: int) -> bool:
        """Indica si el mes esta cerrado."""
        return self.obtener_estado_mes(year, month) == MONTHLY_CLOSURE_CLOSED

    def obtener_meses_pendientes(
        self,
        reference_date: date | None = None,
    ) -> list[MonthlyClosure]:
        """Devuelve meses anteriores disponibles y no cerrados."""
        reference = reference_date or date.today()
        labels = set(self.repository.list_months())
        labels.update(item.label for item in self.repository.load_monthly_closures())
        pending = []
        for label in sorted(labels):
            year, month = self._parse_label(label)
            if (year, month) >= (reference.year, reference.month):
                continue
            closure = self.obtener_cierre(year, month)
            if closure.status != MONTHLY_CLOSURE_CLOSED:
                if closure.status != MONTHLY_CLOSURE_PENDING:
                    closure.status = MONTHLY_CLOSURE_PENDING
                pending.append(closure)
        return pending

    def puntos_faltantes(self, year: int, month: int) -> list[str]:
        """Devuelve checklist pendiente para cerrar el mes."""
        return self.obtener_o_crear_cierre(year, month).faltantes()

    def advertencia_modificacion_mes(
        self,
        year: int,
        month: int,
    ) -> str | None:
        """Devuelve advertencia si el mes esta cerrado."""
        if self.esta_mes_cerrado(year, month):
            return self.WARNING_CLOSED_MONTH
        return None

    def advertencia_modificacion_fecha(
        self,
        value: date | str,
    ) -> str | None:
        """Devuelve advertencia si la fecha pertenece a un mes cerrado."""
        current = self._parse_date(value)
        return self.advertencia_modificacion_mes(current.year, current.month)

    def _update_flag(
        self,
        year: int,
        month: int,
        field_name: str,
        value: bool,
    ) -> MonthlyClosure:
        """Actualiza un punto del checklist."""
        closures = self.repository.load_monthly_closures()
        index, closure = self._get_or_create_in_list(closures, year, month)
        setattr(closure, field_name, bool(value))
        if closure.status != MONTHLY_CLOSURE_CLOSED:
            closure.status = self._estado_inicial(year, month)
        closure.touch()
        closures[index] = closure
        self._save(closures)
        return closure

    def _set_status(
        self,
        year: int,
        month: int,
        status: str,
    ) -> MonthlyClosure:
        """Actualiza solo el estado operativo."""
        closures = self.repository.load_monthly_closures()
        index, closure = self._get_or_create_in_list(closures, year, month)
        closure.status = status
        closure.touch()
        closures[index] = closure
        self._save(closures)
        return closure

    def _find_closure(
        self,
        year: int,
        month: int,
    ) -> MonthlyClosure | None:
        """Busca un cierre mensual sin crearlo."""
        validate_month(year, month)
        for closure in self.repository.load_monthly_closures():
            if closure.year == year and closure.month == month:
                return closure
        return None

    def _get_or_create_in_list(
        self,
        closures: list[MonthlyClosure],
        year: int,
        month: int,
    ) -> tuple[int, MonthlyClosure]:
        """Obtiene un cierre dentro de una lista mutable."""
        validate_month(year, month)
        for index, closure in enumerate(closures):
            if closure.year == year and closure.month == month:
                return index, closure
        closure = MonthlyClosure(
            year=year,
            month=month,
            status=self._estado_inicial(year, month),
        )
        closures.append(closure)
        return len(closures) - 1, closure

    @staticmethod
    def _estado_inicial(year: int, month: int) -> str:
        """Calcula estado inicial segun mes calendario."""
        today = date.today()
        if (year, month) < (today.year, today.month):
            return MONTHLY_CLOSURE_PENDING
        return MONTHLY_CLOSURE_OPEN

    @staticmethod
    def _parse_label(label: str) -> tuple[int, int]:
        """Convierte etiqueta YYYY-MM a anio y mes."""
        year_text, month_text = label.split("-", maxsplit=1)
        year = int(year_text)
        month = int(month_text)
        validate_month(year, month)
        return year, month

    @staticmethod
    def _parse_date(value: date | str) -> date:
        """Convierte fecha ISO o dd-mm-aaaa a date."""
        if isinstance(value, date):
            return value
        text = str(value).strip()
        for fmt in ("%Y-%m-%d", "%d-%m-%Y"):
            try:
                return datetime.strptime(text, fmt).date()
            except ValueError:
                continue
        raise ValueError("La fecha no es valida.")

    def _save(self, closures: list[MonthlyClosure]) -> None:
        """Persiste cierres ordenados por mes."""
        ordered = sorted(closures, key=lambda item: (item.year, item.month))
        self.repository.save_monthly_closures(ordered)
