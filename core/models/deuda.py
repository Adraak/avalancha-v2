"""Modelo base para deudas financieras."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(slots=True)
class Deuda:
    """Representa una deuda, credito o tarjeta pendiente de pago."""

    id: str
    nombre: str
    categoria: str
    saldo_actual: int
    saldo_mes_anterior: int
    pago_mensual_actual: int
    pago_minimo: int = 0
    tasa_interes_mensual: float | None = None
    fecha_inicio: date | None = None
    fecha_actualizacion: date | None = None
    activa: bool = True

    def __post_init__(self) -> None:
        """Normaliza y valida los campos principales de la deuda."""
        self.nombre = self.nombre.strip()
        self.categoria = self.categoria.strip().lower()

        if not self.nombre:
            raise ValueError("El nombre de la deuda es obligatorio.")
        if not self.categoria:
            raise ValueError("La categoria de deuda es obligatoria.")
        if self.saldo_actual < 0:
            raise ValueError("El saldo actual no puede ser negativo.")
        if self.saldo_mes_anterior < 0:
            raise ValueError("El saldo del mes anterior no puede ser negativo.")
        if self.pago_mensual_actual < 0:
            raise ValueError("El pago mensual no puede ser negativo.")
        if self.pago_minimo < 0:
            raise ValueError("El pago minimo no puede ser negativo.")
        if (
            self.tasa_interes_mensual is not None
            and self.tasa_interes_mensual < 0
        ):
            raise ValueError("La tasa de interes no puede ser negativa.")

    @property
    def disminucion_mensual(self) -> int:
        """Calcula cuanto bajo la deuda frente al mes anterior."""
        return self.saldo_mes_anterior - self.saldo_actual

    @property
    def interes_mensual_estimado(self) -> int:
        """Estima el interes mensual en pesos."""
        if not self.tasa_interes_mensual:
            return 0
        return round(self.saldo_actual * (self.tasa_interes_mensual / 100))

    @property
    def debt_id(self) -> str:
        """Alias compatible con los modelos heredados."""
        return self.id

    @property
    def current_balance(self) -> int:
        """Alias compatible con los modelos heredados."""
        return self.saldo_actual

    @property
    def previous_month_balance(self) -> int:
        """Alias compatible con los modelos heredados."""
        return self.saldo_mes_anterior

    @property
    def current_monthly_payment(self) -> int:
        """Alias compatible con los modelos heredados."""
        return self.pago_mensual_actual

    @property
    def monthly_interest_rate(self) -> float | None:
        """Alias compatible con los modelos heredados."""
        return self.tasa_interes_mensual

    @property
    def active(self) -> bool:
        """Alias compatible con los modelos heredados."""
        return self.activa
