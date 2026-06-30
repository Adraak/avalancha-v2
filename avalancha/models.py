"""Domain models for Avalancha."""

from __future__ import annotations

import calendar
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from typing import Any
from uuid import uuid4


EXPENSE = "gasto"
INCOME = "ingreso"
TRANSACTION_TYPES = {EXPENSE, INCOME}
DEBT_CATEGORIES = {
    "tarjeta_credito",
    "credito_consumo",
    "deuda_familiar",
    "credito_tercero",
    "otra",
}
ACCOUNT_TYPES = {
    "cuenta_corriente",
    "cuenta_vista",
    "debito",
    "efectivo",
    "ahorro",
    "tarjeta_credito",
    "inversion",
    "otro",
}


def new_id() -> str:
    """Return a compact random identifier."""
    return uuid4().hex


def today_iso() -> str:
    """Return today's date in ISO format."""
    return date.today().isoformat()


def now_iso() -> str:
    """Return the current timestamp in ISO format."""
    return datetime.now().replace(microsecond=0).isoformat()


def validate_amount(amount: int | float | str) -> int:
    """Validate and normalize CLP amounts as whole pesos."""
    try:
        value = int(str(amount).replace(".", "").replace(",", "").strip())
    except (TypeError, ValueError) as exc:
        raise ValueError("El monto debe ser un numero entero en CLP.") from exc

    if value < 0:
        raise ValueError("El monto no puede ser negativo.")
    return value


def validate_signed_amount(amount: int | float | str) -> int:
    """Validate and normalize a signed CLP amount."""
    try:
        return int(str(amount).replace(".", "").replace(",", "").strip())
    except (TypeError, ValueError) as exc:
        raise ValueError("El saldo debe ser un numero entero en CLP.") from exc


def validate_month(year: int, month: int) -> None:
    """Validate year and month values."""
    if year < 2000 or year > 2100:
        raise ValueError("El ano debe estar entre 2000 y 2100.")
    if month < 1 or month > 12:
        raise ValueError("El mes debe estar entre 1 y 12.")


@dataclass
class CategoryBudget:
    """Budget configuration for one category."""

    name: str
    transaction_type: str = EXPENSE
    budgeted_amount: int = 0
    is_fixed: bool = False
    alert_threshold: int = 80
    budget_id: str = field(default_factory=new_id)
    currency: str = "CLP"
    start_date: str = field(default_factory=today_iso)
    end_date: str | None = None
    active: bool = True
    notes: str = ""

    def __post_init__(self) -> None:
        self.name = self.name.strip()
        self.transaction_type = self.transaction_type.strip().lower()
        self.budgeted_amount = validate_amount(self.budgeted_amount)
        self.alert_threshold = int(self.alert_threshold)
        self.currency = self.currency.strip().upper() or "CLP"
        self.notes = self.notes.strip()

        if not self.name:
            raise ValueError("La categoria necesita un nombre.")
        if self.transaction_type not in TRANSACTION_TYPES:
            raise ValueError("El tipo debe ser gasto o ingreso.")
        if self.alert_threshold < 1 or self.alert_threshold > 100:
            raise ValueError("La alerta debe estar entre 1 y 100.")
        try:
            date.fromisoformat(self.start_date)
        except ValueError as exc:
            raise ValueError("La fecha de inicio debe usar YYYY-MM-DD.") from exc
        if self.end_date:
            try:
                end = date.fromisoformat(self.end_date)
            except ValueError as exc:
                raise ValueError(
                    "La fecha de termino debe usar YYYY-MM-DD."
                ) from exc
            if end < date.fromisoformat(self.start_date):
                raise ValueError(
                    "La fecha de termino no puede ser anterior al inicio."
                )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CategoryBudget":
        """Create an instance from JSON-compatible data."""
        return cls(
            name=data["name"],
            transaction_type=data.get("transaction_type", EXPENSE),
            budgeted_amount=data.get("budgeted_amount", 0),
            is_fixed=bool(data.get("is_fixed", False)),
            alert_threshold=data.get("alert_threshold", 80),
            budget_id=data.get("budget_id", new_id()),
            currency=data.get("currency", "CLP"),
            start_date=data.get("start_date", today_iso()),
            end_date=data.get("end_date"),
            active=bool(data.get("active", True)),
            notes=data.get("notes", ""),
        )

    def to_dict(self) -> dict[str, Any]:
        """Return JSON-compatible data."""
        return asdict(self)


