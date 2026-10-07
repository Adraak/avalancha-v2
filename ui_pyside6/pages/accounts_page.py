"""Pagina CRUD de cuentas financieras para Avalancha V2."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from avalancha.models import CuentaFinanciera
from services.account_service import AccountService
from ui_pyside6.pages.account_dialog import AccountDialog
from ui_pyside6.pages.base_page import ErrorAwarePage


class SortableItem(QTableWidgetItem):
    """Item con valor interno para ordenar columnas."""

    def __init__(self, text: str, sort_value: object | None = None) -> None:
        """Inicializa texto visible y valor de orden."""
        super().__init__(text)
        self.sort_value = sort_value if sort_value is not None else text

    def __lt__(self, other: QTableWidgetItem) -> bool:
        """Compara usando valor interno si existe."""
        if isinstance(other, SortableItem):
            return self.sort_value < other.sort_value
        return super().__lt__(other)


class AccountsPage(ErrorAwarePage):
    """CRUD de cuentas del perfil activo usando AccountService."""

    movements_requested = Signal(str, str)

    HEADERS = [
        "Cuenta",
        "Tipo",
        "Saldo real",
        "Registrado",
        "Diferencia",
        "Estado",
    ]

    def __init__(self, service: AccountService | None = None) -> None:
        """Inicializa la pagina de cuentas."""
        super().__init__()
        self.service = service or AccountService()
        self.table = QTableWidget()
        self._accounts_by_id: dict[str, CuentaFinanciera] = {}
        self._build_ui()
        self.refresh()

    def refresh(self) -> None:
        """Actualiza la tabla desde el servicio."""
        self._populate_table(self.service.obtener_cuentas())

    def new_account(self) -> None:
        """Abre dialogo para crear cuenta."""
        dialog = AccountDialog(self.service, parent=self)
        if dialog.exec() != AccountDialog.DialogCode.Accepted:
            return
        try:
            self.service.crear_cuenta(dialog.obtener_datos())
        except ValueError as exc:
            self._show_error(
                self._value_error_message(
                    exc,
                    context="accounts.create",
                    fallback="No fue posible crear la cuenta.",
                ),
            )
            return
        self.refresh()

    def edit_selected(self) -> None:
        """Edita la cuenta seleccionada."""
        account = self._selected_account()
        if account is None:
            self._show_info("Selecciona una cuenta para editar.")
            return
        dialog = AccountDialog(self.service, account, self)
        if dialog.exec() != AccountDialog.DialogCode.Accepted:
            return
        try:
            self.service.editar_cuenta(account.account_id, dialog.obtener_datos())
        except ValueError as exc:
            self._show_error(
                self._value_error_message(
                    exc,
                    context="accounts.edit",
                    fallback="No fue posible editar la cuenta.",
                ),
            )
            return
        self.refresh()

    def delete_selected(self) -> None:
        """Elimina la cuenta seleccionada si no tiene movimientos."""
        account = self._selected_account()
        if account is None:
            self._show_info("Selecciona una cuenta para eliminar.")
            return
        response = QMessageBox.question(
            self,
            "Eliminar cuenta",
            "Eliminar la cuenta seleccionada?",
        )
        if response != QMessageBox.StandardButton.Yes:
            return
        try:
            self.service.eliminar_cuenta(account.account_id)
        except ValueError as exc:
            self._show_error(
                self._value_error_message(
                    exc,
                    context="accounts.delete",
                    fallback="No fue posible eliminar la cuenta.",
                ),
            )
            return
        self.refresh()

    def activate_selected(self) -> None:
        """Activa la cuenta seleccionada."""
        self._change_selected_state(True)

    def deactivate_selected(self) -> None:
        """Desactiva la cuenta seleccionada."""
        self._change_selected_state(False)

    def view_selected_movements(self) -> None:
        """Solicita abrir movimientos asociados a la cuenta seleccionada."""
        account = self._selected_account()
        if account is None:
            self._show_info("Selecciona una cuenta para ver sus movimientos.")
            return
        self.movements_requested.emit(account.account_id, account.name)

    def _build_ui(self) -> None:
        """Construye titulo, tabla y acciones."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 28, 28, 28)
        layout.setSpacing(16)

        title = QLabel("Cuentas")
        title.setObjectName("PageTitle")

        self.table.setColumnCount(len(self.HEADERS))
        self.table.setHorizontalHeaderLabels(self.HEADERS)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows,
        )
        self.table.setSelectionMode(
            QTableWidget.SelectionMode.SingleSelection,
        )
        self.table.setSortingEnabled(True)
        self.table.doubleClicked.connect(self.edit_selected)
        self.table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch,
        )

        buttons = QHBoxLayout()
        new_button = QPushButton("Nueva cuenta")
        edit_button = QPushButton("Editar")
        delete_button = QPushButton("Eliminar")
        activate_button = QPushButton("Activar")
        deactivate_button = QPushButton("Desactivar")
        movements_button = QPushButton("Ver movimientos")
        refresh_button = QPushButton("Actualizar")

        new_button.clicked.connect(self.new_account)
        edit_button.clicked.connect(self.edit_selected)
        delete_button.clicked.connect(self.delete_selected)
        activate_button.clicked.connect(self.activate_selected)
        deactivate_button.clicked.connect(self.deactivate_selected)
        movements_button.clicked.connect(self.view_selected_movements)
        refresh_button.clicked.connect(self.refresh)

        buttons.addStretch(1)
        buttons.addWidget(new_button)
        buttons.addWidget(edit_button)
        buttons.addWidget(delete_button)
        buttons.addWidget(activate_button)
        buttons.addWidget(deactivate_button)
        buttons.addWidget(movements_button)
        buttons.addWidget(refresh_button)

        layout.addWidget(title)
        layout.addWidget(self.table, stretch=1)
        layout.addLayout(buttons)

    def _populate_table(self, accounts: list[CuentaFinanciera]) -> None:
        """Carga cuentas en la tabla."""
        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)
        self._accounts_by_id = {
            account.account_id: account for account in accounts
        }
        type_labels = dict(self.service.tipos_disponibles())
        for row, account in enumerate(accounts):
            self.table.insertRow(row)
            difference = account.difference if account.difference is not None else 0
            values = [
                (account.name, account.name.casefold()),
                (
                    type_labels.get(account.account_type, account.account_type),
                    account.account_type,
                ),
                (
                    self._format_optional_clp(account.real_balance),
                    account.real_balance if account.real_balance is not None else 0,
                ),
                (
                    self._format_clp(account.registered_balance),
                    account.registered_balance,
                ),
                (self._format_clp(difference), difference),
                ("Activa" if account.active else "Inactiva", account.active),
            ]
            for column, (text, sort_value) in enumerate(values):
                item = SortableItem(text, sort_value)
                if column == 0:
                    item.setData(Qt.ItemDataRole.UserRole, account.account_id)
                if column in {2, 3, 4}:
                    item.setTextAlignment(
                        Qt.AlignmentFlag.AlignRight
                        | Qt.AlignmentFlag.AlignVCenter,
                    )
                self.table.setItem(row, column, item)
        self.table.setSortingEnabled(True)

    def _selected_account(self) -> CuentaFinanciera | None:
        """Devuelve la cuenta seleccionada."""
        row = self.table.currentRow()
        if row < 0:
            return None
        item = self.table.item(row, 0)
        if item is None:
            return None
        account_id = item.data(Qt.ItemDataRole.UserRole)
        return self._accounts_by_id.get(str(account_id))

    def _change_selected_state(self, active: bool) -> None:
        """Cambia el estado de la cuenta seleccionada."""
        account = self._selected_account()
        if account is None:
            self._show_info("Selecciona una cuenta.")
            return
        try:
            if active:
                self.service.activar_cuenta(account.account_id)
            else:
                self.service.desactivar_cuenta(account.account_id)
        except ValueError as exc:
            self._show_error(
                self._value_error_message(
                    exc,
                    context="accounts.change_state",
                    fallback="No fue posible cambiar el estado de la cuenta.",
                ),
            )
            return
        self.refresh()

    @staticmethod
    def _format_optional_clp(amount: int | None) -> str:
        """Formatea monto opcional."""
        if amount is None:
            return "Sin datos"
        return AccountsPage._format_clp(amount)

    @staticmethod
    def _format_clp(amount: int) -> str:
        """Formatea monto CLP."""
        prefix = "-$" if amount < 0 else "$"
        return f"{prefix} {abs(amount):,.0f}".replace(",", ".")

    def _show_error(self, message: str) -> None:
        """Muestra errores de servicio."""
        QMessageBox.critical(self, "Cuentas", message)

    def _show_info(self, message: str) -> None:
        """Muestra mensajes informativos."""
        QMessageBox.information(self, "Cuentas", message)
