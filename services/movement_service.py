"""Servicio de aplicacion para CRUD de movimientos."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from uuid import uuid4

from avalancha.models import (
    Debt,
    DebtPayment,
    DebtSnapshot,
    Transaction,
    today_iso,
)
from avalancha.storage import BudgetRepository

from core.models.movimiento import Movimiento
from services.error_reporting_service import UserFacingError
from services.category_service import CategoryService
from services.debt_service import DebtService


@dataclass(frozen=True, slots=True)
class OpcionCuenta:
    """Representa una cuenta disponible para formularios."""

    id: str
    nombre: str


@dataclass(frozen=True, slots=True)
class OpcionDeuda:
    """Representa una deuda disponible para formularios."""

    id: str
    nombre: str
    saldo_actual: int


@dataclass(slots=True)
class DebtTraceState:
    """Agrupa datos de deuda que deben persistirse juntos."""

    debts: list[Debt]
    payments: list[DebtPayment]
    snapshots: list[DebtSnapshot]


class MovementService:
    """Administra movimientos usando repositorios heredados como storage."""

    def __init__(
        self,
        data_dir: str | Path = "data",
        year: int | None = None,
        month: int | None = None,
        repository: BudgetRepository | None = None,
        category_service: CategoryService | None = None,
        debt_service: DebtService | None = None,
    ) -> None:
        """Inicializa el servicio para un mes de trabajo."""
        today = date.today()
        self.year = year or today.year
        self.month = month or today.month
        self.repository = repository or BudgetRepository(data_dir)
        self.category_service = category_service or CategoryService(
            data_dir=self.repository.data_dir,
            repository=self.repository,
        )
        self.debt_service = debt_service or DebtService(
            data_dir=self.repository.data_dir,
            repository=self.repository,
        )

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
        categoria: str = "",
        cuenta_id: str = "",
        monto: int | str = 0,
        descripcion: str = "",
        imprevisto: bool = False,
        cuenta_destino_id: str | None = None,
        deuda_id: str | None = None,
    ) -> Movimiento:
        """Crea y persiste un movimiento nuevo."""
        normalized_type = str(tipo).strip().lower()
        if normalized_type == "transferencia":
            return self.crear_transferencia(
                fecha=fecha,
                cuenta_origen_id=cuenta_id,
                cuenta_destino_id=cuenta_destino_id,
                monto=monto,
                descripcion=descripcion,
                imprevisto=imprevisto,
            )
        if normalized_type == "pago_deuda":
            return self.crear_pago_deuda(
                fecha=fecha,
                cuenta_origen_id=cuenta_id,
                deuda_id=deuda_id,
                monto=monto,
                descripcion=descripcion,
                imprevisto=imprevisto,
            )
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

    def crear_pago_deuda(
        self,
        fecha: date | str,
        cuenta_origen_id: str,
        deuda_id: str | None,
        monto: int | str,
        descripcion: str = "",
        imprevisto: bool = False,
    ) -> Movimiento:
        """Crea un pago de deuda sin registrarlo como gasto mensual."""
        if imprevisto:
            raise UserFacingError("El pago de deuda no puede ser imprevisto.")
        movimiento = Movimiento(
            id=uuid4().hex,
            fecha=self._normalizar_fecha(fecha),
            tipo="pago_deuda",
            categoria="",
            descripcion=descripcion,
            monto=self._normalizar_monto(monto),
            cuenta_id=cuenta_origen_id,
            medio_pago="Pago de deuda",
            deuda_id=deuda_id,
            imprevisto=False,
            clase="Pago de deuda",
        )
        self._validar_movimiento(movimiento)
        budget = self.repository.load(self.year, self.month)
        budget.add_or_update_transaction(self._a_transaccion(movimiento))
        trace = self._deudas_ajustadas_por_pago(None, movimiento)
        self._guardar_budget_y_trazas(budget, trace)
        return movimiento

    def crear_transferencia(
        self,
        fecha: date | str,
        cuenta_origen_id: str,
        cuenta_destino_id: str | None,
        monto: int | str,
        descripcion: str = "",
        imprevisto: bool = False,
    ) -> Movimiento:
        """Crea una transferencia interna entre cuentas propias."""
        if imprevisto:
            raise UserFacingError("La transferencia no puede ser imprevisto.")
        movimiento = Movimiento(
            id=uuid4().hex,
            fecha=self._normalizar_fecha(fecha),
            tipo="transferencia",
            categoria="",
            descripcion=descripcion,
            monto=self._normalizar_monto(monto),
            cuenta_id=cuenta_origen_id,
            cuenta_destino_id=cuenta_destino_id,
            medio_pago="Transferencia interna",
            imprevisto=False,
            clase="Transferencia",
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
        categoria: str = "",
        cuenta_id: str = "",
        monto: int | str = 0,
        descripcion: str = "",
        imprevisto: bool | None = None,
        cuenta_destino_id: str | None = None,
        deuda_id: str | None = None,
    ) -> Movimiento:
        """Actualiza un movimiento existente."""
        original = self._obtener_transaccion(movimiento_id)
        if original is None:
            raise UserFacingError("El movimiento no existe.")
        normalized_type = str(tipo).strip().lower()
        if normalized_type == "transferencia":
            if imprevisto:
                raise UserFacingError("La transferencia no puede ser imprevisto.")
            movimiento = Movimiento(
                id=movimiento_id,
                fecha=self._normalizar_fecha(fecha),
                tipo="transferencia",
                categoria="",
                descripcion=descripcion,
                monto=self._normalizar_monto(monto),
                cuenta_id=cuenta_id,
                cuenta_destino_id=cuenta_destino_id,
                medio_pago="Transferencia interna",
                imprevisto=False,
                clase="Transferencia",
            )
            self._validar_movimiento(movimiento)
            budget = self.repository.load(self.year, self.month)
            budget.add_or_update_transaction(self._a_transaccion(movimiento))
            trace = self._deudas_ajustadas_por_pago(original, movimiento)
            self._guardar_budget_y_trazas(budget, trace)
            return movimiento
        if normalized_type == "pago_deuda":
            if imprevisto:
                raise UserFacingError("El pago de deuda no puede ser imprevisto.")
            movimiento = Movimiento(
                id=movimiento_id,
                fecha=self._normalizar_fecha(fecha),
                tipo="pago_deuda",
                categoria="",
                descripcion=descripcion,
                monto=self._normalizar_monto(monto),
                cuenta_id=cuenta_id,
                medio_pago="Pago de deuda",
                deuda_id=deuda_id or original.debt_id,
                imprevisto=False,
                clase="Pago de deuda",
            )
            self._validar_movimiento(movimiento)
            budget = self.repository.load(self.year, self.month)
            budget.add_or_update_transaction(self._a_transaccion(movimiento))
            trace = self._deudas_ajustadas_por_pago(original, movimiento)
            self._guardar_budget_y_trazas(budget, trace)
            return movimiento
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
            deuda_id=(
                deuda_id
                or (
                    original.debt_id
                    if original.transaction_type != "pago_deuda"
                    else None
                )
            ),
            imprevisto=es_imprevisto,
            clase=self._clase_por_flags(es_imprevisto, original.recurring_id),
        )
        self._validar_movimiento(
            movimiento,
            categoria_original=original.category,
        )
        budget = self.repository.load(self.year, self.month)
        budget.add_or_update_transaction(self._a_transaccion(movimiento))
        trace = self._deudas_ajustadas_por_pago(original, movimiento)
        self._guardar_budget_y_trazas(budget, trace)
        return movimiento

    def eliminar_movimiento(self, movimiento_id: str) -> None:
        """Elimina un movimiento persistido."""
        budget = self.repository.load(self.year, self.month)
        original = next(
            (
                item
                for item in budget.transactions
                if item.transaction_id == movimiento_id
            ),
            None,
        )
        budget.delete_transaction(movimiento_id)
        trace = self._deudas_ajustadas_por_pago(original, None)
        self._guardar_budget_y_trazas(budget, trace)

    def buscar_movimientos(self, texto: str) -> list[Movimiento]:
        """Busca movimientos por texto libre."""
        filtro = texto.strip().casefold()
        if not filtro:
            return self.obtener_movimientos()
        cuentas = self._mapa_cuentas()
        deudas = self._mapa_deudas()
        encontrados = []
        for movimiento in self.obtener_movimientos():
            destino = ""
            if movimiento.cuenta_destino_id:
                destino = cuentas.get(movimiento.cuenta_destino_id, "")
            contenido = " ".join(
                [
                    movimiento.fecha.strftime("%d-%m-%Y"),
                    movimiento.tipo,
                    movimiento.categoria,
                    movimiento.descripcion,
                    str(movimiento.monto),
                    cuentas.get(movimiento.cuenta_id, ""),
                    destino,
                    deudas.get(movimiento.deuda_id or "", ""),
                    movimiento.clase,
                ]
            ).casefold()
            if filtro in contenido:
                encontrados.append(movimiento)
        return encontrados

    def obtener_movimientos_por_cuenta(
        self,
        cuenta_id: str,
    ) -> list[Movimiento]:
        """Devuelve movimientos asociados a una cuenta origen o destino."""
        cuenta_id = str(cuenta_id).strip()
        if not cuenta_id:
            raise UserFacingError("Debe seleccionar una cuenta.")
        cuentas = {item.id for item in self.obtener_cuentas()}
        if cuenta_id not in cuentas:
            raise UserFacingError("La cuenta seleccionada no existe.")
        return [
            movimiento
            for movimiento in self.obtener_movimientos()
            if (
                movimiento.cuenta_id == cuenta_id
                or movimiento.cuenta_destino_id == cuenta_id
            )
        ]

    def obtener_categorias(
        self,
        tipo: str | None = None,
        incluir_inactivas: bool = False,
        incluir_categoria: str | None = None,
    ) -> list[str]:
        """Devuelve categorias disponibles, filtradas por tipo si aplica."""
        if tipo:
            return self.category_service.nombres_por_tipo(
                tipo,
                incluir_inactivas=incluir_inactivas,
                incluir_nombre=incluir_categoria,
            )
        categorias = (
            self.category_service.listar_categorias()
            if incluir_inactivas
            else self.category_service.listar_activas()
        )
        return [item.nombre for item in categorias]

    def obtener_cuentas(self) -> list[OpcionCuenta]:
        """Devuelve cuentas activas disponibles para movimientos."""
        cuentas = [
            OpcionCuenta(item.account_id, item.name)
            for item in self.repository.load_accounts()
            if item.active
        ]
        return sorted(cuentas, key=lambda item: item.nombre.casefold())

    def obtener_deudas(self) -> list[OpcionDeuda]:
        """Devuelve deudas activas disponibles para pagos."""
        return [
            OpcionDeuda(item.debt_id, item.name, item.current_balance)
            for item in self.debt_service.obtener_deudas_activas()
        ]

    def nombre_cuenta(self, cuenta_id: str) -> str:
        """Devuelve el nombre de una cuenta por identificador."""
        return self._mapa_cuentas().get(cuenta_id, "Sin cuenta")

    def nombre_deuda(self, deuda_id: str) -> str:
        """Devuelve el nombre visible de una deuda por identificador."""
        return self._mapa_deudas().get(deuda_id, "Sin deuda")

    def _validar_movimiento(
        self,
        movimiento: Movimiento,
        categoria_original: str | None = None,
    ) -> None:
        """Valida reglas de negocio antes de guardar."""
        cuentas = {item.id for item in self.obtener_cuentas()}
        if movimiento.monto <= 0:
            raise UserFacingError("El monto debe ser mayor que cero.")
        if movimiento.tipo == "transferencia":
            if movimiento.cuenta_id not in cuentas:
                raise UserFacingError("La cuenta origen seleccionada no existe.")
            if movimiento.cuenta_destino_id not in cuentas:
                raise UserFacingError("La cuenta destino seleccionada no existe.")
            if movimiento.cuenta_id == movimiento.cuenta_destino_id:
                raise UserFacingError(
                    "La cuenta origen y destino deben ser distintas."
                )
            if movimiento.imprevisto:
                raise UserFacingError("La transferencia no puede ser imprevisto.")
            return
        if movimiento.tipo == "pago_deuda":
            if movimiento.cuenta_id not in cuentas:
                raise UserFacingError("La cuenta origen seleccionada no existe.")
            if movimiento.imprevisto:
                raise UserFacingError("El pago de deuda no puede ser imprevisto.")
            if movimiento.recurrente_id:
                raise UserFacingError("El pago de deuda no puede ser recurrente.")
            debts = {
                item.debt_id: item
                for item in self.debt_service.obtener_deudas_activas()
            }
            if movimiento.deuda_id not in debts:
                raise UserFacingError("La deuda seleccionada no existe.")
            return
        permitir_inactiva = (
            categoria_original is not None
            and movimiento.categoria.casefold() == categoria_original.casefold()
        )
        self.category_service.validar_categoria_movimiento(
            movimiento.categoria,
            movimiento.tipo,
            permitir_inactiva=permitir_inactiva,
        )
        if movimiento.cuenta_id not in cuentas:
            raise UserFacingError("La cuenta seleccionada no existe.")

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
            cuenta_destino_id=getattr(
                transaction,
                "destination_account_id",
                None,
            ),
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
            destination_account_id=movimiento.cuenta_destino_id,
        )

    def _mapa_cuentas(self) -> dict[str, str]:
        """Construye un mapa id-nombre de cuentas activas."""
        return {item.id: item.nombre for item in self.obtener_cuentas()}

    def _mapa_deudas(self) -> dict[str, str]:
        """Construye un mapa id-nombre de deudas activas e historicas."""
        return {
            item.debt_id: item.name
            for item in self.debt_service.obtener_deudas()
        }

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
        if transaction.transaction_type == "transferencia":
            return "Transferencia"
        if transaction.transaction_type == "pago_deuda":
            return "Pago de deuda"
        return MovementService._clase_por_flags(
            transaction.is_unexpected,
            transaction.recurring_id,
        )

    def _deudas_ajustadas_por_pago(
        self,
        original: Transaction | None,
        nuevo: Movimiento | None,
    ) -> DebtTraceState:
        """Calcula saldos y trazas al crear, editar o eliminar pagos."""
        debts = self.repository.load_debts()
        payments = self.repository.load_debt_payments()
        snapshots = self.repository.load_debt_snapshots()
        by_id = {debt.debt_id: debt for debt in debts}

        if (
            original is not None
            and original.transaction_type == "pago_deuda"
            and original.debt_id
        ):
            self._revertir_traza_pago(original, by_id, payments, snapshots)

        if nuevo is not None and nuevo.tipo == "pago_deuda":
            self._registrar_traza_pago(nuevo, by_id, payments, snapshots)

        return DebtTraceState(debts, payments, snapshots)

    def _revertir_traza_pago(
        self,
        original: Transaction,
        debts: dict[str, Debt],
        payments: list[DebtPayment],
        snapshots: list[DebtSnapshot],
    ) -> None:
        """Revierte el saldo y elimina el pago activo asociado al movimiento."""
        debt = debts.get(original.debt_id or "")
        if debt is None:
            raise UserFacingError("La deuda original del pago no existe.")

        payment = next(
            (
                item
                for item in payments
                if item.movement_id == original.transaction_id
            ),
            None,
        )
        amount = payment.amount if payment else original.amount
        previous_balance = debt.current_balance
        debt.current_balance += amount
        debt.updated_at = today_iso()

        if payment is not None:
            payments.remove(payment)

        snapshots.append(
            DebtSnapshot(
                movement_id=original.transaction_id,
                debt_id=original.debt_id or "",
                tx_date=original.tx_date,
                previous_balance=previous_balance,
                balance=debt.current_balance,
                source="reversa",
                note="Reversa de pago de deuda.",
            )
        )

    def _registrar_traza_pago(
        self,
        movimiento: Movimiento,
        debts: dict[str, Debt],
        payments: list[DebtPayment],
        snapshots: list[DebtSnapshot],
    ) -> None:
        """Registra pago formal y snapshot de saldo posterior."""
        debt = debts.get(movimiento.deuda_id or "")
        if debt is None:
            raise UserFacingError("La deuda seleccionada no existe.")
        if not debt.active:
            raise UserFacingError("No se puede pagar una deuda inactiva.")
        if movimiento.monto > debt.current_balance:
            raise UserFacingError(
                "El pago no puede superar el saldo actual de la deuda."
            )

        previous_balance = debt.current_balance
        debt.current_balance -= movimiento.monto
        debt.updated_at = today_iso()
        estimated_interest = self.debt_service.calcular_interes_estimado(debt)
        note = movimiento.descripcion

        payments.append(
            DebtPayment(
                movement_id=movimiento.id,
                debt_id=movimiento.deuda_id or "",
                account_id=movimiento.cuenta_id,
                tx_date=movimiento.fecha.isoformat(),
                amount=movimiento.monto,
                balance_before=previous_balance,
                balance_after=debt.current_balance,
                estimated_interest=estimated_interest,
                note=note,
            )
        )
        snapshots.append(
            DebtSnapshot(
                movement_id=movimiento.id,
                debt_id=movimiento.deuda_id or "",
                tx_date=movimiento.fecha.isoformat(),
                previous_balance=previous_balance,
                balance=debt.current_balance,
                source="pago",
                note=note,
            )
        )

    def _guardar_budget_y_trazas(
        self,
        budget,
        trace: DebtTraceState,
    ) -> None:
        """Persiste presupuesto, deudas y trazas con reversa simple."""
        original_debts = self.repository.load_debts()
        original_payments = self.repository.load_debt_payments()
        original_snapshots = self.repository.load_debt_snapshots()
        self.repository.save_debts(trace.debts)
        self.repository.save_debt_payments(trace.payments)
        self.repository.save_debt_snapshots(trace.snapshots)
        try:
            self.repository.save(budget)
        except Exception:
            self.repository.save_debts(original_debts)
            self.repository.save_debt_payments(original_payments)
            self.repository.save_debt_snapshots(original_snapshots)
            raise

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
        raise UserFacingError("La fecha no es valida.")

    @staticmethod
    def _normalizar_monto(value: int | str) -> int:
        """Convierte un monto CLP a entero positivo."""
        try:
            amount = int(str(value).replace(".", "").replace(",", "").strip())
        except (TypeError, ValueError) as exc:
            raise UserFacingError("El monto debe ser numerico.") from exc
        if amount <= 0:
            raise UserFacingError("El monto debe ser mayor que cero.")
        return amount
