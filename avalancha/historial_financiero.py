"""Monthly financial snapshots and historical trend queries."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from avalancha.finanzas import GestorDeudas, ResultadoRiesgo
from avalancha.models import CuentaFinanciera, EXPENSE, MonthlyBudget


class MesYaCerradoError(ValueError):
    """Raised when attempting to close an already closed month."""


class HistorialFinanciero:
    """Persist and query immutable monthly financial snapshots."""

    def __init__(
        self,
        path: str | Path = "data/historial_mensual.json",
    ) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def guardar_snapshot(self, snapshot: dict[str, Any]) -> Path:
        """Append one monthly snapshot, rejecting duplicate months."""
        month = str(snapshot.get("mes", "")).strip()
        if not month:
            raise ValueError("El snapshot necesita un mes.")
        history = self.leer_historial()
        if any(item.get("mes") == month for item in history):
            raise MesYaCerradoError("Este mes ya fue cerrado.")
        history.append(snapshot)
        history.sort(key=lambda item: str(item.get("mes", "")))
        self._write(history)
        return self.path

    def leer_historial(self) -> list[dict[str, Any]]:
        """Return monthly snapshots ordered from oldest to newest."""
        if not self.path.exists():
            return []
        try:
            with self.path.open("r", encoding="utf-8") as file:
                data = json.load(file)
        except (json.JSONDecodeError, OSError) as exc:
            raise ValueError(
                "No se pudo leer el historial mensual."
            ) from exc
        snapshots = data.get("snapshots", []) if isinstance(data, dict) else data
        if not isinstance(snapshots, list):
            raise ValueError("El historial mensual tiene un formato invalido.")
        return sorted(
            [item for item in snapshots if isinstance(item, dict)],
            key=lambda item: str(item.get("mes", "")),
        )

    def obtener_evolucion_deuda(self) -> list[tuple[str, int]]:
        """Return month and total-debt points."""
        return self._series("deuda_total")

    def obtener_evolucion_patrimonio(self) -> list[tuple[str, int]]:
        """Return month and net-worth points."""
        return self._series("patrimonio_neto")

    def obtener_evolucion_flujo(self) -> list[tuple[str, int]]:
        """Return month and free-cash-flow points."""
        return self._series("flujo_libre")

    def obtener_tendencia(self, field: str) -> str:
        """Return direction between the two latest monthly values."""
        series = self._series(field)
        if len(series) < 2:
            return "Sin datos"
        previous = series[-2][1]
        current = series[-1][1]
        if current == previous:
            return "Estable"
        if field == "deuda_total":
            return "Bajando" if current < previous else "Subiendo"
        return "Mejorando" if current > previous else "Empeorando"

    def mes_cerrado(self, month: str) -> bool:
        """Return whether a month already has a snapshot."""
        return any(
            item.get("mes") == month for item in self.leer_historial()
        )

    def _series(self, field: str) -> list[tuple[str, int]]:
        """Return a numeric historical series."""
        points = []
        for item in self.leer_historial():
            month = str(item.get("mes", "")).strip()
            if not month:
                continue
            try:
                value = int(item.get(field, 0))
            except (TypeError, ValueError):
                value = 0
            points.append((month, value))
        return points

    def _write(self, snapshots: list[dict[str, Any]]) -> None:
        """Write snapshots atomically through a temporary file."""
        temporary = self.path.with_suffix(".tmp")
        with temporary.open("w", encoding="utf-8") as file:
            json.dump(
                {"snapshots": snapshots},
                file,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            file.write("\n")
        temporary.replace(self.path)


class GeneradorSnapshot:
    """Build a complete monthly financial snapshot."""

    @staticmethod
    def crear(
        budget: MonthlyBudget,
        debt_manager: GestorDeudas,
        risk: ResultadoRiesgo,
        accounts: list[CuentaFinanciera],
    ) -> dict[str, Any]:
        """Devuelve una fotografía mensual compatible con JSON."""
        debt_summary = debt_manager.obtener_resumen_deuda()
        totals = budget.totals()
        categories = budget.category_actuals(EXPENSE)
        account_balance = sum(
            account.real_balance or 0
            for account in accounts
            if account.active and account.account_type != "tarjeta_credito"
        )
        return {
            "mes": budget.label,
            "deuda_total": debt_manager.deuda_total_actual(),
            "patrimonio_neto": debt_manager.patrimonio_neto(
                assets=account_balance
            ),
            "ingresos_reales": totals["income"],
            "gastos_reales": totals["expenses"],
            "flujo_libre": totals["balance"],
            "amortizacion_neta": debt_summary["amortizacion_neta"],
            "intereses_estimados": (
                debt_summary["interes_mensual_estimado"]
            ),
            "riesgo_financiero": risk.score,
            "saldo_cuentas": account_balance,
            "diferencia_conciliacion": sum(
                account.difference or 0
                for account in accounts
                if account.active and account.difference is not None
            ),
            "categorias": {
                name.lower(): amount
                for name, amount in sorted(categories.items())
            },
        }
