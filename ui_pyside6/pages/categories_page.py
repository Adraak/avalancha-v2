"""Pagina funcional de categorias para Avalancha V2."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
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

from core.models.categoria import Categoria
from services.category_service import CategoryService
from ui_pyside6.pages.base_page import ErrorAwarePage
from ui_pyside6.pages.category_dialog import CategoryDialog


class CategoryItem(QTableWidgetItem):
    """Item de tabla con valor de orden independiente."""

    def __init__(self, text: str, sort_value: object | None = None) -> None:
        """Inicializa texto visible y valor de orden."""
        super().__init__(text)
        self.sort_value = sort_value if sort_value is not None else text

    def __lt__(self, other: QTableWidgetItem) -> bool:
        """Ordena por valor interno cuando corresponde."""
        if isinstance(other, CategoryItem):
            return self.sort_value < other.sort_value
        return super().__lt__(other)


class CategoriesPage(ErrorAwarePage):
    """Pantalla CRUD de categorías usando CategoryService."""

    HEADERS = ["Nombre", "Tipo", "Clase", "Estado", "Color"]

    def __init__(self, service: CategoryService | None = None) -> None:
        """Inicializa la pantalla funcional de categorías."""
        super().__init__()
        self.service = service or CategoryService()
        self.table = QTableWidget()
        self.status_filter = QComboBox()
        self.type_filter = QComboBox()
        self._categories_by_id: dict[str, Categoria] = {}
        self._build_ui()
        self.refresh()

    def refresh(self) -> None:
        """Actualiza la tabla desde el servicio."""
        self._populate_table(self.service.listar_categorias())

    def new_category(self) -> None:
        """Abre diálogo de creación."""
        dialog = CategoryDialog(parent=self)
        if dialog.exec() != CategoryDialog.DialogCode.Accepted:
            return
        data = dialog.obtener_datos()
        try:
            self.service.crear_categoria(
                nombre=str(data["nombre"]),
                tipo=str(data["tipo"]),
                clase=str(data["clase"]),
                color_key=(
                    str(data["color_key"])
                    if data.get("color_key") is not None
                    else None
                ),
            )
        except ValueError as exc:
            self._show_error(
                self._value_error_message(
                    exc,
                    context="categories.create",
                    fallback="No fue posible crear la categoría.",
                ),
            )
            return
        self.refresh()

    def edit_selected(self) -> None:
        """Edita la categoría seleccionada."""
        categoria = self._selected_category()
        if categoria is None:
            self._show_info("Selecciona una categoría para editar.")
            return
        dialog = CategoryDialog(categoria, self)
        if dialog.exec() != CategoryDialog.DialogCode.Accepted:
            return
        data = dialog.obtener_datos()
        try:
            self.service.editar_categoria(
                categoria.id,
                nombre=str(data["nombre"]),
                tipo=str(data["tipo"]),
                clase=str(data["clase"]),
                color_key=(
                    str(data["color_key"])
                    if data.get("color_key") is not None
                    else None
                ),
                activa=bool(data["activa"]),
            )
        except ValueError as exc:
            self._show_error(
                self._value_error_message(
                    exc,
                    context="categories.edit",
                    fallback="No fue posible editar la categoría.",
                ),
            )
            return
        self.refresh()

    def deactivate_selected(self) -> None:
        """Desactiva la categoría seleccionada."""
        categoria = self._selected_category()
        if categoria is None:
            self._show_info("Selecciona una categoría para desactivar.")
            return
        try:
            self.service.desactivar_categoria(categoria.id)
        except ValueError as exc:
            self._show_error(
                self._value_error_message(
                    exc,
                    context="categories.deactivate",
                    fallback="No fue posible desactivar la categoría.",
                ),
            )
            return
        self.refresh()

    def activate_selected(self) -> None:
        """Reactiva la categoría seleccionada."""
        categoria = self._selected_category()
        if categoria is None:
            self._show_info("Selecciona una categoría para reactivar.")
            return
        try:
            self.service.activar_categoria(categoria.id)
        except ValueError as exc:
            self._show_error(
                self._value_error_message(
                    exc,
                    context="categories.activate",
                    fallback="No fue posible activar la categoría.",
                ),
            )
            return
        self.refresh()

    def delete_selected(self) -> None:
        """Evita borrado físico cuando existe historial asociado."""
        categoria = self._selected_category()
        if categoria is None:
            self._show_info("Selecciona una categoría para revisar.")
            return
        if not self.service.puede_eliminar_categoria(categoria.id):
            self._show_info(
                "La categoría tiene historial. Se desactivará para "
                "mantener reportes y movimientos antiguos.",
            )
            self.deactivate_selected()
            return
        response = QMessageBox.question(
            self,
            "Eliminar categoría",
            "La categoría no tiene historial. Se recomienda desactivarla. "
            "¿Deseas desactivarla ahora?",
        )
        if response == QMessageBox.StandardButton.Yes:
            self.deactivate_selected()

    def _build_ui(self) -> None:
        """Construye filtros, tabla y barra de acciones."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 28, 28, 28)
        layout.setSpacing(16)

        title = QLabel("Categorías")
        title.setObjectName("PageTitle")

        filters = QHBoxLayout()
        self.status_filter.addItem("Activas", "activas")
        self.status_filter.addItem("Inactivas", "inactivas")
        self.status_filter.addItem("Todas", "todas")
        self.type_filter.addItem("Todos los tipos", "todos")
        self.type_filter.addItem("Ingreso", "ingreso")
        self.type_filter.addItem("Gasto", "gasto")
        self.type_filter.addItem("Ambos", "ambos")
        self.status_filter.currentIndexChanged.connect(self.refresh)
        self.type_filter.currentIndexChanged.connect(self.refresh)
        filters.addWidget(QLabel("Estado"))
        filters.addWidget(self.status_filter)
        filters.addWidget(QLabel("Tipo"))
        filters.addWidget(self.type_filter)
        filters.addStretch(1)

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
        new_button = QPushButton("Nueva categoría")
        edit_button = QPushButton("Editar")
        deactivate_button = QPushButton("Desactivar")
        activate_button = QPushButton("Reactivar")
        delete_button = QPushButton("Eliminar")
        refresh_button = QPushButton("Actualizar")

        new_button.clicked.connect(self.new_category)
        edit_button.clicked.connect(self.edit_selected)
        deactivate_button.clicked.connect(self.deactivate_selected)
        activate_button.clicked.connect(self.activate_selected)
        delete_button.clicked.connect(self.delete_selected)
        refresh_button.clicked.connect(self.refresh)

        buttons.addStretch(1)
        buttons.addWidget(new_button)
        buttons.addWidget(edit_button)
        buttons.addWidget(deactivate_button)
        buttons.addWidget(activate_button)
        buttons.addWidget(delete_button)
        buttons.addWidget(refresh_button)

        layout.addWidget(title)
        layout.addLayout(filters)
        layout.addWidget(self.table, stretch=1)
        layout.addLayout(buttons)

    def _populate_table(self, categories: list[Categoria]) -> None:
        """Carga categorías filtradas en la tabla."""
        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)
        self._categories_by_id = {}
        rows = self._filtrar(categories)

        for row_index, categoria in enumerate(rows):
            self._categories_by_id[categoria.id] = categoria
            self.table.insertRow(row_index)
            values = [
                (categoria.nombre, categoria.nombre.casefold()),
                (self._titulo(categoria.tipo), categoria.tipo),
                (self._titulo(categoria.clase), categoria.clase),
                ("Activa" if categoria.activa else "Inactiva", categoria.activa),
                (
                    categoria.color_key or "Automático",
                    categoria.color_key or "Automático",
                ),
            ]
            for column, (text, sort_value) in enumerate(values):
                item = CategoryItem(str(text), sort_value)
                if column == 0:
                    item.setData(Qt.ItemDataRole.UserRole, categoria.id)
                self.table.setItem(row_index, column, item)

        self.table.setSortingEnabled(True)

    def _filtrar(self, categories: list[Categoria]) -> list[Categoria]:
        """Aplica filtros visuales sin decidir reglas financieras."""
        status_filter = self.status_filter.currentData()
        type_filter = self.type_filter.currentData()
        rows = []
        for categoria in categories:
            if status_filter == "activas" and not categoria.activa:
                continue
            if status_filter == "inactivas" and categoria.activa:
                continue
            if type_filter != "todos" and categoria.tipo != type_filter:
                continue
            rows.append(categoria)
        return rows

    def _selected_category(self) -> Categoria | None:
        """Devuelve la categoría seleccionada."""
        row = self.table.currentRow()
        if row < 0:
            return None
        item = self.table.item(row, 0)
        if item is None:
            return None
        category_id = item.data(Qt.ItemDataRole.UserRole)
        return self._categories_by_id.get(category_id)

    @staticmethod
    def _titulo(value: str) -> str:
        """Convierte un valor tecnico en texto visible simple."""
        return value[:1].upper() + value[1:]

    def _show_error(self, message: str) -> None:
        """Muestra errores de validación."""
        QMessageBox.critical(self, "Categorías", message)

    def _show_info(self, message: str) -> None:
        """Muestra mensajes informativos."""
        QMessageBox.information(self, "Categorías", message)
