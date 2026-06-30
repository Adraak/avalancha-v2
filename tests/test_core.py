"""Core tests for Avalancha."""

import zipfile
from datetime import date, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase, main

from avalancha.formatting import (
    format_clp_input,
    format_date_for_display,
    parse_display_date,
)
from avalancha.finanzas import (
    AnalizadorResumen,
    DebtProjection,
    DiagnosticoFinanciero,
    GestorConciliacion,
    GestorDeudas,
    IndiceRiesgoFinanciero,
    ProyectorDeuda,
    RankingDeudas,
    ReporteMensual,
    SimuladorPagos,
    SimuladorFinanciero,
)
from avalancha.historial_financiero import (
    GeneradorSnapshot,
    HistorialFinanciero,
    MesYaCerradoError,
)
from avalancha.gestor_reportes import (
    GestorReportes,
    ProveedorClaveLocal,
    ReporteDuplicadoError,
    ReporteInconsistenteError,
)
from avalancha.reporte_mensual import (
    GeneradorReporteMensual,
    ReporteEstructurado,
)
from avalancha.models import (
    CuentaFinanciera,
    Debt,
    EXPENSE,
    INCOME,
    CategoryBudget,
    MonthlyBudget,
    RecurringItem,
    Transaction,
)
from avalancha.perfiles import GestorPerfiles
from avalancha.storage import BudgetRepository, LEGACY_ACCOUNT_NAME
from avalancha.respaldo import GestorRespaldos
from avalancha.validaciones import validar_deuda, validar_movimiento
from avalancha.app import (
    CategoriesTab,
    account_options,
    budget_status_summary,
    configurar_escala_tk,
    normalize_payment_method,
    payment_method_options,
    suggested_payment_method_for_account,
)


