"""Generacion de datos ficticios para el Perfil Demo Avalancha."""

from __future__ import annotations

from datetime import date

from avalancha.models import (
    CategoryBudget,
    CuentaFinanciera,
    Debt,
    EXPENSE,
    INCOME,
    MonthlyBudget,
    RecurringItem,
    Transaction,
)
from avalancha.storage import BudgetRepository

from services.profile_service import PERFIL_DEMO, PerfilAplicacion, ProfileService
from services.reconciliation_service import ReconciliationService
from services.report_service import ReportService


class DemoProfileService:
    """Crea y regenera el perfil demo sin usar datos personales."""

    def __init__(self, profile_service: ProfileService | None = None) -> None:
        """Inicializa el generador con el servicio de perfiles."""
        self.profile_service = profile_service or ProfileService()

    def asegurar_demo(self) -> PerfilAplicacion:
        """Crea el demo si falta y asegura que tenga datos ficticios."""
        profile = self.profile_service.asegurar_demo_registrado()
        if not self._tiene_datos_demo(profile):
            self.regenerar_demo()
        return self.profile_service.obtener_perfil(PERFIL_DEMO)

    def regenerar_demo(self) -> PerfilAplicacion:
        """Sobrescribe datos ficticios del demo sin tocar otros perfiles."""
        profile = self.profile_service.asegurar_demo_registrado()
        today = date.today()
        repository = BudgetRepository(profile.data_dir)
        budget = self._crear_presupuesto_demo(today.year, today.month)
        accounts = self._crear_cuentas_demo()
        debts = self._crear_deudas_demo()

        self._asignar_relaciones_demo(budget, accounts, debts)
        repository.save(budget)
        repository.save_accounts(accounts)
        repository.save_debts(debts)
        self._crear_conciliaciones_demo(profile, today.year, today.month)
        self._crear_reporte_demo(profile, today.year, today.month)
        return profile

    def abrir_demo(self) -> PerfilAplicacion:
        """Activa el perfil demo, creandolo si es necesario."""
        profile = self.asegurar_demo()
        return self.profile_service.seleccionar_perfil(profile.id)

    @staticmethod
    def validar_demo_sin_datos_reales(profile: PerfilAplicacion) -> bool:
        """Verifica marcadores esperados de datos falsos."""
        repository = BudgetRepository(profile.data_dir)
        accounts = repository.load_accounts()
        budgets = repository.list_months()
        if profile.id != PERFIL_DEMO or not budgets:
            return False
        names = " ".join(account.name for account in accounts).casefold()
        return "demo" in names and "avalanch" in names

    @staticmethod
    def _tiene_datos_demo(profile: PerfilAplicacion) -> bool:
        """Indica si el demo ya tiene presupuesto, cuentas y deudas."""
        repository = BudgetRepository(profile.data_dir)
        return (
            bool(repository.list_months())
            and bool(repository.load_accounts())
            and bool(repository.load_debts())
        )

    def _crear_presupuesto_demo(self, year: int, month: int) -> MonthlyBudget:
        """Construye presupuesto demo con un mes completo."""
        budget = MonthlyBudget(
            year=year,
            month=month,
            categories=[
                CategoryBudget("Sueldo", INCOME, 1_850_000, True),
                CategoryBudget("Ingreso extra", INCOME, 120_000, False),
                CategoryBudget("Arriendo", EXPENSE, 620_000, True),
                CategoryBudget("Comida", EXPENSE, 320_000, False),
                CategoryBudget("Transporte", EXPENSE, 120_000, False),
                CategoryBudget("Salud", EXPENSE, 80_000, False),
                CategoryBudget("Servicios", EXPENSE, 190_000, True),
                CategoryBudget("Ocio", EXPENSE, 110_000, False),
                CategoryBudget("Ahorro", EXPENSE, 150_000, True),
                CategoryBudget("Mascota", EXPENSE, 65_000, False),
                CategoryBudget("Tarjeta demo", EXPENSE, 180_000, True),
            ],
        )
        for item in self._movimientos_demo(year, month):
            budget.add_or_update_transaction(item)
        for item in self._recurrentes_demo():
            budget.add_or_update_recurring(item)
        return budget

    @staticmethod
    def _movimientos_demo(year: int, month: int) -> list[Transaction]:
        """Devuelve movimientos ficticios del mes demo."""
        prefix = f"{year:04d}-{month:02d}"
        return [
            Transaction(
                INCOME,
                "Sueldo",
                1_850_000,
                f"{prefix}-05",
                "Remuneracion demo",
                "Transferencia",
            ),
            Transaction(
                INCOME,
                "Ingreso extra",
                80_000,
                f"{prefix}-12",
                "Proyecto freelance demo",
                "Transferencia",
            ),
            Transaction(
                EXPENSE,
                "Arriendo",
                620_000,
                f"{prefix}-01",
                "Arriendo departamento demo",
                "Transferencia",
            ),
            Transaction(
                EXPENSE,
                "Comida",
                96_300,
                f"{prefix}-08",
                "Supermercado semanal demo",
                "Debito",
            ),
            Transaction(
                EXPENSE,
                "Comida",
                74_800,
                f"{prefix}-18",
                "Feria y abarrotes demo",
                "Debito",
            ),
            Transaction(
                EXPENSE,
                "Transporte",
                42_000,
                f"{prefix}-15",
                "Combustible demo",
                "Debito",
            ),
            Transaction(
                EXPENSE,
                "Salud",
                28_000,
                f"{prefix}-16",
                "Farmacia demo",
                "Debito",
                is_unexpected=True,
            ),
            Transaction(
                EXPENSE,
                "Servicios",
                86_500,
                f"{prefix}-03",
                "Electricidad y agua demo",
                "Debito",
            ),
            Transaction(
                EXPENSE,
                "Servicios",
                32_900,
                f"{prefix}-10",
                "Internet hogar demo",
                "Debito",
            ),
            Transaction(
                EXPENSE,
                "Ocio",
                39_990,
                f"{prefix}-20",
                "Salida familiar demo",
                "Credito",
            ),
            Transaction(
                EXPENSE,
                "Mascota",
                48_500,
                f"{prefix}-21",
                "Alimento mascota demo",
                "Debito",
            ),
            Transaction(
                EXPENSE,
                "Ahorro",
                150_000,
                f"{prefix}-05",
                "Ahorro mensual demo",
                "Transferencia",
            ),
            Transaction(
                EXPENSE,
                "Tarjeta demo",
                180_000,
                f"{prefix}-05",
                "Pago tarjeta demo",
                "Transferencia",
            ),
        ]

    @staticmethod
    def _recurrentes_demo() -> list[RecurringItem]:
        """Devuelve pagos recurrentes ficticios."""
        return [
            RecurringItem(
                INCOME,
                "Sueldo",
                1_850_000,
                "Remuneracion demo",
                5,
                "Transferencia",
            ),
            RecurringItem(
                EXPENSE,
                "Arriendo",
                620_000,
                "Arriendo departamento demo",
                1,
                "Transferencia",
            ),
            RecurringItem(
                EXPENSE,
                "Servicios",
                32_900,
                "Internet hogar demo",
                10,
                "Debito",
            ),
            RecurringItem(
                EXPENSE,
                "Ahorro",
                150_000,
                "Ahorro mensual demo",
                5,
                "Transferencia",
            ),
            RecurringItem(
                EXPENSE,
                "Tarjeta demo",
                180_000,
                "Pago tarjeta demo",
                5,
                "Transferencia",
            ),
        ]

    @staticmethod
    def _crear_cuentas_demo() -> list[CuentaFinanciera]:
        """Crea cuentas ficticias con IDs estables."""
        return [
            CuentaFinanciera(
                account_id="demo-cuenta-corriente",
                name="Cuenta corriente Demo Avalancha",
                account_type="cuenta_corriente",
                real_balance=None,
            ),
            CuentaFinanciera(
                account_id="demo-ahorro",
                name="Ahorro emergencia Demo Avalancha",
                account_type="ahorro",
                real_balance=None,
            ),
            CuentaFinanciera(
                account_id="demo-efectivo",
                name="Efectivo Demo Avalancha",
                account_type="efectivo",
                real_balance=None,
            ),
            CuentaFinanciera(
                account_id="demo-tarjeta",
                name="Tarjeta credito Demo Avalancha",
                account_type="tarjeta_credito",
                real_balance=None,
            ),
        ]

    @staticmethod
    def _crear_deudas_demo() -> list[Debt]:
        """Crea deudas ficticias del perfil demo."""
        return [
            Debt(
                debt_id="demo-deuda-tarjeta",
                name="Tarjeta Demo Avalancha",
                category="tarjeta_credito",
                current_balance=1_240_000,
                previous_month_balance=1_390_000,
                current_monthly_payment=180_000,
                minimum_payment=75_000,
                monthly_interest_rate=2.4,
                credit_limit=2_000_000,
            ),
            Debt(
                debt_id="demo-deuda-consumo",
                name="Credito consumo Demo Avalancha",
                category="credito_consumo",
                current_balance=2_800_000,
                previous_month_balance=2_930_000,
                current_monthly_payment=160_000,
                minimum_payment=160_000,
                monthly_interest_rate=1.1,
            ),
        ]

    @staticmethod
    def _asignar_relaciones_demo(
        budget: MonthlyBudget,
        accounts: list[CuentaFinanciera],
        debts: list[Debt],
    ) -> None:
        """Vincula movimientos demo con cuentas y deuda ficticia."""
        current_account = accounts[0].account_id
        card_account = accounts[3].account_id
        card_debt = debts[0].debt_id
        for item in budget.transactions + budget.recurring_items:
            item.account_id = (
                card_account if item.payment_method == "Credito" else current_account
            )
            if item.category == "Tarjeta demo":
                item.debt_id = card_debt

    @staticmethod
    def _crear_conciliaciones_demo(
        profile: PerfilAplicacion,
        year: int,
        month: int,
    ) -> None:
        """Crea una cuenta cuadrada y otra con diferencia pequena."""
        service = ReconciliationService(
            data_dir=profile.data_dir,
            year=year,
            month=month,
        )
        current_balance = service.calcular_diferencia(
            "demo-cuenta-corriente",
            0,
        )
        registered = -current_balance
        service.crear_conciliacion(
            {
                "cuenta_id": "demo-cuenta-corriente",
                "saldo_real": registered,
                "fecha_conciliacion": date(year, month, 25),
                "estado": "Pendiente",
                "observaciones": "Cuenta demo cuadrada.",
            },
        )
        service.crear_conciliacion(
            {
                "cuenta_id": "demo-ahorro",
                "saldo_real": 2_000,
                "fecha_conciliacion": date(year, month, 25),
                "estado": "Pendiente",
                "observaciones": "Diferencia pequena ficticia.",
            },
        )

    @staticmethod
    def _crear_reporte_demo(
        profile: PerfilAplicacion,
        year: int,
        month: int,
    ) -> None:
        """Genera un reporte cifrado dentro del perfil demo."""
        service = ReportService(
            data_dir=profile.data_dir,
            reports_dir=profile.reports_dir,
            key_path=profile.key_path,
        )
        report = service.generar_reporte_mensual(month, year)
        try:
            service.guardar_reporte_cifrado(
                report,
                f"R{year:04d}-{month:02d}.avr",
            )
        except ValueError:
            return