@dataclass
class Transaction:
    """Actual income or expense record."""

    transaction_type: str
    category: str
    amount: int
    tx_date: str = field(default_factory=today_iso)
    description: str = ""
    payment_method: str = "No especificado"
    transaction_id: str = field(default_factory=new_id)
    recurring_id: str | None = None
    is_unexpected: bool = False
    debt_id: str | None = None
    account_id: str | None = None

    def __post_init__(self) -> None:
        self.transaction_type = self.transaction_type.strip().lower()
        self.category = self.category.strip()
        self.description = self.description.strip()
        self.payment_method = self.payment_method.strip() or "No especificado"
        if self.account_id is not None:
            self.account_id = self.account_id.strip() or None
        self.amount = validate_amount(self.amount)

        if self.transaction_type not in TRANSACTION_TYPES:
            raise ValueError("El tipo debe ser gasto o ingreso.")
        if not self.category:
            raise ValueError("La transaccion necesita categoria.")
        try:
            date.fromisoformat(self.tx_date)
        except ValueError as exc:
            raise ValueError("La fecha debe usar formato YYYY-MM-DD.") from exc

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Transaction":
        """Create an instance from JSON-compatible data."""
        return cls(
            transaction_id=data.get("transaction_id", new_id()),
            transaction_type=data["transaction_type"],
            category=data["category"],
            amount=data["amount"],
            tx_date=data.get("tx_date", today_iso()),
            description=data.get("description", ""),
            payment_method=data.get("payment_method", "No especificado"),
            recurring_id=data.get("recurring_id"),
            is_unexpected=bool(data.get("is_unexpected", False)),
            debt_id=data.get("debt_id"),
            account_id=data.get("account_id", data.get("cuenta_id")),
        )

    def to_dict(self) -> dict[str, Any]:
        """Return JSON-compatible data."""
        return asdict(self)


@dataclass
class RecurringItem:
    """Monthly recurring income or expense template."""

    transaction_type: str
    category: str
    amount: int
    description: str
    day_of_month: int = 1
    payment_method: str = "No especificado"
    active: bool = True
    recurring_id: str = field(default_factory=new_id)
    debt_id: str | None = None
    account_id: str | None = None

    def __post_init__(self) -> None:
        self.transaction_type = self.transaction_type.strip().lower()
        self.category = self.category.strip()
        self.description = self.description.strip()
        self.payment_method = self.payment_method.strip() or "No especificado"
        if self.account_id is not None:
            self.account_id = self.account_id.strip() or None
        self.amount = validate_amount(self.amount)
        self.day_of_month = int(self.day_of_month)

        if self.transaction_type not in TRANSACTION_TYPES:
            raise ValueError("El tipo debe ser gasto o ingreso.")
        if not self.category:
            raise ValueError("El recurrente necesita categoria.")
        if not self.description:
            raise ValueError("El recurrente necesita descripcion.")
        if self.day_of_month < 1 or self.day_of_month > 31:
            raise ValueError("El dia debe estar entre 1 y 31.")

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RecurringItem":
        """Create an instance from JSON-compatible data."""
        return cls(
            recurring_id=data.get("recurring_id", new_id()),
            transaction_type=data["transaction_type"],
            category=data["category"],
            amount=data["amount"],
            description=data["description"],
            day_of_month=data.get("day_of_month", 1),
            payment_method=data.get("payment_method", "No especificado"),
            active=bool(data.get("active", True)),
            debt_id=data.get("debt_id"),
            account_id=data.get("account_id", data.get("cuenta_id")),
        )

    def to_dict(self) -> dict[str, Any]:
        """Return JSON-compatible data."""
        return asdict(self)


