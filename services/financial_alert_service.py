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
        umbral_imprevistos: int = 100_000,
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

        if indicadores.gastos_imprevistos > umbral_imprevistos:
            alertas.append(
                FinancialAlert(
                    nivel="advertencia",
                    titulo="Imprevistos altos",
                    mensaje="Los gastos imprevistos superan el umbral mensual.",
                    metrica=indicadores.gastos_imprevistos,
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
