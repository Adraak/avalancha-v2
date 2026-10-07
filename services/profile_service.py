"""Servicio de perfiles locales para Avalancha V2."""

from __future__ import annotations

import json
import shutil
import unicodedata
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from avalancha.models import MonthlyBudget
from avalancha.storage import BudgetRepository


PERFIL_PERSONAL = "personal"
PERFIL_DEMO = "demo_avalancha"

from services.error_reporting_service import UserFacingError
from services.runtime_paths import RuntimePaths


@dataclass(frozen=True, slots=True)
class PerfilAplicacion:
    """Describe un perfil local y sus carpetas separadas."""

    id: str
    nombre: str
    raiz: Path
    activo: bool = False

    @property
    def data_dir(self) -> Path:
        """Devuelve la carpeta de datos del perfil."""
        return self.raiz / "data"

    @property
    def reports_dir(self) -> Path:
        """Devuelve la carpeta de reportes cifrados del perfil."""
        return self.raiz / "reportes"

    @property
    def config_dir(self) -> Path:
        """Devuelve la carpeta de configuracion privada del perfil."""
        return self.raiz / "config"

    @property
    def key_path(self) -> Path:
        """Devuelve la ruta de clave local de reportes del perfil."""
        return self.config_dir / "reporte.key"


class ProfileService:
    """Administra perfiles financieros locales sin depender de UI."""

    def __init__(
        self,
        profiles_root: str | Path | None = None,
        legacy_data_dir: str | Path | None = None,
        legacy_reports_dir: str | Path | None = None,
        legacy_config_dir: str | Path | None = None,
    ) -> None:
        """Inicializa registro y asegura el perfil personal."""
        use_runtime_defaults = all(
            value is None
            for value in (
                profiles_root,
                legacy_data_dir,
                legacy_reports_dir,
                legacy_config_dir,
            )
        )
        if use_runtime_defaults:
            runtime_paths = RuntimePaths.current()
            self.profiles_root = runtime_paths.profiles_root
            self.legacy_data_dir = runtime_paths.legacy_data_dir
            self.legacy_reports_dir = runtime_paths.legacy_reports_dir
            self.legacy_config_dir = runtime_paths.legacy_config_dir
        else:
            self.profiles_root = (
                Path(profiles_root)
                if profiles_root is not None
                else Path("data/perfiles")
            )
            self.legacy_data_dir = (
                Path(legacy_data_dir)
                if legacy_data_dir is not None
                else Path("data")
            )
            self.legacy_reports_dir = (
                Path(legacy_reports_dir)
                if legacy_reports_dir is not None
                else Path("reportes")
            )
            self.legacy_config_dir = (
                Path(legacy_config_dir)
                if legacy_config_dir is not None
                else Path("config")
            )
        self.registry_path = self.profiles_root / "perfiles.json"
        self.active_path = self.profiles_root / "perfil_activo.json"
        self.profiles_root.mkdir(parents=True, exist_ok=True)
        self._ensure_personal_profile()

    def listar_perfiles(self) -> list[PerfilAplicacion]:
        """Devuelve perfiles registrados ordenados por nombre."""
        active_id = self._read_active_id()
        profiles = [
            self._build_profile(item["slug"], item["nombre"], active_id)
            for item in self._read_registry()
        ]
        return sorted(profiles, key=lambda item: item.nombre.casefold())

    def obtener_activo(self) -> PerfilAplicacion:
        """Devuelve el perfil activo actual."""
        return self.obtener_perfil(self._read_active_id())

    def obtener_perfil(self, perfil_id: str) -> PerfilAplicacion:
        """Busca un perfil por identificador."""
        active_id = self._read_active_id()
        for item in self._read_registry():
            if item["slug"] == perfil_id:
                return self._build_profile(item["slug"], item["nombre"], active_id)
        raise UserFacingError("El perfil solicitado no existe.")

    def crear_perfil(self, nombre: str) -> PerfilAplicacion:
        """Crea un perfil vacio e independiente."""
        clean_name = nombre.strip()
        if not clean_name:
            raise UserFacingError("El perfil necesita un nombre.")
        slug = self._unique_slug(self._slugify(clean_name))
        registry = self._read_registry()
        registry.append({"slug": slug, "nombre": clean_name})
        self._write_registry(registry)
        profile = self._build_profile(slug, clean_name, self._read_active_id())
        self._ensure_profile_dirs(profile)
        BudgetRepository(profile.data_dir).save(
            MonthlyBudget.empty(date.today().year, date.today().month),
        )
        return profile

    def seleccionar_perfil(self, perfil_id: str) -> PerfilAplicacion:
        """Cambia el perfil activo y lo devuelve."""
        profile = self.obtener_perfil(perfil_id)
        self._write_json(self.active_path, {"slug": profile.id})
        return self.obtener_perfil(perfil_id)

    def obtener_ruta_activa(self) -> Path:
        """Devuelve la carpeta de datos del perfil activo."""
        return self.obtener_activo().data_dir

    def obtener_periodo_trabajo(
        self,
        perfil_id: str | None = None,
        fecha_base: date | None = None,
    ) -> tuple[int, int]:
        """Devuelve anio y mes operativo para un perfil.

        Usa el mes actual si existe en el perfil. Si no existe, usa el ultimo
        mes disponible para evitar abrir pantallas vacias en perfiles demo.
        """
        profile = (
            self.obtener_perfil(perfil_id)
            if perfil_id
            else self.obtener_activo()
        )
        current = fecha_base or date.today()
        current_label = f"{current.year:04d}-{current.month:02d}"
        repository = BudgetRepository(profile.data_dir)
        months = sorted(repository.list_months())
        if (
            current_label in months
            and self._mes_tiene_movimientos(repository, current_label)
        ):
            return current.year, current.month
        active_months = [
            label
            for label in months
            if self._mes_tiene_movimientos(repository, label)
        ]
        if active_months:
            previous_or_current = [
                label for label in active_months if label <= current_label
            ]
            selected = (
                previous_or_current[-1]
                if previous_or_current
                else active_months[-1]
            )
            year, month = (int(part) for part in selected.split("-"))
            return year, month
        if current_label in months:
            return current.year, current.month
        if months:
            year, month = (int(part) for part in months[-1].split("-"))
            return year, month
        return current.year, current.month

    def asegurar_demo_registrado(self) -> PerfilAplicacion:
        """Registra el perfil demo si falta, sin generar datos."""
        return self._register_if_missing(PERFIL_DEMO, "Demo Avalancha")

    def _ensure_personal_profile(self) -> None:
        """Crea y migra el perfil personal si falta."""
        profile = self._register_if_missing(PERFIL_PERSONAL, "Personal")
        self._ensure_profile_dirs(profile)
        self._copy_legacy_personal_data(profile)
        if not self.active_path.exists():
            self._write_json(self.active_path, {"slug": PERFIL_PERSONAL})

    @staticmethod
    def _mes_tiene_movimientos(
        repository: BudgetRepository,
        label: str,
    ) -> bool:
        """Indica si un mes tiene movimientos reales registrados."""
        try:
            year, month = (int(part) for part in label.split("-"))
            budget = repository.load(year, month)
        except (OSError, ValueError):
            return False
        return bool(budget.transactions)

    def _copy_legacy_personal_data(self, profile: PerfilAplicacion) -> None:
        """Copia datos existentes al perfil personal sin sobrescribir."""
        if not any(profile.data_dir.glob("presupuesto_????-??.json")):
            for source in self.legacy_data_dir.glob("presupuesto_????-??.json"):
                shutil.copy2(source, profile.data_dir / source.name)
            for name in ("cuentas.json", "deudas.json", "historial_mensual.json"):
                self._copy_if_missing(
                    self.legacy_data_dir / name,
                    profile.data_dir / name,
                )
        if not any(profile.reports_dir.glob("*.avr*")):
            for source in self.legacy_reports_dir.glob("*.avr*"):
                self._copy_if_missing(source, profile.reports_dir / source.name)
        self._copy_if_missing(
            self.legacy_config_dir / "reporte.key",
            profile.key_path,
        )

    def _register_if_missing(
        self,
        slug: str,
        name: str,
    ) -> PerfilAplicacion:
        """Registra un perfil si no existe."""
        registry = self._read_registry()
        if not any(item["slug"] == slug for item in registry):
            registry.append({"slug": slug, "nombre": name})
            self._write_registry(registry)
        profile = self._build_profile(slug, name, self._read_active_id())
        self._ensure_profile_dirs(profile)
        return profile

    def _build_profile(
        self,
        slug: str,
        name: str,
        active_id: str,
    ) -> PerfilAplicacion:
        """Construye el objeto de perfil desde el registro."""
        return PerfilAplicacion(
            id=slug,
            nombre=name,
            raiz=self.profiles_root / slug,
            activo=slug == active_id,
        )

    def _ensure_profile_dirs(self, profile: PerfilAplicacion) -> None:
        """Crea carpetas internas del perfil."""
        for path in (
            profile.raiz,
            profile.data_dir,
            profile.reports_dir,
            profile.config_dir,
        ):
            path.mkdir(parents=True, exist_ok=True)

    def _read_active_id(self) -> str:
        """Lee el identificador activo desde disco."""
        data = self._read_json(self.active_path, {"slug": PERFIL_PERSONAL})
        return str(data.get("slug", PERFIL_PERSONAL))

    def _read_registry(self) -> list[dict[str, str]]:
        """Lee y normaliza el registro de perfiles."""
        data = self._read_json(self.registry_path, {"perfiles": []})
        raw_profiles = data.get("perfiles", [])
        if not isinstance(raw_profiles, list):
            return []
        profiles = []
        for item in raw_profiles:
            if not isinstance(item, dict):
                continue
            slug = str(item.get("slug", "")).strip()
            name = str(item.get("nombre", "")).strip()
            if slug and name:
                profiles.append({"slug": slug, "nombre": name})
        return profiles

    def _write_registry(self, profiles: list[dict[str, str]]) -> None:
        """Guarda el registro de perfiles ordenado."""
        profiles.sort(key=lambda item: item["nombre"].casefold())
        self._write_json(self.registry_path, {"perfiles": profiles})

    def _unique_slug(self, base_slug: str) -> str:
        """Genera un slug no utilizado."""
        existing = {item["slug"] for item in self._read_registry()}
        slug = base_slug or "perfil"
        current = slug
        sequence = 1
        while current in existing:
            sequence += 1
            current = f"{slug}_{sequence:02d}"
        return current

    @staticmethod
    def _slugify(name: str) -> str:
        """Convierte un nombre visible en identificador de carpeta."""
        normalized = unicodedata.normalize("NFD", name.casefold())
        cleaned = "".join(
            char
            for char in normalized
            if unicodedata.category(char) != "Mn"
        )
        parts = [char if char.isalnum() else "_" for char in cleaned]
        return "_".join(part for part in "".join(parts).split("_") if part)

    @staticmethod
    def _read_json(path: Path, default: dict[str, Any]) -> dict[str, Any]:
        """Lee JSON de forma tolerante."""
        if not path.exists():
            return default
        with path.open("r", encoding="utf-8") as file:
            data = json.load(file)
        return data if isinstance(data, dict) else default

    @staticmethod
    def _write_json(path: Path, data: dict[str, Any]) -> None:
        """Escribe JSON con formato estable."""
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as file:
            json.dump(data, file, ensure_ascii=False, indent=2, sort_keys=True)
            file.write("\n")

    @staticmethod
    def _copy_if_missing(source: Path, target: Path) -> None:
        """Copia un archivo solo cuando el destino no existe."""
        if not source.exists() or target.exists():
            return
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