class MonthlyBudgetTests(TestCase):
    """Monthly budget behavior tests."""

    def test_tk_scaling_is_centralized(self) -> None:
        """Verifica que la escala Tk se configure con una sola función."""
        calls = []

        class FakeTk:
            """Simula la interfaz mínima de una raíz Tk."""

            def __init__(self) -> None:
                """Inicializa el registro de llamadas."""
                self.tk = self

            def call(self, *args: object) -> None:
                """Registra llamadas hechas por la función probada."""
                calls.append(args)

        configurar_escala_tk(FakeTk(), 1.25)

        self.assertEqual(calls, [("tk", "scaling", 1.25)])

    def test_date_format_helpers(self) -> None:
        self.assertEqual(format_date_for_display("2026-06-15"), "15-06-2026")
        self.assertEqual(parse_display_date("15-06-2026"), "2026-06-15")

    def test_clp_input_formatting(self) -> None:
        self.assertEqual(format_clp_input("2845755"), "2.845.755")
        self.assertEqual(format_clp_input("200000"), "200.000")
        self.assertEqual(format_clp_input("2.845.755"), "2.845.755")
        self.assertEqual(
            format_clp_input("-125000", allow_negative=True),
            "-125.000",
        )

    def test_totals_and_category_report(self) -> None:
        budget = MonthlyBudget(
            year=2026,
            month=6,
            categories=[
                CategoryBudget("Sueldo", INCOME, 1_000_000, True),
                CategoryBudget("Comida", EXPENSE, 200_000, False, 80),
            ],
        )
        budget.add_or_update_transaction(
            Transaction(INCOME, "Sueldo", 1_000_000, "2026-06-01")
        )
        budget.add_or_update_transaction(
            Transaction(EXPENSE, "Comida", 180_000, "2026-06-02")
        )

        self.assertEqual(
            budget.totals(),
            {"income": 1_000_000, "expenses": 180_000, "balance": 820_000},
        )
        report = budget.category_report()[0]
        self.assertEqual(report["name"], "Comida")
        self.assertEqual(report["status"], "alerta")
        self.assertEqual(report["usage"], 90.0)

    def test_expense_breakdown_by_movement_class(self) -> None:
        budget = MonthlyBudget(
            year=2026,
            month=6,
            categories=[
                CategoryBudget("Comida", EXPENSE, 200_000, False),
                CategoryBudget("Servicios", EXPENSE, 50_000, True),
            ],
        )
        budget.add_or_update_transaction(
            Transaction(EXPENSE, "Comida", 10_000, "2026-06-01")
        )
        budget.add_or_update_transaction(
            Transaction(
                EXPENSE,
                "Comida",
                20_000,
                "2026-06-02",
                is_unexpected=True,
            )
        )
        budget.add_or_update_transaction(
            Transaction(
                EXPENSE,
                "Servicios",
                30_000,
                "2026-06-03",
                recurring_id="recurrente",
            )
        )

        self.assertEqual(
            budget.expense_breakdown(),
            {"recurring": 30_000, "unexpected": 20_000, "variable": 10_000},
        )

    def test_budget_status_summary_shows_recurring_and_unexpected_expenses(
        self,
    ) -> None:
        budget = MonthlyBudget(
            year=2026,
            month=6,
            categories=[
                CategoryBudget("Sueldo", INCOME, 1_000_000, True),
                CategoryBudget("Comida", EXPENSE, 200_000, False),
                CategoryBudget("Servicios", EXPENSE, 50_000, True),
            ],
        )
        budget.add_or_update_transaction(
            Transaction(
                INCOME,
                "Sueldo",
                1_000_000,
                "2026-06-01",
                recurring_id="sueldo",
            )
        )
        budget.add_or_update_transaction(
            Transaction(
                EXPENSE,
                "Servicios",
                30_000,
                "2026-06-02",
                recurring_id="servicios",
            )
        )
        budget.add_or_update_transaction(
            Transaction(
                EXPENSE,
                "Comida",
                20_000,
                "2026-06-03",
                is_unexpected=True,
            )
        )

        self.assertEqual(
            budget_status_summary(budget),
            "Recurrentes: $ 30.000 | Imprevistos: $ 20.000",
        )

    def test_old_transactions_default_to_not_unexpected(self) -> None:
        transaction = Transaction.from_dict(
            {
                "transaction_type": EXPENSE,
                "category": "Comida",
                "amount": 10_000,
                "tx_date": "2026-06-01",
            }
        )

        self.assertFalse(transaction.is_unexpected)

    def test_fixed_expense_statuses(self) -> None:
        budget = MonthlyBudget(
            year=2026,
            month=6,
            categories=[
                CategoryBudget("Chat GPT", EXPENSE, 21_416, True),
                CategoryBudget("Credito", EXPENSE, 250_000, True),
                CategoryBudget("Seguro", EXPENSE, 50_000, True),
            ],
        )
        budget.add_or_update_transaction(
            Transaction(EXPENSE, "Chat GPT", 21_416, "2026-06-05")
        )
        budget.add_or_update_transaction(
            Transaction(EXPENSE, "Seguro", 45_000, "2026-06-05")
        )

        report = {
            item["name"]: item["status"]
            for item in budget.category_report()
        }
        self.assertEqual(report["Chat GPT"], "pagado")
        self.assertEqual(report["Credito"], "pendiente")
        self.assertEqual(report["Seguro"], "diferencia")

    def test_active_recurring_uses_fixed_status(self) -> None:
        budget = MonthlyBudget(
            year=2026,
            month=6,
            categories=[
                CategoryBudget("Mascota", EXPENSE, 40_000, False),
            ],
            recurring_items=[
                RecurringItem(
                    EXPENSE,
                    "Mascota",
                    40_000,
                    "Comida perro",
                    active=True,
                )
            ],
        )
        budget.add_or_update_transaction(
            Transaction(EXPENSE, "Mascota", 40_000, "2026-06-10")
        )

        report = budget.category_report()[0]
        self.assertEqual(report["status"], "pagado")
        self.assertTrue(report["is_fixed"])

    def test_active_recurring_without_real_payment_is_programmed(self) -> None:
        budget = MonthlyBudget(
            year=2026,
            month=6,
            categories=[
                CategoryBudget("Fondo solidario", EXPENSE, 250_000, True),
            ],
            recurring_items=[
                RecurringItem(
                    EXPENSE,
                    "Fondo solidario",
                    250_000,
                    "Credito universitario",
                    active=True,
                )
            ],
        )

        report = budget.category_report()[0]
        self.assertEqual(report["status"], "programado")
        self.assertEqual(report["actual"], 0)

    def test_fixed_category_creates_recurring_template_once(self) -> None:
        category = CategoryBudget("Arriendo", EXPENSE, 650_000, True)
        budget = MonthlyBudget(
            year=2026,
            month=6,
            categories=[category],
        )

        first = budget.ensure_recurring_for_category(
            category,
            payment_method="Linea de debito",
        )
        second = budget.ensure_recurring_for_category(
            category,
            payment_method="Linea de debito",
        )

        self.assertIsNotNone(first)
        self.assertEqual(first, second)
        self.assertEqual(len(budget.recurring_items), 1)
        self.assertEqual(budget.recurring_items[0].category, "Arriendo")
        self.assertEqual(budget.recurring_items[0].amount, 650_000)

    def test_apply_fixed_expense_category_without_template(self) -> None:
        budget = MonthlyBudget(
            year=2026,
            month=6,
            categories=[
                CategoryBudget("Arriendo", EXPENSE, 650_000, True),
            ],
        )

        templates = budget.ensure_recurring_for_fixed_expenses(
            payment_method="Linea de debito",
            account_id="cuenta-1",
        )
        created = budget.apply_recurring_items()

        self.assertEqual(templates, 1)
        self.assertEqual(created, 1)
        self.assertEqual(len(budget.transactions), 1)
        self.assertEqual(budget.transactions[0].category, "Arriendo")
        self.assertEqual(budget.transactions[0].amount, 650_000)
        self.assertEqual(budget.transactions[0].account_id, "cuenta-1")

    def test_apply_recurring_items_once_per_month(self) -> None:
        budget = MonthlyBudget(
            year=2026,
            month=6,
            categories=[
                CategoryBudget("Servicios", EXPENSE, 50_000, True),
            ],
            recurring_items=[
                RecurringItem(
                    EXPENSE,
                    "Servicios",
                    35_000,
                    "Internet",
                    day_of_month=5,
                )
            ],
        )

        self.assertEqual(budget.apply_recurring_items(), 1)
        self.assertEqual(budget.apply_recurring_items(), 0)
        self.assertEqual(len(budget.transactions), 1)
        self.assertEqual(budget.transactions[0].tx_date, "2026-06-05")

    def test_apply_one_recurring_item_once(self) -> None:
        recurring = RecurringItem(
            EXPENSE,
            "Servicios",
            21_416,
            "Chat GPT",
            day_of_month=5,
            payment_method="Linea de debito",
            account_id="cuenta-1",
        )
        budget = MonthlyBudget(
            year=2026,
            month=6,
            categories=[
                CategoryBudget("Servicios", EXPENSE, 21_416, True),
            ],
            recurring_items=[recurring],
        )

        self.assertEqual(budget.apply_recurring_item(recurring.recurring_id), 1)
        self.assertEqual(budget.apply_recurring_item(recurring.recurring_id), 0)
        self.assertEqual(len(budget.transactions), 1)
        self.assertEqual(budget.transactions[0].amount, 21_416)
        self.assertEqual(
            budget.transactions[0].payment_method,
            "Linea de debito",
        )
        self.assertEqual(budget.transactions[0].account_id, "cuenta-1")

    def test_sync_recurring_item_updates_current_month_transaction(self) -> None:
        recurring = RecurringItem(
            EXPENSE,
            "Servicios",
            21_416,
            "Chat GPT",
            day_of_month=5,
            payment_method="Linea de debito",
            account_id="cuenta-1",
        )
        budget = MonthlyBudget(
            year=2026,
            month=6,
            categories=[
                CategoryBudget("Servicios", EXPENSE, 21_416, True),
            ],
            recurring_items=[recurring],
        )
        budget.apply_recurring_item(recurring.recurring_id)
        transaction_id = budget.transactions[0].transaction_id

        recurring.amount = 23_157
        recurring.description = "Chat GPT actualizado"
        recurring.day_of_month = 7
        recurring.payment_method = "Cuenta corriente"
        recurring.account_id = "cuenta-2"

        self.assertEqual(
            budget.sync_recurring_item_transaction(recurring.recurring_id),
            1,
        )
        self.assertEqual(len(budget.transactions), 1)
        self.assertEqual(budget.transactions[0].transaction_id, transaction_id)
        self.assertEqual(budget.transactions[0].amount, 23_157)
        self.assertEqual(budget.transactions[0].description, "Chat GPT actualizado")
        self.assertEqual(budget.transactions[0].tx_date, "2026-06-07")
        self.assertEqual(budget.transactions[0].payment_method, "Cuenta corriente")
        self.assertEqual(budget.transactions[0].account_id, "cuenta-2")

    def test_sync_recurring_prefers_matching_transaction_on_id_collision(
        self,
    ) -> None:
        recurring = RecurringItem(
            EXPENSE,
            "Tarjeta",
            200_000,
            "Pago de deuda",
            recurring_id="recurrente-compartido",
        )
        salary = Transaction(
            INCOME,
            "Sueldo",
            1_650_000,
            "2026-06-05",
            recurring_id=recurring.recurring_id,
        )
        card_payment = Transaction(
            EXPENSE,
            "Tarjeta",
            180_000,
            "2026-06-05",
            description="Pago anterior",
            recurring_id=recurring.recurring_id,
        )
        budget = MonthlyBudget(
            year=2026,
            month=6,
            recurring_items=[recurring],
            transactions=[salary, card_payment],
        )

        budget.sync_recurring_item_transaction(recurring.recurring_id)
        synced_payment = next(
            transaction
            for transaction in budget.transactions
            if transaction.transaction_id == card_payment.transaction_id
        )

        self.assertEqual(salary.transaction_type, INCOME)
        self.assertEqual(salary.amount, 1_650_000)
        self.assertEqual(synced_payment.transaction_type, EXPENSE)
        self.assertEqual(synced_payment.amount, 200_000)
        self.assertEqual(synced_payment.description, "Pago de deuda")

    def test_categories_tab_refresh_handles_income_only_budget(self) -> None:
        class FakeTree:
            def __init__(self) -> None:
                self.rows = []

            def get_children(self) -> list[str]:
                return []

            def delete(self, *args: object) -> None:
                return None

            def insert(self, *args: object, **kwargs: object) -> None:
                self.rows.append(kwargs["values"])

        budget = MonthlyBudget(
            year=2026,
            month=6,
            categories=[CategoryBudget("Sueldo", INCOME, 1_000_000, True)],
        )
        tab = object.__new__(CategoriesTab)
        tab.tree = FakeTree()
        tab.get_budget = lambda: budget

        CategoriesTab.refresh(tab)

        self.assertEqual(tab.tree.rows[0][1], "Sueldo")
        self.assertEqual(tab.tree.rows[0][6], "Si")


