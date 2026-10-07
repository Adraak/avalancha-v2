"""Pruebas de integración UI para respaldo y restauración 18F."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox

from core.models.backup import BackupValidationError, RestoreApplyError
from services.backup_service import BackupValidator, ProfileBackupService
from services.error_reporting_service import SafeErrorReporter
from services.demo_profile_service import DemoProfileService
from services.profile_restore_service import ProfileRestoreService
from services.profile_service import PerfilAplicacion, ProfileService
from services.settings_service import SettingsService
from ui_pyside6.main_window import MainWindow
from ui_pyside6.pages.settings_page import SettingsPage

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="session")
def app() -> QApplication:
    """Crea una QApplication única para widgets."""
    return QApplication.instance() or QApplication(sys.argv)


@pytest.fixture()
def service(tmp_path: Path) -> SettingsService:
    """Entrega configuración aislada."""
    return SettingsService(
        tmp_path / "config",
        tmp_path / "reportes",
        tmp_path / "backup",
    )


@pytest.fixture()
def profile(tmp_path: Path) -> PerfilAplicacion:
    """Entrega un perfil aislado."""
    return PerfilAplicacion(
        id="personal",
        nombre="Personal",
        raiz=tmp_path / "perfil",
        activo=True,
    )


def test_actions_disabled_without_profile(
    app: QApplication,
    service: SettingsService,
) -> None:
    """Sin perfil las operaciones con efectos quedan deshabilitadas."""
    _ = app
    page = SettingsPage(service)
    assert not page.create_backup_button.isEnabled()
    assert not page.restore_backup_button.isEnabled()
    page.deleteLater()


def test_create_backup_delegates_to_service(
    app: QApplication,
    service: SettingsService,
    profile: PerfilAplicacion,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Crear respaldo usa exactamente el perfil y SettingsService activos."""
    _ = app
    backup_service = ProfileBackupService()
    expected = tmp_path / "backup" / "Avalancha_personal.zip"
    calls: list[tuple[PerfilAplicacion, SettingsService]] = []

    def fake_create(
        current_profile: PerfilAplicacion,
        current_service: SettingsService,
    ) -> SimpleNamespace:
        calls.append((current_profile, current_service))
        return SimpleNamespace(zip_path=expected)

    monkeypatch.setattr(backup_service, "crear_backup", fake_create)
    monkeypatch.setattr(
        QMessageBox,
        "information",
        lambda *args, **kwargs: QMessageBox.StandardButton.Ok,
    )
    page = SettingsPage(
        service,
        profile=profile,
        backup_service=backup_service,
    )
    page.create_backup()
    assert calls == [(profile, service)]
    assert str(expected) in page.estado_label.text()
    page.deleteLater()


