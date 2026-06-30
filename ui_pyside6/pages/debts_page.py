"""Pagina CRUD de deudas para Avalancha V2."""

from __future__ import annotations

from PySide6.QtCore import Qt
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

from avalancha.models import Debt
from services.debt_service import DebtService
from ui_pyside6.pages.debt_dialog import DebtDialog


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


class DebtsPage(QWidget):
    """CRUD de deudas del perfil activo usando DebtService."""

    HEADERS = [
        "Nombre",
        "Categoría",
        "Saldo actual",
        "Saldo mes anterior",
        "Disminución",
        "Pago mensual",
        "Interés est.",
        "Estado",
    ]

    def __init__(self, service: DebtService | None = None) -> None:
        """Inicializa la pagina de deudas."""
        super().__init__()
        self.service = service or DebtService()
        self.table = QTableWidget()
        self._debts_by_id: dict[str, Debt] = {}
        self._build_ui()
        self.refresh()

    def refresh(self) -> None:
        """Actualiza la tabla desde el servicio."""
        self._populate_table(self.service.obtener_deudas())

    def new_debt(self) -> None:
        """Abre dialogo para crear deuda."""
        dialog = DebtDialog(self.service, parent=self)
        if dialog.exec() != DebtDialog.DialogCode.Accepted:
            return
        try:
            self.service.crear_deuda(dialog.obtener_datos())
        except ValueError as exc:
            self._show_error(str(exc))
            return
        self.refresh()

    def edit_selected(self) -> None:
        """Edita la deuda seleccionada."""
        debt = self._selected_debt()
        if debt is None:
            self._show_info("Selecciona una deuda para editar.")
            return
        dialog = DebtDialog(self.service, debt, self)
        if dialog.exec() != DebtDialog.DialogCode.Accepted:
            return
        try:
            self.service.editar_deuda(debt.debt_id, dialog.obtener_datos())
        except ValueError as exc:
            self._show_error(str(exc))
            return
        self.refresh()

    def delete_selected(self) -> None:
        """Elimina la deuda seleccionada si no tiene movimientos."""
        debt = self._selected_debt()
        if debt is None:
            self._show_info("Selecciona una deuda para eliminar.")
            return
        response = QMessageBox.question(
            self,
            "Eliminar deuda",
            "Eliminar la deuda seleccionada?",
        )
        if response != QMessageBox.StandardButton.Yes:
            return
        try:
            self.service.eliminar_deuda(debt.debt_id)
        except ValueError as exc:
            self._show_error(str(exc))
            return
        self.refresh()

    def activate_selected(self) -> None:
        """Activa la deuda seleccionada."""
        self._change_selected_state(True)

    def deactivate_selected(self) -> None:
        """Desactiva la deuda seleccionada."""
        self._change_selected_state(False)

    def _build_ui(self) -> None:
        """Construye titulo, tabla y acciones."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 28, 28, 28)
        layout.setSpacing(16)

        title = QLabel("Deudas")
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
        new_button = QPushButton("Nueva deuda")
        edit_button = QPushButton("Editar")
        delete_button = QPushButton("Eliminar")
        activate_button = QPushButton("Activar")
        deactivate_button = QPushButton("Desactivar")
        refresh_button = QPushButton("Actualizar")

        new_button.clicked.connect(self.new_debt)
        edit_button.clicked.connect(self.edit_selected)
        delete_button.clicked.connect(self.delete_selected)
        activate_button.clicked.connect(self.activate_selected)
        deactivate_button.clicked.connect(self.deactivate_selected)
        refresh_button.clicked.connect(self.refresh)

        buttons.addStretch(1)
        buttons.addWidget(new_button)
        buttons.addWidget(edit_button)
        buttons.addWidget(delete_button)
        buttons.addWidget(activate_button)
        buttons.addWidget(deactivate_button)
        buttons.addWidget(refresh_button)

        layout.addWidget(title)
        layout.addWidget(self.table, stretch=1)
        layout.addLayout(buttons)

    def _populate_table(self, debts: list[Debt]) -> None:
        """Carga deudas en la tabla."""
        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)
        self._debts_by_id = {debt.debt_id: debt for debt in debts}
        category_labels = dict(self.service.categorias_disponibles())

        for row, debt in enumerate(debts):
            self.table.insertRow(row)
            decrease = self.service.calcular_disminucion_mensual(debt)
            interest = self.service.calcular_interes_estimado(debt)
            values = [
                (debt.name, debt.name.casefold()),
                (
                    category_labels.get(debt.category, debt.category),
                    debt.category,
                ),
                (self._format_clp(debt.current_balance), debt.current_balance),
                (
                    self._format_clp(debt.previous_month_balance),
                    debt.previous_month_balance,
                ),
                (self._format_clp(decrease), decrease),
                (
                    self._format_clp(debt.current_monthly_payment),
                    debt.current_monthly_payment,
                ),
                (self._format_clp(interest), interest),
                ("Activa" if debt.active else "Inactiva", debt.active),
            ]
            for column, (text, sort_value) in enumerate(values):
                item = SortableItem(text, sort_value)
                if column == 0:
                    item.setData(Qt.ItemDataRole.UserRole, debt.debt_id)
                if column in {2, 3, 4, 5, 6}:
                    item.setTextAlignment(
                        Qt.AlignmentFlag.AlignRight
                        | Qt.AlignmentFlag.AlignVCenter,
                    )
                self.table.setItem(row, column, item)
        self.table.setSortingEnabled(True)

    def _selected_debt(self) -> Debt | None:
        """Devuelve la deuda seleccionada."""
        row = self.table.currentRow()
        if row < 0:
            return None
        item = self.table.item(row, 0)
        if item is None:
            return None
        debt_id = item.data(Qt.ItemDataRole.UserRole)
        return self._debts_by_id.get(str(debt_id))

    def _change_selected_state(self, active: bool) -> None:
        """Cambia el estado de la deuda seleccionada."""
        debt = self._selected_debt()
        if debt is None:
            self._show_info("Selecciona una deuda.")
            return
        try:
            if active:
                self.service.activar_deuda(debt.debt_id)
            else:
                self.service.desactivar_deuda(debt.debt_id)
        except ValueError as exc:
            self._show_error(str(exc))
            return
        self.refresh()

    @staticmethod
    def _format_clp(amount: int) -> str:
        """Formatea monto CLP."""
        prefix = "-$" if amount < 0 else "$"
        return f"{prefix} {abs(amount):,.0f}".replace(",", ".")

    def _show_error(self, message: str) -> None:
        """Muestra errores de servicio."""
        QMessageBox.critical(self, "Deudas", message)

    def _show_info(self, message: str) -> None:
        """Muestra mensajes informativos."""
        QMessageBox.information(self, "Deudas", message)
