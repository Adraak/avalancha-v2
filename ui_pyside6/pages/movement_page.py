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

    HEADERS = [
        "Fecha",
        "Categoría",
        "Cuenta",
        "Tipo",
        "Descripcion",
        "Clase",
        "Monto",
    ]

    def __init__(self, service: MovementService | None = None) -> None:
        """Inicializa la pagina funcional de movimientos."""
        super().__init__()
        self.service = service or MovementService()
        self.search_input = QLineEdit()
        self.filter_label = QLabel("")
        self.clear_filter_button = QPushButton("Todos")
        self.table = QTableWidget()
        self._movements_by_id: dict[str, Movimiento] = {}
        self._account_filter_id: str | None = None
        self._account_filter_name: str = ""
        self._build_ui()
        self.refresh()

    def refresh(self) -> None:
        """Actualiza la tabla usando el filtro vigente."""
        if self._account_filter_id:
            movements = self.service.obtener_movimientos_por_cuenta(
                self._account_filter_id,
            )
            search_text = self.search_input.text().strip().casefold()
            if search_text:
                movements = self._filtrar_lista(movements, search_text)
        else:
            movements = self.service.buscar_movimientos(self.search_input.text())
        self._populate_table(movements)

    def filtrar_por_cuenta(self, cuenta_id: str, nombre: str = "") -> None:
        """Aplica filtro de movimientos asociados a una cuenta."""
        self._account_filter_id = cuenta_id
        self._account_filter_name = nombre or self.service.nombre_cuenta(
            cuenta_id,
        )
        self.filter_label.setText(f"Cuenta: {self._account_filter_name}")
        self.clear_filter_button.setVisible(True)
        self.refresh()

    def limpiar_filtro(self) -> None:
        """Limpia el filtro por cuenta y muestra todos los movimientos."""
        self._account_filter_id = None
        self._account_filter_name = ""
        self.filter_label.setText("")
        self.clear_filter_button.setVisible(False)
        self.refresh()

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
        top_bar.addWidget(self.filter_label)
        self.clear_filter_button.clicked.connect(self.limpiar_filtro)
        self.clear_filter_button.setVisible(False)
        top_bar.addWidget(self.clear_filter_button)
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
            QHeaderView.ResizeMode.Interactive,
        )
        self.table.horizontalHeader().setSectionsClickable(True)
        self._configure_table_columns()

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

    def _configure_table_columns(self) -> None:
        """Ajusta anchos para leer transferencias origen-destino."""
        widths = {
            0: 110,
            1: 170,
            2: 520,
            3: 120,
            4: 260,
            5: 130,
            6: 130,
        }
        for column, width in widths.items():
            self.table.setColumnWidth(column, width)

    def _populate_table(self, movements: list[Movimiento]) -> None:
        """Carga movimientos en la tabla."""
        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)
        self._movements_by_id = {item.id: item for item in movements}

        for row, movement in enumerate(movements):
            self.table.insertRow(row)
            account_name = self._account_display(movement)
            values = [
                (
                    movement.fecha.strftime("%d-%m-%Y"),
                    movement.fecha.isoformat(),
                ),
                (
                    self._category_display(movement),
                    self._category_display(movement).casefold(),
                ),
                (account_name, account_name.casefold()),
                (self._type_display(movement), movement.tipo),
                (movement.descripcion, movement.descripcion.casefold()),
                (movement.clase, movement.clase.casefold()),
                (self._format_clp(movement.monto), movement.monto),
            ]
            for column, (text, sort_value) in enumerate(values):
                item = SortableItem(text, sort_value)
                if column == 0:
                    item.setData(Qt.ItemDataRole.UserRole, movement.id)
                if column == 6:
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

    def _account_display(self, movement: Movimiento) -> str:
        """Devuelve cuenta visible, con origen y destino si aplica."""
        origin = self.service.nombre_cuenta(movement.cuenta_id)
        if not movement.es_transferencia:
            return origin
        destination = self.service.nombre_cuenta(
            movement.cuenta_destino_id or "",
        )
        return f"{origin} → {destination}"

    @staticmethod
    def _category_display(movement: Movimiento) -> str:
        """Devuelve categoria visible para la tabla."""
        if movement.es_transferencia:
            return "Transferencia interna"
        return movement.categoria

    @staticmethod
    def _type_display(movement: Movimiento) -> str:
        """Devuelve tipo visible en espanol."""
        if movement.es_transferencia:
            return "Transferencia"
        return movement.tipo.capitalize()

    def _show_error(self, message: str) -> None:
        """Muestra un error de validacion o persistencia."""
        QMessageBox.critical(self, "No se pudo guardar", message)

    def _show_info(self, message: str) -> None:
        """Muestra un mensaje informativo."""
        QMessageBox.information(self, "Movimientos", message)

    def _filtrar_lista(
        self,
        movements: list[Movimiento],
        search_text: str,
    ) -> list[Movimiento]:
        """Filtra una lista ya restringida por cuenta usando texto libre."""
        encontrados = []
        for movement in movements:
            contenido = " ".join(
                [
                    movement.fecha.strftime("%d-%m-%Y"),
                    movement.tipo,
                    movement.categoria,
                    movement.descripcion,
                    str(movement.monto),
                    self._account_display(movement),
                    movement.clase,
                ],
            ).casefold()
            if search_text in contenido:
                encontrados.append(movement)
        return encontrados
