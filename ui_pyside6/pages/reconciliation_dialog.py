"""Dialogo PySide6 para crear y editar conciliaciones."""

from __future__ import annotations

from datetime import date

from PySide6.QtCore import QDate
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QTextEdit,
    QVBoxLayout,
)

from core.models.conciliacion import Conciliacion
from services.reconciliation_service import ReconciliationService


class ReconciliationDialog(QDialog):
    """Formulario modal para una conciliacion de cuenta."""

    def __init__(
        self,
        service: ReconciliationService,
        reconciliation: Conciliacion | None = None,
        parent: object | None = None,
    ) -> None:
        """Inicializa el formulario de conciliacion."""
        super().__init__(parent)
        self.service = service
        self.reconciliation = reconciliation
        self.setWindowTitle(
            "Editar conciliacion" if reconciliation else "Nueva conciliacion",
        )
        self.setMinimumWidth(520)
        self.account_input = QComboBox()
        self.real_balance_input = QLineEdit()
        self.registered_balance_label = QLabel("$ 0")
        self.difference_label = QLabel("$ 0")
        self.date_input = QDateEdit()
        self.status_input = QComboBox()
        self.notes_input = QTextEdit()
        self._build_ui()
        self._load_initial_values()

    def obtener_datos(self) -> dict[str, object]:
        """Devuelve los datos capturados por el dialogo."""
        return {
            "cuenta_id": self.account_input.currentData(),
            "saldo_real": self.real_balance_input.text(),
            "fecha_conciliacion": self.date_input.date().toPython(),
            "estado": self.status_input.currentText(),
            "observaciones": self.notes_input.toPlainText(),
        }

    def _build_ui(self) -> None:
        """Construye los controles visuales del dialogo."""
        layout = QVBoxLayout(self)
        form = QFormLayout()
        form.setFieldGrowthPolicy(
            QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow,
        )

        for account_id, account_name in self.service.opciones_cuentas():
            self.account_input.addItem(account_name, account_id)
        self.account_input.currentIndexChanged.connect(self._refresh_amounts)

        self.real_balance_input.textChanged.connect(self._refresh_amounts)
        self.date_input.setCalendarPopup(True)
        self.date_input.setDisplayFormat("dd-MM-yyyy")
        self.date_input.setDate(QDate.currentDate())
        self.status_input.addItems(
            ["Pendiente", "Revisada", "Con diferencia", "Cuadrada"],
        )
        self.notes_input.setFixedHeight(90)

        form.addRow("Cuenta", self.account_input)
        form.addRow("Saldo registrado", self.registered_balance_label)
        form.addRow("Saldo real", self.real_balance_input)
        form.addRow("Diferencia", self.difference_label)
        form.addRow("Fecha conciliacion", self.date_input)
        form.addRow("Estado", self.status_input)
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
        """Carga datos existentes si se edita una conciliacion."""
        if self.reconciliation is not None:
            index = self.account_input.findData(self.reconciliation.cuenta_id)
            if index >= 0:
                self.account_input.setCurrentIndex(index)
            self.account_input.setEnabled(False)
            if self.reconciliation.saldo_real is not None:
                self.real_balance_input.setText(str(self.reconciliation.saldo_real))
            self.date_input.setDate(
                self._to_qdate(self.reconciliation.fecha_conciliacion),
            )
            status_index = self.status_input.findText(
                self.reconciliation.estado,
            )
            if status_index >= 0:
                self.status_input.setCurrentIndex(status_index)
            self.notes_input.setPlainText(self.reconciliation.observaciones)
        self._refresh_amounts()

    def _refresh_amounts(self) -> None:
        """Actualiza saldo registrado y diferencia mostrada."""
        cuenta_id = self.account_input.currentData()
        if not cuenta_id:
            return
        reconciliation = self.service.obtener_conciliacion_por_cuenta(
            cuenta_id,
        )
        self.registered_balance_label.setText(
            self._format_clp(reconciliation.saldo_registrado),
        )
        try:
            difference = self.service.calcular_diferencia(
                cuenta_id,
                self.real_balance_input.text() or "0",
            )
        except ValueError:
            self.difference_label.setText("Saldo invalido")
            return
        self.difference_label.setText(self._format_clp(difference))

    @staticmethod
    def _to_qdate(value: date) -> QDate:
        """Convierte una fecha Python a QDate."""
        return QDate(value.year, value.month, value.day)

    @staticmethod
    def _format_clp(amount: int) -> str:
        """Formatea un monto CLP."""
        prefix = "-$ " if amount < 0 else "$ "
        return prefix + f"{abs(amount):,.0f}".replace(",", ".")

