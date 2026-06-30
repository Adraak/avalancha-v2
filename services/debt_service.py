"""Servicio CRUD de deudas para Avalancha V2."""

from __future__ import annotations

from pathlib import Path

from avalancha.models import DEBT_CATEGORIES, Debt, new_id, today_iso
from avalancha.storage import BudgetRepository


class DebtService:
    """Administra deudas sin depender de interfaz grafica."""

    CATEGORIAS = {
        "tarjeta_credito": "Tarjeta de crédito",
        "credito_consumo": "Crédito de consumo",
        "deuda_familiar": "Deuda familiar",
        "credito_tercero": "Crédito de tercero",
        "otra": "Otra",
    }

    def __init__(
        self,
        data_dir: str | Path = "data",
        repository: BudgetRepository | None = None,
    ) -> None:
        """Inicializa el servicio con el repositorio del perfil."""
        self.repository = repository or BudgetRepository(data_dir)

    def obtener_deudas(self) -> list[Debt]:
        """Devuelve todas las deudas ordenadas por nombre."""
        return sorted(
            self.repository.load_debts(),
            key=lambda debt: debt.name.casefold(),
        )

    def obtener_deudas_activas(self) -> list[Debt]:
        """Devuelve solo deudas activas."""
        return [debt for debt in self.obtener_deudas() if debt.active]

    def obtener_deuda_por_id(self, debt_id: str) -> Debt:
        """Busca una deuda por identificador estable."""
        for debt in self.repository.load_debts():
            if debt.debt_id == debt_id:
                return debt
        raise ValueError("La deuda no existe.")

    def crear_deuda(self, datos: dict[str, object]) -> Debt:
        """Crea y persiste una deuda."""
        debt = self._crear_modelo(datos)
        self._validar_deuda(debt)
        debts = self.repository.load_debts()
        self._validar_nombre_duplicado(debt.name, debts)
        debts.append(debt)
        self.repository.save_debts(debts)
        return debt

    def editar_deuda(
        self,
        debt_id: str,
        datos: dict[str, object],
    ) -> Debt:
        """Edita una deuda existente."""
        debts = self.repository.load_debts()
        index = self._buscar_indice(debts, debt_id)
        current = debts[index]
        debt = self._crear_modelo(datos, debt_id, current)
        self._validar_deuda(debt)
        self._validar_nombre_duplicado(debt.name, debts, debt_id)
        debts[index] = debt
        self.repository.save_debts(debts)
        return debt

    def eliminar_deuda(self, debt_id: str) -> None:
        """Elimina una deuda si no tiene movimientos asociados."""
        if self._deuda_tiene_movimientos(debt_id):
            raise ValueError(
                "No se puede eliminar una deuda con movimientos asociados. "
                "Puedes desactivarla."
            )
        debts = self.repository.load_debts()
        index = self._buscar_indice(debts, debt_id)
        debts.pop(index)
        self.repository.save_debts(debts)

    def activar_deuda(self, debt_id: str) -> Debt:
        """Marca una deuda como activa."""
        return self._cambiar_estado(debt_id, True)

    def desactivar_deuda(self, debt_id: str) -> Debt:
        """Marca una deuda como inactiva."""
        return self._cambiar_estado(debt_id, False)

    def categorias_disponibles(self) -> list[tuple[str, str]]:
        """Devuelve categorias disponibles para la interfaz."""
        return [
            (key, label)
            for key, label in self.CATEGORIAS.items()
            if key in DEBT_CATEGORIES
        ]

    @staticmethod
    def calcular_disminucion_mensual(debt: Debt) -> int:
        """Calcula cuanto bajo la deuda frente al mes anterior."""
        return debt.previous_month_balance - debt.current_balance

    @staticmethod
    def calcular_interes_estimado(debt: Debt) -> int:
        """Estima el interés mensual de una deuda."""
        if debt.monthly_interest_rate in (None, 0):
            return 0
        return round(debt.current_balance * (debt.monthly_interest_rate / 100))

    def estado_visual(self, debt: Debt) -> str:
        """Clasifica el avance visual de una deuda."""
        if not debt.active:
            return "Inactiva"
        if debt.current_balance <= 0:
            return "Pagada"
        if (
            debt.current_monthly_payment
            <= self.calcular_interes_estimado(debt)
        ):
            return "Crítica"
        if self.calcular_disminucion_mensual(debt) > 0:
            return "Bajando"
        return "Sin avance"

    def _cambiar_estado(self, debt_id: str, active: bool) -> Debt:
        """Actualiza el estado activo/inactivo de una deuda."""
        debts = self.repository.load_debts()
        index = self._buscar_indice(debts, debt_id)
        debt = debts[index]
        debt.active = active
        debts[index] = debt
        self.repository.save_debts(debts)
        return debt

    def _crear_modelo(
        self,
        datos: dict[str, object],
        debt_id: str | None = None,
        actual: Debt | None = None,
    ) -> Debt:
        """Construye una deuda desde datos crudos."""
        category = self._normalizar_categoria(
            datos.get("category", datos.get("categoria", "otra")),
        )
        return Debt(
            debt_id=debt_id or str(datos.get("debt_id", "")).strip()
            or new_id(),
            name=str(datos.get("name", datos.get("nombre", ""))).strip(),
            category=category,
            current_balance=self._normalizar_monto(
                datos.get("current_balance", 0),
                "El saldo actual debe ser numerico.",
            ),
            previous_month_balance=self._normalizar_monto(
                datos.get(
                    "previous_month_balance",
                    actual.previous_month_balance if actual else 0,
                ),
                "El saldo del mes anterior debe ser numerico.",
            ),
            current_monthly_payment=self._normalizar_monto(
                datos.get("current_monthly_payment", 0),
                "El pago mensual debe ser numerico.",
            ),
            minimum_payment=self._normalizar_monto(
                datos.get("minimum_payment", 0),
                "El pago mínimo debe ser numérico.",
            ),
            monthly_interest_rate=self._normalizar_tasa(
                datos.get("monthly_interest_rate"),
            ),
            credit_limit=self._normalizar_monto(
                datos.get(
                    "credit_limit",
                    actual.credit_limit if actual else 0,
                ),
                "El cupo total debe ser numerico.",
            ),
            start_date=str(
                datos.get(
                    "start_date",
                    actual.start_date if actual else today_iso(),
                ),
            ),
            updated_at=today_iso(),
            active=bool(datos.get("active", datos.get("activa", True))),
        )

    @staticmethod
    def _normalizar_categoria(value: object) -> str:
        """Normaliza y valida categoría antes del modelo heredado."""
        category = str(value).strip().lower()
        legacy = {
            "tarjeta": "tarjeta_credito",
            "credito": "credito_consumo",
        }
        category = legacy.get(category, category)
        if category not in DEBT_CATEGORIES:
            raise ValueError("La categoría de deuda no es válida.")
        return category

    @staticmethod
    def _validar_deuda(debt: Debt) -> None:
        """Valida reglas de negocio de deudas."""
        if not debt.name:
            raise ValueError("El nombre de la deuda es obligatorio.")
        if debt.category not in DEBT_CATEGORIES:
            raise ValueError("La categoría de deuda no es válida.")
        if debt.current_monthly_payment <= 0:
            raise ValueError("El pago mensual debe ser mayor que cero.")

    @staticmethod
    def _validar_nombre_duplicado(
        name: str,
        debts: list[Debt],
        debt_id: str | None = None,
    ) -> None:
        """Evita nombres duplicados de deuda."""
        normalized = name.casefold()
        for debt in debts:
            if debt.debt_id == debt_id:
                continue
            if debt.name.casefold() == normalized:
                raise ValueError("Ya existe una deuda con ese nombre.")

    @staticmethod
    def _buscar_indice(debts: list[Debt], debt_id: str) -> int:
        """Busca una deuda por ID y devuelve su posición."""
        for index, debt in enumerate(debts):
            if debt.debt_id == debt_id:
                return index
        raise ValueError("La deuda no existe.")

    def _deuda_tiene_movimientos(self, debt_id: str) -> bool:
        """Indica si una deuda está usada por movimientos o recurrentes."""
        for label in self.repository.list_months():
            year, month = (int(part) for part in label.split("-"))
            budget = self.repository.load(year, month)
            for movement in budget.transactions + budget.recurring_items:
                if movement.debt_id == debt_id:
                    return True
        return False

    @staticmethod
    def _normalizar_monto(value: object, message: str) -> int:
        """Normaliza monto entero positivo."""
        try:
            amount = int(str(value).replace(".", "").replace(",", "").strip())
        except (TypeError, ValueError) as exc:
            raise ValueError(message) from exc
        if amount < 0:
            raise ValueError(message)
        return amount

    @staticmethod
    def _normalizar_tasa(value: object) -> float | None:
        """Normaliza tasa mensual opcional."""
        if value in ("", None):
            return None
        try:
            rate = float(str(value).replace(",", ".").strip())
        except (TypeError, ValueError) as exc:
            raise ValueError("La tasa de interés debe ser numérica.") from exc
        if rate < 0:
            raise ValueError("La tasa de interés no puede ser negativa.")
        return rate
