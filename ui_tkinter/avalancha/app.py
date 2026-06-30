"""Tkinter user interface for Avalancha."""

from __future__ import annotations

import tkinter as tk
import tkinter.font as tkfont
import unicodedata
from datetime import date, datetime
from tkinter import messagebox, simpledialog, ttk
from typing import Any, Callable

from avalancha.formatting import (
    format_clp,
    format_clp_input,
    format_date_for_display,
    parse_clp,
    parse_display_date,
    parse_optional_clp,
)
from avalancha.finanzas import (
    AnalizadorResumen,
    DiagnosticoFinanciero,
    GestorDeudas,
    GestorConciliacion,
    IndiceRiesgoFinanciero,
    ProyectorDeuda,
    RankingDeudas,
    ReporteMensual,
    ResultadoRiesgo,
    SimuladorPagos,
)
from avalancha.gestor_reportes import (
    GestorReportes,
    ProveedorClaveLocal,
    ReporteDuplicadoError,
    ReporteInconsistenteError,
)
from avalancha.historial_financiero import (
    GeneradorSnapshot,
    HistorialFinanciero,
    MesYaCerradoError,
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
    new_id,
)
from avalancha.perfiles import GestorPerfiles, PerfilLocal
from avalancha.storage import BudgetRepository, LEGACY_ACCOUNT_NAME
from avalancha.respaldo import GestorRespaldos
from avalancha.validaciones import validar_deuda, validar_movimiento


BG_COLOR = "#f4f7f7"
PANEL_COLOR = "#ffffff"
TEXT_COLOR = "#1d2528"
MUTED_COLOR = "#657175"
ACCENT_COLOR = "#007c89"
SUCCESS_COLOR = "#16833a"
WARNING_COLOR = "#b7791f"
DANGER_COLOR = "#f97316"
GRID_COLOR = "#d9e1e3"
TK_SCALING = 1.25
FONT_FAMILY = "Segoe UI"
FONT_SIZE_NORMAL = 11
FONT_SIZE_SMALL = 9
FONT_SIZE_TITLE = 20
FONT_SIZE_SUBTITLE = 13
FONT_SIZE_CARD = 15
FONT_SIZE_TABLE = 10
FONT_SIZE_FOOTER = 10
PAD_SMALL = 6
PAD_MEDIUM = 10
PAD_LARGE = 16
TREE_ROW_HEIGHT = 30
WINDOW_SIZE = "1180x820"
WINDOW_MIN_WIDTH = 980
WINDOW_MIN_HEIGHT = 680
BUTTON_PADDING = (PAD_MEDIUM, PAD_SMALL)
STATUS_COLORS = {
    "ok": SUCCESS_COLOR,
    "pagado": SUCCESS_COLOR,
    "programado": ACCENT_COLOR,
    "alerta": WARNING_COLOR,
    "pendiente": WARNING_COLOR,
    "diferencia": WARNING_COLOR,
    "sobrepasado": DANGER_COLOR,
    "sin presupuesto": DANGER_COLOR,
}
DEFAULT_PAYMENT_METHODS = (
    "Debito",
    "Credito",
    "Transferencia",
    "Efectivo",
    "Webpay",
    "Automatico",
    "Otro",
)
DEFAULT_PAYMENT_METHOD = DEFAULT_PAYMENT_METHODS[0]
PAYMENT_METHOD_ALIASES = {
    "debito": "Debito",
    "linea de debito": "Debito",
    "linea debito": "Debito",
    "credito": "Credito",
    "transferencia": "Transferencia",
    "efectivo": "Efectivo",
    "webpay": "Webpay",
    "automatico": "Automatico",
    "otro": "Otro",
}
ACCOUNT_PAYMENT_SUGGESTIONS = {
    "tarjeta_credito": "Credito",
    "debito": "Debito",
    "efectivo": "Efectivo",
}
DEBT_CATEGORY_LABELS = {
    "tarjeta_credito": "Tarjeta credito",
    "credito_consumo": "Credito consumo",
    "deuda_familiar": "Deuda familiar",
    "credito_tercero": "Credito tercero",
    "otra": "Otra",
}
ACCOUNT_TYPE_LABELS = {
    "cuenta_corriente": "Cuenta corriente",
    "debito": "Debito",
    "efectivo": "Efectivo",
    "ahorro": "Ahorro",
    "tarjeta_credito": "Tarjeta credito",
    "otro": "Otro",
}
MONTH_NAMES = (
    "",
    "Enero",
    "Febrero",
    "Marzo",
    "Abril",
    "Mayo",
    "Junio",
    "Julio",
    "Agosto",
    "Septiembre",
    "Octubre",
    "Noviembre",
    "Diciembre",
)


def display_type(transaction_type: str) -> str:
    """Return transaction type for display."""
    return transaction_type.capitalize()


def configurar_escala_tk(root: tk.Tk, escala: float = TK_SCALING) -> None:
    """Configura la escala visual base de Tkinter."""
    root.tk.call("tk", "scaling", escala)


def configurar_fuentes_base(root: tk.Tk) -> None:
    """Ajusta fuentes nombradas de Tk para pantallas HiDPI."""
    fuentes = {
        "TkDefaultFont": FONT_SIZE_NORMAL,
        "TkTextFont": FONT_SIZE_NORMAL,
        "TkFixedFont": FONT_SIZE_NORMAL,
        "TkMenuFont": FONT_SIZE_NORMAL,
        "TkHeadingFont": FONT_SIZE_NORMAL,
        "TkCaptionFont": FONT_SIZE_NORMAL,
        "TkSmallCaptionFont": FONT_SIZE_SMALL,
        "TkIconFont": FONT_SIZE_NORMAL,
        "TkTooltipFont": FONT_SIZE_SMALL,
    }
    for nombre, tamano in fuentes.items():
        try:
            fuente = tkfont.nametofont(nombre)
        except tk.TclError:
            continue
        fuente.configure(family=FONT_FAMILY, size=tamano)


def normalize_option_text(value: str) -> str:
    """Normaliza texto de opciones para comparar valores antiguos."""
    normalized = unicodedata.normalize("NFD", value.strip().casefold())
    return "".join(
        character
        for character in normalized
        if unicodedata.category(character) != "Mn"
    )


def normalize_payment_method(payment_method: str) -> str:
    """Devuelve el medio de pago canonico usado por la interfaz."""
    cleaned = normalize_option_text(payment_method)
    if not cleaned:
        return ""
    return PAYMENT_METHOD_ALIASES.get(cleaned, payment_method.strip())


def suggested_payment_method_for_account(
    account: CuentaFinanciera | None,
) -> str | None:
    """Devuelve el medio sugerido cuando el tipo de cuenta lo define."""
    if account is None:
        return None
    return ACCOUNT_PAYMENT_SUGGESTIONS.get(account.account_type)


def bind_clp_format(
    entry: ttk.Entry,
    variable: tk.StringVar,
    allow_negative: bool = False,
) -> None:
    """Keep a monetary entry formatted with the cursor at the end."""
    formatting = False

    def move_cursor_to_end() -> None:
        if entry.winfo_exists():
            entry.icursor(tk.END)

    def format_value(*_args: object) -> None:
        nonlocal formatting
        if formatting:
            return
        current = variable.get()
        formatted = format_clp_input(current, allow_negative)
        if formatted == current:
            entry.after_idle(move_cursor_to_end)
            return
        formatting = True
        variable.set(formatted)
        formatting = False
        entry.after_idle(move_cursor_to_end)

    variable.trace_add("write", format_value)


def parse_type(display_value: str) -> str:
    """Return normalized transaction type from UI text."""
    return display_value.strip().lower()


def movement_class(transaction: Transaction) -> str:
    """Return a human-readable movement class."""
    if transaction.is_unexpected:
        return "Imprevisto"
    if transaction.recurring_id:
        return "Recurrente"
    return "Normal"


def debt_options(debts: list[Debt]) -> tuple[list[str], dict[str, str]]:
    """Return debt dropdown labels and id lookup."""
    options = [""]
    lookup = {"": ""}
    for debt in sorted(debts, key=lambda item: item.name.lower()):
        if not debt.active:
            continue
        label = f"{debt.name} ({DEBT_CATEGORY_LABELS[debt.category]})"
        options.append(label)
        lookup[label] = debt.debt_id
    return options, lookup


def parse_debt_category(label: str) -> str:
    """Return debt category code from UI label."""
    normalized = label.strip().lower()
    for code, display in DEBT_CATEGORY_LABELS.items():
        if display.lower() == normalized:
            return code
    return "otra"


def parse_account_type(label: str) -> str:
    """Return account type code from UI label."""
    normalized = label.strip().lower()
    for code, display in ACCOUNT_TYPE_LABELS.items():
        if display.lower() == normalized:
            return code
    return "otro"


def display_optional_date(iso_date: str | None) -> str:
    """Return DD-MM-YYYY date text or fallback dash."""
    if not iso_date:
        return "-"
    return format_date_for_display(iso_date)


def payment_method_options(
    budget: MonthlyBudget,
) -> list[str]:
    """Devuelve medios conocidos sin mezclar cuentas financieras."""
    options = list(DEFAULT_PAYMENT_METHODS)
    known = {item.casefold() for item in options}
    used_methods = []
    for item in budget.recurring_items + budget.transactions:
        method = normalize_payment_method(item.payment_method)
        if method and method != "No especificado":
            used_methods.append(method)
    for method in sorted(set(used_methods), key=str.casefold):
        if method.casefold() not in known:
            options.append(method)
            known.add(method.casefold())
    return options


def account_options(
    accounts: list[CuentaFinanciera],
) -> tuple[list[str], dict[str, str]]:
    """Return active account labels and their identifiers."""
    options = [""]
    lookup = {"": ""}
    for account in sorted(accounts, key=lambda item: item.name.casefold()):
        if not account.active:
            continue
        options.append(account.name)
        lookup[account.name] = account.account_id
    return options, lookup


def account_name(
    accounts: list[CuentaFinanciera],
    account_id: str | None,
) -> str:
    """Return an account name for display."""
    for account in accounts:
        if account.account_id == account_id:
            return account.name
    return LEGACY_ACCOUNT_NAME if account_id else ""


def budget_status_summary(budget: MonthlyBudget) -> str:
    """Return short monthly movement totals for the status bar."""
    breakdown = budget.expense_breakdown()
    return (
        f"Recurrentes: {format_clp(breakdown['recurring'])} | "
        f"Imprevistos: {format_clp(breakdown['unexpected'])}"
    )


def calculate_financial_risk(
    budget: MonthlyBudget,
    debt_manager: GestorDeudas,
    accounts: list[CuentaFinanciera],
) -> Any:
    """Return financial risk using the shared application context."""
    totals = budget.totals()
    budgeted = budget.budgeted_totals()
    income = totals["income"] or budgeted["income"]
    basic_expense = sum(
        category.budgeted_amount
        for category in budget.categories
        if category.transaction_type == EXPENSE and category.is_fixed
    )
    if basic_expense <= 0:
        basic_expense = totals["expenses"]
    cards = [
        debt
        for debt in debt_manager.active_debts()
        if debt.category == "tarjeta_credito"
    ]
    card_balance = sum(
        debt_manager.saldo_operativo(debt) for debt in cards
    )
    total_card_limit = sum(debt.credit_limit for debt in cards)
    emergency_fund = sum(
        account.real_balance or 0
        for account in accounts
        if account.active and account.account_type == "ahorro"
    )
    return IndiceRiesgoFinanciero().calcular(
        monthly_debt_payment=debt_manager.calcular_pago_mensual_total(),
        total_debt=debt_manager.deuda_total_actual(),
        net_income=income,
        free_cash_flow=totals["balance"],
        card_balance=card_balance,
        total_card_limit=total_card_limit,
        emergency_fund=emergency_fund,
        basic_monthly_expense=basic_expense,
    )


