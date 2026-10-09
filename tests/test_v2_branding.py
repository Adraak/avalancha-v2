"""Pruebas del branding institucional de Avalancha V2."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
from PySide6.QtCore import QUrlQuery
from PySide6.QtGui import QImage, QImageReader
from PySide6.QtWidgets import QApplication, QFrame, QLabel, QPushButton

from avalancha import __version__
from services.demo_profile_service import DemoProfileService
from services.profile_service import ProfileService
from ui_pyside6.about_dialog import AboutDialog
from ui_pyside6.branding import (
    BrandingAssetResolver,
    ExternalLinkLauncher,
    InstitutionalBranding,
)
from ui_pyside6.main_window import MainWindow
from ui_pyside6.pages.help_page import HelpPage
from ui_pyside6.pages.settings_page import SettingsPage
from ui_pyside6.theme import LIGHT_THEME, ThemeStyleSheet, hoja_estilos


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
PROJECT_ROOT = Path(__file__).resolve().parents[1]
LIGHT_LOGO_NAME = "antisimetria_logo_light.png"
DARK_LOGO_NAME = "antisimetria_logo_dark.png"


@pytest.fixture(scope="session")
def app() -> QApplication:
    """Crea una QApplication unica para las pruebas de widgets."""
    return QApplication.instance() or QApplication(sys.argv)


class RecordingLinkLauncher(ExternalLinkLauncher):
    """Registra acciones externas sin abrir navegador ni correo."""

    def __init__(self) -> None:
        """Inicializa la lista de destinos solicitados."""
        self.calls: list[str] = []

    def open_website(self) -> bool:
        """Registra la apertura del sitio web."""
        self.calls.append("website")
        return True

    def open_report(self) -> bool:
        """Registra la apertura del reporte."""
        self.calls.append("report")
        return True

    def open_suggestion(self) -> bool:
        """Registra la apertura de sugerencias."""
        self.calls.append("suggestion")
        return True


def test_institutional_destinations_are_public_and_exact() -> None:
    """Los destinos contienen solo datos institucionales publicos."""
    assert InstitutionalBranding.website_url().toString() == (
        "https://antisimetria.cl/"
    )

    expected = {
        InstitutionalBranding.REPORT_SUBJECT,
        InstitutionalBranding.SUGGESTION_SUBJECT,
    }
    mail_urls = (
        InstitutionalBranding.report_url(),
        InstitutionalBranding.suggestion_url(),
    )
    subjects = set()
    for url in mail_urls:
        query = QUrlQuery(url)
        assert url.scheme() == "mailto"
        assert url.path() == "contacto@antisimetria.cl"
        assert query.queryItems() == [("subject", query.queryItemValue("subject"))]
        assert not query.hasQueryItem("body")
        subjects.add(query.queryItemValue("subject"))
    assert subjects == expected


def test_about_dialog_uses_canonical_version_and_institutional_text(
    app: QApplication,
) -> None:
    """El dialogo expone version canonica, empresa y datos de contacto."""
    _ = app
    dialog = AboutDialog(link_launcher=RecordingLinkLauncher())
    labels = {label.text() for label in dialog.findChildren(QLabel)}

    assert dialog.windowTitle() == "Acerca de Avalancha"
    assert "Avalancha" in labels
    assert f"Versión {__version__}" in labels
    assert "Un producto de Antisimetría SpA" in labels
    assert "https://antisimetria.cl/" in labels
    assert "contacto@antisimetria.cl" in labels
    dialog.deleteLater()


def test_about_dialog_actions_delegate_without_private_data(
    app: QApplication,
) -> None:
    """Los botones delegan solo en los tres destinos institucionales."""
    _ = app
    launcher = RecordingLinkLauncher()
    dialog = AboutDialog(link_launcher=launcher)
    buttons = {button.text(): button for button in dialog.findChildren(QPushButton)}

    buttons["Abrir sitio web"].click()
    buttons["Reportar un problema"].click()
    buttons["Enviar sugerencia"].click()

    assert launcher.calls == ["website", "report", "suggestion"]
    dialog.deleteLater()


def test_about_dialog_works_without_branding_assets(
    app: QApplication,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """La ausencia de PNG conserva un dialogo textual utilizable."""
    _ = app
    monkeypatch.setattr(BrandingAssetResolver, "resolve", lambda theme: None)

    dialog = AboutDialog(link_launcher=RecordingLinkLauncher())

    assert dialog.logo_path is None
    assert dialog.findChild(QLabel, "InstitutionalLogo") is None
    assert dialog.findChild(QLabel, "InstitutionalBrandingText") is not None
    dialog.deleteLater()


def test_asset_resolver_only_knows_the_light_logo(
    tmp_path: Path,
) -> None:
    """El resolvedor entrega el logo claro e ignora cualquier variante dark."""
    asset_dir = tmp_path / BrandingAssetResolver.RELATIVE_DIRECTORY
    asset_dir.mkdir(parents=True)
    dark_logo = asset_dir / DARK_LOGO_NAME
    light_logo = asset_dir / LIGHT_LOGO_NAME
    dark_logo.touch()
    light_logo.touch()

    assert BrandingAssetResolver.FILE_NAMES == {LIGHT_THEME: LIGHT_LOGO_NAME}
    assert BrandingAssetResolver.resolve(LIGHT_THEME, (tmp_path,)) == light_logo
    with pytest.raises(ValueError):
        BrandingAssetResolver.resolve("dark", (tmp_path,))


def test_real_light_branding_asset_is_a_valid_transparent_png() -> None:
    """El logo claro oficial existe, es PNG y conserva transparencia."""
    expected = (
        PROJECT_ROOT
        / BrandingAssetResolver.RELATIVE_DIRECTORY
        / LIGHT_LOGO_NAME
    )
    resolved = BrandingAssetResolver.resolve(LIGHT_THEME, (PROJECT_ROOT,))
    reader = QImageReader(str(expected))

    assert resolved == expected
    assert reader.canRead()
    assert bytes(reader.format()).lower() == b"png"
    assert reader.size().width() >= HelpPage.LOGO_MAX_WIDTH
    assert reader.size().height() >= HelpPage.LOGO_MAX_HEIGHT
    assert QImage(str(expected)).hasAlphaChannel()


def test_branding_does_not_require_a_dark_logo() -> None:
    """La ausencia del logo dark no afecta al branding oficial."""
    assert DARK_LOGO_NAME not in BrandingAssetResolver.FILE_NAMES.values()
    assert BrandingAssetResolver.resolve(LIGHT_THEME, (PROJECT_ROOT,)) is not None


def test_asset_resolver_returns_none_if_light_logo_is_missing(
    tmp_path: Path,
) -> None:
    """Sin logo claro no hay sustituto: un dark presente no se utiliza."""
    asset_dir = tmp_path / BrandingAssetResolver.RELATIVE_DIRECTORY
    asset_dir.mkdir(parents=True)
    (asset_dir / DARK_LOGO_NAME).touch()

    assert BrandingAssetResolver.resolve(LIGHT_THEME, (tmp_path,)) is None


def test_about_dialog_loads_light_logo_without_distortion(
    app: QApplication,
) -> None:
    """El dialogo carga el logo claro conservando proporcion y limites."""
    _ = app
    dialog = AboutDialog(link_launcher=RecordingLinkLauncher())
    logo = dialog.findChild(QLabel, "InstitutionalLogo")

    assert dialog.logo_path is not None
    assert dialog.logo_path.name == LIGHT_LOGO_NAME
    assert logo is not None
    rendered = logo.pixmap()
    original = QImageReader(str(dialog.logo_path)).size()
    assert rendered is not None
    assert rendered.width() <= AboutDialog.LOGO_MAX_WIDTH
    assert rendered.height() <= AboutDialog.LOGO_MAX_HEIGHT
    if (
        original.width() <= AboutDialog.LOGO_MAX_WIDTH
        and original.height() <= AboutDialog.LOGO_MAX_HEIGHT
    ):
        assert rendered.size() == original
    assert rendered.width() * original.height() == pytest.approx(
        rendered.height() * original.width(),
        abs=max(original.width(), original.height()),
    )
    assert dialog.findChild(QLabel, "InstitutionalBrandingText") is not None
    dialog.deleteLater()


def test_theme_is_light_only() -> None:
    """El tema oficial es claro y no acepta variantes oscuras."""
    assert "background: #f3f5f7" in ThemeStyleSheet.about_dialog()
    assert "background: #f3f6f8" in hoja_estilos()
    with pytest.raises(ValueError):
        ThemeStyleSheet.about_dialog("dark")
    with pytest.raises(ValueError):
        hoja_estilos("dark")


@pytest.mark.parametrize("apariencia", ("Oscuro", "Sistema"))
def test_legacy_appearance_preference_keeps_light_theme(
    app: QApplication,
    tmp_path: Path,
    apariencia: str,
) -> None:
    """Una apariencia historica guardada o recargada mantiene la UI clara."""
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

    settings_page = next(
        window.stack.widget(index)
        for index in range(window.stack.count())
        if isinstance(window.stack.widget(index), SettingsPage)
    )
    labels = {label.text() for label in settings_page.findChildren(QLabel)}
    assert "Apariencia" not in labels

    settings_page.apariencia_combo.setCurrentText(apariencia)
    settings_page.save()
    assert (
        window.settings_service.cargar_configuracion().apariencia
        == apariencia.lower()
    )
    window.close()

    window = MainWindow(profile_service, demo_service)

    assert window.current_theme == LIGHT_THEME
    assert window.styleSheet() == hoja_estilos()
    assert "background: #0b1118" not in window.styleSheet()
    assert window.help_page is not None
    assert window.help_page.theme_variant == LIGHT_THEME
    assert window.help_page.logo_path is not None
    assert window.help_page.logo_path.name == LIGHT_LOGO_NAME
    window.close()


def test_main_window_exposes_integrated_help_section_and_branding(
    app: QApplication,
    tmp_path: Path,
) -> None:
    """Ayuda vive en la navegación lateral y no en una barra nativa."""
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

    labels = [button.text() for button in window.navigation_buttons]
    branding = window.findChild(QLabel, "InstitutionalStatusText")

    assert "Ayuda y soporte" in labels
    assert not hasattr(window, "help_menu")
    assert isinstance(window.help_page, HelpPage)
    assert branding is not None
    assert branding.text() == "Un producto de Antisimetría SpA"
    window.close()


def test_help_page_uses_official_light_logo_within_limits(
    app: QApplication,
) -> None:
    """La página integrada muestra el logo claro sin ampliarlo ni deformarlo."""
    _ = app
    page = HelpPage(link_launcher=RecordingLinkLauncher())
    rendered = page.logo_label.pixmap()
    original = QImageReader(str(page.logo_path)).size()
    logical = rendered.deviceIndependentSize()

    assert page.theme_variant == LIGHT_THEME
    assert page.logo_path is not None
    assert page.logo_path.name == LIGHT_LOGO_NAME
    assert logical.width() <= HelpPage.LOGO_MAX_WIDTH
    assert logical.height() <= HelpPage.LOGO_MAX_HEIGHT
    assert rendered.width() <= original.width()
    assert rendered.height() <= original.height()
    assert rendered.width() * original.height() == pytest.approx(
        rendered.height() * original.width(),
        abs=max(original.width(), original.height()),
    )
    page.deleteLater()


def _minimum_size_window(app: QApplication, tmp_path: Path) -> MainWindow:
    """Abre la ventana principal en el tamaño mínimo declarado."""
    profile_service = ProfileService(
        profiles_root=tmp_path / "perfiles",
        legacy_data_dir=tmp_path / "legacy_data",
        legacy_reports_dir=tmp_path / "legacy_reports",
        legacy_config_dir=tmp_path / "legacy_config",
    )
    demo_service = DemoProfileService(profile_service)
    demo_service.abrir_demo()
    window = MainWindow(profile_service, demo_service)
    window.resize(window.minimumSize())
    window.show()
    app.processEvents()
    return window


def test_help_page_is_fully_reachable_at_minimum_window_size(
    app: QApplication,
    tmp_path: Path,
) -> None:
    """A 980 × 640 el logo no se recorta y todo el contenido es alcanzable."""
    window = _minimum_size_window(app, tmp_path)
    page = window.help_page
    assert page is not None
    window._select_section(window.stack.indexOf(page))
    app.processEvents()

    assert (window.width(), window.height()) == (980, 640)
    logo_size = page.logo_label.pixmap().deviceIndependentSize()
    assert page.logo_label.width() >= logo_size.width()
    assert page.logo_label.height() >= logo_size.height()

    content = page.scroll_area.widget()
    viewport = page.scroll_area.viewport()
    assert content.height() >= content.minimumSizeHint().height()
    scroll_bar = page.scroll_area.verticalScrollBar()
    assert scroll_bar.maximum() == max(0, content.height() - viewport.height())
    for widget in (
        *page.findChildren(QLabel),
        *page.findChildren(QPushButton),
    ):
        assert widget.height() >= widget.minimumSizeHint().height()
        page.scroll_area.ensureWidgetVisible(widget, 0, 0)
        app.processEvents()
        assert not widget.visibleRegion().isEmpty()
    window.close()


def test_side_navigation_is_fully_reachable_at_minimum_window_size(
    app: QApplication,
    tmp_path: Path,
) -> None:
    """A 980 × 640 cada sección es alcanzable y el perfil sigue visible."""
    window = _minimum_size_window(app, tmp_path)
    viewport = window.navigation_scroll.viewport()

    assert [button.text() for button in window.navigation_buttons] == [
        "Resumen",
        "Movimientos",
        "Cuentas",
        "Presupuestos",
        "Categorías",
        "Deudas",
        "Reportes",
        "Cierre mensual",
        "Conciliacion",
        "Perfiles",
        "Configuración",
        "Ayuda y soporte",
    ]
    for index, button in enumerate(window.navigation_buttons):
        assert button.height() >= button.sizeHint().height()
        window._select_section(index)
        app.processEvents()
        top = button.mapTo(viewport, button.rect().topLeft()).y()
        assert top >= 0
        assert top + button.height() <= viewport.height()

    badge = window.findChild(QFrame, "ProfileBadge")
    assert badge is not None
    assert badge.visibleRegion().boundingRect().size() == badge.size()
    for label in badge.findChildren(QLabel):
        assert "\n" not in label.text()
        assert not label.wordWrap()
        assert label.height() >= label.sizeHint().height()
    assert [label.text() for label in badge.findChildren(QLabel)] == [
        "Perfil:",
        window.profile_name,
    ]
    window.close()
