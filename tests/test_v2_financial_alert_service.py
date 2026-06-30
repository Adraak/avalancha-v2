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


if __name__ == "__main__":
    unittest.main()
