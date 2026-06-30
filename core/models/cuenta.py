"""Modelo base para cuentas financieras."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(slots=True)
class Cuenta:
    """Representa una cuenta financiera real del usuario."""

    id: str
    nombre: str
    tipo: str
    saldo_real: int | None = None
    saldo_registrado: int = 0
    fecha_conciliacion: date | None = None
    activa: bool = True

    def __post_init__(self) -> None:
        """Normaliza y valida la cuenta financiera."""
        self.nombre = self.nombre.strip()
        self.tipo = self.tipo.strip().lower()

        if not self.nombre:
            raise ValueError("El nombre de la cuenta es obligatorio.")
        if not self.tipo:
            raise ValueError("El tipo de cuenta es obligatorio.")
        if self.saldo_real is not None and not isinstance(self.saldo_real, int):
            raise ValueError("El saldo real debe ser numerico.")
        if not isinstance(self.saldo_registrado, int):
            raise ValueError("El saldo registrado debe ser numerico.")

    @property
    def diferencia(self) -> int | None:
        """Calcula la diferencia entre saldo real y saldo registrado."""
        if self.saldo_real is None:
            return None
        return self.saldo_real - self.saldo_registrado

    @property
    def account_id(self) -> str:
        """Alias compatible con los modelos heredados."""
        return self.id

    @property
    def account_type(self) -> str:
        """Alias compatible con los modelos heredados."""
        return self.tipo

    @property
    def real_balance(self) -> int | None:
        """Alias compatible con los modelos heredados."""
        return self.saldo_real

    @property
    def registered_balance(self) -> int:
        """Alias compatible con los modelos heredados."""
        return self.saldo_registrado

    @property
    def initial_balance(self) -> int:
        """Saldo base preparado para compatibilidad incremental."""
        return 0

    @property
    def active(self) -> bool:
        """Alias compatible con los modelos heredados."""
        return self.activa

    @property
    def reconciliation_date(self) -> str | None:
        """Alias compatible con los modelos heredados."""
        if self.fecha_conciliacion is None:
            return None
        return self.fecha_conciliacion.isoformat()
