"""Persistencia JSON de Avalancha."""

from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path

from avalancha.models import (
    CuentaFinanciera,
    Debt,
    DebtPayment,
    DebtSnapshot,
    EXPENSE,
    MonthlyBudget,
    now_iso,
    validate_month,
)
from core.versioned_json_store import VersionedJsonStore
from core.models.monthly_closure import MonthlyClosure


LEGACY_ACCOUNT_NAME = "Cuenta por clasificar"


class BudgetRepository:
    """Carga y guarda archivos mensuales y datos financieros globales."""

    def __init__(self, data_dir: str | Path = "data") -> None:
        """Inicializa las carpetas de datos y respaldos internos."""
        self.data_dir = Path(data_dir)
        self.backup_dir = self.data_dir / "backups"
        self._json_store = VersionedJsonStore()
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.backup_dir.mkdir(parents=True, exist_ok=True)

    def budget_path(self, year: int, month: int) -> Path:
        """Devuelve la ruta JSON correspondiente a un mes."""
        validate_month(year, month)
        return self.data_dir / f"presupuesto_{year:04d}-{month:02d}.json"

    @property
    def debts_path(self) -> Path:
        """Devuelve la ruta del archivo global de deudas."""
        return self.data_dir / "deudas.json"

    @property
    def accounts_path(self) -> Path:
        """Devuelve la ruta del archivo global de cuentas."""
        return self.data_dir / "cuentas.json"

    @property
    def debt_payments_path(self) -> Path:
        """Devuelve la ruta del registro formal de pagos de deuda."""
        return self.data_dir / "debt_payments.json"

    @property
    def debt_snapshots_path(self) -> Path:
        """Devuelve la ruta del historial de saldos de deuda."""
        return self.data_dir / "debt_snapshots.json"

    @property
    def monthly_closures_path(self) -> Path:
        """Devuelve la ruta del estado de cierres mensuales."""
        return self.data_dir / "monthly_closures.json"

    def load(self, year: int, month: int) -> MonthlyBudget:
        """Carga un mes existente o crea uno básico en memoria."""
        path = self.budget_path(year, month)
        if not path.exists():
            return MonthlyBudget.empty(year, month)

        data = self._json_store.read(path)
        return MonthlyBudget.from_dict(data)

    def load_or_create_from_previous(
        self,
        year: int,
        month: int,
    ) -> tuple[MonthlyBudget, str | None]:
        """Carga un mes o hereda la configuración del último mes anterior."""
        path = self.budget_path(year, month)
        if path.exists():
            return self.load(year, month), None

        previous_label = self._find_previous_month(year, month)
        if previous_label is None:
            budget = MonthlyBudget.empty(year, month)
            self.save(budget)
            return budget, None

        previous_year, previous_month = (
            int(part) for part in previous_label.split("-")
        )
        previous = self.load(previous_year, previous_month)
        data = previous.to_dict()
        data["year"] = year
        data["month"] = month
        data["transactions"] = []
        data.pop("created_at", None)
        data.pop("updated_at", None)
        budget = MonthlyBudget.from_dict(data)
        self.save(budget)
        return budget, previous_label

    def save(self, budget: MonthlyBudget) -> Path:
        """Guarda un mes y respalda previamente su versión existente."""
        path = self.budget_path(budget.year, budget.month)
        self._json_store.check_existing(path)
        if path.exists():
            shutil.copy2(path, self._backup_path(path))

        budget.touch()
        self._json_store.write(
            path,
            budget.to_dict(),
        )
        return path

    def list_months(self) -> list[str]:
        """Devuelve las etiquetas de meses disponibles."""
        labels = []
        for path in self.data_dir.glob("presupuesto_????-??.json"):
            labels.append(path.stem.replace("presupuesto_", ""))
        return sorted(labels)

    def _find_previous_month(
        self,
        year: int,
        month: int,
    ) -> str | None:
        """Busca el mes almacenado más reciente anterior al solicitado."""
        target = f"{year:04d}-{month:02d}"
        previous = [
            label for label in self.list_months() if label < target
        ]
        return previous[-1] if previous else None

    def load_debts(self) -> list[Debt]:
        """Carga las definiciones globales de deudas."""
        path = self.debts_path
        if not path.exists():
            return []

        data = self._json_store.read(path)
        return [Debt.from_dict(item) for item in data.get("debts", [])]

    def save_debts(self, debts: list[Debt]) -> Path:
        """Guarda las deudas globales con respaldo previo."""
        path = self.debts_path
        self._json_store.check_existing(path)
        if path.exists():
            shutil.copy2(path, self._backup_path(path))

        self._json_store.write(
            path,
            {"debts": [item.to_dict() for item in debts]},
        )
        return path

    def load_debt_payments(self) -> list[DebtPayment]:
        """Carga el registro formal de pagos de deuda."""
        path = self.debt_payments_path
        if not path.exists():
            return []

        data = self._json_store.read(path)
        return [
            DebtPayment.from_dict(item)
            for item in data.get("debt_payments", [])
        ]

    def save_debt_payments(
        self,
        payments: list[DebtPayment],
    ) -> Path:
        """Guarda pagos formales de deuda con respaldo previo."""
        path = self.debt_payments_path
        self._json_store.check_existing(path)
        if path.exists():
            shutil.copy2(path, self._backup_path(path))

        self._json_store.write(
            path,
            {"debt_payments": [item.to_dict() for item in payments]},
        )
        return path

    def load_debt_snapshots(self) -> list[DebtSnapshot]:
        """Carga snapshots historicos de saldo de deuda."""
        path = self.debt_snapshots_path
        if not path.exists():
            return []

        data = self._json_store.read(path)
        return [
            DebtSnapshot.from_dict(item)
            for item in data.get("debt_snapshots", [])
        ]

    def save_debt_snapshots(
        self,
        snapshots: list[DebtSnapshot],
    ) -> Path:
        """Guarda snapshots de deuda con respaldo previo."""
        path = self.debt_snapshots_path
        self._json_store.check_existing(path)
        if path.exists():
            shutil.copy2(path, self._backup_path(path))

        self._json_store.write(
            path,
            {"debt_snapshots": [item.to_dict() for item in snapshots]},
        )
        return path

    def load_accounts(self) -> list[CuentaFinanciera]:
        """Carga las cuentas financieras registradas."""
        path = self.accounts_path
        if not path.exists():
            return []
        data = self._json_store.read(path)
        return [
            CuentaFinanciera.from_dict(item)
            for item in data.get("accounts", [])
        ]

    def save_accounts(self, accounts: list[CuentaFinanciera]) -> Path:
        """Guarda las cuentas financieras con respaldo previo."""
        path = self.accounts_path
        self._json_store.check_existing(path)
        if path.exists():
            shutil.copy2(path, self._backup_path(path))
        self._json_store.write(
            path,
            {"accounts": [item.to_dict() for item in accounts]},
        )
        return path

    def load_monthly_closures(self) -> list[MonthlyClosure]:
        """Carga estados de cierre mensual del perfil."""
        path = self.monthly_closures_path
        if not path.exists():
            return []

        data = self._json_store.read(path)
        return [
            MonthlyClosure.from_dict(item)
            for item in data.get("monthly_closures", [])
        ]

    def save_monthly_closures(
        self,
        closures: list[MonthlyClosure],
    ) -> Path:
        """Guarda estados de cierre mensual con respaldo previo."""
        path = self.monthly_closures_path
        self._json_store.check_existing(path)
        if path.exists():
            shutil.copy2(path, self._backup_path(path))

        self._json_store.write(
            path,
            {
                "monthly_closures": [
                    item.to_dict() for item in closures
                ],
            },
        )
        return path

    @staticmethod
    def migrate_legacy_account_links(
        budget: MonthlyBudget,
        accounts: list[CuentaFinanciera],
    ) -> bool:
        """Asigna registros antiguos a una cuenta temporal."""
        legacy_items = [
            item
            for item in budget.transactions + budget.recurring_items
            if not item.account_id
        ]
        if not legacy_items:
            return False

        account = next(
            (
                current
                for current in accounts
                if current.name.casefold() == LEGACY_ACCOUNT_NAME.casefold()
            ),
            None,
        )
        if account is None:
            account = CuentaFinanciera(
                name=LEGACY_ACCOUNT_NAME,
                account_type="otro",
                initial_balance=0,
                real_balance=None,
            )
            accounts.append(account)

        for item in legacy_items:
            item.account_id = account.account_id
        budget.touch()
        return True

    def _backup_path(self, source: Path) -> Path:
        """Devuelve una ruta de respaldo con precisión suficiente."""
        stamp = datetime.now().strftime("%Y%m%dT%H%M%S%f")
        candidate = self.backup_dir / f"{source.stem}.backup_{stamp}.json"
        sequence = 1
        while candidate.exists():
            candidate = self.backup_dir / (
                f"{source.stem}.backup_{stamp}_{sequence}.json"
            )
            sequence += 1
        return candidate

    def debt_payment_totals(
        self,
        overlay_budget: MonthlyBudget | None = None,
    ) -> dict[str, int]:
        """Devuelve pagos históricos agrupados por deuda."""
        totals: dict[str, int] = {}
        overlay_label = overlay_budget.label if overlay_budget else None

        for path in self.data_dir.glob("presupuesto_????-??.json"):
            label = path.stem.replace("presupuesto_", "")
            if overlay_label and label == overlay_label:
                continue
            budget = MonthlyBudget.from_dict(self._json_store.read(path))
            self._accumulate_debt_payments(budget, totals)

        if overlay_budget is not None:
            self._accumulate_debt_payments(overlay_budget, totals)
        return totals

    @staticmethod
    def _accumulate_debt_payments(
        budget: MonthlyBudget,
        totals: dict[str, int],
    ) -> None:
        """Acumula movimientos de gasto vinculados a deudas."""
        for item in budget.transactions:
            if item.transaction_type != EXPENSE or not item.debt_id:
                continue
            totals[item.debt_id] = totals.get(item.debt_id, 0) + item.amount
