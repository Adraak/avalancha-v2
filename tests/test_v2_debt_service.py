"""Pruebas del CRUD de deudas V2."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from PySide6.QtCore import QDate
from PySide6.QtWidgets import QApplication

from avalancha.models import CategoryBudget, EXPENSE, MonthlyBudget, Transaction
from avalancha.storage import BudgetRepository
from services.debt_service import DebtService
from services.demo_profile_service import DemoProfileService
from services.financial_summary_service import FinancialSummaryService
from services.profile_service import PERFIL_PERSONAL, ProfileService
from ui_pyside6.pages.debt_dialog import DebtDialog


class DebtServiceTest(unittest.TestCase):
    """Valida CRUD, reglas e integracion de deudas."""

    def setUp(self) -> None:
        """Crea repositorio temporal con categoria de pago de deuda."""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.data_dir = Path(self.temp_dir.name)
        self.repository = BudgetRepository(self.data_dir)
        self.repository.save(
            MonthlyBudget(
                year=2026,
                month=6,
                categories=[
                    CategoryBudget(
                        "Pago deuda",
                        EXPENSE,
                        100_000,
                        True,
                    ),
                ],
            ),
        )
        self.service = DebtService(
            data_dir=self.data_dir,
            repository=self.repository,
        )

    def tearDown(self) -> None:
        """Elimina archivos temporales."""
        self.temp_dir.cleanup()

    def test_crear_deuda(self) -> None:
        """Crea y lista una deuda."""
        debt = self._crear_deuda_base()
        loaded = self.service.obtener_deuda_por_id(debt.debt_id)

        self.assertEqual(loaded.name, "Tarjeta prueba")
        self.assertEqual(loaded.current_balance, 500_000)
        self.assertTrue(loaded.active)

    def test_editar_deuda(self) -> None:
        """Edita datos principales de una deuda."""
        debt = self._crear_deuda_base()

        edited = self.service.editar_deuda(
            debt.debt_id,
            {
                "name": "Credito prueba",
                "category": "credito_consumo",
                "current_balance": "300000",
                "previous_month_balance": "350000",
                "current_monthly_payment": "50000",
                "minimum_payment": "25000",
                "monthly_interest_rate": "1.5",
                "credit_limit": "0",
                "active": True,
            },
        )

        self.assertEqual(edited.name, "Credito prueba")
        self.assertEqual(edited.category, "credito_consumo")
        self.assertEqual(edited.current_balance, 300_000)
        self.assertEqual(edited.monthly_interest_rate, 1.5)

    def test_eliminar_deuda(self) -> None:
        """Elimina una deuda sin movimientos asociados."""
        debt = self._crear_deuda_base()

        self.service.eliminar_deuda(debt.debt_id)

        self.assertEqual(self.service.obtener_deudas(), [])

    def test_no_elimina_deuda_con_movimientos(self) -> None:
        """Protege deudas usadas por movimientos."""
        debt = self._crear_deuda_base()
        budget = self.repository.load(2026, 6)
        budget.add_or_update_transaction(
            Transaction(
                transaction_type=EXPENSE,
                category="Pago deuda",
                amount=50_000,
                tx_date="2026-06-01",
                description="Pago tarjeta",
                debt_id=debt.debt_id,
            ),
        )
        self.repository.save(budget)

        with self.assertRaisesRegex(ValueError, "movimientos asociados"):
            self.service.eliminar_deuda(debt.debt_id)

    def test_activar_desactivar_deuda(self) -> None:
        """Cambia estado activo de una deuda."""
        debt = self._crear_deuda_base()

        inactive = self.service.desactivar_deuda(debt.debt_id)
        active = self.service.activar_deuda(debt.debt_id)

        self.assertFalse(inactive.active)
        self.assertTrue(active.active)

    def test_validaciones(self) -> None:
        """Rechaza nombre, categoria, pago y duplicados invalidos."""
        with self.assertRaisesRegex(ValueError, "nombre"):
            self.service.crear_deuda(
                {
                    "name": "",
                    "category": "otra",
                    "current_balance": 1,
                    "current_monthly_payment": 1,
                },
            )

        with self.assertRaisesRegex(ValueError, "categoría"):
            self.service.crear_deuda(
                {
                    "name": "Deuda",
                    "category": "categoria_mala",
                    "current_balance": 1,
                    "current_monthly_payment": 1,
                },
            )

        with self.assertRaisesRegex(ValueError, "pago mensual"):
            self.service.crear_deuda(
                {
                    "name": "Deuda",
                    "category": "otra",
                    "current_balance": 1,
                    "current_monthly_payment": 0,
                },
            )

        self._crear_deuda_base()
        with self.assertRaisesRegex(ValueError, "Ya existe"):
            self._crear_deuda_base()

    def test_indicadores_usan_deudas_del_servicio(self) -> None:
        """Comprueba compatibilidad con resumen financiero."""
        debt = self._crear_deuda_base()
        summary = FinancialSummaryService().calcular_deuda_total(
            self.service.obtener_deudas(),
        )

        self.assertEqual(summary, debt.current_balance)
        self.assertEqual(
            self.service.calcular_interes_estimado(debt),
            10_000,
        )
        self.assertEqual(
            self.service.calcular_disminucion_mensual(debt),
            100_000,
        )

    def test_estado_visual_deuda(self) -> None:
        """Clasifica avance visual de una deuda desde el servicio."""
        debt = self._crear_deuda_base()

        self.assertEqual(self.service.estado_visual(debt), "Bajando")

        debt.previous_month_balance = debt.current_balance
        self.assertEqual(self.service.estado_visual(debt), "Sin avance")

        debt.monthly_interest_rate = 50
        debt.current_monthly_payment = 1
        self.assertEqual(self.service.estado_visual(debt), "Crítica")

    def _crear_deuda_base(self):
        """Crea una deuda base para pruebas."""
        return self.service.crear_deuda(
            {
                "name": "Tarjeta prueba",
                "category": "tarjeta_credito",
                "current_balance": "500000",
                "previous_month_balance": "600000",
                "current_monthly_payment": "100000",
                "minimum_payment": "50000",
                "monthly_interest_rate": "2.0",
                "credit_limit": "1000000",
            },
        )


class DebtProfileIsolationTest(unittest.TestCase):
    """Verifica aislamiento de deudas entre Personal y Demo."""

    def test_deudas_personal_y_demo_no_se_mezclan(self) -> None:
        """Comprueba separacion al regenerar el demo."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            legacy_data = root / "legacy_data"
            repository = BudgetRepository(legacy_data)
            repository.save_debts([])
            profile_service = ProfileService(
                profiles_root=root / "perfiles",
                legacy_data_dir=legacy_data,
                legacy_reports_dir=root / "legacy_reports",
                legacy_config_dir=root / "legacy_config",
            )
            personal = profile_service.obtener_perfil(PERFIL_PERSONAL)
            personal_service = DebtService(data_dir=personal.data_dir)
            personal_service.crear_deuda(
                {
                    "name": "Deuda real separada",
                    "category": "otra",
                    "current_balance": "999",
                    "current_monthly_payment": "100",
                },
            )
            demo_service = DemoProfileService(profile_service)
            demo = demo_service.abrir_demo()

            personal_names = {
                debt.name
                for debt in DebtService(
                    data_dir=personal.data_dir,
                ).obtener_deudas()
            }
            demo_names_before = {
                debt.name
                for debt in DebtService(
                    data_dir=demo.data_dir,
                ).obtener_deudas()
            }
            demo_service.regenerar_demo()
            demo_names_after = {
                debt.name
                for debt in DebtService(
                    data_dir=demo.data_dir,
                ).obtener_deudas()
            }

            self.assertIn("Deuda real separada", personal_names)
            self.assertNotIn("Deuda real separada", demo_names_before)
            self.assertNotIn("Deuda real separada", demo_names_after)
            self.assertTrue(
                any("Demo Avalancha" in name for name in demo_names_after),
            )


