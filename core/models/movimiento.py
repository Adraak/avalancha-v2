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
    cuenta_destino_id: str | None = None
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
        if self.cuenta_destino_id is not None:
            self.cuenta_destino_id = self.cuenta_destino_id.strip() or None
        self.clase = self.clase.strip() or "Normal"

        if self.tipo not in {
            "gasto",
            "ingreso",
            "transferencia",
            "pago_deuda",
        }:
            raise ValueError(
                "El tipo debe ser gasto, ingreso, transferencia o pago de deuda."
            )
        if self.tipo not in {"transferencia", "pago_deuda"} and not self.categoria:
            raise ValueError("La categoria es obligatoria.")
        if not self.cuenta_id:
            raise ValueError("La cuenta financiera es obligatoria.")
        if not self.medio_pago:
            raise ValueError("El medio de pago es obligatorio.")
        if self.monto <= 0:
            raise ValueError("El monto debe ser mayor que cero.")
        if self.tipo == "transferencia":
            self.categoria = ""
            self.imprevisto = False
            self.clase = "Transferencia"
            self.recurrente_id = None
            self.deuda_id = None
            if not self.cuenta_destino_id:
                raise ValueError("La cuenta destino es obligatoria.")
            if self.cuenta_id == self.cuenta_destino_id:
                raise ValueError(
                    "La cuenta origen y destino deben ser distintas."
                )
        if self.tipo == "pago_deuda":
            self.categoria = ""
            self.cuenta_destino_id = None
            self.imprevisto = False
            self.clase = "Pago de deuda"
            self.recurrente_id = None
            if not self.deuda_id:
                raise ValueError("La deuda es obligatoria.")

    @property
    def es_gasto(self) -> bool:
        """Indica si el movimiento corresponde a un gasto."""
        return self.tipo == "gasto"

    @property
    def es_ingreso(self) -> bool:
        """Indica si el movimiento corresponde a un ingreso."""
        return self.tipo == "ingreso"

    @property
    def es_transferencia(self) -> bool:
        """Indica si el movimiento corresponde a transferencia interna."""
        return self.tipo == "transferencia"

    @property
    def es_pago_deuda(self) -> bool:
        """Indica si el movimiento corresponde a pago de deuda."""
        return self.tipo == "pago_deuda"

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
    def destination_account_id(self) -> str | None:
        """Alias compatible para cuenta destino de transferencia."""
        return self.cuenta_destino_id

    @property
    def recurring_id(self) -> str | None:
        """Alias compatible con los modelos heredados."""
        return self.recurrente_id
