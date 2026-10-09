"""Identidad institucional y enlaces publicos de Avalancha."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Iterable

from PySide6.QtCore import QUrl, QUrlQuery
from PySide6.QtGui import QDesktopServices


class InstitutionalBranding:
    """Centraliza los datos publicos de Antisimetria SpA."""

    COMPANY_NAME = "Antisimetría SpA"
    PRODUCT_TEXT = "Un producto de Antisimetría SpA"
    WEBSITE = "https://antisimetria.cl/"
    EMAIL = "contacto@antisimetria.cl"
    REPORT_SUBJECT = "Avalancha - Reporte de problema"
    SUGGESTION_SUBJECT = "Avalancha - Sugerencia"

    @classmethod
    def website_url(cls) -> QUrl:
        """Construye la URL publica del sitio institucional."""
        return QUrl(cls.WEBSITE)

    @classmethod
    def report_url(cls) -> QUrl:
        """Construye el correo para reportar un problema sin datos privados."""
        return cls._mailto_url(cls.REPORT_SUBJECT)

    @classmethod
    def suggestion_url(cls) -> QUrl:
        """Construye el correo para sugerencias sin datos privados."""
        return cls._mailto_url(cls.SUGGESTION_SUBJECT)

    @classmethod
    def _mailto_url(cls, subject: str) -> QUrl:
        """Crea un destino mailto limitado a correo y asunto publicos."""
        url = QUrl(f"mailto:{cls.EMAIL}")
        query = QUrlQuery()
        query.addQueryItem("subject", subject)
        url.setQuery(query)
        return url


class ExternalLinkLauncher:
    """Abre destinos institucionales mediante la API estandar de Qt."""

    def open_website(self) -> bool:
        """Abre el sitio web de Antisimetria."""
        return QDesktopServices.openUrl(InstitutionalBranding.website_url())

    def open_report(self) -> bool:
        """Abre un correo nuevo para reportar un problema."""
        return QDesktopServices.openUrl(InstitutionalBranding.report_url())

    def open_suggestion(self) -> bool:
        """Abre un correo nuevo para enviar una sugerencia."""
        return QDesktopServices.openUrl(InstitutionalBranding.suggestion_url())


class BrandingAssetResolver:
    """Localiza el logo claro oficial sin hacerlo obligatorio para la UI."""

    RELATIVE_DIRECTORY = Path("assets") / "branding" / "antisimetria"
    FILE_NAMES = {
        "light": "antisimetria_logo_light.png",
    }

    @classmethod
    def resolve(
        cls,
        theme: str,
        roots: Iterable[Path] | None = None,
    ) -> Path | None:
        """Devuelve el logo del tema solicitado o ``None`` si no existe."""
        file_name = cls.FILE_NAMES.get(theme)
        if file_name is None:
            raise ValueError(f"Tema de branding no soportado: {theme}")

        search_roots = tuple(roots) if roots is not None else cls._runtime_roots()
        for root in search_roots:
            candidate = root / cls.RELATIVE_DIRECTORY / file_name
            if candidate.is_file():
                return candidate
        return None

    @staticmethod
    def _runtime_roots() -> tuple[Path, ...]:
        """Obtiene ubicaciones seguras para fuente y ejecutable empaquetado."""
        roots: list[Path] = []
        bundle_root = getattr(sys, "_MEIPASS", None)
        if bundle_root:
            roots.append(Path(bundle_root))
        if getattr(sys, "frozen", False):
            roots.append(Path(sys.executable).resolve().parent)
        roots.append(Path(__file__).resolve().parents[1])
        return tuple(dict.fromkeys(roots))
