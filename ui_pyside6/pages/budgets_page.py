"""Pagina funcional de presupuestos para Avalancha V2."""

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

from core.models.presupuesto import Presupuesto
from services.budget_service import BudgetService
from ui_pyside6.pages.budget_dialog import BudgetDialog


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


class BudgetsPage(QWidget):
    """Pantalla CRUD de presupuestos usando BudgetService."""

    HEADERS = [
        "Categoria",
        "Presupuesto",
        "Gastado",
        "Disponible",
        "Porcentaje",
        "Estado",
    ]

    def __init__(self, service: BudgetService | None = None) -> None:
        """Inicializa la pantalla funcional de presupuestos."""
        super().__init__()
        self.service = service or BudgetService()
        self.table = QTableWidget()
        self._budgets_by_id: dict[str, Presupuesto] = {}
        self._build_ui()
        self.refresh()

    def refresh(self) -> None:
        """Actualiza la tabla desde el servicio."""
        self._populate_table(self.service.calcular_ejecucion_general())

    def new_budget(self) -> None:
        """Abre dialogo de creacion."""
        dialog = BudgetDialog(self.service, parent=self)
        if dialog.exec() != BudgetDialog.DialogCode.Accepted:
            return
        try:
            self.service.crear_presupuesto(dialog.obtener_datos())
        except ValueError as exc:
            self._show_error(str(exc))
            return
        self.refresh()

    def edit_selected(self) -> None:
        """Edita el presupuesto seleccionado."""
        presupuesto = self._selected_budget()
        if presupuesto is None:
            self._show_info("Selecciona un presupuesto para editar.")
            return
        dialog = BudgetDialog(self.service, presupuesto, self)
        if dialog.exec() != BudgetDialog.DialogCode.Accepted:
            return
        try:
            self.service.editar_presupuesto(
                presupuesto.id,
                dialog.obtener_datos(),
            )
        except ValueError as exc:
            self._show_error(str(exc))
            return
        self.refresh()

    def delete_selected(self) -> None:
        """Elimina el presupuesto seleccionado."""
        presupuesto = self._selected_budget()
        if presupuesto is None:
            self._show_info("Selecciona un presupuesto para eliminar.")
            return
        response = QMessageBox.question(
            self,
            "Eliminar presupuesto",
            "¿Eliminar el presupuesto seleccionado?",
        )
        if response != QMessageBox.StandardButton.Yes:
            return
        try:
            self.service.eliminar_presupuesto(presupuesto.id)
        except ValueError as exc:
            self._show_error(str(exc))
            return
        self.refresh()

    def activate_selected(self) -> None:
        """Activa el presupuesto seleccionado."""
        presupuesto = self._selected_budget()
        if presupuesto is None:
            self._show_info("Selecciona un presupuesto para activar.")
            return
        try:
            self.service.activar_presupuesto(presupuesto.id)
        except ValueError as exc:
            self._show_error(str(exc))
            return
        self.refresh()

    def deactivate_selected(self) -> None:
        """Desactiva el presupuesto seleccionado."""
        presupuesto = self._selected_budget()
        if presupuesto is None:
            self._show_info("Selecciona un presupuesto para desactivar.")
            return
        try:
            self.service.desactivar_presupuesto(presupuesto.id)
        except ValueError as exc:
            self._show_error(str(exc))
            return
        self.refresh()

    def _build_ui(self) -> None:
        """Construye tabla y barra de acciones."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 28, 28, 28)
        layout.setSpacing(16)

        title = QLabel("Presupuestos")
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
        new_button = QPushButton("Nuevo")
        edit_button = QPushButton("Editar")
        delete_button = QPushButton("Eliminar")
        activate_button = QPushButton("Activar")
        deactivate_button = QPushButton("Desactivar")
        refresh_button = QPushButton("Actualizar")

        new_button.clicked.connect(self.new_budget)
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

    def _populate_table(self, rows: list[dict[str, object]]) -> None:
        """Carga presupuestos y ejecucion en la tabla."""
        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)
        self._budgets_by_id = {}

        for row_index, row in enumerate(rows):
            presupuesto = row["presupuesto"]
            ejecucion = row["ejecucion"]
            if not isinstance(presupuesto, Presupuesto):
                continue
            self._budgets_by_id[presupuesto.id] = presupuesto
            self.table.insertRow(row_index)
            values = [
                (presupuesto.categoria, presupuesto.categoria.casefold()),
                (
                    self._format_clp(ejecucion.monto_presupuestado),
                    ejecucion.monto_presupuestado,
                ),
                (
                    self._format_clp(ejecucion.monto_gastado),
                    ejecucion.monto_gastado,
                ),
                (
                    self._format_clp(ejecucion.saldo_disponible),
                    ejecucion.saldo_disponible,
                ),
                (
                    f"{ejecucion.porcentaje_utilizado:.1f}%",
                    ejecucion.porcentaje_utilizado,
                ),
                (
                    self._estado_texto(presupuesto.activo, ejecucion.estado_visual),
                    ejecucion.estado_visual,
                ),
            ]
            for column, (text, sort_value) in enumerate(values):
                item = SortableItem(text, sort_value)
                if column == 0:
                    item.setData(Qt.ItemDataRole.UserRole, presupuesto.id)
                if column in {1, 2, 3, 4}:
                    item.setTextAlignment(
                        Qt.AlignmentFlag.AlignRight
                        | Qt.AlignmentFlag.AlignVCenter,
                    )
                self.table.setItem(row_index, column, item)

        self.table.setSortingEnabled(True)

    def _selected_budget(self) -> Presupuesto | None:
        """Devuelve el presupuesto seleccionado."""
        row = self.table.currentRow()
        if row < 0:
            return None
        item = self.table.item(row, 0)
        if item is None:
            return None
        presupuesto_id = item.data(Qt.ItemDataRole.UserRole)
        return self._budgets_by_id.get(presupuesto_id)

    @staticmethod
    def _format_clp(amount: int) -> str:
        """Formatea monto CLP."""
        prefix = "-$ " if amount < 0 else "$ "
        return prefix + f"{abs(amount):,.0f}".replace(",", ".")

    @staticmethod
    def _estado_texto(active: bool, estado: str) -> str:
        """Devuelve estado visible para tabla."""
        if not active:
            return "Inactivo"
        return estado.capitalize()

    def _show_error(self, message: str) -> None:
        """Muestra errores de validacion."""
        QMessageBox.critical(self, "Presupuestos", message)

    def _show_info(self, message: str) -> None:
        """Muestra mensajes informativos."""
        QMessageBox.information(self, "Presupuestos", message)

