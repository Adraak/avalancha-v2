"""Input validation rules shared by the Avalancha interface."""

from __future__ import annotations


def validar_movimiento(
    amount: int,
    category: str,
    description: str,
    account_id: str,
    payment_method: str,
) -> None:
    """Validate required movement fields before persistence."""
    if amount <= 0:
        raise ValueError("El monto debe ser mayor que cero.")
    if not category.strip():
        raise ValueError("Selecciona una categoria.")
    if not description.strip():
        raise ValueError("La descripcion es obligatoria.")
    if not account_id.strip():
        raise ValueError("Debe seleccionar una cuenta financiera.")
    if not payment_method.strip():
        raise ValueError("Debe seleccionar un medio de pago.")


def validar_deuda(
    current_balance: int,
    monthly_payment: int,
    minimum_payment: int,
    interest_rate: float | None,
) -> None:
    """Validate debt amounts before persistence."""
    if current_balance < 0:
        raise ValueError("El saldo actual no puede ser negativo.")
    if monthly_payment <= 0:
        raise ValueError("El pago mensual debe ser mayor que cero.")
    if minimum_payment < 0:
        raise ValueError("El pago minimo no puede ser negativo.")
    if interest_rate is not None and interest_rate < 0:
        raise ValueError("El interes no puede ser negativo.")
