"""Pruebas de privacidad para errores de páginas PySide6."""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from services.error_reporting_service import UserFacingError
from services.account_service import AccountService
from ui_pyside6.pages.base_page import ErrorAwarePage


TARGET_PAGES = (
    "accounts_page.py",
    "budgets_page.py",
    "categories_page.py",
    "debts_page.py",
    "monthly_closure_page.py",
    "movement_page.py",
    "profiles_page.py",
    "reconciliation_page.py",
    "reports_page.py",
)


@pytest.fixture(scope="session")
def app() -> QApplication:
    """Crea una QApplication única para las pruebas UI."""
    return QApplication.instance() or QApplication(sys.argv)


def test_user_facing_error_remains_actionable(
    app: QApplication,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Una validación tipada conserva su mensaje sin generar incidente."""
    _ = app
    monkeypatch.setenv("AVALANCHA_LOG_DIR", str(tmp_path / "logs"))
    page = ErrorAwarePage()
    message = page._value_error_message(
        UserFacingError("El monto debe ser mayor que cero."),
        context="test.validation",
    )
    assert message == "El monto debe ser mayor que cero."
    assert not page.error_reporter.log_path.exists()
    page.deleteLater()


def test_unclassified_value_error_is_sanitized(
    app: QApplication,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Un ValueError técnico no expone su contenido en UI ni diagnóstico."""
    _ = app
    monkeypatch.setenv("AVALANCHA_LOG_DIR", str(tmp_path / "logs"))
    page = ErrorAwarePage()
    sensitive = r"C:\Users\Carlos\finanzas\saldo_987654.json"
    message = page._value_error_message(
        ValueError(sensitive),
        context="test.technical_value_error",
    )
    assert "Código de incidente:" in message
    assert sensitive not in message
    log_text = page.error_reporter.log_path.read_text(encoding="utf-8")
    assert sensitive not in log_text
    page.deleteLater()


def test_account_validation_uses_user_facing_error(tmp_path: Path) -> None:
    """Las validaciones de negocio conservan un tipo público explícito."""
    service = AccountService(data_dir=tmp_path / "data")
    with pytest.raises(UserFacingError, match="nombre de la cuenta"):
        service.crear_cuenta(
            {
                "name": "",
                "account_type": "efectivo",
                "initial_balance": 0,
            },
        )


@pytest.mark.parametrize("filename", TARGET_PAGES)
def test_migrated_pages_do_not_render_raw_exception_text(filename: str) -> None:
    """Las páginas migradas no envían str(exc) directamente a la interfaz."""
    path = Path("ui_pyside6/pages") / filename
    source = path.read_text(encoding="utf-8")
    assert "str(exc)" not in source
    assert "ErrorAwarePage" in source


def test_report_service_does_not_rethrow_raw_duplicate_error() -> None:
    """ReportService no convierte el texto crudo del backend en mensaje público."""
    source = Path("services/report_service.py").read_text(encoding="utf-8")
    assert "raise ValueError(str(exc))" not in source
    assert "Este mes ya posee un reporte oficial." in source