class BudgetRepositoryTests(TestCase):
    """Repository behavior tests."""

    def test_new_month_inherits_configuration_without_movements(self) -> None:
        """Verifica el traspaso automático de presupuesto y recurrentes."""
        with TemporaryDirectory() as temp_dir:
            repository = BudgetRepository(Path(temp_dir))
            recurring = RecurringItem(
                EXPENSE,
                "Arriendo",
                650_000,
                "Arriendo mensual",
                payment_method="Transferencia",
                account_id="cuenta-1",
            )
            june = MonthlyBudget(
                year=2026,
                month=6,
                categories=[
                    CategoryBudget("Sueldo", INCOME, 1_650_000, True),
                    CategoryBudget("Arriendo", EXPENSE, 650_000, True),
                ],
                transactions=[
                    Transaction(
                        INCOME,
                        "Sueldo",
                        1_650_000,
                        "2026-06-05",
                        account_id="cuenta-1",
                    )
                ],
                recurring_items=[recurring],
            )
            repository.save(june)

            july, inherited_from = (
                repository.load_or_create_from_previous(2026, 7)
            )

            self.assertEqual(inherited_from, "2026-06")
            self.assertEqual(july.label, "2026-07")
            self.assertEqual(len(july.transactions), 0)
            self.assertEqual(
                [item.to_dict() for item in july.categories],
                [item.to_dict() for item in june.categories],
            )
            self.assertEqual(len(july.recurring_items), 1)
            self.assertEqual(
                july.recurring_items[0].recurring_id,
                recurring.recurring_id,
            )
            self.assertEqual(
                july.recurring_items[0].account_id,
                "cuenta-1",
            )
            self.assertTrue(repository.budget_path(2026, 7).exists())

    def test_existing_month_is_not_overwritten_by_inheritance(self) -> None:
        """Verifica que un mes existente conserve sus movimientos."""
        with TemporaryDirectory() as temp_dir:
            repository = BudgetRepository(Path(temp_dir))
            june = MonthlyBudget.empty(2026, 6)
            repository.save(june)
            july = MonthlyBudget.empty(2026, 7)
            july.add_or_update_transaction(
                Transaction(
                    EXPENSE,
                    "Comida",
                    10_000,
                    "2026-07-03",
                )
            )
            repository.save(july)

            loaded, inherited_from = (
                repository.load_or_create_from_previous(2026, 7)
            )

            self.assertIsNone(inherited_from)
            self.assertEqual(len(loaded.transactions), 1)
            self.assertEqual(loaded.transactions[0].amount, 10_000)

    def test_save_load_and_backup(self) -> None:
        with TemporaryDirectory() as temp_dir:
            repository = BudgetRepository(Path(temp_dir))
            budget = MonthlyBudget.empty(2026, 6)
            first_path = repository.save(budget)
            self.assertTrue(first_path.exists())

            budget.add_or_update_transaction(
                Transaction(EXPENSE, "Comida", 10_000, "2026-06-03")
            )
            repository.save(budget)

            loaded = repository.load(2026, 6)
            backups = list((Path(temp_dir) / "backups").glob("*.json"))
            self.assertEqual(len(loaded.transactions), 1)
            self.assertEqual(loaded.transactions[0].amount, 10_000)
            self.assertEqual(len(backups), 1)

    def test_rapid_saves_create_distinct_backups(self) -> None:
        with TemporaryDirectory() as temp_dir:
            repository = BudgetRepository(Path(temp_dir))
            budget = MonthlyBudget.empty(2026, 6)
            repository.save(budget)

            for amount in (10_000, 20_000):
                budget.add_or_update_transaction(
                    Transaction(EXPENSE, "Comida", amount, "2026-06-03")
                )
                repository.save(budget)

            backups = list((Path(temp_dir) / "backups").glob("*.json"))
            self.assertEqual(len(backups), 2)

    def test_debt_persistence_and_payment_totals(self) -> None:
        with TemporaryDirectory() as temp_dir:
            repository = BudgetRepository(Path(temp_dir))
            debt = Debt(
                name="Tarjeta de credito",
                category="tarjeta_credito",
                current_balance=200_000,
                previous_month_balance=250_000,
                current_monthly_payment=50_000,
            )
            repository.save_debts([debt])

            budget = MonthlyBudget.empty(2026, 6)
            budget.add_or_update_transaction(
                Transaction(
                    EXPENSE,
                    "Tarjeta de credito",
                    50_000,
                    "2026-06-05",
                    debt_id=debt.debt_id,
                )
            )
            repository.save(budget)

            loaded_debts = repository.load_debts()
            totals = repository.debt_payment_totals()
            self.assertEqual(loaded_debts[0].name, "Tarjeta de credito")
            self.assertEqual(totals[debt.debt_id], 50_000)

    def test_recurring_debt_payment_creates_debt_linked_transaction(self) -> None:
        recurring = RecurringItem(
            EXPENSE,
            "Tarjeta de credito",
            50_000,
            "Pago tarjeta",
            debt_id="deuda-1",
        )
        budget = MonthlyBudget(
            year=2026,
            month=6,
            categories=[
                CategoryBudget("Tarjeta de credito", EXPENSE, 50_000, True),
            ],
            recurring_items=[recurring],
        )

        self.assertEqual(budget.apply_recurring_items(), 1)
        self.assertEqual(budget.transactions[0].debt_id, "deuda-1")

    def test_account_persistence(self) -> None:
        with TemporaryDirectory() as temp_dir:
            repository = BudgetRepository(Path(temp_dir))
            account = CuentaFinanciera(
                name="Cuenta principal",
                account_type="debito",
                real_balance=500_000,
                registered_balance=480_000,
                reconciliation_date="2026-06-24",
            )

            repository.save_accounts([account])
            loaded = repository.load_accounts()

            self.assertEqual(len(loaded), 1)
            self.assertEqual(loaded[0].name, "Cuenta principal")
            self.assertEqual(loaded[0].difference, 20_000)


