# Mapa de migracion Avalancha V2

Fecha: 29-06-2026

## Objetivo

Clasificar los modulos heredados antes de migrar pantallas reales a PySide6.
La prioridad es separar reglas financieras, servicios y UI Tkinter para que
Avalancha V2 use un nucleo reutilizable e independiente de la interfaz.

## Tabla de clasificacion

| Archivo actual | Proposito | Logica financiera | UI Tkinter | Destino propuesto | Prioridad | Observaciones |
|---|---|---:|---:|---|---|---|
| `avalancha/app.py` | Aplicacion Tkinter, pestañas, formularios, callbacks y helpers de presentacion. | Si | Si | `ui_tkinter/` y extraccion parcial a `core/` | Alta | Mantener como referencia funcional. Extraer solo reglas reutilizables. |
| `avalancha/models.py` | Modelos actuales: categorias, movimientos, recurrentes, deudas, cuentas y presupuesto mensual. | Si | No | `core/models/` | Alta | Fuente principal para los contratos de datos V2. |
| `avalancha/finanzas.py` | Deuda, simulacion, conciliacion, riesgo, ranking, diagnostico y analisis. | Si | No | `core/` y `services/` | Alta | Separar calculos puros en `core`; analisis operativo en `services`. |
| `avalancha/storage.py` | Persistencia JSON mensual y carga/guardado de presupuestos. | Parcial | No | `services/` y `data/` | Alta | Debe evolucionar a repositorios por perfil. |
| `avalancha/formatting.py` | Formato CLP, parseo de montos y fechas. | Parcial | No | `core/` o `services/` | Media | Utilidad transversal, libre de UI. |
| `avalancha/validaciones.py` | Validaciones de movimientos y deudas. | Si | No | `core/` | Alta | Consolidar con modelos y servicios de dominio. |
| `avalancha/historial_financiero.py` | Cierre mensual, snapshots e historial financiero. | Si | No | `services/` | Alta | Servicio clave para reportes historicos y tendencias. |
| `avalancha/reporte_mensual.py` | Generacion de reporte mensual estructurado en TXT. | Parcial | No | `services/` | Media | Separar contenido del render final. |
| `avalancha/gestor_reportes.py` | Gestion, cifrado y proteccion de reportes. | No | No | `services/` | Media | Servicio tecnico, no nucleo financiero puro. |
| `avalancha/perfiles.py` | Gestion de perfiles locales y demo. | Parcial | No | `services/` | Alta | Controlara rutas de datos por perfil en V2. |
| `avalancha/respaldo.py` | Backups automaticos locales. | No | No | `services/` | Media | Servicio tecnico de proteccion de datos. |
| `avalancha/__init__.py` | Marcador de paquete heredado. | No | No | `legacy/` | Baja | Mantener mientras exista compatibilidad heredada. |
| `ui_tkinter/avalancha/app.py` | Copia preservada de la interfaz Tkinter. | Si | Si | `ui_tkinter/` | Baja | Referencia funcional; no debe ser fuente principal de V2. |
| `ui_pyside6/main_window.py` | Chasis visual PySide6 y navegacion placeholder. | No | No | `ui_pyside6/` | Media | Consumira `core` y `services` en etapas posteriores. |
| `ui_pyside6/pages/*.py` | Paginas placeholder PySide6. | No | No | `ui_pyside6/` | Media | No migrar pantallas reales todavia. |

## Decisiones de arquitectura

- `core/` contendra modelos, reglas y calculos financieros puros.
- `services/` contendra orquestacion, reportes, perfiles, conciliacion,
  persistencia y operaciones que puedan usar archivos.
- `ui_tkinter/` queda como respaldo visual y referencia de comportamiento.
- `ui_pyside6/` no debe importar Tkinter ni reutilizar callbacks de `app.py`.
- Los modelos V2 deben poder importarse sin crear ventanas ni cargar frameworks
  graficos.

## Contratos creados en esta etapa

- `core/models/movimiento.py`
- `core/models/cuenta.py`
- `core/models/presupuesto.py`
- `core/models/deuda.py`
- `core/models/perfil_financiero.py`
- `core/models/resumen_mensual.py`

## Servicios base creados en esta etapa

- `services/financial_summary_service.py`
- `services/profile_service.py`
- `services/report_service.py`
- `services/reconciliation_service.py`

## Pendientes de migracion

- Extraer calculos maduros de `avalancha/finanzas.py` hacia servicios V2.
- Reemplazar dependencias directas a `avalancha/models.py` por modelos V2.
- Crear repositorios por perfil para archivos JSON.
- Migrar dashboard real de Resumen despues de estabilizar el nucleo.
- Mantener pruebas de independencia UI durante toda la migracion.

