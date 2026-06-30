"""Punto de entrada de Avalancha V2 con PySide6."""

from __future__ import annotations

import sys
from os import environ

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from ui_pyside6.main_window import MainWindow


def main() -> int:
    """Inicia la aplicación mínima de Avalancha V2."""
    app = QApplication(sys.argv)
    ventana = MainWindow()
    ventana.show()
    _configurar_cierre_de_prueba(app)
    return app.exec()


def _configurar_cierre_de_prueba(app: QApplication) -> None:
    """Cierra la app automáticamente solo si una prueba lo solicita."""
    valor = environ.get("AVALANCHA_V2_AUTO_CLOSE_MS", "").strip()
    if not valor:
        return
    try:
        milisegundos = int(valor)
    except ValueError:
        return
    QTimer.singleShot(max(milisegundos, 0), app.quit)


if __name__ == "__main__":
    raise SystemExit(main())