class ProfileManagerTests(TestCase):
    """Pruebas de perfiles locales independientes."""

    def test_personal_profile_migrates_legacy_data(self) -> None:
        """Verifica que el perfil personal copia datos existentes."""
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            legacy_data = root / "data"
            repository = BudgetRepository(legacy_data)
            budget = MonthlyBudget.empty(2026, 6)
            budget.add_or_update_transaction(
                Transaction(INCOME, "Sueldo", 1_000_000, "2026-06-05")
            )
            repository.save(budget)
            repository.save_debts([])
            repository.save_accounts([])

            manager = GestorPerfiles(
                root / "perfiles",
                legacy_data,
                root / "reportes",
                root / "config",
            )
            profile = manager.obtener_activo()
            migrated = BudgetRepository(profile.data_dir).load(2026, 6)

            self.assertEqual(profile.nombre, "Personal")
            self.assertEqual(len(migrated.transactions), 1)
            self.assertTrue(
                profile.data_dir.joinpath("presupuesto_2026-06.json").exists()
            )

    def test_demo_profile_uses_isolated_fake_data(self) -> None:
        """Verifica que el demo no reutiliza datos personales."""
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            legacy_data = root / "data"
            repository = BudgetRepository(legacy_data)
            budget = MonthlyBudget.empty(2026, 6)
            budget.add_or_update_transaction(
                Transaction(
                    INCOME,
                    "Sueldo",
                    9_999_999,
                    "2026-06-05",
                    "Dato real sensible",
                )
            )
            repository.save(budget)

            manager = GestorPerfiles(
                root / "perfiles",
                legacy_data,
                root / "reportes",
                root / "config",
            )
            demo = manager.asegurar_demo()
            demo_budget = BudgetRepository(demo.data_dir).load(
                date.today().year,
                date.today().month,
            )
            descriptions = {
                transaction.description
                for transaction in demo_budget.transactions
            }

            self.assertEqual(demo.nombre, "Demo Avalancha")
            self.assertNotIn("Dato real sensible", descriptions)
            self.assertTrue(
                demo.reportes_dir.joinpath("index.avridx").exists()
            )
            self.assertGreater(len(demo_budget.transactions), 8)

    def test_profiles_have_separate_repositories(self) -> None:
        """Verifica que un perfil nuevo no comparte archivos."""
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            manager = GestorPerfiles(
                root / "perfiles",
                root / "data",
                root / "reportes",
                root / "config",
            )
            personal = manager.obtener_activo()
            prueba = manager.crear_perfil("Pruebas locales")

            self.assertNotEqual(personal.data_dir, prueba.data_dir)
            self.assertTrue(prueba.data_dir.exists())
            self.assertFalse(
                prueba.data_dir.joinpath("deudas.json").exists()
            )


