"""Pagina funcional de reportes para Avalancha V2."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from services.report_service import ReportService
from services.monthly_closure_service import MonthlyClosureService
from ui_pyside6.pages.report_viewer_dialog import ReportViewerDialog


class SortableItem(QTableWidgetItem):
    """Item de tabla con valor de orden independiente del texto."""

    def __init__(self, text: str, sort_value: object | None = None) -> None:
        """Inicializa texto visible y valor de orden."""
        super().__init__(text)
        self.sort_value = sort_value if sort_value is not None else text

    def __lt__(self, other: QTableWidgetItem) -> bool:
        """Ordena por valor interno cuando corresponde."""
        if isinstance(other, SortableItem):
            return self.sort_value < other.sort_value
        return super().__lt__(other)


class ReportsPage(QWidget):
    """Pantalla de generacion y lectura de reportes cifrados."""

    HEADERS = ["Mes", "Generado", "Archivo", "Estado"]

    def __init__(
        self,
        service: ReportService | None = None,
        closure_service: MonthlyClosureService | None = None,
    ) -> None:
        """Inicializa la pagina funcional de reportes."""
        super().__init__()
        today = date.today()
        self.service = service or ReportService()
        self.closure_service = closure_service or MonthlyClosureService(
            repository=self.service.repository,
        )
        self.month_input = QSpinBox()
        self.year_input = QSpinBox()
        self.table = QTableWidget()
        self.preview = QLabel("Selecciona o genera un reporte.")
        self._reports_by_id: dict[str, dict[str, Any]] = {}
        self._build_ui(today.month, today.year)
        self.refresh()

    def refresh(self) -> None:
        """Actualiza la lista de reportes cifrados."""
        self._populate_table(self.service.listar_reportes())

    def generate_report(self) -> None:
        """Genera, guarda y abre un reporte mensual cifrado."""
        month = self.month_input.value()
        year = self.year_input.value()
        try:
            report = self.service.generar_reporte_mensual(month, year)
            entry = self.service.guardar_reporte_cifrado(
                report,
                f"R{year:04d}-{month:02d}.avr",
            )
            self.closure_service.marcar_reporte_generado(year, month, True)
            opened = self.service.abrir_reporte_cifrado(entry["id"])
        except ValueError as exc:
            self._show_error(str(exc))
            return
        self.refresh()
        ReportViewerDialog(opened, self).exec()

    def open_selected(self) -> None:
        """Abre el reporte seleccionado dentro de Avalancha."""
        entry = self._selected_report()
        if entry is None:
            self._show_info("Selecciona un reporte para abrir.")
            return
        try:
            report = self.service.abrir_reporte_cifrado(str(entry["id"]))
        except ValueError as exc:
            self._show_error(str(exc))
            return
        ReportViewerDialog(report, self).exec()

    def delete_selected(self) -> None:
        """Elimina el reporte seleccionado despues de confirmar."""
        entry = self._selected_report()
        if entry is None:
            self._show_info("Selecciona un reporte para eliminar.")
            return
        response = QMessageBox.question(
            self,
            "Eliminar reporte",
            "Eliminar el reporte cifrado seleccionado?",
        )
        if response != QMessageBox.StandardButton.Yes:
            return
        try:
            self.service.eliminar_reporte(str(entry["id"]))
        except ValueError as exc:
            self._show_error(str(exc))
            return
        self.refresh()

    def _build_ui(self, month: int, year: int) -> None:
        """Construye selector, tabla y botones."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 28, 28, 28)
        layout.setSpacing(16)

        title = QLabel("Reportes")
        title.setObjectName("PageTitle")

        selector = QHBoxLayout()
        self.month_input.setRange(1, 12)
        self.month_input.setValue(month)
        self.year_input.setRange(2000, 2100)
        self.year_input.setValue(year)
        generate_button = QPushButton("Generar reporte mensual")
        generate_button.clicked.connect(self.generate_report)

        selector.addWidget(QLabel("Mes"))
        selector.addWidget(self.month_input)
        selector.addWidget(QLabel("Anio"))
        selector.addWidget(self.year_input)
        selector.addStretch(1)
        selector.addWidget(generate_button)

        self.table.setColumnCount(len(self.HEADERS))
        self.table.setHorizontalHeaderLabels(self.HEADERS)
        self.table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows,
        )
        self.table.setSelectionMode(
            QTableWidget.SelectionMode.SingleSelection,
        )
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSortingEnabled(True)
        self.table.doubleClicked.connect(self.open_selected)
        self.table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch,
        )

        buttons = QHBoxLayout()
        open_button = QPushButton("Abrir")
        delete_button = QPushButton("Eliminar")
        refresh_button = QPushButton("Actualizar")

        open_button.clicked.connect(self.open_selected)
        delete_button.clicked.connect(self.delete_selected)
        refresh_button.clicked.connect(self.refresh)

        buttons.addStretch(1)
        buttons.addWidget(open_button)
        buttons.addWidget(delete_button)
        buttons.addWidget(refresh_button)

        self.preview.setObjectName("MutedText")
        self.preview.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self.preview.setText(
            "Carpeta de reportes: "
            f"{Path(self.service.obtener_ruta_reportes())} | "
            "Cifrado: activado",
        )

        layout.addWidget(title)
        layout.addLayout(selector)
        layout.addWidget(self.table, stretch=1)
        layout.addWidget(self.preview)
        layout.addLayout(buttons)

    def _populate_table(self, reports: list[dict[str, Any]]) -> None:
        """Carga reportes existentes en la tabla."""
        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)
        self._reports_by_id = {
            str(item["id"]): item for item in reports if item.get("id")
        }

        for row, report in enumerate(reports):
            report_id = str(report.get("id", ""))
            self.table.insertRow(row)
            values = [
                (str(report.get("mes", "")), str(report.get("mes", ""))),
                (
                    self._format_datetime(report.get("fecha_creacion")),
                    str(report.get("fecha_creacion", "")),
                ),
                (str(report.get("nombre", "")), str(report.get("nombre", ""))),
                (str(report.get("estado", "")), str(report.get("estado", ""))),
            ]
            for column, (text, sort_value) in enumerate(values):
                item = SortableItem(text, sort_value)
                if column == 0:
                    item.setData(Qt.ItemDataRole.UserRole, report_id)
                self.table.setItem(row, column, item)

        self.table.setSortingEnabled(True)

    def _selected_report(self) -> dict[str, Any] | None:
        """Devuelve el reporte seleccionado."""
        row = self.table.currentRow()
        if row < 0:
            return None
        item = self.table.item(row, 0)
        if item is None:
            return None
        report_id = item.data(Qt.ItemDataRole.UserRole)
        return self._reports_by_id.get(str(report_id))

    @staticmethod
    def _format_datetime(value: object) -> str:
        """Formatea fecha ISO a texto local simple."""
        if not value:
            return "Sin datos"
        text = str(value)
        return text.replace("T", " ")

    def _show_error(self, message: str) -> None:
        """Muestra errores de servicio."""
        QMessageBox.critical(self, "Reportes", message)

    def _show_info(self, message: str) -> None:
        """Muestra mensajes informativos."""
        QMessageBox.information(self, "Reportes", message)