class Dashboard(ttk.Frame):
    """Monthly summary and charts."""

    def __init__(
        self,
        master: tk.Widget,
        close_month_callback: Callable[[], None],
    ) -> None:
        super().__init__(master)
        self.close_month_callback = close_month_callback
        self.current_budget: MonthlyBudget | None = None
        self.current_analyzer: AnalizadorResumen | None = None
        self.current_history: list[dict[str, Any]] = []
        self.current_diagnostics: list[Any] = []

        self.viewport = tk.Canvas(
            self,
            background=BG_COLOR,
            highlightthickness=0,
        )
        scrollbar = ttk.Scrollbar(
            self,
            orient=tk.VERTICAL,
            command=self.viewport.yview,
        )
        self.viewport.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.viewport.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.content = ttk.Frame(self.viewport)
        self.content_window = self.viewport.create_window(
            (0, 0),
            window=self.content,
            anchor="nw",
        )
        self.content.bind("<Configure>", self._update_scroll_region)
        self.viewport.bind("<Configure>", self._resize_content)
        self.viewport.bind("<Enter>", self._bind_mousewheel)
        self.viewport.bind("<Leave>", self._unbind_mousewheel)

        self.summary = tk.Canvas(
            self.content,
            height=272,
            background=BG_COLOR,
            highlightthickness=0,
        )
        self.summary.pack(fill=tk.X, padx=12, pady=(12, 6))
        self.summary.bind("<Configure>", self._on_summary_resize)

        details = ttk.Frame(self.content)
        details.pack(fill=tk.X, padx=12, pady=(6, 12))
        charts = ttk.Frame(details)
        charts.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.chart = tk.Canvas(
            charts,
            height=180,
            background=PANEL_COLOR,
            highlightthickness=1,
            highlightbackground=GRID_COLOR,
        )
        self.chart.pack(fill=tk.BOTH, expand=True)
        self.chart.bind("<Configure>", self._on_chart_resize)
        self.history_chart = tk.Canvas(
            charts,
            height=110,
            background=PANEL_COLOR,
            highlightthickness=1,
            highlightbackground=GRID_COLOR,
        )
        self.history_chart.pack(fill=tk.X, pady=(8, 0))
        self.history_chart.bind(
            "<Configure>",
            self._on_history_resize,
        )

        sidebar = ttk.Frame(details, width=310)
        sidebar.pack(side=tk.RIGHT, fill=tk.Y, padx=(8, 0))
        sidebar.pack_propagate(False)
        self.expense_ranking = tk.Canvas(
            sidebar,
            width=310,
            height=270,
            background=PANEL_COLOR,
            highlightthickness=1,
            highlightbackground=GRID_COLOR,
        )
        self.expense_ranking.pack(fill=tk.X)
        self.expense_ranking.bind(
            "<Configure>",
            self._on_ranking_resize,
        )
        close_bar = ttk.Frame(sidebar)
        close_bar.pack(side=tk.BOTTOM, fill=tk.X, pady=(8, 0))
        self.close_month_button = ttk.Button(
            close_bar,
            text="Cerrar mes",
            command=self.close_month_callback,
        )
        self.close_month_button.pack(side=tk.RIGHT)
        intelligence = ttk.LabelFrame(
            sidebar,
            text="Tendencias y diagnostico",
        )
        self.intelligence_frame = intelligence
        intelligence.pack(fill=tk.BOTH, expand=True, pady=(8, 0))
        self.intelligence_text = tk.StringVar()
        ttk.Label(
            intelligence,
            textvariable=self.intelligence_text,
            wraplength=280,
            justify=tk.LEFT,
        ).pack(anchor="nw", padx=8, pady=8)

    def _update_scroll_region(self, _event: tk.Event) -> None:
        """Update vertical scrolling bounds after layout changes."""
        required_height = self.content.winfo_reqheight()
        visible_height = self.viewport.winfo_height()
        self.viewport.itemconfigure(
            self.content_window,
            height=max(required_height, visible_height),
        )
        self.viewport.configure(scrollregion=self.viewport.bbox("all"))

    def _resize_content(self, event: tk.Event) -> None:
        """Anchor content at the top and fit the visible viewport."""
        natural_height = self.content.winfo_reqheight()
        self.viewport.itemconfigure(
            self.content_window,
            width=event.width,
            height=max(event.height, natural_height),
        )
        self.viewport.configure(scrollregion=self.viewport.bbox("all"))

    def _on_summary_resize(self, _event: tk.Event) -> None:
        """Redraw summary cards using the final available width."""
        if self.current_budget is None:
            return
        debt_manager = getattr(self, "current_debt_manager", None)
        freedom_date = getattr(self, "current_freedom_date", None)
        risk_level = getattr(self, "current_risk_level", "")
        self._draw_summary(
            self.current_budget,
            debt_manager,
            freedom_date,
            self.current_analyzer,
            risk_level,
        )

    def _bind_mousewheel(self, _event: tk.Event) -> None:
        """Enable wheel scrolling while the pointer is over Resumen."""
        self.viewport.bind_all("<MouseWheel>", self._on_mousewheel)

    def _unbind_mousewheel(self, _event: tk.Event) -> None:
        """Stop capturing the mouse wheel outside Resumen."""
        self.viewport.unbind_all("<MouseWheel>")

    def _on_mousewheel(self, event: tk.Event) -> None:
        """Scroll the dashboard vertically with the mouse wheel."""
        self.viewport.yview_scroll(int(-event.delta / 120), "units")

    def refresh(
        self,
        budget: MonthlyBudget,
        debt_manager: GestorDeudas | None = None,
        freedom_date: str | None = None,
        analyzer: AnalizadorResumen | None = None,
        risk_level: str = "",
        history: list[dict[str, Any]] | None = None,
        trends: dict[str, str] | None = None,
        diagnostics: list[Any] | None = None,
    ) -> None:
        """Redraw dashboard widgets."""
        self.current_budget = budget
        self.current_analyzer = analyzer
        self.current_debt_manager = debt_manager
        self.current_freedom_date = freedom_date
        self.current_risk_level = risk_level
        self.current_history = history or []
        self.current_diagnostics = diagnostics or []
        self._draw_summary(
            budget,
            debt_manager,
            freedom_date,
            analyzer,
            risk_level,
        )
        self._draw_expense_chart(budget)
        self._draw_expense_ranking(analyzer)
        self._draw_history(self.current_history)
        self._draw_intelligence(trends or {}, self.current_diagnostics)

    def _on_chart_resize(self, _event: tk.Event) -> None:
        """Redraw the chart using its final available size."""
        if self.current_budget is not None:
            self._draw_expense_chart(self.current_budget)

    def _on_ranking_resize(self, _event: tk.Event) -> None:
        """Redraw the expense ranking using final available size."""
        self._draw_expense_ranking(self.current_analyzer)

    def _on_history_resize(self, _event: tk.Event) -> None:
        """Redraw historical charts using final available size."""
        self._draw_history(self.current_history)

    def _draw_summary(
        self,
        budget: MonthlyBudget,
        debt_manager: GestorDeudas | None = None,
        freedom_date: str | None = None,
        analyzer: AnalizadorResumen | None = None,
        risk_level: str = "",
    ) -> None:
        self.summary.delete("all")
        totals = budget.totals()
        expense_breakdown = budget.expense_breakdown()
        debt_total = debt_manager.deuda_total_actual() if debt_manager else 0
        variation = (
            debt_manager.variacion_mensual_deuda() if debt_manager else 0
        )
        debt_summary = (
            debt_manager.obtener_resumen_deuda()
            if debt_manager
            else {
                "pago_mensual_total": 0,
                "interes_mensual_estimado": 0,
                "amortizacion_neta": 0,
                "amortizacion_insuficiente": True,
            }
        )
        account_assets = (
            sum(
                account.real_balance or 0
                for account in analyzer.accounts
                if (
                    account.active
                    and account.account_type != "tarjeta_credito"
                )
            )
            if analyzer
            else 0
        )
        net_worth = (
            debt_manager.patrimonio_neto(assets=account_assets)
            if debt_manager
            else account_assets
        )
        variation_color = DANGER_COLOR if variation < 0 else SUCCESS_COLOR
        pending = (
            analyzer.calcular_pendiente_clasificar() if analyzer else 0
        )
        expected = (
            analyzer.calcular_resultado_esperado_fin_mes()
            if analyzer
            else totals["balance"]
        )
        survival = (
            analyzer.texto_dias_supervivencia()
            if analyzer
            else "Sin cuentas"
        )
        state = (
            analyzer.calcular_estado_financiero_general(risk_level)
            if analyzer
            else {"estado": "Verde", "texto": "Mes controlado."}
        )
        indicator_colors = {
            "verde": SUCCESS_COLOR,
            "amarillo": WARNING_COLOR,
            "rojo": DANGER_COLOR,
        }
        pending_color = indicator_colors[
            analyzer.semaforo_pendiente() if analyzer else "verde"
        ]
        expected_color = indicator_colors[
            analyzer.semaforo_resultado_esperado()
            if analyzer
            else "verde"
        ]
        survival_color = indicator_colors[
            analyzer.semaforo_dias_supervivencia()
            if analyzer
            else "amarillo"
        ]
        state_color = indicator_colors[state["estado"].lower()]
        cards = [
            ("Deuda actual", format_clp(debt_total), DANGER_COLOR, ""),
            (
                "Variacion deuda",
                format_clp(variation),
                variation_color,
                "",
            ),
            (
                "Pago mensual deuda",
                format_clp(int(debt_summary["pago_mensual_total"])),
                ACCENT_COLOR,
                "",
            ),
            (
                "Interes mensual est.",
                format_clp(int(debt_summary["interes_mensual_estimado"])),
                WARNING_COLOR,
                "",
            ),
            (
                "Amortizacion neta",
                format_clp(int(debt_summary["amortizacion_neta"])),
                (
                    DANGER_COLOR
                    if debt_summary["amortizacion_insuficiente"]
                    else SUCCESS_COLOR
                ),
                "",
            ),
            ("Flujo libre", format_clp(totals["balance"]), ACCENT_COLOR, ""),
            ("Patrimonio neto", format_clp(net_worth), TEXT_COLOR, ""),
            (
                "Pendiente de clasificar",
                format_clp(pending),
                pending_color,
                "Saldo real menos registrado",
            ),
            (
                "Resultado esperado",
                format_clp(expected),
                expected_color,
                "Incluye recurrentes pendientes",
            ),
            (
                "Dias de supervivencia",
                survival,
                survival_color,
                "Segun saldos reales positivos",
            ),
            (
                "Estado financiero",
                state["estado"],
                state_color,
                state["texto"],
            ),
            (
                "Gastos imprevistos",
                format_clp(expense_breakdown["unexpected"]),
                DANGER_COLOR,
                "Suma de imprevistos del mes",
            ),
        ]

        width = max(self.summary.winfo_width(), 820)
        card_width = (width - 70) / 4
        for index, (title, value, color, subtitle) in enumerate(cards):
            row = index // 4
            column = index % 4
            y0 = 8 + row * 88
            x0 = 12 + column * (card_width + 14)
            x1 = x0 + card_width
            self.summary.create_rectangle(
                x0,
                y0,
                x1,
                y0 + 78,
                fill=PANEL_COLOR,
                outline=GRID_COLOR,
                width=1,
            )
            self.summary.create_text(
                x0 + 16,
                y0 + 19,
                anchor="w",
                fill=MUTED_COLOR,
                font=(FONT_FAMILY, FONT_SIZE_NORMAL),
                text=title,
            )
            self.summary.create_text(
                x0 + 16,
                y0 + 48,
                anchor="w",
                fill=color,
                font=(FONT_FAMILY, FONT_SIZE_CARD, "bold"),
                text=value,
            )
            if subtitle:
                self.summary.create_text(
                    x0 + 16,
                    y0 + 68,
                    anchor="w",
                    fill=MUTED_COLOR,
                    font=(FONT_FAMILY, FONT_SIZE_SMALL),
                    text=subtitle[:40],
                )
    def _draw_expense_chart(self, budget: MonthlyBudget) -> None:
        self.chart.delete("all")
        rows = budget.category_report()
        width = max(self.chart.winfo_width(), 600)
        required_height = max(360, 100 + len(rows) * 24)
        configured_height = int(float(self.chart.cget("height")))
        if configured_height != required_height:
            self.chart.configure(height=required_height)
        height = max(self.chart.winfo_height(), required_height)

        self.chart.create_text(
            20,
            24,
            anchor="w",
            fill=TEXT_COLOR,
            font=(FONT_FAMILY, FONT_SIZE_SUBTITLE, "bold"),
            text="Gasto real vs presupuesto por categoria",
        )

        if not rows:
            self.chart.create_text(
                width / 2,
                height / 2,
                fill=MUTED_COLOR,
                font=(FONT_FAMILY, FONT_SIZE_NORMAL),
                text="Agrega categorias de gasto para ver el grafico.",
            )
            return

        top = 58
        left = 170
        value_x = width - 28
        right = width - 190
        track_width = right - left
        legend_y = height - 30
        available_height = max(legend_y - top - 8, 1)
        row_height = min(30.0, available_height / len(rows))
        bar_height = max(3, min(9, int((row_height - 3) / 2)))
        bar_gap = max(2, int(row_height - (bar_height * 2)))

        for index, row in enumerate(rows):
            y = top + index * row_height
            label_y = y + row_height / 2
            real_y = y + bar_height + bar_gap
            if row["budgeted"] > 0:
                budget_width = track_width
                usage_ratio = min(row["actual"] / row["budgeted"], 1)
                actual_width = int(usage_ratio * track_width)
            elif row["actual"] > 0:
                budget_width = 0
                actual_width = track_width
            else:
                budget_width = 0
                actual_width = 0
            color = STATUS_COLORS.get(row["status"], SUCCESS_COLOR)

            self.chart.create_text(
                20,
                label_y,
                anchor="w",
                fill=TEXT_COLOR,
                font=(FONT_FAMILY, FONT_SIZE_SMALL),
                text=row["name"][:22],
            )
            self.chart.create_rectangle(
                left,
                y,
                right,
                y + bar_height,
                fill="#edf3f4",
                outline="",
            )
            self.chart.create_rectangle(
                left,
                y,
                left + budget_width,
                y + bar_height,
                fill="#9eb8bf",
                outline="",
            )
            self.chart.create_rectangle(
                left,
                real_y,
                left + actual_width,
                real_y + bar_height,
                fill=color,
                outline="",
            )
            self.chart.create_text(
                value_x,
                label_y,
                anchor="e",
                fill=MUTED_COLOR,
                font=(FONT_FAMILY, FONT_SIZE_SMALL),
                text=(
                    f"{format_clp(row['actual'])} / "
                    f"{format_clp(row['budgeted'])}"
                ),
            )

        self.chart.create_rectangle(
            20,
            legend_y,
            38,
            legend_y + 8,
            fill="#9eb8bf",
            outline="",
        )
        self.chart.create_text(
            44,
            legend_y + 4,
            anchor="w",
            fill=MUTED_COLOR,
            font=(FONT_FAMILY, FONT_SIZE_SMALL),
            text="Presupuesto de la categoria",
        )
        self.chart.create_rectangle(
            220,
            legend_y,
            238,
            legend_y + 8,
            fill=ACCENT_COLOR,
            outline="",
        )
        self.chart.create_text(
            244,
            legend_y + 4,
            anchor="w",
            fill=MUTED_COLOR,
            font=(FONT_FAMILY, FONT_SIZE_SMALL),
            text="Real",
        )

    def _draw_expense_ranking(
        self,
        analyzer: AnalizadorResumen | None,
    ) -> None:
        """Draw the five largest expense categories."""
        self.expense_ranking.delete("all")
        width = max(self.expense_ranking.winfo_width(), 280)
        self.expense_ranking.create_text(
            16,
            24,
            anchor="w",
            fill=TEXT_COLOR,
            font=(FONT_FAMILY, FONT_SIZE_SUBTITLE, "bold"),
            text="Principales gastos del mes",
        )
        ranking = analyzer.obtener_ranking_gastos() if analyzer else []
        if not ranking:
            self.expense_ranking.create_text(
                width / 2,
                90,
                fill=MUTED_COLOR,
                font=(FONT_FAMILY, FONT_SIZE_NORMAL),
                text="Sin gastos registrados.",
            )
            return
        for index, item in enumerate(ranking, start=1):
            y = 56 + (index - 1) * 40
            self.expense_ranking.create_text(
                16,
                y,
                anchor="w",
                fill=TEXT_COLOR,
                font=(FONT_FAMILY, FONT_SIZE_SMALL, "bold"),
                text=f"{index}. {item['categoria'][:24]}",
            )
            self.expense_ranking.create_text(
                width - 16,
                y + 18,
                anchor="e",
                fill=ACCENT_COLOR,
                font=(FONT_FAMILY, FONT_SIZE_NORMAL, "bold"),
                text=format_clp(item["monto"]),
            )

    def _draw_history(self, history: list[dict[str, Any]]) -> None:
        """Dibuja la evolución mensual con carriles legibles."""
        self.history_chart.delete("all")
        width = max(self.history_chart.winfo_width(), 600)
        required_height = 230 if len(history) >= 2 else 120
        configured_height = int(float(self.history_chart.cget("height")))
        if configured_height != required_height:
            self.history_chart.configure(height=required_height)
        height = max(self.history_chart.winfo_height(), required_height)
        self.history_chart.create_text(
            14,
            14,
            anchor="w",
            fill=TEXT_COLOR,
            font=(FONT_FAMILY, FONT_SIZE_NORMAL, "bold"),
            text="Evolucion financiera",
        )
        if len(history) < 2:
            self.history_chart.create_text(
                width / 2,
                height / 2 + 8,
                fill=MUTED_COLOR,
                font=(FONT_FAMILY, FONT_SIZE_SMALL),
                text="Se requieren al menos dos cierres mensuales.",
            )
            return

        series = (
            ("Deuda", "deuda_total", DANGER_COLOR),
            ("Patrimonio", "patrimonio_neto", TEXT_COLOR),
            ("Flujo libre", "flujo_libre", ACCENT_COLOR),
        )
        left = 112
        right = width - 140
        value_x = width - 24
        top_area = 42
        lane_height = max((height - top_area - 28) / 3, 52)
        for lane, (label, field, color) in enumerate(series):
            top = top_area + lane * lane_height
            bottom = top + lane_height - 18
            values = [int(item.get(field, 0)) for item in history]
            minimum = min(values)
            maximum = max(values)
            span = maximum - minimum or 1
            center_y = (top + bottom) / 2
            self.history_chart.create_line(
                left,
                center_y,
                right,
                center_y,
                fill="#edf3f4",
            )
            self.history_chart.create_text(
                12,
                center_y,
                anchor="w",
                fill=MUTED_COLOR,
                font=(FONT_FAMILY, FONT_SIZE_SMALL),
                text=label,
            )
            points = []
            for index, value in enumerate(values):
                x = (
                    left
                    if len(values) == 1
                    else left + index * (right - left) / (len(values) - 1)
                )
                y = bottom - ((value - minimum) / span) * (bottom - top)
                points.extend((x, y))
            self.history_chart.create_line(
                *points,
                fill=color,
                width=2,
            )
            for index in (0, len(history) - 1):
                x = left + index * (right - left) / (len(history) - 1)
                value = values[index]
                self.history_chart.create_oval(
                    x - 2,
                    points[index * 2 + 1] - 2,
                    x + 2,
                    points[index * 2 + 1] + 2,
                    fill=color,
                    outline="",
                )
                if lane == 2:
                    self.history_chart.create_text(
                        x,
                        bottom + 7,
                        anchor="center",
                        fill=MUTED_COLOR,
                        font=(FONT_FAMILY, FONT_SIZE_SMALL),
                        text=str(history[index].get("mes", ""))[2:],
                    )
                if index == len(history) - 1:
                    self.history_chart.create_text(
                        value_x,
                        center_y,
                        anchor="e",
                        fill=color,
                        font=(FONT_FAMILY, FONT_SIZE_SMALL, "bold"),
                        text=format_clp(value),
                    )

    def _draw_intelligence(
        self,
        trends: dict[str, str],
        diagnostics: list[Any],
    ) -> None:
        """Display historical trends and prioritized diagnostics."""
        lines = [
            f"Deuda: {trends.get('deuda', 'Sin datos')}",
            f"Patrimonio: {trends.get('patrimonio', 'Sin datos')}",
            f"Flujo libre: {trends.get('flujo', 'Sin datos')}",
            "",
            "Diagnostico financiero:",
        ]
        for alert in diagnostics[:4]:
            prefix = {
                "rojo": "[ROJO]",
                "amarillo": "[AMARILLO]",
                "verde": "[VERDE]",
            }.get(alert.level, "[INFO]")
            lines.append(f"{prefix} {alert.message}")
        self.intelligence_text.set("\n".join(lines))


