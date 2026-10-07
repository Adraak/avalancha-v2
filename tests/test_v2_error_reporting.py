"""Pruebas de diagnóstico local seguro de Avalancha V2."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication, QMessageBox

import main_v2
from core.models.backup import BackupWriteError
from services.backup_service import ProfileBackupService
from services.error_reporting_service import SafeErrorReporter
from services.profile_service import PerfilAplicacion
from services.settings_service import SettingsService
from ui_pyside6.pages.settings_page import SettingsPage


@pytest.fixture(scope="session")
def app() -> QApplication:
    """Crea una QApplication única para pruebas UI."""
    return QApplication.instance() or QApplication(sys.argv)


def test_report_omits_raw_exception_message_and_absolute_path(tmp_path: Path) -> None:
    """El JSONL nunca persiste mensaje, ruta completa ni supuesto secreto."""
    reporter = SafeErrorReporter(tmp_path / "logs")
    secret = "saldo-secreto-987654"
    sensitive_path = r"C:\\Users\\Carlos\\Documentos\\finanzas_privadas.json"
    try:
        raise OSError(f"{sensitive_path} {secret}")
    except OSError as exc:
        notice = reporter.report(
            exc,
            context="test.safe",
            user_message="Ocurrió un error seguro.",
        )

    raw = reporter.log_path.read_text(encoding="utf-8")
    event = json.loads(raw)
    assert notice.incident_id in raw
    assert event["context"] == "test.safe"
    assert event["exception_type"] == "OSError"
    assert sensitive_path not in raw
    assert secret not in raw
    assert "Ocurrió un error seguro." in notice.message
    assert sensitive_path not in notice.message
    assert secret not in notice.message


def test_report_contains_only_safe_traceback_metadata(tmp_path: Path) -> None:
    """Los frames guardan archivo de código, función y línea, no source ni paths."""
    reporter = SafeErrorReporter(tmp_path / "logs")
    try:
        raise RuntimeError("dato que no debe persistirse")
    except RuntimeError as exc:
        reporter.report(exc, context="test.frames", user_message="Fallo técnico.")
    event = json.loads(reporter.log_path.read_text(encoding="utf-8"))
    assert event["frames"]
    frame = event["frames"][-1]
    assert set(frame) == {"module", "function", "line"}
    assert "\\" not in str(frame["module"])
    assert "/" not in str(frame["module"])
    assert "dato que no debe persistirse" not in reporter.log_path.read_text(encoding="utf-8")


def test_log_failure_never_masks_application_error(tmp_path: Path) -> None:
    """Un destino de log imposible no provoca una segunda excepción."""
    blocker = tmp_path / "bloqueo"
    blocker.write_text("archivo", encoding="utf-8")
    reporter = SafeErrorReporter(blocker / "logs")
    exc = OSError("ruta privada")
    notice = reporter.report(
        exc,
        context="test.log_failure",
        user_message="Mensaje seguro.",
    )
    assert "Mensaje seguro." in notice.message
    assert "ruta privada" not in notice.message


def test_settings_backup_error_hides_raw_path(
    app: QApplication,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Un BackupError técnico no expone su ruta original en la interfaz."""
    _ = app
    settings = SettingsService(
        tmp_path / "perfil" / "config",
        tmp_path / "perfil" / "reportes",
        tmp_path / "perfil" / "backup",
    )
    profile = PerfilAplicacion(
        id="personal",
        nombre="Personal",
        raiz=tmp_path / "perfil",
        activo=True,
    )
    backup_service = ProfileBackupService()
    reporter = SafeErrorReporter(tmp_path / "logs")
    raw_path = r"C:\\Users\\Carlos\\datos-financieros.json"

    def fail_backup(*args: object, **kwargs: object) -> object:
        raise BackupWriteError(f"No se pudo escribir {raw_path}")

    monkeypatch.setattr(backup_service, "crear_backup", fail_backup)
    shown: list[str] = []
    monkeypatch.setattr(
        QMessageBox,
        "warning",
        lambda parent, title, message, *args, **kwargs: shown.append(message),
    )
    page = SettingsPage(
        settings,
        profile=profile,
        backup_service=backup_service,
        error_reporter=reporter,
    )
    page.create_backup()
    assert shown
    assert raw_path not in shown[0]
    assert "Código de incidente:" in shown[0]
    log_text = reporter.log_path.read_text(encoding="utf-8")
    assert raw_path not in log_text
    page.deleteLater()


def test_global_exception_hook_uses_safe_notice(
    app: QApplication,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """El hook global informa con código y no muestra el mensaje crudo."""
    _ = app
    reporter = SafeErrorReporter(tmp_path / "logs")
    shown: list[str] = []
    monkeypatch.setattr(
        QMessageBox,
        "critical",
        lambda parent, title, message, *args, **kwargs: shown.append(message),
    )
    previous = sys.excepthook
    try:
        main_v2._instalar_manejador_global(reporter)
        try:
            raise RuntimeError(r"C:\\Users\\Carlos\\secreto.txt")
        except RuntimeError as exc:
            sys.excepthook(type(exc), exc, exc.__traceback__)
    finally:
        sys.excepthook = previous
    assert shown
    assert "Código de incidente:" in shown[0]
    assert "secreto.txt" not in shown[0]
    assert "secreto.txt" not in reporter.log_path.read_text(encoding="utf-8")
