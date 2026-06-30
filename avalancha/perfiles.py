"""Perfiles locales independientes para Avalancha."""

from __future__ import annotations

import json
import shutil
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

from avalancha.finanzas import (
    AnalizadorResumen,
    DiagnosticoFinanciero,
    GestorConciliacion,
    GestorDeudas,
    IndiceRiesgoFinanciero,
    ProyectorDeuda,
    ReporteMensual,
)
from avalancha.gestor_reportes import (
    GestorReportes,
    ProveedorClaveLocal,
    ReporteDuplicadoError,
)
from avalancha.historial_financiero import (
    GeneradorSnapshot,
    HistorialFinanciero,
    MesYaCerradoError,
)
from avalancha.models import (
    CuentaFinanciera,
    Debt,
    EXPENSE,
    INCOME,
    CategoryBudget,
    MonthlyBudget,
    RecurringItem,
    Transaction,
)
from avalancha.reporte_mensual import GeneradorReporteMensual
from avalancha.storage import BudgetRepository


PERFIL_PERSONAL = "personal"
PERFIL_DEMO = "demo_avalancha"


@dataclass(frozen=True)
class PerfilLocal:
    """Describe un perfil local y sus carpetas aisladas."""

    slug: str
    nombre: str
    raiz: Path

    @property
    def data_dir(self) -> Path:
        """Devuelve la carpeta de datos del perfil."""
        return self.raiz / "data"

    @property
    def reportes_dir(self) -> Path:
        """Devuelve la carpeta de reportes cifrados del perfil."""
        return self.raiz / "reportes"

    @property
    def backup_dir(self) -> Path:
        """Devuelve la carpeta de respaldos ZIP del perfil."""
        return self.raiz / "backup"

    @property
    def config_dir(self) -> Path:
        """Devuelve la carpeta de configuración privada del perfil."""
        return self.raiz / "config"

    @property
    def clave_reportes(self) -> Path:
        """Devuelve la ruta de la clave local de reportes."""
        return self.config_dir / "reporte.key"


