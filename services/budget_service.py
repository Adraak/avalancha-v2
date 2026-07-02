"""Servicio de aplicacion para presupuestos V2."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from uuid import uuid4

from avalancha.models import CategoryBudget, EXPENSE
from avalancha.storage import BudgetRepository

from core.models.presupuesto import Presupuesto
from services.category_service import CategoryService
from services.movement_service import MovementService


@dataclass(frozen=True, slots=True)
class EjecucionPresupuesto:
    """Resultado de ejecucion de un presupuesto."""

    presupuesto_id: str
    monto_presupuestado: int
    monto_gastado: int
    saldo_disponible: int
    porcentaje_utilizado: float
    estado_visual: str


class BudgetService:
    """Administra presupuestos y calcula ejecucion desde movimientos."""

    def __init__(
        self,
        data_dir: str | Path = "data",
        year: int | None = None,
        month: int | None = None,
        repository: BudgetRepository | None = None,
        movement_service: MovementService | None = None,
        category_service: CategoryService | None = None,
    ) -> None:
        """Inicializa el servicio para un mes presupuestario."""
        today = date.today()
        self.year = year or today.year
        self.month = month or today.month
        self.repository = repository or BudgetRepository(data_dir)
        self.category_service = category_service or CategoryService(
            data_dir=self.repository.data_dir,
            repository=self.repository,
        )
        self.movement_service = movement_service or MovementService(
            data_dir=data_dir,
            year=self.year,
            month=self.month,
            repository=self.repository,
            category_service=self.category_service,
        )

    def obtener_presupuestos(self) -> list[Presupuesto]:
        """Devuelve los presupuestos del mes."""
        budget = self._load_budget()
        return [
            self._desde_categoria(item)
            for item in sorted(
                budget.categories,
                key=lambda current: current.name.casefold(),
            )
            if item.transaction_type == EXPENSE
        ]

    def obtener_presupuesto_por_id(self, presupuesto_id: str) -> Presupuesto:
        """Busca un presupuesto por identificador estable."""
        category = self._find_category(presupuesto_id)
        return self._desde_categoria(category)

    def crear_presupuesto(self, datos: dict[str, object]) -> Presupuesto:
        """Crea un presupuesto y lo persiste."""
        presupuesto = self._crear_modelo(datos, uuid4().hex)
        self._validar_presupuesto(presupuesto)
        budget = self._load_budget()
        budget.categories.append(self._a_categoria_con_clase(presupuesto))
        self.repository.save(budget)
        return presupuesto

    def editar_presupuesto(
        self,
        presupuesto_id: str,
        datos: dict[str, object],
    ) -> Presupuesto:
        """Edita un presupuesto existente."""
        budget = self._load_budget()
        index = self._find_category_index(budget.categories, presupuesto_id)
        presupuesto = self._crear_modelo(datos, presupuesto_id)
        original = self._desde_categoria(budget.categories[index])
        self._validar_presupuesto(
            presupuesto,
            presupuesto_id,
            categoria_original=original.categoria,
        )
        budget.categories[index] = self._a_categoria_con_clase(presupuesto)
        self.repository.save(budget)
        return presupuesto

    def eliminar_presupuesto(self, presupuesto_id: str) -> None:
        """Elimina un presupuesto por identificador."""
        budget = self._load_budget()
        index = self._find_category_index(budget.categories, presupuesto_id)
        budget.categories.pop(index)
        self.repository.save(budget)

    def activar_presupuesto(self, presupuesto_id: str) -> Presupuesto:
        """Marca un presupuesto como activo."""
        return self._set_active(presupuesto_id, True)

    def desactivar_presupuesto(self, presupuesto_id: str) -> Presupuesto:
        """Marca un presupuesto como inactivo."""
        return self._set_active(presupuesto_id, False)

    def calcular_ejecucion(
        self,
        presupuesto_id: str,
    ) -> EjecucionPresupuesto:
        """Calcula ejecucion de un presupuesto desde movimientos reales."""
        presupuesto = self.obtener_presupuesto_por_id(presupuesto_id)
        movimientos = self.movement_service.obtener_movimientos()
        gastado = sum(
            item.monto
            for item in movimientos
            if (
                item.tipo == "gasto"
                and item.categoria == presupuesto.categoria
                and self._fecha_en_periodo(
                    item.fecha,
                    presupuesto.fecha_inicio,
                    presupuesto.fecha_termino,
                )
            )
        )
        disponible = presupuesto.monto_mensual - gastado
        porcentaje = (
            round((gastado / presupuesto.monto_mensual) * 100, 1)
            if presupuesto.monto_mensual
            else 0.0
        )
        return EjecucionPresupuesto(
            presupuesto_id=presupuesto.id,
            monto_presupuestado=presupuesto.monto_mensual,
            monto_gastado=gastado,
            saldo_disponible=disponible,
            porcentaje_utilizado=porcentaje,
            estado_visual=self._estado_visual(porcentaje),
        )

    def calcular_ejecucion_general(self) -> list[dict[str, object]]:
        """Calcula ejecucion de todos los presupuestos visibles."""
        filas = []
        for presupuesto in self.obtener_presupuestos():
            ejecucion = self.calcular_ejecucion(presupuesto.id)
            filas.append(
                {
                    "presupuesto": presupuesto,
                    "ejecucion": ejecucion,
                }
            )
        return filas

    def categorias_disponibles(
        self,
        incluir_categoria: str | None = None,
    ) -> list[str]:
        """Devuelve categorias disponibles para sugerir en formularios."""
        return self.category_service.nombres_por_tipo(
            EXPENSE,
            incluir_nombre=incluir_categoria,
        )

    def _set_active(
        self,
        presupuesto_id: str,
        active: bool,
    ) -> Presupuesto:
        """Actualiza estado activo/inactivo de un presupuesto."""
        budget = self._load_budget()
        index = self._find_category_index(budget.categories, presupuesto_id)
        category = budget.categories[index]
        category.active = active
        budget.categories[index] = category
        self.repository.save(budget)
        return self._desde_categoria(category)

    def _validar_presupuesto(
        self,
        presupuesto: Presupuesto,
        presupuesto_id: str | None = None,
        categoria_original: str | None = None,
    ) -> None:
        """Valida reglas de negocio del presupuesto."""
        if not presupuesto.nombre:
            raise ValueError("El nombre del presupuesto es obligatorio.")
        if not presupuesto.categoria:
            raise ValueError("La categoria es obligatoria.")
        if presupuesto.monto_mensual <= 0:
            raise ValueError("El monto mensual debe ser mayor que cero.")
        if not presupuesto.moneda:
            raise ValueError("La moneda es obligatoria.")
        permitir_inactiva = (
            categoria_original is not None
            and presupuesto.categoria.casefold() == categoria_original.casefold()
        )
        self.category_service.validar_categoria_presupuesto(
            presupuesto.categoria,
            permitir_inactiva=permitir_inactiva,
        )
        self._validar_conflictos(presupuesto, presupuesto_id)

    def _validar_conflictos(
        self,
        presupuesto: Presupuesto,
        presupuesto_id: str | None,
    ) -> None:
        """Evita duplicados activos por categoria y periodo."""
        if not presupuesto.activo:
            return
        for current in self.obtener_presupuestos():
            if current.id == presupuesto_id or not current.activo:
                continue
            if current.categoria.casefold() != presupuesto.categoria.casefold():
                continue
            if self._periodos_solapados(
                presupuesto.fecha_inicio,
                presupuesto.fecha_termino,
                current.fecha_inicio,
                current.fecha_termino,
            ):
                raise ValueError(
                    "Ya existe un presupuesto activo para esa categoria "
                    "en el periodo indicado."
                )

    def _load_budget(self):
        """Carga el presupuesto mensual y persiste IDs faltantes."""
        budget = self.repository.load(self.year, self.month)
        if self._ensure_category_ids():
            budget = self.repository.load(self.year, self.month)
        return budget

    def _ensure_category_ids(self) -> bool:
        """Persiste IDs en categorias antiguas cuando faltan."""
        path = self.repository.budget_path(self.year, self.month)
        if not path.exists():
            return False
        with path.open("r", encoding="utf-8") as file:
            data = json.load(file)
        changed = False
        for item in data.get("categories", []):
            if not item.get("budget_id"):
                item["budget_id"] = uuid4().hex
                changed = True
        if changed:
            with path.open("w", encoding="utf-8") as file:
                json.dump(
                    data,
                    file,
                    ensure_ascii=False,
                    indent=2,
                    sort_keys=True,
                )
                file.write("\n")
        return changed

    def _find_category(self, presupuesto_id: str) -> CategoryBudget:
        """Obtiene la categoria asociada a un presupuesto."""
        budget = self._load_budget()
        index = self._find_category_index(budget.categories, presupuesto_id)
        return budget.categories[index]

    @staticmethod
    def _find_category_index(
        categories: list[CategoryBudget],
        presupuesto_id: str,
    ) -> int:
        """Obtiene el indice de una categoria por ID."""
        for index, category in enumerate(categories):
            if category.budget_id == presupuesto_id:
                return index
        raise ValueError("El presupuesto no existe.")

    def _crear_modelo(
        self,
        datos: dict[str, object],
        presupuesto_id: str,
    ) -> Presupuesto:
        """Crea un modelo de dominio desde datos de entrada."""
        start = self._normalizar_fecha(
            datos.get("fecha_inicio"),
            date(self.year, self.month, 1),
        )
        end = self._normalizar_fecha(datos.get("fecha_termino"), None)
        moneda = str(datos.get("moneda", "CLP")).strip().upper()
        if not moneda:
            raise ValueError("La moneda es obligatoria.")
        return Presupuesto(
            id=presupuesto_id,
            nombre=str(datos.get("nombre", "")).strip(),
            categoria=str(datos.get("categoria", "")).strip(),
            monto_mensual=self._normalizar_monto(datos.get("monto_mensual")),
            moneda=moneda,
            fecha_inicio=start,
            fecha_termino=end,
            activo=bool(datos.get("activo", True)),
            observaciones=str(datos.get("observaciones", "")).strip(),
            mes=f"{self.year:04d}-{self.month:02d}",
        )

    @staticmethod
    def _desde_categoria(category: CategoryBudget) -> Presupuesto:
        """Convierte una categoria persistida en presupuesto V2."""
        return Presupuesto(
            id=category.budget_id,
            nombre=category.name,
            categoria=category.name,
            monto_mensual=category.budgeted_amount,
            moneda=category.currency,
            fecha_inicio=date.fromisoformat(category.start_date),
            fecha_termino=(
                date.fromisoformat(category.end_date)
                if category.end_date
                else None
            ),
            activo=category.active,
            observaciones=category.notes,
        )

    def _a_categoria_con_clase(self, presupuesto: Presupuesto) -> CategoryBudget:
        """Convierte presupuesto y aplica clase formal fija/variable."""
        category = self._a_categoria(presupuesto)
        category.is_fixed = (
            self.category_service.es_categoria_fija(presupuesto.categoria)
            is True
        )
        return category

    @staticmethod
    def _a_categoria(presupuesto: Presupuesto) -> CategoryBudget:
        """Convierte un presupuesto V2 a categoria persistible."""
        return CategoryBudget(
            name=presupuesto.categoria,
            transaction_type=EXPENSE,
            budgeted_amount=presupuesto.monto_mensual,
            is_fixed=False,
            alert_threshold=80,
            budget_id=presupuesto.id,
            currency=presupuesto.moneda,
            start_date=(
                presupuesto.fecha_inicio or date.today()
            ).isoformat(),
            end_date=(
                presupuesto.fecha_termino.isoformat()
                if presupuesto.fecha_termino
                else None
            ),
            active=presupuesto.activo,
            notes=presupuesto.observaciones,
        )

    @staticmethod
    def _normalizar_fecha(
        value: object,
        default: date | None,
    ) -> date | None:
        """Normaliza fecha desde date, ISO o dd-mm-aaaa."""
        if value in ("", None):
            return default
        if isinstance(value, date):
            return value
        text = str(value).strip()
        for fmt in ("%Y-%m-%d", "%d-%m-%Y"):
            try:
                return datetime.strptime(text, fmt).date()
            except ValueError:
                continue
        raise ValueError("La fecha no es valida.")

    @staticmethod
    def _normalizar_monto(value: object) -> int:
        """Normaliza un monto CLP a entero positivo."""
        try:
            amount = int(str(value).replace(".", "").replace(",", "").strip())
        except (TypeError, ValueError) as exc:
            raise ValueError("El monto mensual debe ser numerico.") from exc
        if amount <= 0:
            raise ValueError("El monto mensual debe ser mayor que cero.")
        return amount

    @staticmethod
    def _fecha_en_periodo(
        value: date,
        start: date | None,
        end: date | None,
    ) -> bool:
        """Indica si una fecha pertenece al periodo del presupuesto."""
        if start and value < start:
            return False
        if end and value > end:
            return False
        return True

    @staticmethod
    def _periodos_solapados(
        start_a: date | None,
        end_a: date | None,
        start_b: date | None,
        end_b: date | None,
    ) -> bool:
        """Indica si dos rangos de fechas se cruzan."""
        min_date = date.min
        max_date = date.max
        a_start = start_a or min_date
        a_end = end_a or max_date
        b_start = start_b or min_date
        b_end = end_b or max_date
        return a_start <= b_end and b_start <= a_end

    @staticmethod
    def _estado_visual(porcentaje: float) -> str:
        """Calcula semaforo visual segun porcentaje usado."""
        if porcentaje < 70:
            return "verde"
        if porcentaje <= 90:
            return "amarillo"
        return "rojo"
