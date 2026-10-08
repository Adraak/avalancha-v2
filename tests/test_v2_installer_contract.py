"""Contrato del instalador Windows de Avalancha."""

from __future__ import annotations

from pathlib import Path

from avalancha import __version__


PROJECT_ROOT = Path(__file__).resolve().parents[1]
INSTALLER_PATH = PROJECT_ROOT / "packaging" / "Avalancha.iss"
STABLE_APP_ID = "BE6AA14A-2F55-5EAD-8AF9-067C70318BF2"


def _installer_text() -> str:
    """Lee el script Inno Setup versionado."""
    return INSTALLER_PATH.read_text(encoding="utf-8")


def test_installer_has_stable_product_identity() -> None:
    """La identidad de Avalancha no cambia entre actualizaciones."""
    text = _installer_text()

    assert f"AppId={STABLE_APP_ID}" in text
    assert 'AppName={#MyAppName}' in text
    assert '#define MyAppName "Avalancha"' in text


def test_installer_uses_current_technical_app_version() -> None:
    """21B reutiliza la versión técnica existente sin declarar Desktop 1.0."""
    text = _installer_text()

    assert f'#define MyAppVersion "{__version__}"' in text
    assert "AppVersion={#MyAppVersion}" in text
    assert "OutputBaseFilename=Avalancha_Setup_{#MyAppVersion}" in text


def test_installer_targets_x64_windows() -> None:
    """El instalador coincide con la arquitectura x64 del ejecutable frozen."""
    text = _installer_text()

    assert "SetupArchitecture=x64" in text


def test_installer_is_per_user_without_admin() -> None:
    """La aplicación se instala en el espacio del usuario."""
    text = _installer_text()

    assert r"DefaultDirName={localappdata}\Programs\Avalancha" in text
    assert "PrivilegesRequired=lowest" in text


def test_installer_contains_only_the_frozen_application() -> None:
    """El instalador consume el EXE de 21A y no el repositorio ni datos."""
    text = _installer_text()

    assert r'Source: "..\dist\{#MyAppExeName}"' in text
    assert 'DestDir: "{app}"' in text

    for forbidden in (
        "data/perfiles",
        r"data\perfiles",
        "reportes/",
        "reportes\\",
        "config/",
        "config\\",
        "backup/",
        "backup\\",
        "backups/",
        "backups\\",
        "main_v2.py",
        "requirements.txt",
    ):
        assert forbidden not in text


def test_uninstaller_does_not_delete_user_runtime_data() -> None:
    """Desinstalar el programa no incorpora reglas de borrado de datos."""
    text = _installer_text()

    assert "[UninstallDelete]" not in text
    assert r"{localappdata}\Avalancha" not in text
    assert "Uninstallable=yes" in text
    assert "CreateUninstallRegKey=yes" in text


def test_installer_creates_shortcuts_without_making_desktop_mandatory() -> None:
    """Inicio queda disponible y el acceso de escritorio es optativo."""
    text = _installer_text()

    assert r'Name: "{autoprograms}\Avalancha"' in text
    assert 'Name: "desktopicon"' in text
    assert "Flags: unchecked" in text
