"""Pagina funcional de conciliacion para Avalancha V2."""

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

from core.models.conciliacion import Conciliacion
from services.reconciliation_service import ReconciliationService
from ui_pyside6.pages.base_page import ErrorAwarePage
from ui_pyside6.pages.reconciliation_dialog import ReconciliationDialog


class SortableItem(QTableWidgetItem):
    """Item de tabla con valor interno de orden."""

    def __init__(self, text: str, sort_value: object | None = None) -> None:
        """Inicializa texto y valor de orden."""
        super().__init__(text)
        self.sort_value = sort_value if sort_value is not None else text

    def __lt__(self, other: QTableWidgetItem) -> bool:
        """Ordena por valor interno."""
        if isinstance(other, SortableItem):
            return self.sort_value < other.sort_value
        return super().__lt__(other)


class ReconciliationPage(ErrorAwarePage):
    """Pantalla CRUD de conciliacion usando ReconciliationService."""

    HEADERS = [
        "Cuenta",
        "Saldo registrado",
        "Saldo real",
        "Diferencia",
        "Fecha ultima conciliacion",
        "Estado",
    ]

    def __init__(
        self,
        service: ReconciliationService | None = None,
    ) -> None:
        """Inicializa la pantalla funcional de conciliacion."""
        super().__init__()
        self.service = service or ReconciliationService()
        self.table = QTableWidget()
        self._items_by_id: dict[str, Conciliacion] = {}
        self._build_ui()
        self.refresh()

    def refresh(self) -> None:
        """Actualiza la tabla desde el servicio."""
        self._populate_table(self.service.obtener_conciliaciones())

    def new_reconciliation(self) -> None:
        """Abre dialogo de nueva conciliacion."""
        dialog = ReconciliationDialog(self.service, parent=self)
        if dialog.exec() != ReconciliationDialog.DialogCode.Accepted:
            return
        try:
            self.service.crear_conciliacion(dialog.obtener_datos())
        except ValueError as exc:
            self._show_error(
                self._value_error_message(
                    exc,
                    context="reconciliation.create",
                    fallback="No fue posible crear la conciliación.",
                ),
            )
            return
        self.refresh()

    def edit_selected(self) -> None:
        """Edita la conciliacion seleccionada."""
        reconciliation = self._selected_reconciliation()
        if reconciliation is None:
            self._show_info("Selecciona una conciliacion para editar.")
            return
        dialog = ReconciliationDialog(self.service, reconciliation, self)
        if dialog.exec() != ReconciliationDialog.DialogCode.Accepted:
            return
        try:
            self.service.editar_conciliacion(
                reconciliation.id,
                dialog.obtener_datos(),
            )
        except ValueError as exc:
            self._show_error(
                self._value_error_message(
                    exc,
                    context="reconciliation.edit",
                    fallback="No fue posible editar la conciliación.",
                ),
            )
            return
        self.refresh()

    def delete_selected(self) -> None:
        """Elimina la conciliacion seleccionada."""
        reconciliation = self._selected_reconciliation()
        if reconciliation is None:
            self._show_info("Selecciona una conciliacion para eliminar.")
            return
        response = QMessageBox.question(
            self,
            "Eliminar conciliacion",
            "¿Eliminar los datos de conciliacion seleccionados?",
        )
        if response != QMessageBox.StandardButton.Yes:
            return
        try:
            self.service.eliminar_conciliacion(reconciliation.id)
        except ValueError as exc:
            self._show_error(
                self._value_error_message(
                    exc,
                    context="reconciliation.delete",
                    fallback="No fue posible eliminar la conciliación.",
                ),
            )
            return
        self.refresh()

    def mark_reviewed(self) -> None:
        """Marca la conciliacion seleccionada como revisada."""
        reconciliation = self._selected_reconciliation()
        if reconciliation is None:
            self._show_info("Selecciona una conciliacion para revisar.")
            return
        try:
            self.service.marcar_como_revisada(reconciliation.id)
        except ValueError as exc:
            self._show_error(
                self._value_error_message(
                    exc,
                    context="reconciliation.mark_reviewed",
                    fallback="No fue posible marcar la conciliación como revisada.",
                ),
            )
            return
        self.refresh()

    def _build_ui(self) -> None:
        """Construye tabla y acciones."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 28, 28, 28)
        layout.setSpacing(16)

        title = QLabel("Conciliacion")
        title.setObjectName("PageTitle")

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
        self.table.doubleClicked.connect(self.edit_selected)
        self.table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch,
        )

        buttons = QHBoxLayout()
        new_button = QPushButton("Nueva conciliacion")
        edit_button = QPushButton("Editar")
        delete_button = QPushButton("Eliminar")
        reviewed_button = QPushButton("Marcar revisada")
        refresh_button = QPushButton("Actualizar")

        new_button.clicked.connect(self.new_reconciliation)
        edit_button.clicked.connect(self.edit_selected)
        delete_button.clicked.connect(self.delete_selected)
        reviewed_button.clicked.connect(self.mark_reviewed)
        refresh_button.clicked.connect(self.refresh)

        buttons.addStretch(1)
        buttons.addWidget(new_button)
        buttons.addWidget(edit_button)
        buttons.addWidget(delete_button)
        buttons.addWidget(reviewed_button)
        buttons.addWidget(refresh_button)

        layout.addWidget(title)
        layout.addWidget(self.table, stretch=1)
        layout.addLayout(buttons)

    def _populate_table(self, items: list[Conciliacion]) -> None:
        """Carga conciliaciones en la tabla."""
        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)
        self._items_by_id = {item.id: item for item in items}

        for row, item in enumerate(items):
            self.table.insertRow(row)
            account_name = self.service.nombre_cuenta(item.cuenta_id)
            difference = item.diferencia if item.diferencia is not None else 0
            values = [
                (account_name, account_name.casefold()),
                (self._format_clp(item.saldo_registrado), item.saldo_registrado),
                (
                    self._format_optional_clp(item.saldo_real),
                    item.saldo_real if item.saldo_real is not None else -10**18,
                ),
                (self._format_clp(difference), difference),
                (
                    item.fecha_conciliacion.strftime("%d-%m-%Y"),
                    item.fecha_conciliacion.isoformat(),
                ),
                (item.estado, item.estado),
            ]
            for column, (text, sort_value) in enumerate(values):
                cell = SortableItem(text, sort_value)
                if column == 0:
                    cell.setData(Qt.ItemDataRole.UserRole, item.id)
                if column in {1, 2, 3}:
                    cell.setTextAlignment(
                        Qt.AlignmentFlag.AlignRight
                        | Qt.AlignmentFlag.AlignVCenter,
                    )
                self.table.setItem(row, column, cell)

        self.table.setSortingEnabled(True)

    def _selected_reconciliation(self) -> Conciliacion | None:
        """Devuelve la conciliacion seleccionada."""
        row = self.table.currentRow()
        if row < 0:
            return None
        item = self.table.item(row, 0)
        if item is None:
            return None
        reconciliation_id = item.data(Qt.ItemDataRole.UserRole)
        return self._items_by_id.get(reconciliation_id)

    @staticmethod
    def _format_optional_clp(amount: int | None) -> str:
        """Formatea saldos opcionales."""
        if amount is None:
            return "Sin datos"
        return ReconciliationPage._format_clp(amount)

    @staticmethod
    def _format_clp(amount: int) -> str:
        """Formatea un monto CLP."""
        prefix = "-$ " if amount < 0 else "$ "
        return prefix + f"{abs(amount):,.0f}".replace(",", ".")

    def _show_error(self, message: str) -> None:
        """Muestra errores de servicio."""
        QMessageBox.critical(self, "Conciliacion", message)

    def _show_info(self, message: str) -> None:
        """Muestra mensajes informativos."""
        QMessageBox.information(self, "Conciliacion", message)

