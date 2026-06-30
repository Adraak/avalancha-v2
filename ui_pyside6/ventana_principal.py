"""Ventana inicial de Avalancha V2 en PySide6."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QLabel,
    QMainWindow,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class VentanaPrincipalV2(QMainWindow):
    """Ventana mínima para validar la migración a PySide6."""

    def __init__(self) -> None:
        """Inicializa la ventana principal de Avalancha V2."""
        super().__init__()
        self.setWindowTitle("Avalancha V2")
        self.resize(520, 240)
        self._construir_interfaz()

    def _construir_interfaz(self) -> None:
        """Construye el contenido inicial de validación."""
        contenedor = QWidget(self)
        layout = QVBoxLayout(contenedor)
        layout.setContentsMargins(32, 32, 32, 32)
        layout.setSpacing(18)

        mensaje = QLabel("Migración PySide6 iniciada")
        mensaje.setAlignment(Qt.AlignmentFlag.AlignCenter)
        mensaje.setStyleSheet("font-size: 18px; font-weight: 600;")

        boton_cerrar = QPushButton("Cerrar")
        boton_cerrar.clicked.connect(self.close)

        layout.addStretch(1)
        layout.addWidget(mensaje)
        layout.addWidget(boton_cerrar)
        layout.addStretch(1)

        self.setCentralWidget(contenedor)
