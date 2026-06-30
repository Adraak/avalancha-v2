"""Modelo base para perfiles financieros locales."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class PerfilFinanciero:
    """Representa un perfil local con datos financieros separados."""

    id: str
    nombre: str
    ruta_datos: Path
    activo: bool = True

    def __post_init__(self) -> None:
        """Normaliza y valida la definicion del perfil."""
        self.nombre = self.nombre.strip()
        self.ruta_datos = Path(self.ruta_datos)

        if not self.nombre:
            raise ValueError("El nombre del perfil es obligatorio.")
        if not str(self.ruta_datos):
            raise ValueError("La ruta de datos del perfil es obligatoria.")

