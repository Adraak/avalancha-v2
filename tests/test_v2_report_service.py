"""Pruebas del servicio de reportes cifrados V2."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from avalancha.models import (
    CategoryBudget,
    CuentaFinanciera,
    Debt,
    EXPENSE,
    INCOME,
    MonthlyBudget,
    Transaction,
)
from avalancha.storage import BudgetRepository
from services.report_service import ReportService


class ReportServiceTest(unittest.TestCase):
    """Valida generacion, cifrado y lectura interna de reportes."""

    def setUp(self) -> None:
        """Crea un repositorio temporal con datos financieros reales."""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.data_dir = self.root / "data"
        self.reports_dir = self.root / "reportes"
        self.key_path = self.root / "config" / "reporte.key"
        self.repository = BudgetRepository(self.data_dir)
        budget = MonthlyBudget(
            year=2026,
            month=6,
            categories=[
                CategoryBudget("Sueldo", INCOME, 1_000_000, True),
                CategoryBudget("Comida", EXPENSE, 80_000, False),
                CategoryBudget("Servicios", EXPENSE, 0, False),
            ],
            transactions=[
                Transaction(
                    transaction_type=INCOME,
                    category="Sueldo",
                    amount=1_000_000,
                    tx_date="2026-06-01",
                    description="Remuneracion",
                    account_id="cuenta-1",
                ),
                Transaction(
                    transaction_type=EXPENSE,
                    category="Comida",
                    amount=90_000,
                    tx_date="2026-06-02",
                    description="Supermercado",
                    account_id="cuenta-1",
                ),
                Transaction(
                    transaction_type=EXPENSE,
                    category="Servicios",
                    amount=25_000,
                    tx_date="2026-06-03",
                    description="Reparacion",
                    account_id="cuenta-1",
                    is_unexpected=True,
                ),
            ],
        )
        self.repository.save(budget)
        self.repository.save_debts(
            [
                Debt(
                    name="Tarjeta prueba",
                    category="tarjeta_credito",
                    current_balance=500_000,
                    previous_month_balance=600_000,
                    current_monthly_payment=100_000,
                    monthly_interest_rate=2.0,
                ),
            ],
        )
        self.repository.save_accounts(
            [
                CuentaFinanciera(
                    account_id="cuenta-1",
                    name="Cuenta corriente",
                    account_type="cuenta_corriente",
                    initial_balance=0,
                    real_balance=885_000,
                    registered_balance=885_000,
                ),
            ],
        )
        self.service = ReportService(
            data_dir=self.data_dir,
            reports_dir=self.reports_dir,
            key_path=self.key_path,
            repository=self.repository,
        )

    def tearDown(self) -> None:
        """Elimina los archivos temporales."""
        self.temp_dir.cleanup()

    def test_generar_reporte_mensual(self) -> None:
        """Genera contenido estructurado con secciones minimas."""
        report = self.service.generar_reporte_mensual(6, 2026)

        self.assertEqual(report.mes, "2026-06")
        self.assertIn("RESUMEN FINANCIERO", report.contenido)
        self.assertIn("DEUDA", report.contenido)
        self.assertIn("CONCILIACION", report.contenido)
        self.assertIn("DIAGNOSTICO FINANCIERO", report.contenido)
        self.assertIn("$ 1.000.000", report.contenido)

    def test_reporte_incluye_detalle_de_imprevistos(self) -> None:
        """Mantiene la clase Imprevisto dentro del reporte mensual."""
        report = self.service.generar_reporte_mensual(6, 2026)

        self.assertIn("Movimientos imprevistos: 1", report.contenido)
        self.assertIn("Detalle de imprevistos:", report.contenido)
        self.assertIn("Clase: Imprevisto", report.contenido)
        self.assertIn("Reparacion", report.contenido)

    def test_guardar_y_abrir_reporte_cifrado(self) -> None:
        """Guarda cifrado, lista y abre desde la app."""
        report = self.service.generar_reporte_mensual(6, 2026)
        entry = self.service.guardar_reporte_cifrado(
            report,
            "R2026-06.avr",
        )

        opened = self.service.abrir_reporte_cifrado(entry["id"])
        listed = self.service.listar_reportes()
        encrypted = (self.reports_dir / "R2026-06.avr").read_bytes()

        self.assertEqual(opened.mes, "2026-06")
        self.assertIn("AVALANCHA - REPORTE MENSUAL", opened.contenido)
        self.assertEqual(listed[0]["nombre"], "R2026-06.avr")
        self.assertNotIn(b"Sueldo", encrypted)
        self.assertNotIn(b"AVALANCHA", encrypted)

    def test_abrir_por_ruta_de_reporte(self) -> None:
        """Abre un reporte usando su ruta local cifrada."""
        report = self.service.generar_reporte_mensual(6, 2026)
        self.service.guardar_reporte_cifrado(report, "R2026-06.avr")

        opened = self.service.abrir_reporte_cifrado(
            self.reports_dir / "R2026-06.avr",
        )

        self.assertEqual(opened.mes, "2026-06")

    def test_eliminar_reporte(self) -> None:
        """Elimina un reporte y actualiza el indice cifrado."""
        report = self.service.generar_reporte_mensual(6, 2026)
        entry = self.service.guardar_reporte_cifrado(
            report,
            "R2026-06.avr",
        )

        self.service.eliminar_reporte(entry["id"])

        self.assertEqual(self.service.listar_reportes(), [])
        self.assertFalse((self.reports_dir / "R2026-06.avr").exists())

    def test_validaciones(self) -> None:
        """Rechaza mes, nombre, duplicado y archivo no indexado."""
        with self.assertRaisesRegex(ValueError, "mes"):
            self.service.generar_reporte_mensual(13, 2026)

        report = self.service.generar_reporte_mensual(6, 2026)
        with self.assertRaisesRegex(ValueError, "nombre"):
            self.service.guardar_reporte_cifrado(report, "otro.avr")

        self.service.guardar_reporte_cifrado(report, "R2026-06.avr")
        with self.assertRaisesRegex(ValueError, "reporte oficial"):
            self.service.guardar_reporte_cifrado(report, "R2026-06.avr")

        plain = self.reports_dir / "plano.txt"
        plain.write_text("AVALANCHA", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "No se encontro"):
            self.service.abrir_reporte_cifrado(plain)


if __name__ == "__main__":
    unittest.main()
