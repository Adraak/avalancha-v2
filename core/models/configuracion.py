"""Modelo puro de configuracion de Avalancha V2."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class ConfiguracionAplicacion:
    """Representa opciones locales editables sin depender de interfaz."""

    carpeta_reportes: Path
    moneda_principal: str = "CLP"
    apariencia: str = "claro"
    cifrado_reportes: bool = True
    carpeta_respaldo: Path | None = None
    sincronizacion_habilitada: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Convierte la configuracion a datos serializables."""
        return {
            "carpeta_reportes": str(self.carpeta_reportes),
            "moneda_principal": self.moneda_principal,
            "apariencia": self.apariencia,
            "cifrado_reportes": self.cifrado_reportes,
            "carpeta_respaldo": (
                str(self.carpeta_respaldo)
                if self.carpeta_respaldo is not None
                else ""
            ),
            "sincronizacion_habilitada": self.sincronizacion_habilitada,
        }

    @classmethod
    def from_dict(
        cls,
        data: dict[str, Any],
        carpeta_reportes_defecto: Path,
        carpeta_respaldo_defecto: Path,
    ) -> "ConfiguracionAplicacion":
        """Construye configuracion desde JSON tolerando campos faltantes."""
        carpeta_reportes = Path(
            str(data.get("carpeta_reportes") or carpeta_reportes_defecto),
        )
        carpeta_respaldo = Path(
            str(data.get("carpeta_respaldo") or carpeta_respaldo_defecto),
        )
        return cls(
            carpeta_reportes=carpeta_reportes,
            moneda_principal=str(data.get("moneda_principal") or "CLP"),
            apariencia=str(data.get("apariencia") or "claro"),
            cifrado_reportes=bool(data.get("cifrado_reportes", True)),
            carpeta_respaldo=carpeta_respaldo,
            sincronizacion_habilitada=bool(
                data.get("sincronizacion_habilitada", False),
            ),
        )
