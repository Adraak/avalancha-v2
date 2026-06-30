"""Punto de entrada de Avalancha Desktop."""

from __future__ import annotations

import ctypes
import sys


def activar_dpi_awareness() -> None:
    """Activa compatibilidad HiDPI en Windows antes de crear Tk."""
    if sys.platform != "win32":
        return

    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


if __name__ == "__main__":
    activar_dpi_awareness()
    from avalancha.app import main

    main()
