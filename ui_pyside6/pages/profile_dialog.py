"""Dialogo para crear perfiles locales."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLineEdit,
    QVBoxLayout,
    QWidget,
)


class ProfileDialog(QDialog):
    """Solicita el nombre de un nuevo perfil local."""

    def __init__(self, parent: QWidget | None = None) -> None:
        """Inicializa el dialogo de perfil."""
        super().__init__(parent)
        self.setWindowTitle("Crear perfil")
        self.name_input = QLineEdit()
        self._build_ui()

    def nombre(self) -> str:
        """Devuelve el nombre ingresado."""
        return self.name_input.text().strip()

    def _build_ui(self) -> None:
        """Construye el formulario."""
        layout = QVBoxLayout(self)
        form = QFormLayout()
        form.addRow("Nombre", self.name_input)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel,
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout.addLayout(form)
        layout.addWidget(buttons)