class FinancialDebtTests(TestCase):
    """Debt indicator, projection, and simulation tests."""

    def test_debt_indicators(self) -> None:
        debt = Debt(
            debt_id="deuda-1",
            name="Credito consumo",
            category="credito_consumo",
            current_balance=1_000_000,
            previous_month_balance=1_200_000,
            current_monthly_payment=100_000,
        )
        manager = GestorDeudas([debt], {"deuda-1": 100_000})

        self.assertEqual(manager.deuda_total_actual(), 900_000)
        self.assertEqual(
            manager.deuda_por_categoria(),
            {"credito_consumo": 900_000},
        )
        self.assertEqual(manager.variacion_mensual_deuda(), 300_000)
        self.assertEqual(manager.pago_total_deuda_mes(), 100_000)
        self.assertEqual(manager.pago_acumulado_historico(), 100_000)
        self.assertEqual(manager.flujo_libre_disponible(1_000_000, 700_000), 300_000)
        self.assertEqual(manager.patrimonio_neto(), -900_000)

    def test_priority_debt_indicators_with_interest(self) -> None:
        consumption = Debt(
            debt_id="consumo",
            name="Credito consumo",
            category="credito_consumo",
            current_balance=841_842,
            current_monthly_payment=50_595,
        )
        card = Debt(
            debt_id="tarjeta",
            name="Tarjeta credito",
            category="tarjeta_credito",
            current_balance=2_845_755,
            current_monthly_payment=200_000,
            monthly_interest_rate=0.0285,
        )
        manager = GestorDeudas([consumption, card])
        summary = manager.obtener_resumen_deuda()

        self.assertEqual(manager.calcular_pago_mensual_total(), 250_595)
        self.assertEqual(manager.calcular_interes_mensual_estimado(), 81_104)
        self.assertEqual(manager.calcular_amortizacion_neta(), 169_491)
        self.assertEqual(summary["pago_mensual_total"], 250_595)
        self.assertEqual(summary["interes_mensual_estimado"], 81_104)
        self.assertEqual(summary["amortizacion_neta"], 169_491)
        self.assertFalse(summary["amortizacion_insuficiente"])

    def test_priority_debt_indicators_accept_percent_rate(self) -> None:
        debt = Debt(
            debt_id="tarjeta",
            name="Tarjeta credito",
            current_balance=2_845_755,
            current_monthly_payment=50_000,
            monthly_interest_rate=2.85,
        )
        manager = GestorDeudas([debt])

        self.assertEqual(manager.calcular_interes_mensual_estimado(), 81_104)
        self.assertEqual(manager.calcular_amortizacion_neta(), -31_104)
        self.assertTrue(
            manager.obtener_resumen_deuda()["amortizacion_insuficiente"]
        )

    def test_projection_without_interest(self) -> None:
        debt = Debt(
            debt_id="deuda-1",
            name="Credito",
            current_balance=1_000_000,
            current_monthly_payment=250_000,
        )
        projection = ProyectorDeuda().proyectar(debt)

        self.assertTrue(projection.amortizes)
        self.assertEqual(projection.months_remaining, 4)
        self.assertEqual(projection.total_paid_estimated, 1_000_000)
        self.assertEqual(projection.interest_estimated, 0)

    def test_projection_with_interest_not_amortizing(self) -> None:
        debt = Debt(
            debt_id="deuda-1",
            name="Tarjeta",
            current_balance=1_000_000,
            current_monthly_payment=10_000,
            monthly_interest_rate=0.02,
        )
        projection = ProyectorDeuda().proyectar(debt)

        self.assertFalse(projection.amortizes)
        self.assertIsNone(projection.months_remaining)

    def test_payment_simulator(self) -> None:
        debt = Debt(
            debt_id="deuda-1",
            name="Credito",
            current_balance=1_000_000,
        )
        scenarios = SimuladorFinanciero().comparar_pagos(
            debt,
            [200_000, 500_000],
        )

        self.assertEqual(scenarios[0]["meses_restantes"], 5)
        self.assertEqual(scenarios[1]["meses_restantes"], 2)

    def test_payment_simulator_compares_against_current_payment(self) -> None:
        debt = Debt(
            debt_id="deuda-1",
            name="Credito",
            current_balance=1_000_000,
            current_monthly_payment=100_000,
        )
        scenarios = SimuladorPagos([debt]).comparar(
            [200_000],
            debt_id="deuda-1",
            consider_interest=False,
        )

        self.assertEqual(scenarios[0]["meses_restantes"], 5)
        self.assertEqual(
            scenarios[0]["meses_ganados_vs_pago_actual"],
            5,
        )
        self.assertEqual(scenarios[0]["interes_total_estimado"], 0)

    def test_payment_simulator_marks_non_amortizing_scenario(self) -> None:
        debt = Debt(
            debt_id="tarjeta",
            name="Tarjeta",
            current_balance=1_000_000,
            current_monthly_payment=50_000,
            monthly_interest_rate=0.05,
        )
        scenario = SimuladorPagos([debt]).comparar([40_000])[0]

        self.assertFalse(scenario["amortiza"])
        self.assertIsNone(scenario["meses_restantes"])

    def test_account_reconciliation_totals_and_traffic_light(self) -> None:
        accounts = [
            CuentaFinanciera(
                name="Debito",
                account_type="debito",
                real_balance=500_000,
                registered_balance=450_000,
                reconciliation_date="2026-06-20",
            ),
            CuentaFinanciera(
                name="Efectivo",
                account_type="efectivo",
                real_balance=100_000,
                registered_balance=90_000,
                reconciliation_date="2026-06-22",
            ),
        ]
        manager = GestorConciliacion(accounts)

        self.assertEqual(manager.saldo_real_total(), 600_000)
        self.assertEqual(manager.saldo_registrado_total(), 540_000)
        self.assertEqual(manager.diferencia_total(), 60_000)
        self.assertEqual(manager.semaforo(), "amarillo")
        self.assertEqual(manager.fecha_ultima_conciliacion(), "2026-06-22")

    def test_registered_account_balance_is_calculated_from_movements(
        self,
    ) -> None:
        account = CuentaFinanciera(
            name="Cuenta Corriente Scotiabank",
            account_type="cuenta_corriente",
            initial_balance=300_000,
            real_balance=1_030_000,
        )
        budget = MonthlyBudget.empty(2026, 6)
        budget.add_or_update_transaction(
            Transaction(
                INCOME,
                "Sueldo",
                1_650_000,
                "2026-06-05",
                payment_method="Transferencia",
                account_id=account.account_id,
            )
        )
        budget.add_or_update_transaction(
            Transaction(
                EXPENSE,
                "Comida",
                900_000,
                "2026-06-10",
                payment_method="Debito",
                account_id=account.account_id,
            )
        )

        manager = GestorConciliacion([account])
        manager.recalcular_saldos_registrados(budget)

        self.assertEqual(account.registered_balance, 1_050_000)
        self.assertEqual(account.difference, -20_000)

    def test_credit_account_balance_uses_expenses_minus_payments(self) -> None:
        account = CuentaFinanciera(
            name="Visa Gold",
            account_type="tarjeta_credito",
        )
        budget = MonthlyBudget.empty(2026, 6)
        budget.add_or_update_transaction(
            Transaction(
                EXPENSE,
                "Comida",
                120_000,
                "2026-06-05",
                payment_method="Credito",
                account_id=account.account_id,
            )
        )
        budget.add_or_update_transaction(
            Transaction(
                INCOME,
                "Pago tarjeta",
                50_000,
                "2026-06-10",
                payment_method="Transferencia",
                account_id=account.account_id,
            )
        )

        GestorConciliacion([account]).recalcular_saldos_registrados(budget)

        self.assertEqual(account.registered_balance, 70_000)

    def test_legacy_movements_are_linked_to_temporary_account(self) -> None:
        budget = MonthlyBudget.empty(2026, 6)
        transaction = Transaction(
            EXPENSE,
            "Comida",
            10_000,
            "2026-06-05",
            payment_method="Linea de debito",
        )
        recurring = RecurringItem(
            EXPENSE,
            "Servicios",
            20_000,
            "Internet",
            payment_method="Automatico",
        )
        budget.transactions.append(transaction)
        budget.recurring_items.append(recurring)
        accounts: list[CuentaFinanciera] = []

        changed = BudgetRepository.migrate_legacy_account_links(
            budget,
            accounts,
        )

        self.assertTrue(changed)
        self.assertEqual(len(accounts), 1)
        self.assertEqual(accounts[0].name, LEGACY_ACCOUNT_NAME)
        self.assertEqual(transaction.account_id, accounts[0].account_id)
        self.assertEqual(recurring.account_id, accounts[0].account_id)
        self.assertEqual(transaction.payment_method, "Linea de debito")

    def test_new_account_base_balance_is_calculated_automatically(
        self,
    ) -> None:
        account_name = "Cuenta Corriente Scotiabank"
        account_id = "cuenta-scotiabank"
        budget = MonthlyBudget.empty(2026, 6)
        budget.add_or_update_transaction(
            Transaction(
                INCOME,
                "Sueldo",
                1_650_000,
                "2026-06-05",
                payment_method="Transferencia",
                account_id=account_id,
            )
        )
        budget.add_or_update_transaction(
            Transaction(
                EXPENSE,
                "Comida",
                900_000,
                "2026-06-10",
                payment_method="Debito",
                account_id=account_id,
            )
        )
        manager = GestorConciliacion([])
        base = manager.calcular_saldo_base_automatico(
            budget,
            account_id,
            1_030_000,
        )
        account = CuentaFinanciera(
            name=account_name,
            account_type="cuenta_corriente",
            account_id=account_id,
            initial_balance=base,
            real_balance=1_030_000,
        )
        manager = GestorConciliacion([account])
        manager.recalcular_saldos_registrados(budget)

        self.assertEqual(base, 280_000)
        self.assertEqual(account.registered_balance, 1_030_000)
        self.assertEqual(account.difference, 0)

    def test_old_account_uses_registered_balance_as_initial_balance(
        self,
    ) -> None:
        account = CuentaFinanciera.from_dict(
            {
                "name": "Cuenta antigua",
                "account_type": "debito",
                "real_balance": 500_000,
                "registered_balance": 480_000,
            }
        )

        self.assertEqual(account.initial_balance, 480_000)
        self.assertEqual(account.registered_balance, 480_000)

    def test_account_without_real_balance_is_not_reconciled(self) -> None:
        account = CuentaFinanciera(
            name="Cuenta nueva",
            account_type="debito",
            initial_balance=100_000,
            real_balance=None,
        )
        manager = GestorConciliacion([account])
        manager.recalcular_saldos_registrados(
            MonthlyBudget.empty(2026, 6)
        )

        self.assertIsNone(account.difference)
        self.assertEqual(manager.cuentas_sin_conciliar(), 1)
        self.assertEqual(manager.saldo_registrado_total(), 100_000)
        self.assertEqual(manager.diferencia_total(), 0)

    def test_survival_days_exclude_credit_card_balance(self) -> None:
        budget = MonthlyBudget.empty(2026, 6)
        budget.transactions.append(
            Transaction(
                EXPENSE,
                "Comida",
                240_000,
                "2026-06-24",
            )
        )
        accounts = [
            CuentaFinanciera(
                name="Cuenta corriente",
                account_type="debito",
                real_balance=100_000,
            ),
            CuentaFinanciera(
                name="Tarjeta",
                account_type="tarjeta_credito",
                real_balance=900_000,
            ),
        ]
        analyzer = AnalizadorResumen(
            budget,
            accounts,
            reference_date=date(2026, 6, 24),
        )

        self.assertEqual(analyzer.calcular_dias_supervivencia(), 10.0)

    def test_payment_methods_and_accounts_are_separate(self) -> None:
        account = CuentaFinanciera(
            name="Cuenta Corriente Scotiabank",
            account_type="cuenta_corriente",
        )
        methods = payment_method_options(MonthlyBudget.empty(2026, 6))
        accounts, lookup = account_options([account])

        self.assertNotIn("Cuenta Corriente Scotiabank", methods)
        self.assertIn("Debito", methods)
        self.assertIn("Cuenta Corriente Scotiabank", accounts)
        self.assertEqual(
            lookup["Cuenta Corriente Scotiabank"],
            account.account_id,
        )

    def test_payment_method_aliases_are_normalized(self) -> None:
        budget = MonthlyBudget.empty(2026, 6)
        budget.add_or_update_transaction(
            Transaction(
                EXPENSE,
                "Transporte",
                13_000,
                payment_method="Linea de debito",
            )
        )
        budget.add_or_update_transaction(
            Transaction(
                EXPENSE,
                "Comida",
                5_000,
                payment_method="Línea de débito",
            )
        )
        methods = payment_method_options(budget)

        self.assertEqual(normalize_payment_method("Línea de débito"), "Debito")
        self.assertEqual(methods.count("Debito"), 1)
        self.assertNotIn("Linea de debito", methods)
        self.assertNotIn("Línea de débito", methods)

    def test_account_type_suggests_payment_method(self) -> None:
        credit_card = CuentaFinanciera(
            name="Visa",
            account_type="tarjeta_credito",
        )
        debit_card = CuentaFinanciera(
            name="Debito",
            account_type="debito",
        )
        current_account = CuentaFinanciera(
            name="Corriente",
            account_type="cuenta_corriente",
        )

        self.assertEqual(
            suggested_payment_method_for_account(credit_card),
            "Credito",
        )
        self.assertEqual(
            suggested_payment_method_for_account(debit_card),
            "Debito",
        )
        self.assertIsNone(
            suggested_payment_method_for_account(current_account),
        )

    def test_financial_risk_returns_score_level_and_cause(self) -> None:
        result = IndiceRiesgoFinanciero().calcular(
            monthly_debt_payment=400_000,
            total_debt=5_000_000,
            net_income=1_000_000,
            free_cash_flow=-100_000,
            card_balance=900_000,
            total_card_limit=1_000_000,
            emergency_fund=0,
            basic_monthly_expense=600_000,
        )

        self.assertGreaterEqual(result.score, 51)
        self.assertIn(result.level, {"Alto", "Critico"})
        self.assertTrue(result.principal_cause)
        self.assertTrue(result.recommended_action)

    def test_debt_ranking_prioritizes_high_interest_card(self) -> None:
        debts = [
            Debt(
                debt_id="consumo",
                name="Credito consumo",
                category="credito_consumo",
                current_balance=3_000_000,
                current_monthly_payment=200_000,
                monthly_interest_rate=0.01,
            ),
            Debt(
                debt_id="tarjeta",
                name="Tarjeta bancaria",
                category="tarjeta_credito",
                current_balance=900_000,
                current_monthly_payment=80_000,
                monthly_interest_rate=0.04,
                credit_limit=1_000_000,
            ),
        ]
        ranking = RankingDeudas(debts).obtener()

        self.assertEqual(ranking[0]["deuda_id"], "tarjeta")
        self.assertEqual(ranking[0]["posicion"], 1)
        self.assertIn("alto uso de cupo", ranking[0]["razon"])


