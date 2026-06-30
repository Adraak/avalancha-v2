"""Dialogo de creacion y edicion de deudas."""

from __future__ import annotations

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
    QWidget,
)

from avalancha.models import Debt
from services.debt_service import DebtService


class DebtDialog(QDialog):
    """Formulario PySide6 para datos basicos de una deuda."""

    def __init__(
        self,
        service: DebtService,
        debt: Debt | None = None,
        parent: QWidget | None = None,
    ) -> None:
        """Inicializa el dialogo con una deuda opcional."""
        super().__init__(parent)
        self.service = service
        self.debt = debt
        self.setWindowTitle("Deuda")
        self.name_input = QLineEdit()
        self.category_input = QComboBox()
        self.current_balance_input = QLineEdit()
        self.previous_balance_input = QLineEdit()
        self.monthly_payment_input = QLineEdit()
        self.minimum_payment_input = QLineEdit()
        self.interest_input = QLineEdit()
        self.credit_limit_input = QLineEdit()
        self.start_date_input = QDateEdit()
        self.active_input = QCheckBox("Activa")
        self._build_ui()
        self._load_debt()

    def obtener_datos(self) -> dict[str, object]:
        """Devuelve datos crudos para validacion del servicio."""
        return {
            "name": self.name_input.text(),
            "category": self.category_input.currentData(),
            "current_balance": self.current_balance_input.text(),
            "previous_month_balance": self.previous_balance_input.text(),
            "current_monthly_payment": self.monthly_payment_input.text(),
            "minimum_payment": self.minimum_payment_input.text(),
            "monthly_interest_rate": self.interest_input.text(),
            "credit_limit": self.credit_limit_input.text(),
            "start_date": self.start_date_input.date().toString("yyyy-MM-dd"),
            "active": self.active_input.isChecked(),
        }

    def _build_ui(self) -> None:
        """Construye formulario y botones."""
        layout = QVBoxLayout(self)
        form = QFormLayout()

        for value, label in self.service.categorias_disponibles():
            self.category_input.addItem(label, value)
        self.start_date_input.setCalendarPopup(True)
        self.start_date_input.setDisplayFormat("dd-MM-yyyy")

        form.addRow("Nombre", self.name_input)
        form.addRow("Categoría", self.category_input)
        form.addRow("Saldo actual", self.current_balance_input)
        form.addRow("Saldo mes anterior", self.previous_balance_input)
        form.addRow("Pago mensual", self.monthly_payment_input)
        form.addRow("Pago mínimo", self.minimum_payment_input)
        form.addRow("Interés mensual %", self.interest_input)
        form.addRow("Cupo tarjeta", self.credit_limit_input)
        form.addRow("Fecha inicio", self.start_date_input)
        form.addRow("", self.active_input)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel,
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout.addLayout(form)
        layout.addWidget(buttons)

    def _load_debt(self) -> None:
        """Carga datos de la deuda editada."""
        self.active_input.setChecked(True)
        self.start_date_input.setDate(QDate.currentDate())
        if self.debt is None:
            return
        self.name_input.setText(self.debt.name)
        index = self.category_input.findData(self.debt.category)
        if index >= 0:
            self.category_input.setCurrentIndex(index)
        self.current_balance_input.setText(str(self.debt.current_balance))
        self.previous_balance_input.setText(
            str(self.debt.previous_month_balance),
        )
        self.monthly_payment_input.setText(
            str(self.debt.current_monthly_payment),
        )
        self.minimum_payment_input.setText(str(self.debt.minimum_payment))
        if self.debt.monthly_interest_rate is not None:
            self.interest_input.setText(str(self.debt.monthly_interest_rate))
        self.credit_limit_input.setText(str(self.debt.credit_limit))
        self.start_date_input.setDate(self._safe_qdate(self.debt.start_date))
        self.active_input.setChecked(self.debt.active)

    @staticmethod
    def _safe_qdate(value: object) -> QDate:
        """Convierte fecha heredada y usa hoy si viene corrupta."""
        date_value = QDate.fromString(str(value or ""), "yyyy-MM-dd")
        if date_value.isValid():
            return date_value
        return QDate.currentDate()
