"""Pagina funcional de movimientos para Avalancha V2."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.models.movimiento import Movimiento
from services.movement_service import MovementService
from ui_pyside6.pages.movement_dialog import MovementDialog


class SortableItem(QTableWidgetItem):
    """Item de tabla que ordena por un valor interno."""

    def __init__(self, text: str, sort_value: object | None = None) -> None:
        """Inicializa el item con texto visible y valor de orden."""
        super().__init__(text)
        self.sort_value = sort_value if sort_value is not None else text

    def __lt__(self, other: QTableWidgetItem) -> bool:
        """Compara usando el valor interno cuando existe."""
        if isinstance(other, SortableItem):
            return self.sort_value < other.sort_value
        return super().__lt__(other)


class MovementsPage(QWidget):
    """Pantalla CRUD de movimientos usando MovementService."""

    HEADERS = ["Fecha", "Categoria", "Cuenta", "Tipo", "Descripcion", "Monto"]

    def __init__(self, service: MovementService | None = None) -> None:
        """Inicializa la pagina funcional de movimientos."""
        super().__init__()
        self.service = service or MovementService()
        self.search_input = QLineEdit()
        self.table = QTableWidget()
        self._movements_by_id: dict[str, Movimiento] = {}
        self._build_ui()
        self.refresh()

    def refresh(self) -> None:
        """Actualiza la tabla usando el filtro vigente."""
        movements = self.service.buscar_movimientos(self.search_input.text())
        self._populate_table(movements)

    def new_movement(self) -> None:
        """Abre el dialogo para crear un movimiento."""
        dialog = MovementDialog(self.service, parent=self)
        if dialog.exec() != MovementDialog.DialogCode.Accepted:
            return
        try:
            self.service.crear_movimiento(**dialog.obtener_datos())
        except ValueError as exc:
            self._show_error(str(exc))
            return
        self.refresh()

    def edit_selected(self) -> None:
        """Edita el movimiento seleccionado."""
        movement = self._selected_movement()
        if movement is None:
            self._show_info("Selecciona un movimiento para editar.")
            return
        dialog = MovementDialog(self.service, movement, self)
        if dialog.exec() != MovementDialog.DialogCode.Accepted:
            return
        try:
            self.service.editar_movimiento(
                movement.id,
                **dialog.obtener_datos(),
            )
        except ValueError as exc:
            self._show_error(str(exc))
            return
        self.refresh()

    def delete_selected(self) -> None:
        """Elimina el movimiento seleccionado tras confirmar."""
        movement = self._selected_movement()
        if movement is None:
            self._show_info("Selecciona un movimiento para eliminar.")
            return
        response = QMessageBox.question(
            self,
            "Eliminar movimiento",
            "¿Eliminar el movimiento seleccionado?",
        )
        if response != QMessageBox.StandardButton.Yes:
            return
        try:
            self.service.eliminar_movimiento(movement.id)
        except ValueError as exc:
            self._show_error(str(exc))
            return
        self.refresh()

    def _build_ui(self) -> None:
        """Construye buscador, tabla y botones de accion."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 28, 28, 28)
        layout.setSpacing(16)

        title = QLabel("Movimientos")
        title.setObjectName("PageTitle")

        top_bar = QHBoxLayout()
        self.search_input.setPlaceholderText("Buscar movimiento")
        self.search_input.textChanged.connect(self.refresh)

        new_top_button = QPushButton("Nuevo Movimiento")
        new_top_button.clicked.connect(self.new_movement)

        top_bar.addWidget(self.search_input, stretch=1)
        top_bar.addWidget(new_top_button)

        self.table.setColumnCount(len(self.HEADERS))
        self.table.setHorizontalHeaderLabels(self.HEADERS)
        self.table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows,
        )
        self.table.setSelectionMode(
            QTableWidget.SelectionMode.SingleSelection,
        )
        self.table.setEditTriggers(
            QTableWidget.EditTrigger.NoEditTriggers,
        )
        self.table.setSortingEnabled(True)
        self.table.doubleClicked.connect(self.edit_selected)
        self.table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch,
        )
        self.table.horizontalHeader().setSectionsClickable(True)

        bottom_bar = QHBoxLayout()
        new_button = QPushButton("Nuevo")
        edit_button = QPushButton("Editar")
        delete_button = QPushButton("Eliminar")
        refresh_button = QPushButton("Actualizar")

        new_button.clicked.connect(self.new_movement)
        edit_button.clicked.connect(self.edit_selected)
        delete_button.clicked.connect(self.delete_selected)
        refresh_button.clicked.connect(self.refresh)

        bottom_bar.addStretch(1)
        bottom_bar.addWidget(new_button)
        bottom_bar.addWidget(edit_button)
        bottom_bar.addWidget(delete_button)
        bottom_bar.addWidget(refresh_button)

        layout.addWidget(title)
        layout.addLayout(top_bar)
        layout.addWidget(self.table, stretch=1)
        layout.addLayout(bottom_bar)

    def _populate_table(self, movements: list[Movimiento]) -> None:
        """Carga movimientos en la tabla."""
        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)
        self._movements_by_id = {item.id: item for item in movements}

        for row, movement in enumerate(movements):
            self.table.insertRow(row)
            account_name = self.service.nombre_cuenta(movement.cuenta_id)
            values = [
                (
                    movement.fecha.strftime("%d-%m-%Y"),
                    movement.fecha.isoformat(),
                ),
                (movement.categoria, movement.categoria.casefold()),
                (account_name, account_name.casefold()),
                (movement.tipo.capitalize(), movement.tipo),
                (movement.descripcion, movement.descripcion.casefold()),
                (self._format_clp(movement.monto), movement.monto),
            ]
            for column, (text, sort_value) in enumerate(values):
                item = SortableItem(text, sort_value)
                if column == 0:
                    item.setData(Qt.ItemDataRole.UserRole, movement.id)
                if column == 5:
                    item.setTextAlignment(
                        Qt.AlignmentFlag.AlignRight
                        | Qt.AlignmentFlag.AlignVCenter,
                    )
                self.table.setItem(row, column, item)

        self.table.setSortingEnabled(True)

    def _selected_movement(self) -> Movimiento | None:
        """Devuelve el movimiento seleccionado o None."""
        row = self.table.currentRow()
        if row < 0:
            return None
        item = self.table.item(row, 0)
        if item is None:
            return None
        movement_id = item.data(Qt.ItemDataRole.UserRole)
        return self._movements_by_id.get(movement_id)

    @staticmethod
    def _format_clp(amount: int) -> str:
        """Formatea un monto como CLP."""
        return f"$ {amount:,.0f}".replace(",", ".")

    def _show_error(self, message: str) -> None:
        """Muestra un error de validacion o persistencia."""
        QMessageBox.critical(self, "No se pudo guardar", message)

    def _show_info(self, message: str) -> None:
        """Muestra un mensaje informativo."""
        QMessageBox.information(self, "Movimientos", message)