class TransactionsTab(ttk.Frame):
    """Transaction table and editor."""

    def __init__(
        self,
        master: tk.Widget,
        get_budget: Callable[[], MonthlyBudget],
        get_debts: Callable[[], list[Debt]],
        get_accounts: Callable[[], list[CuentaFinanciera]],
        save_callback: Callable[[], None],
    ) -> None:
        super().__init__(master)
        self.get_budget = get_budget
        self.get_debts = get_debts
        self.get_accounts = get_accounts
        self.save_callback = save_callback
        self.transaction_id = tk.StringVar()
        self.tx_type = tk.StringVar(value=display_type(EXPENSE))
        self.tx_date = tk.StringVar(
            value=format_date_for_display(date.today().isoformat())
        )
        self.category = tk.StringVar()
        self.description = tk.StringVar()
        self.amount = tk.StringVar()
        self.payment_method = tk.StringVar()
        self.account_choice = tk.StringVar()
        self.account_lookup: dict[str, str] = {"": ""}
        self.is_unexpected = tk.BooleanVar(value=False)
        self.recurring_choice = tk.StringVar()
        self.recurring_source_id = tk.StringVar()
        self.debt_choice = tk.StringVar()
        self.debt_lookup: dict[str, str] = {"": ""}
        self.recurring_options: dict[str, RecurringItem] = {}
        self.last_amount_suggestion = ""
        self.last_description_suggestion = ""
        self.last_payment_method_suggestion = DEFAULT_PAYMENT_METHOD

        form = ttk.LabelFrame(self, text="Movimiento")
        form.pack(fill=tk.X, padx=12, pady=12)
        self._build_form(form)

        columns = (
            "date",
            "type",
            "category",
            "description",
            "amount",
            "class",
            "account",
            "payment",
        )
        self.tree = ttk.Treeview(
            self,
            columns=columns,
            show="headings",
            height=12,
        )
        headings = {
            "date": "Fecha",
            "type": "Tipo",
            "category": "Categoria",
            "description": "Descripcion",
            "amount": "Monto",
            "class": "Clase",
            "account": "Cuenta financiera",
            "payment": "Medio de pago",
        }
        widths = {
            "date": 95,
            "type": 80,
            "category": 130,
            "description": 230,
            "amount": 110,
            "class": 100,
            "account": 155,
            "payment": 120,
        }
        for column in columns:
            self.tree.heading(column, text=headings[column])
            self.tree.column(column, width=widths[column], anchor=tk.W)
        self.tree.pack(fill=tk.BOTH, expand=True, padx=12, pady=(0, 12))
        self.tree.bind("<<TreeviewSelect>>", self._on_select)
        self.tx_type.trace_add("write", lambda *_: self.refresh_categories())

    def _build_form(self, form: ttk.LabelFrame) -> None:
        ttk.Label(form, text="Tipo").grid(row=0, column=0, sticky="w", padx=8)
        ttk.Combobox(
            form,
            textvariable=self.tx_type,
            values=[display_type(EXPENSE), display_type(INCOME)],
            state="readonly",
            width=14,
        ).grid(row=1, column=0, sticky="ew", padx=8, pady=(0, 8))

        ttk.Label(form, text="Fecha").grid(row=0, column=1, sticky="w", padx=8)
        ttk.Entry(form, textvariable=self.tx_date, width=14).grid(
            row=1,
            column=1,
            sticky="ew",
            padx=8,
            pady=(0, 8),
        )

        ttk.Label(form, text="Categoria").grid(
            row=0,
            column=2,
            sticky="w",
            padx=8,
        )
        self.category_combo = ttk.Combobox(
            form,
            textvariable=self.category,
            width=18,
            state="readonly",
        )
        self.category_combo.grid(
            row=1,
            column=2,
            sticky="ew",
            padx=8,
            pady=(0, 8),
        )

        ttk.Label(form, text="Monto").grid(row=0, column=3, sticky="w", padx=8)
        amount_entry = ttk.Entry(
            form,
            textvariable=self.amount,
            width=15,
        )
        amount_entry.grid(
            row=1,
            column=3,
            sticky="ew",
            padx=8,
            pady=(0, 8),
        )
        bind_clp_format(amount_entry, self.amount)

        ttk.Label(form, text="Descripcion").grid(
            row=2,
            column=0,
            sticky="w",
            padx=8,
        )
        ttk.Entry(form, textvariable=self.description).grid(
            row=3,
            column=0,
            columnspan=3,
            sticky="ew",
            padx=8,
            pady=(0, 8),
        )

        ttk.Label(form, text="Medio de pago").grid(
            row=2,
            column=3,
            sticky="w",
            padx=8,
        )
        self.payment_method_combo = ttk.Combobox(
            form,
            textvariable=self.payment_method,
            state="readonly",
        )
        self.payment_method_combo.grid(
            row=3,
            column=3,
            sticky="ew",
            padx=8,
            pady=(0, 8),
        )
        ttk.Checkbutton(
            form,
            text="Imprevisto",
            variable=self.is_unexpected,
        ).grid(row=4, column=3, sticky="w", padx=8, pady=(0, 8))

        ttk.Label(form, text="Cuenta financiera").grid(
            row=4,
            column=0,
            sticky="w",
            padx=8,
        )
        self.account_combo = ttk.Combobox(
            form,
            textvariable=self.account_choice,
            state="readonly",
        )
        self.account_combo.grid(
            row=5,
            column=0,
            columnspan=3,
            sticky="ew",
            padx=8,
            pady=(0, 8),
        )

        ttk.Label(form, text="Pago recurrente").grid(
            row=6,
            column=0,
            sticky="w",
            padx=8,
        )
        self.recurring_combo = ttk.Combobox(
            form,
            textvariable=self.recurring_choice,
            width=48,
            state="readonly",
        )
        self.recurring_combo.grid(
            row=7,
            column=0,
            columnspan=2,
            sticky="ew",
            padx=8,
            pady=(0, 8),
        )
        ttk.Label(form, text="Deuda asociada").grid(
            row=6,
            column=2,
            sticky="w",
            padx=8,
        )
        self.debt_combo = ttk.Combobox(
            form,
            textvariable=self.debt_choice,
            state="readonly",
        )
        self.debt_combo.grid(
            row=7,
            column=2,
            columnspan=2,
            sticky="ew",
            padx=8,
            pady=(0, 8),
        )
        self.recurring_combo.bind(
            "<<ComboboxSelected>>",
            self._on_recurring_selected,
        )
        self.category_combo.bind(
            "<<ComboboxSelected>>",
            self._on_category_selected,
        )
        self.category_combo.bind(
            "<FocusOut>",
            self._on_category_selected,
        )
        self.account_combo.bind(
            "<<ComboboxSelected>>",
            self._on_account_selected,
        )

        buttons = ttk.Frame(form)
        buttons.grid(row=1, column=4, rowspan=7, sticky="ns", padx=8)
        ttk.Button(buttons, text="Guardar", command=self.save).pack(
            fill=tk.X,
            pady=(0, 6),
        )
        ttk.Button(buttons, text="Nuevo", command=self.clear).pack(
            fill=tk.X,
            pady=(0, 6),
        )
        ttk.Button(buttons, text="Eliminar", command=self.delete).pack(
            fill=tk.X,
        )

        for column in range(4):
            form.columnconfigure(column, weight=1)

    def refresh(self) -> None:
        """Refresh table and category options."""
        self.refresh_categories()
        self.refresh_payment_methods()
        self.refresh_accounts()
        self.refresh_debts()
        self.tree.delete(*self.tree.get_children())
        for tx in sorted(
            self.get_budget().transactions,
            key=lambda item: (item.tx_date, item.description.lower()),
            reverse=True,
        ):
            self.tree.insert(
                "",
                tk.END,
                iid=tx.transaction_id,
                values=(
                    format_date_for_display(tx.tx_date),
                    display_type(tx.transaction_type),
                    tx.category,
                    tx.description,
                    format_clp(tx.amount),
                    movement_class(tx),
                    account_name(self.get_accounts(), tx.account_id),
                    normalize_payment_method(tx.payment_method),
                ),
            )

    def refresh_categories(self) -> None:
        """Refresh category combobox values."""
        names = self.get_budget().get_category_names(
            parse_type(self.tx_type.get())
        )
        self.category_combo.configure(values=names)
        self._refresh_recurring_options()
        if names and self.category.get() not in names:
            self.category.set(names[0])
            self._suggest_amount_from_category()

    def refresh_payment_methods(self) -> None:
        """Actualiza los medios de pago disponibles."""
        options = payment_method_options(self.get_budget())
        self.payment_method_combo.configure(values=options)
        current = normalize_payment_method(self.payment_method.get())
        if current in options:
            self.payment_method.set(current)
        else:
            self.payment_method.set(DEFAULT_PAYMENT_METHOD)
        self._apply_account_payment_method()

    def refresh_accounts(self) -> None:
        """Actualiza las cuentas financieras activas seleccionables."""
        options, self.account_lookup = account_options(self.get_accounts())
        self.account_combo.configure(values=options)
        if self.account_choice.get() not in options:
            self.account_choice.set("")
        self._apply_account_payment_method()

    def refresh_debts(self) -> None:
        """Refresh debt options."""
        options, self.debt_lookup = debt_options(self.get_debts())
        self.debt_combo.configure(values=options)
        if self.debt_choice.get() not in options:
            self.debt_choice.set("")

    def clear(self) -> None:
        """Reset the editor."""
        self.transaction_id.set("")
        self.tx_type.set(display_type(EXPENSE))
        self.tx_date.set(format_date_for_display(date.today().isoformat()))
        self.description.set("")
        self.amount.set("")
        self.payment_method.set(DEFAULT_PAYMENT_METHOD)
        self.account_choice.set("")
        self.is_unexpected.set(False)
        self.recurring_choice.set("")
        self.recurring_source_id.set("")
        self.debt_choice.set("")
        self.last_amount_suggestion = ""
        self.last_description_suggestion = ""
        self.last_payment_method_suggestion = DEFAULT_PAYMENT_METHOD
        self.refresh_categories()
        self.refresh_payment_methods()
        self.refresh_accounts()
        self.refresh_debts()

    def save(self) -> None:
        """Save a transaction."""
        try:
            category = self.category.get().strip()
            description = self.description.get().strip()
            amount = parse_clp(self.amount.get())
            selected_account_id = self.account_lookup.get(
                self.account_choice.get(),
                "",
            )
            validar_movimiento(
                amount,
                category,
                description,
                selected_account_id,
                normalize_payment_method(self.payment_method.get()),
            )
            transaction_date = parse_display_date(self.tx_date.get())
            transaction = Transaction(
                transaction_id=self.transaction_id.get() or new_id(),
                transaction_type=parse_type(self.tx_type.get()),
                tx_date=transaction_date,
                category=category,
                description=description,
                amount=amount,
                payment_method=normalize_payment_method(
                    self.payment_method.get(),
                ),
                recurring_id=self.recurring_source_id.get() or None,
                is_unexpected=self.is_unexpected.get(),
                debt_id=self.debt_lookup.get(self.debt_choice.get()) or None,
                account_id=selected_account_id,
            )
            self.get_budget().add_or_update_transaction(transaction)
            self.save_callback()
            self.clear()
        except ValueError as exc:
            messagebox.showerror("No se pudo guardar", str(exc))

    def delete(self) -> None:
        """Delete the selected transaction."""
        selected = self.tree.selection()
        if not selected:
            return
        if not messagebox.askyesno(
            "Eliminar movimiento",
            "Eliminar el movimiento seleccionado?",
        ):
            return
        try:
            self.get_budget().delete_transaction(selected[0])
            self.save_callback()
            self.clear()
        except ValueError as exc:
            messagebox.showerror("No se pudo eliminar", str(exc))

    def _on_select(self, _event: tk.Event) -> None:
        selected = self.tree.selection()
        if not selected:
            return
        transaction_id = selected[0]
        for tx in self.get_budget().transactions:
            if tx.transaction_id != transaction_id:
                continue
            self.transaction_id.set(tx.transaction_id)
            self.tx_type.set(display_type(tx.transaction_type))
            self.tx_date.set(format_date_for_display(tx.tx_date))
            self.category.set(tx.category)
            self.description.set(tx.description)
            self.amount.set(str(tx.amount))
            self.payment_method.set(normalize_payment_method(
                tx.payment_method
            ))
            self._set_account_choice(tx.account_id)
            self.is_unexpected.set(tx.is_unexpected)
            self.recurring_source_id.set(tx.recurring_id or "")
            self._set_debt_choice(tx.debt_id)
            self.recurring_choice.set("")
            self.last_amount_suggestion = str(tx.amount)
            self.last_description_suggestion = tx.description
            self.last_payment_method_suggestion = (
                normalize_payment_method(tx.payment_method)
            )
            break

    def _on_category_selected(self, _event: tk.Event) -> None:
        """Keep recurring payment empty until explicitly selected."""
        self.recurring_choice.set("")
        self.recurring_source_id.set("")
        self.debt_choice.set("")
        self._suggest_amount_from_category()

    def _refresh_recurring_options(self) -> None:
        """Refresh recurring payment options for the current type."""
        options = [""]
        self.recurring_options = {}
        for item in sorted(
            self.get_budget().recurring_items,
            key=lambda current: (
                current.transaction_type,
                current.day_of_month,
                current.description.lower(),
            ),
        ):
            if (
                item.transaction_type != parse_type(self.tx_type.get())
                or not item.active
            ):
                continue
            label = (
                f"Dia {item.day_of_month:02d} | {item.description} | "
                f"{item.category} | {format_clp(item.amount)}"
            )
            options.append(label)
            self.recurring_options[label] = item
        self.recurring_combo.configure(values=options)
        if self.recurring_choice.get() not in options:
            self.recurring_choice.set("")

    def _on_recurring_selected(self, _event: tk.Event) -> None:
        """Fill transaction fields from the selected recurring item."""
        item = self.recurring_options.get(self.recurring_choice.get())
        if item is None:
            self.recurring_source_id.set("")
            return
        self._apply_recurring_item(item)

    def _apply_recurring_item(self, item: RecurringItem) -> None:
        """Fill transaction fields from a recurring item."""
        self.tx_type.set(display_type(item.transaction_type))
        self.category.set(item.category)
        self.is_unexpected.set(False)
        if self._can_replace_description():
            self.description.set(item.description)
            self.last_description_suggestion = item.description
        self.amount.set(str(item.amount))
        if self._can_replace_payment_method():
            method = normalize_payment_method(item.payment_method)
            self.payment_method.set(method)
            self.last_payment_method_suggestion = method
        self._set_account_choice(item.account_id)
        self.recurring_source_id.set(item.recurring_id)
        self._set_debt_choice(item.debt_id)
        self.last_amount_suggestion = str(item.amount)

    def _set_debt_choice(self, debt_id: str | None) -> None:
        """Select the debt dropdown label for a debt id."""
        for label, current_id in self.debt_lookup.items():
            if current_id == (debt_id or ""):
                self.debt_choice.set(label)
                return
        self.debt_choice.set("")

    def _set_account_choice(self, account_id: str | None) -> None:
        """Select the account dropdown label for an account id."""
        for label, current_id in self.account_lookup.items():
            if current_id == (account_id or ""):
                self.account_choice.set(label)
                self._apply_account_payment_method()
                return
        self.account_choice.set("")
        self._apply_account_payment_method()

    def _on_account_selected(self, _event: tk.Event) -> None:
        """Ajusta el medio de pago cuando cambia la cuenta."""
        self._apply_account_payment_method(force=True)

    def _selected_account(self) -> CuentaFinanciera | None:
        """Devuelve la cuenta actualmente seleccionada."""
        account_id = self.account_lookup.get(self.account_choice.get(), "")
        for account in self.get_accounts():
            if account.account_id == account_id:
                return account
        return None

    def _apply_account_payment_method(self, force: bool = False) -> None:
        """Sugiere y bloquea el medio si la cuenta ya lo define."""
        suggested = suggested_payment_method_for_account(
            self._selected_account(),
        )
        if suggested is None:
            self.payment_method_combo.configure(state="readonly")
            return
        if force or self.payment_method.get() != suggested:
            self.payment_method.set(suggested)
        self.last_payment_method_suggestion = suggested
        self.payment_method_combo.configure(state="disabled")

    def _suggest_amount_from_category(self) -> None:
        """Suggest category budget as amount when the amount is empty."""
        if not self._can_replace_amount():
            return
        category = self._selected_category_budget()
        if category is None or category.budgeted_amount <= 0:
            return
        suggestion = str(category.budgeted_amount)
        self.amount.set(suggestion)
        self.last_amount_suggestion = suggestion

    def _selected_category_budget(self) -> CategoryBudget | None:
        for category in self.get_budget().categories:
            if (
                category.name == self.category.get()
                and category.transaction_type == parse_type(self.tx_type.get())
            ):
                return category
        return None

    def _can_replace_amount(self) -> bool:
        current = self.amount.get().strip()
        return not current or current == self.last_amount_suggestion

    def _can_replace_description(self) -> bool:
        current = self.description.get().strip()
        return not current or current == self.last_description_suggestion

    def _can_replace_payment_method(self) -> bool:
        current = self.payment_method.get().strip()
        return not current or current == self.last_payment_method_suggestion