## Etapa 4 - Extraccion controlada de logica real

### Modulos extraidos

- `core/financial_metrics.py`: indicadores financieros puros.
- `services/budget_storage_service.py`: almacenamiento JSON base.
- `services/financial_summary_service.py`: resumen mensual usando `core`.
- `services/reconciliation_service.py`: conciliacion compatible con modelos
  V2 y heredados.

### Funciones migradas o cubiertas por equivalencia

- Ingresos reales.
- Gastos reales.
- Flujo libre.
- Resultado esperado de fin de mes.
- Deuda actual.
- Variacion mensual de deuda.
- Pago mensual total de deuda.
- Interés mensual estimado.
- Amortizacion neta.
- Patrimonio neto.
- Activos liquidos.
- Pasivos totales.
- Gastos imprevistos.
- Principales gastos.
- Categorías sobrepasadas.
- Categorías sin presupuesto.
- Conciliacion de cuentas.

### Funciones pendientes

- Proyeccion completa de deuda y curva mensual.
- Simulador de pagos completo.
- Ranking avanzado de deuda.
- Diagnostico financiero completo.
- Riesgo financiero.
- Persistencia mensual con herencia desde mes anterior.
- Adaptadores formales desde JSON heredado a modelos V2.

### Riesgos encontrados

- `avalancha/app.py` todavia mezcla UI, callbacks y reglas de presentacion.
- Los modelos heredados usan nombres en ingles y los modelos V2 usan nombres
  en español; se agregaron alias para compatibilidad gradual.
- La conciliacion debe seguir soportando cuentas heredadas mientras la UI V1
  exista dentro de V2 como referencia.

### Tests creados

- `tests/test_v2_financial_equivalence.py`
- `tests/test_v2_architecture.py`

## Etapa 6 - Migracion de Movimientos

### Modulos funcionales

- `services/movement_service.py`: CRUD completo de movimientos con validacion.
- `ui_pyside6/pages/movement_page.py`: tabla, busqueda, seleccion, doble clic
  para editar y botones de accion.
- `ui_pyside6/pages/movement_dialog.py`: formulario PySide6 para crear y
  editar movimientos.
- `ui_pyside6/pages/movements_page.py`: compatibilidad de importacion.

### Flujo de arquitectura aplicado

`PySide6 -> MovementService -> BudgetRepository heredado -> JSON mensual`

La interfaz no accede directamente a archivos ni a `BudgetRepository`.

### Dependencias Tkinter eliminadas

- La pantalla Movimientos V2 no usa Tkinter.
- `MovementService` no importa Tkinter ni PySide6.
- Las validaciones de movimientos viven en `services/movement_service.py`.

### Porcentaje aproximado migrado

- Movimientos: 100% funcional en V2 para CRUD basico.
- Proyecto V2 completo: 20% aproximado, porque Dashboard, Cuentas,
  Presupuestos, Conciliacion, Reportes, Perfiles y Configuracion aun no estan
  migrados funcionalmente.

### Riesgos encontrados

- El storage real sigue siendo el repositorio heredado; se usa como adaptador
  temporal para no duplicar datos.
- Los movimientos antiguos sin cuenta se muestran como `Sin cuenta`, pero para
  guardar registros nuevos se exige cuenta valida.
- La pantalla todavia no expone campos avanzados como deuda asociada,
  recurrente o imprevisto; el CRUD base solicitado si queda cubierto.

### Tests creados

- `tests/test_v2_movement_service.py`

## Etapa 8 - Migracion de Presupuestos

### Modulos funcionales

- `services/budget_service.py`: CRUD completo, validaciones y calculo de
  ejecucion presupuestaria.
- `ui_pyside6/pages/budgets_page.py`: tabla funcional con acciones Nuevo,
  Editar, Eliminar, Activar, Desactivar y Actualizar.
- `ui_pyside6/pages/budget_dialog.py`: formulario PySide6 para crear y editar
  presupuestos.
- `core/models/presupuesto.py`: contrato de presupuesto con datos minimos del
  modulo V2.

### Integracion aplicada

`PySide6 -> BudgetService -> MovementService -> BudgetRepository -> JSON`

Presupuestos calcula gasto real leyendo movimientos existentes. No duplica
movimientos ni crea una segunda fuente de datos.

### Dependencias eliminadas

- La pantalla Presupuestos V2 no usa Tkinter.
- `BudgetService` no importa PySide6 ni Tkinter.
- Las validaciones viven en `services/budget_service.py`.

