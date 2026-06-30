"""Modelo base para movimientos financieros."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(slots=True)
class Movimiento:
    """Representa un ingreso o gasto registrado por el usuario."""

    id: str
    fecha: date
    tipo: str
    categoria: str
    descripcion: str
    monto: int
    cuenta_id: str
    medio_pago: str
    recurrente_id: str | None = None
    deuda_id: str | None = None
    imprevisto: bool = False
    clase: str = "Normal"

    def __post_init__(self) -> None:
        """Normaliza y valida los campos basicos del movimiento."""
        self.tipo = self.tipo.strip().lower()
        self.categoria = self.categoria.strip()
        self.descripcion = self.descripcion.strip()
        self.cuenta_id = self.cuenta_id.strip()
        self.medio_pago = self.medio_pago.strip()
        self.clase = self.clase.strip() or "Normal"

        if self.tipo not in {"gasto", "ingreso"}:
            raise ValueError("El tipo debe ser gasto o ingreso.")
        if not self.categoria:
            raise ValueError("La categoria es obligatoria.")
        if not self.cuenta_id:
            raise ValueError("La cuenta financiera es obligatoria.")
        if not self.medio_pago:
            raise ValueError("El medio de pago es obligatorio.")
        if self.monto <= 0:
            raise ValueError("El monto debe ser mayor que cero.")

    @property
    def es_gasto(self) -> bool:
        """Indica si el movimiento corresponde a un gasto."""
        return self.tipo == "gasto"

    @property
    def es_ingreso(self) -> bool:
        """Indica si el movimiento corresponde a un ingreso."""
        return self.tipo == "ingreso"

    @property
    def transaction_type(self) -> str:
        """Alias compatible con los modelos heredados."""
        return self.tipo

    @property
    def category(self) -> str:
        """Alias compatible con los modelos heredados."""
        return self.categoria

    @property
    def amount(self) -> int:
        """Alias compatible con los modelos heredados."""
        return self.monto

    @property
    def is_unexpected(self) -> bool:
        """Alias compatible con los modelos heredados."""
        return self.imprevisto

    @property
    def account_id(self) -> str:
        """Alias compatible con los modelos heredados."""
        return self.cuenta_id

    @property
    def recurring_id(self) -> str | None:
        """Alias compatible con los modelos heredados."""
        return self.recurrente_id
