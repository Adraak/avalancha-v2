"""Pruebas del servicio de alertas financieras."""

from __future__ import annotations

import unittest
from types import SimpleNamespace

from services.financial_alert_service import FinancialAlertService


class FinancialAlertServiceTest(unittest.TestCase):
    """Valida reglas simples de alertas financieras."""

    def setUp(self) -> None:
        """Crea el servicio bajo prueba."""
        self.service = FinancialAlertService()

    def test_flujo_negativo_y_gastos_mayores_generan_alertas(self) -> None:
        """Detecta deficit operativo del mes."""
        indicators = SimpleNamespace(
            flujo_libre=-50_000,
            gastos_reales=250_000,
            ingresos_reales=200_000,
            deuda_actual=100_000,
            gastos_imprevistos=0,
        )

        alerts = self.service.generar_alertas(indicators, [])
        titles = {alert.titulo for alert in alerts}

        self.assertIn("Flujo libre negativo", titles)
        self.assertIn("Gastos sobre ingresos", titles)

    def test_presupuesto_excedido_genera_alerta_critica(self) -> None:
        """Detecta categorias sobre presupuesto."""
        indicators = SimpleNamespace(
            flujo_libre=100_000,
            gastos_reales=100_000,
            ingresos_reales=200_000,
            deuda_actual=0,
            gastos_imprevistos=0,
        )

        alerts = self.service.generar_alertas(
            indicators,
            [{"name": "Comida", "status": "sobrepasado"}],
        )

        self.assertEqual(alerts[0].nivel, "critico")
        self.assertEqual(alerts[0].titulo, "Presupuesto excedido")

    def test_pago_fijo_pagado_no_genera_alerta_critica(self) -> None:
        """Ignora categorias fijas cumplidas en alertas de presupuesto."""
        indicators = SimpleNamespace(
            flujo_libre=100_000,
            gastos_reales=100_000,
            ingresos_reales=200_000,
            deuda_actual=0,
            gastos_imprevistos=0,
        )

        alerts = self.service.generar_alertas(
            indicators,
            [
                {
                    "name": "Arriendo",
                    "status": "sobrepasado",
                    "usage": 100.0,
                    "is_fixed": True,
                },
            ],
        )

        self.assertFalse(
            any(alert.titulo == "Presupuesto excedido" for alert in alerts),
        )

    def test_presupuesto_sobre_90_genera_advertencia(self) -> None:
        """Detecta categorias cerca del limite presupuestario."""
        indicators = SimpleNamespace(
            flujo_libre=100_000,
            gastos_reales=100_000,
            ingresos_reales=200_000,
            deuda_actual=0,
            gastos_imprevistos=0,
        )

        alerts = self.service.generar_alertas(
            indicators,
            [{"name": "Transporte", "status": "ok", "usage": 95.0}],
        )

        self.assertTrue(
            any(
                alert.nivel == "advertencia"
                and alert.titulo == "Presupuesto sobre 90%"
                for alert in alerts
            ),
        )

    def test_deuda_mayor_que_ingreso_genera_advertencia(self) -> None:
        """Detecta deuda total mayor que ingreso mensual."""
        indicators = SimpleNamespace(
            flujo_libre=50_000,
            gastos_reales=150_000,
            ingresos_reales=200_000,
            deuda_actual=300_000,
            gastos_imprevistos=0,
        )

        alerts = self.service.generar_alertas(indicators, [])

        self.assertTrue(
            any(alert.titulo == "Deuda alta" for alert in alerts),
        )

    def test_sin_alertas_devuelve_info(self) -> None:
        """Devuelve una alerta informativa cuando no hay problemas."""
        indicators = SimpleNamespace(
            flujo_libre=50_000,
            gastos_reales=150_000,
            ingresos_reales=200_000,
            deuda_actual=0,
            gastos_imprevistos=0,
        )

        alerts = self.service.generar_alertas(indicators, [])

        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0].nivel, "info")

    def test_imprevistos_moderados_generan_advertencia(self) -> None:
        """Advierte si imprevistos superan 20% del gasto mensual."""
        indicators = SimpleNamespace(
            flujo_libre=50_000,
            gastos_reales=100_000,
            ingresos_reales=200_000,
            deuda_actual=0,
            gastos_imprevistos=28_000,
        )

        alerts = self.service.generar_alertas(indicators, [])

        self.assertTrue(
            any(
                alert.nivel == "advertencia"
                and alert.titulo == "Gastos imprevistos altos"
                for alert in alerts
            ),
        )

    def test_imprevistos_altos_generan_alerta_critica(self) -> None:
        """Marca critico si imprevistos superan 35% del gasto mensual."""
        indicators = SimpleNamespace(
            flujo_libre=50_000,
            gastos_reales=100_000,
            ingresos_reales=200_000,
            deuda_actual=0,
            gastos_imprevistos=40_000,
        )

        alerts = self.service.generar_alertas(indicators, [])

        self.assertTrue(
            any(
                alert.nivel == "critico"
                and alert.titulo == "Gastos imprevistos altos"
                for alert in alerts
            ),
        )

    def test_imprevistos_bajos_no_generan_alerta(self) -> None:
        """No alerta si imprevistos existen pero son proporcionales."""
        indicators = SimpleNamespace(
            flujo_libre=50_000,
            gastos_reales=100_000,
            ingresos_reales=200_000,
            deuda_actual=0,
            gastos_imprevistos=10_000,
        )

        alerts = self.service.generar_alertas(indicators, [])

        self.assertFalse(
            any(alert.titulo == "Gastos imprevistos altos" for alert in alerts),
        )

    def test_sin_gastos_no_genera_alerta_de_imprevistos(self) -> None:
        """No falla ni alerta si no existe gasto mensual."""
        indicators = SimpleNamespace(
            flujo_libre=0,
            gastos_reales=0,
            ingresos_reales=0,
            deuda_actual=0,
            gastos_imprevistos=0,
        )

        alerts = self.service.generar_alertas(indicators, [])

        self.assertEqual(alerts[0].titulo, "Sin alertas críticas")


if __name__ == "__main__":
    unittest.main()
