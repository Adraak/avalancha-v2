"""Modelo base para conciliaciones financieras."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date


ESTADOS_CONCILIACION = {
    "Pendiente",
    "Revisada",
    "Con diferencia",
    "Cuadrada",
}


@dataclass(slots=True)
class Conciliacion:
    """Representa la conciliacion vigente de una cuenta."""

    id: str
    cuenta_id: str
    saldo_real: int | None
    saldo_registrado: int
    fecha_conciliacion: date
    estado: str = "Pendiente"
    observaciones: str = ""

    def __post_init__(self) -> None:
        """Valida reglas basicas de la conciliacion."""
        self.cuenta_id = self.cuenta_id.strip()
        self.estado = self.estado.strip()
        self.observaciones = self.observaciones.strip()

        if not self.id.strip():
            raise ValueError("La conciliacion necesita un identificador.")
        if not self.cuenta_id:
            raise ValueError("La cuenta es obligatoria.")
        if self.saldo_real is not None and not isinstance(self.saldo_real, int):
            raise ValueError("El saldo real debe ser numerico.")
        if not isinstance(self.saldo_registrado, int):
            raise ValueError("El saldo registrado debe ser numerico.")
        if self.estado not in ESTADOS_CONCILIACION:
            raise ValueError("El estado de conciliacion no es valido.")

    @property
    def diferencia(self) -> int | None:
        """Calcula saldo real menos saldo registrado."""
        if self.saldo_real is None:
            return None
        return self.saldo_real - self.saldo_registrado