def test_invalid_backup_is_rejected_before_restore(
    app: QApplication,
    service: SettingsService,
    profile: PerfilAplicacion,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Un ZIP inválido nunca alcanza ProfileRestoreService."""
    _ = app
    validator = BackupValidator()
    restore_service = ProfileRestoreService()
    selected = tmp_path / "invalido.zip"
    restore_calls: list[Path] = []
    errors: list[str] = []
    reporter = SafeErrorReporter(tmp_path / "logs")
    monkeypatch.setattr(
        QFileDialog,
        "getOpenFileName",
        lambda *args, **kwargs: (str(selected), "Respaldos ZIP (*.zip)"),
    )
    monkeypatch.setattr(
        validator,
        "validar_backup",
        lambda *args, **kwargs: SimpleNamespace(
            valid=False,
            error=BackupValidationError(
                r"Respaldo inválido en C:\Users\Carlos\privado.zip",
            ),
        ),
    )
    monkeypatch.setattr(
        restore_service,
        "restaurar",
        lambda path, current_profile: restore_calls.append(path),
    )
    page = SettingsPage(
        service,
        profile=profile,
        backup_validator=validator,
        restore_service=restore_service,
        error_reporter=reporter,
    )
    monkeypatch.setattr(page, "_show_backup_error", errors.append)
    page.restore_backup()
    assert len(errors) == 1
    assert errors[0].startswith(
        "El respaldo seleccionado no es válido o no corresponde al perfil activo.",
    )
    assert "Código de incidente:" in errors[0]
    assert "C:\\Users\\Carlos" not in errors[0]
    assert restore_calls == []
    page.deleteLater()


def test_cancelled_restore_has_no_effect(
    app: QApplication,
    service: SettingsService,
    profile: PerfilAplicacion,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """La respuesta No conserva el perfil sin invocar restauración."""
    _ = app
    validator = BackupValidator()
    restore_service = ProfileRestoreService()
    selected = tmp_path / "valido.zip"
    calls: list[Path] = []
    monkeypatch.setattr(
        QFileDialog,
        "getOpenFileName",
        lambda *args, **kwargs: (str(selected), "Respaldos ZIP (*.zip)"),
    )
    monkeypatch.setattr(
        validator,
        "validar_backup",
        lambda *args, **kwargs: SimpleNamespace(valid=True, error=None),
    )
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *args, **kwargs: QMessageBox.StandardButton.No,
    )
    monkeypatch.setattr(
        restore_service,
        "restaurar",
        lambda path, current_profile: calls.append(path),
    )
    page = SettingsPage(
        service,
        profile=profile,
        backup_validator=validator,
        restore_service=restore_service,
    )
    page.restore_backup()
    assert calls == []
    page.deleteLater()


def test_successful_restore_emits_profile_restored(
    app: QApplication,
    service: SettingsService,
    profile: PerfilAplicacion,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Una restauración aplicada emite la señal de reconstrucción."""
    _ = app
    validator = BackupValidator()
    restore_service = ProfileRestoreService()
    selected = tmp_path / "valido.zip"
    calls: list[tuple[Path, PerfilAplicacion]] = []
    emitted: list[bool] = []
    monkeypatch.setattr(
        QFileDialog,
        "getOpenFileName",
        lambda *args, **kwargs: (str(selected), "Respaldos ZIP (*.zip)"),
    )
    monkeypatch.setattr(
        validator,
        "validar_backup",
        lambda *args, **kwargs: SimpleNamespace(valid=True, error=None),
    )

    def fake_restore(
        path: Path,
        current_profile: PerfilAplicacion,
    ) -> SimpleNamespace:
        calls.append((path, current_profile))
        return SimpleNamespace(
            outcome="APPLIED",
            error=None,
            staging_dir=None,
        )

    monkeypatch.setattr(restore_service, "restaurar", fake_restore)
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *args, **kwargs: QMessageBox.StandardButton.Yes,
    )
    monkeypatch.setattr(
        QMessageBox,
        "information",
        lambda *args, **kwargs: QMessageBox.StandardButton.Ok,
    )
    page = SettingsPage(
        service,
        profile=profile,
        backup_validator=validator,
        restore_service=restore_service,
    )
    page.profile_restored.connect(lambda: emitted.append(True))
    page.restore_backup()
    assert calls == [(selected, profile)]
    assert emitted == [True]
    assert page.estado_label.text() == "Respaldo restaurado correctamente."
    page.deleteLater()


