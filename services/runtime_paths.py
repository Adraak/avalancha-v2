"""Resolución central de rutas mutables de Avalancha."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class RuntimePaths:
    """Separa datos persistentes del código y del ejecutable instalado."""

    source_root: Path
    user_root: Path

    @classmethod
    def current(cls, source_root: str | Path | None = None) -> "RuntimePaths":
        """Resuelve rutas para ejecución desde fuente o aplicación congelada."""
        source = (
            Path(source_root).resolve()
            if source_root is not None
            else Path(__file__).resolve().parents[1]
        )
        override = os.environ.get("AVALANCHA_APP_DATA_DIR", "").strip()
        if override:
            user_root = Path(override).expanduser().resolve()
        elif bool(getattr(sys, "frozen", False)):
            local_app_data = os.environ.get("LOCALAPPDATA", "").strip()
            base = Path(local_app_data) if local_app_data else Path.home()
            user_root = (base / "Avalancha").resolve()
        else:
            user_root = source
        return cls(source_root=source, user_root=user_root)

    @property
    def profiles_root(self) -> Path:
        """Devuelve el catálogo y las carpetas de perfiles financieros."""
        return self.user_root / "data" / "perfiles"

    @property
    def legacy_data_dir(self) -> Path:
        """Devuelve la ubicación compatible con datos planos históricos."""
        return self.user_root / "data"

    @property
    def legacy_reports_dir(self) -> Path:
        """Devuelve la ubicación compatible con reportes históricos."""
        return self.user_root / "reportes"

    @property
    def legacy_config_dir(self) -> Path:
        """Devuelve la ubicación compatible con configuración histórica."""
        return self.user_root / "config"
