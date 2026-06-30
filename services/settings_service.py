"""Servicio de configuracion por perfil para Avalancha V2."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from core.models.configuracion import ConfiguracionAplicacion


class SettingsService:
    """Lee, valida y guarda configuracion sin depender de la interfaz."""

    MONEDAS_PERMITIDAS = ("CLP", "USD", "EUR")
    APARIENCIAS_PERMITIDAS = ("claro", "oscuro", "sistema")
    ARCHIVO_CONFIGURACION = "settings.json"

    def __init__(
        self,
        config_dir: str | Path,
        reports_dir: str | Path,
        backup_dir: str | Path,
    ) -> None:
        """Inicializa rutas base para un perfil especifico."""
        self.config_dir = Path(config_dir)
        self.reports_dir = Path(reports_dir)
        self.backup_dir = Path(backup_dir)
        self.settings_path = self.config_dir / self.ARCHIVO_CONFIGURACION

    def cargar_configuracion(self) -> ConfiguracionAplicacion:
        """Carga configuracion persistida o devuelve valores por defecto."""
        data = self._leer_json()
        config = ConfiguracionAplicacion.from_dict(
            data,
            self.reports_dir,
            self.backup_dir,
        )
        return self._normalizar_configuracion(config)

    def guardar_configuracion(
        self,
        datos: dict[str, object] | ConfiguracionAplicacion,
    ) -> ConfiguracionAplicacion:
        """Valida, crea carpetas necesarias y guarda configuracion."""
        config = (
            datos
            if isinstance(datos, ConfiguracionAplicacion)
            else self._crear_desde_datos(datos)
        )
        config = self._validar_configuracion(config)
        self._crear_carpetas_configuradas(config)
        self.config_dir.mkdir(parents=True, exist_ok=True)
        with self.settings_path.open("w", encoding="utf-8") as file:
            json.dump(
                config.to_dict(),
                file,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            file.write("\n")
        return config

    def restaurar_valores_por_defecto(self) -> ConfiguracionAplicacion:
        """Restaura y persiste los valores iniciales del perfil."""
        config = self.obtener_configuracion_por_defecto()
        return self.guardar_configuracion(config)

    def obtener_configuracion_por_defecto(self) -> ConfiguracionAplicacion:
        """Devuelve la configuracion base sugerida para el perfil."""
        return ConfiguracionAplicacion(
            carpeta_reportes=self.reports_dir,
            moneda_principal="CLP",
            apariencia="claro",
            cifrado_reportes=True,
            carpeta_respaldo=self.backup_dir,
            sincronizacion_habilitada=False,
        )

    def ruta_archivo_configuracion(self) -> Path:
        """Devuelve la ruta interna donde se persiste la configuracion."""
        return self.settings_path

    def _crear_desde_datos(
        self,
        datos: dict[str, object],
    ) -> ConfiguracionAplicacion:
        """Construye el modelo desde datos crudos de UI o tests."""
        return ConfiguracionAplicacion(
            carpeta_reportes=Path(str(datos.get("carpeta_reportes", ""))),
            moneda_principal=str(datos.get("moneda_principal", "")),
            apariencia=str(datos.get("apariencia", "")),
            cifrado_reportes=bool(datos.get("cifrado_reportes", True)),
            carpeta_respaldo=Path(str(datos.get("carpeta_respaldo", ""))),
            sincronizacion_habilitada=bool(
                datos.get("sincronizacion_habilitada", False),
            ),
        )

    def _normalizar_configuracion(
        self,
        config: ConfiguracionAplicacion,
    ) -> ConfiguracionAplicacion:
        """Aplica defaults seguros antes de validar."""
        moneda = config.moneda_principal.strip().upper() or "CLP"
        apariencia = config.apariencia.strip().lower() or "claro"
        return ConfiguracionAplicacion(
            carpeta_reportes=config.carpeta_reportes,
            moneda_principal=moneda,
            apariencia=apariencia,
            cifrado_reportes=config.cifrado_reportes,
            carpeta_respaldo=config.carpeta_respaldo or self.backup_dir,
            sincronizacion_habilitada=config.sincronizacion_habilitada,
        )

    def _validar_configuracion(
        self,
        config: ConfiguracionAplicacion,
    ) -> ConfiguracionAplicacion:
        """Valida reglas de configuracion y devuelve modelo normalizado."""
        config = self._normalizar_configuracion(config)
        self._validar_carpeta(
            config.carpeta_reportes,
            "La carpeta de reportes no es valida.",
        )
        if config.carpeta_respaldo is None:
            raise ValueError("La carpeta de respaldo es obligatoria.")
        self._validar_carpeta(
            config.carpeta_respaldo,
            "La carpeta de respaldo no es valida.",
        )
        if config.moneda_principal not in self.MONEDAS_PERMITIDAS:
            raise ValueError("La moneda principal no esta soportada.")
        if config.apariencia not in self.APARIENCIAS_PERMITIDAS:
            raise ValueError("La apariencia seleccionada no esta soportada.")
        return config

    @staticmethod
    def _validar_carpeta(path: Path, mensaje: str) -> None:
        """Valida que una ruta sea carpeta o pueda crearse."""
        if not str(path).strip():
            raise ValueError(mensaje)
        if path.exists() and not path.is_dir():
            raise ValueError(mensaje)

    @staticmethod
    def _crear_carpetas_configuradas(
        config: ConfiguracionAplicacion,
    ) -> None:
        """Crea las carpetas configuradas si aun no existen."""
        config.carpeta_reportes.mkdir(parents=True, exist_ok=True)
        if config.carpeta_respaldo is not None:
            config.carpeta_respaldo.mkdir(parents=True, exist_ok=True)

    def _leer_json(self) -> dict[str, Any]:
        """Lee el archivo de configuracion de forma tolerante."""
        if not self.settings_path.exists():
            return {}
        with self.settings_path.open("r", encoding="utf-8") as file:
            data = json.load(file)
        return data if isinstance(data, dict) else {}
