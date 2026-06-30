"""Tema visual claro de Avalancha V2."""

from __future__ import annotations


COLOR_FONDO = "#f3f6f8"
COLOR_PANEL = "#ffffff"
COLOR_MENU = "#12324a"
COLOR_MENU_ACTIVO = "#1f6f8b"
COLOR_MENU_HOVER = "#19465f"
COLOR_TEXTO = "#1f2933"
COLOR_TEXTO_SUAVE = "#6b7785"
COLOR_BORDE = "#d8e1e7"
COLOR_ACENTO = "#007c89"
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
        border-right: 1px solid {COLOR_MENU};
    }}

    QPushButton[menuButton="true"] {{
        background: transparent;
        color: #e9f0f4;
        border: none;
        border-radius: 8px;
        padding: 11px 14px;
        text-align: left;
        font-size: 13px;
        font-weight: 600;
    }}

    QPushButton[menuButton="true"]:hover {{
        background: {COLOR_MENU_HOVER};
    }}

    QPushButton[menuButton="true"]:checked {{
        background: {COLOR_MENU_ACTIVO};
        color: #ffffff;
    }}

    #ContentPanel {{
        background: {COLOR_PANEL};
        border: 1px solid {COLOR_BORDE};
        border-radius: 10px;
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