class CategoriesTab(ttk.Frame):
    """Category budget table and editor."""

    def __init__(
        self,
        master: tk.Widget,
        get_budget: Callable[[], MonthlyBudget],
        save_callback: Callable[[], None],
    ) -> None:
        super().__init__(master)
        self.get_budget = get_budget
        self.save_callback = save_callback
        self.name = tk.StringVar()
        self.tx_type = tk.StringVar(value=display_type(EXPENSE))
        self.budgeted_amount = tk.StringVar()
        self.is_fixed = tk.BooleanVar(value=False)
        self.alert_threshold = tk.StringVar(value="80")

        form = ttk.LabelFrame(self, text="Categoria y presupuesto")
        form.pack(fill=tk.X, padx=12, pady=12)
        self._build_form(form)
        self.is_fixed.trace_add(
            "write",
            lambda *_: self._refresh_alert_field_state(),
        )
        self._refresh_alert_field_state()

        columns = (
            "type",
            "name",
            "budgeted",
            "actual",
            "remaining",
            "usage",
            "fixed",
            "status",
        )
        self.tree = ttk.Treeview(
            self,
            columns=columns,
            show="headings",
            height=13,
        )
        headings = {
            "type": "Tipo",
            "name": "Categoria",
            "budgeted": "Presup.",
            "actual": "Real",
            "remaining": "Diferencia",
            "usage": "Uso",
            "fixed": "Fija",
            "status": "Estado",
        }
        widths = {
            "type": 80,
            "name": 150,
            "budgeted": 110,
            "actual": 110,
            "remaining": 110,
            "usage": 70,
            "fixed": 60,
            "status": 95,
        }
        for column in columns:
            self.tree.heading(column, text=headings[column])
            self.tree.column(column, width=widths[column], anchor=tk.W)
        self.tree.tag_configure("alerta", foreground=WARNING_COLOR)
        self.tree.tag_configure("pendiente", foreground=WARNING_COLOR)
        self.tree.tag_configure("diferencia", foreground=WARNING_COLOR)
        self.tree.tag_configure("pagado", foreground=SUCCESS_COLOR)
        self.tree.tag_configure("programado", foreground=ACCENT_COLOR)
        self.tree.tag_configure("sobrepasado", foreground=DANGER_COLOR)
        self.tree.tag_configure("sin presupuesto", foreground=DANGER_COLOR)
        self.tree.pack(fill=tk.BOTH, expand=True, padx=12, pady=(0, 12))
        self.tree.bind("<<TreeviewSelect>>", self._on_select)

    def _build_form(self, form: ttk.LabelFrame) -> None:
        ttk.Label(form, text="Tipo").grid(row=0, column=0, sticky="w", padx=8)
        ttk.Combobox(
            form,
            textvariable=self.tx_type,
            values=[display_type(EXPENSE), display_type(INCOME)],
            state="readonly",
            width=14,
        ).grid(row=1, column=0, sticky="ew", padx=8, pady=(0, 8))

        ttk.Label(form, text="Nombre").grid(row=0, column=1, sticky="w", padx=8)
        ttk.Entry(form, textvariable=self.name).grid(
            row=1,
            column=1,
            sticky="ew",
            padx=8,
            pady=(0, 8),
        )

        ttk.Label(form, text="Presupuesto").grid(
            row=0,
            column=2,
            sticky="w",
            padx=8,
        )
        budget_entry = ttk.Entry(
            form,
            textvariable=self.budgeted_amount,
            width=14,
        )
        budget_entry.grid(
            row=1,
            column=2,
            sticky="ew",
            padx=8,
            pady=(0, 8),
        )
        bind_clp_format(budget_entry, self.budgeted_amount)

        self.alert_label = ttk.Label(form, text="Alerta % (variables)")
        self.alert_label.grid(
            row=0,
            column=3,
            sticky="w",
            padx=8,
        )
        self.alert_entry = ttk.Entry(
            form,
            textvariable=self.alert_threshold,
            width=8,
        )
        self.alert_entry.grid(
            row=1,
            column=3,
            sticky="ew",
            padx=8,
            pady=(0, 8),
        )
        ttk.Checkbutton(
            form,
            text="Fija / recurrente",
            variable=self.is_fixed,
        ).grid(row=1, column=4, sticky="w", padx=8, pady=(0, 8))

        buttons = ttk.Frame(form)
        buttons.grid(row=1, column=5, sticky="e", padx=8)
        ttk.Button(buttons, text="Guardar", command=self.save).pack(
            side=tk.LEFT,
            padx=(0, 6),
        )
        ttk.Button(buttons, text="Nuevo", command=self.clear).pack(
            side=tk.LEFT,
            padx=(0, 6),
        )
        ttk.Button(buttons, text="Eliminar", command=self.delete).pack(
            side=tk.LEFT,
        )

        for column in range(2):
            form.columnconfigure(column, weight=1)

    def refresh(self) -> None:
        """Refresh table rows."""
        self.tree.delete(*self.tree.get_children())
        expense_report = {
            row["name"]: row for row in self.get_budget().category_report()
        }
        actual_income = self.get_budget().category_actuals(INCOME)
        for category in sorted(
            self.get_budget().categories,
            key=lambda item: (item.transaction_type, item.name.lower()),
        ):
            if category.transaction_type == EXPENSE:
                report = expense_report.get(category.name, {})
                actual = report.get("actual", 0)
                remaining = report.get("remaining", category.budgeted_amount)
                usage = report.get("usage", 0)
                status = report.get("status", "ok")
                is_fixed = report.get("is_fixed", category.is_fixed)
            else:
                actual = actual_income.get(category.name, 0)
                remaining = actual - category.budgeted_amount
                usage = (
                    round((actual / category.budgeted_amount) * 100, 1)
                    if category.budgeted_amount
                    else 0
                )
                status = "ok"
                is_fixed = category.is_fixed

            iid = self._category_iid(category.name, category.transaction_type)
            self.tree.insert(
                "",
                tk.END,
                iid=iid,
                tags=(status,),
                values=(
                    display_type(category.transaction_type),
                    category.name,
                    format_clp(category.budgeted_amount),
                    format_clp(actual),
                    format_clp(remaining),
                    f"{usage}%",
                    "Si" if is_fixed else "No",
                    status,
                ),
            )

    def clear(self) -> None:
        """Reset editor."""
        self.name.set("")
        self.tx_type.set(display_type(EXPENSE))
        self.budgeted_amount.set("")
        self.is_fixed.set(False)
        self.alert_threshold.set("80")
        self._refresh_alert_field_state()

    def save(self) -> None:
        """Save a category."""
        try:
            category = CategoryBudget(
                name=self.name.get(),
                transaction_type=parse_type(self.tx_type.get()),
                budgeted_amount=parse_clp(self.budgeted_amount.get()),
                is_fixed=self.is_fixed.get(),
                alert_threshold=int(self.alert_threshold.get()),
            )
            self.get_budget().add_or_update_category(category)
            self.get_budget().ensure_recurring_for_category(
                category,
                payment_method=DEFAULT_PAYMENT_METHOD,
            )
            self.save_callback()
        except ValueError as exc:
            messagebox.showerror("No se pudo guardar", str(exc))

    def delete(self) -> None:
        """Delete the selected category."""
        selected = self.tree.selection()
        if not selected:
            return
        values = self.tree.item(selected[0], "values")
        tx_type = parse_type(values[0])
        name = values[1]
        if not messagebox.askyesno(
            "Eliminar categoria",
            f"Eliminar la categoria '{name}'?",
        ):
            return
        try:
            self.get_budget().delete_category(name, tx_type)
            self.save_callback()
            self.clear()
        except ValueError as exc:
            messagebox.showerror("No se pudo eliminar", str(exc))

    def _on_select(self, _event: tk.Event) -> None:
        selected = self.tree.selection()
        if not selected:
            return
        values = self.tree.item(selected[0], "values")
        self.tx_type.set(values[0])
        self.name.set(values[1])
        self.budgeted_amount.set(values[2])
        self.is_fixed.set(values[6] == "Si")
        for category in self.get_budget().categories:
            if (
                category.name == values[1]
                and category.transaction_type == parse_type(values[0])
            ):
                self.alert_threshold.set(str(category.alert_threshold))
                break
        self._refresh_alert_field_state()

    def _refresh_alert_field_state(self) -> None:
        """Enable alert percent only for variable categories."""
        state = "disabled" if self.is_fixed.get() else "normal"
        self.alert_entry.configure(state=state)

    @staticmethod
    def _category_iid(name: str, transaction_type: str) -> str:
        return f"{transaction_type}|{name}"


