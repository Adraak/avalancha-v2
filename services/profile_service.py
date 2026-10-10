"""Servicio de perfiles locales para Avalancha V2."""

from __future__ import annotations

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

from core.versioned_json_store import VersionedJsonStore
from services.error_reporting_service import UserFacingError
from services.profile_metadata_service import ProfileMetadataService
from services.runtime_paths import RuntimePaths


@dataclass(frozen=True, slots=True)
class _LegacyCopy:
    """Describe una copia pendiente desde las carpetas planas historicas."""

    source: Path
    target: Path
    versioned: bool


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
        metadata_service: ProfileMetadataService | None = None,
    ) -> None:
        """Inicializa registro y asegura el perfil personal."""
        self._metadata_service = metadata_service or ProfileMetadataService()
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
        self._validate_existing_catalog()
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
        """Busca un perfil por identificador y lo deja operativo.

        Antes de devolverlo valida sus metadatos globales, o los crea
        una sola vez si es un perfil historico sin ellos.
        """
        active_id = self._read_active_id()
        for item in self._read_registry():
            if item["slug"] == perfil_id:
                profile = self._build_profile(
                    item["slug"],
                    item["nombre"],
                    active_id,
                )
                self._metadata_service.ensure(profile)
                return profile
        raise UserFacingError("El perfil solicitado no existe.")

    def crear_perfil(self, nombre: str) -> PerfilAplicacion:
        """Crea un perfil vacio e independiente."""
        self._validate_existing_catalog()
        clean_name = nombre.strip()
        if not clean_name:
            raise UserFacingError("El perfil necesita un nombre.")
        slug = self._unique_slug(self._slugify(clean_name))
        registry = self._read_registry()
        profile = self._build_profile(slug, clean_name, self._read_active_id())
        self._metadata_service.validate_existing(profile)
        registry.append({"slug": slug, "nombre": clean_name})
        self._register_with_metadata(profile, registry)
        BudgetRepository(profile.data_dir).save(
            MonthlyBudget.empty(date.today().year, date.today().month),
        )
        return profile

    def seleccionar_perfil(self, perfil_id: str) -> PerfilAplicacion:
        """Cambia el perfil activo y lo devuelve."""
        self._validate_existing_catalog()
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

    def _validate_existing_catalog(self) -> None:
        """Lee catalogo y perfil activo antes de permitir mutaciones."""
        for path in (self.registry_path, self.active_path):
            self._read_json(path, {})

    def _ensure_personal_profile(self) -> None:
        """Crea y migra el perfil personal si falta."""
        self._register_if_missing(
            PERFIL_PERSONAL,
            "Personal",
            copy_legacy_data=True,
        )
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

    def _plan_legacy_personal_copy(
        self,
        profile: PerfilAplicacion,
    ) -> list[_LegacyCopy]:
        """Determina, sin escribir, que datos planos historicos se copiarian.

        Conserva las reglas historicas: los datos solo se copian si el
        perfil no tiene presupuestos, los reportes solo si no tiene
        ninguno, y nunca se sobrescribe un archivo existente. Marca como
        versionados los JSON ordinarios cuyo esquema debe revisarse antes
        de copiar; el historial mensual, los reportes cifrados y la clave
        quedan fuera de esa revision.
        """
        plan: list[_LegacyCopy] = []
        if not any(profile.data_dir.glob("presupuesto_????-??.json")):
            for source in sorted(
                self.legacy_data_dir.glob("presupuesto_????-??.json"),
            ):
                plan.append(
                    _LegacyCopy(source, profile.data_dir / source.name, True),
                )
            for name, versioned in (
                ("cuentas.json", True),
                ("deudas.json", True),
                ("historial_mensual.json", False),
            ):
                self._plan_copy_if_missing(
                    plan,
                    self.legacy_data_dir / name,
                    profile.data_dir / name,
                    versioned,
                )
        if not any(profile.reports_dir.glob("*.avr*")):
            for source in sorted(self.legacy_reports_dir.glob("*.avr*")):
                self._plan_copy_if_missing(
                    plan,
                    source,
                    profile.reports_dir / source.name,
                    False,
                )
        self._plan_copy_if_missing(
            plan,
            self.legacy_config_dir / "reporte.key",
            profile.key_path,
            False,
        )
        return plan

    @staticmethod
    def _plan_copy_if_missing(
        plan: list[_LegacyCopy],
        source: Path,
        target: Path,
        versioned: bool,
    ) -> None:
        """Agrega una copia al plan solo si hay origen y falta el destino."""
        if source.exists() and not target.exists():
            plan.append(_LegacyCopy(source, target, versioned))

    @staticmethod
    def _run_legacy_copy(plan: list[_LegacyCopy]) -> None:
        """Ejecuta las copias historicas ya planificadas y revisadas."""
        for item in plan:
            item.target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item.source, item.target)

    def _register_if_missing(
        self,
        slug: str,
        name: str,
        copy_legacy_data: bool = False,
    ) -> PerfilAplicacion:
        """Registra un perfil si no existe y asegura sus metadatos.

        Antes de cualquier mutacion valida los metadatos presentes y,
        si el perfil aun no esta etiquetado, sus archivos actuales y
        las fuentes historicas que se copiarian. Solo despues crea
        carpetas, copia, etiqueta y registra.
        """
        self._validate_existing_catalog()
        registry = self._read_registry()
        active_id = self._read_active_id()
        profile = self._build_profile(slug, name, active_id)
        registered = next(
            (item for item in registry if item["slug"] == slug),
            None,
        )
        catalog_profile = self._build_profile(
            slug,
            registered["nombre"] if registered else name,
            active_id,
        )
        if self._metadata_service.validate_existing(catalog_profile) is None:
            self._metadata_service.preflight_legacy_documents(catalog_profile)
        plan = (
            self._plan_legacy_personal_copy(catalog_profile)
            if copy_legacy_data
            else []
        )
        self._metadata_service.validate_documents(
            [item.source for item in plan if item.versioned],
            slug,
        )
        if registered is None:
            registry.append({"slug": slug, "nombre": name})
            self._register_with_metadata(catalog_profile, registry, plan)
            return profile
        self._ensure_profile_dirs(catalog_profile)
        self._run_legacy_copy(plan)
        self._metadata_service.ensure(catalog_profile)
        return profile

    def _register_with_metadata(
        self,
        profile: PerfilAplicacion,
        registry: list[dict[str, str]],
        legacy_copy_plan: list[_LegacyCopy] | None = None,
    ) -> None:
        """Crea carpetas y metadatos y solo despues registra el perfil.

        Si algo falla antes de completar el registro, retira lo que esta
        misma operacion creo: los metadatos nuevos y las carpetas que
        sigan vacias. Nunca borra carpetas ni metadatos preexistentes.
        """
        had_metadata = self._metadata_service.has_metadata(profile)
        created_dirs = self._ensure_profile_dirs(profile)
        try:
            self._run_legacy_copy(legacy_copy_plan or [])
            self._metadata_service.ensure(profile)
            self._write_registry(registry)
        except BaseException:
            if not had_metadata:
                self._metadata_service.discard(profile)
            for path in reversed(created_dirs):
                try:
                    path.rmdir()
                except OSError:
                    continue
            raise

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

    def _ensure_profile_dirs(self, profile: PerfilAplicacion) -> list[Path]:
        """Crea carpetas internas del perfil y devuelve las nuevas."""
        created = []
        for path in (
            profile.raiz,
            profile.data_dir,
            profile.reports_dir,
            profile.config_dir,
        ):
            if not path.exists():
                path.mkdir(parents=True, exist_ok=True)
                created.append(path)
        return created

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
        data = VersionedJsonStore().read(path)
        return data if isinstance(data, dict) else default

    @staticmethod
    def _write_json(path: Path, data: dict[str, Any]) -> None:
        """Escribe JSON con formato estable."""
        path.parent.mkdir(parents=True, exist_ok=True)
        VersionedJsonStore().write(path, data)
