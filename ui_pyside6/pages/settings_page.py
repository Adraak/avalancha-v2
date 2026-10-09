"""Pagina funcional de configuracion de Avalancha V2."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Signal
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

from core.models.backup import BackupError
from core.models.configuracion import ConfiguracionAplicacion
from services.backup_service import BackupValidator, ProfileBackupService
from services.error_reporting_service import SafeErrorReporter
from services.profile_restore_service import ProfileRestoreService
from services.profile_service import PerfilAplicacion
from services.settings_service import SettingsService


class SettingsPage(QWidget):
    """Pantalla para editar configuracion persistida por perfil."""

    profile_restored = Signal()

    def __init__(
        self,
        service: SettingsService,
        profile: PerfilAplicacion | None = None,
        backup_service: ProfileBackupService | None = None,
        backup_validator: BackupValidator | None = None,
        restore_service: ProfileRestoreService | None = None,
        error_reporter: SafeErrorReporter | None = None,
    ) -> None:
        """Inicializa configuracion y acciones seguras del perfil activo."""
        super().__init__()
        self.service = service
        self.profile = profile
        self.backup_service = backup_service or ProfileBackupService()
        self.backup_validator = backup_validator or BackupValidator()
        self.restore_service = restore_service or ProfileRestoreService()
        self.error_reporter = error_reporter or SafeErrorReporter()
        self.reportes_input = QLineEdit()
        self.respaldo_input = QLineEdit()
        self.moneda_combo = QComboBox()
        self.apariencia_combo = QComboBox()
        self.cifrado_check = QCheckBox("Mantener reportes cifrados")
        self.sincronizacion_check = QCheckBox("Preparar sincronización futura")
        self.create_backup_button = QPushButton("Crear respaldo ahora")
        self.restore_backup_button = QPushButton("Restaurar respaldo...")
        enabled = profile is not None
        self.create_backup_button.setEnabled(enabled)
        self.restore_backup_button.setEnabled(enabled)
        self.estado_label = QLabel("")
        self._build_ui()
        self.reload()

    def reload(self) -> None:
        """Recarga valores desde el servicio."""
        self._load_config(self.service.cargar_configuracion())
        self.estado_label.setText("Configuración cargada.")

    def save(self) -> None:
        """Solicita al servicio validar y guardar configuracion."""
        try:
            config = self.service.guardar_configuracion(self._collect_data())
        except ValueError as exc:
            self._show_error(str(exc))
            return
        except (OSError, RuntimeError) as exc:
            self._show_error(
                self._technical_error(
                    exc,
                    context="settings.save",
                    fallback="No fue posible guardar la configuración.",
                ),
            )
            return
        self._load_config(config)
        self.estado_label.setText("Configuración guardada.")

    def restore_defaults(self) -> None:
        """Restaura valores por defecto despues de confirmar."""
        response = QMessageBox.question(
            self,
            "Restaurar configuración",
            "Restaurar valores por defecto del perfil activo?",
        )
        if response != QMessageBox.StandardButton.Yes:
            return
        try:
            config = self.service.restaurar_valores_por_defecto()
        except ValueError as exc:
            self._show_error(str(exc))
            return
        except (OSError, RuntimeError) as exc:
            self._show_error(
                self._technical_error(
                    exc,
                    context="settings.defaults",
                    fallback="No fue posible restaurar la configuración.",
                ),
            )
            return
        self._load_config(config)
        self.estado_label.setText("Valores por defecto restaurados.")

    def select_reports_folder(self) -> None:
        """Permite elegir carpeta de reportes desde el sistema."""
        self._select_folder(self.reportes_input, "Seleccionar reportes")

    def select_backup_folder(self) -> None:
        """Permite elegir carpeta de respaldo desde el sistema."""
        self._select_folder(self.respaldo_input, "Seleccionar respaldo")

    def create_backup(self) -> None:
        """Crea un respaldo verificado del perfil activo."""
        if self.profile is None:
            self._show_backup_error(
                "No hay un perfil activo disponible para respaldar.",
            )
            return
        try:
            result = self.backup_service.crear_backup(
                self.profile,
                self.service,
            )
        except (BackupError, ValueError, OSError, RuntimeError) as exc:
            self._show_backup_error(
                self._technical_error(
                    exc,
                    context="settings.backup.create",
                    fallback="No fue posible crear el respaldo.",
                ),
            )
            return
        self.estado_label.setText(f"Respaldo creado: {result.zip_path}")
        QMessageBox.information(
            self,
            "Respaldo creado",
            f"El respaldo se creó correctamente en:\n{result.zip_path}",
        )

    def restore_backup(self) -> None:
        """Valida, confirma y restaura un ZIP sobre el perfil activo."""
        if self.profile is None:
            self._show_backup_error(
                "No hay un perfil activo disponible para restaurar.",
            )
            return

        selected, _ = QFileDialog.getOpenFileName(
            self,
            "Seleccionar respaldo",
            self.respaldo_input.text() or str(Path.cwd()),
            "Respaldos ZIP (*.zip)",
        )
        if not selected:
            return

        zip_path = Path(selected)
        try:
            validation = self.backup_validator.validar_backup(
                zip_path,
                expected_profile_id=self.profile.id,
            )
        except (BackupError, ValueError, OSError, RuntimeError) as exc:
            self._show_backup_error(
                self._technical_error(
                    exc,
                    context="settings.backup.validate",
                    fallback="No fue posible validar el respaldo seleccionado.",
                ),
            )
            return

        if not validation.valid:
            if validation.error is None:
                message = "El respaldo seleccionado no es válido."
            else:
                message = self._technical_error(
                    validation.error,
                    context="settings.backup.invalid",
                    fallback=(
                        "El respaldo seleccionado no es válido o no "
                        "corresponde al perfil activo."
                    ),
                )
            self._show_backup_error(message)
            return

        response = QMessageBox.question(
            self,
            "Restaurar respaldo",
            (
                "La restauración reemplazará los datos administrados del "
                "perfil activo para que coincidan con el respaldo.\n\n"
                "Si el respaldo incluye reporte.key, también puede "
                "reemplazar la unidad criptográfica de reportes.\n\n"
                "¿Continuar con la restauración?"
            ),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if response != QMessageBox.StandardButton.Yes:
            return

        try:
            result = self.restore_service.restaurar(zip_path, self.profile)
        except (BackupError, ValueError, OSError, RuntimeError) as exc:
            self._show_backup_error(
                self._technical_error(
                    exc,
                    context="settings.restore.execute",
                    fallback="No fue posible restaurar el respaldo.",
                ),
            )
            return

        if result.outcome == "APPLIED":
            self.estado_label.setText("Respaldo restaurado correctamente.")
            QMessageBox.information(
                self,
                "Restauración completada",
                "El perfil activo fue restaurado correctamente.",
            )
            self.profile_restored.emit()
            return

        detail = (
            self._technical_error(
                result.error,
                context="settings.restore.result",
                fallback="La restauración no pudo completarse.",
            )
            if result.error is not None
            else "La restauración no pudo completarse."
        )
        if result.outcome == "FAILED_ROLLBACK_OK":
            self.estado_label.setText(
                "Restauración fallida; cambios revertidos correctamente.",
            )
            QMessageBox.warning(
                self,
                "Restauración revertida",
                (
                    f"{detail}\n\n"
                    "Los cambios parciales fueron revertidos y el perfil "
                    "conserva su estado anterior."
                ),
            )
            return

        self.estado_label.setText(
            "Restauración fallida y rollback incompleto.",
        )
        evidence = (
            "\n\nSe conservó evidencia técnica local para diagnóstico."
            if result.staging_dir is not None
            else ""
        )
        QMessageBox.critical(
            self,
            "Restauración incompleta",
            (
                f"{detail}\n\n"
                "No fue posible revertir por completo la restauración. "
                "No continúe modificando el perfil hasta diagnosticarlo."
                f"{evidence}"
            ),
        )

    def _build_ui(self) -> None:
        """Construye formulario y botones de accion."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 28, 28, 28)
        layout.setSpacing(16)

        title = QLabel("Configuración")
        title.setObjectName("PageTitle")

        subtitle = QLabel(
            "Preferencias locales del perfil activo. "
            "La sincronización queda solo preparada para una etapa futura.",
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
        form.addRow("Cifrado", self.cifrado_check)
        form.addRow("Carpeta de respaldo", self._folder_row(
            self.respaldo_input,
            self.select_backup_folder,
        ))
        form.addRow("Sincronización", self.sincronizacion_check)

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

        backup_title = QLabel("Respaldo y restauración")
        backup_title.setObjectName("SectionTitle")
        backup_description = QLabel(
            "Crea un ZIP verificado del perfil activo o restaura un respaldo "
            "compatible. La restauración exige validación y confirmación.",
        )
        backup_description.setObjectName("MutedText")
        backup_description.setWordWrap(True)
        backup_actions = QHBoxLayout()
        backup_actions.setSpacing(8)
        self.create_backup_button.clicked.connect(self.create_backup)
        self.restore_backup_button.clicked.connect(self.restore_backup)
        backup_actions.addWidget(self.create_backup_button)
        backup_actions.addWidget(self.restore_backup_button)
        backup_actions.addStretch(1)

        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addLayout(form)
        layout.addWidget(backup_title)
        layout.addWidget(backup_description)
        layout.addLayout(backup_actions)
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
        self.estado_label.setText(f"Error: {message}")
        QMessageBox.warning(self, "Configuración", message)

    def _show_backup_error(self, message: str) -> None:
        """Muestra un error de respaldo o restauración."""
        self.estado_label.setText(f"Error: {message}")
        QMessageBox.warning(self, "Respaldos", message)

    def _technical_error(
        self,
        exc: BaseException,
        *,
        context: str,
        fallback: str,
    ) -> str:
        """Registra un fallo técnico sin exponer su contenido crudo."""
        notice = self.error_reporter.report(
            exc,
            context=context,
            user_message=fallback,
        )
        return notice.message
