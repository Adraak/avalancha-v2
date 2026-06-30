"""Pruebas del Perfil Demo Avalancha V2."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from avalancha.models import EXPENSE, MonthlyBudget, Transaction
from avalancha.storage import BudgetRepository
from services.demo_profile_service import DemoProfileService
from services.profile_service import PERFIL_DEMO, PERFIL_PERSONAL, ProfileService


class DemoProfileServiceTest(unittest.TestCase):
    """Valida perfiles locales y datos ficticios del demo."""

    def setUp(self) -> None:
        """Crea carpetas temporales y un dato personal sensible."""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.legacy_data = self.root / "legacy_data"
        self.legacy_reports = self.root / "legacy_reports"
        self.legacy_config = self.root / "legacy_config"
        self._crear_dato_personal()
        self.profile_service = ProfileService(
            profiles_root=self.root / "perfiles",
            legacy_data_dir=self.legacy_data,
            legacy_reports_dir=self.legacy_reports,
            legacy_config_dir=self.legacy_config,
        )
        self.demo_service = DemoProfileService(self.profile_service)

    def tearDown(self) -> None:
        """Elimina archivos temporales."""
        self.temp_dir.cleanup()

    def test_crear_perfil_demo(self) -> None:
        """Crea el demo con datos ficticios completos."""
        profile = self.demo_service.abrir_demo()
        repository = BudgetRepository(profile.data_dir)
        budget = repository.load(2026, 6)

        self.assertEqual(profile.id, PERFIL_DEMO)
        self.assertGreaterEqual(len(repository.load_accounts()), 4)
        self.assertGreaterEqual(len(repository.load_debts()), 2)
        self.assertGreaterEqual(len(budget.transactions), 10)
        self.assertGreaterEqual(len(budget.categories), 8)
        self.assertTrue(profile.reports_dir.joinpath("R2026-06.avr").exists())

    def test_demo_no_copia_datos_personales(self) -> None:
        """Verifica que el demo no reutiliza movimientos reales."""
        profile = self.demo_service.abrir_demo()
        budget = BudgetRepository(profile.data_dir).load(2026, 6)
        descriptions = " ".join(item.description for item in budget.transactions)

        self.assertNotIn("Dato real sensible", descriptions)
        self.assertIn("demo", descriptions.casefold())

    def test_regenerar_demo_mantiene_separacion(self) -> None:
        """Regenerar demo no modifica el perfil personal."""
        personal = self.profile_service.obtener_perfil(PERFIL_PERSONAL)
        personal_budget = BudgetRepository(personal.data_dir).load(2026, 6)
        before = [item.description for item in personal_budget.transactions]

        self.demo_service.regenerar_demo()
        personal_after = BudgetRepository(personal.data_dir).load(2026, 6)
        after = [item.description for item in personal_after.transactions]

        self.assertEqual(before, after)

    def test_cambio_de_perfil(self) -> None:
        """Cambia entre Personal y Demo."""
        demo = self.demo_service.abrir_demo()
        active_demo = self.profile_service.obtener_activo()

        self.profile_service.seleccionar_perfil(PERFIL_PERSONAL)
        active_personal = self.profile_service.obtener_activo()

        self.assertEqual(demo.id, active_demo.id)
        self.assertEqual(active_personal.id, PERFIL_PERSONAL)

    def test_conciliaciones_demo(self) -> None:
        """Verifica una cuenta cuadrada y otra con diferencia."""
        profile = self.demo_service.abrir_demo()
        accounts = BudgetRepository(profile.data_dir).load_accounts()
        states = {account.reconciliation_status for account in accounts}
        differences = [
            account.difference
            for account in accounts
            if account.difference is not None
        ]

        self.assertIn("Cuadrada", states)
        self.assertIn("Con diferencia", states)
        self.assertTrue(any(difference != 0 for difference in differences))

    def test_reportes_demo_en_carpeta_demo(self) -> None:
        """Verifica que los reportes demo quedan aislados."""
        profile = self.demo_service.abrir_demo()
        personal = self.profile_service.obtener_perfil(PERFIL_PERSONAL)

        self.assertTrue(profile.reports_dir.joinpath("index.avridx").exists())
        self.assertFalse(personal.reports_dir.joinpath("R2026-06.avr").exists())

    def _crear_dato_personal(self) -> None:
        """Crea un presupuesto personal que no debe copiarse al demo."""
        repository = BudgetRepository(self.legacy_data)
        budget = MonthlyBudget.empty(2026, 6)
        budget.add_or_update_transaction(
            Transaction(
                EXPENSE,
                "Comida",
                1_000,
                "2026-06-01",
                "Dato real sensible",
                "Debito",
            ),
        )
        repository.save(budget)


if __name__ == "__main__":
    unittest.main()