@dataclass
class Debt:
    """Long-lived debt, credit card, or loan balance."""

    name: str
    category: str = "otra"
    current_balance: int = 0
    previous_month_balance: int = 0
    current_monthly_payment: int = 0
    minimum_payment: int = 0
    monthly_interest_rate: float | None = None
    credit_limit: int = 0
    start_date: str = field(default_factory=today_iso)
    updated_at: str = field(default_factory=now_iso)
    active: bool = True
    debt_id: str = field(default_factory=new_id)

    def __post_init__(self) -> None:
        self.name = self.name.strip()
        self.category = self._normalize_category(self.category)
        self.current_balance = validate_amount(self.current_balance)
        self.previous_month_balance = validate_amount(
            self.previous_month_balance
        )
        self.current_monthly_payment = validate_amount(
            self.current_monthly_payment
        )
        self.minimum_payment = validate_amount(self.minimum_payment)
        self.credit_limit = validate_amount(self.credit_limit)
        if self.monthly_interest_rate in ("", None):
            self.monthly_interest_rate = None
        else:
            self.monthly_interest_rate = float(self.monthly_interest_rate)
            if self.monthly_interest_rate < 0:
                raise ValueError("La tasa de interes no puede ser negativa.")

        if not self.name:
            raise ValueError("La deuda necesita un nombre.")
        try:
            date.fromisoformat(self.start_date)
        except ValueError as exc:
            raise ValueError("La fecha de inicio debe usar YYYY-MM-DD.") from exc

    @staticmethod
    def _normalize_category(category: str) -> str:
        """Return supported category, mapping old values when needed."""
        normalized = str(category).strip().lower()
        legacy = {
            "tarjeta": "tarjeta_credito",
            "credito": "credito_consumo",
        }
        normalized = legacy.get(normalized, normalized)
        if normalized not in DEBT_CATEGORIES:
            return "otra"
        return normalized

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Debt":
        """Create an instance from JSON-compatible data."""
        category = data.get("category", data.get("debt_type", "otra"))
        current_balance = data.get(
            "current_balance",
            data.get("initial_balance", 0),
        )
        return cls(
            debt_id=data.get("debt_id", new_id()),
            name=data["name"],
            category=category,
            current_balance=current_balance,
            previous_month_balance=data.get("previous_month_balance", 0),
            current_monthly_payment=data.get("current_monthly_payment", 0),
            minimum_payment=data.get("minimum_payment", 0),
            monthly_interest_rate=data.get("monthly_interest_rate"),
            credit_limit=data.get("credit_limit", 0),
            start_date=data.get("start_date", today_iso()),
            updated_at=data.get("updated_at", now_iso()),
            active=bool(data.get("active", True)),
        )

    def to_dict(self) -> dict[str, Any]:
        """Return JSON-compatible data."""
        return asdict(self)

    @property
    def debt_type(self) -> str:
        """Compatibility alias for older UI code."""
        return self.category

    @property
    def initial_balance(self) -> int:
        """Compatibility alias for older UI code."""
        return self.current_balance


