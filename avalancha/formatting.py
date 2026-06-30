"""Formatting helpers for the Avalancha UI."""

from __future__ import annotations

from datetime import date, datetime


def format_clp(amount: int | float) -> str:
    """Format an amount in Chilean pesos."""
    value = int(round(amount))
    sign = "-" if value < 0 else ""
    value = abs(value)
    return f"{sign}$ {value:,}".replace(",", ".")


def parse_clp(text: str) -> int:
    """Parse CLP text from user input."""
    cleaned = (
        text.replace("$", "")
        .replace(".", "")
        .replace(",", "")
        .replace(" ", "")
        .strip()
    )
    if not cleaned:
        return 0
    try:
        return int(cleaned)
    except ValueError as exc:
        raise ValueError("El monto debe ser un numero valido.") from exc


def parse_optional_clp(text: str) -> int | None:
    """Parse an optional CLP value, returning None when blank."""
    if not str(text).strip():
        return None
    return parse_clp(text)


def format_clp_input(text: str, allow_negative: bool = False) -> str:
    """Format an editable CLP value using dot thousands separators."""
    raw = str(text).strip()
    negative = allow_negative and raw.startswith("-")
    digits = "".join(character for character in raw if character.isdigit())
    if not digits:
        return "-" if negative else ""
    value = int(digits)
    formatted = f"{value:,}".replace(",", ".")
    return f"-{formatted}" if negative else formatted


def format_date_for_display(iso_date: str) -> str:
    """Convert YYYY-MM-DD to DD-MM-YYYY for the UI."""
    return date.fromisoformat(iso_date).strftime("%d-%m-%Y")


def parse_display_date(text: str) -> str:
    """Convert DD-MM-YYYY UI input to YYYY-MM-DD for storage."""
    cleaned = text.strip()
    try:
        return datetime.strptime(cleaned, "%d-%m-%Y").date().isoformat()
    except ValueError as exc:
        raise ValueError("La fecha debe usar formato DD-MM-YYYY.") from exc
