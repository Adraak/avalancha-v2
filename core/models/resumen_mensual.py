"""Modelo base para resumen financiero mensual."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class ResumenMensual:
    """Consolida los indicadores principales de un mes."""

    mes: str
    ingresos_reales: int = 0
    gastos_reales: int = 0
    flujo_libre: int = 0
    deuda_total: int = 0
    patrimonio_neto: int = 0
    gastos_imprevistos: int = 0
    categorias: dict[str, int] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Valida el formato del mes y montos principales."""
        self.mes = self.mes.strip()
        if len(self.mes) != 7 or self.mes[4] != "-":
            raise ValueError("El mes debe usar formato YYYY-MM.")
        if self.ingresos_reales < 0:
            raise ValueError("Los ingresos reales no pueden ser negativos.")
        if self.gastos_reales < 0:
            raise ValueError("Los gastos reales no pueden ser negativos.")
        if self.deuda_total < 0:
            raise ValueError("La deuda total no puede ser negativa.")
        if self.gastos_imprevistos < 0:
            raise ValueError("Los gastos imprevistos no pueden ser negativos.")