class RecurringTab(ttk.Frame):
    """Recurring item table and editor."""

    def __init__(
        self,
        master: tk.Widget,
        get_budget: Callable[[], MonthlyBudget],
        get_debts: Callable[[], list[Debt]],
        get_accounts: Callable[[], list[CuentaFinanciera]],
        save_callback: Callable[[], None],
    ) -> None:
        super().__init__(master)
        self.get_budget = get_budget
        self.get_debts = get_debts
        self.get_accounts = get_accounts
        self.save_callback = save_callback
        self.recurring_id = tk.StringVar()
        self.tx_type = tk.StringVar(value=display_type(EXPENSE))
        self.category = tk.StringVar()
        self.description = tk.StringVar()
        self.amount = tk.StringVar()
        self.day = tk.StringVar(value="1")
        self.payment_method = tk.StringVar()
        self.account_choice = tk.StringVar()
        self.account_lookup: dict[str, str] = {"": ""}
        self.debt_choice = tk.StringVar()
        self.debt_lookup: dict[str, str] = {"": ""}
        self.active = tk.BooleanVar(value=True)
        self.last_amount_suggestion = ""

        form = ttk.LabelFrame(self, text="Recurrente mensual")
        form.pack(fill=tk.X, padx=12, pady=12)
        self._build_form(form)

        columns = (
            "active",
            "day",
            "type",
            "category",
            "description",
            "amount",
            "account",
            "payment",
        )
        self.tree = ttk.Treeview(
            self,
            columns=columns,
            show="headings",
            height=12,
        )
        headings = {
            "active": "Activo",
            "day": "Dia",
            "type": "Tipo",
            "category": "Categoria",
            "description": "Descripcion",
            "amount": "Monto",
            "account": "Cuenta financiera",
            "payment": "Medio de pago",
        }
        widths = {
            "active": 65,
            "day": 55,
            "type": 80,
            "category": 130,
            "description": 260,
            "amount": 110,
            "account": 170,
            "payment": 130,
        }
        for column in columns:
            self.tree.heading(column, text=headings[column])
            self.tree.column(column, width=widths[column], anchor=tk.W)
        self.tree.pack(fill=tk.BOTH, expand=True, padx=12, pady=(0, 12))
        self.tree.bind("<<TreeviewSelect>>", self._on_select)
        self.tx_type.trace_add("write", lambda *_: self.refresh_categories())

    def _build_form(self, form: ttk.LabelFrame) -> None:
        ttk.Label(form, text="Tipo").grid(row=0, column=0, sticky="w", padx=8)
        ttk.Combobox(
            form,
            textvariable=self.tx_type,
            values=[display_type(EXPENSE), display_type(INCOME)],
            state="readonly",
            width=14,
        ).grid(row=1, column=0, sticky="ew", padx=8, pady=(0, 8))

        ttk.Label(form, text="Categoria").grid(
            row=0,
            column=1,
            sticky="w",
            padx=8,
        )
        self.category_combo = ttk.Combobox(
            form,
            textvariable=self.category,
            width=18,
            state="readonly",
        )
        self.category_combo.grid(
            row=1,
            column=1,
            sticky="ew",
            padx=8,
            pady=(0, 8),
        )
        self.category_combo.bind(
            "<<ComboboxSelected>>",
            lambda _event: self._suggest_amount_from_category(),
        )

        ttk.Label(form, text="Descripcion").grid(
            row=0,
            column=2,
            sticky="w",
            padx=8,
        )
        ttk.Entry(form, textvariable=self.description).grid(
            row=1,
            column=2,
            sticky="ew",
            padx=8,
            pady=(0, 8),
        )

        ttk.Label(form, text="Monto").grid(row=0, column=3, sticky="w", padx=8)
        amount_entry = ttk.Entry(
            form,
            textvariable=self.amount,
            width=13,
        )
        amount_entry.grid(
            row=1,
            column=3,
            sticky="ew",
            padx=8,
            pady=(0, 8),
        )
        bind_clp_format(amount_entry, self.amount)

        ttk.Label(form, text="Dia").grid(row=0, column=4, sticky="w", padx=8)
        ttk.Entry(form, textvariable=self.day, width=6).grid(
            row=1,
            column=4,
            sticky="ew",
            padx=8,
            pady=(0, 8),
        )

        ttk.Label(form, text="Medio de pago").grid(
            row=2,
            column=0,
            sticky="w",
            padx=8,
        )
        self.payment_method_combo = ttk.Combobox(
            form,
            textvariable=self.payment_method,
            state="readonly",
        )
        self.payment_method_combo.grid(
            row=3,
            column=0,
            columnspan=2,
            sticky="ew",
            padx=8,
            pady=(0, 8),
        )
        ttk.Label(form, text="Cuenta financiera").grid(
            row=2,
            column=2,
            sticky="w",
            padx=8,
        )
        self.account_combo = ttk.Combobox(
            form,
            textvariable=self.account_choice,
            state="readonly",
        )
        self.account_combo.grid(
            row=3,
            column=2,
            sticky="ew",
            padx=8,
            pady=(0, 8),
        )
        self.account_combo.bind(
            "<<ComboboxSelected>>",
            self._on_account_selected,
        )
        ttk.Label(form, text="Deuda asociada").grid(
            row=2,
            column=3,
            sticky="w",
            padx=8,
        )
        self.debt_combo = ttk.Combobox(
            form,
            textvariable=self.debt_choice,
            state="readonly",
        )
        self.debt_combo.grid(
            row=3,
            column=3,
            sticky="ew",
            padx=8,
            pady=(0, 8),
        )
        ttk.Checkbutton(
            form,
            text="Activo",
            variable=self.active,
        ).grid(row=3, column=4, sticky="w", padx=8, pady=(0, 8))

        buttons = ttk.Frame(form)
        buttons.grid(row=4, column=0, columnspan=5, sticky="e", padx=8)
        ttk.Button(buttons, text="Guardar", command=self.save).pack(
            side=tk.LEFT,
            padx=(0, 6),
        )
        ttk.Button(buttons, text="Nuevo", command=self.clear).pack(
            side=tk.LEFT,
            padx=(0, 6),
        )
        ttk.Button(buttons, text="Eliminar", command=self.delete).pack(
            side=tk.LEFT,
            padx=(0, 6),
        )
        ttk.Button(
            buttons,
            text="Crear reales del mes",
            command=self.apply_to_month,
        ).pack(side=tk.LEFT)

        for column in range(5):
            form.columnconfigure(column, weight=1)

    def refresh(self) -> None:
        """Refresh table and category options."""
        self.refresh_categories()
        self.refresh_payment_methods()
        self.refresh_accounts()
        self.refresh_debts()
        self.tree.delete(*self.tree.get_children())
        for item in sorted(
            self.get_budget().recurring_items,
            key=lambda current: (current.day_of_month, current.description),
        ):
            self.tree.insert(
                "",
                tk.END,
                iid=item.recurring_id,
                values=(
                    "Si" if item.active else "No",
                    item.day_of_month,
                    display_type(item.transaction_type),
                    item.category,
                    item.description,
                    format_clp(item.amount),
                    account_name(self.get_accounts(), item.account_id),
                    normalize_payment_method(item.payment_method),
                ),
            )

    def refresh_categories(self) -> None:
        """Refresh category combobox values."""
        names = self.get_budget().get_category_names(
            parse_type(self.tx_type.get())
        )
        self.category_combo.configure(values=names)
        if names and self.category.get() not in names:
            self.category.set(names[0])
            self._suggest_amount_from_category()

    def refresh_payment_methods(self) -> None:
        """Actualiza los medios de pago disponibles."""
        options = payment_method_options(self.get_budget())
        self.payment_method_combo.configure(values=options)
        current = normalize_payment_method(self.payment_method.get())
        if current in options:
            self.payment_method.set(current)
        else:
            self.payment_method.set(DEFAULT_PAYMENT_METHOD)
        self._apply_account_payment_method()

    def refresh_accounts(self) -> None:
        """Actualiza las cuentas financieras activas seleccionables."""
        options, self.account_lookup = account_options(self.get_accounts())
        self.account_combo.configure(values=options)
        if self.account_choice.get() not in options:
            self.account_choice.set("")
        self._apply_account_payment_method()

    def refresh_debts(self) -> None:
        """Refresh debt options."""
        options, self.debt_lookup = debt_options(self.get_debts())
        self.debt_combo.configure(values=options)
        if self.debt_choice.get() not in options:
            self.debt_choice.set("")

    def clear(self) -> None:
        """Reset editor."""
        self.recurring_id.set("")
        self.tx_type.set(display_type(EXPENSE))
        self.description.set("")
        self.amount.set("")
        self.day.set("1")
        self.payment_method.set(DEFAULT_PAYMENT_METHOD)
        self.account_choice.set("")
        self.debt_choice.set("")
        self.active.set(True)
        self.last_amount_suggestion = ""
        self.refresh_categories()
        self.refresh_payment_methods()
        self.refresh_accounts()
        self.refresh_debts()

    def save(self) -> None:
        """Save a recurring item."""
        try:
            selected_account_id = self.account_lookup.get(
                self.account_choice.get(),
                "",
            )
            if not selected_account_id:
                raise ValueError("Debe seleccionar una cuenta financiera.")
            if not self.payment_method.get().strip():
                raise ValueError("Debe seleccionar un medio de pago.")
            item = RecurringItem(
                recurring_id=self.recurring_id.get() or new_id(),
                transaction_type=parse_type(self.tx_type.get()),
                category=self.category.get(),
                description=self.description.get(),
                amount=parse_clp(self.amount.get()),
                day_of_month=int(self.day.get()),
                payment_method=normalize_payment_method(
                    self.payment_method.get(),
                ),
                active=self.active.get(),
                debt_id=self.debt_lookup.get(self.debt_choice.get()) or None,
                account_id=selected_account_id,
            )
            self.get_budget().add_or_update_recurring(item)
            self.get_budget().sync_recurring_item_transaction(item.recurring_id)
            self.save_callback()
            self.clear()
        except ValueError as exc:
            messagebox.showerror("No se pudo guardar", str(exc))

    def delete(self) -> None:
        """Delete the selected recurring item."""
        selected = self.tree.selection()
        if not selected:
            return
        if not messagebox.askyesno(
            "Eliminar recurrente",
            "Eliminar el recurrente seleccionado?",
        ):
            return
        try:
            self.get_budget().delete_recurring(selected[0])
            self.save_callback()
            self.clear()
        except ValueError as exc:
            messagebox.showerror("No se pudo eliminar", str(exc))

    def apply_to_month(self) -> None:
        """Create monthly transactions from recurring items."""
        fallback_account = next(
            (
                account
                for account in self.get_accounts()
                if account.active
                and account.name.casefold() == LEGACY_ACCOUNT_NAME.casefold()
            ),
            None,
        )
        templates_created = 0
        if fallback_account is not None:
            templates_created = (
                self.get_budget().ensure_recurring_for_fixed_expenses(
                    DEFAULT_PAYMENT_METHOD,
                    fallback_account.account_id,
                )
            )
        missing_account = [
            item
            for item in self.get_budget().recurring_items
            if item.active and not item.account_id
        ]
        if missing_account:
            messagebox.showerror(
                "No se pudieron crear movimientos",
                (
                    "Hay pagos recurrentes sin cuenta financiera. "
                    "Edite esos registros antes de continuar."
                ),
            )
            return
        created = self.get_budget().apply_recurring_items()
        self.save_callback()
        messagebox.showinfo(
            "Recurrentes aplicados",
            (
                f"Plantillas creadas: {templates_created}\n"
                f"Movimientos creados: {created}"
            ),
        )

    def _on_select(self, _event: tk.Event) -> None:
        selected = self.tree.selection()
        if not selected:
            return
        recurring_id = selected[0]
        for item in self.get_budget().recurring_items:
            if item.recurring_id != recurring_id:
                continue
            self.recurring_id.set(item.recurring_id)
            self.tx_type.set(display_type(item.transaction_type))
            self.category.set(item.category)
            self.description.set(item.description)
            self.amount.set(str(item.amount))
            self.day.set(str(item.day_of_month))
            self.payment_method.set(normalize_payment_method(
                item.payment_method
            ))
            self._set_account_choice(item.account_id)
            self._set_debt_choice(item.debt_id)
            self.active.set(item.active)
            self.last_amount_suggestion = str(item.amount)
            break

    def _set_debt_choice(self, debt_id: str | None) -> None:
        """Select the debt dropdown label for a debt id."""
        for label, current_id in self.debt_lookup.items():
            if current_id == (debt_id or ""):
                self.debt_choice.set(label)
                return
        self.debt_choice.set("")

    def _set_account_choice(self, account_id: str | None) -> None:
        """Select the account dropdown label for an account id."""
        for label, current_id in self.account_lookup.items():
            if current_id == (account_id or ""):
                self.account_choice.set(label)
                self._apply_account_payment_method()
                return
        self.account_choice.set("")
        self._apply_account_payment_method()

    def _on_account_selected(self, _event: tk.Event) -> None:
        """Ajusta el medio de pago cuando cambia la cuenta."""
        self._apply_account_payment_method(force=True)

    def _selected_account(self) -> CuentaFinanciera | None:
        """Devuelve la cuenta actualmente seleccionada."""
        account_id = self.account_lookup.get(self.account_choice.get(), "")
        for account in self.get_accounts():
            if account.account_id == account_id:
                return account
        return None

    def _apply_account_payment_method(self, force: bool = False) -> None:
        """Sugiere y bloquea el medio si la cuenta ya lo define."""
        suggested = suggested_payment_method_for_account(
            self._selected_account(),
        )
        if suggested is None:
            self.payment_method_combo.configure(state="readonly")
            return
        if force or self.payment_method.get() != suggested:
            self.payment_method.set(suggested)
        self.payment_method_combo.configure(state="disabled")

    def _suggest_amount_from_category(self) -> None:
        """Suggest the category budget as recurring amount."""
        if not self._can_replace_amount():
            return
        for category in self.get_budget().categories:
            if (
                category.name == self.category.get()
                and category.transaction_type == parse_type(self.tx_type.get())
            ):
                if category.budgeted_amount > 0:
                    suggestion = str(category.budgeted_amount)
                    self.amount.set(suggestion)
                    self.last_amount_suggestion = suggestion
                return

    def _can_replace_amount(self) -> bool:
        current = self.amount.get().strip()
        return not current or current == self.last_amount_suggestion


