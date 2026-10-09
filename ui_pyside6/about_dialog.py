"""Dialogo institucional Acerca de Avalancha."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from avalancha import __version__
from ui_pyside6.branding import (
    BrandingAssetResolver,
    ExternalLinkLauncher,
    InstitutionalBranding,
)
from ui_pyside6.theme import LIGHT_THEME, ThemeStyleSheet


class AboutDialog(QDialog):
    """Presenta version, autoria institucional y canales de contacto."""

    LOGO_MAX_WIDTH = 360
    LOGO_MAX_HEIGHT = 220

    def __init__(
        self,
        parent: QWidget | None = None,
        link_launcher: ExternalLinkLauncher | None = None,
        theme_variant: str = LIGHT_THEME,
    ) -> None:
        """Inicializa el dialogo con branding opcional y enlaces publicos."""
        super().__init__(parent)
        self.link_launcher = link_launcher or ExternalLinkLauncher()
        self.theme_variant = theme_variant
        self.logo_path = BrandingAssetResolver.resolve(theme_variant)
        self.setObjectName("AboutDialog")
        self.setWindowTitle("Acerca de Avalancha")
        self.setModal(True)
        self.setMinimumWidth(500)
        self.setStyleSheet(ThemeStyleSheet.about_dialog(theme_variant))
        self._build_ui()

    def _build_ui(self) -> None:
        """Construye un contenido sobrio que funciona aun sin logo."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 28, 32, 24)
        layout.setSpacing(14)

        logo = self._build_logo()
        if logo is not None:
            layout.addWidget(logo, alignment=Qt.AlignmentFlag.AlignCenter)

        title = QLabel("Avalancha")
        title.setObjectName("AboutTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-size: 26px; font-weight: 700;")

        version = QLabel(f"Versión {__version__}")
        version.setObjectName("AboutVersion")
        version.setAlignment(Qt.AlignmentFlag.AlignCenter)

        institutional = QLabel(InstitutionalBranding.PRODUCT_TEXT)
        institutional.setObjectName("InstitutionalBrandingText")
        institutional.setAlignment(Qt.AlignmentFlag.AlignCenter)
        institutional.setStyleSheet("font-size: 14px; font-weight: 600;")

        website = QLabel(InstitutionalBranding.WEBSITE)
        website.setObjectName("InstitutionalWebsite")
        website.setAlignment(Qt.AlignmentFlag.AlignCenter)

        email = QLabel(InstitutionalBranding.EMAIL)
        email.setObjectName("InstitutionalEmail")
        email.setAlignment(Qt.AlignmentFlag.AlignCenter)

        layout.addWidget(title)
        layout.addWidget(version)
        layout.addSpacing(4)
        layout.addWidget(institutional)
        layout.addWidget(website)
        layout.addWidget(email)
        layout.addSpacing(8)
        layout.addLayout(self._build_action_buttons())

        close_buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        close_buttons.rejected.connect(self.reject)
        layout.addWidget(close_buttons)

    def _build_logo(self) -> QLabel | None:
        """Crea el logo disponible o permite degradar a contenido textual."""
        if self.logo_path is None:
            return None
        pixmap = QPixmap(str(self.logo_path))
        if pixmap.isNull():
            return None
        logo = QLabel()
        logo.setObjectName("InstitutionalLogo")
        logo.setPixmap(self._fit_logo(pixmap))
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        return logo

    def _fit_logo(self, pixmap: QPixmap) -> QPixmap:
        """Reduce logos grandes sin ampliar ni alterar su proporcion."""
        native = pixmap.size()
        logical = native
        if (
            native.width() > self.LOGO_MAX_WIDTH
            or native.height() > self.LOGO_MAX_HEIGHT
        ):
            logical = native.scaled(
                self.LOGO_MAX_WIDTH,
                self.LOGO_MAX_HEIGHT,
                Qt.AspectRatioMode.KeepAspectRatio,
            )
        pixel_ratio = (self.parentWidget() or self).devicePixelRatioF()
        target = logical * pixel_ratio
        if target.width() < native.width():
            pixmap = pixmap.scaled(
                target,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        pixmap.setDevicePixelRatio(pixmap.width() / logical.width())
        return pixmap

    def _build_action_buttons(self) -> QHBoxLayout:
        """Construye accesos que no incorporan informacion del usuario."""
        layout = QHBoxLayout()
        layout.setSpacing(8)

        website_button = QPushButton("Abrir sitio web")
        website_button.setObjectName("OpenInstitutionalWebsiteButton")
        website_button.clicked.connect(self.link_launcher.open_website)

        report_button = QPushButton("Reportar un problema")
        report_button.setObjectName("ReportProblemButton")
        report_button.clicked.connect(self.link_launcher.open_report)

        suggestion_button = QPushButton("Enviar sugerencia")
        suggestion_button.setObjectName("SendSuggestionButton")
        suggestion_button.clicked.connect(self.link_launcher.open_suggestion)

        layout.addWidget(website_button)
        layout.addWidget(report_button)
        layout.addWidget(suggestion_button)
        return layout
