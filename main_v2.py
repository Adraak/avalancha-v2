"""Punto de entrada de Avalancha V2 con PySide6."""

from __future__ import annotations

import sys
from os import environ

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QMessageBox

from services.error_reporting_service import SafeErrorReporter
from ui_pyside6.main_window import MainWindow


def main() -> int:
    """Inicia Avalancha V2 con diagnóstico local seguro."""
    app = QApplication(sys.argv)
    reporter = SafeErrorReporter()
    _instalar_manejador_global(reporter)
    try:
        ventana = MainWindow()
    except Exception as exc:
        notice = reporter.report(
            exc,
            context="app.startup",
            user_message=(
                "Avalancha no pudo iniciar correctamente. "
                "El diagnóstico técnico quedó registrado localmente."
            ),
        )
        QMessageBox.critical(None, "Avalancha", notice.message)
        return 1
    ventana.show()
    _configurar_cierre_de_prueba(app)
    return app.exec()


def _instalar_manejador_global(reporter: SafeErrorReporter) -> None:
    """Evita mostrar tracebacks crudos ante excepciones no controladas."""
    def handle(
        exc_type: type[BaseException],
        exc_value: BaseException,
        exc_traceback: object,
    ) -> None:
        if issubclass(exc_type, (KeyboardInterrupt, SystemExit)):
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return
        notice = reporter.report(
            exc_value,
            context="app.unhandled",
            user_message=(
                "Ocurrió un error inesperado. "
                "El diagnóstico técnico quedó registrado localmente."
            ),
        )
        QMessageBox.critical(None, "Error inesperado", notice.message)

    sys.excepthook = handle


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
