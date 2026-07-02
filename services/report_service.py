"""Servicio de reportes cifrados para Avalancha V2."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from avalancha.gestor_reportes import (
    GestorReportes,
    ProveedorClaveLocal,
    ReporteDuplicadoError,
)
from avalancha.models import MonthlyBudget, validate_month
from avalancha.reporte_mensual import ReporteEstructurado, SeccionReporte
from avalancha.storage import BudgetRepository

from core.models.resumen_mensual import ResumenMensual
from services.account_service import AccountService
from services.budget_service import BudgetService
from services.financial_summary_service import FinancialSummaryService
from services.movement_service import MovementService
from services.reconciliation_service import ReconciliationService


@dataclass(frozen=True, slots=True)
class ReporteMensualGenerado:
    """Representa un reporte mensual listo para guardar o visualizar."""

    mes: str
    anio: int
    mes_numero: int
    fecha_generacion: datetime
    estructura: ReporteEstructurado
    contenido: str


@dataclass(frozen=True, slots=True)
class ReporteCifradoAbierto:
    """Representa un reporte descifrado dentro de Avalancha V2."""

    id: str
    mes: str
    fecha_generacion: str
    titulo: str
    contenido: str


class ReportService:
    """Coordina generacion, cifrado y lectura interna de reportes."""

    MESES = (
        "",
        "Enero",
        "Febrero",
        "Marzo",
        "Abril",
        "Mayo",
        "Junio",
        "Julio",
        "Agosto",
        "Septiembre",
        "Octubre",
        "Noviembre",
        "Diciembre",
    )

    def __init__(
        self,
        data_dir: str | Path = "data",
        reports_dir: str | Path = "reportes",
        key_path: str | Path = "config/reporte.key",
        repository: BudgetRepository | None = None,
        financial_service: FinancialSummaryService | None = None,
        gestor_reportes: GestorReportes | None = None,
    ) -> None:
        """Inicializa servicios y repositorios usados por reportes."""
        self.data_dir = Path(data_dir)
        self.repository = repository or BudgetRepository(self.data_dir)
        self.financial_service = (
            financial_service or FinancialSummaryService()
        )
        self.gestor_reportes = gestor_reportes or GestorReportes(
            reports_dir,
            ProveedorClaveLocal(key_path),
        )

    def construir_datos(self, resumen: ResumenMensual) -> dict[str, object]:
        """Convierte un resumen mensual en una estructura serializable."""
        return asdict(resumen)

    def renderizar_txt(
        self,
        resumen: ResumenMensual | ReporteEstructurado,
    ) -> str:
        """Renderiza un resumen o estructura como texto legible."""
        if isinstance(resumen, ReporteEstructurado):
            return self._renderizar_estructura(resumen)
        return "\n".join(
            [
                "AVALANCHA - REPORTE MENSUAL",
                f"Mes reportado: {resumen.mes}",
                "",
                "RESUMEN FINANCIERO",
                f"Ingresos reales: {resumen.ingresos_reales}",
                f"Gastos reales: {resumen.gastos_reales}",
                f"Flujo libre: {resumen.flujo_libre}",
                f"Deuda total: {resumen.deuda_total}",
                f"Patrimonio neto: {resumen.patrimonio_neto}",
            ],
        )

    def generar_reporte_mensual(
        self,
        mes: int,
        anio: int,
    ) -> ReporteMensualGenerado:
        """Genera un reporte mensual desde datos reales de V2."""
        self._validar_mes_anio(mes, anio)
        budget = self.repository.load(anio, mes)
        movimientos = self._movement_service(anio, mes).obtener_movimientos()
        debts = self.repository.load_debts()
        accounts = self._account_service().obtener_cuentas()
        payments = self.repository.debt_payment_totals(budget)
        indicators = self.financial_service.calcular_indicadores_mensuales(
            movimientos=budget.transactions,
            categorias=budget.categories,
            recurrentes=budget.recurring_items,
            deudas=debts,
            cuentas=accounts,
            pagos_por_deuda=payments,
        )
        reconciliacion = self._reconciliation_service(
            anio,
            mes,
        ).resumen_conciliacion(accounts)
        presupuesto = self._budget_service(anio, mes)
        ejecucion = presupuesto.calcular_ejecucion_general()
        estructura = self._crear_estructura(
            budget=budget,
            movimientos=movimientos,
            indicadores=indicators,
            conciliacion=reconciliacion,
            ejecucion=ejecucion,
        )
        return ReporteMensualGenerado(
            mes=budget.label,
            anio=anio,
            mes_numero=mes,
            fecha_generacion=datetime.now().replace(microsecond=0),
            estructura=estructura,
            contenido=self._renderizar_estructura(estructura),
        )

    def guardar_reporte_cifrado(
        self,
        reporte: ReporteMensualGenerado | ReporteEstructurado,
        nombre_archivo: str | None = None,
    ) -> dict[str, Any]:
        """Guarda un reporte cifrado sin sobrescribir meses existentes."""
        estructura = (
            reporte.estructura
            if isinstance(reporte, ReporteMensualGenerado)
            else reporte
        )
        mes = (
            reporte.mes
            if isinstance(reporte, ReporteMensualGenerado)
            else self._obtener_mes_desde_estructura(estructura)
        )
        if not estructura.encabezado and not estructura.secciones:
            raise ValueError("No se puede guardar un reporte vacio.")
        self._validar_nombre_archivo(nombre_archivo, mes)
        try:
            return self.gestor_reportes.guardar_reporte(estructura, mes)
        except ReporteDuplicadoError as exc:
            raise ValueError(str(exc)) from exc

    def abrir_reporte_cifrado(
        self,
        ruta: str | Path,
    ) -> ReporteCifradoAbierto:
        """Abre un reporte cifrado por ID, nombre o ruta de archivo."""
        reporte_id = self._resolver_reporte_id(ruta)
        documento = self.gestor_reportes.abrir_reporte(reporte_id)
        estructura = ReporteEstructurado(
            encabezado=list(documento.get("encabezado", [])),
            secciones=[
                SeccionReporte(
                    str(seccion.get("titulo", "")),
                    list(seccion.get("lineas", [])),
                )
                for seccion in documento.get("secciones", [])
                if isinstance(seccion, dict)
            ],
        )
        return ReporteCifradoAbierto(
            id=str(documento.get("id", reporte_id)),
            mes=str(documento.get("mes", "")),
            fecha_generacion=str(documento.get("fecha_creacion", "")),
            titulo=estructura.encabezado[0] if estructura.encabezado else "",
            contenido=self._renderizar_estructura(estructura),
        )

    def listar_reportes(self) -> list[dict[str, Any]]:
        """Lista reportes cifrados existentes."""
        return self.gestor_reportes.listar_reportes()

    def eliminar_reporte(self, reporte_id: str) -> None:
        """Elimina un reporte cifrado autorizado desde la interfaz."""
        if not reporte_id:
            raise ValueError("Debe seleccionar un reporte.")
        self.gestor_reportes.eliminar_reporte(reporte_id)

    def obtener_ruta_reportes(self) -> Path:
        """Devuelve la carpeta local de reportes cifrados."""
        return self.gestor_reportes.carpeta_reportes

    def _crear_estructura(
        self,
        budget: MonthlyBudget,
        movimientos: list[Any],
        indicadores: Any,
        conciliacion: dict[str, object],
        ejecucion: list[dict[str, object]],
    ) -> ReporteEstructurado:
        """Construye una estructura neutral para el reporte mensual."""
        fecha = datetime.now().replace(microsecond=0)
        diagnostico = self._diagnostico(indicadores, conciliacion)
        saldo_real_total = int(conciliacion["saldo_real_total"])
        saldo_registrado_total = int(
            conciliacion["saldo_registrado_total"],
        )
        diferencia_total = int(conciliacion["diferencia_total"])
        encabezado = [
            "AVALANCHA - REPORTE MENSUAL",
            (
                "Mes reportado: "
                f"{self.MESES[budget.month]} {budget.year}"
            ),
            f"Generado: {fecha.strftime('%d-%m-%Y %H:%M')}",
        ]
        secciones = [
            SeccionReporte(
                "RESUMEN FINANCIERO",
                [
                    (
                        "Ingresos reales: "
                        f"{self._format_clp(indicadores.ingresos_reales)}"
                    ),
                    (
                        "Gastos reales: "
                        f"{self._format_clp(indicadores.gastos_reales)}"
                    ),
                    (
                        "Flujo libre: "
                        f"{self._format_clp(indicadores.flujo_libre)}"
                    ),
                    (
                        "Resultado esperado: "
                        f"{self._format_clp(indicadores.resultado_esperado)}"
                    ),
                    f"Estado financiero: {self._estado_financiero(diagnostico)}",
                ],
            ),
            SeccionReporte(
                "DEUDA",
                [
                    (
                        "Deuda actual: "
                        f"{self._format_clp(indicadores.deuda_actual)}"
                    ),
                    (
                        "Variacion deuda: "
                        f"{self._format_clp(indicadores.variacion_deuda)}"
                    ),
                    (
                        "Pago mensual deuda: "
                        f"{self._format_clp(indicadores.pago_mensual_deuda)}"
                    ),
                    (
                        "Interés mensual estimado: "
                        f"{self._format_clp(indicadores.interes_mensual_estimado)}"
                    ),
                    (
                        "Amortizacion neta: "
                        f"{self._format_clp(indicadores.amortizacion_neta)}"
                    ),
                ],
            ),
            SeccionReporte(
                "PATRIMONIO",
                [
                    (
                        "Patrimonio neto: "
                        f"{self._format_clp(indicadores.patrimonio_neto)}"
                    ),
                    (
                        "Activos liquidos: "
                        f"{self._format_clp(indicadores.activos_liquidos)}"
                    ),
                    (
                        "Pasivos totales: "
                        f"{self._format_clp(indicadores.pasivos_totales)}"
                    ),
                ],
            ),
            SeccionReporte(
                "CONCILIACION",
                [
                    (
                        "Saldo real total: "
                        f"{self._format_clp(saldo_real_total)}"
                    ),
                    (
                        "Saldo registrado total: "
                        f"{self._format_clp(saldo_registrado_total)}"
                    ),
                    (
                        "Diferencia total: "
                        f"{self._format_clp(diferencia_total)}"
                    ),
                    (
                        "Fecha ultima conciliacion: "
                        f"{conciliacion['fecha_ultima_conciliacion'] or 'Sin datos'}"
                    ),
                    (
                        "Cuentas sin conciliar: "
                        f"{conciliacion['cuentas_sin_conciliar']}"
                    ),
                ],
            ),
            SeccionReporte(
                "GASTOS",
                [
                    (
                        "Gastos imprevistos: "
                        f"{self._format_clp(indicadores.gastos_imprevistos)}"
                    ),
                    (
                        "Movimientos imprevistos: "
                        f"{self._contar_imprevistos(movimientos)}"
                    ),
                    "",
                    "Detalle de imprevistos:",
                    *self._lineas_imprevistos(movimientos),
                    "",
                    "Principales gastos del mes:",
                    *self._lineas_principales_gastos(
                        indicadores.principales_gastos,
                    ),
                    "",
                        "Categorías sobrepasadas:",
                    *self._lineas_o_sin_datos(
                        indicadores.categorias_sobrepasadas,
                    ),
                    "",
                        "Categorías sin presupuesto:",
                    *self._lineas_o_sin_datos(
                        indicadores.categorias_sin_presupuesto,
                    ),
                    "",
                    "Ejecucion presupuestaria:",
                    *self._lineas_ejecucion(ejecucion),
                ],
            ),
            SeccionReporte(
                "DIAGNOSTICO FINANCIERO",
                diagnostico,
            ),
        ]
        if not movimientos:
            secciones.append(
                SeccionReporte(
                    "OBSERVACIONES",
                    ["No existen movimientos registrados para este mes."],
                ),
            )
        return ReporteEstructurado(encabezado, secciones)

    @staticmethod
    def _renderizar_estructura(estructura: ReporteEstructurado) -> str:
        """Renderiza una estructura de reporte a texto."""
        lineas: list[str] = []
        lineas.extend(estructura.encabezado)
        for seccion in estructura.secciones:
            lineas.extend(["", seccion.titulo])
            lineas.extend(seccion.lineas)
        return "\n".join(lineas).strip() + "\n"

    def _movement_service(self, anio: int, mes: int) -> MovementService:
        """Crea servicio de movimientos para el mes solicitado."""
        return MovementService(
            data_dir=self.data_dir,
            year=anio,
            month=mes,
            repository=self.repository,
        )

    def _budget_service(self, anio: int, mes: int) -> BudgetService:
        """Crea servicio de presupuestos para el mes solicitado."""
        movement_service = self._movement_service(anio, mes)
        return BudgetService(
            data_dir=self.data_dir,
            year=anio,
            month=mes,
            repository=self.repository,
            movement_service=movement_service,
        )

    def _account_service(self) -> AccountService:
        """Crea servicio de cuentas para el reporte."""
        return AccountService(
            data_dir=self.data_dir,
            repository=self.repository,
        )

    def _reconciliation_service(
        self,
        anio: int,
        mes: int,
    ) -> ReconciliationService:
        """Crea servicio de conciliacion para el mes solicitado."""
        return ReconciliationService(
            data_dir=self.data_dir,
            year=anio,
            month=mes,
            account_service=self._account_service(),
            movement_service=self._movement_service(anio, mes),
            repository=self.repository,
        )

    @staticmethod
    def _diagnostico(
        indicadores: Any,
        conciliacion: dict[str, object],
    ) -> list[str]:
        """Genera diagnostico financiero por reglas deterministicas."""
        alertas: list[str] = []
        if indicadores.flujo_libre < 0:
            alertas.append("[ROJO] El flujo libre es negativo.")
        if indicadores.variacion_deuda < 0:
            alertas.append("[ROJO] La deuda aumento respecto al mes anterior.")
        if indicadores.amortizacion_neta <= 0:
            alertas.append("[ROJO] Los pagos no amortizan la deuda.")
        diferencia = int(conciliacion["diferencia_total"])
        if diferencia != 0:
            alertas.append("[AMARILLO] Existen diferencias de conciliacion.")
        if indicadores.categorias_sin_presupuesto:
            alertas.append("[AMARILLO] Hay categorias sin presupuesto.")
        if indicadores.categorias_sobrepasadas:
            alertas.append("[AMARILLO] Hay categorias sobrepasadas.")
        return alertas or ["[VERDE] Sin alertas criticas."]

    @staticmethod
    def _estado_financiero(diagnostico: list[str]) -> str:
        """Calcula estado general segun diagnostico."""
        if any(linea.startswith("[ROJO]") for linea in diagnostico):
            return "Rojo"
        if any(linea.startswith("[AMARILLO]") for linea in diagnostico):
            return "Amarillo"
        return "Verde"

    @staticmethod
    def _lineas_principales_gastos(
        ranking: list[dict[str, Any]],
    ) -> list[str]:
        """Renderiza ranking de principales gastos."""
        if not ranking:
            return ["Sin datos."]
        return [
            (
                f"{index}. {item['categoria']}: "
                f"{ReportService._format_clp(int(item['monto']))}"
            )
            for index, item in enumerate(ranking, start=1)
        ]

    @staticmethod
    def _contar_imprevistos(movimientos: list[Any]) -> int:
        """Cuenta movimientos marcados como imprevistos."""
        return sum(
            1
            for movimiento in movimientos
            if bool(getattr(movimiento, "imprevisto", False))
        )

    @staticmethod
    def _lineas_imprevistos(movimientos: list[Any]) -> list[str]:
        """Renderiza movimientos imprevistos sin perder su clase."""
        imprevistos = [
            movimiento
            for movimiento in movimientos
            if bool(getattr(movimiento, "imprevisto", False))
        ]
        if not imprevistos:
            return ["Sin datos."]
        return [
            (
                f"- {movimiento.fecha.strftime('%d-%m-%Y')} | "
                f"{movimiento.categoria} | "
                f"{movimiento.descripcion or 'Sin descripcion'} | "
                f"{ReportService._format_clp(int(movimiento.monto))} | "
                "Clase: Imprevisto"
            )
            for movimiento in imprevistos
        ]

    @staticmethod
    def _lineas_o_sin_datos(valores: list[str]) -> list[str]:
        """Renderiza una lista textual o ausencia de datos."""
        if not valores:
            return ["Sin datos."]
        return [f"- {valor}" for valor in valores]

    @staticmethod
    def _lineas_ejecucion(rows: list[dict[str, object]]) -> list[str]:
        """Renderiza ejecucion presupuestaria resumida."""
        if not rows:
            return ["Sin presupuestos registrados."]
        lineas = []
        for row in rows:
            presupuesto = row["presupuesto"]
            ejecucion = row["ejecucion"]
            lineas.append(
                f"- {presupuesto.categoria}: "
                f"{ReportService._format_clp(ejecucion.monto_gastado)} / "
                f"{ReportService._format_clp(ejecucion.monto_presupuestado)} "
                f"({ejecucion.porcentaje_utilizado:.1f}%)",
            )
        return lineas

    @staticmethod
    def _format_clp(amount: int) -> str:
        """Formatea un entero como moneda CLP."""
        prefix = "-$" if amount < 0 else "$"
        return f"{prefix} {abs(amount):,.0f}".replace(",", ".")

    @staticmethod
    def _validar_mes_anio(mes: int, anio: int) -> None:
        """Valida mes y anio antes de leer datos."""
        try:
            validate_month(int(anio), int(mes))
        except (TypeError, ValueError) as exc:
            raise ValueError("El mes o anio no es valido.") from exc

    @staticmethod
    def _validar_nombre_archivo(
        nombre_archivo: str | None,
        mes: str,
    ) -> None:
        """Valida estrategia de nombre sin permitir otro mes."""
        if not nombre_archivo:
            return
        nombre = Path(nombre_archivo).name
        esperado = f"R{mes}.avr"
        if nombre != esperado:
            raise ValueError(
                f"El nombre del reporte debe ser {esperado}.",
            )

    @staticmethod
    def _obtener_mes_desde_estructura(
        estructura: ReporteEstructurado,
    ) -> str:
        """Extrae etiqueta YYYY-MM desde un reporte estructurado."""
        for linea in estructura.encabezado:
            if "Mes reportado:" in linea:
                partes = linea.rsplit(" ", 2)
                if len(partes) == 3 and partes[-1].isdigit():
                    mes_nombre = partes[-2].casefold()
                    meses = {
                        nombre.casefold(): indice
                        for indice, nombre in enumerate(ReportService.MESES)
                        if nombre
                    }
                    numero = meses.get(mes_nombre)
                    if numero:
                        return f"{int(partes[-1]):04d}-{numero:02d}"
        raise ValueError("No se pudo determinar el mes del reporte.")

    def _resolver_reporte_id(self, ruta: str | Path) -> str:
        """Resuelve un identificador desde ID, nombre o ruta."""
        valor = str(ruta)
        reportes = self.listar_reportes()
        for item in reportes:
            if valor == item.get("id"):
                return str(item["id"])
            if valor == item.get("nombre") or valor == item.get("ruta"):
                return str(item["id"])
            if Path(valor) == self.obtener_ruta_reportes() / str(item["ruta"]):
                return str(item["id"])
        raise ValueError("No se encontro el reporte seleccionado.")
