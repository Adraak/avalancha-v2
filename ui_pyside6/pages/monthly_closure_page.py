"""Pagina de cierre mensual para Avalancha V2."""

from __future__ import annotations

from datetime import date

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from core.models.monthly_closure import (
    MONTHLY_CLOSURE_CLOSED,
    MONTHLY_CLOSURE_OPEN,
    MONTHLY_CLOSURE_PENDING,
    MonthlyClosure,
)
from services.monthly_closure_service import MonthlyClosureService


class MonthlyClosurePage(QWidget):
    """Pantalla operativa para revisar y cerrar meses financieros."""

    STATUS_LABELS = {
        MONTHLY_CLOSURE_OPEN: "Abierto",
        MONTHLY_CLOSURE_PENDING: "Pendiente de cierre",
        MONTHLY_CLOSURE_CLOSED: "Cerrado",
    }

    def __init__(
        self,
        service: MonthlyClosureService | None = None,
        year: int | None = None,
        month: int | None = None,
    ) -> None:
        """Inicializa pagina de cierre mensual."""
        super().__init__()
        today = date.today()
        self.service = service or MonthlyClosureService()
        self.year_input = QSpinBox()
        self.month_input = QSpinBox()
        self.status_value = QLabel()
        self.message_label = QLabel()
        self.pending_label = QLabel()
        self.checks: dict[str, QCheckBox] = {}
        self._loading = False
        self._build_ui(year or today.year, month or today.month)
        self.refresh()

    def refresh(self) -> None:
        """Actualiza estado, checklist y pendientes."""
        year = self.year_input.value()
        month = self.month_input.value()
        closure = self.service.obtener_cierre(year, month)
        self._load_closure(closure)
        self._load_pending()

    def close_month(self) -> None:
        """Intenta cerrar el mes seleccionado."""
        try:
            closure = self.service.cerrar_mes(
                self.year_input.value(),
                self.month_input.value(),
            )
        except ValueError as exc:
            self._show_info(str(exc))
            self.refresh()
            return
        self._load_closure(closure)
        self._show_info("Mes cerrado correctamente.")

    def reopen_month(self) -> None:
        """Reabre el mes seleccionado."""
        response = QMessageBox.question(
            self,
            "Reabrir mes",
            "Reabrir el mes seleccionado?",
        )
        if response != QMessageBox.StandardButton.Yes:
            return
        closure = self.service.reabrir_mes(
            self.year_input.value(),
            self.month_input.value(),
        )
        self._load_closure(closure)

    def _build_ui(self, year: int, month: int) -> None:
        """Construye controles principales de cierre."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 28, 28, 28)
        layout.setSpacing(16)

        title = QLabel("Cierre mensual")
        title.setObjectName("PageTitle")

        selector = QHBoxLayout()
        self.month_input.setRange(1, 12)
        self.month_input.setValue(month)
        self.month_input.valueChanged.connect(self.refresh)
        self.year_input.setRange(2000, 2100)
        self.year_input.setValue(year)
        self.year_input.valueChanged.connect(self.refresh)
        selector.addWidget(QLabel("Mes"))
        selector.addWidget(self.month_input)
        selector.addWidget(QLabel("Año"))
        selector.addWidget(self.year_input)
        selector.addStretch(1)

        status_row = QHBoxLayout()
        status_title = QLabel("Estado del mes:")
        status_title.setObjectName("SectionTitle")
        self.status_value.setObjectName("SectionTitle")
        status_row.addWidget(status_title)
        status_row.addWidget(self.status_value)
        status_row.addStretch(1)

        checklist = self._build_checklist()

        buttons = QHBoxLayout()
        close_button = QPushButton("Cerrar mes")
        reopen_button = QPushButton("Reabrir mes")
        refresh_button = QPushButton("Actualizar")
        close_button.clicked.connect(self.close_month)
        reopen_button.clicked.connect(self.reopen_month)
        refresh_button.clicked.connect(self.refresh)
        buttons.addStretch(1)
        buttons.addWidget(close_button)
        buttons.addWidget(reopen_button)
        buttons.addWidget(refresh_button)

        self.message_label.setObjectName("MutedText")
        self.pending_label.setObjectName("MutedText")
        self.pending_label.setWordWrap(True)

        layout.addWidget(title)
        layout.addLayout(selector)
        layout.addLayout(status_row)
        layout.addWidget(checklist)
        layout.addWidget(self.message_label)
        layout.addWidget(self.pending_label)
        layout.addStretch(1)
        layout.addLayout(buttons)

    def _build_checklist(self) -> QWidget:
        """Construye checklist de revision mensual."""
        wrapper = QWidget()
        grid = QGridLayout(wrapper)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(20)
        grid.setVerticalSpacing(12)

        items = [
            ("movements_reviewed", "Movimientos revisados"),
            ("accounts_reconciled", "Cuentas conciliadas"),
            ("debts_reviewed", "Deudas revisadas"),
            ("budgets_reviewed", "Presupuestos revisados"),
            ("report_generated", "Reporte generado"),
        ]
        for index, (key, text) in enumerate(items):
            checkbox = QCheckBox(text)
            checkbox.stateChanged.connect(
                lambda _state=0, current=key: self._update_flag(current),
            )
            self.checks[key] = checkbox
            grid.addWidget(checkbox, index // 2, index % 2)
        return wrapper

    def _update_flag(self, key: str) -> None:
        """Persiste un punto de checklist desde la UI."""
        if self._loading:
            return
        value = self.checks[key].isChecked()
        year = self.year_input.value()
        month = self.month_input.value()
        actions = {
            "movements_reviewed": self.service.marcar_movimientos_revisados,
            "accounts_reconciled": self.service.marcar_cuentas_conciliadas,
            "debts_reviewed": self.service.marcar_deudas_revisadas,
            "budgets_reviewed": self.service.marcar_presupuestos_revisados,
            "report_generated": self.service.marcar_reporte_generado,
        }
        closure = actions[key](year, month, value)
        self._load_closure(closure)

    def _load_closure(self, closure: MonthlyClosure) -> None:
        """Carga estado visible del cierre mensual."""
        self._loading = True
        values = {
            "movements_reviewed": closure.movements_reviewed,
            "accounts_reconciled": closure.accounts_reconciled,
            "debts_reviewed": closure.debts_reviewed,
            "budgets_reviewed": closure.budgets_reviewed,
            "report_generated": closure.report_generated,
        }
        for key, value in values.items():
            checkbox = self.checks[key]
            checkbox.blockSignals(True)
            checkbox.setChecked(value)
            checkbox.setEnabled(closure.status != MONTHLY_CLOSURE_CLOSED)
            checkbox.blockSignals(False)
        self._loading = False

        self.status_value.setText(
            self.STATUS_LABELS.get(closure.status, closure.status),
        )
        missing = closure.faltantes()
        if closure.status == MONTHLY_CLOSURE_CLOSED:
            self.message_label.setText(
                "Mes cerrado. Los cambios posteriores requieren confirmacion.",
            )
        elif missing:
            self.message_label.setText(
                "Pendiente para cerrar: " + ", ".join(missing) + ".",
            )
        else:
            self.message_label.setText("Checklist completo. El mes puede cerrarse.")

    def _load_pending(self) -> None:
        """Muestra meses anteriores pendientes de cierre."""
        pending = self.service.obtener_meses_pendientes()
        if not pending:
            self.pending_label.setText("No hay cierres mensuales pendientes.")
            return
        labels = ", ".join(item.label for item in pending)
        self.pending_label.setText(f"Cierres mensuales pendientes: {labels}.")

    def _show_info(self, message: str) -> None:
        """Muestra mensaje operativo de cierre."""
        QMessageBox.information(self, "Cierre mensual", message)
