"""Debt indicators, projections, simulations, and textual reports."""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date, datetime
from math import ceil
from typing import Any

from avalancha.models import (
    CuentaFinanciera,
    Debt,
    EXPENSE,
    INCOME,
    MonthlyBudget,
)


MAX_PROJECTION_MONTHS = 600


def normalize_monthly_rate(rate: float | int | str | None) -> float:
    """Return a monthly interest value as a decimal rate."""
    if rate in ("", None):
        return 0.0
    try:
        value = float(rate)
    except (TypeError, ValueError):
        return 0.0
    if value <= 0:
        return 0.0
    if value > 1:
        return value / 100
    return value


def add_months(start_date: date, months: int) -> date:
    """Return a date shifted by whole months."""
    month_index = start_date.month - 1 + months
    year = start_date.year + month_index // 12
    month = month_index % 12 + 1
    day = min(start_date.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


@dataclass
class DebtProjection:
    """Projection result for a single debt payment plan."""

    debt_id: str
    months_remaining: int | None
    extinction_date: str | None
    total_paid_estimated: int
    interest_estimated: int
    amortizes: bool
    balance_curve: list[dict[str, Any]]


class ProyectorDeuda:
    """Project payoff dates and balances for debts."""

    def __init__(self, start_date: date | None = None) -> None:
        self.start_date = start_date or date.today()

    def proyectar(
        self,
        debt: Debt,
        payment: int | None = None,
        balance: int | None = None,
        consider_interest: bool = True,
    ) -> DebtProjection:
        """Project payoff of a debt with optional payment override."""
        saldo = max(balance if balance is not None else debt.current_balance, 0)
        pago = payment if payment is not None else debt.current_monthly_payment
        pago = max(int(pago), 0)
        tasa = (
            normalize_monthly_rate(debt.monthly_interest_rate)
            if consider_interest
            else 0.0
        )
        curva: list[dict[str, Any]] = []

        if saldo <= 0:
            return DebtProjection(
                debt_id=debt.debt_id,
                months_remaining=0,
                extinction_date=self.start_date.isoformat(),
                total_paid_estimated=0,
                interest_estimated=0,
                amortizes=True,
                balance_curve=[],
            )

        if pago <= 0:
            return self._no_amortiza(debt.debt_id, curva)

        if tasa <= 0:
            meses = ceil(saldo / pago)
            extinction = add_months(self.start_date, meses)
            return DebtProjection(
                debt_id=debt.debt_id,
                months_remaining=meses,
                extinction_date=extinction.isoformat(),
                total_paid_estimated=saldo,
                interest_estimated=0,
                amortizes=True,
                balance_curve=self._curva_sin_interes(saldo, pago),
            )

        total_pagado = 0
        intereses = 0
        for mes in range(1, MAX_PROJECTION_MONTHS + 1):
            interes_mes = int(round(saldo * tasa))
            if pago <= interes_mes:
                return self._no_amortiza(debt.debt_id, curva)

            saldo += interes_mes
            intereses += interes_mes
            pago_mes = min(pago, saldo)
            saldo -= pago_mes
            total_pagado += pago_mes
            curva.append({"mes": mes, "saldo": max(saldo, 0)})
            if saldo <= 0:
                extinction = add_months(self.start_date, mes)
                return DebtProjection(
                    debt_id=debt.debt_id,
                    months_remaining=mes,
                    extinction_date=extinction.isoformat(),
                    total_paid_estimated=total_pagado,
                    interest_estimated=intereses,
                    amortizes=True,
                    balance_curve=curva,
                )

        return self._no_amortiza(debt.debt_id, curva)

    @staticmethod
    def _curva_sin_interes(balance: int, payment: int) -> list[dict[str, Any]]:
        """Return monthly balance curve without interest."""
        curva = []
        saldo = balance
        mes = 0
        while saldo > 0 and mes < MAX_PROJECTION_MONTHS:
            mes += 1
            saldo = max(saldo - payment, 0)
            curva.append({"mes": mes, "saldo": saldo})
        return curva

    @staticmethod
    def _no_amortiza(
        debt_id: str,
        curve: list[dict[str, Any]],
    ) -> DebtProjection:
        """Return a non-amortizing projection."""
        return DebtProjection(
            debt_id=debt_id,
            months_remaining=None,
            extinction_date=None,
            total_paid_estimated=0,
            interest_estimated=0,
            amortizes=False,
            balance_curve=curve,
        )


class GestorDeudas:
    """Calculate global debt indicators."""

    def __init__(
        self,
        debts: list[Debt],
        payment_totals: dict[str, int] | None = None,
    ) -> None:
        self.debts = debts
        self.payment_totals = payment_totals or {}

    def active_debts(self) -> list[Debt]:
        """Return active debts only."""
        return [debt for debt in self.debts if debt.active]

    def saldo_operativo(self, debt: Debt) -> int:
        """Return current balance reduced by linked payments."""
        paid = self.payment_totals.get(debt.debt_id, 0)
        return max(debt.current_balance - paid, 0)

    def deuda_total_actual(self) -> int:
        """Return total current debt."""
        return sum(self.saldo_operativo(debt) for debt in self.active_debts())

    def deuda_por_categoria(self) -> dict[str, int]:
        """Return current debt by category."""
        totals: dict[str, int] = {}
        for debt in self.active_debts():
            totals[debt.category] = totals.get(debt.category, 0)
            totals[debt.category] += self.saldo_operativo(debt)
        return totals

    def variacion_mensual_deuda(self) -> int:
        """Return previous month total minus current total."""
        previous = sum(debt.previous_month_balance for debt in self.active_debts())
        return previous - self.deuda_total_actual()

    def calcular_pago_mensual_total(self) -> int:
        """Return scheduled monthly debt payments."""
        return sum(debt.current_monthly_payment for debt in self.active_debts())

    def pago_total_deuda_mes(self) -> int:
        """Return scheduled monthly debt payments."""
        return self.calcular_pago_mensual_total()

    def calcular_interes_mensual_estimado(self) -> int:
        """Return estimated monthly interest for active debts."""
        total = 0
        for debt in self.active_debts():
            rate = self._normalized_monthly_rate(debt.monthly_interest_rate)
            if rate <= 0:
                continue
            total += int(round(self.saldo_operativo(debt) * rate))
        return total

    def calcular_amortizacion_neta(self) -> int:
        """Return planned debt payment minus estimated interest."""
        return (
            self.calcular_pago_mensual_total()
            - self.calcular_interes_mensual_estimado()
        )

    def obtener_resumen_deuda(self) -> dict[str, int | bool]:
        """Return priority debt indicators for dashboards and reports."""
        amortization = self.calcular_amortizacion_neta()
        return {
            "pago_mensual_total": self.calcular_pago_mensual_total(),
            "interes_mensual_estimado": (
                self.calcular_interes_mensual_estimado()
            ),
            "amortizacion_neta": amortization,
            "amortizacion_insuficiente": amortization <= 0,
        }

    def pago_acumulado_historico(self) -> int:
        """Return linked historical payments."""
        return sum(self.payment_totals.values())

    def flujo_libre_disponible(self, income: int, expenses: int) -> int:
        """Return free monthly cash flow."""
        return income - expenses

    def porcentaje_ingreso_destinado_a_deuda(self, income: int) -> float:
        """Return percent of income assigned to debt payments."""
        if income <= 0:
            return 0.0
        return round((self.pago_total_deuda_mes() / income) * 100, 1)

    def patrimonio_neto(self, assets: int = 0, emergency_fund: int = 0) -> int:
        """Return simple net worth."""
        return assets + emergency_fund - self.deuda_total_actual()

    @staticmethod
    def porcentaje_avance_fondo_emergencia(
        emergency_fund: int,
        emergency_goal: int,
    ) -> float:
        """Return emergency fund progress percent."""
        if emergency_goal <= 0:
            return 0.0
        return round((emergency_fund / emergency_goal) * 100, 1)

    @staticmethod
    def _normalized_monthly_rate(rate: float | int | str | None) -> float:
        """Return monthly interest as a decimal rate."""
        return normalize_monthly_rate(rate)


class SimuladorFinanciero:
    """Compare debt payoff scenarios."""

    def __init__(self, projector: ProyectorDeuda | None = None) -> None:
        self.projector = projector or ProyectorDeuda()

    def comparar_pagos(
        self,
        debt: Debt,
        payments: list[int],
        balance: int | None = None,
    ) -> list[dict[str, Any]]:
        """Return payoff scenarios for alternative payments."""
        scenarios = []
        for payment in payments:
            projection = self.projector.proyectar(
                debt,
                payment=payment,
                balance=balance,
            )
            scenarios.append(
                {
                    "pago_mensual": payment,
                    "meses_restantes": projection.months_remaining,
                    "fecha_extincion": projection.extinction_date,
                    "total_pagado_estimado": projection.total_paid_estimated,
                    "intereses_estimados": projection.interest_estimated,
                    "amortiza": projection.amortizes,
                }
            )
        return scenarios


class SimuladorPagos:
    """Compare payment scenarios for one debt or all active debts."""

    def __init__(
        self,
        debts: list[Debt],
        payment_totals: dict[str, int] | None = None,
        projector: ProyectorDeuda | None = None,
    ) -> None:
        self.manager = GestorDeudas(debts, payment_totals)
        self.projector = projector or ProyectorDeuda()

    def comparar(
        self,
        possible_payments: list[int],
        debt_id: str | None = None,
        consider_interest: bool = True,
    ) -> list[dict[str, Any]]:
        """Return comparison rows for requested payment scenarios."""
        payments = sorted({int(value) for value in possible_payments if value > 0})
        debts = [
            debt
            for debt in self.manager.active_debts()
            if debt_id is None or debt.debt_id == debt_id
        ]
        scenarios = []
        for debt in debts:
            balance = self.manager.saldo_operativo(debt)
            current = self.projector.proyectar(
                debt,
                balance=balance,
                consider_interest=consider_interest,
            )
            for payment in payments:
                projection = self.projector.proyectar(
                    debt,
                    payment=payment,
                    balance=balance,
                    consider_interest=consider_interest,
                )
                months_gained = self._months_gained(current, projection)
                scenarios.append(
                    {
                        "deuda_id": debt.debt_id,
                        "deuda": debt.name,
                        "pago_mensual": payment,
                        "meses_restantes": projection.months_remaining,
                        "fecha_extincion": projection.extinction_date,
                        "total_pagado_estimado": (
                            projection.total_paid_estimated
                        ),
                        "interes_total_estimado": (
                            projection.interest_estimated
                        ),
                        "meses_ganados_vs_pago_actual": months_gained,
                        "amortiza": projection.amortizes,
                    }
                )
        return scenarios

    @staticmethod
    def _months_gained(
        current: DebtProjection,
        scenario: DebtProjection,
    ) -> int | None:
        """Return payoff months saved against the current payment."""
        if (
            current.months_remaining is None
            or scenario.months_remaining is None
        ):
            return None
        return current.months_remaining - scenario.months_remaining


class GestorConciliacion:
    """Calculate manual account reconciliation indicators."""

    def __init__(self, accounts: list[CuentaFinanciera]) -> None:
        self.accounts = accounts

    def active_accounts(self) -> list[CuentaFinanciera]:
        """Return active financial accounts."""
        return [account for account in self.accounts if account.active]

    def saldo_real_total(self) -> int:
        """Return total manually observed balance."""
        return sum(
            account.real_balance
            for account in self.active_accounts()
            if account.real_balance is not None
        )

    def saldo_registrado_total(self) -> int:
        """Return registered balance for all active accounts."""
        return sum(
            account.registered_balance for account in self.active_accounts()
        )

    def diferencia_total(self) -> int:
        """Return total difference for accounts with a real balance."""
        return sum(
            account.difference
            for account in self.active_accounts()
            if account.difference is not None
        )

    def fecha_ultima_conciliacion(self) -> str | None:
        """Return the most recent reconciliation date."""
        dates = [
            account.reconciliation_date
            for account in self.active_accounts()
            if account.reconciliation_date
        ]
        return max(dates) if dates else None

    def semaforo(self) -> str:
        """Return reconciliation severity color name."""
        difference = abs(self.diferencia_total())
        if difference <= 20_000:
            return "verde"
        if difference <= 100_000:
            return "amarillo"
        return "rojo"

    def recalcular_saldos_registrados(
        self,
        budget: MonthlyBudget,
    ) -> None:
        """Update registered balances from account-linked movements."""
        active_accounts = {
            account.account_id: account
            for account in self.active_accounts()
        }
        income_totals = {account_id: 0 for account_id in active_accounts}
        expense_totals = {account_id: 0 for account_id in active_accounts}
        for transaction in budget.transactions:
            account_id = transaction.account_id
            if account_id not in active_accounts:
                continue
            if transaction.transaction_type == INCOME:
                income_totals[account_id] += transaction.amount
            elif transaction.transaction_type == EXPENSE:
                expense_totals[account_id] += transaction.amount
        for account_id, account in active_accounts.items():
            income = income_totals[account_id]
            expenses = expense_totals[account_id]
            if account.account_type == "tarjeta_credito":
                account.registered_balance = (
                    account.initial_balance + expenses - income
                )
            else:
                account.registered_balance = (
                    account.initial_balance + income - expenses
                )

    def calcular_saldo_base_automatico(
        self,
        budget: MonthlyBudget,
        account_id: str,
        real_balance: int | None,
    ) -> int:
        """Return hidden base balance so a new account starts reconciled."""
        if real_balance is None:
            return 0
        income = 0
        expenses = 0
        for transaction in budget.transactions:
            if transaction.account_id != account_id:
                continue
            if transaction.transaction_type == INCOME:
                income += transaction.amount
            elif transaction.transaction_type == EXPENSE:
                expenses += transaction.amount
        return real_balance - income + expenses

    def cuentas_sin_conciliar(self) -> int:
        """Return active account count without a real balance."""
        return sum(
            account.real_balance is None
            for account in self.active_accounts()
        )

    def obtener_resumen(self) -> dict[str, int | str | None]:
        """Return reconciliation totals and status."""
        return {
            "saldo_real_total": self.saldo_real_total(),
            "saldo_registrado_total": self.saldo_registrado_total(),
            "diferencia_total": self.diferencia_total(),
            "fecha_ultima_conciliacion": (
                self.fecha_ultima_conciliacion()
            ),
            "semaforo": self.semaforo(),
            "cuentas_sin_conciliar": self.cuentas_sin_conciliar(),
        }


class AnalizadorResumen:
    """Calculate actionable monthly indicators for the main dashboard."""

    def __init__(
        self,
        budget: MonthlyBudget,
        accounts: list[CuentaFinanciera] | None = None,
        reference_date: date | None = None,
    ) -> None:
        self.budget = budget
        self.accounts = accounts or []
        self.reference_date = reference_date or date.today()
        self.reconciliation = GestorConciliacion(self.accounts)

    def calcular_pendiente_clasificar(self) -> int:
        """Return real account balance minus registered balance."""
        return self.reconciliation.diferencia_total()

    def semaforo_pendiente(self) -> str:
        """Return reconciliation traffic-light status."""
        return self.reconciliation.semaforo()

    def calcular_recurrentes_pendientes(self) -> int:
        """Return active recurring expenses not yet recorded this month."""
        recorded_ids = {
            transaction.recurring_id
            for transaction in self.budget.transactions
            if transaction.recurring_id
        }
        return sum(
            item.amount
            for item in self.budget.recurring_items
            if (
                item.active
                and item.transaction_type == EXPENSE
                and item.recurring_id not in recorded_ids
            )
        )

    def calcular_resultado_esperado_fin_mes(self) -> int:
        """Return income minus actual and pending recurring expenses."""
        totals = self.budget.totals()
        return (
            totals["income"]
            - totals["expenses"]
            - self.calcular_recurrentes_pendientes()
        )

    def semaforo_resultado_esperado(self) -> str:
        """Return expected-result traffic-light status."""
        result = self.calcular_resultado_esperado_fin_mes()
        if result >= 0:
            return "verde"
        if result >= -50_000:
            return "amarillo"
        return "rojo"

    def obtener_ranking_gastos(self, limit: int = 5) -> list[dict[str, Any]]:
        """Return top expense categories ordered by actual amount."""
        actuals = self.budget.category_actuals(EXPENSE)
        ranking = [
            {"categoria": category, "monto": amount}
            for category, amount in actuals.items()
            if amount > 0
        ]
        ranking.sort(
            key=lambda item: (-item["monto"], item["categoria"].lower())
        )
        return ranking[:max(limit, 0)]

    def calcular_dias_supervivencia(self) -> float | None:
        """Return days supportable with positive real account balances."""
        active_accounts = [
            account
            for account in self.accounts
            if account.active and account.account_type != "tarjeta_credito"
        ]
        if not active_accounts:
            return None
        available = sum(
            account.real_balance
            for account in active_accounts
            if account.real_balance is not None
            and account.real_balance > 0
        )
        if available <= 0:
            return 0.0
        expenses = self.budget.totals()["expenses"]
        day_number = self._elapsed_day()
        daily_average = expenses / day_number if day_number > 0 else 0
        if daily_average <= 0:
            return None
        return round(available / daily_average, 1)

    def texto_dias_supervivencia(self) -> str:
        """Return survival-days text including missing-data states."""
        if not any(account.active for account in self.accounts):
            return "Sin cuentas"
        days = self.calcular_dias_supervivencia()
        if days is None:
            return "Sin datos"
        return f"{days:.1f} dias"

    def semaforo_dias_supervivencia(self) -> str:
        """Return survival-days traffic-light status."""
        days = self.calcular_dias_supervivencia()
        if days is None:
            return "amarillo"
        if days > 20:
            return "verde"
        if days >= 10:
            return "amarillo"
        return "rojo"

    def calcular_estado_financiero_general(
        self,
        risk_level: str = "",
    ) -> dict[str, str]:
        """Return overall monthly financial state and explanation."""
        flow = self.budget.totals()["balance"]
        expected = self.calcular_resultado_esperado_fin_mes()
        pending = abs(self.calcular_pendiente_clasificar())
        normalized_risk = risk_level.strip().lower()

        red = (
            flow < -50_000
            or expected < -50_000
            or pending > 100_000
            or normalized_risk in {"alto", "critico"}
        )
        yellow = (
            flow < 0
            or expected < 0
            or pending > 20_000
            or normalized_risk == "moderado"
        )
        if red:
            return {
                "estado": "Rojo",
                "texto": "Riesgo: deficit o registros inconsistentes.",
            }
        if yellow:
            return {
                "estado": "Amarillo",
                "texto": "Atencion: margen ajustado.",
            }
        return {"estado": "Verde", "texto": "Mes controlado."}

    def _elapsed_day(self) -> int:
        """Return elapsed day for current or historical budget month."""
        if (
            self.reference_date.year == self.budget.year
            and self.reference_date.month == self.budget.month
        ):
            return self.reference_date.day
        return calendar.monthrange(self.budget.year, self.budget.month)[1]


@dataclass
class AlertaDiagnostico:
    """One financial diagnostic alert."""

    level: str
    message: str


class DiagnosticoFinanciero:
    """Generate red and yellow alerts from current financial data."""

    def __init__(
        self,
        budget: MonthlyBudget,
        debt_manager: GestorDeudas,
        accounts: list[CuentaFinanciera],
        reference_date: date | None = None,
    ) -> None:
        self.budget = budget
        self.debt_manager = debt_manager
        self.accounts = accounts
        self.reference_date = reference_date or date.today()

    def obtener_alertas(self) -> list[AlertaDiagnostico]:
        """Return prioritized current financial alerts."""
        alerts: list[AlertaDiagnostico] = []
        totals = self.budget.totals()
        if totals["balance"] < 0:
            alerts.append(
                AlertaDiagnostico("rojo", "El flujo libre es negativo.")
            )
        if self.debt_manager.variacion_mensual_deuda() < 0:
            alerts.append(
                AlertaDiagnostico("rojo", "La deuda total esta aumentando.")
            )
        for debt in self.debt_manager.active_debts():
            interest = int(
                round(
                    self.debt_manager.saldo_operativo(debt)
                    * normalize_monthly_rate(debt.monthly_interest_rate)
                )
            )
            if interest > 0 and debt.current_monthly_payment <= interest:
                alerts.append(
                    AlertaDiagnostico(
                        "rojo",
                        f"El pago de {debt.name} no cubre el interes.",
                    )
                )

        unbudgeted = [
            row["name"]
            for row in self.budget.category_report()
            if row["status"] == "sin presupuesto"
        ]
        if unbudgeted:
            alerts.append(
                AlertaDiagnostico(
                    "amarillo",
                    "Hay gastos sin presupuesto: "
                    + ", ".join(unbudgeted[:3])
                    + ".",
                )
            )
        reconciliation = GestorConciliacion(self.accounts)
        if abs(reconciliation.diferencia_total()) > 20_000:
            alerts.append(
                AlertaDiagnostico(
                    "amarillo",
                    "Existe una diferencia de conciliacion pendiente.",
                )
            )
        if self._has_stale_accounts():
            alerts.append(
                AlertaDiagnostico(
                    "amarillo",
                    "Hay cuentas sin actualizar durante mas de 30 dias.",
                )
            )
        if not alerts:
            return [
                AlertaDiagnostico("verde", "Sin alertas criticas.")
            ]
        order = {"rojo": 0, "amarillo": 1, "verde": 2}
        return sorted(alerts, key=lambda item: order[item.level])

    def _has_stale_accounts(self) -> bool:
        """Return whether an active account is older than 30 days."""
        for account in self.accounts:
            if not account.active:
                continue
            try:
                reconciliation_date = date.fromisoformat(
                    account.reconciliation_date
                )
            except ValueError:
                return True
            if (self.reference_date - reconciliation_date).days > 30:
                return True
        return False


@dataclass
class ResultadoRiesgo:
    """Financial risk score and interpretation."""

    score: int
    level: str
    principal_cause: str
    recommended_action: str
    components: dict[str, float]


class IndiceRiesgoFinanciero:
    """Calculate a transparent financial risk score from 0 to 100."""

    WEIGHTS = {
        "carga_financiera": 0.30,
        "apalancamiento": 0.25,
        "flujo_libre": 0.20,
        "uso_tarjeta": 0.15,
        "fondo_emergencia": 0.10,
    }

    CAUSES = {
        "carga_financiera": (
            "alta carga financiera",
            "reducir pagos no esenciales y evitar nuevos creditos.",
        ),
        "apalancamiento": (
            "deuda alta respecto al ingreso",
            "priorizar amortizacion de capital antes de asumir nueva deuda.",
        ),
        "flujo_libre": (
            "flujo libre insuficiente",
            "ajustar gastos mensuales para recuperar margen disponible.",
        ),
        "uso_tarjeta": (
            "alto uso de tarjeta",
            "priorizar pago de tarjeta antes de tomar nuevos creditos.",
        ),
        "fondo_emergencia": (
            "fondo de emergencia insuficiente",
            "formar gradualmente un fondo para cubrir gastos basicos.",
        ),
    }

    def calcular(
        self,
        monthly_debt_payment: int,
        total_debt: int,
        net_income: int,
        free_cash_flow: int,
        card_balance: int = 0,
        total_card_limit: int = 0,
        emergency_fund: int = 0,
        basic_monthly_expense: int = 0,
    ) -> ResultadoRiesgo:
        """Return weighted risk score and recommendation."""
        components = {
            "carga_financiera": self._ratio_score(
                monthly_debt_payment,
                net_income,
                maximum_ratio=0.50,
            ),
            "apalancamiento": self._ratio_score(
                total_debt,
                net_income,
                maximum_ratio=12.0,
            ),
            "flujo_libre": self._cash_flow_score(
                free_cash_flow,
                net_income,
            ),
            "uso_tarjeta": self._card_use_score(
                card_balance,
                total_card_limit,
            ),
            "fondo_emergencia": self._emergency_score(
                emergency_fund,
                basic_monthly_expense,
            ),
        }
        weighted = {
            name: components[name] * self.WEIGHTS[name]
            for name in self.WEIGHTS
        }
        score = int(round(sum(weighted.values())))
        main_component = max(weighted, key=weighted.get)
        cause, action = self.CAUSES[main_component]
        return ResultadoRiesgo(
            score=max(0, min(score, 100)),
            level=self._level(score),
            principal_cause=cause,
            recommended_action=action,
            components=components,
        )

    @staticmethod
    def _ratio_score(
        numerator: int,
        denominator: int,
        maximum_ratio: float,
    ) -> float:
        if numerator <= 0:
            return 0.0
        if denominator <= 0:
            return 100.0
        ratio = numerator / denominator
        return min(max((ratio / maximum_ratio) * 100, 0.0), 100.0)

    @staticmethod
    def _cash_flow_score(free_cash_flow: int, income: int) -> float:
        if income <= 0:
            return 100.0 if free_cash_flow <= 0 else 50.0
        ratio = free_cash_flow / income
        return min(max(50 - (ratio * 250), 0.0), 100.0)

    @staticmethod
    def _card_use_score(balance: int, total_limit: int) -> float:
        """Return card utilization risk, neutral when limit is unknown."""
        if total_limit <= 0:
            return 0.0
        return min(max((max(balance, 0) / total_limit) * 100, 0.0), 100.0)

    @staticmethod
    def _emergency_score(fund: int, basic_expense: int) -> float:
        if basic_expense <= 0:
            return 0.0
        coverage_months = max(fund, 0) / basic_expense
        return min(max(100 - (coverage_months / 3 * 100), 0.0), 100.0)

    @staticmethod
    def _level(score: int) -> str:
        if score <= 25:
            return "Bajo"
        if score <= 50:
            return "Moderado"
        if score <= 75:
            return "Alto"
        return "Critico"


class RankingDeudas:
    """Order active debts by attack priority."""

    def __init__(
        self,
        debts: list[Debt],
        payment_totals: dict[str, int] | None = None,
    ) -> None:
        self.manager = GestorDeudas(debts, payment_totals)

    def obtener(self) -> list[dict[str, Any]]:
        """Return ranked debts with reason and recommended action."""
        ranked = []
        for debt in self.manager.active_debts():
            balance = self.manager.saldo_operativo(debt)
            rate = normalize_monthly_rate(debt.monthly_interest_rate)
            interest = int(round(balance * rate))
            card_usage = (
                balance / debt.credit_limit
                if debt.credit_limit > 0
                else 0.0
            )
            payment_margin = debt.current_monthly_payment - interest
            score = (
                min(rate / 0.05, 1.0) * 40
                + (20 if debt.category == "tarjeta_credito" else 0)
                + min(card_usage, 1.0) * 20
                + min(balance / 10_000_000, 1.0) * 10
                + (10 if payment_margin <= 0 else 0)
            )
            reasons = self._reasons(
                debt,
                balance,
                rate,
                card_usage,
                payment_margin,
            )
            ranked.append(
                {
                    "deuda_id": debt.debt_id,
                    "nombre": debt.name,
                    "puntaje": round(score, 1),
                    "razon": ", ".join(reasons),
                    "accion_recomendada": self._action(
                        debt,
                        payment_margin,
                    ),
                }
            )
        ranked.sort(key=lambda item: item["puntaje"], reverse=True)
        for position, item in enumerate(ranked, start=1):
            item["posicion"] = position
        return ranked

    @staticmethod
    def _reasons(
        debt: Debt,
        balance: int,
        rate: float,
        card_usage: float,
        payment_margin: int,
    ) -> list[str]:
        reasons = []
        if rate > 0:
            reasons.append(f"interes mensual {rate * 100:.2f}%")
        if debt.category == "tarjeta_credito":
            reasons.append("es tarjeta de credito")
        if card_usage >= 0.70:
            reasons.append("alto uso de cupo")
        if balance >= 1_000_000:
            reasons.append("saldo alto")
        if payment_margin <= 0:
            reasons.append("el pago no cubre el interes")
        if not reasons:
            reasons.append("saldo pendiente")
        return reasons

    @staticmethod
    def _action(debt: Debt, payment_margin: int) -> str:
        if payment_margin <= 0:
            return "Aumentar el pago mensual para comenzar a amortizar."
        if debt.category == "tarjeta_credito":
            return "Aumentar el pago si el flujo libre lo permite."
        return "Mantener el pago y dirigir abonos extra a esta deuda."


class ReporteMensual:
    """Generate concise monthly debt progress text."""

    def __init__(
        self,
        manager: GestorDeudas,
        projections: dict[str, DebtProjection],
    ) -> None:
        self.manager = manager
        self.projections = projections

    def generar(self) -> str:
        """Return monthly debt summary text."""
        variation = self.manager.variacion_mensual_deuda()
        paid = self.manager.pago_total_deuda_mes()
        freedom = self.fecha_libertad_financiera()
        debt_summary = self.manager.obtener_resumen_deuda()
        if variation >= 0:
            change = f"bajo en ${variation:,}".replace(",", ".")
        else:
            change = f"subio en ${abs(variation):,}".replace(",", ".")
        paid_text = f"${paid:,}".replace(",", ".")
        interest_text = self._format_money(
            debt_summary["interes_mensual_estimado"]
        )
        amortization_text = self._format_money(
            debt_summary["amortizacion_neta"]
        )
        warning = (
            " Los pagos actuales no reducen suficientemente la deuda."
            if debt_summary["amortizacion_insuficiente"]
            else ""
        )
        return (
            f"Este mes la deuda total {change}. "
            f"El pago total destinado a deuda fue de {paid_text}. "
            f"De ese monto, aproximadamente {interest_text} corresponde "
            f"a intereses y {amortization_text} reduce efectivamente "
            f"el capital."
            f"{warning} "
            + f"Si mantienes este ritmo, la deuda total se extinguiria en "
            f"{self._format_date(freedom) if freedom else 'sin fecha estimada'}."
        )

    def fecha_libertad_financiera(self) -> str | None:
        """Return the latest projected payoff date among amortizing debts."""
        dates = [
            item.extinction_date
            for item in self.projections.values()
            if item.amortizes and item.extinction_date
        ]
        return max(dates) if dates else None

    @staticmethod
    def _format_date(iso_date: str) -> str:
        """Return DD-MM-YYYY text from an ISO date."""
        return datetime.strptime(iso_date, "%Y-%m-%d").strftime("%d-%m-%Y")

    @staticmethod
    def _format_money(amount: int | bool) -> str:
        """Return CLP text without importing UI helpers."""
        return f"${int(amount):,}".replace(",", ".")