class GestorPerfiles:
    """Administra perfiles locales sin usuarios ni conexión externa."""

    def __init__(
        self,
        raiz_perfiles: str | Path = "data/perfiles",
        data_legacy: str | Path = "data",
        reportes_legacy: str | Path = "reportes",
        config_legacy: str | Path = "config",
    ) -> None:
        """Inicializa rutas y asegura el perfil personal."""
        self.raiz_perfiles = Path(raiz_perfiles)
        self.data_legacy = Path(data_legacy)
        self.reportes_legacy = Path(reportes_legacy)
        self.config_legacy = Path(config_legacy)
        self.raiz_perfiles.mkdir(parents=True, exist_ok=True)
        self.ruta_registro = self.raiz_perfiles / "perfiles.json"
        self.ruta_activo = self.raiz_perfiles / "perfil_activo.json"
        self._asegurar_perfil_personal()

    def obtener_activo(self) -> PerfilLocal:
        """Devuelve el perfil activo actual."""
        slug = self._leer_slug_activo()
        return self.obtener_perfil(slug)

    def listar_perfiles(self) -> list[PerfilLocal]:
        """Lista perfiles registrados ordenados por nombre."""
        perfiles = self._leer_registro()
        return sorted(
            [
                self._crear_perfil(item["slug"], item["nombre"])
                for item in perfiles
            ],
            key=lambda item: item.nombre.casefold(),
        )

    def obtener_perfil(self, slug: str) -> PerfilLocal:
        """Busca un perfil por identificador interno."""
        for perfil in self.listar_perfiles():
            if perfil.slug == slug:
                return perfil
        raise ValueError("El perfil solicitado no existe.")

    def activar_perfil(self, slug: str) -> PerfilLocal:
        """Guarda y devuelve el perfil activo seleccionado."""
        perfil = self.obtener_perfil(slug)
        self._escribir_json(self.ruta_activo, {"slug": perfil.slug})
        return perfil

    def crear_perfil(self, nombre: str) -> PerfilLocal:
        """Crea un perfil vacío con datos independientes."""
        nombre_limpio = nombre.strip()
        if not nombre_limpio:
            raise ValueError("El perfil necesita un nombre.")
        slug = self._slugificar(nombre_limpio)
        perfiles = self._leer_registro()
        slugs = {item["slug"] for item in perfiles}
        base_slug = slug
        secuencia = 1
        while slug in slugs:
            secuencia += 1
            slug = f"{base_slug}_{secuencia:02d}"
        perfiles.append({"slug": slug, "nombre": nombre_limpio})
        self._guardar_registro(perfiles)
        perfil = self._crear_perfil(slug, nombre_limpio)
        self._crear_carpetas(perfil)
        BudgetRepository(perfil.data_dir).save(
            MonthlyBudget.empty(date.today().year, date.today().month)
        )
        return perfil

    def asegurar_demo(self) -> PerfilLocal:
        """Crea o actualiza el perfil Demo Avalancha con datos ficticios."""
        perfil = self._registrar_si_falta(PERFIL_DEMO, "Demo Avalancha")
        self._crear_carpetas(perfil)
        self._generar_datos_demo(perfil)
        return perfil

    def _asegurar_perfil_personal(self) -> None:
        """Registra y migra sin borrar el perfil personal."""
        perfil = self._registrar_si_falta(PERFIL_PERSONAL, "Personal")
        self._crear_carpetas(perfil)
        self._migrar_datos_personales(perfil)
        if not self.ruta_activo.exists():
            self._escribir_json(self.ruta_activo, {"slug": perfil.slug})

    def _migrar_datos_personales(self, perfil: PerfilLocal) -> None:
        """Copia datos antiguos al perfil personal si aún no existen."""
        destino_tiene_datos = any(
            perfil.data_dir.glob("presupuesto_????-??.json")
        )
        if not destino_tiene_datos:
            for ruta in self.data_legacy.glob("presupuesto_????-??.json"):
                shutil.copy2(ruta, perfil.data_dir / ruta.name)
            for nombre in (
                "cuentas.json",
                "deudas.json",
                "historial_mensual.json",
            ):
                self._copiar_si_existe(
                    self.data_legacy / nombre,
                    perfil.data_dir / nombre,
                )
        if not any(perfil.reportes_dir.glob("*.avr")):
            for ruta in self.reportes_legacy.glob("*.avr*"):
                shutil.copy2(ruta, perfil.reportes_dir / ruta.name)
        self._copiar_si_existe(
            self.config_legacy / "reporte.key",
            perfil.clave_reportes,
        )

    def _generar_datos_demo(self, perfil: PerfilLocal) -> None:
        """Sobrescribe el demo solo con información falsa."""
        hoy = date.today()
        presupuesto = self._crear_presupuesto_demo(hoy.year, hoy.month)
        cuentas = self._crear_cuentas_demo()
        deudas = self._crear_deudas_demo()
        cuenta_corriente = cuentas[0]
        tarjeta = cuentas[3]
        deuda_tarjeta = deudas[0]

        self._asignar_cuenta_demo(
            presupuesto,
            cuenta_corriente.account_id,
            tarjeta.account_id,
            deuda_tarjeta.debt_id,
        )
        GestorConciliacion(cuentas).recalcular_saldos_registrados(
            presupuesto
        )
        cuentas[0].real_balance = cuentas[0].registered_balance - 18_500
        cuentas[1].real_balance = cuentas[1].registered_balance
        cuentas[2].real_balance = cuentas[2].registered_balance + 2_000
        cuentas[3].real_balance = cuentas[3].registered_balance

        repositorio = BudgetRepository(perfil.data_dir)
        repositorio.save(presupuesto)
        repositorio.save_debts(deudas)
        repositorio.save_accounts(cuentas)
        self._crear_historial_demo(perfil, presupuesto, deudas, cuentas)
        self._crear_reporte_demo(perfil, presupuesto, deudas, cuentas)

    def _crear_presupuesto_demo(self, year: int, month: int) -> MonthlyBudget:
        """Construye un mes demo con ingresos y gastos realistas."""
        presupuesto = MonthlyBudget(
            year=year,
            month=month,
            categories=[
                CategoryBudget("Sueldo", INCOME, 1_850_000, True),
                CategoryBudget("Otros ingresos", INCOME, 120_000, False),
                CategoryBudget("Arriendo", EXPENSE, 620_000, True),
                CategoryBudget("Servicios", EXPENSE, 190_000, True),
                CategoryBudget("Comida", EXPENSE, 320_000, False),
                CategoryBudget("Transporte", EXPENSE, 120_000, False),
                CategoryBudget("Salud", EXPENSE, 80_000, False),
                CategoryBudget("Educacion", EXPENSE, 90_000, True),
                CategoryBudget("Ocio", EXPENSE, 110_000, False),
                CategoryBudget("Mascota", EXPENSE, 65_000, False),
                CategoryBudget("Ahorro", EXPENSE, 150_000, True),
                CategoryBudget("Tarjeta demo", EXPENSE, 180_000, True),
            ],
        )
        for item in self._movimientos_demo(year, month):
            presupuesto.add_or_update_transaction(item)
        for item in self._recurrentes_demo():
            presupuesto.add_or_update_recurring(item)
        return presupuesto

    def _movimientos_demo(self, year: int, month: int) -> list[Transaction]:
        """Devuelve movimientos ficticios para el mes demo."""
        prefijo = f"{year:04d}-{month:02d}"
        return [
            Transaction(INCOME, "Sueldo", 1_850_000, f"{prefijo}-05",
                        "Remuneracion demo", "Transferencia"),
            Transaction(INCOME, "Otros ingresos", 80_000, f"{prefijo}-12",
                        "Venta de articulos usados", "Transferencia"),
            Transaction(EXPENSE, "Arriendo", 620_000, f"{prefijo}-01",
                        "Arriendo departamento demo", "Transferencia"),
            Transaction(EXPENSE, "Servicios", 86_500, f"{prefijo}-03",
                        "Electricidad y agua", "Debito"),
            Transaction(EXPENSE, "Servicios", 32_900, f"{prefijo}-10",
                        "Internet hogar", "Debito"),
            Transaction(EXPENSE, "Comida", 96_300, f"{prefijo}-08",
                        "Supermercado semanal", "Debito"),
            Transaction(EXPENSE, "Comida", 74_800, f"{prefijo}-18",
                        "Feria y abarrotes", "Debito"),
            Transaction(EXPENSE, "Transporte", 42_000, f"{prefijo}-15",
                        "Combustible", "Debito"),
            Transaction(EXPENSE, "Salud", 28_000, f"{prefijo}-16",
                        "Farmacia", "Debito", is_unexpected=True),
            Transaction(EXPENSE, "Ocio", 39_990, f"{prefijo}-20",
                        "Cena familiar", "Credito"),
            Transaction(EXPENSE, "Mascota", 48_500, f"{prefijo}-21",
                        "Alimento mascota", "Debito"),
            Transaction(EXPENSE, "Ahorro", 150_000, f"{prefijo}-05",
                        "Ahorro mensual", "Transferencia"),
            Transaction(EXPENSE, "Tarjeta demo", 180_000, f"{prefijo}-05",
                        "Pago tarjeta demo", "Transferencia"),
        ]

    def _recurrentes_demo(self) -> list[RecurringItem]:
        """Devuelve plantillas recurrentes falsas para el demo."""
        return [
            RecurringItem(EXPENSE, "Arriendo", 620_000,
                          "Arriendo departamento demo", 1,
                          "Transferencia"),
            RecurringItem(INCOME, "Sueldo", 1_850_000,
                          "Remuneracion demo", 5, "Transferencia"),
            RecurringItem(EXPENSE, "Servicios", 32_900,
                          "Internet hogar", 10, "Debito"),
            RecurringItem(EXPENSE, "Educacion", 90_000,
                          "Curso online demo", 12, "Debito"),
            RecurringItem(EXPENSE, "Ahorro", 150_000,
                          "Ahorro mensual", 5, "Transferencia"),
            RecurringItem(EXPENSE, "Tarjeta demo", 180_000,
                          "Pago tarjeta demo", 5, "Transferencia"),
        ]

    def _crear_cuentas_demo(self) -> list[CuentaFinanciera]:
        """Crea cuentas ficticias del demo."""
        return [
            CuentaFinanciera(
                name="Cuenta corriente Demo Los Andes",
                account_type="cuenta_corriente",
                real_balance=0,
            ),
            CuentaFinanciera(
                name="Ahorro emergencia Demo",
                account_type="ahorro",
                real_balance=0,
            ),
            CuentaFinanciera(
                name="Efectivo Demo",
                account_type="efectivo",
                real_balance=0,
            ),
            CuentaFinanciera(
                name="Visa Demo Avalancha",
                account_type="tarjeta_credito",
                real_balance=0,
            ),
        ]

    def _crear_deudas_demo(self) -> list[Debt]:
        """Crea deudas ficticias del demo."""
        return [
            Debt(
                name="Visa Demo Avalancha",
                category="tarjeta_credito",
                current_balance=1_240_000,
                previous_month_balance=1_390_000,
                current_monthly_payment=180_000,
                minimum_payment=75_000,
                monthly_interest_rate=2.4,
                credit_limit=2_000_000,
            ),
            Debt(
                name="Credito consumo demo",
                category="credito_consumo",
                current_balance=2_800_000,
                previous_month_balance=2_930_000,
                current_monthly_payment=160_000,
                minimum_payment=160_000,
                monthly_interest_rate=1.1,
            ),
        ]

    def _asignar_cuenta_demo(
        self,
        presupuesto: MonthlyBudget,
        cuenta_corriente_id: str,
        tarjeta_id: str,
        deuda_tarjeta_id: str,
    ) -> None:
        """Vincula movimientos y recurrentes demo con cuentas falsas."""
        for item in presupuesto.transactions + presupuesto.recurring_items:
            if item.payment_method == "Credito":
                item.account_id = tarjeta_id
            else:
                item.account_id = cuenta_corriente_id
            if item.category == "Tarjeta demo":
                item.debt_id = deuda_tarjeta_id

    def _crear_historial_demo(
        self,
        perfil: PerfilLocal,
        presupuesto: MonthlyBudget,
        deudas: list[Debt],
        cuentas: list[CuentaFinanciera],
    ) -> None:
        """Genera cierres mensuales ficticios para gráficos e informes."""
        ruta = perfil.data_dir / "historial_mensual.json"
        if ruta.exists():
            ruta.unlink()
        gestor = HistorialFinanciero(ruta)
        gestor_deudas = GestorDeudas(deudas, {"": 0})
        riesgo = IndiceRiesgoFinanciero().calcular(
            monthly_debt_payment=340_000,
            total_debt=4_040_000,
            net_income=1_930_000,
            free_cash_flow=487_010,
            card_balance=1_240_000,
            total_card_limit=2_000_000,
            emergency_fund=450_000,
            basic_monthly_expense=900_000,
        )
        snapshot = GeneradorSnapshot.crear(
            presupuesto,
            gestor_deudas,
            riesgo,
            cuentas,
        )
        year = presupuesto.year
        month = presupuesto.month
        anteriores = [
            (self._desplazar_mes(year, month, -2), 4_420_000, -3_880_000),
            (self._desplazar_mes(year, month, -1), 4_200_000, -3_610_000),
        ]
        for label, deuda, patrimonio in anteriores:
            falso = dict(snapshot)
            falso["mes"] = label
            falso["deuda_total"] = deuda
            falso["patrimonio_neto"] = patrimonio
            falso["flujo_libre"] = 210_000
            gestor.guardar_snapshot(falso)
        try:
            gestor.guardar_snapshot(snapshot)
        except MesYaCerradoError:
            pass

    def _crear_reporte_demo(
        self,
        perfil: PerfilLocal,
        presupuesto: MonthlyBudget,
        deudas: list[Debt],
        cuentas: list[CuentaFinanciera],
    ) -> None:
        """Guarda un reporte cifrado de ejemplo dentro del perfil demo."""
        gestor_deudas = GestorDeudas(deudas, {})
        proyecciones = {
            deuda.debt_id: ProyectorDeuda().proyectar(deuda)
            for deuda in deudas
        }
        fecha_libertad = ReporteMensual(
            gestor_deudas,
            proyecciones,
        ).fecha_libertad_financiera()
        analizador = AnalizadorResumen(presupuesto, cuentas)
        diagnosticos = DiagnosticoFinanciero(
            presupuesto,
            gestor_deudas,
            cuentas,
        ).obtener_alertas()
        historial = HistorialFinanciero(
            perfil.data_dir / "historial_mensual.json"
        ).leer_historial()
        reporte = GeneradorReporteMensual(
            presupuesto,
            gestor_deudas,
            cuentas,
            analizador,
            diagnosticos,
            fecha_libertad,
            "Moderado",
            datetime.now(),
            historial,
            42,
        ).generar_estructura_reporte()
        gestor = GestorReportes(
            perfil.reportes_dir,
            ProveedorClaveLocal(perfil.clave_reportes),
        )
        try:
            gestor.guardar_reporte(reporte, presupuesto.label)
        except ReporteDuplicadoError:
            pass

    def _desplazar_mes(self, year: int, month: int, delta: int) -> str:
        """Devuelve una etiqueta YYYY-MM desplazada en meses."""
        total = year * 12 + month - 1 + delta
        nuevo_year = total // 12
        nuevo_month = total % 12 + 1
        return f"{nuevo_year:04d}-{nuevo_month:02d}"

    def _crear_carpetas(self, perfil: PerfilLocal) -> None:
        """Crea todas las carpetas internas del perfil."""
        for ruta in (
            perfil.raiz,
            perfil.data_dir,
            perfil.reportes_dir,
            perfil.backup_dir,
            perfil.config_dir,
        ):
            ruta.mkdir(parents=True, exist_ok=True)

    def _registrar_si_falta(self, slug: str, nombre: str) -> PerfilLocal:
        """Agrega un perfil al registro si todavía no existe."""
        perfiles = self._leer_registro()
        if not any(item["slug"] == slug for item in perfiles):
            perfiles.append({"slug": slug, "nombre": nombre})
            self._guardar_registro(perfiles)
        return self._crear_perfil(slug, nombre)

    def _crear_perfil(self, slug: str, nombre: str) -> PerfilLocal:
        """Construye el objeto de perfil para un registro."""
        return PerfilLocal(slug, nombre, self.raiz_perfiles / slug)

    def _leer_slug_activo(self) -> str:
        """Lee el identificador del perfil activo."""
        if not self.ruta_activo.exists():
            return PERFIL_PERSONAL
        data = self._leer_json(self.ruta_activo, {"slug": PERFIL_PERSONAL})
        return str(data.get("slug", PERFIL_PERSONAL))

    def _leer_registro(self) -> list[dict[str, str]]:
        """Lee el registro local de perfiles."""
        data = self._leer_json(self.ruta_registro, {"perfiles": []})
        perfiles = data.get("perfiles", [])
        if not isinstance(perfiles, list):
            return []
        validos = []
        for item in perfiles:
            if not isinstance(item, dict):
                continue
            slug = str(item.get("slug", "")).strip()
            nombre = str(item.get("nombre", "")).strip()
            if slug and nombre:
                validos.append({"slug": slug, "nombre": nombre})
        return validos

    def _guardar_registro(self, perfiles: list[dict[str, str]]) -> None:
        """Guarda el registro local de perfiles."""
        perfiles.sort(key=lambda item: item["nombre"].casefold())
        self._escribir_json(self.ruta_registro, {"perfiles": perfiles})

    def _leer_json(
        self,
        ruta: Path,
        default: dict[str, Any],
    ) -> dict[str, Any]:
        """Lee JSON y devuelve un valor seguro si no existe."""
        if not ruta.exists():
            return default
        with ruta.open("r", encoding="utf-8") as file:
            data = json.load(file)
        return data if isinstance(data, dict) else default

    def _escribir_json(self, ruta: Path, data: dict[str, Any]) -> None:
        """Escribe JSON con formato estable."""
        ruta.parent.mkdir(parents=True, exist_ok=True)
        with ruta.open("w", encoding="utf-8") as file:
            json.dump(data, file, ensure_ascii=False, indent=2,
                      sort_keys=True)
            file.write("\n")

    def _copiar_si_existe(self, origen: Path, destino: Path) -> None:
        """Copia un archivo si existe y el destino no está creado."""
        if origen.exists() and not destino.exists():
            destino.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(origen, destino)

    def _slugificar(self, nombre: str) -> str:
        """Convierte un nombre visible en identificador de carpeta."""
        normalizado = unicodedata.normalize("NFD", nombre.casefold())
        limpio = "".join(
            char
            for char in normalizado
            if unicodedata.category(char) != "Mn"
        )
        partes = []
        for char in limpio:
            partes.append(char if char.isalnum() else "_")
        slug = "_".join(
            parte for parte in "".join(partes).split("_") if parte
        )
        return slug or "perfil"
