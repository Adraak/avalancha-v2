"""Tema visual claro de Avalancha V2."""

from __future__ import annotations

from ui_pyside6.color_system import (
    BORDER as COLOR_BORDE,
    INFO as COLOR_ACENTO,
    PANEL as COLOR_PANEL,
    TEXT as COLOR_TEXTO,
    TEXT_MUTED as COLOR_TEXTO_SUAVE,
)


COLOR_FONDO = "#f3f6f8"
COLOR_MENU = "#071526"
COLOR_MENU_ACTIVO = "#17457f"
COLOR_MENU_HOVER = "#10233a"
COLOR_MENU_TEXTO = "#d8e3ee"
COLOR_MENU_ACTIVO_TEXTO = "#ffffff"
FUENTE_BASE = "Segoe UI"


def hoja_estilos() -> str:
    """Devuelve la hoja de estilos principal de PySide6."""
    return f"""
    QMainWindow {{
        background: {COLOR_FONDO};
        font-family: "{FUENTE_BASE}";
    }}

    QLabel {{
        color: {COLOR_TEXTO};
    }}

    #TopBar {{
        background: {COLOR_PANEL};
        border-bottom: 1px solid {COLOR_BORDE};
    }}

    #AppTitle {{
        font-size: 24px;
        font-weight: 700;
        color: {COLOR_TEXTO};
    }}

    #AppSubtitle {{
        font-size: 12px;
        color: {COLOR_TEXTO_SUAVE};
    }}

    #ProfileLabel {{
        font-size: 13px;
        font-weight: 600;
        color: {COLOR_ACENTO};
    }}

    #SideMenu {{
        background: {COLOR_MENU};
        border-right: 1px solid #0b1f35;
    }}

    QPushButton[menuButton="true"] {{
        background: transparent;
        color: {COLOR_MENU_TEXTO};
        border: none;
        border-radius: 9px;
        padding: 12px 14px;
        text-align: left;
        font-size: 13px;
        font-weight: 600;
    }}

    QPushButton[menuButton="true"]:hover {{
        background: {COLOR_MENU_HOVER};
    }}

    QPushButton[menuButton="true"]:checked {{
        background: {COLOR_MENU_ACTIVO};
        color: {COLOR_MENU_ACTIVO_TEXTO};
    }}

    QPushButton[secondaryButton="true"] {{
        background: {COLOR_PANEL};
        color: {COLOR_TEXTO};
        border: 1px solid {COLOR_BORDE};
        border-radius: 8px;
        padding: 8px 14px;
        font-size: 12px;
        font-weight: 600;
    }}

    QPushButton[secondaryButton="true"]:hover {{
        background: #f8fbff;
        border-color: {COLOR_ACENTO};
    }}

    #ContentPanel {{
        background: transparent;
        border: none;
    }}

    #PageTitle {{
        font-size: 22px;
        font-weight: 700;
        color: {COLOR_TEXTO};
    }}

    #PageSubtitle {{
        font-size: 14px;
        color: {COLOR_TEXTO_SUAVE};
    }}

    #StatusBar {{
        background: {COLOR_PANEL};
        border-top: 1px solid {COLOR_BORDE};
    }}

    #StatusText {{
        color: {COLOR_TEXTO_SUAVE};
        font-size: 12px;
    }}
    """
