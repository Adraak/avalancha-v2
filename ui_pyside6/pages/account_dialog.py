"""Dialogo de creacion y edicion de cuentas financieras."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLineEdit,
    QVBoxLayout,
    QWidget,
)

from avalancha.models import CuentaFinanciera
from services.account_service import AccountService


class AccountDialog(QDialog):
    """Formulario PySide6 para datos basicos de una cuenta."""

    def __init__(
        self,
        service: AccountService,
        account: CuentaFinanciera | None = None,
        parent: QWidget | None = None,
    ) -> None:
        """Inicializa el dialogo con una cuenta opcional."""
        super().__init__(parent)
        self.service = service
        self.account = account
        self.setWindowTitle("Cuenta financiera")
        self.name_input = QLineEdit()
        self.type_input = QComboBox()
        self.real_balance_input = QLineEdit()
        self.active_input = QCheckBox("Activa")
        self._build_ui()
        self._load_account()

    def obtener_datos(self) -> dict[str, object]:
        """Devuelve datos crudos para validacion del servicio."""
        return {
            "name": self.name_input.text(),
            "account_type": self.type_input.currentData(),
            "real_balance": self.real_balance_input.text(),
            "active": self.active_input.isChecked(),
        }

    def _build_ui(self) -> None:
        """Construye formulario y botones."""
        layout = QVBoxLayout(self)
        form = QFormLayout()

        for value, label in self.service.tipos_disponibles():
            self.type_input.addItem(label, value)

        form.addRow("Nombre", self.name_input)
        form.addRow("Tipo", self.type_input)
        form.addRow("Saldo real", self.real_balance_input)
        form.addRow("", self.active_input)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel,
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout.addLayout(form)
        layout.addWidget(buttons)

    def _load_account(self) -> None:
        """Carga datos de la cuenta editada."""
        self.active_input.setChecked(True)
        if self.account is None:
            return
        self.name_input.setText(self.account.name)
        index = self.type_input.findData(self.account.account_type)
        if index >= 0:
            self.type_input.setCurrentIndex(index)
        if self.account.real_balance is not None:
            self.real_balance_input.setText(str(self.account.real_balance))
        self.active_input.setChecked(self.account.active)
