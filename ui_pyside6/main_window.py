"""Ventana principal de Avalancha V2."""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from services.account_service import AccountService
from services.budget_service import BudgetService
from services.category_service import CategoryService
from services.demo_profile_service import DemoProfileService
from services.debt_service import DebtService
from services.movement_service import MovementService
from services.monthly_closure_service import MonthlyClosureService
from services.profile_service import PERFIL_DEMO, ProfileService
from services.reconciliation_service import ReconciliationService
from services.report_service import ReportService
from services.settings_service import SettingsService
from ui_pyside6.pages.accounts_page import AccountsPage
from ui_pyside6.pages.budgets_page import BudgetsPage
from ui_pyside6.pages.categories_page import CategoriesPage
from ui_pyside6.pages.dashboard_page import DashboardPage
from ui_pyside6.pages.debts_page import DebtsPage
from ui_pyside6.pages.monthly_closure_page import MonthlyClosurePage
from ui_pyside6.pages.movements_page import MovementsPage
from ui_pyside6.pages.profiles_page import ProfilesPage
from ui_pyside6.pages.reconciliation_page import ReconciliationPage
from ui_pyside6.pages.reports_page import ReportsPage
from ui_pyside6.pages.settings_page import SettingsPage
from ui_pyside6.theme import hoja_estilos


@dataclass(frozen=True)
class NavigationItem:
    """Define una seccion navegable del chasis visual."""

    name: str
    widget: QWidget


