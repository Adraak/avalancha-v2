"""Dialogo PySide6 para crear y editar movimientos."""

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
    QVBoxLayout,
)

from core.models.movimiento import Movimiento
from services.movement_service import MovementService


class MovementDialog(QDialog):
    """Formulario modal para capturar datos de un movimiento."""

    def __init__(
        self,
        service: MovementService,
        movement: Movimiento | None = None,
        parent: object | None = None,
    ) -> None:
        """Inicializa el formulario en modo creacion o edicion."""
        super().__init__(parent)
        self.service = service
        self.movement = movement
        self.setWindowTitle(
            "Editar movimiento" if movement else "Nuevo movimiento",
        )
        self.setMinimumWidth(460)
        self.date_input = QDateEdit()
        self.type_input = QComboBox()
        self.category_input = QComboBox()
        self.account_input = QComboBox()
        self.amount_input = QLineEdit()
        self.description_input = QLineEdit()
        self.unexpected_input = QCheckBox("Marcar como imprevisto")
        self._build_ui()
        self._load_accounts()
        self._load_initial_values()

    def obtener_datos(self) -> dict[str, object]:
        """Devuelve los datos capturados para entregarlos al servicio."""
        return {
            "fecha": self.date_input.date().toPython(),
            "tipo": self.type_input.currentData(),
            "categoria": self.category_input.currentText(),
            "cuenta_id": self.account_input.currentData(),
            "monto": self.amount_input.text(),
            "descripcion": self.description_input.text(),
            "imprevisto": self.unexpected_input.isChecked(),
        }

    def _build_ui(self) -> None:
        """Construye los widgets del dialogo."""
        layout = QVBoxLayout(self)
        form = QFormLayout()
        form.setFieldGrowthPolicy(
            QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow,
        )

        self.date_input.setCalendarPopup(True)
        self.date_input.setDisplayFormat("dd-MM-yyyy")
        self.date_input.setDate(QDate.currentDate())

        self.type_input.addItem("Gasto", "gasto")
        self.type_input.addItem("Ingreso", "ingreso")
        self.type_input.currentIndexChanged.connect(self._load_categories)

        form.addRow("Fecha", self.date_input)
        form.addRow("Tipo", self.type_input)
        form.addRow("Categoría", self.category_input)
        form.addRow("Cuenta", self.account_input)
        form.addRow("Monto", self.amount_input)
        form.addRow("Descripción", self.description_input)
        form.addRow("Imprevisto", self.unexpected_input)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel,
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout.addLayout(form)
        layout.addWidget(buttons)

    def _load_accounts(self) -> None:
        """Carga las cuentas activas desde el servicio."""
        self.account_input.clear()
        for account in self.service.obtener_cuentas():
            self.account_input.addItem(account.nombre, account.id)

    def _load_categories(self) -> None:
        """Carga categorias segun el tipo seleccionado."""
        current = self.category_input.currentText()
        historical = self.movement.categoria if self.movement else None
        self.category_input.clear()
        for category in self.service.obtener_categorias(
            self.type_input.currentData(),
            incluir_categoria=historical,
        ):
            self.category_input.addItem(category)
        if current:
            index = self.category_input.findText(current)
            if index >= 0:
                self.category_input.setCurrentIndex(index)

    def _load_initial_values(self) -> None:
        """Completa el formulario con valores existentes si corresponde."""
        self._load_categories()
        if self.movement is None:
            return

        self.date_input.setDate(self._to_qdate(self.movement.fecha))
        type_index = self.type_input.findData(self.movement.tipo)
        if type_index >= 0:
            self.type_input.setCurrentIndex(type_index)
        self._load_categories()

        category_index = self.category_input.findText(self.movement.categoria)
        if category_index >= 0:
            self.category_input.setCurrentIndex(category_index)

        account_index = self.account_input.findData(self.movement.cuenta_id)
        if account_index >= 0:
            self.account_input.setCurrentIndex(account_index)

        self.amount_input.setText(str(self.movement.monto))
        self.description_input.setText(self.movement.descripcion)
        self.unexpected_input.setChecked(self.movement.imprevisto)

    @staticmethod
    def _to_qdate(value: date) -> QDate:
        """Convierte una fecha Python a QDate."""
        return QDate(value.year, value.month, value.day)
