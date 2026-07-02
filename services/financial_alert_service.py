"""Servicio de alertas financieras simples para Avalancha V2."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class FinancialAlert:
    """Representa una alerta financiera lista para interfaz."""

    nivel: str
    titulo: str
    mensaje: str
    metrica: int | float | None = None


class FinancialAlertService:
    """Genera alertas financieras deterministicas sin depender de UI."""

    def generar_alertas(
        self,
        indicadores: Any,
        categorias: list[dict[str, Any]],
    ) -> list[FinancialAlert]:
        """Construye alertas simples a partir de indicadores mensuales."""
        alertas: list[FinancialAlert] = []

        if indicadores.flujo_libre < 0:
            alertas.append(
                FinancialAlert(
                    nivel="critico",
                    titulo="Flujo libre negativo",
                    mensaje="Este mes los gastos superan los ingresos.",
                    metrica=indicadores.flujo_libre,
                ),
            )

        if indicadores.gastos_reales > indicadores.ingresos_reales:
            alertas.append(
                FinancialAlert(
                    nivel="critico",
                    titulo="Gastos sobre ingresos",
                    mensaje="El gasto real del mes es mayor que el ingreso.",
                    metrica=(
                        indicadores.gastos_reales
                        - indicadores.ingresos_reales
                    ),
                ),
            )

        if (
            indicadores.ingresos_reales > 0
            and indicadores.deuda_actual > indicadores.ingresos_reales
        ):
            alertas.append(
                FinancialAlert(
                    nivel="advertencia",
                    titulo="Deuda alta",
                    mensaje="La deuda actual supera el ingreso mensual.",
                    metrica=indicadores.deuda_actual,
                ),
            )

        excedidas = [
            item["name"]
            for item in categorias
            if item.get("status") == "sobrepasado"
            and not bool(item.get("is_fixed", False))
        ]
        if excedidas:
            alertas.append(
                FinancialAlert(
                    nivel="critico",
                    titulo="Presupuesto excedido",
                    mensaje=(
                        "Categorías sobre presupuesto: "
                        + ", ".join(excedidas)
                    ),
                    metrica=len(excedidas),
                ),
            )

        en_riesgo = [
            str(item.get("name", ""))
            for item in categorias
            if item.get("status") != "sobrepasado"
            and not bool(item.get("is_fixed", False))
            and float(item.get("usage", 0.0) or 0.0) >= 90
        ]
        if en_riesgo:
            alertas.append(
                FinancialAlert(
                    nivel="advertencia",
                    titulo="Presupuesto sobre 90%",
                    mensaje=(
                        "Categorías cerca del límite: "
                        + ", ".join(en_riesgo)
                    ),
                    metrica=len(en_riesgo),
                ),
            )

        porcentaje_imprevistos = self._porcentaje_imprevistos(indicadores)
        if porcentaje_imprevistos > 35:
            alertas.append(
                FinancialAlert(
                    nivel="critico",
                    titulo="Gastos imprevistos altos",
                    mensaje=(
                        "Este mes los gastos imprevistos representan "
                        f"el {porcentaje_imprevistos:.1f}% de tus gastos."
                    ),
                    metrica=porcentaje_imprevistos,
                ),
            )
        elif porcentaje_imprevistos > 20:
            alertas.append(
                FinancialAlert(
                    nivel="advertencia",
                    titulo="Gastos imprevistos altos",
                    mensaje=(
                        "Este mes los gastos imprevistos representan "
                        f"el {porcentaje_imprevistos:.1f}% de tus gastos."
                    ),
                    metrica=porcentaje_imprevistos,
                ),
            )

        if not alertas:
            alertas.append(
                FinancialAlert(
                    nivel="info",
                    titulo="Sin alertas críticas",
                    mensaje="No se detectaron alertas financieras relevantes.",
                ),
            )

        return alertas

    @staticmethod
    def _porcentaje_imprevistos(indicadores: Any) -> float:
        """Calcula peso de imprevistos sin generar alertas falsas."""
        gastos = int(getattr(indicadores, "gastos_reales", 0) or 0)
        imprevistos = int(getattr(indicadores, "gastos_imprevistos", 0) or 0)
        if gastos <= 0 or imprevistos <= 0:
            return 0.0
        return round((imprevistos / gastos) * 100, 1)
