"""Modelo de cierre mensual financiero."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any

from avalancha.models import new_id, now_iso, validate_month


MONTHLY_CLOSURE_OPEN = "abierto"
MONTHLY_CLOSURE_PENDING = "pendiente_cierre"
MONTHLY_CLOSURE_CLOSED = "cerrado"
MONTHLY_CLOSURE_STATUSES = {
    MONTHLY_CLOSURE_OPEN,
    MONTHLY_CLOSURE_PENDING,
    MONTHLY_CLOSURE_CLOSED,
}


@dataclass(slots=True)
class MonthlyClosure:
    """Representa el estado operativo de cierre de un mes."""

    year: int
    month: int
    status: str = MONTHLY_CLOSURE_OPEN
    closed_at: str | None = None
    report_generated: bool = False
    movements_reviewed: bool = False
    accounts_reconciled: bool = False
    debts_reviewed: bool = False
    budgets_reviewed: bool = False
    notes: str = ""
    closure_id: str = field(default_factory=new_id)
    created_at: str = field(default_factory=now_iso)
    updated_at: str = field(default_factory=now_iso)

    def __post_init__(self) -> None:
        """Normaliza y valida el cierre mensual."""
        self.year = int(self.year)
        self.month = int(self.month)
        validate_month(self.year, self.month)
        self.status = str(self.status).strip().lower() or MONTHLY_CLOSURE_OPEN
        if self.status not in MONTHLY_CLOSURE_STATUSES:
            raise ValueError("El estado de cierre mensual no es valido.")
        self.notes = self.notes.strip()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MonthlyClosure":
        """Crea un cierre mensual desde datos JSON."""
        return cls(
            closure_id=data.get("closure_id", data.get("id", new_id())),
            year=int(data["year"]),
            month=int(data["month"]),
            status=data.get("status", MONTHLY_CLOSURE_OPEN),
            closed_at=data.get("closed_at"),
            report_generated=bool(data.get("report_generated", False)),
            movements_reviewed=bool(data.get("movements_reviewed", False)),
            accounts_reconciled=bool(data.get("accounts_reconciled", False)),
            debts_reviewed=bool(data.get("debts_reviewed", False)),
            budgets_reviewed=bool(data.get("budgets_reviewed", False)),
            notes=data.get("notes", ""),
            created_at=data.get("created_at", now_iso()),
            updated_at=data.get("updated_at", now_iso()),
        )

    def to_dict(self) -> dict[str, Any]:
        """Devuelve datos compatibles con JSON."""
        data = asdict(self)
        data["id"] = self.closure_id
        return data

    @property
    def label(self) -> str:
        """Devuelve etiqueta YYYY-MM del cierre."""
        return f"{self.year:04d}-{self.month:02d}"

    @property
    def checklist_completo(self) -> bool:
        """Indica si todos los puntos de cierre estan revisados."""
        return all(
            [
                self.movements_reviewed,
                self.accounts_reconciled,
                self.debts_reviewed,
                self.budgets_reviewed,
                self.report_generated,
            ]
        )

    def faltantes(self) -> list[str]:
        """Devuelve nombres de puntos pendientes para cerrar."""
        missing = []
        if not self.movements_reviewed:
            missing.append("Movimientos revisados")
        if not self.accounts_reconciled:
            missing.append("Cuentas conciliadas")
        if not self.debts_reviewed:
            missing.append("Deudas revisadas")
        if not self.budgets_reviewed:
            missing.append("Presupuestos revisados")
        if not self.report_generated:
            missing.append("Reporte generado")
        return missing

    def touch(self) -> None:
        """Actualiza la fecha de modificacion del cierre."""
        self.updated_at = now_iso()

    def close(self) -> None:
        """Marca el cierre como cerrado."""
        self.status = MONTHLY_CLOSURE_CLOSED
        self.closed_at = datetime.now().isoformat(timespec="seconds")
        self.touch()

    def reopen(self) -> None:
        """Reabre un mes cerrado o pendiente."""
        self.status = MONTHLY_CLOSURE_OPEN
        self.closed_at = None
        self.touch()
