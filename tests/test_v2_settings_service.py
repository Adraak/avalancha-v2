"""Pruebas de configuracion por perfil para Avalancha V2."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from avalancha.models import (
    CategoryBudget,
    CuentaFinanciera,
    INCOME,
    MonthlyBudget,
    Transaction,
)
from avalancha.storage import BudgetRepository
from services.profile_service import ProfileService
from services.report_service import ReportService
from services.settings_service import SettingsService


class SettingsServiceTest(unittest.TestCase):
    """Valida lectura, guardado y aislamiento de configuracion."""

    def setUp(self) -> None:
        """Crea carpetas temporales para pruebas aisladas."""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.service = SettingsService(
            config_dir=self.root / "config",
            reports_dir=self.root / "reportes",
            backup_dir=self.root / "backup",
        )

    def tearDown(self) -> None:
        """Elimina archivos temporales creados por la prueba."""
        self.temp_dir.cleanup()

    def test_cargar_configuracion_por_defecto(self) -> None:
        """Carga CLP, tema claro y rutas base si no existe archivo."""
        config = self.service.cargar_configuracion()

        self.assertEqual(config.moneda_principal, "CLP")
        self.assertEqual(config.apariencia, "claro")
        self.assertTrue(config.cifrado_reportes)
        self.assertEqual(config.carpeta_reportes, self.root / "reportes")
        self.assertEqual(config.carpeta_respaldo, self.root / "backup")

    def test_guardar_configuracion(self) -> None:
        """Persiste configuracion y crea carpetas configuradas."""
        reports = self.root / "salida_reportes"
        backup = self.root / "salida_backup"

        saved = self.service.guardar_configuracion(
            {
                "carpeta_reportes": reports,
                "moneda_principal": "USD",
                "apariencia": "oscuro",
                "cifrado_reportes": False,
                "carpeta_respaldo": backup,
                "sincronizacion_habilitada": True,
            },
        )
        loaded = self.service.cargar_configuracion()

        self.assertEqual(saved.moneda_principal, "USD")
        self.assertEqual(loaded.apariencia, "oscuro")
        self.assertFalse(loaded.cifrado_reportes)
        self.assertTrue(loaded.sincronizacion_habilitada)
        self.assertTrue(reports.is_dir())
        self.assertTrue(backup.is_dir())

    def test_configuraciones_en_directorios_distintos_no_se_mezclan(self) -> None:
        """Verifica el aislamiento total entre dos instancias con rutas diferentes."""
        dir1 = self.root / "service1"
        dir2 = self.root / "service2"
        for d in [dir1, dir2]:
            (d / "config").mkdir(parents=True, exist_ok=True)
            (d / "reportes").mkdir(parents=True, exist_ok=True)
            (d / "backup").mkdir(parents=True, exist_ok=True)

        s1 = SettingsService(dir1/"config", dir1/"reportes", dir1/"backup")
        s2 = SettingsService(dir2/"config", dir2/"reportes", dir2/"pathname_error_placeholder") # logic error in placeholder but let's use real paths
        # Let's refine the addresses to be safer
        s2 = SettingsService(dir2/"config", dir2/"reportes", dir2/"backup")

        s1.guardar_configuracion({
            "carpeta_reportes": dir1 / "rep",
            "moneda_principal": "CLP",
            "apariencia": "claro",
            "carpeta_respaldo": dir1 / "bak"
        })
        s2.guardar_configuracion({
            "carpeta_reportes": dir2 / "rep",
            "moneda_principal": "USD",
            "apariencia": "oscuro",
            "carpeta_respaldo": dir2 / "bak"
        })

        c1 = s1.cargar_configuracion()
        c2 = s2.cargar_configuracion()

        self.assertEqual(c1.moneda_principal, "CLP")
        self.assertEqual(c2.moneda_principal, "USD")
        self.assertEqual(c1.apariencia, "claro")
        self.assertEqual(c2.apariencia, "oscuro")
        self.assertNotEqual(c1.carpeta_reportes, c2.carpeta_reportes)


    def test_report_service_usa_carpeta_configurada(self) -> None:
        """Genera reporte cifrado en la carpeta configurada."""
        reports = self.root / "reportes_configurados"
        config = self.service.guardar_configuracion(
            {
                "carpeta_reportes": reports,
                "moneda_principal": "CLP",
                "apariencia": "claro",
                "cifrado_reportes": False,
                "carpeta_respaldo": self.root / "backup",
            },
        )
        repository = self._crear_repositorio_con_datos()
        report_service = ReportService(
            data_dir=self.root / "data",
            reports_dir=config.carpeta_reportes,
            key_path=self.root / "config" / "reporte.key",
            repository=repository,
        )

        report = report_service.generar_reporte_mensual(6, 2026)
        entry = report_service.guardar_reporte_cifrado(report, "R2026-06.avr")
        encrypted = (reports / "R2026-06.avr").read_bytes()

        self.assertEqual(report_service.obtener_ruta_reportes(), reports)
        self.assertEqual(Path(entry["ruta"]).parent, Path("."))
        self.assertTrue((reports / "R2026-06.avr").exists())
        self.assertNotIn(b"AVALANCHA", encrypted)
        self.assertNotIn(b"Sueldo", encrypted)

    def test_validar_carpeta_reportes(self) -> None:
        """Rechaza una ruta de reportes que apunta a un archivo."""
        invalid = self.root / "archivo.txt"
        invalid.write_text("contenido", encoding="utf-8")

        with self.assertRaisesRegex(ValueError, "reportes"):
            self.service.guardar_configuracion(
                {
                    "carpeta_reportes": invalid,
                    "moneda_principal": "CLP",
                    "apariencia": "claro",
                    "carpeta_respaldo": self.root / "backup",
                },
            )

    def test_validar_moneda_principal(self) -> None:
        """Rechaza monedas no soportadas en esta etapa."""
        with self.assertRaisesRegex(ValueError, "moneda"):
            self.service.guardar_configuracion(
                {
                    "carpeta_reportes": self.root / "reportes",
                    "moneda_principal": "BTC",
                    "apariencia": "claro",
                    "carpeta_respaldo": self.root / "backup",
                },
            )

    def test_aislamiento_por_perfil(self) -> None:
        """Guarda configuraciones distintas para Personal y Demo."""
        profile_service = ProfileService(
            profiles_root=self.root / "perfiles",
            legacy_data_dir=self.root / "legacy_data",
            legacy_reports_dir=self.root / "legacy_reports",
            legacy_config_dir=self.root / "legacy_config",
        )
        personal = profile_service.obtener_perfil("personal")
        demo = profile_service.asegurar_demo_registrado()
        personal_service = SettingsService(
            personal.config_dir,
            personal.reports_dir,
            personal.raiz / "backup",
        )
        demo_service = SettingsService(
            demo.config_dir,
            demo.reports_dir,
            demo.raiz / "backup",
        )

        personal_service.guardar_configuracion(
            {
                "carpeta_reportes": personal.raiz / "reportes_personales",
                "moneda_principal": "CLP",
                "apariencia": "claro",
                "carpeta_respaldo": personal.raiz / "backup_personal",
            },
        )
        demo_service.guardar_configuracion(
            {
                "carpeta_reportes": demo.raiz / "reportes_demo",
                "moneda_principal": "USD",
                "apariencia": "oscuro",
                "carpeta_respaldo": demo.raiz / "backup_demo",
            },
        )

        self.assertNotEqual(
            personal_service.cargar_configuracion().carpeta_reportes,
            demo_service.cargar_configuracion().carpeta_reportes,
        )
        self.assertEqual(
            personal_service.cargar_configuracion().moneda_principal,
            "CLP",
        )
        self.assertEqual(
            demo_service.cargar_configuracion().moneda_principal,
            "USD",
        )

    def test_settings_page_no_accede_a_storage(self) -> None:
        """Verifica que la UI no importe almacenamiento directo."""
        page = Path("ui_pyside6/pages/settings_page.py").read_text(
            encoding="utf-8",
        )
        self.assertNotIn("BudgetRepository", page)
        self.assertNotIn("avalancha.storage", page)

    def test_validar_apariencia_no_soportada(self) -> None:
        """Verifica que se lanza error ante apariencia no soportada."""
        with self.assertRaisesRegex(ValueError, "apariencia.*no esta soportada"):
            self.service.guardar_configuracion(
                {
                    "carpeta_reportes": self.root / "rep",
                    "moneda_principal": "CLP",
                    "apariencia": "neon",
                    "carpeta_respaldo": self.root / "bak",
                },
            )

    def test_validar_carpeta_respaldo_no_puede_ser_archivo(self) -> None:
        """Verifica que se lanza error si la carpeta de respaldo es un archivo."""
        archivo_invalido = self.root / "backup_invalido.txt"
        archivo_invalido.write_text("contenido", encoding="utf-8")

        with self.assertRaisesRegex(ValueError, "La carpeta de respaldo no es valida"):
            self.service.guardar_configuracion({
                "carpeta_reportes": self.root / "rep",
                "moneda_principal": "CLP",
                "apariencia": "claro",
                "carpeta_respaldo": archivo_invalido,
            })



    def _crear_repositorio_con_datos(self) -> BudgetRepository:
        """Crea un repositorio minimo para generar reportes."""
        repository = BudgetRepository(self.root / "data")
        repository.save(
            MonthlyBudget(
                year=2026,
                month=6,
                categories=[
                    CategoryBudget("Sueldo", INCOME, 1_000_000, True),
                ],
                transactions=[
                    Transaction(
                        transaction_type=INCOME,
                        category="Sueldo",
                        amount=1_000_000,
                        tx_date="2026-06-01",
                        description="Remuneracion",
                    ),
                ],
            ),
        )
        repository.save_accounts(
            [
                CuentaFinanciera(
                    account_id="cuenta-1",
                    name="Cuenta prueba",
                    account_type="cuenta_corriente",
                    real_balance=1_000_000,
                    registered_balance=1_000_000,
                ),
            ],
        )
        repository.save_debts([])
        return repository


if __name__ == "__main__":
    unittest.main()
