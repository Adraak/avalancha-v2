"""Modelo base para presupuestos."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date


@dataclass(slots=True)
class Presupuesto:
    """Representa un presupuesto mensual de una categoria."""

    id: str
    nombre: str = ""
    categoria: str = ""
    monto_mensual: int = 0
    moneda: str = "CLP"
    fecha_inicio: date | None = None
    fecha_termino: date | None = None
    activo: bool = True
    observaciones: str = ""
    mes: str = ""
    categorias: dict[str, int] = field(default_factory=dict)
    ingresos_presupuestados: int = 0
    gastos_presupuestados: int = 0

    def __post_init__(self) -> None:
        """Valida reglas basicas del presupuesto."""
        self.nombre = self.nombre.strip()
        self.categoria = self.categoria.strip()
        self.moneda = self.moneda.strip().upper() or "CLP"
        self.observaciones = self.observaciones.strip()
        self.mes = self.mes.strip()
        if self.mes and (len(self.mes) != 7 or self.mes[4] != "-"):
            raise ValueError("El mes debe usar formato YYYY-MM.")
        if self.fecha_termino and self.fecha_inicio:
            if self.fecha_termino < self.fecha_inicio:
                raise ValueError(
                    "La fecha de termino no puede ser anterior al inicio."
                )
        if self.monto_mensual < 0:
            raise ValueError("El monto mensual no puede ser negativo.")
        if self.ingresos_presupuestados < 0:
            raise ValueError("Los ingresos presupuestados no pueden ser negativos.")
        if self.gastos_presupuestados < 0:
            raise ValueError("Los gastos presupuestados no pueden ser negativos.")
        for categoria, monto in self.categorias.items():
            if not categoria.strip():
                raise ValueError("Las categorias no pueden estar vacias.")
            if monto < 0:
                raise ValueError("El presupuesto por categoria no puede ser negativo.")
