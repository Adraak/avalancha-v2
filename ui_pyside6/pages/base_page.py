"""Página base para secciones pendientes de migración."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from services.error_reporting_service import SafeErrorReporter, UserFacingError


class ErrorAwarePage(QWidget):
    """Base para páginas que distinguen validación de fallo técnico."""

    def __init__(self) -> None:
        """Inicializa reporte técnico local sin escribir hasta un incidente."""
        super().__init__()
        self.error_reporter = SafeErrorReporter()

    def _value_error_message(
        self,
        exc: ValueError,
        *,
        context: str,
        fallback: str = "No fue posible completar la operación.",
    ) -> str:
        """Devuelve validación pública o registra un ValueError técnico."""
        if isinstance(exc, UserFacingError):
            return str(exc)
        return self._technical_error(exc, context=context, fallback=fallback)

    def _technical_error(
        self,
        exc: BaseException,
        *,
        context: str,
        fallback: str,
    ) -> str:
        """Registra un fallo técnico sin exponer su contenido crudo."""
        notice = self.error_reporter.report(
            exc,
            context=context,
            user_message=fallback,
        )
        return notice.message


class PlaceholderPage(QWidget):
    """Representa una sección aún no migrada a PySide6."""

    def __init__(self, title: str, message: str) -> None:
        """Inicializa la página con título y mensaje breve."""
        super().__init__()
        self.title = title
        self._build_ui(title, message)

    def _build_ui(self, title: str, message: str) -> None:
        """Construye el contenido visual del placeholder."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(42, 42, 42, 42)
        layout.setSpacing(12)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        title_label = QLabel(title)
        title_label.setObjectName("PageTitle")

        message_label = QLabel(message)
        message_label.setObjectName("PageSubtitle")
        message_label.setWordWrap(True)

        layout.addWidget(title_label)
        layout.addWidget(message_label)
        layout.addStretch(1)
