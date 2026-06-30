"""Pruebas del CRUD de cuentas V2."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from avalancha.models import CategoryBudget, EXPENSE, MonthlyBudget
from avalancha.storage import BudgetRepository
from services.account_service import AccountService
from services.demo_profile_service import DemoProfileService
from services.movement_service import MovementService
from services.profile_service import PERFIL_PERSONAL, ProfileService


class AccountServiceTest(unittest.TestCase):
    """Valida CRUD, reglas e integracion de cuentas."""

    def setUp(self) -> None:
        """Crea repositorio temporal con categoria de gasto."""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.data_dir = Path(self.temp_dir.name)
        self.repository = BudgetRepository(self.data_dir)
        self.repository.save(
            MonthlyBudget(
                year=2026,
                month=6,
                categories=[
                    CategoryBudget("Comida", EXPENSE, 100_000, False),
                ],
            ),
        )
        self.service = AccountService(
            data_dir=self.data_dir,
            repository=self.repository,
        )

    def tearDown(self) -> None:
        """Elimina archivos temporales."""
        self.temp_dir.cleanup()

    def test_crear_cuenta(self) -> None:
        """Crea y lista una cuenta financiera."""
        account = self.service.crear_cuenta(
            {
                "name": "Cuenta corriente prueba",
                "account_type": "cuenta_corriente",
                "real_balance": "150000",
            },
        )

        loaded = self.service.obtener_cuenta_por_id(account.account_id)

        self.assertEqual(loaded.name, "Cuenta corriente prueba")
        self.assertEqual(loaded.real_balance, 150_000)
        self.assertTrue(loaded.active)

    def test_editar_cuenta(self) -> None:
        """Edita nombre, tipo y saldo real."""
        account = self._crear_cuenta_base()

        edited = self.service.editar_cuenta(
            account.account_id,
            {
                "name": "Ahorro prueba",
                "account_type": "ahorro",
                "real_balance": "200000",
                "active": True,
            },
        )

        self.assertEqual(edited.name, "Ahorro prueba")
        self.assertEqual(edited.account_type, "ahorro")
        self.assertEqual(edited.real_balance, 200_000)

    def test_eliminar_cuenta(self) -> None:
        """Elimina una cuenta sin movimientos asociados."""
        account = self._crear_cuenta_base()

        self.service.eliminar_cuenta(account.account_id)

        self.assertEqual(self.service.obtener_cuentas(), [])

    def test_no_elimina_cuenta_con_movimientos(self) -> None:
        """Protege cuentas usadas por movimientos."""
        account = self._crear_cuenta_base()
        MovementService(
            data_dir=self.data_dir,
            year=2026,
            month=6,
            repository=self.repository,
        ).crear_movimiento(
            fecha="01-06-2026",
            tipo="gasto",
            categoria="Comida",
            cuenta_id=account.account_id,
            monto=10_000,
            descripcion="Compra",
        )

        with self.assertRaisesRegex(ValueError, "movimientos asociados"):
            self.service.eliminar_cuenta(account.account_id)

    def test_activar_desactivar_cuenta(self) -> None:
        """Cambia estado activo de una cuenta."""
        account = self._crear_cuenta_base()

        inactive = self.service.desactivar_cuenta(account.account_id)
        active = self.service.activar_cuenta(account.account_id)

        self.assertFalse(inactive.active)
        self.assertTrue(active.active)

    def test_validaciones(self) -> None:
        """Rechaza nombre, tipo, saldo y duplicados invalidos."""
        with self.assertRaisesRegex(ValueError, "nombre"):
            self.service.crear_cuenta({"name": "", "account_type": "ahorro"})

        with self.assertRaisesRegex(ValueError, "tipo"):
            self.service.crear_cuenta({"name": "Cuenta", "account_type": "x"})

        with self.assertRaisesRegex(ValueError, "saldo real"):
            self.service.crear_cuenta(
                {
                    "name": "Cuenta",
                    "account_type": "ahorro",
                    "real_balance": "malo",
                },
            )

        self._crear_cuenta_base()
        with self.assertRaisesRegex(ValueError, "Ya existe"):
            self._crear_cuenta_base()

    def test_compatibilidad_con_movement_service(self) -> None:
        """Las cuentas creadas quedan disponibles para movimientos."""
        account = self._crear_cuenta_base()
        movement_service = MovementService(
            data_dir=self.data_dir,
            year=2026,
            month=6,
            repository=self.repository,
        )

        options = movement_service.obtener_cuentas()

        self.assertEqual(options[0].id, account.account_id)

    def _crear_cuenta_base(self):
        """Crea una cuenta base para pruebas."""
        return self.service.crear_cuenta(
            {
                "name": "Cuenta prueba",
                "account_type": "cuenta_corriente",
                "real_balance": "100000",
            },
        )


class AccountProfileIsolationTest(unittest.TestCase):
    """Verifica aislamiento de cuentas entre Personal y Demo."""

    def test_cuentas_personal_y_demo_no_se_mezclan(self) -> None:
        """Comprueba separacion al regenerar el demo."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            legacy_data = root / "legacy_data"
            repository = BudgetRepository(legacy_data)
            repository.save_accounts([])
            profile_service = ProfileService(
                profiles_root=root / "perfiles",
                legacy_data_dir=legacy_data,
                legacy_reports_dir=root / "legacy_reports",
                legacy_config_dir=root / "legacy_config",
            )
            personal = profile_service.obtener_perfil(PERFIL_PERSONAL)
            personal_service = AccountService(data_dir=personal.data_dir)
            personal_service.crear_cuenta(
                {
                    "name": "Cuenta real separada",
                    "account_type": "cuenta_corriente",
                    "real_balance": "999",
                },
            )
            demo_service = DemoProfileService(profile_service)
            demo = demo_service.abrir_demo()

            personal_names = {
                account.name
                for account in AccountService(
                    data_dir=personal.data_dir,
                ).obtener_cuentas()
            }
            demo_names_before = {
                account.name
                for account in AccountService(
                    data_dir=demo.data_dir,
                ).obtener_cuentas()
            }
            demo_service.regenerar_demo()
            demo_names_after = {
                account.name
                for account in AccountService(
                    data_dir=demo.data_dir,
                ).obtener_cuentas()
            }

            self.assertIn("Cuenta real separada", personal_names)
            self.assertNotIn("Cuenta real separada", demo_names_before)
            self.assertNotIn("Cuenta real separada", demo_names_after)
            self.assertTrue(
                any("Demo Avalancha" in name for name in demo_names_after),
            )


if __name__ == "__main__":
    unittest.main()