class SummaryAnalyzerTests(TestCase):
    """Monthly dashboard intelligence tests."""

    def _budget(self) -> MonthlyBudget:
        pending = RecurringItem(
            EXPENSE,
            "Servicios",
            100_000,
            "Internet pendiente",
            recurring_id="pendiente",
        )
        budget = MonthlyBudget(
            year=2026,
            month=6,
            categories=[
                CategoryBudget("Sueldo", INCOME, 1_000_000, True),
                CategoryBudget("Arriendo", EXPENSE, 500_000, True),
                CategoryBudget("Comida", EXPENSE, 200_000, False),
                CategoryBudget("Servicios", EXPENSE, 100_000, True),
            ],
            recurring_items=[pending],
        )
        budget.add_or_update_transaction(
            Transaction(INCOME, "Sueldo", 1_000_000, "2026-06-01")
        )
        budget.add_or_update_transaction(
            Transaction(EXPENSE, "Arriendo", 300_000, "2026-06-01")
        )
        budget.add_or_update_transaction(
            Transaction(EXPENSE, "Comida", 100_000, "2026-06-10")
        )
        return budget

    def test_expected_result_includes_pending_recurring_expenses(self) -> None:
        analyzer = AnalizadorResumen(
            self._budget(),
            reference_date=date(2026, 6, 20),
        )

        self.assertEqual(analyzer.calcular_recurrentes_pendientes(), 100_000)
        self.assertEqual(
            analyzer.calcular_resultado_esperado_fin_mes(),
            500_000,
        )
        self.assertEqual(analyzer.semaforo_resultado_esperado(), "verde")

    def test_expense_ranking_orders_categories_descending(self) -> None:
        ranking = AnalizadorResumen(self._budget()).obtener_ranking_gastos()

        self.assertEqual(ranking[0], {"categoria": "Arriendo", "monto": 300_000})
        self.assertEqual(ranking[1], {"categoria": "Comida", "monto": 100_000})

    def test_pending_classification_and_survival_days(self) -> None:
        account = CuentaFinanciera(
            name="Debito",
            account_type="debito",
            real_balance=500_000,
            registered_balance=450_000,
            reconciliation_date="2026-06-20",
        )
        analyzer = AnalizadorResumen(
            self._budget(),
            [account],
            reference_date=date(2026, 6, 20),
        )

        self.assertEqual(analyzer.calcular_pendiente_clasificar(), 50_000)
        self.assertEqual(analyzer.semaforo_pendiente(), "amarillo")
        self.assertEqual(analyzer.calcular_dias_supervivencia(), 25.0)
        self.assertEqual(analyzer.semaforo_dias_supervivencia(), "verde")

    def test_survival_days_handles_missing_accounts(self) -> None:
        analyzer = AnalizadorResumen(self._budget(), [])

        self.assertIsNone(analyzer.calcular_dias_supervivencia())
        self.assertEqual(analyzer.texto_dias_supervivencia(), "Sin cuentas")

    def test_general_financial_state(self) -> None:
        yellow_account = CuentaFinanciera(
            name="Debito",
            account_type="debito",
            real_balance=500_000,
            registered_balance=450_000,
        )
        yellow = AnalizadorResumen(
            self._budget(),
            [yellow_account],
        ).calcular_estado_financiero_general("Bajo")
        red = AnalizadorResumen(
            self._budget(),
            [yellow_account],
        ).calcular_estado_financiero_general("Alto")

        self.assertEqual(yellow["estado"], "Amarillo")
        self.assertEqual(red["estado"], "Rojo")

    def test_monthly_report_uses_display_date(self) -> None:
        debt = Debt(
            debt_id="deuda-1",
            name="Credito",
            current_balance=1_000_000,
            previous_month_balance=1_200_000,
            current_monthly_payment=100_000,
        )
        manager = GestorDeudas([debt], {})
        projection = DebtProjection(
            debt_id="deuda-1",
            months_remaining=10,
            extinction_date="2027-04-01",
            total_paid_estimated=1_000_000,
            interest_estimated=0,
            amortizes=True,
            balance_curve=[],
        )

        report = ReporteMensual(manager, {"deuda-1": projection}).generar()
        self.assertIn("01-04-2027", report)


