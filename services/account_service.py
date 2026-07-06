"""Servicio de cuentas financieras para Avalancha V2."""

from __future__ import annotations

from pathlib import Path

from avalancha.models import ACCOUNT_TYPES, CuentaFinanciera, new_id, today_iso
from avalancha.storage import BudgetRepository


class AccountService:
    """Administra cuentas financieras sin depender de interfaz grafica."""

    TIPOS_CUENTA = {
        "cuenta_corriente": "Cuenta corriente",
        "cuenta_vista": "Cuenta vista",
        "tarjeta_credito": "Tarjeta de crédito",
        "ahorro": "Cuenta de ahorro",
        "efectivo": "Efectivo",
        "inversion": "Inversion",
        "debito": "Debito",
        "otro": "Otro",
    }

    def __init__(
        self,
        data_dir: str | Path = "data",
        year: int | None = None,
        month: int | None = None,
        repository: BudgetRepository | None = None,
    ) -> None:
        """Inicializa el servicio con el repositorio disponible."""
        self.repository = repository or BudgetRepository(data_dir)
        self.year = year
        self.month = month

    def obtener_cuentas(self) -> list[CuentaFinanciera]:
        """Devuelve todas las cuentas registradas."""
        return sorted(
            self._cuentas_con_saldo_registrado(
                self.repository.load_accounts(),
            ),
            key=lambda account: account.name.casefold(),
        )

    def obtener_cuentas_activas(self) -> list[CuentaFinanciera]:
        """Devuelve solo cuentas activas."""
        return [cuenta for cuenta in self.obtener_cuentas() if cuenta.active]

    def obtener_cuenta_por_id(self, cuenta_id: str) -> CuentaFinanciera:
        """Obtiene una cuenta por identificador estable."""
        for cuenta in self.obtener_cuentas():
            if cuenta.account_id == cuenta_id:
                return cuenta
        raise ValueError("La cuenta no existe.")

    def crear_cuenta(self, datos: dict[str, object]) -> CuentaFinanciera:
        """Crea y persiste una cuenta financiera."""
        cuenta = self._crear_modelo(datos)
        self._validar_cuenta(cuenta)
        cuentas = self.repository.load_accounts()
        self._validar_nombre_duplicado(cuenta.name, cuentas)
        cuentas.append(cuenta)
        self.repository.save_accounts(cuentas)
        return cuenta

    def editar_cuenta(
        self,
        cuenta_id: str,
        datos: dict[str, object],
    ) -> CuentaFinanciera:
        """Edita una cuenta existente."""
        cuentas = self.repository.load_accounts()
        index = self._buscar_indice(cuentas, cuenta_id)
        current = cuentas[index]
        cuenta = self._crear_modelo(datos, cuenta_id, current)
        self._validar_cuenta(cuenta)
        self._validar_nombre_duplicado(cuenta.name, cuentas, cuenta_id)
        cuentas[index] = cuenta
        self.repository.save_accounts(cuentas)
        return cuenta

    def eliminar_cuenta(self, cuenta_id: str) -> None:
        """Elimina una cuenta si no tiene movimientos asociados."""
        if self._cuenta_tiene_movimientos(cuenta_id):
            raise ValueError(
                "No se puede eliminar una cuenta con movimientos asociados. "
                "Puedes desactivarla."
            )
        cuentas = self.repository.load_accounts()
        index = self._buscar_indice(cuentas, cuenta_id)
        cuentas.pop(index)
        self.repository.save_accounts(cuentas)

    def activar_cuenta(self, cuenta_id: str) -> CuentaFinanciera:
        """Marca una cuenta como activa."""
        return self._cambiar_estado(cuenta_id, True)

    def desactivar_cuenta(self, cuenta_id: str) -> CuentaFinanciera:
        """Marca una cuenta como inactiva."""
        return self._cambiar_estado(cuenta_id, False)

    def guardar_cuenta(self, cuenta_actualizada: CuentaFinanciera) -> None:
        """Persiste una cuenta reemplazando su version anterior."""
        cuentas = self.repository.load_accounts()
        index = self._buscar_indice(cuentas, cuenta_actualizada.account_id)
        cuentas[index] = cuenta_actualizada
        self.repository.save_accounts(cuentas)

    def tipos_disponibles(self) -> list[tuple[str, str]]:
        """Devuelve tipos de cuenta disponibles para UI."""
        return [
            (key, label)
            for key, label in self.TIPOS_CUENTA.items()
            if key in ACCOUNT_TYPES
        ]

    def _cuentas_con_saldo_registrado(
        self,
        cuentas: list[CuentaFinanciera],
    ) -> list[CuentaFinanciera]:
        """Recalcula saldo registrado actual usando todos los meses."""
        movimientos = self._movimientos_registrados()
        for cuenta in cuentas:
            cuenta.registered_balance = self._calcular_saldo_registrado(
                cuenta,
                movimientos,
            )
        return cuentas

    def _movimientos_registrados(self) -> list[object]:
        """Carga movimientos de todos los meses guardados del perfil."""
        movimientos: list[object] = []
        for label in self.repository.list_months():
            year, month = (int(part) for part in label.split("-"))
            movimientos.extend(self.repository.load(year, month).transactions)
        return movimientos

    @staticmethod
    def _calcular_saldo_registrado(
        cuenta: CuentaFinanciera,
        movimientos: list[object],
    ) -> int:
        """Calcula saldo registrado desde movimientos asociados a la cuenta."""
        saldo = cuenta.initial_balance
        for movimiento in movimientos:
            tipo = getattr(movimiento, "transaction_type", "")
            monto = int(getattr(movimiento, "amount", 0))
            cuenta_origen = getattr(movimiento, "account_id", "")
            cuenta_destino = getattr(movimiento, "destination_account_id", "")
            if tipo == "transferencia":
                if cuenta_origen == cuenta.account_id:
                    saldo -= monto
                if cuenta_destino == cuenta.account_id:
                    saldo += monto
                continue
            if cuenta_origen != cuenta.account_id:
                continue
            if tipo == "pago_deuda":
                saldo -= monto
                continue
            if cuenta.account_type == "tarjeta_credito":
                if tipo == "gasto":
                    saldo += monto
                elif tipo == "ingreso":
                    saldo -= monto
                continue
            if tipo == "ingreso":
                saldo += monto
            elif tipo == "gasto":
                saldo -= monto
        return saldo

    def _cambiar_estado(
        self,
        cuenta_id: str,
        active: bool,
    ) -> CuentaFinanciera:
        """Actualiza el estado activo/inactivo de una cuenta."""
        cuentas = self.repository.load_accounts()
        index = self._buscar_indice(cuentas, cuenta_id)
        cuenta = cuentas[index]
        cuenta.active = active
        cuentas[index] = cuenta
        self.repository.save_accounts(cuentas)
        return cuenta

    def _crear_modelo(
        self,
        datos: dict[str, object],
        cuenta_id: str | None = None,
        actual: CuentaFinanciera | None = None,
    ) -> CuentaFinanciera:
        """Construye una cuenta desde datos validados externamente."""
        return CuentaFinanciera(
            account_id=(
                cuenta_id
                or str(datos.get("account_id", "")).strip()
                or new_id()
            ),
            name=str(datos.get("name", datos.get("nombre", ""))).strip(),
            account_type=str(
                datos.get("account_type", datos.get("tipo", "")),
            ).strip(),
            initial_balance=self._normalizar_monto(
                datos.get(
                    "initial_balance",
                    actual.initial_balance if actual else 0,
                ),
            ),
            real_balance=self._normalizar_saldo_real(
                datos.get(
                    "real_balance",
                    datos.get(
                        "saldo_real",
                        actual.real_balance if actual else None,
                    ),
                ),
            ),
            registered_balance=(
                actual.registered_balance if actual else 0
            ),
            reconciliation_date=(
                actual.reconciliation_date if actual else None
            ) or today_iso(),
            reconciliation_status=(
                actual.reconciliation_status if actual else "Pendiente"
            ),
            reconciliation_notes=(
                actual.reconciliation_notes if actual else ""
            ),
            active=bool(datos.get("active", datos.get("activa", True))),
        )

    def _validar_cuenta(self, cuenta: CuentaFinanciera) -> None:
        """Valida reglas de negocio de cuentas."""
        if not cuenta.name:
            raise ValueError("El nombre de la cuenta es obligatorio.")
        if not cuenta.account_type:
            raise ValueError("El tipo de cuenta es obligatorio.")
        if cuenta.account_type not in ACCOUNT_TYPES:
            raise ValueError("El tipo de cuenta no es valido.")

    @staticmethod
    def _validar_nombre_duplicado(
        name: str,
        cuentas: list[CuentaFinanciera],
        cuenta_id: str | None = None,
    ) -> None:
        """Evita duplicados activos por nombre."""
        normalized = name.casefold()
        for cuenta in cuentas:
            if cuenta.account_id == cuenta_id:
                continue
            if cuenta.name.casefold() == normalized:
                raise ValueError("Ya existe una cuenta con ese nombre.")

    @staticmethod
    def _buscar_indice(
        cuentas: list[CuentaFinanciera],
        cuenta_id: str,
    ) -> int:
        """Busca una cuenta por ID y devuelve su posicion."""
        for index, cuenta in enumerate(cuentas):
            if cuenta.account_id == cuenta_id:
                return index
        raise ValueError("La cuenta no existe.")

    def _cuenta_tiene_movimientos(self, cuenta_id: str) -> bool:
        """Indica si una cuenta esta usada por movimientos o recurrentes."""
        for label in self.repository.list_months():
            year, month = (int(part) for part in label.split("-"))
            budget = self.repository.load(year, month)
            for movement in budget.transactions + budget.recurring_items:
                if movement.account_id == cuenta_id:
                    return True
                if getattr(movement, "destination_account_id", None) == cuenta_id:
                    return True
        return False

    @staticmethod
    def _normalizar_monto(value: object) -> int:
        """Normaliza un monto entero con signo."""
        try:
            return int(str(value).replace(".", "").replace(",", "").strip())
        except (TypeError, ValueError) as exc:
            raise ValueError("El saldo inicial debe ser numerico.") from exc

    @staticmethod
    def _normalizar_saldo_real(value: object) -> int | None:
        """Normaliza saldo real opcional."""
        if value in ("", None):
            return None
        try:
            return int(str(value).replace(".", "").replace(",", "").strip())
        except (TypeError, ValueError) as exc:
            raise ValueError("El saldo real debe ser numerico.") from exc