### Estado del modulo Cuentas

Cuentas sigue pendiente como modulo PySide6 funcional. La integracion actual
usa cuentas existentes a traves de los movimientos, pero aun falta CRUD V2 de
cuentas.

### Porcentaje aproximado migrado

- Presupuestos: 100% del CRUD y ejecucion requeridos.
- Avalancha V2 total: 30% aproximado.

### Riesgos pendientes

- El repositorio de storage sigue siendo el heredado como adaptador temporal.
- Los presupuestos se persisten como categorias mensuales enriquecidas con
  metadatos V2. Esto evita duplicar datos, pero requiere mantener compatibilidad
  hasta completar la migracion de storage.
- Cuentas aun no esta migrado; la integracion completa de patrimonio y
  conciliacion depende de esa etapa.

### Tests agregados

- `tests/test_v2_budget_service.py`

## Etapa 7 - Cierre real de Cuentas

### Modulos funcionales

- `services/account_service.py`: CRUD completo, validaciones, activacion,
  desactivacion y proteccion de integridad.
- `ui_pyside6/pages/accounts_page.py`: tabla funcional con acciones Nueva
  cuenta, Editar, Eliminar, Activar, Desactivar y Actualizar.
- `ui_pyside6/pages/account_dialog.py`: formulario PySide6 para crear y editar
  cuentas.
- `avalancha/models.py`: tipos de cuenta V2 ampliados para cuenta vista e
  inversion.

### Integracion aplicada

`PySide6 -> AccountService -> BudgetRepository -> cuentas.json`

La UI no valida reglas financieras ni accede al storage directamente. Las
reglas viven en `AccountService`.

### Reglas implementadas

- Nombre obligatorio.
- Tipo obligatorio y existente.
- Saldo real numerico si se informa.
- Nombre de cuenta no duplicado.
- No eliminar cuentas con movimientos o recurrentes asociados.
- Activar y desactivar cuentas sin borrar datos.

### Aislamiento por perfil

El servicio opera sobre el `data_dir` recibido desde `MainWindow`, que proviene
del perfil activo. Las pruebas verifican que las cuentas personales no aparecen
en Demo y que regenerar Demo no modifica cuentas reales.

### Diagnostico Git

Existe `D:\Python\Programas\Avalancha_V2\.git`, pero no es un repositorio Git
valido porque no contiene `HEAD`, `config` ni `objects`. No se inicializo ni se
reparo sin autorizacion explicita.

### Porcentaje aproximado migrado

- Cuentas: 100% del CRUD definido.
- Proyecto V2 completo: 55% aproximado.

### Tests agregados

- `tests/test_v2_account_service.py`

## Etapa 9 - Migracion de Conciliacion

### Modulos funcionales

- `core/models/conciliacion.py`: contrato de conciliacion con saldo real,
  saldo registrado, diferencia, fecha, estado y observaciones.
- `services/account_service.py`: adaptador minimo para leer y persistir
  cuentas desde el storage actual.
- `services/reconciliation_service.py`: CRUD completo, validaciones, calculo
  de saldo registrado, diferencia y estados de conciliacion.
- `ui_pyside6/pages/reconciliation_page.py`: tabla funcional con acciones
  Nueva conciliacion, Editar, Eliminar, Marcar revisada y Actualizar.
- `ui_pyside6/pages/reconciliation_dialog.py`: formulario PySide6 para crear
  y editar conciliaciones.

### Integracion aplicada

`PySide6 -> ReconciliationService -> AccountService / MovementService ->
BudgetRepository -> JSON`

Conciliacion calcula el saldo registrado con movimientos reales asociados a
cada cuenta. El saldo real lo ingresa el usuario y la diferencia se calcula en
el servicio.

### Dependencias eliminadas

- La pantalla Conciliacion V2 no usa Tkinter.
- `ReconciliationService` no importa PySide6 ni Tkinter.
- Las validaciones viven en `services/reconciliation_service.py`.

### Estado del modulo Cuentas

Se agrego un `AccountService` minimo para sostener la integracion. El CRUD
visual completo de Cuentas sigue pendiente como modulo PySide6.

### Porcentaje aproximado migrado

- Conciliacion: 100% del alcance definido.
- Proyecto V2 completo: 38% aproximado.

### Riesgos pendientes

- La persistencia sigue usando `BudgetRepository` heredado como adaptador
  temporal.
- El historial de conciliaciones por cuenta aun no esta separado en una
  coleccion propia.
- Cuentas necesita UI PySide6 funcional para que el usuario gestione cuentas
  sin depender de datos heredados.

### Tests agregados

