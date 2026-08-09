"""Pagina CRUD de deudas para Avalancha V2."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from avalancha.models import Debt
from services.debt_analytics_service import (
    DebtAnalyticsService,
    PagoRecienteDeuda,
    ResumenTemporalDeuda,
)
from services.debt_service import DebtService
from services.monthly_closure_service import MonthlyClosureService
from ui_pyside6.color_system import get_debt_status_color
from ui_pyside6.pages.debt_dialog import DebtDialog


class SortableItem(QTableWidgetItem):
    """Item con valor interno para ordenar columnas."""

    def __init__(self, text: str, sort_value: object | None = None) -> None:
        """Inicializa texto visible y valor de orden."""
        super().__init__(text)
        self.sort_value = sort_value if sort_value is not None else text

    def __lt__(self, other: QTableWidgetItem) -> bool:
        """Compara usando valor interno si existe."""
        if isinstance(other, SortableItem):
            return self.sort_value < other.sort_value
        return super().__lt__(other)


class DebtsPage(QWidget):
    """CRUD de deudas del perfil activo usando DebtService."""

    HEADERS = [
        "Nombre",
        "Categoría",
        "Saldo actual",
        "Saldo mes anterior",
        "Disminución",
        "Pago mensual",
        "Interés est.",
        "Estado",
    ]

    def __init__(
        self,
        service: DebtService | None = None,
        closure_service: MonthlyClosureService | None = None,
        year: int | None = None,
        month: int | None = None,
    ) -> None:
        """Inicializa la pagina de deudas."""
        super().__init__()
        self.service = service or DebtService()
        self.closure_service = closure_service or MonthlyClosureService(
            repository=self.service.repository,
        )
        self.year = year
        self.month = month
        self.analytics_service = DebtAnalyticsService(
            repository=self.service.repository,
            debt_service=self.service,
        )
        self.table = QTableWidget()
        self.payments_table = QTableWidget()
        self.empty_payments_label = QLabel(
            "Sin pagos recientes de deuda registrados.",
        )
        self.summary_labels: dict[str, QLabel] = {}
        self._debts_by_id: dict[str, Debt] = {}
        self._build_ui()
        self.refresh()

    def refresh(self) -> None:
        """Actualiza la tabla desde el servicio."""
        self._populate_summary(
            self.analytics_service.obtener_resumen_temporal_deudas(),
        )
        self._populate_table(self.service.obtener_deudas())
        self._populate_payments_table(
            self.analytics_service.obtener_pagos_recientes(8),
        )

    def new_debt(self) -> None:
        """Abre dialogo para crear deuda."""
        if not self._confirm_closed_month():
            return
        dialog = DebtDialog(self.service, parent=self)
        if dialog.exec() != DebtDialog.DialogCode.Accepted:
            return
        try:
            self.service.crear_deuda(dialog.obtener_datos())
        except ValueError as exc:
            self._show_error(str(exc))
            return
        self.refresh()

    def edit_selected(self) -> None:
        """Edita la deuda seleccionada."""
        debt = self._selected_debt()
        if debt is None:
            self._show_info("Selecciona una deuda para editar.")
            return
        if not self._confirm_closed_month():
            return
        dialog = DebtDialog(self.service, debt, self)
        if dialog.exec() != DebtDialog.DialogCode.Accepted:
            return
        try:
            self.service.editar_deuda(debt.debt_id, dialog.obtener_datos())
        except ValueError as exc:
            self._show_error(str(exc))
            return
        self.refresh()

    def delete_selected(self) -> None:
        """Elimina la deuda seleccionada si no tiene movimientos."""
        debt = self._selected_debt()
        if debt is None:
            self._show_info("Selecciona una deuda para eliminar.")
            return
        if not self._confirm_closed_month():
            return
        response = QMessageBox.question(
            self,
            "Eliminar deuda",
            "Eliminar la deuda seleccionada?",
        )
        if response != QMessageBox.StandardButton.Yes:
            return
        try:
            self.service.eliminar_deuda(debt.debt_id)
        except ValueError as exc:
            self._show_error(str(exc))
            return
        self.refresh()

    def activate_selected(self) -> None:
        """Activa la deuda seleccionada."""
        self._change_selected_state(True)

    def deactivate_selected(self) -> None:
        """Desactiva la deuda seleccionada."""
        self._change_selected_state(False)

    def _build_ui(self) -> None:
        """Construye titulo, tabla y acciones."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 28, 28, 28)
        layout.setSpacing(16)

        title = QLabel("Deudas")
        title.setObjectName("PageTitle")

        self._configure_debt_table()
        self._configure_payments_table()

        payments_title = QLabel("Pagos recientes de deuda")
        payments_title.setObjectName("SectionTitle")

        buttons = self._build_buttons()

        layout.addWidget(title)
        layout.addWidget(self._build_summary_cards())
        layout.addWidget(self.table, stretch=2)
        layout.addWidget(payments_title)
        layout.addWidget(self.empty_payments_label)
        layout.addWidget(self.payments_table, stretch=1)
        layout.addLayout(buttons)

    def _configure_debt_table(self) -> None:
        """Configura tabla principal de deudas."""
        self.table.setColumnCount(len(self.HEADERS))
        self.table.setHorizontalHeaderLabels(self.HEADERS)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows,
        )
        self.table.setSelectionMode(
            QTableWidget.SelectionMode.SingleSelection,
        )
        self.table.setSortingEnabled(True)
        self.table.doubleClicked.connect(self.edit_selected)
        self.table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch,
        )

    def _configure_payments_table(self) -> None:
        """Configura tabla de pagos recientes."""
        headers = [
            "Fecha",
            "Deuda",
            "Cuenta",
            "Monto",
            "Saldo antes",
            "Saldo despues",
        ]
        self.payments_table.setColumnCount(len(headers))
        self.payments_table.setHorizontalHeaderLabels(headers)
        self.payments_table.setEditTriggers(
            QTableWidget.EditTrigger.NoEditTriggers,
        )
        self.payments_table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows,
        )
        self.payments_table.setSelectionMode(
            QTableWidget.SelectionMode.SingleSelection,
        )
        self.payments_table.setSortingEnabled(True)
        self.payments_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch,
        )

    def _build_buttons(self) -> QHBoxLayout:
        """Construye botones de accion de la pagina."""
        buttons = QHBoxLayout()
        new_button = QPushButton("Nueva deuda")
        edit_button = QPushButton("Editar")
        delete_button = QPushButton("Eliminar")
        activate_button = QPushButton("Activar")
        deactivate_button = QPushButton("Desactivar")
        refresh_button = QPushButton("Actualizar")

        new_button.clicked.connect(self.new_debt)
        edit_button.clicked.connect(self.edit_selected)
        delete_button.clicked.connect(self.delete_selected)
        activate_button.clicked.connect(self.activate_selected)
        deactivate_button.clicked.connect(self.deactivate_selected)
        refresh_button.clicked.connect(self.refresh)

        buttons.addStretch(1)
        buttons.addWidget(new_button)
        buttons.addWidget(edit_button)
        buttons.addWidget(delete_button)
        buttons.addWidget(activate_button)
        buttons.addWidget(deactivate_button)
        buttons.addWidget(refresh_button)
        return buttons

    def _build_summary_cards(self) -> QWidget:
        """Construye indicadores temporales de deuda."""
        container = QWidget()
        grid = QGridLayout(container)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(12)

        cards = [
            ("deuda_total", "Deuda total actual"),
            ("pagado_mes", "Pagado este mes"),
            ("variacion", "Variación mensual"),
            ("tendencia", "Tendencia"),
        ]
        for column, (key, title) in enumerate(cards):
            card = QFrame()
            card.setObjectName("SummaryCard")
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(14, 12, 14, 12)
            card_layout.setSpacing(4)

            title_label = QLabel(title)
            title_label.setObjectName("MutedLabel")
            value_label = QLabel("Sin datos")
            value_label.setObjectName("MetricValue")
            self.summary_labels[key] = value_label

            card_layout.addWidget(title_label)
            card_layout.addWidget(value_label)
            grid.addWidget(card, 0, column)
        return container

    def _populate_table(self, debts: list[Debt]) -> None:
        """Carga deudas en la tabla."""
        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)
        self._debts_by_id = {debt.debt_id: debt for debt in debts}
        category_labels = dict(self.service.categorias_disponibles())

        for row, debt in enumerate(debts):
            self.table.insertRow(row)
            decrease = self.service.calcular_disminucion_mensual(debt)
            interest = self.service.calcular_interes_estimado(debt)
            values = [
                (debt.name, debt.name.casefold()),
                (
                    category_labels.get(debt.category, debt.category),
                    debt.category,
                ),
                (self._format_clp(debt.current_balance), debt.current_balance),
                (
                    self._format_clp(debt.previous_month_balance),
                    debt.previous_month_balance,
                ),
                (self._format_clp(decrease), decrease),
                (
                    self._format_clp(debt.current_monthly_payment),
                    debt.current_monthly_payment,
                ),
                (self._format_clp(interest), interest),
                (self.service.estado_visual(debt), debt.active),
            ]
            for column, (text, sort_value) in enumerate(values):
                item = SortableItem(text, sort_value)
                if column == 0:
                    item.setData(Qt.ItemDataRole.UserRole, debt.debt_id)
                if column in {2, 3, 4, 5, 6}:
                    item.setTextAlignment(
                        Qt.AlignmentFlag.AlignRight
                        | Qt.AlignmentFlag.AlignVCenter,
                    )
                if column == 7:
                    item.setForeground(
                        QColor(get_debt_status_color(str(text))),
                    )
                self.table.setItem(row, column, item)
        self.table.setSortingEnabled(True)

    def _populate_summary(self, summary: ResumenTemporalDeuda) -> None:
        """Carga indicadores temporales de deuda."""
        values = {
            "deuda_total": self._format_clp(summary.deuda_total_actual),
            "pagado_mes": self._format_clp(summary.pagado_mes_actual),
            "variacion": self._format_clp(summary.variacion_deuda_mes),
            "tendencia": self._format_tendency(summary.tendencia),
        }
        for key, text in values.items():
            self.summary_labels[key].setText(text)

    def _populate_payments_table(
        self,
        payments: list[PagoRecienteDeuda],
    ) -> None:
        """Carga pagos recientes en la tabla secundaria."""
        self.payments_table.setSortingEnabled(False)
        self.payments_table.setRowCount(0)
        self.empty_payments_label.setVisible(not payments)
        self.payments_table.setVisible(bool(payments))

        for row, payment in enumerate(payments):
            self.payments_table.insertRow(row)
            values = [
                (self._format_date(payment.fecha), payment.fecha),
                (payment.deuda, payment.deuda.casefold()),
                (payment.cuenta, payment.cuenta.casefold()),
                (self._format_clp(payment.monto), payment.monto),
                (self._format_clp(payment.saldo_antes), payment.saldo_antes),
                (
                    self._format_clp(payment.saldo_despues),
                    payment.saldo_despues,
                ),
            ]
            for column, (text, sort_value) in enumerate(values):
                item = SortableItem(text, sort_value)
                if column in {3, 4, 5}:
                    item.setTextAlignment(
                        Qt.AlignmentFlag.AlignRight
                        | Qt.AlignmentFlag.AlignVCenter,
                    )
                self.payments_table.setItem(row, column, item)
        self.payments_table.setSortingEnabled(True)

    def _selected_debt(self) -> Debt | None:
        """Devuelve la deuda seleccionada."""
        row = self.table.currentRow()
        if row < 0:
            return None
        item = self.table.item(row, 0)
        if item is None:
            return None
        debt_id = item.data(Qt.ItemDataRole.UserRole)
        return self._debts_by_id.get(str(debt_id))

    def _change_selected_state(self, active: bool) -> None:
        """Cambia el estado de la deuda seleccionada."""
        debt = self._selected_debt()
        if debt is None:
            self._show_info("Selecciona una deuda.")
            return
        if not self._confirm_closed_month():
            return
        try:
            if active:
                self.service.activar_deuda(debt.debt_id)
            else:
                self.service.desactivar_deuda(debt.debt_id)
        except ValueError as exc:
            self._show_error(str(exc))
            return
        self.refresh()

    @staticmethod
    def _format_clp(amount: int) -> str:
        """Formatea monto CLP."""
        prefix = "-$" if amount < 0 else "$"
        return f"{prefix} {abs(amount):,.0f}".replace(",", ".")

    @staticmethod
    def _format_date(value: object) -> str:
        """Formatea fecha como dd-mm-aaaa."""
        return value.strftime("%d-%m-%Y")

    @staticmethod
    def _format_tendency(value: str) -> str:
        """Formatea tendencia para texto visible."""
        labels = {
            "sin_datos": "Sin datos",
            "bajando": "Bajando",
            "estable": "Estable",
            "subiendo": "Subiendo",
        }
        return labels.get(value, value.replace("_", " ").capitalize())

    def _show_error(self, message: str) -> None:
        """Muestra errores de servicio."""
        QMessageBox.critical(self, "Deudas", message)

    def _show_info(self, message: str) -> None:
        """Muestra mensajes informativos."""
        QMessageBox.information(self, "Deudas", message)

    def _confirm_closed_month(self) -> bool:
        """Pide confirmacion si el periodo activo esta cerrado."""
        if self.year is None or self.month is None:
            return True
        warning = self.closure_service.advertencia_modificacion_mes(
            self.year,
            self.month,
        )
        if not warning:
            return True
        response = QMessageBox.question(
            self,
            "Mes cerrado",
            warning + "\n\nQuieres continuar?",
        )
        return response == QMessageBox.StandardButton.Yes
