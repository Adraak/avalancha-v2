"""Pruebas del sistema de colores de Avalancha V2."""

from __future__ import annotations

import unittest

from ui_pyside6.color_system import (
    DANGER,
    DANGER_STRONG,
    NEUTRAL,
    SUCCESS,
    WARNING,
    get_budget_usage_color,
    get_category_color,
    get_debt_status_color,
    get_flow_color,
    get_semantic_color,
    get_viridis_color,
    is_hex_color,
)


class ColorSystemTest(unittest.TestCase):
    """Valida paletas y helpers visuales centralizados."""

    def test_semantic_color_known_and_unknown(self) -> None:
        """Devuelve colores semanticos o neutral."""
        self.assertEqual(get_semantic_color("success"), SUCCESS)
        self.assertEqual(get_semantic_color("critico"), DANGER)
        self.assertEqual(get_semantic_color("estado-raro"), NEUTRAL)

    def test_category_color_known_and_unknown_is_stable(self) -> None:
        """Mantiene color fijo para categorias conocidas y desconocidas."""
        self.assertEqual(get_category_color("Comida"), "#16a34a")

        first = get_category_color("Categoria nueva")
        second = get_category_color("Categoria nueva")

        self.assertEqual(first, second)
        self.assertTrue(is_hex_color(first))

    def test_budget_usage_risk_scale(self) -> None:
        """Aplica escala de riesgo presupuestario."""
        self.assertEqual(get_budget_usage_color(50), SUCCESS)
        self.assertEqual(get_budget_usage_color(80), WARNING)
        self.assertEqual(get_budget_usage_color(95), DANGER)
        self.assertEqual(get_budget_usage_color(120), DANGER_STRONG)

    def test_flow_color(self) -> None:
        """Clasifica flujo positivo y negativo."""
        self.assertEqual(get_flow_color(1), SUCCESS)
        self.assertEqual(get_flow_color(-1), DANGER)
        self.assertEqual(get_flow_color(0), WARNING)

    def test_debt_status_color(self) -> None:
        """Clasifica estados visuales de deuda."""
        self.assertEqual(get_debt_status_color("Bajando"), SUCCESS)
        self.assertEqual(get_debt_status_color("Sin avance"), WARNING)
        self.assertEqual(get_debt_status_color("Crítica"), DANGER)

    def test_viridis_color_handles_equal_range(self) -> None:
        """Evita division por cero en escala continua."""
        color = get_viridis_color(10, 10, 10)

        self.assertTrue(is_hex_color(color))

    def test_viridis_color_returns_hex(self) -> None:
        """Devuelve HEX valido en valores normales."""
        self.assertTrue(is_hex_color(get_viridis_color(5, 0, 10)))


if __name__ == "__main__":
    unittest.main()
