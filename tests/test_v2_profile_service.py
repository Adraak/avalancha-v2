"""Pruebas del servicio de perfiles de Avalancha V2."""

from __future__ import annotations

import tempfile
import unittest
from datetime import date
from pathlib import Path

from avalancha.models import EXPENSE, INCOME, MonthlyBudget, Transaction
from avalancha.storage import BudgetRepository
from services.profile_service import PERFIL_PERSONAL, ProfileService


class ProfileServiceTest(unittest.TestCase):
    """Valida seleccion de periodo operativo por perfil."""

    def setUp(self) -> None:
        """Crea perfiles temporales sin tocar datos reales."""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.service = ProfileService(
            profiles_root=self.root / "perfiles",
            legacy_data_dir=self.root / "legacy_data",
            legacy_reports_dir=self.root / "legacy_reports",
            legacy_config_dir=self.root / "legacy_config",
        )
        self.profile = self.service.obtener_perfil(PERFIL_PERSONAL)
        self.repository = BudgetRepository(self.profile.data_dir)

    def tearDown(self) -> None:
        """Elimina carpetas temporales."""
        self.temp_dir.cleanup()

    def test_periodo_ignora_mes_actual_vacio_si_existe_mes_con_movimientos(
        self,
    ) -> None:
        """Usa el ultimo mes con movimientos si el mes actual esta vacio."""
        self.repository.save(
            MonthlyBudget(
                year=2026,
                month=6,
                transactions=[
                    Transaction(
                        INCOME,
                        "Sueldo",
                        100_000,
                        "2026-06-01",
                        "Ingreso prueba",
                    ),
                ],
            ),
        )
        self.repository.save(MonthlyBudget.empty(2026, 7))

        period = self.service.obtener_periodo_trabajo(
            PERFIL_PERSONAL,
            date(2026, 7, 1),
        )

        self.assertEqual(period, (2026, 6))

    def test_periodo_usa_mes_actual_si_tiene_movimientos(self) -> None:
        """Mantiene el mes actual cuando ya contiene registros reales."""
        self.repository.save(
            MonthlyBudget(
                year=2026,
                month=7,
                transactions=[
                    Transaction(
                        EXPENSE,
                        "Comida",
                        10_000,
                        "2026-07-01",
                        "Gasto prueba",
                    ),
                ],
            ),
        )

        period = self.service.obtener_periodo_trabajo(
            PERFIL_PERSONAL,
            date(2026, 7, 1),
        )

        self.assertEqual(period, (2026, 7))


if __name__ == "__main__":
    unittest.main()
