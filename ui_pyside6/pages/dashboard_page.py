"""Dashboard visual de Avalancha V2."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
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
    EvolutionPoint,
    FixedPaymentValue,
    FixedPaymentsSummary,
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


class VerticalBarChart(QWidget):
    """Grafico simple de barras verticales para ingresos versus gastos."""

    def __init__(self, values: list[ChartValue], parent=None) -> None:
        """Inicializa el grafico con valores ya preparados."""
        super().__init__(parent)
        self.values = values
        self.setMinimumHeight(220)

    def paintEvent(self, event) -> None:
        """Dibuja barras verticales con montos y etiquetas."""
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if not self.values:
            painter.setPen(QColor(TEXT_MUTED))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "Sin datos.")
            return

        margin_x = 34
        top = 30
        bottom = 52
        chart_height = max(self.height() - top - bottom, 1)
        max_amount = max((value.monto for value in self.values), default=0)
        min_amount = min((value.monto for value in self.values), default=0)
        positive_range = max(max_amount, 0)
        negative_range = abs(min(min_amount, 0))
        total_range = max(positive_range + negative_range, 1)
        baseline = top + chart_height * (positive_range / total_range)
        slot_width = max((self.width() - margin_x * 2) / len(self.values), 1)
        bar_width = min(slot_width * 0.46, 70)

        painter.setPen(QColor(BORDER))
        painter.drawLine(margin_x, baseline, self.width() - margin_x, baseline)

        for index, value in enumerate(self.values):
            x_center = margin_x + slot_width * index + slot_width / 2
            bar_height = chart_height * (abs(value.monto) / total_range)
            top_y = baseline - bar_height if value.monto >= 0 else baseline
            rect = QRectF(
                x_center - bar_width / 2,
                top_y,
                bar_width,
                bar_height,
            )
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(self._bar_color(value)))
            painter.drawRoundedRect(rect, 7, 7)

            painter.setPen(QColor(TEXT_MUTED))
            amount_rect = QRectF(
                x_center - slot_width / 2,
                max(top - 24, 0),
                slot_width,
                20,
            )
            painter.drawText(
                amount_rect,
                Qt.AlignmentFlag.AlignCenter,
                DashboardPage._format_clp(value.monto),
            )
            label_rect = QRectF(
                x_center - slot_width / 2,
                baseline + 8,
                slot_width,
                20,
            )
            painter.drawText(
                label_rect,
                Qt.AlignmentFlag.AlignCenter,
                value.etiqueta,
            )

    @staticmethod
    def _bar_color(value: ChartValue) -> str:
        """Devuelve color semantico para cada barra."""
        label = value.etiqueta
        if label.casefold() == "ingresos":
            return get_semantic_color("success")
        if label.casefold() == "flujo libre":
            return get_flow_color(value.monto)
        return get_semantic_color("danger")


class LineChart(QWidget):
    """Grafico lineal simple para evolucion de flujo libre."""

    def __init__(self, values: list[EvolutionPoint], parent=None) -> None:
        """Inicializa el grafico con puntos mensuales preparados."""
        super().__init__(parent)
        self.values = values
        self.setMinimumHeight(220)

    def paintEvent(self, event) -> None:
        """Dibuja una linea temporal o mensaje sin historial."""
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if len(self.values) < 2:
            painter.setPen(QColor(TEXT_MUTED))
            painter.drawText(
                self.rect(),
                Qt.AlignmentFlag.AlignCenter,
                "Aun no hay suficiente historial para mostrar evolucion.",
            )
            return

        left = 72
        right = self.width() - 28
        top = 24
        bottom = self.height() - 42
        amounts = [point.monto for point in self.values]
        minimum = min(0, min(amounts))
        maximum = max(amounts)
        if minimum == maximum:
            minimum -= 1
            maximum += 1

        grid_pen = QPen(QColor(BORDER))
        grid_pen.setWidth(1)
        painter.setPen(grid_pen)
        y_steps = 4
        for step in range(y_steps + 1):
            ratio = step / y_steps
            y = bottom - ratio * (bottom - top)
            value = minimum + ratio * (maximum - minimum)
            painter.drawLine(left, y, right, y)
            painter.setPen(QColor(TEXT_MUTED))
            painter.drawText(
                QRectF(0, y - 9, left - 10, 18),
                Qt.AlignmentFlag.AlignRight,
                self._format_axis_amount(round(value)),
            )
            painter.setPen(grid_pen)

        painter.drawLine(left, top, left, bottom)
        painter.drawLine(left, bottom, right, bottom)

        path = QPainterPath()
        points = []
        for index, point in enumerate(self.values):
            x = left + index * (right - left) / (len(self.values) - 1)
            ratio = (point.monto - minimum) / (maximum - minimum)
            y = bottom - ratio * (bottom - top)
            points.append(QPointF(x, y))
            if index == 0:
                path.moveTo(x, y)
            else:
                path.lineTo(x, y)

        fill_path = QPainterPath(path)
        fill_path.lineTo(points[-1].x(), bottom)
        fill_path.lineTo(points[0].x(), bottom)
        fill_path.closeSubpath()
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#eaf4ff"))
        painter.drawPath(fill_path)

        line_pen = QPen(QColor("#2f7df6"))
        line_pen.setWidth(3)
        painter.setPen(line_pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(path)
        for point, data in zip(points, self.values):
            painter.setBrush(QColor("#2f7df6"))
            painter.setPen(QColor(PANEL))
            painter.drawEllipse(point, 5, 5)
            painter.setPen(QColor(TEXT_MUTED))
            painter.drawText(
                QRectF(point.x() - 34, bottom + 10, 68, 18),
                Qt.AlignmentFlag.AlignCenter,
                data.mes[2:],
            )

    @staticmethod
    def _format_axis_amount(amount: int) -> str:
        """Formatea montos compactos para eje Y."""
        abs_amount = abs(amount)
        sign = "-" if amount < 0 else ""
        if abs_amount >= 1_000_000:
            return f"{sign}CLP {abs_amount / 1_000_000:.1f}M"
        if abs_amount >= 1_000:
            return f"{sign}CLP {round(abs_amount / 1_000)}k"
        return f"{sign}CLP {abs_amount}"


class DonutChart(QWidget):
    """Grafico circular simple para distribuciones financieras."""

    def __init__(
        self,
        values: list[ChartValue],
        center_title: str,
        center_amount: int,
        parent=None,
    ) -> None:
        """Inicializa el grafico con valores ya calculados."""
        super().__init__(parent)
        self.values = [value for value in values if value.monto > 0]
        self.center_title = center_title
        self.center_amount = center_amount
        self.setMinimumHeight(220)

    def paintEvent(self, event) -> None:
        """Dibuja dona, leyenda y texto central."""
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if not self.values:
            painter.setPen(QColor(TEXT_MUTED))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "Sin datos.")
            return

        margin = 18
        legend_width = min(230, max(self.width() * 0.42, 145))
        chart_width = max(self.width() - legend_width - margin * 3, 80)
        side = min(self.height() - margin * 2, chart_width, 170)
        side = max(side, 80)
        rect = QRectF(
            margin,
            (self.height() - side) / 2,
            side,
            side,
        )
        total = sum(value.monto for value in self.values)
        start = 90 * 16
        pen = QPen()
        pen.setWidth(max(round(side * 0.16), 14))
        pen.setCapStyle(Qt.PenCapStyle.FlatCap)
        painter.setPen(pen)

        for value in self.values:
            span = round(-360 * 16 * (value.monto / total))
            pen.setColor(QColor(self._color(value)))
            painter.setPen(pen)
            painter.drawArc(rect, start, span)
            start += span

        painter.setPen(QColor(TEXT_MUTED))
        center_font = painter.font()
        center_font.setPointSize(8)
        painter.setFont(center_font)
        painter.drawText(
            rect,
            Qt.AlignmentFlag.AlignCenter,
            (
                f"{self.center_title}\n"
                f"{DashboardPage._format_clp(self.center_amount)}"
            ),
        )

        legend_x = rect.right() + margin
        y = rect.top() + 8
        legend_font = painter.font()
        legend_font.setPointSize(8)
        painter.setFont(legend_font)
        for value in self.values:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(self._color(value)))
            painter.drawEllipse(QPointF(legend_x, y + 7), 5, 5)
            painter.setPen(QColor(TEXT_MUTED))
            text = (
                f"{value.etiqueta}: "
                f"{DashboardPage._format_clp(value.monto)} "
                f"({value.porcentaje:.1f}%)"
            )
            painter.drawText(
                QRectF(
                    legend_x + 14,
                    y - 2,
                    self.width() - legend_x - 22,
                    34,
                ),
                Qt.TextFlag.TextWordWrap,
                text,
            )
            y += 34

    @staticmethod
    def _color(value: ChartValue) -> str:
        """Devuelve color de dona segun etiqueta."""
        label = value.etiqueta.casefold()
        if label == "ingresos":
            return get_semantic_color("success")
        if label == "gastos":
            return get_semantic_color("danger")
        if label == "imprevisto":
            return get_semantic_color("warning")
        if label == "recurrente":
            return get_semantic_color("info")
        return get_category_color(value.etiqueta)


class DashboardPage(QWidget):
    """Muestra lectura visual rapida del perfil activo."""

    def __init__(
        self,
        data_dir: str | Path = "data",
        year: int | None = None,
        month: int | None = None,
        service: DashboardVisualService | None = None,
    ) -> None:
        """Inicializa el dashboard con servicio visual del perfil."""
        super().__init__()
        self.service = service or DashboardVisualService(data_dir=data_dir)
        self.year = year
        self.month = month
        self.content_layout = QVBoxLayout()
        self._build_ui()
        self.refresh()

    def refresh(self) -> None:
        """Actualiza tarjetas, graficos y alertas desde servicios."""
        data = self.service.obtener_dashboard(self.year, self.month)
        self._clear_layout(self.content_layout)
        self.content_layout.addLayout(self._build_cards(data.tarjetas))
        self.content_layout.addLayout(
            self._build_chart_row(
                data.gastos_por_categoria,
                data.ingresos_vs_gastos,
            ),
        )
        self.content_layout.addLayout(
            self._build_bottom_row(
                data.evolucion_flujo,
                data.gastos_por_clase,
                data.presupuestos,
                data.pagos_fijos,
            ),
        )
        relevant_alerts = self._alertas_relevantes(data.alertas)
        self.content_layout.addWidget(self._build_alert_details(relevant_alerts))
        self.content_layout.addStretch(1)

    def _build_ui(self) -> None:
        """Construye la estructura fija del dashboard."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 28, 28, 28)
        layout.setSpacing(16)

        header = QHBoxLayout()
        title_box = QVBoxLayout()
        title = QLabel("Resumen")
        title.setObjectName("PageTitle")
        subtitle = QLabel("Visión general de tu situación financiera actual")
        subtitle.setObjectName("PageSubtitle")
        title_box.addWidget(title)
        title_box.addWidget(subtitle)

        period_button = QPushButton(self._month_label())
        period_button.setProperty("secondaryButton", True)
        filter_button = QPushButton("Filtros")
        filter_button.setProperty("secondaryButton", True)
        refresh_button = QPushButton("Actualizar")
        refresh_button.setProperty("secondaryButton", True)
        refresh_button.clicked.connect(self.refresh)

        header.addLayout(title_box, stretch=1)
        header.addWidget(period_button)
        header.addWidget(filter_button)
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
            grid.addWidget(self._card(card), 0, index)
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
        tint = self._card_tint(color)
        widget.setStyleSheet(
            """
            #MetricCard {
                background: %s;
                border: 1px solid %s;
                border-radius: 9px;
            }
            """
            % (tint, color),
        )
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(10)

        top = QHBoxLayout()
        icon = QLabel(self._card_symbol(card.titulo))
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setFixedSize(32, 32)
        icon.setStyleSheet(
            f"background: {color}; color: white; border-radius: 16px; "
            "font-size: 16px; font-weight: 800;",
        )

        title = QLabel(card.titulo)
        title.setObjectName("PageSubtitle")
        top.addWidget(icon)
        top.addWidget(title, stretch=1)

        amount = QLabel(self._format_clp(card.monto))
        amount.setStyleSheet(
            "font-size: 19px; font-weight: 800; color: #111827;",
        )
        state = QLabel(card.estado)
        state.setAlignment(Qt.AlignmentFlag.AlignCenter)
        state.setStyleSheet(
            f"font-size: 11px; font-weight: 700; color: {color}; "
            f"background: {PANEL}; border-radius: 9px; padding: 4px 10px;",
        )

        layout.addLayout(top)
        layout.addWidget(amount)
        layout.addWidget(state, alignment=Qt.AlignmentFlag.AlignLeft)
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
            self._build_horizontal_bar_section(
                "Gastos por categoría",
                gastos,
                empty_text="Sin gastos registrados para mostrar.",
            ),
            stretch=2,
        )
        row.addWidget(
            self._build_income_expense_section(
                ingresos_vs_gastos,
            ),
            stretch=1,
        )
        return row

    def _build_bottom_row(
        self,
        evolucion: list[EvolutionPoint],
        clases: list[ChartValue],
        presupuestos: list[BudgetUsageValue],
        pagos_fijos: FixedPaymentsSummary,
    ) -> QVBoxLayout:
        """Construye bloque inferior sin comprimir paneles visuales."""
        container = QVBoxLayout()
        container.setSpacing(14)

        first_row = QHBoxLayout()
        first_row.setSpacing(14)
        first_row.addWidget(self._build_evolution_section(evolucion), stretch=1)
        first_row.addWidget(self._build_budget_section(presupuestos), stretch=1)

        second_row = QHBoxLayout()
        second_row.setSpacing(14)
        second_row.addWidget(
            self._build_fixed_payments_section(pagos_fijos),
            stretch=1,
        )
        second_row.addWidget(self._build_class_section(clases), stretch=1)

        container.addLayout(first_row)
        container.addLayout(second_row)
        return container

    def _build_horizontal_bar_section(
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
            layout.addWidget(
                self._progress_row(
                    label=value.etiqueta,
                    amount=value.monto,
                    percentage=value.porcentaje,
                    color=get_category_color(value.etiqueta),
                    suffix=f"{value.porcentaje:.1f}%",
                ),
            )
        return panel

    def _build_income_expense_section(
        self,
        values: list[ChartValue],
    ) -> QFrame:
        """Construye grafico vertical de ingresos versus gastos."""
        panel = self._panel("Ingresos vs gastos")
        layout = panel.layout()
        if not isinstance(layout, QVBoxLayout):
            return panel
        flujo = next(
            (value.monto for value in values if value.etiqueta == "Flujo libre"),
            0,
        )
        comparables = [
            value
            for value in values
            if value.etiqueta in {"Ingresos", "Gastos"}
        ]
        layout.addWidget(DonutChart(comparables, "Flujo libre", flujo))
        flow_label = QLabel(f"Flujo libre: {self._format_clp(flujo)}")
        flow_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        flow_label.setStyleSheet(
            f"font-size: 14px; font-weight: 800; color: {get_flow_color(flujo)};"
        )
        layout.addWidget(flow_label)
        return panel

    def _build_evolution_section(
        self,
        values: list[EvolutionPoint],
    ) -> QFrame:
        """Construye grafico de evolucion de flujo libre."""
        panel = self._panel("Evolución del flujo libre")
        layout = panel.layout()
        if isinstance(layout, QVBoxLayout):
            subtitle = QLabel("Últimos 6 meses")
            subtitle.setStyleSheet(f"font-size: 12px; color: {TEXT_MUTED};")
            layout.addWidget(subtitle)
            layout.addWidget(LineChart(values))
        return panel

    def _build_class_section(
        self,
        values: list[ChartValue],
    ) -> QFrame:
        """Construye grafico de gasto por clase financiera."""
        panel = self._panel("Gastos por clase")
        layout = panel.layout()
        if not isinstance(layout, QVBoxLayout):
            return panel
        useful_values = [item for item in values if item.monto > 0]
        if not useful_values:
            layout.addWidget(QLabel("Sin clasificacion de gastos para mostrar."))
            return panel
        total = sum(item.monto for item in useful_values)
        layout.addWidget(DonutChart(useful_values, "Total", total))
        return panel

    def _build_budget_section(
        self,
        values: list[BudgetUsageValue],
    ) -> QFrame:
        """Construye panel de presupuesto variable versus gasto."""
        panel = self._panel("Presupuesto variable")
        layout = panel.layout()
        if not isinstance(layout, QVBoxLayout):
            return panel
        if not values:
            layout.addWidget(QLabel("Sin presupuestos variables para comparar."))
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

    def _build_fixed_payments_section(
        self,
        summary: FixedPaymentsSummary,
    ) -> QFrame:
        """Construye panel de cumplimiento de pagos fijos del mes."""
        panel = self._panel("Pagos fijos del mes")
        layout = panel.layout()
        if not isinstance(layout, QVBoxLayout):
            return panel
        if not summary.items:
            layout.addWidget(QLabel("Sin pagos fijos configurados."))
            return panel

        totals = QLabel(
            "Pagado "
            f"{self._format_clp(summary.total_fijo_pagado)} / "
            f"{self._format_clp(summary.total_fijo_esperado)} | "
            f"Pendiente {self._format_clp(summary.total_fijo_pendiente)}"
        )
        totals.setWordWrap(True)
        totals.setStyleSheet(
            f"font-size: 12px; font-weight: 700; color: {TEXT_MUTED};"
        )
        layout.addWidget(totals)

        for item in summary.items[:8]:
            layout.addWidget(self._fixed_payment_row(item))
        return panel

    def _fixed_payment_row(self, item: FixedPaymentValue) -> QWidget:
        """Crea fila compacta de un pago fijo mensual."""
        row = QFrame()
        row.setStyleSheet(
            f"background: {PANEL_SOFT}; border-radius: 7px; padding: 0;"
        )
        layout = QHBoxLayout(row)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(8)

        color = self._fixed_payment_color(item.estado)
        status = QLabel(self._fixed_payment_marker(item.estado))
        status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        status.setFixedSize(34, 24)
        status.setStyleSheet(
            f"background: {color}; color: white; border-radius: 6px; "
            "font-size: 10px; font-weight: 800;"
        )

        name = QLabel(item.nombre)
        name.setStyleSheet("font-size: 12px; font-weight: 700;")
        amount = QLabel(
            f"{self._format_clp(item.monto_pagado)} / "
            f"{self._format_clp(item.monto_esperado)}"
        )
        amount.setAlignment(Qt.AlignmentFlag.AlignRight)
        amount.setStyleSheet(f"font-size: 12px; color: {TEXT_MUTED};")
        state = QLabel(item.estado)
        state.setAlignment(Qt.AlignmentFlag.AlignRight)
        state.setStyleSheet(f"font-size: 12px; font-weight: 700; color: {color};")

        layout.addWidget(status)
        layout.addWidget(name, stretch=1)
        layout.addWidget(amount)
        layout.addWidget(state)
        return row

    def _build_alerts(self, alerts: list[FinancialAlert]) -> QFrame:
        """Construye panel de alertas financieras."""
        panel = self._panel("Alertas financieras")
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

    def _build_alert_details(self, alerts: list[FinancialAlert]) -> QFrame:
        """Construye el panel unico de alertas financieras."""
        panel = QFrame()
        panel.setObjectName("AlertDetailPanel")
        panel.setStyleSheet(
            """
            #AlertDetailPanel {
                background: %s;
                border: 1px solid %s;
                border-radius: 9px;
            }
            """
            % (PANEL, BORDER),
        )
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(8)

        title = QLabel("Alertas financieras")
        title.setStyleSheet("font-size: 15px; font-weight: 800;")
        layout.addWidget(title)

        if not alerts:
            empty = QLabel("No se detectaron alertas financieras relevantes.")
            empty.setStyleSheet(f"color: {TEXT_MUTED};")
            layout.addWidget(empty)
            return panel

        for alert in alerts:
            color = get_semantic_color(alert.nivel)
            item = QFrame()
            item.setStyleSheet(
                """
                QFrame {
                    background: %s;
                    border-left: 5px solid %s;
                    border-radius: 7px;
                }
                """
                % (self._alert_tint(color), color),
            )
            item_layout = QVBoxLayout(item)
            item_layout.setContentsMargins(12, 8, 12, 8)
            item_layout.setSpacing(3)

            item_title = QLabel(self._alert_title_text(alert))
            item_title.setStyleSheet(
                f"font-size: 13px; font-weight: 800; color: {color};"
            )
            item_message = QLabel(alert.mensaje)
            item_message.setWordWrap(True)
            item_message.setStyleSheet("font-size: 12px;")
            item_layout.addWidget(item_title)
            item_layout.addWidget(item_message)
            layout.addWidget(item)

        return panel

    @staticmethod
    def _alert_level_label(level: str) -> str:
        """Devuelve nivel de alerta legible para usuario."""
        mapping = {
            "critico": "Crítico",
            "advertencia": "Advertencia",
            "info": "Información",
        }
        return mapping.get(level.casefold(), level.capitalize())

    @staticmethod
    def _alert_title_text(alert: FinancialAlert) -> str:
        """Devuelve titulo de alerta sin simbolos propensos a fallar."""
        return (
            f"{DashboardPage._alert_level_label(alert.nivel)}: "
            f"{alert.titulo}"
        )

    @staticmethod
    def _alertas_relevantes(
        alerts: list[FinancialAlert],
    ) -> list[FinancialAlert]:
        """Filtra alertas informativas para la banda inferior."""
        relevant = [alert for alert in alerts if alert.nivel != "info"]
        return relevant or alerts

    @staticmethod
    def _alert_tint(color: str) -> str:
        """Devuelve fondo suave para banda de alerta."""
        mapping = {
            get_semantic_color("danger"): "#fff1f2",
            get_semantic_color("warning"): "#fff8e7",
            get_semantic_color("info"): "#effcff",
            get_semantic_color("success"): "#f0fff6",
        }
        return mapping.get(color, PANEL_SOFT)

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

    @staticmethod
    def _fixed_payment_color(estado: str) -> str:
        """Devuelve color visual para estado de pago fijo."""
        normalized = estado.casefold()
        if normalized == "pagado":
            return get_semantic_color("success")
        if normalized == "parcial":
            return get_semantic_color("warning")
        return get_semantic_color("neutral")

    @staticmethod
    def _fixed_payment_marker(estado: str) -> str:
        """Devuelve marcador textual para estado de pago fijo."""
        normalized = estado.casefold()
        if normalized == "pagado":
            return "OK"
        if normalized == "parcial":
            return "PAR"
        return "PEN"

    @staticmethod
    def _class_color(label: str) -> str:
        """Devuelve color consistente para clase de movimiento."""
        normalized = label.casefold()
        if normalized == "imprevisto":
            return get_semantic_color("warning")
        if normalized == "recurrente":
            return get_semantic_color("info")
        return get_semantic_color("neutral")

    @staticmethod
    def _card_symbol(title: str) -> str:
        """Devuelve un simbolo textual simple para la tarjeta."""
        mapping = {
            "Ingresos del mes": "$",
            "Gastos del mes": "-",
            "Flujo libre": "+",
            "Deuda total": "D",
            "Patrimonio neto": "P",
            "Imprevistos": "!",
        }
        return mapping.get(title, "i")

    @staticmethod
    def _card_tint(color: str) -> str:
        """Devuelve fondo suave para una tarjeta semantica."""
        mapping = {
            get_semantic_color("success"): "#f0fff6",
            get_semantic_color("warning"): "#fff8e7",
            get_semantic_color("danger"): "#fff1f2",
            get_semantic_color("danger_strong"): "#fff1f2",
            get_semantic_color("info"): "#effcff",
            get_semantic_color("neutral"): "#f8fafc",
        }
        return mapping.get(color, PANEL)

    def _month_label(self) -> str:
        """Entrega etiqueta del periodo activo para la cabecera."""
        month_names = {
            1: "Enero",
            2: "Febrero",
            3: "Marzo",
            4: "Abril",
            5: "Mayo",
            6: "Junio",
            7: "Julio",
            8: "Agosto",
            9: "Septiembre",
            10: "Octubre",
            11: "Noviembre",
            12: "Diciembre",
        }
        if self.year is None or self.month is None:
            return "Periodo actual"
        return f"{month_names.get(self.month, 'Mes')} {self.year}"

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
