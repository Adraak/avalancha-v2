"""Dashboard basico de Avalancha V2."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from PySide6.QtWidgets import (
    QGridLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from avalancha.storage import BudgetRepository
from services.financial_summary_service import FinancialSummaryService


class DashboardPage(QWidget):
    """Muestra indicadores principales del perfil activo."""

    def __init__(
        self,
        data_dir: str | Path = "data",
        service: FinancialSummaryService | None = None,
    ) -> None:
        """Inicializa el dashboard con la ruta de datos activa."""
        super().__init__()
        self.data_dir = Path(data_dir)
        self.service = service or FinancialSummaryService()
        self.repository = BudgetRepository(self.data_dir)
        self.grid = QGridLayout()
        self._build_ui()
        self.refresh()

    def refresh(self) -> None:
        """Actualiza indicadores desde el presupuesto del mes actual."""
        today = date.today()
        budget = self.repository.load(today.year, today.month)
        accounts = self.repository.load_accounts()
        debts = self.repository.load_debts()
        payments = self.repository.debt_payment_totals(budget)
        indicators = self.service.calcular_indicadores_mensuales(
            movimientos=budget.transactions,
            categorias=budget.categories,
            recurrentes=budget.recurring_items,
            deudas=debts,
            cuentas=accounts,
            pagos_por_deuda=payments,
        )
        values = [
            ("Ingresos reales", indicators.ingresos_reales),
            ("Gastos reales", indicators.gastos_reales),
            ("Flujo libre", indicators.flujo_libre),
            ("Deuda actual", indicators.deuda_actual),
            ("Patrimonio neto", indicators.patrimonio_neto),
            ("Gastos imprevistos", indicators.gastos_imprevistos),
        ]
        self._clear_grid()
        for index, (title, amount) in enumerate(values):
            self.grid.addWidget(self._card(title, amount), index // 3, index % 3)

    def _build_ui(self) -> None:
        """Construye el layout del dashboard."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 28, 28, 28)
        layout.setSpacing(16)

        title = QLabel("Dashboard")
        title.setObjectName("PageTitle")

        refresh_button = QPushButton("Actualizar")
        refresh_button.clicked.connect(self.refresh)

        layout.addWidget(title)
        layout.addLayout(self.grid)
        layout.addStretch(1)
        layout.addWidget(refresh_button)

    def _card(self, title: str, amount: int) -> QWidget:
        """Crea una tarjeta simple de indicador."""
        card = QWidget()
        layout = QVBoxLayout(card)
        label = QLabel(title)
        value = QLabel(self._format_clp(amount))
        value.setObjectName("PageTitle")
        layout.addWidget(label)
        layout.addWidget(value)
        return card

    def _clear_grid(self) -> None:
        """Elimina widgets anteriores del grid."""
        while self.grid.count():
            item = self.grid.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    @staticmethod
    def _format_clp(amount: int) -> str:
        """Formatea monto CLP."""
        prefix = "-$" if amount < 0 else "$"
        return f"{prefix} {abs(amount):,.0f}".replace(",", ".")