- `tests/test_v2_reconciliation_service.py`

## Etapa 10 - Migracion de Reportes

### Modulos funcionales

- `services/report_service.py`: generacion de reporte mensual, render TXT en
  memoria, guardado cifrado, apertura, listado y eliminacion.
- `ui_pyside6/pages/reports_page.py`: pantalla funcional con selector mes/anio,
  tabla de reportes, acciones abrir, eliminar y actualizar.
- `ui_pyside6/pages/report_viewer_dialog.py`: visor interno de reporte
  descifrado.
- `services/financial_summary_service.py`: metodo de indicadores mensuales
  completos para reportes.

### Integracion aplicada

`PySide6 -> ReportService -> FinancialSummaryService / BudgetService /
ReconciliationService / AccountService / MovementService -> BudgetRepository`

Reportes coordina servicios existentes y no duplica movimientos, presupuestos
ni cuentas. El archivo financiero plano no se escribe a disco.

### Seguridad aplicada

- Archivos `.avr` cifrados con Fernet.
- Indice `.avridx` cifrado.
- Clave local administrada por `ProveedorClaveLocal`.
- Apertura solo desde Avalancha V2 mediante descifrado interno.
- Rechazo de archivos no indexados o no cifrados como reportes.

### Dependencias eliminadas

- La pantalla Reportes V2 no usa Tkinter.
- `ReportService` no importa PySide6 ni Tkinter.
- La UI no accede directamente a storage.

### Porcentaje aproximado migrado

- Reportes: 100% del alcance definido.
- Proyecto V2 completo: 45% aproximado.

### Riesgos pendientes

- `GestorReportes` sigue ubicado en el paquete heredado `avalancha`, aunque
  queda encapsulado por `ReportService`.
- El formato sigue siendo TXT estructurado; PDF y Word quedan fuera del
  alcance de esta etapa.
- Falta Perfil Demo V2 como proxima etapa para mostrar reportes sin datos
  personales.

### Tests agregados

- `tests/test_v2_report_service.py`

## Etapa 11 - Perfil Demo completo

### Modulos funcionales

- `services/profile_service.py`: registro local, perfil activo, creacion de
  perfiles y rutas separadas.
- `services/demo_profile_service.py`: generacion de datos ficticios y reporte
  demo cifrado.
- `ui_pyside6/pages/profiles_page.py`: pantalla para abrir demo, regenerar
  demo, volver a Personal y crear perfiles.
- `ui_pyside6/pages/profile_dialog.py`: formulario de perfil nuevo.
- `ui_pyside6/main_window.py`: barra superior con perfil activo real y
  reconstruccion de paginas al cambiar perfil.
- `ui_pyside6/pages/dashboard_page.py`: dashboard basico del perfil activo.
- `ui_pyside6/pages/accounts_page.py`: vista basica de cuentas del perfil
  activo.

### Integracion aplicada

`MainWindow -> ProfileService -> servicios V2 con rutas del perfil activo`

Los servicios de Movimientos, Cuentas, Presupuestos, Conciliacion y Reportes
son creados con `data_dir`, `reports_dir` y `key_path` del perfil activo. Esto
evita mezclar datos personales con datos demo.

### Separacion de datos

- Personal: `data/perfiles/personal/`
- Demo: `data/perfiles/demo_avalancha/`

Cada perfil tiene sus propias carpetas `data`, `reportes` y `config`.

### Privacidad aplicada

El demo se genera con fixtures de codigo y marcadores "Demo Avalancha". Las
pruebas verifican que no copie movimientos personales ni escriba reportes demo
en la carpeta del perfil personal.

### Porcentaje aproximado migrado

- Perfil Demo: 100% del alcance definido.
- Proyecto V2 completo: 52% aproximado.

### Riesgos pendientes

- Dashboard y Cuentas aun son vistas basicas; el CRUD completo de Cuentas
  queda como deuda tecnica de integracion.
- La administracion avanzada de perfiles queda para Configuracion.
- Los modulos futuros deben mantener inyeccion de rutas desde `ProfileService`.

### Tests agregados

- `tests/test_v2_profile_demo.py`

## Etapa 12 - Configuracion

### Modulos funcionales

- `core/models/configuracion.py`: contrato puro de configuracion.
- `services/settings_service.py`: carga, validacion y persistencia por perfil.
- `ui_pyside6/pages/settings_page.py`: pantalla PySide6 funcional.
- `ui_pyside6/main_window.py`: inyecta `SettingsService` y usa la carpeta de
  reportes configurada al crear `ReportService`.

### Flujo de arquitectura

