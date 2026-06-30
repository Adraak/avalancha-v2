"""Dialogo de visualizacion interna de reportes cifrados."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
)

from services.report_service import ReporteCifradoAbierto


class ReportViewerDialog(QDialog):
    """Muestra un reporte descifrado sin abrir archivos externos."""

    def __init__(
        self,
        reporte: ReporteCifradoAbierto,
        parent: QWidget | None = None,
    ) -> None:
        """Inicializa el visor con contenido ya descifrado por el servicio."""
        super().__init__(parent)
        self.reporte = reporte
        self.setWindowTitle("Reporte mensual")
        self.resize(820, 620)
        self._build_ui()

    def _build_ui(self) -> None:
        """Construye encabezado, contenido y boton de cierre."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        title = QLabel(self.reporte.titulo or "Reporte mensual")
        title.setObjectName("PageTitle")

        metadata = QLabel(
            f"Mes: {self.reporte.mes} | "
            f"Generado: {self.reporte.fecha_generacion}"
        )
        metadata.setObjectName("MutedText")

        content = QPlainTextEdit()
        content.setReadOnly(True)
        content.setPlainText(self.reporte.contenido)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)

        layout.addWidget(title)
        layout.addWidget(metadata)
        layout.addWidget(content, stretch=1)
        layout.addWidget(buttons)