class MainWindow(QMainWindow):
    """Chasis visual principal de Avalancha V2 en PySide6."""

    def __init__(
        self,
        profile_service: ProfileService | None = None,
        demo_service: DemoProfileService | None = None,
    ) -> None:
        """Inicializa la ventana principal y su navegacion."""
        super().__init__()
        self.setWindowTitle("Avalancha V2")
        self.resize(1200, 750)
        self.setMinimumSize(980, 640)
        self.setStyleSheet(hoja_estilos())
        self.profile_service = profile_service or ProfileService()
        self.demo_service = demo_service or DemoProfileService(
            self.profile_service,
        )
        self._ensure_active_demo_data()
        self.active_profile = self.profile_service.obtener_activo()
        self.profile_name = self.active_profile.nombre
        self.navigation_buttons: list[QPushButton] = []
        self.button_group = QButtonGroup(self)
        self.button_group.setExclusive(True)
        self.stack = QStackedWidget()
        self.active_section_label = QLabel()
        self.profile_label = QLabel()
        self._build_ui()
        self._select_section(0)

    def _ensure_active_demo_data(self) -> None:
        """Asegura datos demo completos si el perfil activo es Demo."""
        active = self.profile_service.obtener_activo()
        if active.id == PERFIL_DEMO:
            self.demo_service.asegurar_demo()

    def _build_ui(self) -> None:
        """Construye la estructura general de la ventana."""
        root = QWidget(self)
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        root_layout.addWidget(self._build_top_bar())
        root_layout.addWidget(self._build_body(), stretch=1)
        root_layout.addWidget(self._build_status_bar())

        self.setCentralWidget(root)

    def _build_top_bar(self) -> QWidget:
        """Construye la barra superior con app y perfil activo."""
        bar = QFrame()
        bar.setObjectName("TopBar")
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(24, 16, 24, 16)
        layout.setSpacing(16)

        title_box = QVBoxLayout()
        title_box.setSpacing(2)

        title = QLabel("Avalancha")
        title.setObjectName("AppTitle")

        subtitle = QLabel("Sistema de control financiero personal")
        subtitle.setObjectName("AppSubtitle")

        title_box.addWidget(title)
        title_box.addWidget(subtitle)

        self.profile_label = QLabel(f"Perfil: {self.profile_name}")
        self.profile_label.setObjectName("ProfileLabel")
        self.profile_label.setAlignment(Qt.AlignmentFlag.AlignRight)

        layout.addLayout(title_box, stretch=1)
        layout.addWidget(self.profile_label)
        return bar

    def _build_body(self) -> QWidget:
        """Construye menu lateral y area central."""
        body = QWidget()
        layout = QHBoxLayout(body)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        layout.addWidget(self._build_side_menu())
        layout.addWidget(self._build_content_area(), stretch=1)
        return body

    def _build_side_menu(self) -> QWidget:
        """Construye el menu lateral de navegacion."""
        menu = QFrame()
        menu.setObjectName("SideMenu")
        menu.setFixedWidth(210)

        layout = QVBoxLayout(menu)
        layout.setContentsMargins(14, 20, 14, 20)
        layout.setSpacing(8)

        for index, item in enumerate(self._navigation_items()):
            button = QPushButton(item.name)
            button.setCheckable(True)
            button.setProperty("menuButton", True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(
                lambda checked=False, current=index: (
                    self._select_section(current)
                ),
            )
            self.button_group.addButton(button, index)
            self.navigation_buttons.append(button)
            self.stack.addWidget(item.widget)
            layout.addWidget(button)

        layout.addStretch(1)
        layout.addWidget(self._build_profile_badge())
        return menu

    def _build_profile_badge(self) -> QWidget:
        """Construye bloque inferior con perfil activo."""
        badge = QFrame()
        badge.setObjectName("ProfileBadge")
        badge.setStyleSheet(
            """
            #ProfileBadge {
                background: #0d2035;
                border: 1px solid #173653;
                border-radius: 10px;
            }
            """
        )
        layout = QVBoxLayout(badge)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(3)

        label = QLabel("Perfil activo")
        label.setStyleSheet("color: #9fb2c7; font-size: 11px;")
        value = QLabel(self.profile_name)
        value.setStyleSheet("color: #ffffff; font-size: 13px; font-weight: 700;")

        layout.addWidget(label)
        layout.addWidget(value)
        return badge

    def _build_content_area(self) -> QWidget:
        """Construye el panel central dinamico."""
        wrapper = QWidget()
        wrapper_layout = QVBoxLayout(wrapper)
        wrapper_layout.setContentsMargins(22, 22, 22, 22)
        wrapper_layout.setSpacing(0)

        panel = QFrame()
        panel.setObjectName("ContentPanel")
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(0, 0, 0, 0)
        panel_layout.addWidget(self.stack)

        wrapper_layout.addWidget(panel)
        return wrapper

    def _build_status_bar(self) -> QWidget:
        """Construye la barra inferior con estado y seccion activa."""
        status = QFrame()
        status.setObjectName("StatusBar")
        layout = QHBoxLayout(status)
        layout.setContentsMargins(22, 9, 22, 9)
        layout.setSpacing(14)

        left = QLabel("Estado: Listo")
        left.setObjectName("StatusText")

        version = QLabel("Avalancha V2 - PySide6")
        version.setObjectName("StatusText")
        version.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.active_section_label.setObjectName("StatusText")
        self.active_section_label.setAlignment(Qt.AlignmentFlag.AlignRight)

        layout.addWidget(left)
        layout.addWidget(version, stretch=1)
        layout.addWidget(self.active_section_label)
        return status

    def _navigation_items(self) -> list[NavigationItem]:
        """Devuelve las paginas disponibles para el perfil activo."""
        profile = self.profile_service.obtener_activo()
        data_dir = profile.data_dir
        year, month = self.profile_service.obtener_periodo_trabajo(profile.id)
        category_service = CategoryService(data_dir=data_dir)
        movement_service = MovementService(
            data_dir=data_dir,
            year=year,
            month=month,
            category_service=category_service,
        )
        budget_service = BudgetService(
            data_dir=data_dir,
            year=year,
            month=month,
            category_service=category_service,
        )
        account_service = AccountService(
            data_dir=data_dir,
            year=year,
            month=month,
        )
        debt_service = DebtService(data_dir=data_dir)
        monthly_closure_service = MonthlyClosureService(data_dir=data_dir)
        reconciliation_service = ReconciliationService(
            data_dir=data_dir,
            year=year,
            month=month,
        )
        settings_service = SettingsService(
            config_dir=profile.config_dir,
            reports_dir=profile.reports_dir,
            backup_dir=profile.raiz / "backup",
        )
        settings = settings_service.cargar_configuracion()
        report_service = ReportService(
            data_dir=data_dir,
            reports_dir=settings.carpeta_reportes,
            key_path=profile.key_path,
        )
        movements_page = MovementsPage(
            movement_service,
            closure_service=monthly_closure_service,
        )
        accounts_page = AccountsPage(account_service)
        accounts_page.movements_requested.connect(
            self._open_account_movements,
        )
        movements_page.movements_changed.connect(
            self.refresh_financial_views,
        )
        profiles_page = ProfilesPage(
            self.profile_service,
            self.demo_service,
        )
        profiles_page.profile_changed.connect(self._reload_profile)
        return [
            NavigationItem(
                "Resumen",
                DashboardPage(data_dir=data_dir, year=year, month=month),
            ),
            NavigationItem("Movimientos", movements_page),
            NavigationItem("Cuentas", accounts_page),
            NavigationItem(
                "Presupuestos",
                BudgetsPage(
                    budget_service,
                    closure_service=monthly_closure_service,
                ),
            ),
            NavigationItem("Categorías", CategoriesPage(category_service)),
            NavigationItem(
                "Deudas",
                DebtsPage(
                    debt_service,
                    closure_service=monthly_closure_service,
                    year=year,
                    month=month,
                ),
            ),
            NavigationItem(
                "Reportes",
                ReportsPage(
                    report_service,
                    closure_service=monthly_closure_service,
                ),
            ),
            NavigationItem(
                "Cierre mensual",
                MonthlyClosurePage(monthly_closure_service, year, month),
            ),
            NavigationItem(
                "Conciliacion",
                ReconciliationPage(reconciliation_service),
            ),
            NavigationItem("Perfiles", profiles_page),
            NavigationItem("Configuración", SettingsPage(settings_service)),
        ]

    def _select_section(self, index: int) -> None:
        """Cambia la pagina central y actualiza el estado inferior."""
        if index < 0 or index >= self.stack.count():
            return
        self.stack.setCurrentIndex(index)
        button = self.navigation_buttons[index]
        button.setChecked(True)
        section = button.text()
        self.active_section_label.setText(f"Sección activa: {section}")
        self._refresh_widget(self.stack.currentWidget())

    def refresh_financial_views(self, reason: str = "") -> None:
        """Recarga paginas financieras despues de cambiar movimientos."""
        _ = reason
        for page_index in range(self.stack.count()):
            self._refresh_widget(self.stack.widget(page_index))

    @staticmethod
    def _refresh_widget(widget: QWidget | None) -> None:
        """Invoca refresh si la pagina expone recarga de datos."""
        if widget is None:
            return
        refresh = getattr(widget, "refresh", None)
        if callable(refresh):
            refresh()

    def _open_account_movements(
        self,
        cuenta_id: str,
        cuenta_nombre: str,
    ) -> None:
        """Abre Movimientos filtrando por la cuenta solicitada."""
        for index in range(self.stack.count()):
            widget = self.stack.widget(index)
            if isinstance(widget, MovementsPage):
                widget.filtrar_por_cuenta(cuenta_id, cuenta_nombre)
                self._select_section(index)
                return

    def _reload_profile(self) -> None:
        """Reconstruye las paginas al cambiar el perfil activo."""
        current_index = self.stack.currentIndex()
        self.active_profile = self.profile_service.obtener_activo()
        self.profile_name = self.active_profile.nombre
        self.navigation_buttons = []
        self.button_group = QButtonGroup(self)
        self.button_group.setExclusive(True)
        self.stack = QStackedWidget()
        self.active_section_label = QLabel()
        self._build_ui()
        self._select_section(min(current_index, self.stack.count() - 1))