`PySide6 -> SettingsService -> ConfiguracionAplicacion -> config/settings.json`

La UI no lee ni escribe JSON directamente. Tampoco accede a
`BudgetRepository` ni a storage heredado.

### Configuracion por perfil

Cada perfil guarda sus preferencias en su propia carpeta `config`:

- Personal: `data/perfiles/personal/config/settings.json`
- Demo: `data/perfiles/demo_avalancha/config/settings.json`

Esto mantiene separadas rutas de reportes, respaldo, moneda y preferencias
futuras.

### Reglas implementadas

- Moneda principal permitida: CLP, USD o EUR.
- Apariencia preparada: claro, oscuro o sistema.
- Carpeta de reportes obligatoria y no puede apuntar a un archivo.
- Carpeta de respaldo obligatoria y no puede apuntar a un archivo.
- Las carpetas configuradas se crean al guardar.
- Sincronizacion queda solo como bandera futura.

### Porcentaje aproximado migrado

- Configuracion: 100% del alcance definido para V1 funcional.
- Proyecto V2 completo: 56% aproximado.

### Riesgos pendientes

- Modo oscuro aun no aplica una hoja de estilos alternativa.
- La accion manual de backup queda para una etapa posterior.
- La sincronizacion futura aun no tiene implementacion tecnica.

### Tests agregados

- `tests/test_v2_settings_service.py`
- `tests/test_v2_architecture.py` actualizado para importar `SettingsService`
  sin cargar frameworks de UI.

## Etapa 13 - Deudas

### Motivo de seleccion

Deudas quedo como la siguiente prioridad porque ya era parte de los indicadores
financieros, reportes, Perfil Demo y pagos vinculados, pero no existia una
pantalla V2 ni un servicio CRUD propio para administrarla.

### Modulos funcionales

- `services/debt_service.py`: CRUD, validaciones, activacion, desactivacion y
  proteccion de integridad.
- `ui_pyside6/pages/debt_dialog.py`: formulario PySide6 para crear y editar
  deudas.
- `ui_pyside6/pages/debts_page.py`: tabla funcional con acciones Nueva deuda,
  Editar, Eliminar, Activar, Desactivar y Actualizar.
- `ui_pyside6/main_window.py`: nueva entrada visible "Deudas".

### Flujo de arquitectura

`PySide6 -> DebtService -> BudgetRepository -> deudas.json`

La UI no accede directamente a JSON ni almacenamiento. Las reglas de negocio
viven en `DebtService`.

### Reglas implementadas

- Nombre obligatorio.
- Categoría válida.
- Saldos y pagos numericos.
- Pago mensual mayor que cero.
- Interés mensual no negativo.
- Nombre no duplicado.
- Eliminacion bloqueada si la deuda esta asociada a movimientos o recurrentes.

### Integracion aplicada

- Usa `data_dir` del perfil activo.
- Compatible con `FinancialSummaryService`.
- Compatible con reportes y Perfil Demo.
- Las pruebas verifican aislamiento entre Personal y Demo Avalancha.

### Porcentaje aproximado migrado

- Deudas: 100% del CRUD definido para V2.
- Proyecto V2 completo: 62% aproximado.

## Etapa 14 - Visualización Financiera

### Subfase 14.0 - Sistema Visual Base

Se incorpora Avalancha Color System V1 para estandarizar colores semánticos,
paletas categóricas, escala Viridis y escala de riesgo. El objetivo es mejorar
la lectura visual de indicadores financieros y evitar colores arbitrarios.

El módulo central es `ui_pyside6/color_system.py`. No se creó
`ui_pyside6/theme/color_system.py` porque `ui_pyside6/theme.py` ya existe como
archivo y no se modificó esa estructura para evitar cambios destructivos.

### Módulos funcionales

- `services/financial_alert_service.py`: reglas determinísticas de alertas
  financieras.
- `services/dashboard_visual_service.py`: prepara tarjetas, series de barras,
  ejecución presupuestaria y alertas para el Dashboard.
- `ui_pyside6/color_system.py`: colores semánticos, paleta categórica,
  escala Viridis, escala de riesgo y helpers visuales.
- `ui_pyside6/pages/dashboard_page.py`: tablero visual con tarjetas,
  gráficos de barras y alertas.
- `services/debt_service.py`: estado visual de deuda para presentación.

### Flujo de arquitectura

`PySide6 -> DashboardVisualService -> FinancialMetrics / BudgetRepository`

La UI solo renderiza datos ya preparados. No accede directamente a JSON ni
almacenamiento.

Los servicios entregan estados y métricas; la UI traduce esos estados a colores
mediante `color_system.py`.

