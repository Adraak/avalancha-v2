"""Pruebas de configuracion por perfil para Avalancha V2."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from services.profile_service import ProfileService
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


if __name__ == "__main__":
    unittest.main()
