"""Sistema centralizado de colores para Avalancha V2."""

from __future__ import annotations

import hashlib
import re


SUCCESS = "#138a43"
WARNING = "#f59e0b"
DANGER = "#dc2626"
DANGER_STRONG = "#991b1b"
INFO = "#007c89"
NEUTRAL = "#64748b"
TEXT = "#1f2933"
TEXT_MUTED = "#6b7785"
BORDER = "#d8e1e7"
PANEL = "#ffffff"
PANEL_SOFT = "#f8fafc"
BAR_BACKGROUND = "#eef3f5"

SEMANTIC_COLORS = {
    "success": SUCCESS,
    "saludable": SUCCESS,
    "positivo": SUCCESS,
    "bajo control": SUCCESS,
    "warning": WARNING,
    "advertencia": WARNING,
    "atencion": WARNING,
    "atención": WARNING,
    "danger": DANGER,
    "critico": DANGER,
    "crítico": DANGER,
    "negativo": DANGER,
    "excedido": DANGER_STRONG,
    "danger_strong": DANGER_STRONG,
    "info": INFO,
    "informativo": INFO,
    "neutral": NEUTRAL,
    "sin datos": NEUTRAL,
    "sin deuda": SUCCESS,
}

CONTINUOUS_SCALE_VIRIDIS = [
    "#440154",
    "#482878",
    "#3e4989",
    "#31688e",
    "#26828e",
    "#1f9e89",
    "#35b779",
    "#6ece58",
    "#b5de2b",
    "#fde725",
]

CATEGORY_PALETTE = {
    "vivienda": "#2563eb",
    "arriendo": "#2563eb",
    "alimentacion": "#16a34a",
    "alimentación": "#16a34a",
    "comida": "#16a34a",
    "supermercado": "#16a34a",
    "transporte": "#f97316",
    "salud": "#ef4444",
    "deudas": "#7c3aed",
    "deuda": "#7c3aed",
    "tarjeta demo": "#7c3aed",
    "tarjeta de crédito": "#7c3aed",
    "ocio": "#db2777",
    "educacion": "#0ea5e9",
    "educación": "#0ea5e9",
    "servicios": "#b7791f",
    "ahorro": "#166534",
    "inversion": "#0f766e",
    "inversión": "#0f766e",
    "mascota": "#92400e",
    "mascotas": "#92400e",
    "otros": NEUTRAL,
    "otros gastos": NEUTRAL,
}

HASH_PALETTE = [
    "#2563eb",
    "#16a34a",
    "#f97316",
    "#ef4444",
    "#7c3aed",
    "#db2777",
    "#0ea5e9",
    "#b7791f",
    "#166534",
    "#0f766e",
    "#92400e",
    "#64748b",
]


def get_semantic_color(status: str) -> str:
    """Devuelve color semantico para un estado conocido."""
    key = _normalize_key(status)
    return SEMANTIC_COLORS.get(key, NEUTRAL)


def get_category_color(category: str) -> str:
    """Devuelve color estable para una categoria financiera."""
    key = _normalize_key(category)
    if key in CATEGORY_PALETTE:
        return CATEGORY_PALETTE[key]
    if not key:
        return CATEGORY_PALETTE["otros"]
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
    index = int(digest[:8], 16) % len(HASH_PALETTE)
    return HASH_PALETTE[index]


def get_budget_usage_color(usage_percent: float) -> str:
    """Devuelve color de riesgo para uso presupuestario."""
    usage = _safe_float(usage_percent)
    if usage > 100:
        return DANGER_STRONG
    if usage > 90:
        return DANGER
    if usage >= 70:
        return WARNING
    return SUCCESS


def get_flow_color(amount: float) -> str:
    """Devuelve color para flujo libre."""
    value = _safe_float(amount)
    if value > 0:
        return SUCCESS
    if value < 0:
        return DANGER
    return WARNING


def get_debt_status_color(status: str) -> str:
    """Devuelve color semantico para estado de deuda."""
    key = _normalize_key(status)
    mapping = {
        "bajando": SUCCESS,
        "pagada": SUCCESS,
        "sin avance": WARNING,
        "crítica": DANGER,
        "critica": DANGER,
        "inactiva": NEUTRAL,
    }
    return mapping.get(key, get_semantic_color(key))


def get_viridis_color(
    value: float,
    min_value: float,
    max_value: float,
) -> str:
    """Devuelve color Viridis para un valor continuo."""
    current = _safe_float(value)
    minimum = _safe_float(min_value)
    maximum = _safe_float(max_value)
    if maximum == minimum:
        return CONTINUOUS_SCALE_VIRIDIS[len(CONTINUOUS_SCALE_VIRIDIS) // 2]
    ratio = (current - minimum) / (maximum - minimum)
    ratio = max(0.0, min(1.0, ratio))
    index = round(ratio * (len(CONTINUOUS_SCALE_VIRIDIS) - 1))
    return CONTINUOUS_SCALE_VIRIDIS[index]


def is_hex_color(value: str) -> bool:
    """Indica si el texto es un color HEX valido."""
    return bool(re.fullmatch(r"#[0-9a-fA-F]{6}", value))


def _safe_float(value: float) -> float:
    """Convierte un valor a float sin propagar errores."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _normalize_key(value: str) -> str:
    """Normaliza claves de colores para busqueda estable."""
    return str(value or "").strip().casefold()