@dataclass
class CuentaFinanciera:
    """Manual financial account used for reconciliation."""

    name: str
    account_type: str = "otro"
    initial_balance: int = 0
    real_balance: int | None = None
    registered_balance: int = 0
    reconciliation_date: str = field(default_factory=today_iso)
    reconciliation_status: str = "Pendiente"
    reconciliation_notes: str = ""
    active: bool = True
    account_id: str = field(default_factory=new_id)

    def __post_init__(self) -> None:
        self.name = self.name.strip()
        self.account_type = self.account_type.strip().lower()
        self.reconciliation_status = (
            self.reconciliation_status.strip() or "Pendiente"
        )
        self.reconciliation_notes = self.reconciliation_notes.strip()
        self.initial_balance = validate_signed_amount(self.initial_balance)
        if self.real_balance in ("", None):
            self.real_balance = None
        else:
            self.real_balance = validate_signed_amount(self.real_balance)
        self.registered_balance = validate_signed_amount(
            self.registered_balance
        )
        if not self.name:
            raise ValueError("La cuenta necesita un nombre.")
        if self.account_type not in ACCOUNT_TYPES:
            raise ValueError("El tipo de cuenta no es valido.")
        try:
            date.fromisoformat(self.reconciliation_date)
        except ValueError as exc:
            raise ValueError(
                "La fecha de conciliacion debe usar YYYY-MM-DD."
            ) from exc

    @property
    def difference(self) -> int | None:
        """Return real balance minus registered balance."""
        if self.real_balance is None:
            return None
        return self.real_balance - self.registered_balance

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CuentaFinanciera":
        """Create an account from JSON-compatible data."""
        legacy_registered = data.get("registered_balance", 0)
        return cls(
            account_id=data.get("account_id", data.get("id", new_id())),
            name=data["name"],
            account_type=data.get("account_type", data.get("type", "otro")),
            initial_balance=data.get(
                "initial_balance",
                legacy_registered,
            ),
            real_balance=data.get("real_balance"),
            registered_balance=legacy_registered,
            reconciliation_date=data.get(
                "reconciliation_date",
                today_iso(),
            ),
            reconciliation_status=data.get(
                "reconciliation_status",
                "Pendiente",
            ),
            reconciliation_notes=data.get("reconciliation_notes", ""),
            active=bool(data.get("active", True)),
        )

    def to_dict(self) -> dict[str, Any]:
        """Return JSON-compatible account data."""
        return asdict(self)


FinancialAccount = CuentaFinanciera


