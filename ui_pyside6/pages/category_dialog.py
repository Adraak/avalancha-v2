"""Dialogo PySide6 para crear y editar categorias."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLineEdit,
    QVBoxLayout,
)

from core.models.categoria import Categoria


class CategoryDialog(QDialog):
    """Formulario modal para capturar categorias financieras."""

    def __init__(
        self,
        categoria: Categoria | None = None,
        parent: object | None = None,
    ) -> None:
        """Inicializa el dialogo en modo creacion o edicion."""
        super().__init__(parent)
        self.categoria = categoria
        self.setWindowTitle("Editar categoría" if categoria else "Nueva categoría")
        self.setMinimumWidth(420)
        self.name_input = QLineEdit()
        self.type_input = QComboBox()
        self.class_input = QComboBox()
        self.active_input = QCheckBox("Activa")
        self._build_ui()
        self._load_initial_values()

    def obtener_datos(self) -> dict[str, object]:
        """Devuelve los datos capturados para el servicio."""
        return {
            "nombre": self.name_input.text(),
            "tipo": self.type_input.currentData(),
            "clase": self.class_input.currentData(),
            "color_key": self.categoria.color_key if self.categoria else None,
            "activa": self.active_input.isChecked(),
        }

    def _build_ui(self) -> None:
        """Construye los controles del formulario."""
        layout = QVBoxLayout(self)
        form = QFormLayout()
        form.setFieldGrowthPolicy(
            QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow,
        )

        self.type_input.addItem("Ingreso", "ingreso")
        self.type_input.addItem("Gasto", "gasto")
        self.type_input.addItem("Ambos", "ambos")
        self.class_input.addItem("Fija", "fija")
        self.class_input.addItem("Variable", "variable")
        self.active_input.setChecked(True)

        form.addRow("Nombre", self.name_input)
        form.addRow("Tipo", self.type_input)
        form.addRow("Clase", self.class_input)
        form.addRow("Estado", self.active_input)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel,
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("Guardar")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Cancelar")

        layout.addLayout(form)
        layout.addWidget(buttons)

    def _load_initial_values(self) -> None:
        """Carga valores existentes en modo edicion."""
        if self.categoria is None:
            return
        self.name_input.setText(self.categoria.nombre)
        type_index = self.type_input.findData(self.categoria.tipo)
        if type_index >= 0:
            self.type_input.setCurrentIndex(type_index)
        class_index = self.class_input.findData(self.categoria.clase)
        if class_index >= 0:
            self.class_input.setCurrentIndex(class_index)
        self.active_input.setChecked(self.categoria.activa)
