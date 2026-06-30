"""Pagina funcional de configuracion de Avalancha V2."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from core.models.configuracion import ConfiguracionAplicacion
from services.settings_service import SettingsService


class SettingsPage(QWidget):
    """Pantalla para editar configuracion persistida por perfil."""

    def __init__(self, service: SettingsService) -> None:
        """Inicializa la pagina usando exclusivamente el servicio."""
        super().__init__()
        self.service = service
        self.reportes_input = QLineEdit()
        self.respaldo_input = QLineEdit()
        self.moneda_combo = QComboBox()
        self.apariencia_combo = QComboBox()
        self.cifrado_check = QCheckBox("Mantener reportes cifrados")
        self.sincronizacion_check = QCheckBox("Preparar sincronizacion futura")
        self.estado_label = QLabel("")
        self._build_ui()
        self.reload()

    def reload(self) -> None:
        """Recarga valores desde el servicio."""
        self._load_config(self.service.cargar_configuracion())
        self.estado_label.setText("Configuracion cargada.")

    def save(self) -> None:
        """Solicita al servicio validar y guardar configuracion."""
        try:
            config = self.service.guardar_configuracion(self._collect_data())
        except ValueError as exc:
            self._show_error(str(exc))
            return
        self._load_config(config)
        self.estado_label.setText("Configuracion guardada.")

    def restore_defaults(self) -> None:
        """Restaura valores por defecto despues de confirmar."""
        response = QMessageBox.question(
            self,
            "Restaurar configuracion",
            "Restaurar valores por defecto del perfil activo?",
        )
        if response != QMessageBox.StandardButton.Yes:
            return
        config = self.service.restaurar_valores_por_defecto()
        self._load_config(config)
        self.estado_label.setText("Valores por defecto restaurados.")

    def select_reports_folder(self) -> None:
        """Permite elegir carpeta de reportes desde el sistema."""
        self._select_folder(self.reportes_input, "Seleccionar reportes")

    def select_backup_folder(self) -> None:
        """Permite elegir carpeta de respaldo desde el sistema."""
        self._select_folder(self.respaldo_input, "Seleccionar respaldo")

    def _build_ui(self) -> None:
        """Construye formulario y botones de accion."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 28, 28, 28)
        layout.setSpacing(16)

        title = QLabel("Configuracion")
        title.setObjectName("PageTitle")

        subtitle = QLabel(
            "Preferencias locales del perfil activo. "
            "La sincronizacion queda solo preparada para una etapa futura.",
        )
        subtitle.setObjectName("PageSubtitle")
        subtitle.setWordWrap(True)

        form = QFormLayout()
        form.setSpacing(12)
        form.addRow("Carpeta de reportes", self._folder_row(
            self.reportes_input,
            self.select_reports_folder,
        ))
        form.addRow("Moneda principal", self.moneda_combo)
        form.addRow("Apariencia", self.apariencia_combo)
        form.addRow("Cifrado", self.cifrado_check)
        form.addRow("Carpeta de respaldo", self._folder_row(
            self.respaldo_input,
            self.select_backup_folder,
        ))
        form.addRow("Sincronizacion", self.sincronizacion_check)

        buttons = QHBoxLayout()
        save_button = QPushButton("Guardar")
        cancel_button = QPushButton("Cancelar")
        defaults_button = QPushButton("Restaurar valores por defecto")
        save_button.clicked.connect(self.save)
        cancel_button.clicked.connect(self.reload)
        defaults_button.clicked.connect(self.restore_defaults)
        buttons.addStretch(1)
        buttons.addWidget(defaults_button)
        buttons.addWidget(cancel_button)
        buttons.addWidget(save_button)

        self.moneda_combo.addItems(SettingsService.MONEDAS_PERMITIDAS)
        self.apariencia_combo.addItems(
            item.capitalize()
            for item in SettingsService.APARIENCIAS_PERMITIDAS
        )
        self.estado_label.setObjectName("MutedText")

        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addLayout(form)
        layout.addWidget(self.estado_label)
        layout.addStretch(1)
        layout.addLayout(buttons)

    @staticmethod
    def _folder_row(
        line_edit: QLineEdit,
        callback: object,
    ) -> QWidget:
        """Crea fila visual para ruta y boton examinar."""
        wrapper = QWidget()
        layout = QHBoxLayout(wrapper)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        button = QPushButton("Examinar")
        button.clicked.connect(callback)  # type: ignore[arg-type]
        layout.addWidget(line_edit, stretch=1)
        layout.addWidget(button)
        return wrapper

    def _collect_data(self) -> dict[str, object]:
        """Recolecta datos crudos para validacion en servicio."""
        return {
            "carpeta_reportes": self.reportes_input.text(),
            "moneda_principal": self.moneda_combo.currentText(),
            "apariencia": self.apariencia_combo.currentText().lower(),
            "cifrado_reportes": self.cifrado_check.isChecked(),
            "carpeta_respaldo": self.respaldo_input.text(),
            "sincronizacion_habilitada": (
                self.sincronizacion_check.isChecked()
            ),
        }

    def _load_config(self, config: ConfiguracionAplicacion) -> None:
        """Muestra la configuracion actual en el formulario."""
        self.reportes_input.setText(str(config.carpeta_reportes))
        self.respaldo_input.setText(str(config.carpeta_respaldo or Path()))
        self.moneda_combo.setCurrentText(config.moneda_principal)
        self.apariencia_combo.setCurrentText(config.apariencia.capitalize())
        self.cifrado_check.setChecked(config.cifrado_reportes)
        self.sincronizacion_check.setChecked(
            config.sincronizacion_habilitada,
        )

    def _select_folder(self, input_field: QLineEdit, title: str) -> None:
        """Abre selector de carpeta y actualiza el campo si hay seleccion."""
        selected = QFileDialog.getExistingDirectory(
            self,
            title,
            input_field.text() or str(Path.cwd()),
        )
        if selected:
            input_field.setText(selected)

    def _show_error(self, message: str) -> None:
        """Muestra errores de validacion generados por el servicio."""
        QMessageBox.warning(self, "Configuracion", message)