class SecureReportTests(TestCase):
    """Pruebas del reporte mensual estructurado y cifrado."""

    def _build_report(self) -> ReporteEstructurado:
        """Construye una estructura financiera reutilizable en las pruebas."""
        budget = MonthlyBudget(
            year=2026,
            month=6,
            categories=[
                CategoryBudget("Sueldo", INCOME, 1_000_000, True),
                CategoryBudget("Comida", EXPENSE, 50_000, False),
                CategoryBudget("Otros", EXPENSE, 0, False),
            ],
            transactions=[
                Transaction(
                    INCOME,
                    "Sueldo",
                    1_000_000,
                    "2026-06-01",
                    description="Remuneración",
                    account_id="cuenta-1",
                ),
                Transaction(
                    EXPENSE,
                    "Comida",
                    80_000,
                    "2026-06-05",
                    description="Supermercado",
                    account_id="cuenta-1",
                ),
                Transaction(
                    EXPENSE,
                    "Otros",
                    10_000,
                    "2026-06-06",
                    description="Imprevisto",
                    is_unexpected=True,
                    account_id="cuenta-1",
                ),
            ],
        )
        account = CuentaFinanciera(
            account_id="cuenta-1",
            name="Cuenta corriente",
            account_type="debito",
            real_balance=900_000,
            registered_balance=910_000,
            reconciliation_date="2026-06-25",
        )
        debt = Debt(
            name="Crédito",
            current_balance=500_000,
            previous_month_balance=550_000,
            current_monthly_payment=100_000,
            monthly_interest_rate=0.01,
        )
        manager = GestorDeudas([debt])
        analyzer = AnalizadorResumen(
            budget,
            [account],
            reference_date=date(2026, 6, 25),
        )
        diagnostics = DiagnosticoFinanciero(
            budget,
            manager,
            [account],
            reference_date=date(2026, 6, 25),
        ).obtener_alertas()
        generator = GeneradorReporteMensual(
            presupuesto=budget,
            gestor_deudas=manager,
            cuentas=[account],
            analizador=analyzer,
            diagnosticos=diagnostics,
            fecha_libertad="2027-01-25",
            nivel_riesgo="Moderado",
            fecha_generacion=datetime(2026, 6, 29, 21, 45),
            historial=[
                {
                    "mes": "2026-05",
                    "ingresos_reales": 900_000,
                    "gastos_reales": 120_000,
                    "deuda_total": 550_000,
                    "patrimonio_neto": 350_000,
                    "riesgo_financiero": 45,
                    "diferencia_conciliacion": 40_000,
                }
            ],
            puntaje_riesgo=40,
        )
        return generator.generar_estructura_reporte()

    def test_report_structure_contains_executive_sections(self) -> None:
        """Verifica que el contenido estructurado mantenga el informe V2."""
        structure = self._build_report()
        titles = [section.titulo for section in structure.secciones]

        self.assertIn("RESUMEN EJECUTIVO", titles)
        self.assertIn("COMPARACIÓN CON EL MES ANTERIOR", titles)
        self.assertIn("INDICADORES", titles)
        self.assertIn("DIAGNÓSTICO FINANCIERO", titles)
        self.assertIn("HITOS DEL MES", titles)
        self.assertIn("OPORTUNIDADES", titles)
        executive = next(
            section
            for section in structure.secciones
            if section.titulo == "RESUMEN EJECUTIVO"
        )
        self.assertLessEqual(len(executive.lineas), 10)

    def test_encrypted_report_and_index_do_not_expose_content(self) -> None:
        """Verifica cifrado, índice y lectura interna del reporte."""
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            manager = GestorReportes(
                root / "reportes",
                ProveedorClaveLocal(root / "config" / "report.key"),
            )
            entry = manager.guardar_reporte(
                self._build_report(),
                "2026-06",
                datetime(2026, 6, 29, 21, 45),
            )
            report_bytes = (root / "reportes" / "R2026-06.avr").read_bytes()
            index_bytes = (root / "reportes" / "index.avridx").read_bytes()
            opened = manager.abrir_reporte(entry["id"])
            listed = manager.listar_reportes()

        self.assertNotIn(b"AVALANCHA", report_bytes)
        self.assertNotIn(b"2026-06", index_bytes)
        self.assertEqual(opened["mes"], "2026-06")
        self.assertEqual(listed[0]["estado"], "Íntegro")
        self.assertEqual(listed[0]["nombre"], "R2026-06.avr")

    def test_duplicate_month_is_rejected(self) -> None:
        """Verifica que un mes no pueda tener dos reportes oficiales."""
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            manager = GestorReportes(
                root / "reportes",
                ProveedorClaveLocal(root / "config" / "report.key"),
            )
            report = self._build_report()
            manager.guardar_reporte(report, "2026-06")

            with self.assertRaises(ReporteDuplicadoError):
                manager.guardar_reporte(report, "2026-06")

    def test_modified_report_is_blocked(self) -> None:
        """Verifica que la alteración de un archivo invalide su apertura."""
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            manager = GestorReportes(
                root / "reportes",
                ProveedorClaveLocal(root / "config" / "report.key"),
            )
            entry = manager.guardar_reporte(
                self._build_report(),
                "2026-06",
            )
            report_path = root / "reportes" / "R2026-06.avr"
            report_path.chmod(0o600)
            report_path.write_bytes(report_path.read_bytes() + b"alterado")

            with self.assertRaises(ReporteInconsistenteError):
                manager.abrir_reporte(entry["id"])

            listed = manager.listar_reportes()

        self.assertEqual(listed[0]["estado"], "Inconsistente")

    def test_local_key_is_reused(self) -> None:
        """Verifica que reiniciar el gestor no cambie la clave local."""
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            key_path = root / "config" / "report.key"
            manager = GestorReportes(
                root / "reportes",
                ProveedorClaveLocal(key_path),
            )
            entry = manager.guardar_reporte(
                self._build_report(),
                "2026-06",
            )
            restarted = GestorReportes(
                root / "reportes",
                ProveedorClaveLocal(key_path),
            )

            opened = restarted.abrir_reporte(entry["id"])

        self.assertEqual(opened["mes"], "2026-06")