### Reglas implementadas

- Flujo libre positivo: saludable.
- Flujo libre negativo: crítico.
- Gastos mayores que ingresos: alerta crítica.
- Deuda mayor que ingreso mensual: advertencia.
- Presupuesto mayor a 90%: crítico.
- Presupuesto mayor a 100%: excedido.
- Gastos imprevistos sobre umbral: advertencia.

### Porcentaje aproximado migrado

- Visualización financiera V2: 65% de una primera versión ejecutiva.
- Proyecto V2 completo: 66% aproximado.

## Etapa 14.1 - Dashboard con gráficos y alertas

### Módulos ajustados

- `ui_pyside6/pages/dashboard_page.py`: incorpora gráfico vertical nativo para
  ingresos versus gastos y mantiene barras horizontales para gastos y
  presupuesto versus gasto.
- `services/dashboard_visual_service.py`: se mantiene como fuente de datos
  preparados del Dashboard.
- `services/financial_alert_service.py`: entrega alertas financieras visibles.
- `tests/test_v2_dashboard_visual_service.py`: valida datos de gráficos y
  aislamiento por `data_dir`.
- `tests/test_v2_financial_alert_service.py`: valida alerta de deuda alta.
- `tests/test_v2_architecture.py`: verifica que Dashboard no importe storage y
  use `color_system.py`.

### Ajuste final de Resumen

- `ui_pyside6/main_window.py`: muestra `Resumen` como primera opcion del menu.
- `ui_pyside6/pages/dashboard_page.py`: renderiza tarjetas superiores, gastos
  por categoria, ingresos/gastos/flujo libre, evolucion de flujo libre,
  gastos por clase y alertas.
- `services/dashboard_visual_service.py`: entrega evolucion historica y clases
  de gasto sin calcular reglas en la UI.
- `services/financial_alert_service.py`: agrega alerta de presupuesto sobre
  90% junto con alertas de imprevistos.

### Flujo de arquitectura

`PySide6 -> DashboardVisualService -> FinancialMetrics / BudgetRepository`

La UI renderiza gráficos y traduce estados a colores. Los servicios entregan
métricas, porcentajes, rankings y alertas.

### Decisión técnica

PyQtGraph no está instalado. La primera versión usa gráficos nativos PySide6
para evitar dependencias nuevas y mantener el tablero estable.

### Riesgos pendientes

- Movimientos aun no permite seleccionar deuda asociada desde el dialogo V2.
- Resumen queda como tablero consolidado inicial; aun no tiene interaccion
  avanzada en graficos.
- La persistencia definitiva sigue usando `BudgetRepository` heredado como
  adaptador temporal.

### Ajuste fijo versus variable

- `DashboardVisualService` separa categorias variables de pagos fijos usando
  `is_fixed` del reporte financiero, que ya considera categorias fijas y
  recurrentes activos. Como respaldo inicial tambien aplica una lista
  normalizada de categorias fijas frecuentes: arriendo, chatgpt, spotify,
  internet, servicios, fondo solidario, tarjeta de credito y dante.
- `Presupuesto variable` muestra solo gastos controlables con semaforo de uso.
- `Pagos fijos del mes` muestra obligaciones con estado de cumplimiento y
  totales esperado/pagado/pendiente.
- `FinancialAlertService` ignora categorias fijas en alertas de presupuesto
  excedido o sobre 90%, evitando falsos criticos por pagos cumplidos.
- Pendiente futuro: modulo de obligaciones mensuales con vencimientos y alertas
  de atraso.
- Pendiente futuro: transferencias internas separadas de ingresos/gastos,
  presupuesto, flujo libre y graficos.

## Roadmap inmediato posterior a 14.1

La Etapa 14.1 deja una clasificacion inicial fijo/variable en
`DashboardVisualService`, pero esa regla es transitoria. Antes de seguir con
transferencias internas, pago correcto de deudas y analisis temporal, Avalancha
necesita un modulo formal de categorias.

| Etapa | Nombre |
| ----: | ------ |
| 14.1 | Resumen Visual |
| 14.2 | Gestion de Categorias |
| 14.3 | Transferencias internas |
| 14.4 | Pago correcto de deudas/tarjetas |
| 14.5 | Trazabilidad de deuda |
| 14.6 | Analisis temporal de deudas |

### Etapa 14.2 - Gestion de Categorias

Estado: implementada para revision, pendiente de commit de cierre.

Diagnostico:

- Las categorias estaban guardadas como strings en `Transaction.category` y
  `CategoryBudget.name`.
