"""Página integrada de ayuda y soporte institucional de Avalancha."""

from __future__ import annotations

from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QPixmap, QShowEvent
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from avalancha import __version__
from ui_pyside6.branding import (
    BrandingAssetResolver,
    ExternalLinkLauncher,
    InstitutionalBranding,
)
from ui_pyside6.theme import LIGHT_THEME


class HelpPage(QWidget):
    """Muestra ayuda, soporte e identidad institucional dentro del chasis."""

    LOGO_MAX_WIDTH = 360
    LOGO_MAX_HEIGHT = 220

    def __init__(
        self,
        link_launcher: ExternalLinkLauncher | None = None,
        theme_variant: str = LIGHT_THEME,
    ) -> None:
        """Inicializa la página institucional integrada."""
        super().__init__()
        self.link_launcher = link_launcher or ExternalLinkLauncher()
        self.theme_variant = theme_variant
        self.logo_path = None
        self._logo_pixel_ratio = 1.0
        self.logo_label = QLabel()
        self.logo_label.setObjectName("InstitutionalLogo")
        self.logo_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._build_ui()
        self.set_theme_variant(theme_variant)

    def _build_ui(self) -> None:
        """Construye una página de soporte sobria y coherente con Avalancha."""
        content = QWidget()
        content.setObjectName("HelpContent")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(28, 28, 28, 10)
        layout.setSpacing(16)

        title = QLabel("Ayuda y soporte")
        title.setObjectName("PageTitle")

        subtitle = QLabel(
            "Información de Avalancha, soporte y canales oficiales de contacto."
        )
        subtitle.setObjectName("PageSubtitle")
        subtitle.setWordWrap(True)

        card = QFrame()
        card.setObjectName("SupportCard")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(28, 24, 28, 24)
        card_layout.setSpacing(12)

        card_layout.addWidget(
            self.logo_label,
            alignment=Qt.AlignmentFlag.AlignCenter,
        )

        product = QLabel("Avalancha")
        product.setObjectName("SupportProductTitle")
        product.setAlignment(Qt.AlignmentFlag.AlignCenter)

        version = QLabel(f"Versión {__version__}")
        version.setObjectName("SupportVersion")
        version.setAlignment(Qt.AlignmentFlag.AlignCenter)

        institutional = QLabel(InstitutionalBranding.PRODUCT_TEXT)
        institutional.setObjectName("InstitutionalBrandingText")
        institutional.setAlignment(Qt.AlignmentFlag.AlignCenter)

        website = QLabel(InstitutionalBranding.WEBSITE)
        website.setObjectName("InstitutionalWebsite")
        website.setAlignment(Qt.AlignmentFlag.AlignCenter)

        email = QLabel(InstitutionalBranding.EMAIL)
        email.setObjectName("InstitutionalEmail")
        email.setAlignment(Qt.AlignmentFlag.AlignCenter)

        card_layout.addWidget(product)
        card_layout.addWidget(version)
        card_layout.addWidget(institutional)
        card_layout.addWidget(website)
        card_layout.addWidget(email)

        actions = QHBoxLayout()
        actions.setSpacing(10)

        website_button = QPushButton("Abrir sitio web")
        website_button.setObjectName("OpenInstitutionalWebsiteButton")
        website_button.clicked.connect(self.link_launcher.open_website)

        report_button = QPushButton("Reportar un problema")
        report_button.setObjectName("ReportProblemButton")
        report_button.clicked.connect(self.link_launcher.open_report)

        suggestion_button = QPushButton("Enviar sugerencia")
        suggestion_button.setObjectName("SendSuggestionButton")
        suggestion_button.clicked.connect(self.link_launcher.open_suggestion)

        actions.addStretch(1)
        actions.addWidget(website_button)
        actions.addWidget(report_button)
        actions.addWidget(suggestion_button)
        actions.addStretch(1)
        card_layout.addLayout(actions)

        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addWidget(card)
        layout.addStretch(1)

        self.scroll_area = QScrollArea()
        self.scroll_area.setObjectName("HelpScroll")
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_area.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff,
        )
        self.scroll_area.setWidget(content)

        page_layout = QVBoxLayout(self)
        page_layout.setContentsMargins(0, 0, 0, 0)
        page_layout.addWidget(self.scroll_area)

    def set_theme_variant(self, theme_variant: str) -> None:
        """Carga el logo institucional del tema claro oficial."""
        self.theme_variant = theme_variant
        self.logo_path = BrandingAssetResolver.resolve(theme_variant)
        self.logo_label.clear()
        self.logo_label.setVisible(False)
        if self.logo_path is None:
            return
        pixmap = QPixmap(str(self.logo_path))
        if pixmap.isNull():
            return
        self._logo_pixel_ratio = self.devicePixelRatioF()
        self.logo_label.setPixmap(self._fit_logo(pixmap))
        self.logo_label.setVisible(True)

    def _fit_logo(self, pixmap: QPixmap) -> QPixmap:
        """Reduce el logo a los píxeles físicos de la pantalla sin ampliarlo."""
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
        target = logical * self._logo_pixel_ratio
        if target.width() < native.width():
            pixmap = pixmap.scaled(
                target,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        pixmap.setDevicePixelRatio(pixmap.width() / logical.width())
        return pixmap

    def showEvent(self, event: QShowEvent) -> None:
        """Ajusta el logo a la densidad real de la pantalla al mostrarse."""
        super().showEvent(event)
        self._refresh_logo_for_screen()

    def event(self, event: QEvent) -> bool:
        """Vuelve a ajustar el logo si la ventana cambia de densidad."""
        if event.type() == QEvent.Type.DevicePixelRatioChange:
            self._refresh_logo_for_screen()
        return super().event(event)

    def _refresh_logo_for_screen(self) -> None:
        """Regenera el logo solo si cambió la densidad de píxeles."""
        if self.devicePixelRatioF() != self._logo_pixel_ratio:
            self.set_theme_variant(self.theme_variant)
