"""Servicio de aplicacion para CRUD de movimientos."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from uuid import uuid4

from avalancha.models import Transaction
from avalancha.storage import BudgetRepository

from core.models.movimiento import Movimiento


@dataclass(frozen=True, slots=True)
class OpcionCuenta:
    """Representa una cuenta disponible para formularios."""

    id: str
    nombre: str


class MovementService:
    """Administra movimientos usando repositorios heredados como storage."""

    def __init__(
        self,
        data_dir: str | Path = "data",
        year: int | None = None,
        month: int | None = None,
        repository: BudgetRepository | None = None,
    ) -> None:
        """Inicializa el servicio para un mes de trabajo."""
        today = date.today()
        self.year = year or today.year
        self.month = month or today.month
        self.repository = repository or BudgetRepository(data_dir)

    def obtener_movimientos(self) -> list[Movimiento]:
        """Devuelve los movimientos del mes ordenados del mas reciente."""
        budget = self.repository.load(self.year, self.month)
        movimientos = [
            self._desde_transaccion(item) for item in budget.transactions
        ]
        return sorted(
            movimientos,
            key=lambda item: (item.fecha, item.id),
            reverse=True,
        )

    def crear_movimiento(
        self,
        fecha: date | str,
        tipo: str,
        categoria: str,
        cuenta_id: str,
        monto: int | str,
        descripcion: str = "",
        imprevisto: bool = False,
    ) -> Movimiento:
        """Crea y persiste un movimiento nuevo."""
        movimiento = Movimiento(
            id=uuid4().hex,
            fecha=self._normalizar_fecha(fecha),
            tipo=tipo,
            categoria=categoria,
            descripcion=descripcion,
            monto=self._normalizar_monto(monto),
            cuenta_id=cuenta_id,
            medio_pago=self._medio_pago_por_cuenta(cuenta_id),
            imprevisto=bool(imprevisto),
            clase=self._clase_por_flags(bool(imprevisto), None),
        )
        self._validar_movimiento(movimiento)
        budget = self.repository.load(self.year, self.month)
        budget.add_or_update_transaction(self._a_transaccion(movimiento))
        self.repository.save(budget)
        return movimiento

    def editar_movimiento(
        self,
        movimiento_id: str,
        fecha: date | str,
        tipo: str,
        categoria: str,
        cuenta_id: str,
        monto: int | str,
        descripcion: str = "",
        imprevisto: bool | None = None,
    ) -> Movimiento:
        """Actualiza un movimiento existente."""
        original = self._obtener_transaccion(movimiento_id)
        if original is None:
            raise ValueError("El movimiento no existe.")
        es_imprevisto = (
            original.is_unexpected if imprevisto is None else bool(imprevisto)
        )
        movimiento = Movimiento(
            id=movimiento_id,
            fecha=self._normalizar_fecha(fecha),
            tipo=tipo,
            categoria=categoria,
            descripcion=descripcion,
            monto=self._normalizar_monto(monto),
            cuenta_id=cuenta_id,
            medio_pago=self._medio_pago_por_cuenta(cuenta_id),
            recurrente_id=original.recurring_id,
            deuda_id=original.debt_id,
            imprevisto=es_imprevisto,
            clase=self._clase_por_flags(es_imprevisto, original.recurring_id),
        )
        self._validar_movimiento(movimiento)
        budget = self.repository.load(self.year, self.month)
        budget.add_or_update_transaction(self._a_transaccion(movimiento))
        self.repository.save(budget)
        return movimiento

    def eliminar_movimiento(self, movimiento_id: str) -> None:
        """Elimina un movimiento persistido."""
        budget = self.repository.load(self.year, self.month)
        budget.delete_transaction(movimiento_id)
        self.repository.save(budget)

    def buscar_movimientos(self, texto: str) -> list[Movimiento]:
        """Busca movimientos por texto libre."""
        filtro = texto.strip().casefold()
        if not filtro:
            return self.obtener_movimientos()
        cuentas = self._mapa_cuentas()
        encontrados = []
        for movimiento in self.obtener_movimientos():
            contenido = " ".join(
                [
                    movimiento.fecha.strftime("%d-%m-%Y"),
                    movimiento.tipo,
                    movimiento.categoria,
                    movimiento.descripcion,
                    str(movimiento.monto),
                    cuentas.get(movimiento.cuenta_id, ""),
                    movimiento.clase,
                ]
            ).casefold()
            if filtro in contenido:
                encontrados.append(movimiento)
        return encontrados

    def obtener_categorias(self, tipo: str | None = None) -> list[str]:
        """Devuelve categorias disponibles, filtradas por tipo si aplica."""
        budget = self.repository.load(self.year, self.month)
        tipo_normalizado = tipo.strip().lower() if tipo else None
        categorias = [
            item.name
            for item in budget.categories
            if getattr(item, "active", True)
            and (
                tipo_normalizado is None
                or item.transaction_type == tipo_normalizado
            )
        ]
        return sorted(set(categorias), key=str.casefold)

    def obtener_cuentas(self) -> list[OpcionCuenta]:
        """Devuelve cuentas activas disponibles para movimientos."""
        cuentas = [
            OpcionCuenta(item.account_id, item.name)
            for item in self.repository.load_accounts()
            if item.active
        ]
        return sorted(cuentas, key=lambda item: item.nombre.casefold())

    def nombre_cuenta(self, cuenta_id: str) -> str:
        """Devuelve el nombre de una cuenta por identificador."""
        return self._mapa_cuentas().get(cuenta_id, "Sin cuenta")

    def _validar_movimiento(self, movimiento: Movimiento) -> None:
        """Valida reglas de negocio antes de guardar."""
        categorias = self.obtener_categorias(movimiento.tipo)
        cuentas = {item.id for item in self.obtener_cuentas()}
        if movimiento.categoria not in categorias:
            raise ValueError("La categoria seleccionada no existe.")
        if movimiento.cuenta_id not in cuentas:
            raise ValueError("La cuenta seleccionada no existe.")
        if movimiento.monto <= 0:
            raise ValueError("El monto debe ser mayor que cero.")

    def _existe_movimiento(self, movimiento_id: str) -> bool:
        """Indica si existe un movimiento en el mes activo."""
        return self._obtener_transaccion(movimiento_id) is not None

    def _obtener_transaccion(
        self,
        movimiento_id: str,
    ) -> Transaction | None:
        """Devuelve una transaccion heredada por id si existe."""
        budget = self.repository.load(self.year, self.month)
        for item in budget.transactions:
            if item.transaction_id == movimiento_id:
                return item
        return None

    def _desde_transaccion(self, transaction: Transaction) -> Movimiento:
        """Convierte una transaccion heredada al modelo V2."""
        return Movimiento(
            id=transaction.transaction_id,
            fecha=date.fromisoformat(transaction.tx_date),
            tipo=transaction.transaction_type,
            categoria=transaction.category,
            descripcion=transaction.description,
            monto=transaction.amount,
            cuenta_id=transaction.account_id or "sin-cuenta",
            medio_pago=transaction.payment_method,
            recurrente_id=transaction.recurring_id,
            deuda_id=transaction.debt_id,
            imprevisto=transaction.is_unexpected,
            clase=self._clase_movimiento(transaction),
        )

    def _a_transaccion(self, movimiento: Movimiento) -> Transaction:
        """Convierte un movimiento V2 a transaccion heredada persistible."""
        return Transaction(
            transaction_id=movimiento.id,
            transaction_type=movimiento.tipo,
            category=movimiento.categoria,
            amount=movimiento.monto,
            tx_date=movimiento.fecha.isoformat(),
            description=movimiento.descripcion,
            payment_method=movimiento.medio_pago,
            recurring_id=movimiento.recurrente_id,
            is_unexpected=movimiento.imprevisto,
            debt_id=movimiento.deuda_id,
            account_id=movimiento.cuenta_id,
        )

    def _mapa_cuentas(self) -> dict[str, str]:
        """Construye un mapa id-nombre de cuentas activas."""
        return {item.id: item.nombre for item in self.obtener_cuentas()}

    def _medio_pago_por_cuenta(self, cuenta_id: str) -> str:
        """Sugiere un medio de pago segun el tipo de cuenta."""
        cuentas = {
            item.account_id: item
            for item in self.repository.load_accounts()
            if item.active
        }
        cuenta = cuentas.get(cuenta_id)
        if cuenta is None:
            return "No especificado"
        medios = {
            "tarjeta_credito": "Credito",
            "debito": "Debito",
            "cuenta_corriente": "Transferencia",
            "efectivo": "Efectivo",
            "ahorro": "Transferencia",
        }
        return medios.get(cuenta.account_type, "Otro")

    @staticmethod
    def _clase_movimiento(transaction: Transaction) -> str:
        """Clasifica visualmente una transaccion heredada."""
        return MovementService._clase_por_flags(
            transaction.is_unexpected,
            transaction.recurring_id,
        )

    @staticmethod
    def _clase_por_flags(
        imprevisto: bool,
        recurrente_id: str | None,
    ) -> str:
        """Prioriza Imprevisto sobre Recurrente para evitar ambiguedad."""
        if imprevisto:
            return "Imprevisto"
        if recurrente_id:
            return "Recurrente"
        return "Normal"

    @staticmethod
    def _normalizar_fecha(value: date | str) -> date:
        """Convierte fecha ISO o dd-mm-aaaa a date."""
        if isinstance(value, date):
            return value
        text = value.strip()
        for fmt in ("%Y-%m-%d", "%d-%m-%Y"):
            try:
                return datetime.strptime(text, fmt).date()
            except ValueError:
                continue
        raise ValueError("La fecha no es valida.")

    @staticmethod
    def _normalizar_monto(value: int | str) -> int:
        """Convierte un monto CLP a entero positivo."""
        try:
            amount = int(str(value).replace(".", "").replace(",", "").strip())
        except (TypeError, ValueError) as exc:
            raise ValueError("El monto debe ser numerico.") from exc
        if amount <= 0:
            raise ValueError("El monto debe ser mayor que cero.")
        return amount