def test_successful_rollback_is_reported_as_safe_failure(
    app: QApplication,
    service: SettingsService,
    profile: PerfilAplicacion,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Un rollback exitoso se informa sin fingir restauración exitosa."""
    _ = app
    validator = BackupValidator()
    restore_service = ProfileRestoreService()
    selected = tmp_path / "valido.zip"
    warnings: list[str] = []
    reporter = SafeErrorReporter(tmp_path / "logs")
    monkeypatch.setattr(
        QFileDialog,
        "getOpenFileName",
        lambda *args, **kwargs: (str(selected), "Respaldos ZIP (*.zip)"),
    )
    monkeypatch.setattr(
        validator,
        "validar_backup",
        lambda *args, **kwargs: SimpleNamespace(valid=True, error=None),
    )
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *args, **kwargs: QMessageBox.StandardButton.Yes,
    )
    monkeypatch.setattr(
        QMessageBox,
        "warning",
        lambda parent, title, message, *args, **kwargs: warnings.append(message),
    )
    monkeypatch.setattr(
        restore_service,
        "restaurar",
        lambda *args, **kwargs: SimpleNamespace(
            outcome="FAILED_ROLLBACK_OK",
            error=RestoreApplyError(
                r"Falla simulada en C:\Users\Carlos\privado.json",
            ),
            staging_dir=None,
        ),
    )
    page = SettingsPage(
        service,
        profile=profile,
        backup_validator=validator,
        restore_service=restore_service,
        error_reporter=reporter,
    )
    page.restore_backup()
    assert "revertidos correctamente" in page.estado_label.text()
    assert warnings
    assert "estado anterior" in warnings[0]
    assert "Código de incidente:" in warnings[0]
    assert "C:\\Users\\Carlos" not in warnings[0]
    page.deleteLater()


def test_failed_rollback_is_critical_and_preserves_evidence_path(
    app: QApplication,
    service: SettingsService,
    profile: PerfilAplicacion,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Rollback incompleto se informa como condición crítica."""
    _ = app
    validator = BackupValidator()
    restore_service = ProfileRestoreService()
    selected = tmp_path / "valido.zip"
    staging = tmp_path / "staging_evidencia"
    critical: list[str] = []
    reporter = SafeErrorReporter(tmp_path / "logs")
    monkeypatch.setattr(
        QFileDialog,
        "getOpenFileName",
        lambda *args, **kwargs: (str(selected), "Respaldos ZIP (*.zip)"),
    )
    monkeypatch.setattr(
        validator,
        "validar_backup",
        lambda *args, **kwargs: SimpleNamespace(valid=True, error=None),
    )
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *args, **kwargs: QMessageBox.StandardButton.Yes,
    )
    monkeypatch.setattr(
        QMessageBox,
        "critical",
        lambda parent, title, message, *args, **kwargs: critical.append(message),
    )
    monkeypatch.setattr(
        restore_service,
        "restaurar",
        lambda *args, **kwargs: SimpleNamespace(
            outcome="FAILED_ROLLBACK_FAILED",
            error=RestoreApplyError(
                r"Falla simulada en C:\Users\Carlos\privado.json",
            ),
            staging_dir=staging,
        ),
    )
    page = SettingsPage(
        service,
        profile=profile,
        backup_validator=validator,
        restore_service=restore_service,
        error_reporter=reporter,
    )
    page.restore_backup()
    assert "rollback incompleto" in page.estado_label.text()
    assert critical
    assert str(staging) not in critical[0]
    assert "Se conservó evidencia técnica local" in critical[0]
    assert "Código de incidente:" in critical[0]
    assert "C:\\Users\\Carlos" not in critical[0]
    page.deleteLater()


def test_main_window_injects_active_profile_and_reloads_after_restore(
    app: QApplication,
    tmp_path: Path,
) -> None:
    """MainWindow conecta Configuración con el perfil y reconstruye tras restore."""
    _ = app
    profile_service = ProfileService(
        profiles_root=tmp_path / "perfiles",
        legacy_data_dir=tmp_path / "legacy_data",
        legacy_reports_dir=tmp_path / "legacy_reports",
        legacy_config_dir=tmp_path / "legacy_config",
    )
    demo_service = DemoProfileService(profile_service)
    demo_service.abrir_demo()
    window = MainWindow(profile_service, demo_service)
    previous = next(
        widget
        for index in range(window.stack.count())
        if isinstance((widget := window.stack.widget(index)), SettingsPage)
    )
    assert previous.profile is not None
    assert previous.profile.id == profile_service.obtener_activo().id
    previous_id = previous.profile.id
    previous.profile_restored.emit()
    current = next(
        widget
        for index in range(window.stack.count())
        if isinstance((widget := window.stack.widget(index)), SettingsPage)
    )
    assert current is not previous
    assert current.profile is not None
    assert current.profile.id == previous_id
    window.close()
