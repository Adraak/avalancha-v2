"""Pagina funcional de perfiles locales para Avalancha V2."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
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

from services.demo_profile_service import DemoProfileService
from services.profile_service import PERFIL_DEMO, PERFIL_PERSONAL, ProfileService
from ui_pyside6.pages.profile_dialog import ProfileDialog


class ProfilesPage(QWidget):
    """Administra seleccion basica de perfiles locales."""

    profile_changed = Signal()
    HEADERS = ["Perfil", "ID", "Activo"]

    def __init__(
        self,
        profile_service: ProfileService | None = None,
        demo_service: DemoProfileService | None = None,
    ) -> None:
        """Inicializa la pantalla de perfiles."""
        super().__init__()
        self.profile_service = profile_service or ProfileService()
        self.demo_service = demo_service or DemoProfileService(
            self.profile_service,
        )
        self.active_label = QLabel()
        self.table = QTableWidget()
        self._build_ui()
        self.refresh()

    def refresh(self) -> None:
        """Actualiza perfil activo y tabla."""
        active = self.profile_service.obtener_activo()
        self.active_label.setText(f"Perfil activo: {active.nombre}")
        profiles = self.profile_service.listar_perfiles()
        self.table.setRowCount(0)
        for row, profile in enumerate(profiles):
            self.table.insertRow(row)
            values = [
                profile.nombre,
                profile.id,
                "Si" if profile.activo else "No",
            ]
            for column, text in enumerate(values):
                item = QTableWidgetItem(text)
                if column == 0:
                    item.setData(Qt.ItemDataRole.UserRole, profile.id)
                self.table.setItem(row, column, item)

    def open_selected(self) -> None:
        """Activa el perfil seleccionado."""
        profile_id = self._selected_profile_id()
        if not profile_id:
            self._show_info("Selecciona un perfil para abrir.")
            return
        try:
            self.profile_service.seleccionar_perfil(profile_id)
        except ValueError as exc:
            self._show_error(str(exc))
            return
        self.profile_changed.emit()

    def open_demo(self) -> None:
        """Crea si falta y activa el Perfil Demo."""
        try:
            self.demo_service.abrir_demo()
        except ValueError as exc:
            self._show_error(str(exc))
            return
        self.profile_changed.emit()

    def regenerate_demo(self) -> None:
        """Regenera datos ficticios del Perfil Demo con confirmacion."""
        response = QMessageBox.warning(
            self,
            "Regenerar Perfil Demo",
            (
                "Esto reemplazara los datos ficticios del Perfil Demo. "
                "No afecta tus datos reales."
            ),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if response != QMessageBox.StandardButton.Yes:
            return
        try:
            self.demo_service.regenerar_demo()
            self.profile_service.seleccionar_perfil(PERFIL_DEMO)
        except ValueError as exc:
            self._show_error(str(exc))
            return
        self.profile_changed.emit()

    def open_personal(self) -> None:
        """Vuelve al perfil personal."""
        try:
            self.profile_service.seleccionar_perfil(PERFIL_PERSONAL)
        except ValueError as exc:
            self._show_error(str(exc))
            return
        self.profile_changed.emit()

    def create_profile(self) -> None:
        """Crea un perfil vacio."""
        dialog = ProfileDialog(self)
        if dialog.exec() != ProfileDialog.DialogCode.Accepted:
            return
        try:
            profile = self.profile_service.crear_perfil(dialog.nombre())
            self.profile_service.seleccionar_perfil(profile.id)
        except ValueError as exc:
            self._show_error(str(exc))
            return
        self.profile_changed.emit()

    def _build_ui(self) -> None:
        """Construye tabla y acciones."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 28, 28, 28)
        layout.setSpacing(16)

        title = QLabel("Perfiles")
        title.setObjectName("PageTitle")
        self.active_label.setObjectName("PageSubtitle")

        self.table.setColumnCount(len(self.HEADERS))
        self.table.setHorizontalHeaderLabels(self.HEADERS)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows,
        )
        self.table.setSelectionMode(
            QTableWidget.SelectionMode.SingleSelection,
        )
        self.table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch,
        )
        self.table.doubleClicked.connect(self.open_selected)

        buttons = QHBoxLayout()
        open_button = QPushButton("Cambiar perfil")
        personal_button = QPushButton("Abrir Personal")
        demo_button = QPushButton("Abrir Perfil Demo")
        regenerate_button = QPushButton("Regenerar Demo")
        new_button = QPushButton("Crear perfil nuevo")

        open_button.clicked.connect(self.open_selected)
        personal_button.clicked.connect(self.open_personal)
        demo_button.clicked.connect(self.open_demo)
        regenerate_button.clicked.connect(self.regenerate_demo)
        new_button.clicked.connect(self.create_profile)

        buttons.addStretch(1)
        buttons.addWidget(open_button)
        buttons.addWidget(personal_button)
        buttons.addWidget(demo_button)
        buttons.addWidget(regenerate_button)
        buttons.addWidget(new_button)

        layout.addWidget(title)
        layout.addWidget(self.active_label)
        layout.addWidget(self.table, stretch=1)
        layout.addLayout(buttons)

    def _selected_profile_id(self) -> str | None:
        """Devuelve ID del perfil seleccionado."""
        row = self.table.currentRow()
        if row < 0:
            return None
        item = self.table.item(row, 0)
        if item is None:
            return None
        return str(item.data(Qt.ItemDataRole.UserRole))

    def _show_error(self, message: str) -> None:
        """Muestra errores del servicio."""
        QMessageBox.critical(self, "Perfiles", message)

    def _show_info(self, message: str) -> None:
        """Muestra mensajes informativos."""
        QMessageBox.information(self, "Perfiles", message)
