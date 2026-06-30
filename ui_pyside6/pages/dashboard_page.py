"""Dashboard visual de Avalancha V2."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from services.dashboard_visual_service import (
    BudgetUsageValue,
    ChartValue,
    DashboardCard,
    DashboardVisualService,
)
from services.financial_alert_service import FinancialAlert
from ui_pyside6.color_system import (
    BAR_BACKGROUND,
    BORDER,
    PANEL,
    PANEL_SOFT,
    TEXT_MUTED,
    get_budget_usage_color,
    get_category_color,
    get_flow_color,
    get_semantic_color,
)


class DashboardPage(QWidget):
    """Muestra lectura visual rapida del perfil activo."""

    def __init__(
        self,
        data_dir: str | Path = "data",
        service: DashboardVisualService | None = None,
    ) -> None:
        """Inicializa el dashboard con servicio visual del perfil."""
        super().__init__()
        self.service = service or DashboardVisualService(data_dir=data_dir)
        self.content_layout = QVBoxLayout()
        self._build_ui()
        self.refresh()

    def refresh(self) -> None:
        """Actualiza tarjetas, graficos y alertas desde servicios."""
        data = self.service.obtener_dashboard()
        self._clear_layout(self.content_layout)
        self.content_layout.addLayout(self._build_cards(data.tarjetas))
        self.content_layout.addLayout(
            self._build_chart_row(
                data.gastos_por_categoria,
                data.ingresos_vs_gastos,
            ),
        )
        self.content_layout.addWidget(
            self._build_budget_section(data.presupuestos),
        )
        self.content_layout.addWidget(self._build_alerts(data.alertas))
        self.content_layout.addStretch(1)

    def _build_ui(self) -> None:
        """Construye la estructura fija del dashboard."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 28, 28, 28)
        layout.setSpacing(16)

        header = QHBoxLayout()
        title_box = QVBoxLayout()
        title = QLabel("Dashboard")
        title.setObjectName("PageTitle")
        subtitle = QLabel("Lectura visual de la situacion financiera")
        subtitle.setObjectName("PageSubtitle")
        title_box.addWidget(title)
        title_box.addWidget(subtitle)

        refresh_button = QPushButton("Actualizar")
        refresh_button.clicked.connect(self.refresh)

        header.addLayout(title_box, stretch=1)
        header.addWidget(refresh_button)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        content = QWidget()
        self.content_layout = QVBoxLayout(content)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.setSpacing(16)
        scroll.setWidget(content)

        layout.addLayout(header)
        layout.addWidget(scroll, stretch=1)

    def _build_cards(self, cards: list[DashboardCard]) -> QGridLayout:
        """Construye tarjetas semanticas principales."""
        grid = QGridLayout()
        grid.setSpacing(12)
        for index, card in enumerate(cards):
            grid.addWidget(self._card(card), index // 3, index % 3)
        return grid

    def _card(self, card: DashboardCard) -> QFrame:
        """Crea una tarjeta visual con color semantico."""
        widget = QFrame()
        widget.setObjectName("MetricCard")
        color = (
            get_flow_color(card.monto)
            if card.titulo == "Flujo libre"
            else get_semantic_color(card.estado)
        )
        widget.setStyleSheet(
            """
            #MetricCard {
                background: %s;
                border: 1px solid %s;
                border-left: 6px solid %s;
                border-radius: 10px;
            }
            """
            % (PANEL, BORDER, color),
        )
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(8)

        title = QLabel(card.titulo)
        title.setObjectName("PageSubtitle")
        amount = QLabel(self._format_clp(card.monto))
        amount.setStyleSheet(
            f"font-size: 22px; font-weight: 800; color: {color};",
        )
        state = QLabel(card.estado)
        state.setStyleSheet(f"font-size: 12px; color: {TEXT_MUTED};")

        layout.addWidget(title)
        layout.addWidget(amount)
        layout.addWidget(state)
        return widget

    def _build_chart_row(
        self,
        gastos: list[ChartValue],
        ingresos_vs_gastos: list[ChartValue],
    ) -> QHBoxLayout:
        """Construye fila con graficos principales."""
        row = QHBoxLayout()
        row.setSpacing(14)
        row.addWidget(
            self._build_bar_section(
                "Gastos por categoría",
                gastos,
                empty_text="Sin gastos registrados.",
            ),
            stretch=2,
        )
        row.addWidget(
            self._build_bar_section(
                "Ingresos vs gastos",
                ingresos_vs_gastos,
                empty_text="Sin datos del mes.",
            ),
            stretch=1,
        )
        return row

    def _build_bar_section(
        self,
        title: str,
        values: list[ChartValue],
        empty_text: str,
    ) -> QFrame:
        """Crea un panel de barras horizontales."""
        panel = self._panel(title)
        layout = panel.layout()
        if not isinstance(layout, QVBoxLayout):
            return panel
        if not values:
            layout.addWidget(QLabel(empty_text))
            return panel
        for value in values[:8]:
            color = (
                self._income_expense_color(value.etiqueta)
                if title == "Ingresos vs gastos"
                else get_category_color(value.etiqueta)
            )
            layout.addWidget(
                self._progress_row(
                    label=value.etiqueta,
                    amount=value.monto,
                    percentage=value.porcentaje,
                    color=color,
                    suffix=f"{value.porcentaje:.1f}%",
                ),
            )
        return panel

    def _build_budget_section(
        self,
        values: list[BudgetUsageValue],
    ) -> QFrame:
        """Construye panel de presupuesto versus gasto."""
        panel = self._panel("Presupuesto vs gasto")
        layout = panel.layout()
        if not isinstance(layout, QVBoxLayout):
            return panel
        if not values:
            layout.addWidget(QLabel("Sin presupuestos para comparar."))
            return panel
        for value in values[:8]:
            suffix = (
                f"{value.estado} | "
                f"{self._format_clp(value.gastado)} / "
                f"{self._format_clp(value.presupuesto)}"
            )
            layout.addWidget(
                self._progress_row(
                    label=value.categoria,
                    amount=value.gastado,
                    percentage=value.porcentaje,
                    color=get_budget_usage_color(value.porcentaje),
                    suffix=suffix,
                ),
            )
        return panel

    def _build_alerts(self, alerts: list[FinancialAlert]) -> QFrame:
        """Construye panel de alertas financieras."""
        panel = self._panel("Alertas")
        layout = panel.layout()
        if not isinstance(layout, QVBoxLayout):
            return panel
        for alert in alerts:
            color = get_semantic_color(alert.nivel)
            item = QLabel(f"{alert.titulo}: {alert.mensaje}")
            item.setWordWrap(True)
            item.setStyleSheet(
                f"border-left: 5px solid {color}; "
                f"padding: 8px 10px; background: {PANEL_SOFT};"
            )
            layout.addWidget(item)
        return panel

    def _progress_row(
        self,
        label: str,
        amount: int,
        percentage: float,
        color: str,
        suffix: str,
    ) -> QWidget:
        """Crea una fila visual con etiqueta, barra y monto."""
        row = QWidget()
        layout = QVBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        header = QHBoxLayout()
        name = QLabel(label)
        value = QLabel(f"{self._format_clp(amount)} | {suffix}")
        value.setAlignment(Qt.AlignmentFlag.AlignRight)
        value.setStyleSheet(f"color: {TEXT_MUTED};")
        header.addWidget(name, stretch=1)
        header.addWidget(value)

        bar = QProgressBar()
        bar.setRange(0, 100)
        bar.setValue(min(round(percentage), 100))
        bar.setTextVisible(False)
        bar.setFixedHeight(12)
        bar.setStyleSheet(
            """
            QProgressBar {
                background: %s;
                border: none;
                border-radius: 6px;
            }
            QProgressBar::chunk {
                background: %s;
                border-radius: 6px;
            }
            """
            % (BAR_BACKGROUND, color),
        )

        layout.addLayout(header)
        layout.addWidget(bar)
        return row

    def _panel(self, title: str) -> QFrame:
        """Crea un panel visual base."""
        panel = QFrame()
        panel.setObjectName("DashboardPanel")
        panel.setStyleSheet(
            """
            #DashboardPanel {
                background: %s;
                border: 1px solid %s;
                border-radius: 10px;
            }
            """
            % (PANEL, BORDER),
        )
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)
        label = QLabel(title)
        label.setStyleSheet("font-size: 16px; font-weight: 800;")
        layout.addWidget(label)
        return panel

    @staticmethod
    def _clear_layout(layout: QVBoxLayout) -> None:
        """Elimina widgets y sublayouts del contenedor."""
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            child_layout = item.layout()
            if widget is not None:
                widget.deleteLater()
            elif child_layout is not None:
                DashboardPage._clear_nested_layout(child_layout)

    @staticmethod
    def _clear_nested_layout(layout) -> None:
        """Elimina recursivamente elementos de un layout."""
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            child_layout = item.layout()
            if widget is not None:
                widget.deleteLater()
            elif child_layout is not None:
                DashboardPage._clear_nested_layout(child_layout)

    @staticmethod
    def _format_clp(amount: int) -> str:
        """Formatea monto CLP."""
        prefix = "-$" if amount < 0 else "$"
        return f"{prefix} {abs(amount):,.0f}".replace(",", ".")

    @staticmethod
    def _income_expense_color(label: str) -> str:
        """Devuelve color semantico para ingresos y gastos."""
        if label.casefold() == "ingresos":
            return get_semantic_color("success")
        return get_semantic_color("danger")
