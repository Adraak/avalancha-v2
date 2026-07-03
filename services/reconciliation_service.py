"""Servicio de aplicacion para conciliacion financiera."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Any

from avalancha.models import CuentaFinanciera
from avalancha.storage import BudgetRepository

from core.models.conciliacion import Conciliacion
from core.models.cuenta import Cuenta
from core.models.movimiento import Movimiento
from services.account_service import AccountService
from services.movement_service import MovementService


class ReconciliationService:
    """Administra conciliaciones usando cuentas y movimientos reales."""

    def __init__(
        self,
        data_dir: str | Path = "data",
        year: int | None = None,
        month: int | None = None,
        account_service: AccountService | None = None,
        movement_service: MovementService | None = None,
        repository: BudgetRepository | None = None,
    ) -> None:
        """Inicializa el servicio para un mes de conciliacion."""
        today = date.today()
        self.year = year or today.year
        self.month = month or today.month
        self.repository = repository or BudgetRepository(data_dir)
        self.account_service = account_service or AccountService(
            data_dir=data_dir,
            repository=self.repository,
        )
        self.movement_service = movement_service or MovementService(
            data_dir=data_dir,
            year=self.year,
            month=self.month,
            repository=self.repository,
        )

    def obtener_conciliaciones(self) -> list[Conciliacion]:
        """Devuelve conciliaciones vigentes por cuenta activa."""
        return [
            self._desde_cuenta(cuenta)
            for cuenta in sorted(
                self.account_service.obtener_cuentas_activas(),
                key=lambda item: item.name.casefold(),
            )
        ]

    def obtener_conciliacion_por_id(
        self,
        conciliacion_id: str,
    ) -> Conciliacion:
        """Obtiene una conciliacion por identificador estable."""
        return self.obtener_conciliacion_por_cuenta(conciliacion_id)

    def obtener_conciliacion_por_cuenta(
        self,
        cuenta_id: str,
    ) -> Conciliacion:
        """Obtiene la conciliacion vigente de una cuenta."""
        cuenta = self.account_service.obtener_cuenta_por_id(cuenta_id)
        return self._desde_cuenta(cuenta)

    def crear_conciliacion(self, datos: dict[str, object]) -> Conciliacion:
        """Crea una conciliacion para una cuenta."""
        cuenta_id = str(datos.get("cuenta_id", "")).strip()
        fecha = self._normalizar_fecha(datos.get("fecha_conciliacion"))
        cuenta = self.account_service.obtener_cuenta_por_id(cuenta_id)
        if (
            cuenta.real_balance is not None
            and cuenta.reconciliation_date == fecha.isoformat()
        ):
            raise ValueError(
                "Ya existe una conciliacion para esa cuenta y fecha."
            )
        return self._guardar_desde_datos(cuenta_id, datos)

    def editar_conciliacion(
        self,
        conciliacion_id: str,
        datos: dict[str, object],
    ) -> Conciliacion:
        """Edita una conciliacion existente."""
        self.account_service.obtener_cuenta_por_id(conciliacion_id)
        cuenta_id = str(datos.get("cuenta_id", conciliacion_id)).strip()
        if cuenta_id != conciliacion_id:
            raise ValueError("No se puede cambiar la cuenta conciliada.")
        return self._guardar_desde_datos(conciliacion_id, datos)

    def eliminar_conciliacion(self, conciliacion_id: str) -> None:
        """Elimina datos de conciliacion sin eliminar la cuenta."""
        cuenta = self.account_service.obtener_cuenta_por_id(conciliacion_id)
        cuenta.real_balance = None
        cuenta.registered_balance = self._saldo_registrado_actual(cuenta)
        cuenta.reconciliation_date = date.today().isoformat()
        cuenta.reconciliation_status = "Pendiente"
        cuenta.reconciliation_notes = ""
        self.account_service.guardar_cuenta(cuenta)

    def calcular_diferencia(self, cuenta_id: str, saldo_real: int | str) -> int:
        """Calcula diferencia entre saldo real y saldo registrado."""
        cuenta = self.account_service.obtener_cuenta_por_id(cuenta_id)
        saldo = self._normalizar_monto(saldo_real)
        return saldo - self._saldo_registrado_actual(cuenta)

    def marcar_como_revisada(self, conciliacion_id: str) -> Conciliacion:
        """Marca una conciliacion como revisada."""
        conciliacion = self.obtener_conciliacion_por_id(conciliacion_id)
        datos = {
            "cuenta_id": conciliacion.cuenta_id,
            "saldo_real": conciliacion.saldo_real,
            "fecha_conciliacion": conciliacion.fecha_conciliacion,
            "estado": "Revisada",
            "observaciones": conciliacion.observaciones,
        }
        return self._guardar_desde_datos(conciliacion_id, datos)

    def obtener_cuentas_con_diferencia(self) -> list[Conciliacion]:
        """Devuelve conciliaciones con diferencia distinta de cero."""
        return [
            item
            for item in self.obtener_conciliaciones()
            if item.diferencia not in (None, 0)
        ]

    def calcular_saldo_registrado(
        self,
        cuenta: Cuenta | Any,
        movimientos: list[Movimiento | Any],
    ) -> int:
        """Calcula el saldo registrado desde movimientos asociados."""
        account_id = self._account_id(cuenta)
        account_type = self._account_type(cuenta)
        saldo = getattr(cuenta, "initial_balance", 0)
        for movimiento in movimientos:
            if self._is_transfer(movimiento):
                if self._movement_account_id(movimiento) == account_id:
                    saldo -= self._amount(movimiento)
                if (
                    self._movement_destination_account_id(movimiento)
                    == account_id
                ):
                    saldo += self._amount(movimiento)
                continue
            if self._movement_account_id(movimiento) != account_id:
                continue
            if account_type == "tarjeta_credito":
                if self._is_expense(movimiento):
                    saldo += self._amount(movimiento)
                if self._is_income(movimiento):
                    saldo -= self._amount(movimiento)
            else:
                if self._is_income(movimiento):
                    saldo += self._amount(movimiento)
                if self._is_expense(movimiento):
                    saldo -= self._amount(movimiento)
        return saldo

    def conciliar(
        self,
        cuenta: Cuenta | Any,
        movimientos: list[Movimiento | Any],
    ) -> Cuenta | Any:
        """Devuelve una cuenta con saldo registrado recalculado."""
        nuevo_saldo = self.calcular_saldo_registrado(cuenta, movimientos)
        if hasattr(cuenta, "saldo_registrado"):
            cuenta.saldo_registrado = nuevo_saldo
        else:
            cuenta.registered_balance = nuevo_saldo
        return cuenta

    def diferencia_total(self, cuentas: list[Cuenta | Any]) -> int:
        """Suma diferencias disponibles de cuentas conciliadas."""
        return sum(self._difference(cuenta) or 0 for cuenta in cuentas)

    def resumen_conciliacion(
        self,
        cuentas: list[Cuenta | Any],
    ) -> dict[str, object]:
        """Calcula totales de conciliacion de cuentas activas."""
        activas = [cuenta for cuenta in cuentas if self._is_active(cuenta)]
        diferencias = [
            self._difference(cuenta)
            for cuenta in activas
            if self._difference(cuenta) is not None
        ]
        fechas = [
            self._reconciliation_date(cuenta)
            for cuenta in activas
            if self._reconciliation_date(cuenta) is not None
        ]
        return {
            "saldo_real_total": sum(
                self._real_balance(cuenta)
                for cuenta in activas
                if self._real_balance(cuenta) is not None
            ),
            "saldo_registrado_total": sum(
                self._registered_balance(cuenta) for cuenta in activas
            ),
            "diferencia_total": sum(diferencias),
            "fecha_ultima_conciliacion": max(fechas) if fechas else None,
            "semaforo": self.semaforo(sum(diferencias)),
            "cuentas_sin_conciliar": sum(
                self._real_balance(cuenta) is None for cuenta in activas
            ),
        }

    @staticmethod
    def semaforo(diferencia: int) -> str:
        """Devuelve el color de alerta para la diferencia registrada."""
        diferencia_absoluta = abs(diferencia)
        if diferencia_absoluta <= 20_000:
            return "verde"
        if diferencia_absoluta <= 100_000:
            return "amarillo"
        return "rojo"

    def nombre_cuenta(self, cuenta_id: str) -> str:
        """Devuelve el nombre visible de una cuenta."""
        return self.account_service.obtener_cuenta_por_id(cuenta_id).name

    def opciones_cuentas(self) -> list[tuple[str, str]]:
        """Devuelve pares id/nombre de cuentas activas."""
        return [
            (cuenta.account_id, cuenta.name)
            for cuenta in self.account_service.obtener_cuentas_activas()
        ]

    def _guardar_desde_datos(
        self,
        cuenta_id: str,
        datos: dict[str, object],
    ) -> Conciliacion:
        """Valida, calcula y persiste una conciliacion."""
        cuenta = self.account_service.obtener_cuenta_por_id(cuenta_id)
        saldo_real = self._normalizar_monto(datos.get("saldo_real"))
        fecha = self._normalizar_fecha(datos.get("fecha_conciliacion"))
        saldo_registrado = self._saldo_registrado_actual(cuenta)
        diferencia = saldo_real - saldo_registrado
        estado_solicitado = str(datos.get("estado", "")).strip()
        estado = self._resolver_estado(estado_solicitado, diferencia)

        cuenta.real_balance = saldo_real
        cuenta.registered_balance = saldo_registrado
        cuenta.reconciliation_date = fecha.isoformat()
        cuenta.reconciliation_status = estado
        cuenta.reconciliation_notes = str(
            datos.get("observaciones", ""),
        ).strip()
        self.account_service.guardar_cuenta(cuenta)

        return Conciliacion(
            id=cuenta.account_id,
            cuenta_id=cuenta.account_id,
            saldo_real=saldo_real,
            saldo_registrado=saldo_registrado,
            fecha_conciliacion=fecha,
            estado=estado,
            observaciones=cuenta.reconciliation_notes,
        )

    def _desde_cuenta(self, cuenta: CuentaFinanciera) -> Conciliacion:
        """Construye una conciliacion desde una cuenta persistida."""
        saldo_registrado = self._saldo_registrado_actual(cuenta)
        diferencia = self._diferencia_desde_valores(
            cuenta.real_balance,
            saldo_registrado,
        )
        return Conciliacion(
            id=cuenta.account_id,
            cuenta_id=cuenta.account_id,
            saldo_real=cuenta.real_balance,
            saldo_registrado=saldo_registrado,
            fecha_conciliacion=self._normalizar_fecha(
                cuenta.reconciliation_date,
            ),
            estado=self._resolver_estado(
                getattr(cuenta, "reconciliation_status", ""),
                diferencia,
            ),
            observaciones=getattr(cuenta, "reconciliation_notes", ""),
        )

    def _saldo_registrado_actual(self, cuenta: CuentaFinanciera) -> int:
        """Calcula saldo registrado desde movimientos y tipo de cuenta."""
        return self.calcular_saldo_registrado(
            cuenta,
            self.movement_service.obtener_movimientos(),
        )

    @staticmethod
    def _resolver_estado(estado: str, diferencia: int | None) -> str:
        """Calcula estado de conciliacion segun diferencia."""
        if estado == "Revisada":
            return "Revisada"
        if diferencia is None:
            return "Pendiente"
        if diferencia == 0:
            return "Cuadrada"
        return "Con diferencia"

    @staticmethod
    def _diferencia_desde_valores(
        saldo_real: int | None,
        saldo_registrado: int,
    ) -> int | None:
        """Calcula diferencia con soporte para saldo real faltante."""
        if saldo_real is None:
            return None
        return saldo_real - saldo_registrado

    @staticmethod
    def _normalizar_monto(value: object) -> int:
        """Normaliza saldo real a entero."""
        try:
            return int(str(value).replace(".", "").replace(",", "").strip())
        except (TypeError, ValueError) as exc:
            raise ValueError("El saldo real debe ser numerico.") from exc

    @staticmethod
    def _normalizar_fecha(value: object) -> date:
        """Normaliza fecha desde date, ISO o dd-mm-aaaa."""
        if isinstance(value, date):
            return value
        if value in ("", None):
            raise ValueError("La fecha de conciliacion es obligatoria.")
        text = str(value).strip()
        for fmt in ("%Y-%m-%d", "%d-%m-%Y"):
            try:
                return datetime.strptime(text, fmt).date()
            except ValueError:
                continue
        raise ValueError("La fecha de conciliacion no es valida.")

    @staticmethod
    def _account_id(cuenta: Cuenta | Any) -> str:
        """Obtiene el identificador de cuenta en modelos V2 o heredados."""
        return getattr(cuenta, "account_id", getattr(cuenta, "id", ""))

    @staticmethod
    def _account_type(cuenta: Cuenta | Any) -> str:
        """Obtiene el tipo de cuenta en modelos V2 o heredados."""
        return getattr(cuenta, "account_type", getattr(cuenta, "tipo", ""))

    @staticmethod
    def _movement_account_id(movimiento: Movimiento | Any) -> str | None:
        """Obtiene la cuenta asociada a un movimiento."""
        return getattr(
            movimiento,
            "account_id",
            getattr(movimiento, "cuenta_id", None),
        )

    @staticmethod
    def _movement_destination_account_id(
        movimiento: Movimiento | Any,
    ) -> str | None:
        """Obtiene la cuenta destino de una transferencia."""
        return getattr(
            movimiento,
            "destination_account_id",
            getattr(movimiento, "cuenta_destino_id", None),
        )

    @staticmethod
    def _transaction_type(movimiento: Movimiento | Any) -> str:
        """Obtiene el tipo de movimiento."""
        return getattr(
            movimiento,
            "transaction_type",
            getattr(movimiento, "tipo", ""),
        )

    @classmethod
    def _is_income(cls, movimiento: Movimiento | Any) -> bool:
        """Indica si el movimiento es ingreso."""
        return cls._transaction_type(movimiento) == "ingreso"

    @classmethod
    def _is_expense(cls, movimiento: Movimiento | Any) -> bool:
        """Indica si el movimiento es gasto."""
        return cls._transaction_type(movimiento) == "gasto"

    @classmethod
    def _is_transfer(cls, movimiento: Movimiento | Any) -> bool:
        """Indica si el movimiento es transferencia interna."""
        return cls._transaction_type(movimiento) == "transferencia"

    @staticmethod
    def _amount(movimiento: Movimiento | Any) -> int:
        """Obtiene el monto de un movimiento."""
        return getattr(movimiento, "amount", getattr(movimiento, "monto", 0))

    @staticmethod
    def _is_active(cuenta: Cuenta | Any) -> bool:
        """Indica si la cuenta esta activa."""
        return getattr(cuenta, "active", getattr(cuenta, "activa", False))

    @staticmethod
    def _real_balance(cuenta: Cuenta | Any) -> int | None:
        """Obtiene el saldo real de una cuenta."""
        return getattr(
            cuenta,
            "real_balance",
            getattr(cuenta, "saldo_real", None),
        )

    @staticmethod
    def _registered_balance(cuenta: Cuenta | Any) -> int:
        """Obtiene el saldo registrado de una cuenta."""
        return getattr(
            cuenta,
            "registered_balance",
            getattr(cuenta, "saldo_registrado", 0),
        )

    @staticmethod
    def _difference(cuenta: Cuenta | Any) -> int | None:
        """Obtiene o calcula la diferencia de conciliacion."""
        if hasattr(cuenta, "difference"):
            return cuenta.difference
        if hasattr(cuenta, "diferencia"):
            return cuenta.diferencia
        real = ReconciliationService._real_balance(cuenta)
        if real is None:
            return None
        return real - ReconciliationService._registered_balance(cuenta)

    @staticmethod
    def _reconciliation_date(cuenta: Cuenta | Any) -> str | None:
        """Obtiene la fecha de conciliacion como texto ISO."""
        value = getattr(
            cuenta,
            "reconciliation_date",
            getattr(cuenta, "fecha_conciliacion", None),
        )
        if value is None:
            return None
        if hasattr(value, "isoformat"):
            return value.isoformat()
        return str(value)