class AccountsTab(ttk.Frame):
    """Manual account reconciliation and financial risk view."""

    def __init__(
        self,
        master: tk.Widget,
        get_accounts: Callable[[], list[CuentaFinanciera]],
        get_budget: Callable[[], MonthlyBudget],
        get_debts: Callable[[], list[Debt]],
        get_payments: Callable[[], dict[str, int]],
        save_callback: Callable[[], None],
    ) -> None:
        super().__init__(master)
        self.get_accounts = get_accounts
        self.get_budget = get_budget
        self.get_debts = get_debts
        self.get_payments = get_payments
        self.save_callback = save_callback
        self.account_id = tk.StringVar()
        self.name = tk.StringVar()
        self.account_type = tk.StringVar(value=ACCOUNT_TYPE_LABELS["debito"])
        self.real_balance = tk.StringVar()
        self.registered_balance = tk.StringVar()
        self.reconciliation_date = tk.StringVar(
            value=format_date_for_display(date.today().isoformat())
        )
        self.active = tk.BooleanVar(value=True)
        self.reconciliation_summary = tk.StringVar()
        self.risk_summary = tk.StringVar()

        form = ttk.LabelFrame(self, text="Cuenta financiera")
        form.pack(fill=tk.X, padx=12, pady=12)
        self._build_form(form)

        columns = (
            "name",
            "type",
            "real",
            "registered",
            "difference",
            "date",
            "active",
        )
        self.tree = ttk.Treeview(
            self,
            columns=columns,
            show="headings",
            height=10,
        )
        headings = {
            "name": "Cuenta",
            "type": "Tipo",
            "real": "Saldo real",
            "registered": "Saldo registrado",
            "difference": "Diferencia",
            "date": "Conciliacion",
            "active": "Activa",
        }
        widths = {
            "name": 180,
            "type": 130,
            "real": 120,
            "registered": 130,
            "difference": 120,
            "date": 110,
            "active": 70,
        }
        for column in columns:
            self.tree.heading(column, text=headings[column])
            self.tree.column(column, width=widths[column], anchor=tk.W)
        self.tree.pack(fill=tk.BOTH, expand=True, padx=12, pady=(0, 8))
        self.tree.bind("<<TreeviewSelect>>", self._on_select)

        reconciliation = ttk.LabelFrame(
            self,
            text="Diferencia por registrar",
        )
        reconciliation.pack(fill=tk.X, padx=12, pady=(0, 8))
        self.reconciliation_label = ttk.Label(
            reconciliation,
            textvariable=self.reconciliation_summary,
            font=(FONT_FAMILY, FONT_SIZE_NORMAL, "bold"),
        )
        self.reconciliation_label.pack(anchor="w", padx=10, pady=8)

        risk = ttk.LabelFrame(self, text="Riesgo financiero")
        risk.pack(fill=tk.X, padx=12, pady=(0, 12))
        ttk.Label(
            risk,
            textvariable=self.risk_summary,
            wraplength=1040,
        ).pack(anchor="w", padx=10, pady=8)

    def _build_form(self, form: ttk.LabelFrame) -> None:
        labels = (
            ("Nombre", self.name),
            ("Tipo", self.account_type),
            ("Saldo real", self.real_balance),
            ("Saldo registrado", self.registered_balance),
            ("Fecha conciliacion", self.reconciliation_date),
        )
        for column, (label, variable) in enumerate(labels):
            ttk.Label(form, text=label).grid(
                row=0,
                column=column,
                sticky="w",
                padx=8,
            )
            if label == "Tipo":
                widget = ttk.Combobox(
                    form,
                    textvariable=variable,
                    values=list(ACCOUNT_TYPE_LABELS.values()),
                    state="readonly",
                )
            else:
                state = "readonly" if label == "Saldo registrado" else "normal"
                widget = ttk.Entry(
                    form,
                    textvariable=variable,
                    state=state,
                )
                if label == "Saldo registrado":
                    self.registered_balance_entry = widget
            widget.grid(
                row=1,
                column=column,
                sticky="ew",
                padx=8,
                pady=(0, 8),
            )
            if label == "Saldo real":
                bind_clp_format(widget, variable, allow_negative=True)
            form.columnconfigure(column, weight=1)

        ttk.Checkbutton(
            form,
            text="Activa",
            variable=self.active,
        ).grid(row=2, column=0, sticky="w", padx=8, pady=(0, 8))
        buttons = ttk.Frame(form)
        buttons.grid(row=2, column=3, columnspan=2, sticky="e", padx=8)
        ttk.Button(buttons, text="Guardar", command=self.save).pack(
            side=tk.LEFT,
            padx=(0, 6),
        )
        ttk.Button(buttons, text="Nuevo", command=self.clear).pack(
            side=tk.LEFT,
            padx=(0, 6),
        )
        ttk.Button(buttons, text="Eliminar", command=self.delete).pack(
            side=tk.LEFT,
        )

    def refresh(self) -> None:
        """Refresh accounts, reconciliation and risk indicators."""
        reconciliation_manager = GestorConciliacion(self.get_accounts())
        reconciliation_manager.recalcular_saldos_registrados(
            self.get_budget()
        )
        self.tree.delete(*self.tree.get_children())
        for account in sorted(
            self.get_accounts(),
            key=lambda item: item.name.lower(),
        ):
            self.tree.insert(
                "",
                tk.END,
                iid=account.account_id,
                values=(
                    account.name,
                    ACCOUNT_TYPE_LABELS[account.account_type],
                    (
                        format_clp(account.real_balance)
                        if account.real_balance is not None
                        else "Sin conciliacion"
                    ),
                    format_clp(account.registered_balance),
                    (
                        format_clp(account.difference)
                        if account.difference is not None
                        else "Sin conciliacion"
                    ),
                    display_optional_date(account.reconciliation_date),
                    "Si" if account.active else "No",
                ),
            )
        reconciliation = reconciliation_manager.obtener_resumen()
        self.reconciliation_summary.set(
            f"Saldo real: {format_clp(reconciliation['saldo_real_total'])} | "
            "Saldo registrado: "
            f"{format_clp(reconciliation['saldo_registrado_total'])} | "
            "Diferencia: "
            f"{format_clp(reconciliation['diferencia_total'])} | "
            "Ultima conciliacion: "
            f"{display_optional_date(reconciliation['fecha_ultima_conciliacion'])}"
            " | Sin conciliar: "
            f"{reconciliation['cuentas_sin_conciliar']}"
        )
        color = {
            "verde": SUCCESS_COLOR,
            "amarillo": WARNING_COLOR,
            "rojo": DANGER_COLOR,
        }[str(reconciliation["semaforo"])]
        self.reconciliation_label.configure(foreground=color)
        self._refresh_risk()

    def _refresh_risk(self) -> None:
        manager = GestorDeudas(self.get_debts(), self.get_payments())
        result = calculate_financial_risk(
            self.get_budget(),
            manager,
            self.get_accounts(),
        )
        self.risk_summary.set(
            f"Riesgo financiero: {result.score}/100 | "
            f"Nivel: {result.level} | "
            f"Principal causa: {result.principal_cause}. "
            f"Accion recomendada: {result.recommended_action}"
        )

    def clear(self) -> None:
        """Reset account editor."""
        selected = self.tree.selection()
        if selected:
            self.tree.selection_remove(selected)
        self.account_id.set("")
        self.name.set("")
        self.account_type.set(ACCOUNT_TYPE_LABELS["debito"])
        self.real_balance.set("")
        self.registered_balance.set("")
        self.reconciliation_date.set(
            format_date_for_display(date.today().isoformat())
        )
        self.active.set(True)

    def save(self) -> None:
        """Add or update a financial account."""
        try:
            accounts = self.get_accounts()
            existing = next(
                (
                    current
                    for current in accounts
                    if current.account_id == self.account_id.get()
                ),
                None,
            )
            name = self.name.get().strip()
            duplicate = next(
                (
                    current
                    for current in accounts
                    if current.name.casefold() == name.casefold()
                    and current.account_id != self.account_id.get()
                ),
                None,
            )
            if duplicate is not None:
                raise ValueError("Ya existe una cuenta con ese nombre.")
            real_balance = parse_optional_clp(self.real_balance.get())
            initial_balance = (
                existing.initial_balance
                if existing is not None
                else 0
            )
            account = CuentaFinanciera(
                account_id=self.account_id.get() or new_id(),
                name=name,
                account_type=parse_account_type(self.account_type.get()),
                initial_balance=initial_balance,
                real_balance=real_balance,
                registered_balance=0,
                reconciliation_date=parse_display_date(
                    self.reconciliation_date.get()
                ),
                active=self.active.get(),
            )
            for index, current in enumerate(accounts):
                if current.account_id == account.account_id:
                    accounts[index] = account
                    break
            else:
                accounts.append(account)
            self.save_callback()
            self.clear()
        except ValueError as exc:
            messagebox.showerror("No se pudo guardar", str(exc))

    def delete(self) -> None:
        """Delete selected financial account after confirmation."""
        selected = self.tree.selection()
        if not selected:
            return
        account_id = selected[0]
        linked_movements = any(
            item.account_id == account_id
            for item in self.get_budget().transactions
        )
        linked_recurring = any(
            item.account_id == account_id
            for item in self.get_budget().recurring_items
        )
        if linked_movements or linked_recurring:
            messagebox.showerror(
                "No se pudo eliminar",
                (
                    "La cuenta tiene movimientos o pagos recurrentes "
                    "asociados. Puede dejarla inactiva."
                ),
            )
            return
        if not messagebox.askyesno(
            "Eliminar cuenta",
            "Eliminar la cuenta seleccionada?",
        ):
            return
        accounts = self.get_accounts()
        accounts[:] = [
            account
            for account in accounts
            if account.account_id != account_id
        ]
        self.save_callback()
        self.clear()

    def _on_select(self, _event: tk.Event) -> None:
        selected = self.tree.selection()
        if not selected:
            return
        account = next(
            (
                item
                for item in self.get_accounts()
                if item.account_id == selected[0]
            ),
            None,
        )
        if account is None:
            return
        self.account_id.set(account.account_id)
        self.name.set(account.name)
        self.account_type.set(ACCOUNT_TYPE_LABELS[account.account_type])
        self.real_balance.set(
            "" if account.real_balance is None else str(account.real_balance)
        )
        self.registered_balance.set(
            format_clp_input(str(account.registered_balance), True)
        )
        self.reconciliation_date.set(
            display_optional_date(account.reconciliation_date)
        )
        self.active.set(account.active)


