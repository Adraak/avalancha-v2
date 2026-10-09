"""Servicio de aplicacion para categorias financieras."""

from __future__ import annotations

import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from avalancha.models import EXPENSE, INCOME
from avalancha.storage import BudgetRepository
from core.versioned_json_store import VersionedJsonStore
from core.models.categoria import (
    CLASES_CATEGORIA,
    TIPOS_CATEGORIA,
    Categoria,
)

from services.error_reporting_service import UserFacingError

class CategoryService:
    """Administra categorias por perfil sin depender de interfaz grafica."""

    CATEGORIAS_FIJAS_INICIALES = {
        "arriendo",
        "chatgpt",
        "chat gpt",
        "spotify",
        "internet",
        "servicios",
        "fondo solidario",
        "tarjeta de credito",
        "tarjeta demo",
        "tarjeta de credito demo",
        "dante",
    }

    CATEGORIAS_BASE = (
        ("Arriendo", EXPENSE, "fija"),
        ("Internet", EXPENSE, "fija"),
        ("Servicios", EXPENSE, "fija"),
        ("ChatGPT", EXPENSE, "fija"),
        ("Spotify", EXPENSE, "fija"),
        ("Fondo solidario", EXPENSE, "fija"),
        ("Pago tarjeta de credito", EXPENSE, "fija"),
        ("Alimentacion", EXPENSE, "variable"),
        ("Comida", EXPENSE, "variable"),
        ("Supermercado", EXPENSE, "variable"),
        ("Transporte", EXPENSE, "variable"),
        ("Ocio", EXPENSE, "variable"),
        ("Salud", EXPENSE, "variable"),
        ("Mascota", EXPENSE, "variable"),
        ("Electronica", EXPENSE, "variable"),
        ("Ropa", EXPENSE, "variable"),
        ("Otros gastos", EXPENSE, "variable"),
        ("Sueldo", INCOME, "fija"),
        ("Ingreso extra", INCOME, "variable"),
        ("Reembolso", INCOME, "variable"),
        ("Venta", INCOME, "variable"),
    )

    def __init__(
        self,
        data_dir: str | Path = "data",
        repository: BudgetRepository | None = None,
    ) -> None:
        """Inicializa el servicio con la carpeta de datos del perfil."""
        self.repository = repository or BudgetRepository(data_dir)
        self.data_dir = self.repository.data_dir
        self.categories_path = self.data_dir / "categorias.json"
        self._json_store = VersionedJsonStore()

    def listar_categorias(self) -> list[Categoria]:
        """Devuelve todas las categorias conocidas del perfil."""
        categorias = self._load()
        return sorted(categorias, key=lambda item: item.nombre.casefold())

    def listar_activas(self) -> list[Categoria]:
        """Devuelve solo categorias activas."""
        return [item for item in self.listar_categorias() if item.activa]

    def listar_por_tipo(
        self,
        tipo: str,
        incluir_inactivas: bool = False,
        incluir_nombre: str | None = None,
    ) -> list[Categoria]:
        """Devuelve categorias compatibles con ingreso o gasto."""
        tipo_normalizado = self._normalizar_tipo(tipo)
        nombre_extra = self._normalizar_nombre(incluir_nombre or "")
        categorias = []
        for categoria in self.listar_categorias():
            if not categoria.admite_tipo(tipo_normalizado):
                continue
            if categoria.activa or incluir_inactivas:
                categorias.append(categoria)
                continue
            if (
                nombre_extra
                and self._normalizar_nombre(categoria.nombre) == nombre_extra
            ):
                categorias.append(categoria)
        return categorias

    def nombres_por_tipo(
        self,
        tipo: str,
        incluir_inactivas: bool = False,
        incluir_nombre: str | None = None,
    ) -> list[str]:
        """Devuelve nombres compatibles para formularios."""
        return [
            item.nombre
            for item in self.listar_por_tipo(
                tipo,
                incluir_inactivas=incluir_inactivas,
                incluir_nombre=incluir_nombre,
            )
        ]

    def obtener_categoria(self, categoria_id: str) -> Categoria:
        """Busca una categoria por identificador estable."""
        for categoria in self.listar_categorias():
            if categoria.id == categoria_id:
                return categoria
        raise UserFacingError("La categoria no existe.")

    def obtener_por_nombre(
        self,
        nombre: str,
        tipo: str | None = None,
    ) -> Categoria | None:
        """Busca una categoria por nombre visible y tipo compatible."""
        nombre_normalizado = self._normalizar_nombre(nombre)
        tipo_normalizado = self._normalizar_tipo(tipo) if tipo else None
        for categoria in self.listar_categorias():
            if self._normalizar_nombre(categoria.nombre) != nombre_normalizado:
                continue
            if tipo_normalizado and not categoria.admite_tipo(tipo_normalizado):
                continue
            return categoria
        return None

    def crear_categoria(
        self,
        nombre: str,
        tipo: str,
        clase: str,
        color_key: str | None = None,
    ) -> Categoria:
        """Crea una categoria activa con ID estable."""
        categoria = Categoria(
            id=self._nuevo_id(nombre),
            nombre=nombre,
            tipo=tipo,
            clase=clase,
            activa=True,
            color_key=color_key,
            created_at=self._ahora(),
            updated_at=self._ahora(),
        )
        self._validar_categoria(categoria)
        categorias = self._load()
        categorias.append(categoria)
        self._save(categorias)
        return categoria

    def editar_categoria(
        self,
        categoria_id: str,
        nombre: str | None = None,
        tipo: str | None = None,
        clase: str | None = None,
        color_key: str | None = None,
        activa: bool | None = None,
    ) -> Categoria:
        """Edita una categoria existente sin cambiar su ID."""
        categorias = self._load()
        index = self._index_por_id(categorias, categoria_id)
        actual = categorias[index]
        editada = Categoria(
            id=actual.id,
            nombre=actual.nombre if nombre is None else nombre,
            tipo=actual.tipo if tipo is None else tipo,
            clase=actual.clase if clase is None else clase,
            activa=actual.activa if activa is None else activa,
            color_key=actual.color_key if color_key is None else color_key,
            created_at=actual.created_at,
            updated_at=self._ahora(),
        )
        self._validar_categoria(editada, categoria_id)
        categorias[index] = editada
        self._save(categorias)
        return editada

    def desactivar_categoria(self, categoria_id: str) -> Categoria:
        """Desactiva una categoria sin perder historial."""
        return self.editar_categoria(categoria_id, activa=False)

    def activar_categoria(self, categoria_id: str) -> Categoria:
        """Reactiva una categoria desactivada."""
        return self.editar_categoria(categoria_id, activa=True)

    def puede_eliminar_categoria(self, categoria_id: str) -> bool:
        """Indica si una categoria no tiene datos asociados."""
        categoria = self.obtener_categoria(categoria_id)
        return not self._tiene_asociaciones(categoria.nombre)

    def clase_por_nombre(self, nombre: str) -> str | None:
        """Devuelve clase formal de una categoria, si existe."""
        categoria = self.obtener_por_nombre(nombre)
        return categoria.clase if categoria else None

    def es_categoria_fija(self, nombre: str) -> bool | None:
        """Indica si una categoria formal es fija, o None si no existe."""
        clase = self.clase_por_nombre(nombre)
        if clase is None:
            return None
        return clase == "fija"

    def validar_categoria_movimiento(
        self,
        nombre: str,
        tipo: str,
        permitir_inactiva: bool = False,
    ) -> None:
        """Valida que una categoria pueda usarse en un movimiento."""
        categoria = self.obtener_por_nombre(nombre, tipo)
        if categoria is None:
            raise UserFacingError("La categoria seleccionada no existe.")
        if not categoria.activa and not permitir_inactiva:
            raise UserFacingError("La categoria seleccionada esta inactiva.")

    def validar_categoria_presupuesto(
        self,
        nombre: str,
        permitir_inactiva: bool = False,
    ) -> None:
        """Valida que una categoria pueda usarse en presupuestos."""
        categoria = self.obtener_por_nombre(nombre, EXPENSE)
        if categoria is None:
            raise UserFacingError("La categoria seleccionada no existe.")
        if not categoria.activa and not permitir_inactiva:
            raise UserFacingError("La categoria seleccionada esta inactiva.")

    def sincronizar_desde_datos(self) -> list[Categoria]:
        """Sincroniza categorias formales desde datos heredados."""
        categorias = self._load(sin_sincronizar=True)
        changed = self._agregar_base_si_falta(categorias)
        changed = self._agregar_desde_presupuestos(categorias) or changed
        if changed:
            self._save(categorias)
        return sorted(categorias, key=lambda item: item.nombre.casefold())

    def _load(self, sin_sincronizar: bool = False) -> list[Categoria]:
        """Carga categorias y asegura compatibilidad heredada."""
        if not self.categories_path.exists():
            categorias: list[Categoria] = []
            self._agregar_base_si_falta(categorias)
            self._agregar_desde_presupuestos(categorias)
            self._save(categorias)
            return categorias

        data = self._json_store.read(self.categories_path)
        raw_categories = data.get("categories", [])
        categorias = []
        if isinstance(raw_categories, list):
            for item in raw_categories:
                if isinstance(item, dict):
                    categorias.append(Categoria.from_dict(item))
        if not sin_sincronizar and self._agregar_desde_presupuestos(categorias):
            self._save(categorias)
        return categorias

    def _save(self, categorias: list[Categoria]) -> None:
        """Persiste categorias con formato estable."""
        self.categories_path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "categories": [
                item.to_dict()
                for item in sorted(
                    categorias,
                    key=lambda value: (value.tipo, value.nombre.casefold()),
                )
            ]
        }
        self._json_store.write(self.categories_path, data)

    def _validar_categoria(
        self,
        categoria: Categoria,
        categoria_id: str | None = None,
    ) -> None:
        """Aplica reglas de negocio de categorias."""
        if categoria.tipo not in TIPOS_CATEGORIA:
            raise UserFacingError("El tipo de categoria no es valido.")
        if categoria.clase not in CLASES_CATEGORIA:
            raise UserFacingError("La clase de categoria no es valida.")
        if not categoria.activa:
            return
        nombre = self._normalizar_nombre(categoria.nombre)
        for actual in self._load(sin_sincronizar=True):
            if actual.id == categoria_id or not actual.activa:
                continue
            if self._normalizar_nombre(actual.nombre) != nombre:
                continue
            if actual.tipo == categoria.tipo or "ambos" in {
                actual.tipo,
                categoria.tipo,
            }:
                raise UserFacingError(
                    "Ya existe una categoria activa con ese nombre y tipo."
                )

    def _agregar_base_si_falta(self, categorias: list[Categoria]) -> bool:
        """Agrega categorias base sin duplicar equivalentes."""
        changed = False
        for nombre, tipo, clase in self.CATEGORIAS_BASE:
            if self._existe_nombre_tipo(categorias, nombre, tipo):
                continue
            categorias.append(
                Categoria(
                    id=self._nuevo_id(nombre, categorias),
                    nombre=nombre,
                    tipo=tipo,
                    clase=clase,
                    activa=True,
                    created_at=self._ahora(),
                    updated_at=self._ahora(),
                )
            )
            changed = True
        return changed

    def _agregar_desde_presupuestos(
        self,
        categorias: list[Categoria],
    ) -> bool:
        """Agrega nombres detectados en presupuestos y movimientos."""
        changed = False
        for label in self.repository.list_months():
            try:
                year, month = (int(part) for part in label.split("-"))
                budget = self.repository.load(year, month)
            except (OSError, ValueError):
                continue
            fixed_names = {
                str(getattr(item, "category", "")).strip()
                for item in budget.recurring_items
                if str(getattr(item, "transaction_type", "")).lower() == EXPENSE
            }
            for item in budget.categories:
                nombre = str(getattr(item, "name", "")).strip()
                tipo = str(getattr(item, "transaction_type", EXPENSE)).lower()
                if not nombre or self._existe_nombre_tipo(categorias, nombre, tipo):
                    continue
                clase = self._inferir_clase(
                    nombre,
                    bool(getattr(item, "is_fixed", False)),
                    nombre in fixed_names,
                    tipo,
                )
                categorias.append(
                    Categoria(
                        id=self._nuevo_id(nombre, categorias),
                        nombre=nombre,
                        tipo=tipo if tipo in TIPOS_CATEGORIA else EXPENSE,
                        clase=clase,
                        activa=bool(getattr(item, "active", True)),
                        created_at=self._ahora(),
                        updated_at=self._ahora(),
                    )
                )
                changed = True
            for item in budget.transactions + budget.recurring_items:
                nombre = str(getattr(item, "category", "")).strip()
                tipo = str(getattr(item, "transaction_type", EXPENSE)).lower()
                if not nombre or self._existe_nombre_tipo(categorias, nombre, tipo):
                    continue
                categorias.append(
                    Categoria(
                        id=self._nuevo_id(nombre, categorias),
                        nombre=nombre,
                        tipo=tipo if tipo in TIPOS_CATEGORIA else EXPENSE,
                        clase=self._inferir_clase(
                            nombre,
                            False,
                            item in budget.recurring_items,
                            tipo,
                        ),
                        activa=True,
                        created_at=self._ahora(),
                        updated_at=self._ahora(),
                    )
                )
                changed = True
        return changed

    def _tiene_asociaciones(self, nombre: str) -> bool:
        """Busca uso historico de una categoria por nombre."""
        objetivo = self._normalizar_nombre(nombre)
        for label in self.repository.list_months():
            try:
                year, month = (int(part) for part in label.split("-"))
                budget = self.repository.load(year, month)
            except (OSError, ValueError):
                continue
            for item in budget.categories:
                if self._normalizar_nombre(getattr(item, "name", "")) == objetivo:
                    return True
            for item in budget.transactions + budget.recurring_items:
                if self._normalizar_nombre(getattr(item, "category", "")) == objetivo:
                    return True
        return False

    def _existe_nombre_tipo(
        self,
        categorias: list[Categoria],
        nombre: str,
        tipo: str,
    ) -> bool:
        """Indica si ya existe nombre compatible con tipo."""
        nombre_normalizado = self._normalizar_nombre(nombre)
        tipo_normalizado = self._normalizar_tipo(tipo)
        for categoria in categorias:
            if self._normalizar_nombre(categoria.nombre) != nombre_normalizado:
                continue
            if categoria.tipo == tipo_normalizado or "ambos" in {
                categoria.tipo,
                tipo_normalizado,
            }:
                return True
        return False

    def _nuevo_id(
        self,
        nombre: str,
        categorias: list[Categoria] | None = None,
    ) -> str:
        """Genera un ID estable y unico dentro del perfil."""
        existing = {
            item.id
            for item in (categorias if categorias is not None else self._load())
        }
        base = f"cat_{self._slugify(nombre)}" or f"cat_{uuid4().hex}"
        current = base
        sequence = 1
        while current in existing:
            sequence += 1
            current = f"{base}_{sequence:02d}"
        return current

    @staticmethod
    def _inferir_clase(
        nombre: str,
        is_fixed: bool,
        recurrente: bool,
        tipo: str,
    ) -> str:
        """Infiere clase para datos antiguos sin categoria formal."""
        if tipo == INCOME:
            return "fija"
        normalized = CategoryService._normalizar_nombre(nombre)
        if (
            is_fixed
            or recurrente
            or normalized in CategoryService.CATEGORIAS_FIJAS_INICIALES
        ):
            return "fija"
        return "variable"

    @staticmethod
    def _normalizar_tipo(tipo: str) -> str:
        """Normaliza y valida tipo de categoria."""
        tipo_normalizado = tipo.strip().lower()
        if tipo_normalizado not in TIPOS_CATEGORIA:
            raise UserFacingError("El tipo de categoria no es valido.")
        return tipo_normalizado

    @staticmethod
    def _normalizar_nombre(nombre: Any) -> str:
        """Normaliza nombres para comparar sin tildes ni mayusculas."""
        normalized = unicodedata.normalize("NFD", str(nombre).strip().casefold())
        return "".join(
            char
            for char in normalized
            if unicodedata.category(char) != "Mn"
        )

    @staticmethod
    def _slugify(nombre: str) -> str:
        """Convierte nombre visible en identificador legible."""
        normalized = CategoryService._normalizar_nombre(nombre)
        cleaned = [char if char.isalnum() else "_" for char in normalized]
        return "_".join(part for part in "".join(cleaned).split("_") if part)

    @staticmethod
    def _ahora() -> str:
        """Devuelve timestamp ISO sin microsegundos."""
        return datetime.now().replace(microsecond=0).isoformat()

    @staticmethod
    def _index_por_id(categorias: list[Categoria], categoria_id: str) -> int:
        """Devuelve indice de categoria o falla con mensaje claro."""
        for index, categoria in enumerate(categorias):
            if categoria.id == categoria_id:
                return index
        raise UserFacingError("La categoria no existe.")