- Los presupuestos reutilizaban `CategoryBudget` del repositorio heredado.
- `MovementService.obtener_categorias()` leia categorias desde el presupuesto
  mensual.
- `DashboardVisualService` separaba fijo/variable con `is_fixed`, recurrentes
  y fallback por nombres normalizados.
- `FinancialAlertService` solo recibia `is_fixed` dentro del reporte de
  categorias.

Decision tecnica:

- Se implementa catalogo formal por perfil con compatibilidad por nombre.
- No se agrega `categoria_id` a movimientos todavia para evitar migracion
  destructiva.
- `categorias.json` se guarda dentro del `data_dir` del perfil activo y queda
  fuera de Git por las reglas existentes de datos.

Archivos agregados:

- `core/models/categoria.py`
- `services/category_service.py`
- `ui_pyside6/pages/categories_page.py`
- `ui_pyside6/pages/category_dialog.py`
- `tests/test_v2_category_service.py`

Archivos integrados:

- `services/movement_service.py`
- `services/budget_service.py`
- `services/dashboard_visual_service.py`
- `services/financial_alert_service.py`
- `services/demo_profile_service.py`
- `ui_pyside6/main_window.py`
- `ui_pyside6/pages/movement_dialog.py`
- `ui_pyside6/pages/budget_dialog.py`
- `tests/test_v2_architecture.py`

Reglas implementadas:

- crear, editar, desactivar y reactivar categorias;
- validar nombre, tipo y clase;
- evitar duplicados activos compatibles por nombre y tipo;
- listar por tipo incluyendo categorias `ambos`;
- ocultar inactivas en formularios nuevos;
- permitir inactiva historica al editar datos antiguos;
- no borrar fisicamente categorias con asociaciones;
- sincronizar categorias base y categorias heredadas si falta catalogo formal;
- mantener Personal y Demo aislados mediante `data_dir` independiente.

## Etapa 14.3 - Transferencias internas

Estado: cerrada con commit `160c96e Etapa 14.3 Transferencias Internas`.

| Archivo | Proposito | Contiene logica financiera | Contiene UI | Destino | Prioridad | Observaciones |
| --- | --- | --- | --- | --- | --- | --- |
| `avalancha/models.py` | Modelo persistible heredado | Si | No | `legacy/core` | Alta | `Transaction` acepta `transferencia` y `destination_account_id`. |
| `core/models/movimiento.py` | Contrato V2 puro | Si | No | `core/` | Alta | `Movimiento` distingue ingreso, gasto y transferencia. |
| `services/movement_service.py` | CRUD de movimientos | Si | No | `services/` | Alta | Crea y valida transferencias con origen/destino. |
| `services/reconciliation_service.py` | Conciliacion por cuenta | Si | No | `services/` | Alta | Origen resta y destino suma en saldo registrado. |
| `services/account_service.py` | Administracion de cuentas | Si | No | `services/` | Media | Protege cuentas usadas como destino historico. |
| `services/report_service.py` | Reporte mensual | Si | No | `services/` | Media | Agrega seccion separada de transferencias internas. |
| `ui_pyside6/pages/movement_dialog.py` | Formulario de movimientos | No | Si | `ui_pyside6/` | Alta | Muestra origen/destino y oculta categoria para transferencias. |
| `ui_pyside6/pages/movement_page.py` | Tabla de movimientos | No | Si | `ui_pyside6/` | Alta | Presenta `origen → destino` y filtra por cuenta origen/destino. |
| `ui_pyside6/pages/accounts_page.py` | Tabla de cuentas | No | Si | `ui_pyside6/` | Media | Agrega `Ver movimientos` para solicitar historial por cuenta. |
| `ui_pyside6/main_window.py` | Navegacion principal | No | Si | `ui_pyside6/` | Media | Conecta Cuentas con Movimientos filtrado por cuenta. |
| `tests/test_v2_internal_transfers.py` | Cobertura de etapa 14.3 | No | No | `tests/` | Alta | Verifica totales, saldos, reportes y arquitectura. |

Decision tecnica:

- Se eligio movimiento unico de transferencia para evitar registros partidos.
- `cuenta_id` queda como cuenta origen para no romper datos antiguos.
- `cuenta_destino_id` queda como campo opcional nuevo.
- Las transferencias aparecen en el historial de ambas cuentas.
- No se implementa pago de deuda ni tarjeta en esta etapa.

## Etapa 14.4 - Pago correcto de deudas/tarjetas

Estado: implementada para revision, sin commit de cierre.