@dataclass
class MonthlyBudget:
    """Complete budget data for one month."""

    year: int
    month: int
    categories: list[CategoryBudget] = field(default_factory=list)
    transactions: list[Transaction] = field(default_factory=list)
    recurring_items: list[RecurringItem] = field(default_factory=list)
    created_at: str = field(default_factory=now_iso)
    updated_at: str = field(default_factory=now_iso)

    def __post_init__(self) -> None:
        validate_month(int(self.year), int(self.month))
        self.year = int(self.year)
        self.month = int(self.month)

    @classmethod
    def empty(cls, year: int, month: int) -> "MonthlyBudget":
        """Create a month with starter categories."""
        return cls(
            year=year,
            month=month,
            categories=[
                CategoryBudget("Sueldo", INCOME, 0, True),
                CategoryBudget("Otros ingresos", INCOME, 0, False),
                CategoryBudget("Vivienda", EXPENSE, 0, True),
                CategoryBudget("Comida", EXPENSE, 0, False),
                CategoryBudget("Transporte", EXPENSE, 0, False),
                CategoryBudget("Servicios", EXPENSE, 0, True),
                CategoryBudget("Salud", EXPENSE, 0, False),
                CategoryBudget("Ocio", EXPENSE, 0, False),
                CategoryBudget("Ahorro", EXPENSE, 0, True),
                CategoryBudget("Otros gastos", EXPENSE, 0, False),
            ],
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MonthlyBudget":
        """Create an instance from JSON-compatible data."""
        return cls(
            year=data["year"],
            month=data["month"],
            categories=[
                CategoryBudget.from_dict(item)
                for item in data.get("categories", [])
            ],
            transactions=[
                Transaction.from_dict(item)
                for item in data.get("transactions", [])
            ],
            recurring_items=[
                RecurringItem.from_dict(item)
                for item in data.get("recurring_items", [])
            ],
            created_at=data.get("created_at", now_iso()),
            updated_at=data.get("updated_at", now_iso()),
        )

    def to_dict(self) -> dict[str, Any]:
        """Return JSON-compatible data."""
        return {
            "year": self.year,
            "month": self.month,
            "categories": [item.to_dict() for item in self.categories],
            "transactions": [item.to_dict() for item in self.transactions],
            "recurring_items": [
                item.to_dict() for item in self.recurring_items
            ],
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @property
    def label(self) -> str:
        """Return the YYYY-MM label for this budget."""
        return f"{self.year:04d}-{self.month:02d}"

    def touch(self) -> None:
        """Update the modification timestamp."""
        self.updated_at = now_iso()

    def get_category_names(self, transaction_type: str | None = None) -> list[str]:
        """Return sorted category names, optionally filtered by type."""
        names = []
        for category in self.categories:
            if transaction_type is None:
                names.append(category.name)
            elif category.transaction_type == transaction_type:
                names.append(category.name)
        return sorted(set(names))

    def add_or_update_category(self, category: CategoryBudget) -> None:
        """Add a category or replace the existing one by name and type."""
        for index, current in enumerate(self.categories):
            same_name = current.name.lower() == category.name.lower()
            same_type = current.transaction_type == category.transaction_type
            if same_name and same_type:
                self.categories[index] = category
                self.touch()
                return
        self.categories.append(category)
        self.touch()

    def delete_category(self, name: str, transaction_type: str) -> None:
        """Delete a category if no transaction or recurrent item uses it."""
        in_transactions = any(
            item.category == name and item.transaction_type == transaction_type
            for item in self.transactions
        )
        in_recurring = any(
            item.category == name and item.transaction_type == transaction_type
            for item in self.recurring_items
        )
        if in_transactions or in_recurring:
            raise ValueError(
                "No se puede eliminar una categoria con movimientos asociados."
            )
        self.categories = [
            item
            for item in self.categories
            if not (
                item.name == name
                and item.transaction_type == transaction_type
            )
        ]
        self.touch()

    def add_or_update_transaction(self, transaction: Transaction) -> None:
        """Add or update a transaction."""
        self._ensure_category_exists(
            transaction.category,
            transaction.transaction_type,
        )
        for index, current in enumerate(self.transactions):
            if current.transaction_id == transaction.transaction_id:
                self.transactions[index] = transaction
                self.touch()
                return
        self.transactions.append(transaction)
        self.touch()

    def delete_transaction(self, transaction_id: str) -> None:
        """Delete a transaction by identifier."""
        before = len(self.transactions)
        self.transactions = [
            item
            for item in self.transactions
            if item.transaction_id != transaction_id
        ]
        if len(self.transactions) == before:
            raise ValueError("No se encontro la transaccion seleccionada.")
        self.touch()

    def add_or_update_recurring(self, item: RecurringItem) -> None:
        """Add or update a recurring item."""
        self._ensure_category_exists(item.category, item.transaction_type)
        for index, current in enumerate(self.recurring_items):
            if current.recurring_id == item.recurring_id:
                self.recurring_items[index] = item
                self.touch()
                return
        self.recurring_items.append(item)
        self.touch()

    def ensure_recurring_for_category(
        self,
        category: CategoryBudget,
        payment_method: str = "No especificado",
        account_id: str | None = None,
    ) -> RecurringItem | None:
        """Create a recurring template for a fixed category if missing."""
        if not category.is_fixed or category.budgeted_amount <= 0:
            return None

        existing = next(
            (
                item
                for item in self.recurring_items
                if (
                    item.category == category.name
                    and item.transaction_type == category.transaction_type
                    and item.active
                )
            ),
            None,
        )
        if existing is not None:
            return existing

        item = RecurringItem(
            transaction_type=category.transaction_type,
            category=category.name,
            amount=category.budgeted_amount,
            description=category.name,
            day_of_month=1,
            payment_method=payment_method,
            active=True,
            account_id=account_id,
        )
        self.recurring_items.append(item)
        self.touch()
        return item

    def ensure_recurring_for_fixed_expenses(
        self,
        payment_method: str = "No especificado",
        account_id: str | None = None,
    ) -> int:
        """Create missing recurring templates for fixed expense categories."""
        created = 0
        for category in self.categories:
            if category.transaction_type != EXPENSE:
                continue
            before = len(self.recurring_items)
            self.ensure_recurring_for_category(
                category,
                payment_method,
                account_id,
            )
            if len(self.recurring_items) > before:
                created += 1
        return created

    def delete_recurring(self, recurring_id: str) -> None:
        """Delete a recurring template."""
        before = len(self.recurring_items)
        self.recurring_items = [
            item
            for item in self.recurring_items
            if item.recurring_id != recurring_id
        ]
        if len(self.recurring_items) == before:
            raise ValueError("No se encontro el recurrente seleccionado.")
        self.touch()

    def apply_recurring_items(self) -> int:
        """Create this month's transactions from active recurring items."""
        created = 0
        for item in self.recurring_items:
            created += self.apply_recurring_item(item.recurring_id)
        return created

    def apply_recurring_item(self, recurring_id: str) -> int:
        """Create this month's transaction for one active recurring item."""
        item = next(
            (
                current
                for current in self.recurring_items
                if current.recurring_id == recurring_id
            ),
            None,
        )
        if item is None or not item.active:
            return 0

        already_exists = any(
            tx.recurring_id == item.recurring_id
            and tx.tx_date[:7] == self.label
            for tx in self.transactions
        )
        if already_exists:
            return 0

        last_day = calendar.monthrange(self.year, self.month)[1]
        day = min(item.day_of_month, last_day)
        tx_date = f"{self.year:04d}-{self.month:02d}-{day:02d}"
        self.transactions.append(
            Transaction(
                transaction_type=item.transaction_type,
                category=item.category,
                amount=item.amount,
                tx_date=tx_date,
                description=item.description,
                payment_method=item.payment_method,
                recurring_id=item.recurring_id,
                debt_id=item.debt_id,
                account_id=item.account_id,
            )
        )
        self.touch()
        return 1

    def sync_recurring_item_transaction(self, recurring_id: str) -> int:
        """Create or update this month's transaction for one recurring item."""
        item = next(
            (
                current
                for current in self.recurring_items
                if current.recurring_id == recurring_id
            ),
            None,
        )
        if item is None or not item.active:
            return 0

        last_day = calendar.monthrange(self.year, self.month)[1]
        day = min(item.day_of_month, last_day)
        tx_date = f"{self.year:04d}-{self.month:02d}-{day:02d}"
        linked_transactions = [
            tx
            for tx in self.transactions
            if tx.recurring_id == item.recurring_id
            and tx.tx_date[:7] == self.label
        ]
        existing = next(
            (
                tx
                for tx in linked_transactions
                if (
                    tx.transaction_type == item.transaction_type
                    and tx.category == item.category
                )
            ),
            linked_transactions[0] if len(linked_transactions) == 1 else None,
        )
        synced = Transaction(
            transaction_id=existing.transaction_id if existing else new_id(),
            transaction_type=item.transaction_type,
            category=item.category,
            amount=item.amount,
            tx_date=tx_date,
            description=item.description,
            payment_method=item.payment_method,
            recurring_id=item.recurring_id,
            is_unexpected=existing.is_unexpected if existing else False,
            debt_id=item.debt_id,
            account_id=item.account_id,
        )
        if existing is None:
            self.transactions.append(synced)
        else:
            index = self.transactions.index(existing)
            self.transactions[index] = synced
        self.touch()
        return 1

    def totals(self) -> dict[str, int]:
        """Return actual income, expense and balance totals."""
        income = sum(
            item.amount
            for item in self.transactions
            if item.transaction_type == INCOME
        )
        expenses = sum(
            item.amount
            for item in self.transactions
            if item.transaction_type == EXPENSE
        )
        return {
            "income": income,
            "expenses": expenses,
            "balance": income - expenses,
        }

    def expense_breakdown(self) -> dict[str, int]:
        """Return expenses grouped by movement class."""
        recurring = 0
        unexpected = 0
        variable = 0
        for item in self.transactions:
            if item.transaction_type != EXPENSE:
                continue
            if item.is_unexpected:
                unexpected += item.amount
            elif item.recurring_id:
                recurring += item.amount
            else:
                variable += item.amount
        return {
            "recurring": recurring,
            "unexpected": unexpected,
            "variable": variable,
        }

    def budgeted_totals(self) -> dict[str, int]:
        """Return budgeted income, expense and balance totals."""
        income = sum(
            item.budgeted_amount
            for item in self.categories
            if item.transaction_type == INCOME
        )
        expenses = sum(
            item.budgeted_amount
            for item in self.categories
            if item.transaction_type == EXPENSE
        )
        return {
            "income": income,
            "expenses": expenses,
            "balance": income - expenses,
        }

    def category_actuals(self, transaction_type: str) -> dict[str, int]:
        """Return actual totals by category."""
        totals: dict[str, int] = {}
        for item in self.transactions:
            if item.transaction_type != transaction_type:
                continue
            totals[item.category] = totals.get(item.category, 0) + item.amount
        return totals

    def category_report(self) -> list[dict[str, Any]]:
        """Return budget versus actual details for expense categories."""
        actuals = self.category_actuals(EXPENSE)
        recurring_categories = {
            item.category
            for item in self.recurring_items
            if item.transaction_type == EXPENSE and item.active
        }
        rows = []
        for category in sorted(
            self.categories,
            key=lambda item: (item.transaction_type, item.name.lower()),
        ):
            if category.transaction_type != EXPENSE:
                continue
            actual = actuals.get(category.name, 0)
            budgeted = category.budgeted_amount
            usage = round((actual / budgeted) * 100, 1) if budgeted else 0.0
            has_active_recurring = category.name in recurring_categories
            uses_fixed_control = (
                category.is_fixed or has_active_recurring
            )

            if uses_fixed_control:
                status = self._fixed_category_status(
                    actual,
                    budgeted,
                    has_active_recurring,
                )
            elif budgeted and actual > budgeted:
                status = "sobrepasado"
            elif budgeted and usage >= category.alert_threshold:
                status = "alerta"
            elif not budgeted and actual > 0:
                status = "sin presupuesto"
            else:
                status = "ok"
            rows.append(
                {
                    "name": category.name,
                    "budgeted": budgeted,
                    "actual": actual,
                    "remaining": budgeted - actual,
                    "usage": usage,
                    "status": status,
                    "is_fixed": uses_fixed_control,
                }
            )
        return rows

    @staticmethod
    def _fixed_category_status(
        actual: int,
        budgeted: int,
        has_active_recurring: bool = False,
    ) -> str:
        """Return a compliance status for fixed or recurring expenses."""
        if budgeted <= 0:
            return "sin presupuesto" if actual > 0 else "ok"
        if actual == 0:
            if has_active_recurring:
                return "programado"
            return "pendiente"
        if actual == budgeted:
            return "pagado"
        if actual > budgeted:
            return "sobrepasado"
        return "diferencia"

    def _ensure_category_exists(
        self,
        name: str,
        transaction_type: str,
    ) -> None:
        exists = any(
            item.name == name and item.transaction_type == transaction_type
            for item in self.categories
        )
        if not exists:
            self.categories.append(
                CategoryBudget(
                    name=name,
                    transaction_type=transaction_type,
                    budgeted_amount=0,
                )
            )