class ReportsTab(ttk.Frame):
    """Lista y muestra reportes oficiales sin usar aplicaciones externas."""

    def __init__(
        self,
        master: tk.Widget,
        report_manager: GestorReportes,
    ) -> None:
        """Construye el índice visible y el visor interno de solo lectura."""
        super().__init__(master)
        self.report_manager = report_manager

        header = ttk.Frame(self)
        header.pack(fill=tk.X, padx=12, pady=(12, 8))
        ttk.Label(
            header,
            text="Reportes oficiales",
            font=(FONT_FAMILY, FONT_SIZE_SUBTITLE, "bold"),
        ).pack(side=tk.LEFT)
        ttk.Button(
            header,
            text="Exportar reporte",
            state=tk.DISABLED,
        ).pack(side=tk.RIGHT, padx=(8, 0))
        ttk.Button(
            header,
            text="Abrir reporte",
            command=self.open_selected,
        ).pack(side=tk.RIGHT)

        content = ttk.Panedwindow(self, orient=tk.HORIZONTAL)
        content.pack(fill=tk.BOTH, expand=True, padx=12, pady=(0, 12))

        list_frame = ttk.Frame(content, width=370)
        viewer_frame = ttk.LabelFrame(content, text="Vista protegida")
        content.add(list_frame, weight=1)
        content.add(viewer_frame, weight=3)

        columns = ("month", "date", "status")
        self.tree = ttk.Treeview(
            list_frame,
            columns=columns,
            show="headings",
            height=18,
        )
        self.tree.heading("month", text="Mes")
        self.tree.heading("date", text="Fecha")
        self.tree.heading("status", text="Estado")
        self.tree.column("month", width=130, anchor=tk.W)
        self.tree.column("date", width=130, anchor=tk.W)
        self.tree.column("status", width=95, anchor=tk.W)
        self.tree.pack(fill=tk.BOTH, expand=True)
        self.tree.bind("<Double-1>", self._on_double_click)

        scrollbar = ttk.Scrollbar(viewer_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.viewer = tk.Text(
            viewer_frame,
            wrap=tk.WORD,
            state=tk.DISABLED,
            background=PANEL_COLOR,
            foreground=TEXT_COLOR,
            font=("Consolas", 10),
            padx=12,
            pady=12,
            yscrollcommand=scrollbar.set,
        )
        self.viewer.pack(fill=tk.BOTH, expand=True)
        scrollbar.configure(command=self.viewer.yview)

    def refresh(self) -> None:
        """Actualiza el listado desde el índice cifrado."""
        self.tree.delete(*self.tree.get_children())
        try:
            reports = self.report_manager.listar_reportes()
        except ReporteInconsistenteError as exc:
            self._show_text(str(exc))
            return
        for report in reports:
            report_id = str(report.get("id", ""))
            if not report_id:
                continue
            self.tree.insert(
                "",
                tk.END,
                iid=report_id,
                values=(
                    self._display_month(str(report.get("mes", ""))),
                    self._display_datetime(
                        str(report.get("fecha_creacion", ""))
                    ),
                    report.get("estado", "Inconsistente"),
                ),
            )

    def open_selected(self) -> None:
        """Descifra y muestra el reporte seleccionado dentro de Avalancha."""
        selected = self.tree.selection()
        if not selected:
            return
        try:
            report = self.report_manager.abrir_reporte(selected[0])
        except (ReporteInconsistenteError, ValueError) as exc:
            messagebox.showerror("No se pudo abrir el reporte", str(exc))
            self.refresh()
            return
        self._show_text(self._render_report(report))

    def _on_double_click(self, _event: tk.Event) -> None:
        """Abre el reporte al hacer doble clic sobre el índice."""
        self.open_selected()

    def _show_text(self, content: str) -> None:
        """Reemplaza el contenido del visor manteniéndolo bloqueado."""
        self.viewer.configure(state=tk.NORMAL)
        self.viewer.delete("1.0", tk.END)
        self.viewer.insert("1.0", content)
        self.viewer.configure(state=tk.DISABLED)

    @staticmethod
    def _render_report(report: dict[str, Any]) -> str:
        """Renderiza el objeto descifrado únicamente para el visor interno."""
        lines = [
            str(line)
            for line in report.get("encabezado", [])
        ]
        for section in report.get("secciones", []):
            if not isinstance(section, dict):
                continue
            lines.extend(("", str(section.get("titulo", ""))))
            lines.extend(
                str(line) for line in section.get("lineas", [])
            )
        return "\n".join(lines)

    @staticmethod
    def _display_month(label: str) -> str:
        """Convierte YYYY-MM en un nombre de mes legible."""
        try:
            year_text, month_text = label.split("-", 1)
            return f"{MONTH_NAMES[int(month_text)]} {int(year_text)}"
        except (ValueError, IndexError):
            return label or "Sin datos"

    @staticmethod
    def _display_datetime(value: str) -> str:
        """Convierte una fecha ISO en texto local de fecha y hora."""
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError:
            return "Sin datos"
        return parsed.strftime("%d-%m-%Y %H:%M")


class DebtsTab(ttk.Frame):
    """Debt tracker with historical payment balance."""

    def __init__(
        self,
        master: tk.Widget,
        get_debts: Callable[[], list[Debt]],
        get_payments: Callable[[], dict[str, int]],
        save_callback: Callable[[], None],
    ) -> None:
        super().__init__(master)
        self.get_debts = get_debts
        self.get_payments = get_payments
        self.save_callback = save_callback
        self.debt_id = tk.StringVar()
        self.category = tk.StringVar(value=DEBT_CATEGORY_LABELS["otra"])
        self.name = tk.StringVar()
        self.current_balance = tk.StringVar()
        self.previous_balance = tk.StringVar()
        self.monthly_payment = tk.StringVar()
        self.minimum_payment = tk.StringVar()
        self.interest_rate = tk.StringVar()
        self.credit_limit = tk.StringVar()
        self.simulation_payments = tk.StringVar(value="")
        self.report_text = tk.StringVar(value="")
        self.consider_interest = tk.BooleanVar(value=True)
        self.simulate_all = tk.BooleanVar(value=False)
        self.active = tk.BooleanVar(value=True)

        form = ttk.LabelFrame(self, text="Credito o tarjeta")
        form.pack(fill=tk.X, padx=12, pady=12)
        self._build_form(form)

        columns = (
            "category",
            "name",
            "current",
            "previous",
            "variation",
            "paid",
            "monthly",
            "months",
            "extinction",
            "active",
        )
        self.tree = ttk.Treeview(
            self,
            columns=columns,
            show="headings",
            height=5,
        )
        headings = {
            "category": "Categoria",
            "name": "Nombre",
            "current": "Saldo actual",
            "previous": "Saldo mes ant.",
            "variation": "Disminucion",
            "paid": "Pagado",
            "monthly": "Pago mensual",
            "months": "Meses",
            "extinction": "Extincion",
            "active": "Activo",
        }
        widths = {
            "category": 110,
            "name": 145,
            "current": 100,
            "previous": 100,
            "variation": 95,
            "paid": 85,
            "monthly": 95,
            "months": 60,
            "extinction": 90,
            "active": 55,
        }
        for column in columns:
            self.tree.heading(column, text=headings[column])
            self.tree.column(column, width=widths[column], anchor=tk.W)
        self.tree.pack(fill=tk.BOTH, expand=True, padx=12, pady=(0, 12))
        self.tree.bind("<<TreeviewSelect>>", self._on_select)

        simulation = ttk.LabelFrame(self, text="Simulador de pagos")
        simulation.pack(fill=tk.X, padx=12, pady=(0, 8))
        controls = ttk.Frame(simulation)
        controls.pack(fill=tk.X, padx=8, pady=6)
        ttk.Label(controls, text="Pagos separados por coma").pack(
            side=tk.LEFT,
        )
        ttk.Entry(
            controls,
            textvariable=self.simulation_payments,
            width=28,
        ).pack(side=tk.LEFT, padx=6)
        ttk.Checkbutton(
            controls,
            text="Considerar interes",
            variable=self.consider_interest,
        ).pack(side=tk.LEFT, padx=6)
        ttk.Checkbutton(
            controls,
            text="Todas las deudas",
            variable=self.simulate_all,
        ).pack(side=tk.LEFT, padx=6)
        ttk.Button(
            controls,
            text="Simular",
            command=self.simulate_selected,
        ).pack(side=tk.RIGHT)
        simulation_columns = (
            "debt",
            "payment",
            "months",
            "date",
            "total",
            "interest",
            "gained",
        )
        self.simulation_tree = ttk.Treeview(
            simulation,
            columns=simulation_columns,
            show="headings",
            height=3,
        )
        simulation_headings = {
            "debt": "Deuda",
            "payment": "Pago",
            "months": "Meses",
            "date": "Extincion",
            "total": "Total estimado",
            "interest": "Intereses",
            "gained": "Meses ganados",
        }
        for column in simulation_columns:
            self.simulation_tree.heading(
                column,
                text=simulation_headings[column],
            )
            self.simulation_tree.column(
                column,
                width=135 if column == "debt" else 100,
                anchor=tk.W,
            )
        self.simulation_tree.pack(
            fill=tk.X,
            padx=8,
            pady=(0, 8),
        )

        ranking = ttk.LabelFrame(self, text="Prioridad de ataque")
        ranking.pack(fill=tk.X, padx=12, pady=(0, 8))
        ranking_columns = ("position", "name", "reason", "action")
        self.ranking_tree = ttk.Treeview(
            ranking,
            columns=ranking_columns,
            show="headings",
            height=2,
        )
        ranking_headings = {
            "position": "#",
            "name": "Deuda",
            "reason": "Razon",
            "action": "Accion recomendada",
        }
        ranking_widths = {
            "position": 40,
            "name": 170,
            "reason": 360,
            "action": 380,
        }
        for column in ranking_columns:
            self.ranking_tree.heading(column, text=ranking_headings[column])
            self.ranking_tree.column(
                column,
                width=ranking_widths[column],
                anchor=tk.W,
            )
        self.ranking_tree.pack(fill=tk.X, padx=8, pady=8)

        footer = ttk.Frame(self)
        footer.pack(fill=tk.X, padx=12, pady=(0, 12))
        ttk.Label(
            footer,
            textvariable=self.report_text,
            foreground=MUTED_COLOR,
            wraplength=1060,
        ).pack(side=tk.LEFT, fill=tk.X, expand=True)

    def _build_form(self, form: ttk.LabelFrame) -> None:
        ttk.Label(form, text="Categoria").grid(
            row=0,
            column=0,
            sticky="w",
            padx=8,
        )
        ttk.Combobox(
            form,
            textvariable=self.category,
            values=list(DEBT_CATEGORY_LABELS.values()),
            state="readonly",
        ).grid(row=1, column=0, sticky="ew", padx=8, pady=(0, 8))

        ttk.Label(form, text="Nombre").grid(row=0, column=1, sticky="w", padx=8)
        ttk.Entry(form, textvariable=self.name).grid(
            row=1,
            column=1,
            sticky="ew",
            padx=8,
            pady=(0, 8),
        )

        ttk.Label(form, text="Saldo actual").grid(
            row=0,
            column=2,
            sticky="w",
            padx=8,
        )
        current_balance_entry = ttk.Entry(
            form,
            textvariable=self.current_balance,
        )
        current_balance_entry.grid(
            row=1,
            column=2,
            sticky="ew",
            padx=8,
            pady=(0, 8),
        )
        bind_clp_format(current_balance_entry, self.current_balance)
        ttk.Label(form, text="Saldo mes ant.").grid(
            row=0,
            column=3,
            sticky="w",
            padx=8,
        )
        previous_balance_entry = ttk.Entry(
            form,
            textvariable=self.previous_balance,
        )
        previous_balance_entry.grid(
            row=1,
            column=3,
            sticky="ew",
            padx=8,
            pady=(0, 8),
        )
        bind_clp_format(previous_balance_entry, self.previous_balance)
        ttk.Label(form, text="Pago mensual").grid(
            row=2,
            column=0,
            sticky="w",
            padx=8,
        )
        monthly_payment_entry = ttk.Entry(
            form,
            textvariable=self.monthly_payment,
        )
        monthly_payment_entry.grid(
            row=3,
            column=0,
            sticky="ew",
            padx=8,
            pady=(0, 8),
        )
        bind_clp_format(monthly_payment_entry, self.monthly_payment)
        ttk.Label(form, text="Pago minimo").grid(
            row=2,
            column=1,
            sticky="w",
            padx=8,
        )
        minimum_payment_entry = ttk.Entry(
            form,
            textvariable=self.minimum_payment,
        )
        minimum_payment_entry.grid(
            row=3,
            column=1,
            sticky="ew",
            padx=8,
            pady=(0, 8),
        )
        bind_clp_format(minimum_payment_entry, self.minimum_payment)
        ttk.Label(form, text="Interes mensual").grid(
            row=2,
            column=2,
            sticky="w",
            padx=8,
        )
        ttk.Entry(form, textvariable=self.interest_rate).grid(
            row=3,
            column=2,
            sticky="ew",
            padx=8,
            pady=(0, 8),
        )
        ttk.Label(form, text="Cupo total tarjeta").grid(
            row=2,
            column=3,
            sticky="w",
            padx=8,
        )
        credit_limit_entry = ttk.Entry(
            form,
            textvariable=self.credit_limit,
        )
        credit_limit_entry.grid(
            row=3,
            column=3,
            sticky="ew",
            padx=8,
            pady=(0, 8),
        )
        bind_clp_format(credit_limit_entry, self.credit_limit)
        ttk.Checkbutton(
            form,
            text="Activo",
            variable=self.active,
        ).grid(row=4, column=0, sticky="w", padx=8, pady=(0, 8))

        buttons = ttk.Frame(form)
        buttons.grid(
            row=4,
            column=1,
            columnspan=3,
            sticky="e",
            padx=8,
        )
        ttk.Button(buttons, text="Guardar", command=self.save).pack(
            side=tk.LEFT,
            padx=(0, 6),
        )
        ttk.Button(buttons, text="Nuevo", command=self.clear).pack(
            side=tk.LEFT,
        )

        for column in range(4):
            form.columnconfigure(column, weight=1)

    def refresh(self) -> None:
        """Refresh debt table."""
        self.tree.delete(*self.tree.get_children())
        payments = self.get_payments()
        manager = GestorDeudas(self.get_debts(), payments)
        projector = ProyectorDeuda()
        projections = {}
        for debt in sorted(self.get_debts(), key=lambda item: item.name.lower()):
            paid = payments.get(debt.debt_id, 0)
            balance = manager.saldo_operativo(debt)
            variation = debt.previous_month_balance - balance
            projection = projector.proyectar(debt, balance=balance)
            projections[debt.debt_id] = projection
            months = (
                str(projection.months_remaining)
                if projection.months_remaining is not None
                else "No amortiza"
            )
            self.tree.insert(
                "",
                tk.END,
                iid=debt.debt_id,
                values=(
                    DEBT_CATEGORY_LABELS[debt.category],
                    debt.name,
                    format_clp(balance),
                    format_clp(debt.previous_month_balance),
                    format_clp(variation),
                    format_clp(paid),
                    format_clp(debt.current_monthly_payment),
                    months,
                    display_optional_date(projection.extinction_date),
                    "Si" if debt.active else "No",
                ),
            )
        self.ranking_tree.delete(*self.ranking_tree.get_children())
        for row in RankingDeudas(self.get_debts(), payments).obtener():
            self.ranking_tree.insert(
                "",
                tk.END,
                values=(
                    row["posicion"],
                    row["nombre"],
                    row["razon"],
                    row["accion_recomendada"],
                ),
            )
        self.report_text.set(ReporteMensual(manager, projections).generar())

    def clear(self) -> None:
        """Reset editor."""
        if hasattr(self, "tree"):
            selected = self.tree.selection()
            if selected:
                self.tree.selection_remove(selected)
        self.debt_id.set("")
        self.category.set(DEBT_CATEGORY_LABELS["otra"])
        self.name.set("")
        self.current_balance.set("")
        self.previous_balance.set("")
        self.monthly_payment.set("")
        self.minimum_payment.set("")
        self.interest_rate.set("")
        self.credit_limit.set("")
        if hasattr(self, "simulation_tree"):
            self.simulation_tree.delete(
                *self.simulation_tree.get_children()
            )
        self.active.set(True)

    def save(self) -> None:
        """Save debt definition."""
        try:
            current_balance = parse_clp(self.current_balance.get())
            monthly_payment = parse_clp(self.monthly_payment.get())
            minimum_payment = parse_clp(self.minimum_payment.get())
            interest_rate = self._parse_interest_rate()
            validar_deuda(
                current_balance,
                monthly_payment,
                minimum_payment,
                interest_rate,
            )
            debt = Debt(
                debt_id=self.debt_id.get() or new_id(),
                name=self.name.get(),
                category=parse_debt_category(self.category.get()),
                current_balance=current_balance,
                previous_month_balance=parse_clp(self.previous_balance.get()),
                current_monthly_payment=monthly_payment,
                minimum_payment=minimum_payment,
                monthly_interest_rate=interest_rate,
                credit_limit=parse_clp(self.credit_limit.get()),
                active=self.active.get(),
            )
            debts = self.get_debts()
            for index, current in enumerate(debts):
                if current.debt_id == debt.debt_id:
                    debts[index] = debt
                    break
            else:
                debts.append(debt)
            self.save_callback()
            self.clear()
        except ValueError as exc:
            messagebox.showerror("No se pudo guardar", str(exc))

    def simulate_selected(self) -> None:
        """Run payment scenarios for the selected debt."""
        selected = self.tree.selection()
        if not selected and not self.simulate_all.get():
            messagebox.showinfo("Simulacion", "Selecciona una deuda primero.")
            return
        debt_id = None if self.simulate_all.get() else selected[0]
        try:
            payments = [
                parse_clp(item)
                for item in self.simulation_payments.get().split(",")
                if item.strip()
            ]
        except ValueError as exc:
            messagebox.showerror("No se pudo simular", str(exc))
            return
        if not payments:
            messagebox.showinfo(
                "Simulacion",
                "Ingresa uno o mas pagos separados por coma.",
            )
            return

        scenarios = SimuladorPagos(
            self.get_debts(),
            self.get_payments(),
        ).comparar(
            payments,
            debt_id=debt_id,
            consider_interest=self.consider_interest.get(),
        )
        self.simulation_tree.delete(*self.simulation_tree.get_children())
        for scenario in scenarios:
            months = scenario["meses_restantes"]
            date_text = (
                display_optional_date(scenario["fecha_extincion"])
                if scenario["fecha_extincion"]
                else "no amortiza"
            )
            gained = scenario["meses_ganados_vs_pago_actual"]
            self.simulation_tree.insert(
                "",
                tk.END,
                values=(
                    scenario["deuda"],
                    format_clp(scenario["pago_mensual"]),
                    months if months is not None else "No amortiza",
                    date_text,
                    format_clp(scenario["total_pagado_estimado"]),
                    format_clp(scenario["interes_total_estimado"]),
                    gained if gained is not None else "-",
                ),
            )

    def _parse_interest_rate(self) -> float | None:
        """Parse optional monthly interest rate from UI."""
        text = self.interest_rate.get().strip().replace(",", ".")
        if not text:
            return None
        value = float(text)
        if value > 1:
            value = value / 100
        return value

    def _on_select(self, _event: tk.Event) -> None:
        selected = self.tree.selection()
        if not selected:
            return
        debt_id = selected[0]
        for debt in self.get_debts():
            if debt.debt_id != debt_id:
                continue
            self.debt_id.set(debt.debt_id)
            self.category.set(DEBT_CATEGORY_LABELS[debt.category])
            self.name.set(debt.name)
            self.current_balance.set(str(debt.current_balance))
            self.previous_balance.set(str(debt.previous_month_balance))
            self.monthly_payment.set(str(debt.current_monthly_payment))
            self.minimum_payment.set(str(debt.minimum_payment))
            self.interest_rate.set(
                "" if debt.monthly_interest_rate is None
                else str(debt.monthly_interest_rate)
            )
            self.credit_limit.set(str(debt.credit_limit or ""))
            self.active.set(debt.active)
            break


class AvalanchaApp(tk.Tk):
    """Main Tk application."""

    def __init__(self) -> None:
        super().__init__()
        configurar_escala_tk(self)
        configurar_fuentes_base(self)
        self.title("Avalancha - Presupuesto mensual")
        self.geometry(WINDOW_SIZE)
        self.minsize(WINDOW_MIN_WIDTH, WINDOW_MIN_HEIGHT)
        self.configure(background=BG_COLOR)

        self.profile_manager = GestorPerfiles()
        self.active_profile = self.profile_manager.obtener_activo()
        self.repository = BudgetRepository(self.active_profile.data_dir)
        today = date.today()
        self.year = tk.IntVar(value=today.year)
        self.month = tk.IntVar(value=today.month)
        self.status = tk.StringVar(value="")
        self.freedom_status = tk.StringVar(value="")
        self.profile_status = tk.StringVar(value="")
        self.status_message = ""
        self._cargar_contexto_perfil(self.active_profile)

        self._migrate_legacy_account_links()
        self._configure_style()
        self._build_header()
        self._build_tabs()
        self._build_status()
        self.refresh_all()

    def _cargar_contexto_perfil(self, perfil: PerfilLocal) -> None:
        """Carga repositorios y datos desde un perfil local."""
        self.active_profile = perfil
        self.repository = BudgetRepository(perfil.data_dir)
        self.history_manager = HistorialFinanciero(
            perfil.data_dir / "historial_mensual.json"
        )
        self.report_manager = GestorReportes(
            perfil.reportes_dir,
            ProveedorClaveLocal(perfil.clave_reportes),
        )
        self.budget, inherited_from = (
            self.repository.load_or_create_from_previous(
                self.year.get(),
                self.month.get(),
            )
        )
        self.debts = self.repository.load_debts()
        self.accounts = self.repository.load_accounts()
        self.status_message = self._crear_respaldo_perfil(perfil)
        if inherited_from:
            prefix = f"{self.status_message} | " if self.status_message else ""
            self.status_message = (
                f"{prefix}Configuracion heredada desde {inherited_from}."
            )
        self.profile_status.set(perfil.nombre)

    def _crear_respaldo_perfil(self, perfil: PerfilLocal) -> str:
        """Crea un respaldo de inicio dentro del perfil activo."""
        try:
            ruta = GestorRespaldos(
                data_dir=perfil.data_dir,
                backup_dir=perfil.backup_dir,
                reports_dir=perfil.reportes_dir,
            ).crear_respaldo()
        except OSError as exc:
            return f"No se pudo crear respaldo: {exc}"
        return f"Respaldo creado en {ruta}"

    def change_profile(self) -> None:
        """Abre una ventana simple para elegir otro perfil local."""
        ventana = tk.Toplevel(self)
        ventana.title("Cambiar perfil")
        ventana.transient(self)
        ventana.grab_set()
        ventana.resizable(False, False)
        ttk.Label(
            ventana,
            text="Selecciona un perfil local:",
        ).pack(anchor="w", padx=12, pady=(12, 6))
        perfiles = self.profile_manager.listar_perfiles()
        lista = tk.Listbox(ventana, height=8, width=38)
        lista.pack(fill=tk.BOTH, expand=True, padx=12, pady=(0, 8))
        for perfil in perfiles:
            lista.insert(tk.END, perfil.nombre)
        activo = self.active_profile.slug
        for indice, perfil in enumerate(perfiles):
            if perfil.slug == activo:
                lista.selection_set(indice)
                lista.activate(indice)
                break

        def aceptar() -> None:
            """Activa el perfil seleccionado en la lista."""
            seleccion = lista.curselection()
            if not seleccion:
                return
            perfil = perfiles[seleccion[0]]
            ventana.destroy()
            self._activar_perfil(perfil.slug)

        botones = ttk.Frame(ventana)
        botones.pack(fill=tk.X, padx=12, pady=(0, 12))
        ttk.Button(botones, text="Abrir", command=aceptar).pack(
            side=tk.RIGHT,
            padx=(6, 0),
        )
        ttk.Button(botones, text="Cancelar", command=ventana.destroy).pack(
            side=tk.RIGHT,
        )
        lista.bind("<Double-Button-1>", lambda _event: aceptar())

    def create_profile(self) -> None:
        """Crea un perfil local vacío y lo abre."""
        nombre = simpledialog.askstring(
            "Crear perfil nuevo",
            "Nombre del nuevo perfil:",
            parent=self,
        )
        if nombre is None:
            return
        try:
            perfil = self.profile_manager.crear_perfil(nombre)
        except ValueError as exc:
            messagebox.showerror("No se pudo crear perfil", str(exc))
            return
        self._activar_perfil(perfil.slug)

    def open_demo_profile(self) -> None:
        """Genera y abre el perfil Demo Avalancha."""
        try:
            perfil = self.profile_manager.asegurar_demo()
        except (OSError, ValueError) as exc:
            messagebox.showerror("No se pudo abrir demo", str(exc))
            return
        self._activar_perfil(perfil.slug)

    def _activar_perfil(self, slug: str) -> None:
        """Cambia el contexto activo sin mezclar datos entre perfiles."""
        try:
            perfil = self.profile_manager.activar_perfil(slug)
        except ValueError as exc:
            messagebox.showerror("No se pudo cambiar perfil", str(exc))
            return
        self._cargar_contexto_perfil(perfil)
        self._migrate_legacy_account_links()
        if hasattr(self, "reports_tab"):
            self.reports_tab.report_manager = self.report_manager
        self.refresh_all()

    def _configure_style(self) -> None:
        """Configura estilos visuales base compatibles con HiDPI."""
        style = ttk.Style(self)
        if "clam" in style.theme_names():
            style.theme_use("clam")
        style.configure("TFrame", background=BG_COLOR)
        style.configure("TLabelframe", background=BG_COLOR)
        style.configure("TLabelframe.Label", background=BG_COLOR)
        style.configure(
            "TLabel",
            background=BG_COLOR,
            foreground=TEXT_COLOR,
            font=(FONT_FAMILY, FONT_SIZE_NORMAL),
        )
        style.configure(
            "TButton",
            font=(FONT_FAMILY, FONT_SIZE_NORMAL),
            padding=BUTTON_PADDING,
        )
        style.configure(
            "TNotebook.Tab",
            font=(FONT_FAMILY, FONT_SIZE_NORMAL),
            padding=(PAD_MEDIUM, PAD_SMALL),
        )
        style.configure(
            "Treeview",
            rowheight=TREE_ROW_HEIGHT,
            font=(FONT_FAMILY, FONT_SIZE_TABLE),
        )
        style.configure(
            "Treeview.Heading",
            font=(FONT_FAMILY, FONT_SIZE_TABLE, "bold"),
        )
        style.configure(
            "Footer.TLabel",
            background=BG_COLOR,
            foreground=MUTED_COLOR,
            font=(FONT_FAMILY, FONT_SIZE_FOOTER),
        )
        style.configure(
            "FooterBold.TLabel",
            background=BG_COLOR,
            foreground=MUTED_COLOR,
            font=(FONT_FAMILY, FONT_SIZE_FOOTER, "bold"),
        )
        style.map(
            "Treeview",
            background=[("selected", ACCENT_COLOR)],
            foreground=[("selected", "#ffffff")],
        )

    def _build_header(self) -> None:
        header = ttk.Frame(self)
        header.pack(fill=tk.X, padx=12, pady=(12, 0))

        title_box = ttk.Frame(header)
        title_box.pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Label(
            title_box,
            text="Avalancha",
            font=(FONT_FAMILY, FONT_SIZE_TITLE, "bold"),
        ).pack(anchor="w")
        ttk.Label(
            title_box,
            text="Seguimiento mensual de ingresos, gastos y presupuesto",
            foreground=MUTED_COLOR,
            font=(FONT_FAMILY, FONT_SIZE_NORMAL),
        ).pack(anchor="w")
        profile_box = ttk.Frame(title_box)
        profile_box.pack(anchor="w", pady=(6, 0))
        ttk.Label(
            profile_box,
            text="Perfil activo:",
            foreground=MUTED_COLOR,
        ).pack(side=tk.LEFT)
        ttk.Label(
            profile_box,
            textvariable=self.profile_status,
            font=(FONT_FAMILY, FONT_SIZE_SMALL, "bold"),
        ).pack(side=tk.LEFT, padx=(4, 12))
        ttk.Button(
            profile_box,
            text="Cambiar perfil",
            command=self.change_profile,
        ).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(
            profile_box,
            text="Crear perfil nuevo",
            command=self.create_profile,
        ).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(
            profile_box,
            text="Abrir Perfil Demo",
            command=self.open_demo_profile,
        ).pack(side=tk.LEFT)

        month_box = ttk.Frame(header)
        month_box.pack(side=tk.RIGHT)
        ttk.Button(month_box, text="<", width=3, command=self.previous_month).pack(
            side=tk.LEFT,
            padx=(0, 6),
        )
        self.month_label = ttk.Label(
            month_box,
            width=22,
            anchor=tk.CENTER,
            font=(FONT_FAMILY, FONT_SIZE_NORMAL, "bold"),
        )
        self.month_label.pack(side=tk.LEFT)
        ttk.Button(month_box, text=">", width=3, command=self.next_month).pack(
            side=tk.LEFT,
            padx=(6, 0),
        )

    def _build_tabs(self) -> None:
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=12, pady=12)

        self.dashboard = Dashboard(
            self.notebook,
            self.close_month,
        )
        self.transactions_tab = TransactionsTab(
            self.notebook,
            self.get_budget,
            self.get_debts,
            self.get_accounts,
            self.save_and_refresh,
        )
        self.categories_tab = CategoriesTab(
            self.notebook,
            self.get_budget,
            self.save_and_refresh,
        )
        self.recurring_tab = RecurringTab(
            self.notebook,
            self.get_budget,
            self.get_debts,
            self.get_accounts,
            self.save_and_refresh,
        )
        self.accounts_tab = AccountsTab(
            self.notebook,
            self.get_accounts,
            self.get_budget,
            self.get_debts,
            self.get_debt_payments,
            self.save_accounts_and_refresh,
        )
        self.reports_tab = ReportsTab(
            self.notebook,
            self.report_manager,
        )
        self.debts_tab = DebtsTab(
            self.notebook,
            self.get_debts,
            self.get_debt_payments,
            self.save_debts_and_refresh,
        )

        self.notebook.add(self.dashboard, text="Resumen")
        self.notebook.add(self.transactions_tab, text="Movimientos")
        self.notebook.add(self.categories_tab, text="Categorias")
        self.notebook.add(self.recurring_tab, text="Recurrentes")
        self.notebook.add(self.accounts_tab, text="Cuentas")
        self.notebook.add(self.reports_tab, text="Reportes")
        self.notebook.add(self.debts_tab, text="Deudas")

    def _build_status(self) -> None:
        """Construye la barra inferior con tamaño legible en HiDPI."""
        footer = ttk.Frame(self)
        footer.pack(
            fill=tk.X,
            padx=PAD_LARGE,
            pady=(PAD_SMALL, PAD_MEDIUM),
        )
        ttk.Label(
            footer,
            textvariable=self.status,
            style="Footer.TLabel",
            anchor=tk.W,
        ).pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Label(
            footer,
            textvariable=self.freedom_status,
            style="FooterBold.TLabel",
            anchor=tk.E,
        ).pack(side=tk.RIGHT, padx=(12, 0))

    def get_budget(self) -> MonthlyBudget:
        """Return the current monthly budget."""
        return self.budget

    def get_debts(self) -> list[Debt]:
        """Return global debts."""
        return self.debts

    def get_accounts(self) -> list[CuentaFinanciera]:
        """Return global manual financial accounts."""
        return self.accounts

    def get_debt_payments(self) -> dict[str, int]:
        """Return debt payments including unsaved current month changes."""
        return self.repository.debt_payment_totals(self.budget)

    def get_debt_manager(self) -> GestorDeudas:
        """Return debt manager with current payment totals."""
        return GestorDeudas(self.debts, self.get_debt_payments())

    def get_debt_projections(self) -> dict[str, Any]:
        """Return projections for active debts."""
        manager = self.get_debt_manager()
        projector = ProyectorDeuda()
        return {
            debt.debt_id: projector.proyectar(
                debt,
                balance=manager.saldo_operativo(debt),
            )
            for debt in manager.active_debts()
        }

    def previous_month(self) -> None:
        """Move to the previous month."""
        year = self.year.get()
        month = self.month.get() - 1
        if month == 0:
            year -= 1
            month = 12
        self.load_month(year, month)

    def next_month(self) -> None:
        """Move to the next month."""
        year = self.year.get()
        month = self.month.get() + 1
        if month == 13:
            year += 1
            month = 1
        self.load_month(year, month)

    def load_month(self, year: int, month: int) -> None:
        """Carga un mes y hereda su configuración cuando es nuevo."""
        self.year.set(year)
        self.month.set(month)
        self.status_message = ""
        self.budget, inherited_from = (
            self.repository.load_or_create_from_previous(year, month)
        )
        if inherited_from:
            self.status_message = (
                f"Nuevo mes creado desde {inherited_from}. "
                "Los movimientos reales comienzan vacíos."
            )
        self._migrate_legacy_account_links()
        self.refresh_all()

    def _migrate_legacy_account_links(self) -> None:
        """Link old movements to the temporary classification account."""
        changed = self.repository.migrate_legacy_account_links(
            self.budget,
            self.accounts,
        )
        if not changed:
            return
        self.recalculate_account_balances()
        self.repository.save(self.budget)
        self.repository.save_accounts(self.accounts)
        self.status_message = (
            "Datos antiguos vinculados a Cuenta por clasificar."
        )

    def save_and_refresh(self) -> None:
        """Persist current budget and refresh all tabs."""
        self.recalculate_account_balances()
        path = self.repository.save(self.budget)
        if self.accounts:
            self.repository.save_accounts(self.accounts)
        self.status_message = f"Guardado en {path}"
        self.refresh_all()

    def save_debts_and_refresh(self) -> None:
        """Persist global debts and refresh all tabs."""
        path = self.repository.save_debts(self.debts)
        self.status_message = f"Deudas guardadas en {path}"
        self.refresh_all()

    def save_accounts_and_refresh(self) -> None:
        """Persist global financial accounts and refresh all tabs."""
        self.recalculate_account_balances()
        path = self.repository.save_accounts(self.accounts)
        self.status_message = f"Cuentas guardadas en {path}"
        self.refresh_all()

    def recalculate_account_balances(self) -> None:
        """Recalculate registered account balances for the active month."""
        GestorConciliacion(
            self.accounts
        ).recalcular_saldos_registrados(self.budget)

    def close_month(self) -> None:
        """Cierra el mes y guarda su reporte oficial cifrado."""
        if self.history_manager.mes_cerrado(self.budget.label):
            messagebox.showinfo(
                "Cerrar mes",
                "Este mes ya fue cerrado.",
            )
            return
        if not messagebox.askyesno(
            "Cerrar mes",
            f"Cerrar definitivamente {self.budget.label}?",
        ):
            return
        try:
            self.recalculate_account_balances()
            self.repository.save(self.budget)
            self.repository.save_debts(self.debts)
            self.repository.save_accounts(self.accounts)
            manager = self.get_debt_manager()
            risk = calculate_financial_risk(
                self.budget,
                manager,
                self.accounts,
            )
            snapshot = GeneradorSnapshot.crear(
                self.budget,
                manager,
                risk,
                self.accounts,
            )
            report = self._build_official_report(manager, risk)
            report_entry = self.report_manager.guardar_reporte(
                report,
                self.budget.label,
            )
            history_path = self.history_manager.guardar_snapshot(snapshot)
        except MesYaCerradoError:
            messagebox.showinfo("Cerrar mes", "Este mes ya fue cerrado.")
            return
        except ReporteDuplicadoError:
            messagebox.showinfo(
                "Cerrar mes",
                "Este mes ya posee un reporte oficial.",
            )
            return
        except ReporteInconsistenteError as exc:
            messagebox.showerror(
                "No se pudo cerrar el mes",
                str(exc),
            )
            return
        except (OSError, ValueError) as exc:
            messagebox.showerror(
                "No se pudo cerrar el mes",
                str(exc),
            )
            return
        self.status_message = (
            f"Mes cerrado en {history_path} | "
            f"Reporte: {report_entry['nombre']}"
        )
        self.refresh_all()
        messagebox.showinfo(
            "Mes cerrado",
            "El mes y su reporte cifrado fueron guardados correctamente.",
        )

    def _build_official_report(
        self,
        manager: GestorDeudas,
        risk: ResultadoRiesgo,
    ) -> ReporteEstructurado:
        """Construye el reporte estructurado que será cifrado."""
        projections = self.get_debt_projections()
        freedom_date = ReporteMensual(
            manager,
            projections,
        ).fecha_libertad_financiera()
        analyzer = AnalizadorResumen(self.budget, self.accounts)
        diagnostics = DiagnosticoFinanciero(
            self.budget,
            manager,
            self.accounts,
        ).obtener_alertas()
        try:
            history = self.history_manager.leer_historial()
        except ValueError:
            history = []
        generator = GeneradorReporteMensual(
            presupuesto=self.budget,
            gestor_deudas=manager,
            cuentas=self.accounts,
            analizador=analyzer,
            diagnosticos=diagnostics,
            fecha_libertad=freedom_date,
            nivel_riesgo=risk.level,
            historial=history,
            puntaje_riesgo=risk.score,
        )
        return generator.generar_estructura_reporte()

    def refresh_status(self) -> None:
        """Refresh the status bar with save message and monthly totals."""
        summary = budget_status_summary(self.budget)
        if self.status_message:
            self.status.set(f"{self.status_message} | {summary}")
        else:
            self.status.set(summary)

    def refresh_all(self) -> None:
        """Refresh every visible component."""
        self.recalculate_account_balances()
        month_name = MONTH_NAMES[self.month.get()]
        self.month_label.configure(text=f"{month_name} {self.year.get()}")
        manager = self.get_debt_manager()
        projections = self.get_debt_projections()
        freedom_date = ReporteMensual(manager, projections)
        freedom_value = freedom_date.fecha_libertad_financiera()
        self.freedom_status.set(
            "Libertad financiera estimada: "
            f"{display_optional_date(freedom_value)}"
        )
        analyzer = AnalizadorResumen(self.budget, self.accounts)
        risk = calculate_financial_risk(
            self.budget,
            manager,
            self.accounts,
        )
        try:
            history = self.history_manager.leer_historial()
            trends = {
                "deuda": self.history_manager.obtener_tendencia(
                    "deuda_total"
                ),
                "patrimonio": self.history_manager.obtener_tendencia(
                    "patrimonio_neto"
                ),
                "flujo": self.history_manager.obtener_tendencia(
                    "flujo_libre"
                ),
            }
        except ValueError:
            history = []
            trends = {
                "deuda": "Sin datos",
                "patrimonio": "Sin datos",
                "flujo": "Sin datos",
            }
        diagnostics = DiagnosticoFinanciero(
            self.budget,
            manager,
            self.accounts,
        ).obtener_alertas()
        self.dashboard.refresh(
            self.budget,
            manager,
            freedom_value,
            analyzer,
            risk.level,
            history,
            trends,
            diagnostics,
        )
        self.transactions_tab.refresh()
        self.categories_tab.refresh()
        self.recurring_tab.refresh()
        self.accounts_tab.refresh()
        self.reports_tab.refresh()
        self.debts_tab.refresh()
        self.refresh_status()


def main() -> None:
    """Start the Avalancha application."""
    app = AvalanchaApp()
    app.mainloop()
