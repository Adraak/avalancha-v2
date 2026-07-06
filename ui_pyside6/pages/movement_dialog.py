"""Dialogo PySide6 para crear y editar movimientos."""

from __future__ import annotations

from datetime import date

from PySide6.QtCore import QDate, QRegularExpression
from PySide6.QtGui import QRegularExpressionValidator
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
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
        self._formatting_amount = False
        self.date_input = QDateEdit()
        self.type_input = QComboBox()
        self.category_input = QComboBox()
        self.account_input = QComboBox()
        self.destination_account_input = QComboBox()
        self.debt_input = QComboBox()
        self.amount_input = QLineEdit()
        self.description_input = QLineEdit()
        self.unexpected_input = QCheckBox("Marcar como imprevisto")
        self.category_label = QLabel("Categoria")
        self.account_label = QLabel("Cuenta")
        self.destination_account_label = QLabel("Cuenta destino")
        self.debt_label = QLabel("Deuda")
        self.unexpected_label = QLabel("Imprevisto")
        self._build_ui()
        self._load_accounts()
        self._load_debts()
        self._load_initial_values()

    def obtener_datos(self) -> dict[str, object]:
        """Devuelve los datos capturados para entregarlos al servicio."""
        return {
            "fecha": self.date_input.date().toPython(),
            "tipo": self.type_input.currentData(),
            "categoria": self._categoria_actual(),
            "cuenta_id": self.account_input.currentData(),
            "cuenta_destino_id": self.destination_account_input.currentData(),
            "deuda_id": self.debt_input.currentData(),
            "monto": self._parse_clp_amount(self.amount_input.text()),
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
        self.type_input.addItem("Transferencia interna", "transferencia")
        self.type_input.addItem("Pago de deuda", "pago_deuda")
        self.type_input.currentIndexChanged.connect(self._on_type_changed)

        form.addRow("Fecha", self.date_input)
        form.addRow("Tipo", self.type_input)
        form.addRow(self.category_label, self.category_input)
        form.addRow(self.account_label, self.account_input)
        form.addRow(
            self.destination_account_label,
            self.destination_account_input,
        )
        form.addRow(self.debt_label, self.debt_input)
        form.addRow("Monto", self.amount_input)
        form.addRow("Descripcion", self.description_input)
        form.addRow(self.unexpected_label, self.unexpected_input)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel,
        )
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("Guardar")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(
            "Cancelar",
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout.addLayout(form)
        layout.addWidget(buttons)
        amount_validator = QRegularExpressionValidator(
            QRegularExpression(r"[0-9.]*"),
            self.amount_input,
        )
        self.amount_input.setValidator(amount_validator)
        self.amount_input.textChanged.connect(self._format_amount_live)
        self._update_transfer_fields()

    def _load_accounts(self) -> None:
        """Carga las cuentas activas desde el servicio."""
        self.account_input.clear()
        self.destination_account_input.clear()
        for account in self.service.obtener_cuentas():
            self.account_input.addItem(account.nombre, account.id)
            self.destination_account_input.addItem(account.nombre, account.id)

    def _load_debts(self) -> None:
        """Carga deudas activas desde el servicio."""
        self.debt_input.clear()
        for debt in self.service.obtener_deudas():
            self.debt_input.addItem(debt.nombre, debt.id)

    def _load_categories(self) -> None:
        """Carga categorias segun el tipo seleccionado."""
        if self._es_transferencia() or self._es_pago_deuda():
            self.category_input.clear()
            return
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
            self._update_transfer_fields()
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

        destination_index = self.destination_account_input.findData(
            self.movement.cuenta_destino_id,
        )
        if destination_index >= 0:
            self.destination_account_input.setCurrentIndex(destination_index)

        debt_index = self.debt_input.findData(self.movement.deuda_id)
        if debt_index >= 0:
            self.debt_input.setCurrentIndex(debt_index)

        self.amount_input.setText(self._format_clp_amount(self.movement.monto))
        self.description_input.setText(self.movement.descripcion)
        self.unexpected_input.setChecked(self.movement.imprevisto)
        self._update_transfer_fields()

    def _on_type_changed(self) -> None:
        """Actualiza categorias y campos visibles segun tipo."""
        self._load_categories()
        self._update_transfer_fields()

    def _update_transfer_fields(self) -> None:
        """Muestra campos segun tipo financiero seleccionado."""
        es_transferencia = self._es_transferencia()
        es_pago_deuda = self._es_pago_deuda()
        requiere_categoria = not (es_transferencia or es_pago_deuda)
        self.category_label.setVisible(requiere_categoria)
        self.category_input.setVisible(requiere_categoria)
        self.unexpected_label.setVisible(requiere_categoria)
        self.unexpected_input.setVisible(requiere_categoria)
        self.destination_account_label.setVisible(es_transferencia)
        self.destination_account_input.setVisible(es_transferencia)
        self.debt_label.setVisible(es_pago_deuda)
        self.debt_input.setVisible(es_pago_deuda)
        self.account_label.setText(
            "Cuenta origen"
            if es_transferencia or es_pago_deuda
            else "Cuenta",
        )
        if es_transferencia or es_pago_deuda:
            self.unexpected_input.setChecked(False)

    def _categoria_actual(self) -> str:
        """Devuelve categoria solo para ingresos o gastos."""
        if self._es_transferencia() or self._es_pago_deuda():
            return ""
        return self.category_input.currentText()

    def _es_transferencia(self) -> bool:
        """Indica si el tipo actual es transferencia interna."""
        return self.type_input.currentData() == "transferencia"

    def _es_pago_deuda(self) -> bool:
        """Indica si el tipo actual es pago de deuda."""
        return self.type_input.currentData() == "pago_deuda"

    def _format_amount_live(self, text: str) -> None:
        """Formatea el monto mientras se escribe evitando loops de senal."""
        if self._formatting_amount:
            return
        digits = self._digits_from_live_amount_text(text)
        if not digits:
            return
        cursor = self.amount_input.cursorPosition()
        digits_to_right = sum(
            1 for char in text[cursor:] if char.isdigit()
        )
        formatted = self._format_digits_as_clp(digits)
        if formatted == text:
            return
        self._formatting_amount = True
        try:
            self.amount_input.setText(formatted)
            self.amount_input.setCursorPosition(
                self._cursor_position_from_right_digits(
                    formatted,
                    digits_to_right,
                ),
            )
        finally:
            self._formatting_amount = False

    @classmethod
    def _format_clp_amount(cls, value: int | str) -> str:
        """Formatea un monto entero CLP sin simbolo peso."""
        digits = cls._digits_from_live_amount_text(value)
        if not digits:
            raise ValueError("Ingresa un monto valido.")
        if int(digits) <= 0:
            raise ValueError("Ingresa un monto valido.")
        return cls._format_digits_as_clp(digits)

    @classmethod
    def _parse_clp_amount(cls, text: int | str) -> int:
        """Convierte texto CLP con puntos de miles a entero."""
        digits = cls._digits_from_amount_text(text)
        amount = int(digits)
        if amount <= 0:
            raise ValueError("Ingresa un monto valido.")
        return amount

    @staticmethod
    def _digits_from_amount_text(text: int | str) -> str:
        """Extrae digitos desde un monto con formato CLP valido."""
        raw = str(text).strip()
        if not raw:
            raise ValueError("Ingresa un monto valido.")
        if any(char not in "0123456789." for char in raw):
            raise ValueError("Ingresa un monto valido.")
        if raw.startswith(".") or raw.endswith(".") or ".." in raw:
            raise ValueError("Ingresa un monto valido.")
        if "." in raw:
            groups = raw.split(".")
            if not groups[0] or len(groups[0]) > 3:
                raise ValueError("Ingresa un monto valido.")
            if any(len(group) != 3 for group in groups[1:]):
                raise ValueError("Ingresa un monto valido.")
        digits = raw.replace(".", "")
        if not digits.isdigit():
            raise ValueError("Ingresa un monto valido.")
        return digits

    @staticmethod
    def _digits_from_live_amount_text(text: int | str) -> str:
        """Extrae digitos para formateo visual tolerando puntos intermedios."""
        return "".join(char for char in str(text) if char.isdigit())

    @staticmethod
    def _format_digits_as_clp(digits: str) -> str:
        """Formatea digitos como CLP con puntos de miles."""
        return f"{int(digits):,}".replace(",", ".")

    @staticmethod
    def _cursor_position_from_right_digits(
        text: str,
        digits_to_right: int,
    ) -> int:
        """Calcula posicion de cursor preservando digitos a la derecha."""
        if digits_to_right <= 0:
            return len(text)
        seen = 0
        for index in range(len(text) - 1, -1, -1):
            if text[index].isdigit():
                seen += 1
            if seen == digits_to_right:
                return index
        return 0

    @staticmethod
    def _to_qdate(value: date) -> QDate:
        """Convierte una fecha Python a QDate."""
        return QDate(value.year, value.month, value.day)
