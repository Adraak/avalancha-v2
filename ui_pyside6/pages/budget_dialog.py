"""Dialogo PySide6 para crear y editar presupuestos."""

from __future__ import annotations

from datetime import date

from PySide6.QtCore import QDate
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLineEdit,
    QTextEdit,
    QVBoxLayout,
)

from core.models.presupuesto import Presupuesto
from services.budget_service import BudgetService


class BudgetDialog(QDialog):
    """Formulario modal para capturar datos de un presupuesto."""

    def __init__(
        self,
        service: BudgetService,
        presupuesto: Presupuesto | None = None,
        parent: object | None = None,
    ) -> None:
        """Inicializa el dialogo en modo creacion o edicion."""
        super().__init__(parent)
        self.service = service
        self.presupuesto = presupuesto
        self.setWindowTitle(
            "Editar presupuesto" if presupuesto else "Nuevo presupuesto",
        )
        self.setMinimumWidth(520)
        self.name_input = QLineEdit()
        self.category_input = QComboBox()
        self.amount_input = QLineEdit()
        self.currency_input = QComboBox()
        self.start_date_input = QDateEdit()
        self.end_enabled_input = QCheckBox("Usar fecha de termino")
        self.end_date_input = QDateEdit()
        self.active_input = QCheckBox("Activo")
        self.notes_input = QTextEdit()
        self._build_ui()
        self._load_initial_values()

    def obtener_datos(self) -> dict[str, object]:
        """Devuelve los datos capturados para entregarlos al servicio."""
        return {
            "nombre": self.name_input.text(),
            "categoria": self.category_input.currentText(),
            "monto_mensual": self.amount_input.text(),
            "moneda": self.currency_input.currentText(),
            "fecha_inicio": self.start_date_input.date().toPython(),
            "fecha_termino": (
                self.end_date_input.date().toPython()
                if self.end_enabled_input.isChecked()
                else None
            ),
            "activo": self.active_input.isChecked(),
            "observaciones": self.notes_input.toPlainText(),
        }

    def _build_ui(self) -> None:
        """Construye los controles del formulario."""
        layout = QVBoxLayout(self)
        form = QFormLayout()
        form.setFieldGrowthPolicy(
            QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow,
        )

        self.category_input.setEditable(False)
        current_category = self.presupuesto.categoria if self.presupuesto else None
        for category in self.service.categorias_disponibles(current_category):
            self.category_input.addItem(category)

        self.currency_input.addItems(["CLP", "USD", "EUR"])
        self.start_date_input.setCalendarPopup(True)
        self.start_date_input.setDisplayFormat("dd-MM-yyyy")
        self.start_date_input.setDate(QDate.currentDate())
        self.end_date_input.setCalendarPopup(True)
        self.end_date_input.setDisplayFormat("dd-MM-yyyy")
        self.end_date_input.setDate(QDate.currentDate())
        self.end_date_input.setEnabled(False)
        self.end_enabled_input.toggled.connect(self.end_date_input.setEnabled)
        self.active_input.setChecked(True)
        self.notes_input.setFixedHeight(90)

        form.addRow("Nombre", self.name_input)
        form.addRow("Categoría", self.category_input)
        form.addRow("Monto mensual", self.amount_input)
        form.addRow("Moneda", self.currency_input)
        form.addRow("Fecha inicio", self.start_date_input)
        form.addRow("", self.end_enabled_input)
        form.addRow("Fecha término", self.end_date_input)
        form.addRow("Estado", self.active_input)
        form.addRow("Observaciones", self.notes_input)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel,
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout.addLayout(form)
        layout.addWidget(buttons)

    def _load_initial_values(self) -> None:
        """Carga valores existentes cuando se edita un presupuesto."""
        if self.presupuesto is None:
            return
        self.name_input.setText(self.presupuesto.nombre)
        self.category_input.setCurrentText(self.presupuesto.categoria)
        self.amount_input.setText(str(self.presupuesto.monto_mensual))
        self.currency_input.setCurrentText(self.presupuesto.moneda)
        if self.presupuesto.fecha_inicio:
            self.start_date_input.setDate(
                self._to_qdate(self.presupuesto.fecha_inicio),
            )
        if self.presupuesto.fecha_termino:
            self.end_enabled_input.setChecked(True)
            self.end_date_input.setDate(
                self._to_qdate(self.presupuesto.fecha_termino),
            )
        self.active_input.setChecked(self.presupuesto.activo)
        self.notes_input.setPlainText(self.presupuesto.observaciones)

    @staticmethod
    def _to_qdate(value: date) -> QDate:
        """Convierte date de Python a QDate."""
        return QDate(value.year, value.month, value.day)