class DebtDialogTest(unittest.TestCase):
    """Valida comportamiento seguro del formulario de deudas."""

    @classmethod
    def setUpClass(cls) -> None:
        """Asegura una aplicacion Qt para construir dialogos."""
        cls.app = QApplication.instance() or QApplication([])

    def test_fecha_invalida_usa_fecha_actual(self) -> None:
        """Evita que una fecha heredada corrupta rompa el dialogo."""
        today = QDate.currentDate()

        parsed = DebtDialog._safe_qdate("fecha-corrupta")

        self.assertTrue(parsed.isValid())
        self.assertEqual(parsed, today)

    def test_fecha_vacia_o_none_usa_fecha_actual(self) -> None:
        """Evita fallas con fechas antiguas vacias o nulas."""
        today = QDate.currentDate()

        empty_date = DebtDialog._safe_qdate("")
        none_date = DebtDialog._safe_qdate(None)

        self.assertEqual(empty_date, today)
        self.assertEqual(none_date, today)

    def test_fecha_valida_se_mantiene(self) -> None:
        """Respeta fechas heredadas validas."""
        parsed = DebtDialog._safe_qdate("2026-06-15")

        self.assertEqual(parsed, QDate(2026, 6, 15))


if __name__ == "__main__":
    unittest.main()