| Archivo | Proposito | Contiene logica financiera | Contiene UI | Destino | Prioridad | Observaciones |
| --- | --- | --- | --- | --- | --- | --- |
| `avalancha/models.py` | Modelo persistible heredado | Si | No | `legacy/core` | Alta | `Transaction` acepta `pago_deuda` sin categoria ni cuenta destino. |
| `core/models/movimiento.py` | Contrato V2 puro | Si | No | `core/` | Alta | `Movimiento` distingue pago de deuda de gasto y transferencia. |
| `services/movement_service.py` | Registro de movimientos | Si | No | `services/` | Alta | Crea, edita y elimina pagos ajustando saldo de deuda. |
| `services/debt_service.py` | Gestion de deudas | Si | No | `services/` | Alta | Expone operaciones para aplicar y revertir pagos de deuda. |
| `services/reconciliation_service.py` | Saldos registrados por cuenta | Si | No | `services/` | Alta | Pago de deuda descuenta la cuenta origen. |
| `services/report_service.py` | Reporte mensual | Si | No | `services/` | Media | Agrega seccion `PAGOS DE DEUDA`. |
| `ui_pyside6/pages/movement_dialog.py` | Formulario de movimientos | No | Si | `ui_pyside6/` | Alta | Muestra selector de deuda y oculta categoria/destino/imprevisto. |
| `ui_pyside6/pages/movement_page.py` | Tabla de movimientos | No | Si | `ui_pyside6/` | Alta | Muestra `Pago deuda: cuenta -> deuda`. |
| `tests/test_v2_debt_payments.py` | Cobertura de etapa 14.4 | No | No | `tests/` | Alta | Verifica validaciones, saldos, reportes, presupuesto y aislamiento. |

Decision tecnica:

- Se usa un movimiento unico `tipo = pago_deuda`.
- No se crea aun tabla separada de pagos formales.
- Los pagos nuevos reducen `Debt.current_balance` y quedan en movimientos para
  historial visible.
- No se transforman movimientos historicos con `tipo = gasto` y `debt_id`.

Riesgo documentado:

- La persistencia JSON no es una transaccion real. `MovementService` valida todo
  antes de guardar y aplica una reversa simple de deudas si falla el guardado
  del presupuesto, pero la trazabilidad completa queda para 14.5.
- El flujo libre sigue siendo operativo. La separacion con flujo de caja real
  queda pendiente.

## Roadmap futuro - Analisis temporal de deudas

### Diagnostico arquitectonico

El analisis temporal de deudas queda registrado como mejora futura, pero no se
implementa en esta etapa porque la trazabilidad actual no alcanza para graficos
confiables.

El sistema actual permite:

- listar deudas y calcular indicadores basicos desde `DebtService`;
- conocer saldo actual y saldo del mes anterior;
- vincular movimientos a una deuda mediante `debt_id`;
- asociar movimientos a cuenta financiera mediante `cuenta_id`;
- sumar pagos historicos aproximados con `BudgetRepository.debt_payment_totals()`.

El sistema actual no permite todavia:

- distinguir formalmente pago de deuda versus gasto comun;
- separar compra con tarjeta y pago posterior de tarjeta sin riesgo de doble
  conteo;
- registrar saldo anterior y saldo posterior por pago;
- reconstruir una serie historica mensual por deuda;
- distinguir capital, interes, ajuste y pago minimo;
- separar transferencias internas de ingresos/gastos.

### Cambios de modelo necesarios

Se recomienda crear mas adelante:

- `DebtPayment`: registro formal de pago con `deuda_id`, `cuenta_origen_id`,
  fecha, monto pagado, tipo de pago, saldo anterior, saldo posterior, interes
  estimado y nota.
- `DebtSnapshot`: punto historico de saldo con `deuda_id`, fecha, saldo y
  origen (`manual`, `pago`, `cierre_mensual`, `ajuste`).
- `DebtAnalysisService`: servicio de consulta para evolucion de saldos, pagos
  por mes, tendencia por deuda y resumen de deuda total.

### Orden recomendado

1. `Etapa 14.2 - Gestion de Categorias`.
2. `Etapa 14.3 - Transferencias internas`.
3. `Etapa 14.4 - Pago correcto de deudas/tarjetas`.
4. `Etapa 14.5 - Trazabilidad de deuda`.
5. `Etapa 14.6 - Analisis temporal de deudas`.

El Dashboard solo deberia consumir una sintesis: deuda total, variacion mensual
y tendencia. El detalle con curvas y pagos debe vivir dentro del modulo Deudas.

### Tests agregados

- `tests/test_v2_debt_service.py`
- `tests/test_v2_architecture.py` actualizado para importar `DebtService`
  sin cargar frameworks de UI.
