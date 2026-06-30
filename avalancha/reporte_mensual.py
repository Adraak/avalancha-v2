"""Construcción estructurada de reportes mensuales de Avalancha."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from avalancha.finanzas import (
    AlertaDiagnostico,
    AnalizadorResumen,
    GestorConciliacion,
    GestorDeudas,
    RankingDeudas,
)
from avalancha.formatting import format_clp, format_date_for_display
from avalancha.models import CuentaFinanciera, MonthlyBudget


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


@dataclass(frozen=True)
class SeccionReporte:
    """Representa una sección independiente del formato de salida."""

    titulo: str
    lineas: list[str]


@dataclass(frozen=True)
class ReporteEstructurado:
    """Contiene el reporte neutral que podrá usar otro exportador."""

    encabezado: list[str]
    secciones: list[SeccionReporte]


class GeneradorReporteMensual:
    """Construye una fotografía financiera independiente del formato."""

    def __init__(
        self,
        presupuesto: MonthlyBudget,
        gestor_deudas: GestorDeudas,
        cuentas: list[CuentaFinanciera],
        analizador: AnalizadorResumen,
        diagnosticos: list[AlertaDiagnostico],
        fecha_libertad: str | None = None,
        nivel_riesgo: str = "",
        fecha_generacion: datetime | None = None,
        historial: list[dict[str, Any]] | None = None,
        puntaje_riesgo: int | None = None,
    ) -> None:
        """Inicializa el generador con una fotografía de los datos actuales."""
        self.presupuesto = presupuesto
        self.gestor_deudas = gestor_deudas
        self.cuentas = cuentas
        self.analizador = analizador
        self.diagnosticos = diagnosticos
        self.fecha_libertad = fecha_libertad
        self.nivel_riesgo = nivel_riesgo
        self.fecha_generacion = fecha_generacion or datetime.now()
        self.historial = sorted(
            historial or [],
            key=lambda item: str(item.get("mes", "")),
        )
        self.puntaje_riesgo = puntaje_riesgo

    def generar_estructura_reporte(self) -> ReporteEstructurado:
        """Construye el contenido financiero sin ligarlo al formato TXT."""
        datos = self._obtener_datos_actuales()
        anterior = self._obtener_mes_anterior()
        encabezado = [
            "AVALANCHA - REPORTE MENSUAL",
            (
                f"Mes reportado: {MESES[self.presupuesto.month]} "
                f"{self.presupuesto.year}"
            ),
            (
                "Generado: "
                f"{self.fecha_generacion.strftime('%d-%m-%Y %H:%M')}"
            ),
        ]
        secciones = [
            SeccionReporte(
                "RESUMEN EJECUTIVO",
                self._generar_resumen_ejecutivo(datos, anterior),
            ),
            SeccionReporte(
                "COMPARACIÓN CON EL MES ANTERIOR",
                self._generar_comparacion(datos, anterior),
            ),
            SeccionReporte(
                "INDICADORES",
                self._generar_indicadores(datos),
            ),
            SeccionReporte(
                "RESUMEN FINANCIERO",
                self._generar_resumen_financiero(datos),
            ),
            SeccionReporte("DEUDA", self._generar_deuda(datos)),
            SeccionReporte("PATRIMONIO", self._generar_patrimonio(datos)),
            SeccionReporte(
                "CONCILIACIÓN",
                self._generar_conciliacion(datos),
            ),
            SeccionReporte("GASTOS", self._generar_gastos(datos)),
            SeccionReporte(
                "DIAGNÓSTICO FINANCIERO",
                self._generar_diagnostico_inteligente(datos, anterior),
            ),
            SeccionReporte(
                "HITOS DEL MES",
                self._generar_hitos(datos, anterior),
            ),
            SeccionReporte(
                "OPORTUNIDADES",
                self._generar_oportunidades(datos),
            ),
        ]
        return ReporteEstructurado(encabezado, secciones)

    def _obtener_datos_actuales(self) -> dict[str, Any]:
        """Reúne una sola vez todos los indicadores usados por el reporte."""
        totales = self.presupuesto.totals()
        deuda = self.gestor_deudas.obtener_resumen_deuda()
        conciliacion = GestorConciliacion(self.cuentas).obtener_resumen()
        activos = self._calcular_activos_liquidos()
        patrimonio = self.gestor_deudas.patrimonio_neto(
            assets=activos or 0
        )
        filas = self.presupuesto.category_report()
        presupuesto_gastos = self.presupuesto.budgeted_totals()["expenses"]
        pago = int(deuda["pago_mensual_total"])
        interes = int(deuda["interes_mensual_estimado"])
        amortizacion = int(deuda["amortizacion_neta"])
        estado = self.analizador.calcular_estado_financiero_general(
            self.nivel_riesgo
        )
        return {
            "ingresos": totales["income"],
            "gastos": totales["expenses"],
            "flujo": totales["balance"],
            "resultado_esperado": (
                self.analizador.calcular_resultado_esperado_fin_mes()
            ),
            "estado": estado["estado"],
            "deuda": self.gestor_deudas.deuda_total_actual(),
            "variacion_deuda": (
                self.gestor_deudas.variacion_mensual_deuda()
            ),
            "pago_deuda": pago,
            "interes": interes,
            "amortizacion": amortizacion,
            "activos": activos,
            "patrimonio": patrimonio,
            "pasivos": self.gestor_deudas.deuda_total_actual(),
            "pendiente": (
                self.analizador.calcular_pendiente_clasificar()
            ),
            "conciliacion": conciliacion,
            "imprevistos": self.presupuesto.expense_breakdown()[
                "unexpected"
            ],
            "ranking": self.analizador.obtener_ranking_gastos(),
            "filas_categorias": filas,
            "presupuesto_gastos": presupuesto_gastos,
            "porcentaje_reduccion": self._porcentaje_reduccion_deuda(),
            "porcentaje_interes": self._porcentaje(interes, pago),
            "porcentaje_amortizacion": self._porcentaje(
                amortizacion,
                pago,
            ),
            "porcentaje_ejecucion": self._porcentaje(
                totales["expenses"],
                presupuesto_gastos,
            ),
            "porcentaje_conciliacion": (
                self._porcentaje_conciliacion(conciliacion)
            ),
        }

    def _obtener_mes_anterior(self) -> dict[str, Any] | None:
        """Devuelve el último cierre anterior al mes reportado."""
        candidatos = [
            item
            for item in self.historial
            if str(item.get("mes", "")) < self.presupuesto.label
        ]
        return candidatos[-1] if candidatos else None

    def _generar_resumen_ejecutivo(
        self,
        datos: dict[str, Any],
        anterior: dict[str, Any] | None,
    ) -> list[str]:
        """Resume en no más de diez líneas la situación del mes."""
        lineas = []
        reduccion = datos["porcentaje_reduccion"]
        if reduccion is not None:
            verbo = "disminuyó" if reduccion >= 0 else "aumentó"
            porcentaje = self._formatear_porcentaje(abs(reduccion))
            lineas.append(
                f"✔ La deuda {verbo} un {porcentaje}."
            )
        patrimonio_anterior = self._valor_historico(
            anterior,
            "patrimonio_neto",
        )
        if patrimonio_anterior is not None:
            cambio = datos["patrimonio"] - patrimonio_anterior
            verbo = "mejoró" if cambio >= 0 else "empeoró"
            lineas.append(
                f"✔ El patrimonio {verbo} {format_clp(abs(cambio))}."
            )
        flujo = datos["flujo"]
        lineas.append(
            "✔ El flujo libre es positivo."
            if flujo >= 0
            else "✔ El flujo libre continúa negativo."
        )
        if abs(datos["pendiente"]) > 20_000:
            lineas.append("✔ Existen diferencias de conciliación.")
        else:
            lineas.append("✔ Las cuentas están conciliadas.")
        if datos["ranking"]:
            lineas.append(
                "✔ El principal gasto del mes fue "
                f"{datos['ranking'][0]['categoria']}."
            )
        nivel = self.nivel_riesgo or datos["estado"]
        lineas.append(
            f"✔ El riesgo financiero permanece en estado {nivel}."
        )
        return lineas[:10]

    def _generar_comparacion(
        self,
        datos: dict[str, Any],
        anterior: dict[str, Any] | None,
    ) -> list[str]:
        """Compara el mes actual con el cierre histórico anterior."""
        if anterior is None:
            return ["No existe información histórica suficiente."]
        lineas = []
        comparaciones = (
            ("INGRESOS", "ingresos_reales", datos["ingresos"]),
            ("GASTOS", "gastos_reales", datos["gastos"]),
            ("DEUDA", "deuda_total", datos["deuda"]),
            ("PATRIMONIO", "patrimonio_neto", datos["patrimonio"]),
        )
        for titulo, campo, actual in comparaciones:
            previo = self._valor_historico(anterior, campo)
            lineas.append(titulo)
            lineas.extend(self._lineas_comparacion_monetaria(previo, actual))
            lineas.append("")
        riesgo_anterior = self._valor_historico(
            anterior,
            "riesgo_financiero",
        )
        lineas.append("RIESGO FINANCIERO")
        lineas.append(
            f"Mes anterior: {riesgo_anterior}"
            if riesgo_anterior is not None
            else "Mes anterior: Sin datos"
        )
        lineas.append(
            f"Mes actual: {self.puntaje_riesgo}"
            if self.puntaje_riesgo is not None
            else "Mes actual: Sin datos"
        )
        if riesgo_anterior is None or self.puntaje_riesgo is None:
            lineas.append("Cambio: Sin datos")
        else:
            lineas.append(
                f"Cambio: {self.puntaje_riesgo - riesgo_anterior:+d} puntos"
            )
        return lineas

    def _generar_indicadores(self, datos: dict[str, Any]) -> list[str]:
        """Genera los porcentajes de eficiencia financiera del mes."""
        indicadores = (
            ("Reducción deuda", datos["porcentaje_reduccion"]),
            (
                "Pago destinado a amortización",
                datos["porcentaje_amortizacion"],
            ),
            ("Pago destinado a intereses", datos["porcentaje_interes"]),
            (
                "Ejecución del presupuesto",
                datos["porcentaje_ejecucion"],
            ),
            (
                "Conciliación de cuentas",
                datos["porcentaje_conciliacion"],
            ),
        )
        lineas = []
        for nombre, valor in indicadores:
            lineas.append(f"{nombre}:")
            lineas.append(
                self._formatear_porcentaje(valor)
                if valor is not None
                else "Sin datos"
            )
            lineas.append("")
        return lineas[:-1]

    def _generar_resumen_financiero(
        self,
        datos: dict[str, Any],
    ) -> list[str]:
        """Genera los principales resultados operativos del mes."""
        return [
            f"Ingresos reales: {format_clp(datos['ingresos'])}",
            f"Gastos reales: {format_clp(datos['gastos'])}",
            f"Flujo libre: {format_clp(datos['flujo'])}",
            (
                "Resultado esperado: "
                f"{format_clp(datos['resultado_esperado'])}"
            ),
            f"Estado financiero: {datos['estado']}",
        ]

    def _generar_deuda(self, datos: dict[str, Any]) -> list[str]:
        """Genera el detalle de deuda y libertad financiera."""
        return [
            f"Deuda actual: {format_clp(datos['deuda'])}",
            (
                "Variación deuda: "
                f"{format_clp(datos['variacion_deuda'])}"
            ),
            f"Pago mensual deuda: {format_clp(datos['pago_deuda'])}",
            (
                "Interés mensual estimado: "
                f"{format_clp(datos['interes'])}"
            ),
            f"Amortización neta: {format_clp(datos['amortizacion'])}",
            (
                "Libertad financiera estimada: "
                f"{self._formatear_fecha_opcional(self.fecha_libertad)}"
            ),
            f"Restan: {self._calcular_meses_restantes()}",
        ]

    def _generar_patrimonio(self, datos: dict[str, Any]) -> list[str]:
        """Genera activos, pasivos y patrimonio neto."""
        return [
            f"Patrimonio neto: {format_clp(datos['patrimonio'])}",
            (
                "Activos líquidos: "
                f"{self._formatear_monto_opcional(datos['activos'])}"
            ),
            f"Pasivos totales: {format_clp(datos['pasivos'])}",
        ]

    def _generar_conciliacion(self, datos: dict[str, Any]) -> list[str]:
        """Genera el estado y detalle de conciliación bancaria."""
        conciliacion = datos["conciliacion"]
        fecha = self._formatear_fecha_opcional(
            conciliacion["fecha_ultima_conciliacion"]
        )
        return [
            f"Pendiente de clasificar: {format_clp(datos['pendiente'])}",
            (
                "Saldo real total: "
                f"{format_clp(int(conciliacion['saldo_real_total']))}"
            ),
            (
                "Saldo registrado total: "
                f"{format_clp(int(conciliacion['saldo_registrado_total']))}"
            ),
            (
                "Diferencia total: "
                f"{format_clp(int(conciliacion['diferencia_total']))}"
            ),
            f"Fecha última conciliación: {fecha}",
            "Cuentas con diferencia:",
            *self._generar_lineas_cuentas_con_diferencia(),
        ]

    def _generar_gastos(self, datos: dict[str, Any]) -> list[str]:
        """Genera imprevistos, ranking y categorías problemáticas."""
        filas = datos["filas_categorias"]
        return [
            f"Gastos imprevistos: {format_clp(datos['imprevistos'])}",
            "",
            "PRINCIPALES GASTOS",
            *self._generar_lineas_principales_gastos(),
            "",
            "CATEGORÍAS SOBREPASADAS",
            *self._generar_lineas_categorias(filas, "sobrepasado"),
            "",
            "CATEGORÍAS SIN PRESUPUESTO",
            *self._generar_lineas_categorias(filas, "sin presupuesto"),
        ]

    def _generar_diagnostico_inteligente(
        self,
        datos: dict[str, Any],
        anterior: dict[str, Any] | None,
    ) -> list[str]:
        """Construye un análisis determinístico mediante reglas."""
        lineas = []
        reduccion = datos["porcentaje_reduccion"]
        if reduccion is not None:
            verbo = "disminuyó" if reduccion >= 0 else "aumentó"
            lineas.append(
                f"Durante {MESES[self.presupuesto.month].lower()} la deuda "
                f"{verbo} un {self._formatear_porcentaje(abs(reduccion))}."
            )
        patrimonio_anterior = self._valor_historico(
            anterior,
            "patrimonio_neto",
        )
        if patrimonio_anterior is not None:
            verbo = (
                "mejora"
                if datos["patrimonio"] > patrimonio_anterior
                else "deterioro"
            )
            lineas.append(
                f"El patrimonio presentó una {verbo} respecto al mes "
                "anterior."
            )
        if datos["flujo"] < 0:
            lineas.append(
                "El flujo libre continúa negativo, por lo que existe "
                "un déficit operativo."
            )
        else:
            lineas.append(
                "El flujo libre es positivo y permite absorber "
                "compromisos del mes."
            )
        if abs(datos["pendiente"]) > 20_000:
            lineas.append(
                "Persisten diferencias de conciliación bancaria que "
                "deberían corregirse antes del cierre definitivo."
            )
        ranking = RankingDeudas(
            self.gestor_deudas.debts,
            self.gestor_deudas.payment_totals,
        ).obtener()
        if ranking:
            lineas.append(
                "La principal oportunidad de mejora es priorizar "
                f"{ranking[0]['nombre']}."
            )
        return lineas

    def _generar_hitos(
        self,
        datos: dict[str, Any],
        anterior: dict[str, Any] | None,
    ) -> list[str]:
        """Detecta logros mensuales usando datos históricos disponibles."""
        hitos = []
        if self._es_mayor_reduccion_anual(datos):
            hitos.append("✔ Mayor reducción de deuda del año.")
        if self._es_primera_conciliacion_completa(datos):
            hitos.append("✔ Primer mes con conciliación completa.")
        if self._patrimonio_mejora_tres_meses(datos):
            hitos.append("✔ Patrimonio mejora por tercer mes consecutivo.")
        riesgo_anterior = self._valor_historico(
            anterior,
            "riesgo_financiero",
        )
        if (
            riesgo_anterior is not None
            and self.puntaje_riesgo is not None
            and self.puntaje_riesgo < riesgo_anterior
        ):
            hitos.append(
                "✔ Riesgo financiero disminuye respecto al mes anterior."
            )
        return hitos or ["No se registran hitos este mes."]

    def _generar_oportunidades(self, datos: dict[str, Any]) -> list[str]:
        """Genera recomendaciones accionables mediante reglas."""
        oportunidades = []
        ranking = RankingDeudas(
            self.gestor_deudas.debts,
            self.gestor_deudas.payment_totals,
        ).obtener()
        if ranking:
            oportunidades.append(
                f"• Priorizar el pago de {ranking[0]['nombre']}."
            )
        sin_presupuesto = [
            fila["name"]
            for fila in datos["filas_categorias"]
            if fila["status"] == "sin presupuesto"
        ]
        for categoria in sin_presupuesto[:2]:
            oportunidades.append(
                f"• Definir presupuesto para {categoria}."
            )
        if datos["imprevistos"] > 0:
            oportunidades.append("• Reducir gastos imprevistos.")
        if abs(datos["pendiente"]) > 20_000:
            oportunidades.append(
                "• Corregir diferencias de conciliación."
            )
        if datos["flujo"] < 0:
            oportunidades.append(
                "• Ajustar gastos para recuperar flujo libre positivo."
            )
        return oportunidades or ["No se detectan oportunidades críticas."]

    def _calcular_activos_liquidos(self) -> int | None:
        """Suma saldos reales de cuentas que representan dinero disponible."""
        saldos = [
            cuenta.real_balance
            for cuenta in self.cuentas
            if (
                cuenta.active
                and cuenta.account_type != "tarjeta_credito"
                and cuenta.real_balance is not None
            )
        ]
        return sum(saldos) if saldos else None

    def _porcentaje_reduccion_deuda(self) -> float | None:
        """Calcula la reducción de deuda respecto al saldo anterior."""
        actual = self.gestor_deudas.deuda_total_actual()
        variacion = self.gestor_deudas.variacion_mensual_deuda()
        anterior = actual + variacion
        if anterior <= 0:
            return None
        return variacion / anterior * 100

    @staticmethod
    def _porcentaje(numerador: int, denominador: int) -> float | None:
        """Calcula un porcentaje o devuelve ausencia sin denominador."""
        if denominador <= 0:
            return None
        return numerador / denominador * 100

    @staticmethod
    def _porcentaje_conciliacion(
        conciliacion: dict[str, int | str | None],
    ) -> float | None:
        """Estima qué porcentaje del saldo real está conciliado."""
        real = abs(int(conciliacion["saldo_real_total"] or 0))
        diferencia = abs(int(conciliacion["diferencia_total"] or 0))
        if real <= 0:
            return None
        return max(0.0, min(100.0, 100 - diferencia / real * 100))

    def _calcular_meses_restantes(self) -> str:
        """Calcula meses calendario hasta la libertad financiera."""
        if not self.fecha_libertad:
            return "Sin datos"
        try:
            final = date.fromisoformat(self.fecha_libertad)
        except ValueError:
            return "Sin datos"
        inicio = self.fecha_generacion.date()
        meses = (final.year - inicio.year) * 12
        meses += final.month - inicio.month
        if final.day > inicio.day:
            meses += 1
        return f"{max(meses, 0)} meses"

    def _generar_lineas_cuentas_con_diferencia(self) -> list[str]:
        """Genera el detalle de cuentas con diferencias de conciliación."""
        cuentas = [
            cuenta
            for cuenta in self.cuentas
            if (
                cuenta.active
                and cuenta.difference is not None
                and cuenta.difference != 0
            )
        ]
        if not cuentas:
            return ["Sin diferencias registradas."]
        return [
            f"- {cuenta.name}: {format_clp(cuenta.difference or 0)}"
            for cuenta in sorted(
                cuentas,
                key=lambda actual: abs(actual.difference or 0),
                reverse=True,
            )
        ]

    def _generar_lineas_principales_gastos(self) -> list[str]:
        """Genera el ranking de las principales categorías de gasto."""
        ranking = self.analizador.obtener_ranking_gastos()
        if not ranking:
            return ["Sin datos."]
        return [
            f"{indice}. {item['categoria']}: {format_clp(item['monto'])}"
            for indice, item in enumerate(ranking, start=1)
        ]

    @staticmethod
    def _generar_lineas_categorias(
        filas: list[dict[str, object]],
        estado: str,
    ) -> list[str]:
        """Genera líneas para las categorías que comparten un estado."""
        seleccionadas = [
            fila for fila in filas if fila.get("status") == estado
        ]
        if not seleccionadas:
            return ["Sin datos."]
        return [
            f"- {fila['name']}: {format_clp(int(fila['actual']))}"
            for fila in seleccionadas
        ]

    @staticmethod
    def _lineas_comparacion_monetaria(
        anterior: int | None,
        actual: int,
    ) -> list[str]:
        """Genera valores y variaciones para una comparación monetaria."""
        if anterior is None:
            return [
                "Mes anterior: Sin datos",
                f"Mes actual: {format_clp(actual)}",
                "Variación: Sin datos",
                "Variación %: Sin datos",
            ]
        variacion = actual - anterior
        porcentaje = (
            variacion / abs(anterior) * 100
            if anterior != 0
            else None
        )
        return [
            f"Mes anterior: {format_clp(anterior)}",
            f"Mes actual: {format_clp(actual)}",
            f"Variación: {format_clp(variacion)}",
            (
                "Variación %: "
                f"{GeneradorReporteMensual._formatear_porcentaje(porcentaje)}"
                if porcentaje is not None
                else "Variación %: Sin datos"
            ),
        ]

    def _es_mayor_reduccion_anual(self, datos: dict[str, Any]) -> bool:
        """Indica si el mes tiene la mayor reducción anual disponible."""
        puntos = {
            str(item.get("mes", "")): item.get("deuda_total")
            for item in self.historial
            if str(item.get("mes", "")).startswith(
                f"{self.presupuesto.year:04d}-"
            )
        }
        puntos[self.presupuesto.label] = datos["deuda"]
        valores = []
        for mes, valor in sorted(puntos.items()):
            try:
                valores.append((mes, int(valor)))
            except (TypeError, ValueError):
                continue
        if len(valores) < 2:
            return False
        reducciones = [
            valores[indice - 1][1] - valores[indice][1]
            for indice in range(1, len(valores))
        ]
        return reducciones[-1] > 0 and reducciones[-1] == max(reducciones)

    def _es_primera_conciliacion_completa(
        self,
        datos: dict[str, Any],
    ) -> bool:
        """Indica si es el primer mes históricamente conciliado."""
        if abs(datos["pendiente"]) > 20_000:
            return False
        anteriores = [
            self._valor_historico(item, "diferencia_conciliacion")
            for item in self.historial
            if str(item.get("mes", "")) < self.presupuesto.label
        ]
        conocidos = [valor for valor in anteriores if valor is not None]
        return bool(conocidos) and all(
            abs(valor) > 20_000 for valor in conocidos
        )

    def _patrimonio_mejora_tres_meses(
        self,
        datos: dict[str, Any],
    ) -> bool:
        """Indica si el patrimonio mejoró durante tres meses seguidos."""
        valores = [
            self._valor_historico(item, "patrimonio_neto")
            for item in self.historial
            if str(item.get("mes", "")) < self.presupuesto.label
        ]
        conocidos = [valor for valor in valores if valor is not None]
        serie = conocidos[-2:] + [datos["patrimonio"]]
        return len(serie) == 3 and serie[0] < serie[1] < serie[2]

    @staticmethod
    def _valor_historico(
        snapshot: dict[str, Any] | None,
        campo: str,
    ) -> int | None:
        """Obtiene un entero histórico sin convertir ausencias en cero."""
        if snapshot is None or campo not in snapshot:
            return None
        try:
            return int(snapshot[campo])
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _formatear_porcentaje(valor: float | None) -> str:
        """Formatea porcentajes con coma decimal para lectura local."""
        if valor is None:
            return "Sin datos"
        return f"{valor:.2f}%".replace(".", ",")

    @staticmethod
    def _formatear_fecha_opcional(fecha_iso: object) -> str:
        """Formatea una fecha ISO o devuelve un texto de ausencia."""
        if not isinstance(fecha_iso, str) or not fecha_iso:
            return "Sin datos"
        try:
            return format_date_for_display(fecha_iso)
        except ValueError:
            return "Sin datos"

    @staticmethod
    def _formatear_monto_opcional(monto: int | None) -> str:
        """Formatea un monto disponible o devuelve un texto de ausencia."""
        return format_clp(monto) if monto is not None else "Sin datos"
