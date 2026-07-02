"""Modelo base para categorias financieras."""

from __future__ import annotations

from dataclasses import dataclass


TIPOS_CATEGORIA = {"ingreso", "gasto", "ambos"}
CLASES_CATEGORIA = {"fija", "variable"}


@dataclass(slots=True)
class Categoria:
    """Representa una categoria financiera administrable por perfil."""

    id: str
    nombre: str
    tipo: str
    clase: str
    activa: bool = True
    color_key: str | None = None
    created_at: str = ""
    updated_at: str = ""

    def __post_init__(self) -> None:
        """Normaliza y valida los campos basicos de la categoria."""
        self.id = self.id.strip()
        self.nombre = self.nombre.strip()
        self.tipo = self.tipo.strip().lower()
        self.clase = self.clase.strip().lower()
        if self.color_key is not None:
            self.color_key = self.color_key.strip() or None
        self.created_at = self.created_at.strip()
        self.updated_at = self.updated_at.strip()

        if not self.id:
            raise ValueError("La categoria necesita un identificador.")
        if not self.nombre:
            raise ValueError("El nombre de la categoria es obligatorio.")
        if self.tipo not in TIPOS_CATEGORIA:
            raise ValueError("El tipo de categoria no es valido.")
        if self.clase not in CLASES_CATEGORIA:
            raise ValueError("La clase de categoria no es valida.")

    def admite_tipo(self, tipo: str) -> bool:
        """Indica si la categoria sirve para el tipo solicitado."""
        tipo_normalizado = tipo.strip().lower()
        return self.tipo == "ambos" or self.tipo == tipo_normalizado

    def to_dict(self) -> dict[str, object]:
        """Convierte la categoria a datos persistibles."""
        return {
            "id": self.id,
            "nombre": self.nombre,
            "tipo": self.tipo,
            "clase": self.clase,
            "activa": self.activa,
            "color_key": self.color_key,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> "Categoria":
        """Crea una categoria desde datos JSON tolerantes."""
        return cls(
            id=str(data.get("id", "")).strip(),
            nombre=str(data.get("nombre", "")).strip(),
            tipo=str(data.get("tipo", "")).strip(),
            clase=str(data.get("clase", "")).strip(),
            activa=bool(data.get("activa", True)),
            color_key=(
                str(data.get("color_key", "")).strip()
                if data.get("color_key") is not None
                else None
            ),
            created_at=str(data.get("created_at", "")).strip(),
            updated_at=str(data.get("updated_at", "")).strip(),
        )
