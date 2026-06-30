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
from services.demo_profile_service import DemoProfileService
from services.movement_service import MovementService
from services.profile_service import ProfileService
from services.reconciliation_service import ReconciliationService
from services.report_service import ReportService
from ui_pyside6.pages.accounts_page import AccountsPage
from ui_pyside6.pages.budgets_page import BudgetsPage
from ui_pyside6.pages.dashboard_page import DashboardPage
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

    def __init__(self) -> None:
        """Inicializa la ventana principal y su navegacion."""
        super().__init__()
        self.setWindowTitle("Avalancha V2")
        self.resize(1200, 750)
        self.setMinimumSize(980, 640)
        self.setStyleSheet(hoja_estilos())
        self.profile_service = ProfileService()
        self.demo_service = DemoProfileService(self.profile_service)
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
        return menu

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
        movement_service = MovementService(data_dir=data_dir)
        budget_service = BudgetService(data_dir=data_dir)
        account_service = AccountService(data_dir=data_dir)
        reconciliation_service = ReconciliationService(data_dir=data_dir)
        report_service = ReportService(
            data_dir=data_dir,
            reports_dir=profile.reports_dir,
            key_path=profile.key_path,
        )
        profiles_page = ProfilesPage(
            self.profile_service,
            self.demo_service,
        )
        profiles_page.profile_changed.connect(self._reload_profile)
        return [
            NavigationItem("Dashboard", DashboardPage(data_dir=data_dir)),
            NavigationItem("Movimientos", MovementsPage(movement_service)),
            NavigationItem("Cuentas", AccountsPage(account_service)),
            NavigationItem("Presupuestos", BudgetsPage(budget_service)),
            NavigationItem("Reportes", ReportsPage(report_service)),
            NavigationItem(
                "Conciliacion",
                ReconciliationPage(reconciliation_service),
            ),
            NavigationItem("Perfiles", profiles_page),
            NavigationItem("Configuracion", SettingsPage()),
        ]

    def _select_section(self, index: int) -> None:
        """Cambia la pagina central y actualiza el estado inferior."""
        if index < 0 or index >= self.stack.count():
            return
        self.stack.setCurrentIndex(index)
        button = self.navigation_buttons[index]
        button.setChecked(True)
        section = button.text()
        self.active_section_label.setText(f"Seccion activa: {section}")

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