class HistoryReliabilityTests(TestCase):
    """Monthly history, diagnostics, validation and backup tests."""

    def test_monthly_history_rejects_duplicate_closure(self) -> None:
        with TemporaryDirectory() as temp_dir:
            history = HistorialFinanciero(
                Path(temp_dir) / "historial_mensual.json"
            )
            history.guardar_snapshot(
                {
                    "mes": "2026-05",
                    "deuda_total": 1_000_000,
                    "patrimonio_neto": -1_000_000,
                    "flujo_libre": 50_000,
                }
            )
            history.guardar_snapshot(
                {
                    "mes": "2026-06",
                    "deuda_total": 900_000,
                    "patrimonio_neto": -800_000,
                    "flujo_libre": 80_000,
                }
            )

            with self.assertRaises(MesYaCerradoError):
                history.guardar_snapshot({"mes": "2026-06"})

            self.assertEqual(
                history.obtener_evolucion_deuda(),
                [("2026-05", 1_000_000), ("2026-06", 900_000)],
            )
            self.assertEqual(
                history.obtener_tendencia("deuda_total"),
                "Bajando",
            )
            self.assertEqual(
                history.obtener_tendencia("patrimonio_neto"),
                "Mejorando",
            )

    def test_snapshot_contains_financial_state(self) -> None:
        budget = MonthlyBudget.empty(2026, 6)
        budget.add_or_update_transaction(
            Transaction(INCOME, "Sueldo", 1_000_000, "2026-06-01")
        )
        budget.add_or_update_transaction(
            Transaction(EXPENSE, "Comida", 100_000, "2026-06-02")
        )
        debt = Debt(
            name="Credito",
            current_balance=500_000,
            current_monthly_payment=100_000,
        )
        manager = GestorDeudas([debt])
        risk = IndiceRiesgoFinanciero().calcular(
            monthly_debt_payment=100_000,
            total_debt=500_000,
            net_income=1_000_000,
            free_cash_flow=900_000,
        )
        snapshot = GeneradorSnapshot.crear(budget, manager, risk, [])

        self.assertEqual(snapshot["mes"], "2026-06")
        self.assertEqual(snapshot["deuda_total"], 500_000)
        self.assertEqual(snapshot["ingresos_reales"], 1_000_000)
        self.assertEqual(snapshot["gastos_reales"], 100_000)
        self.assertEqual(snapshot["flujo_libre"], 900_000)
        self.assertEqual(snapshot["categorias"]["comida"], 100_000)

    def test_snapshot_excludes_credit_cards_from_liquid_assets(self) -> None:
        """Verifica que una tarjeta no infle el patrimonio histórico."""
        budget = MonthlyBudget.empty(2026, 6)
        debt = Debt(name="Crédito", current_balance=500_000)
        manager = GestorDeudas([debt])
        risk = IndiceRiesgoFinanciero().calcular(
            monthly_debt_payment=0,
            total_debt=500_000,
            net_income=0,
            free_cash_flow=0,
        )
        accounts = [
            CuentaFinanciera(
                name="Débito",
                account_type="debito",
                real_balance=100_000,
            ),
            CuentaFinanciera(
                name="Tarjeta",
                account_type="tarjeta_credito",
                real_balance=900_000,
            ),
        ]

        snapshot = GeneradorSnapshot.crear(
            budget,
            manager,
            risk,
            accounts,
        )

        self.assertEqual(snapshot["saldo_cuentas"], 100_000)
        self.assertEqual(snapshot["patrimonio_neto"], -400_000)

    def test_diagnostic_detects_red_and_yellow_alerts(self) -> None:
        budget = MonthlyBudget(
            year=2026,
            month=6,
            categories=[
                CategoryBudget("Otros", EXPENSE, 0, False),
            ],
        )
        budget.add_or_update_transaction(
            Transaction(EXPENSE, "Otros", 100_000, "2026-06-01")
        )
        debt = Debt(
            name="Tarjeta",
            category="tarjeta_credito",
            current_balance=1_000_000,
            previous_month_balance=900_000,
            current_monthly_payment=10_000,
            monthly_interest_rate=0.02,
        )
        alerts = DiagnosticoFinanciero(
            budget,
            GestorDeudas([debt]),
            [],
        ).obtener_alertas()

        levels = {alert.level for alert in alerts}
        messages = " ".join(alert.message for alert in alerts)
        self.assertIn("rojo", levels)
        self.assertIn("amarillo", levels)
        self.assertIn("no cubre el interes", messages)

    def test_input_validations(self) -> None:
        with self.assertRaisesRegex(ValueError, "mayor que cero"):
            validar_movimiento(
                0,
                "Comida",
                "Compra",
                "cuenta-1",
                "Debito",
            )
        with self.assertRaisesRegex(ValueError, "descripcion"):
            validar_movimiento(
                1_000,
                "Comida",
                "",
                "cuenta-1",
                "Debito",
            )
        with self.assertRaisesRegex(ValueError, "cuenta financiera"):
            validar_movimiento(
                1_000,
                "Comida",
                "Compra",
                "",
                "Debito",
            )
        with self.assertRaisesRegex(ValueError, "pago mensual"):
            validar_deuda(100_000, 0, 0, 0)

    def test_startup_backup_contains_required_files_and_retention(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            data_dir = root / "data"
            backup_dir = root / "backup"
            reports_dir = root / "reportes"
            reports_dir.mkdir()
            (reports_dir / "R2026-06.avr").write_bytes(b"cifrado")
            (reports_dir / "index.avridx").write_bytes(b"indice-cifrado")
            (reports_dir / "no_incluir.txt").write_text(
                "texto visible",
                encoding="utf-8",
            )
            repository = BudgetRepository(data_dir)
            repository.save(MonthlyBudget.empty(2026, 6))
            repository.save_debts([])
            repository.save_accounts([])
            history = HistorialFinanciero(
                data_dir / "historial_mensual.json"
            )
            history.guardar_snapshot({"mes": "2026-06"})
            manager = GestorRespaldos(
                data_dir=data_dir,
                backup_dir=backup_dir,
                reports_dir=reports_dir,
                retention=2,
            )

            first = manager.crear_respaldo()
            manager.crear_respaldo()
            latest = manager.crear_respaldo()

            self.assertFalse(first.exists())
            self.assertEqual(len(list(backup_dir.glob("backup_*.zip"))), 2)
            with zipfile.ZipFile(latest) as archive:
                names = set(archive.namelist())
            self.assertTrue(
                {
                    "movimientos.json",
                    "categorias.json",
                    "recurrentes.json",
                    "deudas.json",
                    "cuentas.json",
                    "historial_mensual.json",
                    "reportes/R2026-06.avr",
                    "reportes/index.avridx",
                }.issubset(names)
            )
            self.assertNotIn("reportes/no_incluir.txt", names)


if __name__ == "__main__":
    main()
