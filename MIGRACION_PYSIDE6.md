# Migración PySide6 - Avalancha V2

Fecha de inicio: 29-06-2026

## Objetivo

Crear `Avalancha_V2` como laboratorio independiente para migrar la interfaz
desde Tkinter hacia PySide6 sin modificar la versión actual de Avalancha.

## Razón de la migración

Tkinter permitió construir una V1 funcional, pero en Windows con escalado
HiDPI puede presentar limitaciones visuales. PySide6 entrega mejor control de
DPI, layout, estilos, widgets complejos y empaquetado de escritorio.

## Regla crítica

No modificar Avalancha original durante esta migración. La carpeta
`D:\Python\Programas\Presupuestos` queda como respaldo funcional.

## Estructura nueva

- `core/`: lógica financiera y modelos independientes de interfaz.
- `services/`: persistencia, reportes, perfiles, respaldo e integración.
- `ui_tkinter/`: copia preservada de la interfaz Tkinter actual.
- `ui_pyside6/`: nueva interfaz PySide6.
- `resources/`: recursos visuales y archivos estáticos.
- `data/`: datos locales de trabajo de V2.
- `reports/`: salidas o reportes de V2.
- `tests/`: pruebas automatizadas.

## Etapas planificadas

1. Clonar proyecto y validar ventana mínima PySide6.
2. Separar núcleo financiero desde `avalancha/` hacia `core/` y `services/`.
3. Crear layout principal PySide6 con navegación y perfil activo.
4. Migrar Resumen y gráficos.
5. Migrar Movimientos, Categorías y Recurrentes.
6. Migrar Cuentas, Deudas y Reportes.
7. Empaquetar con PyInstaller.
8. Retirar dependencia de Tkinter solo cuando V2 alcance paridad funcional.

## Etapa 3 - Separacion nucleo/interfaz

### Objetivo

Identificar los modulos heredados y crear una primera capa de modelos y
servicios que pueda importarse sin Tkinter ni PySide6.

### Avance realizado

- Se creo `MAPA_MIGRACION_V2.md` con clasificacion de archivos heredados.
- Se creo `core/models/` con contratos base para movimientos, cuentas,
  presupuestos, deudas, perfiles y resumen mensual.
- Se creo `services/` con servicios iniciales para resumen financiero,
  perfiles, reportes y conciliacion.
- Se agrego una prueba de arquitectura para importar el nucleo en un proceso
  limpio sin cargar frameworks de interfaz.

### Decisiones de arquitectura

- `core/` queda reservado para modelos y reglas financieras puras.
- `services/` queda reservado para orquestacion, reportes, perfiles,
  conciliacion, persistencia y operaciones de archivo.
- `ui_tkinter/` queda como referencia funcional preservada.
- `ui_pyside6/` seguira con placeholders hasta que el nucleo este estable.
- No se migraron pantallas reales en esta etapa.

### Archivos creados

- `MAPA_MIGRACION_V2.md`
- `core/__init__.py`
- `core/models/__init__.py`
- `core/models/movimiento.py`
- `core/models/cuenta.py`
- `core/models/presupuesto.py`
- `core/models/deuda.py`
- `core/models/perfil_financiero.py`
- `core/models/resumen_mensual.py`
- `services/__init__.py`
- `services/financial_summary_service.py`
- `services/profile_service.py`
- `services/report_service.py`
- `services/reconciliation_service.py`
- `tests/test_v2_architecture.py`

### Archivos pendientes de migrar

- `avalancha/models.py`
- `avalancha/finanzas.py`
- `avalancha/storage.py`
- `avalancha/historial_financiero.py`
- `avalancha/reporte_mensual.py`
- `avalancha/perfiles.py`
- `avalancha/validaciones.py`

## Etapa 4 - Extraccion controlada de logica real

### Objetivo

Extraer calculos financieros reales desde `avalancha/finanzas.py`,
`avalancha/models.py` y `avalancha/storage.py` hacia `core/` y `services/`,
manteniendo independencia completa de la interfaz grafica.

### Avance realizado

- Se creo `core/financial_metrics.py` con calculos puros de resumen mensual,
  deuda, patrimonio, gastos, categorias y resultado esperado.
- Se actualizo `services/financial_summary_service.py` para usar el nucleo
  financiero en vez de duplicar calculos.
- Se fortalecio `services/reconciliation_service.py` para conciliar cuentas
  V2 y objetos heredados.
- Se creo `services/budget_storage_service.py` como base de almacenamiento JSON
  independiente de la interfaz.
- Se agregaron alias de compatibilidad en modelos V2 para convivencia temporal
  con estructuras heredadas.
- Se creo `tests/test_v2_financial_equivalence.py` para comparar resultados
  entre logica heredada y nucleo V2.

### Funciones migradas

- Ingresos reales.
- Gastos reales.
- Flujo libre.
- Resultado esperado.
- Estado de categorias.
- Deuda actual.
- Variacion de deuda.
- Pago mensual de deuda.
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

- Proyector de deuda completo.
- Simulador de pagos.
- Ranking avanzado de deudas.
- Diagnostico financiero.
- Riesgo financiero.
- Repositorio mensual completo con herencia de meses.
- Adaptadores formales para datos heredados.

### Riesgos encontrados

- `avalancha/app.py` sigue siendo una mezcla de UI y reglas de presentacion.
- Durante la transicion conviven nombres heredados en ingles con modelos V2 en
  español; los alias deben eliminarse solo cuando la migracion sea completa.
- La persistencia real todavia usa `avalancha/storage.py`; el servicio V2 es
  base, no reemplazo total.

### Tests creados

- `tests/test_v2_financial_equivalence.py`
- `tests/test_v2_architecture.py`

## Etapa 6 - Migracion de Movimientos

### Objetivo

Migrar el modulo Movimientos a PySide6 con CRUD completo, usando la ruta de
arquitectura `PySide6 -> Services -> Core -> Storage`.

### Avance realizado

- Se creo `services/movement_service.py` con metodos:
  `obtener_movimientos`, `crear_movimiento`, `editar_movimiento`,
  `eliminar_movimiento` y `buscar_movimientos`.
- Se creo `ui_pyside6/pages/movement_page.py` como pantalla funcional con
  buscador, tabla ordenable, seleccion de filas, doble clic para editar y
  botones Nuevo, Editar, Eliminar y Actualizar.
- Se creo `ui_pyside6/pages/movement_dialog.py` como dialogo PySide6 para
  creacion y edicion.
- Se dejo `ui_pyside6/pages/movements_page.py` como modulo de compatibilidad
  para el chasis existente.
- Se amplio `core.models.Movimiento` para permitir descripcion vacia, de
  acuerdo con la definicion del modulo.
- Se agregaron pruebas de CRUD e integracion con storage.

### Validaciones migradas a services

- Monto mayor que cero.
- Fecha valida.
- Categoría existente para el tipo seleccionado.
- Cuenta financiera existente.
- Tipo permitido por el modelo `Movimiento`.

### Dependencias eliminadas de Tkinter

- La pantalla Movimientos V2 no importa ni usa Tkinter.
- El servicio de movimientos no importa PySide6 ni Tkinter.
- El acceso a JSON queda detras de `MovementService`.

### Modulos ya funcionales

- Movimientos: funcional para visualizar, crear, editar, eliminar y buscar.

### Porcentaje aproximado migrado

- Modulo Movimientos: 100% del CRUD basico requerido.
- Avalancha V2 total: 20% aproximado.

### Riesgos encontrados

- El almacenamiento sigue usando `BudgetRepository` heredado como adaptador
  temporal; no se duplican datos, pero la persistencia final aun debe moverse
  completamente a servicios V2.
- El dialogo cubre campos base. Campos avanzados heredados, como deuda
  asociada, recurrente e imprevisto, quedan pendientes para una etapa de
  ampliacion del modulo.

### Tests creados

- `tests/test_v2_movement_service.py`

## Etapa 8 - Migracion completa de Presupuestos

### Objetivo

Migrar Presupuestos a PySide6 usando la arquitectura
`PySide6 -> Services -> Core -> Storage`, integrado con movimientos reales.

### Avance realizado

- Se creo `services/budget_service.py`.
- Se reemplazo el placeholder `ui_pyside6/pages/budgets_page.py` por una
  pantalla funcional.
- Se creo `ui_pyside6/pages/budget_dialog.py`.
- Se amplio `core/models/presupuesto.py` con los campos requeridos para V2.
- Se extendio `avalancha.models.CategoryBudget` dentro de V2 para persistir
  metadatos de presupuesto sin crear una segunda base de datos.
- Se ajusto `services/movement_service.py` para considerar solo categorias
  activas al crear movimientos nuevos.

### Funcionalidades implementadas

- Ver presupuestos.
- Crear presupuesto.
- Editar presupuesto.
- Eliminar presupuesto.
- Activar presupuesto.
- Desactivar presupuesto.
- Ver monto presupuestado.
- Ver gasto asociado desde movimientos reales.
- Ver saldo disponible.
- Ver porcentaje utilizado.
- Ver estado visual verde, amarillo o rojo.

### Integracion con Movimientos y Cuentas

- El gasto se calcula desde `MovementService`.
- No se duplican movimientos.
- Los presupuestos se guardan en el JSON mensual usado por el storage actual.
- Cuentas aun no esta migrado como CRUD PySide6, pero los movimientos ya siguen
  usando cuentas por ID estable.

### Validaciones migradas a services

- Nombre obligatorio.
- Categoría obligatoria.
- Monto mensual mayor que cero.
- Moneda obligatoria.
- Fecha de termino no anterior a fecha de inicio.
- Duplicados activos por categoria y periodo.

### Dependencias eliminadas

- Presupuestos V2 no usa Tkinter.
- La UI no accede al storage directamente.
- `BudgetService` no depende de PySide6.

### Estado del modulo

Presupuestos queda funcional para CRUD y ejecucion mensual. El siguiente modulo
recomendado sigue siendo Conciliacion, despues de cerrar la administracion de
Cuentas si se decide respetar la integracion completa del ecosistema.

### Porcentaje aproximado migrado

- Presupuestos: 100% del alcance definido.
- Avalancha V2 total: 30% aproximado.

### Riesgos pendientes

- El storage definitivo aun no esta completamente desacoplado del paquete
  heredado `avalancha`.
- Cuentas sigue como placeholder, por lo que la experiencia de integracion
  completa presupuesto-movimiento-cuenta aun depende de datos existentes.
- La UI cubre presupuestos de gastos; presupuestos de ingresos quedan fuera del
  alcance de esta etapa.

### Pruebas agregadas

- `tests/test_v2_budget_service.py`

## Etapa 7 - Cierre real de Cuentas

### Objetivo

Cerrar la deuda pendiente del modulo Cuentas antes de continuar con Etapa 12,
dejandolo como CRUD completo en PySide6.

### Avance realizado

- Se reemplazo `services/account_service.py` por un servicio CRUD completo.
- Se creo `ui_pyside6/pages/account_dialog.py`.
- Se reemplazo `ui_pyside6/pages/accounts_page.py` por una pantalla CRUD.
- Se ampliaron tipos de cuenta soportados en `avalancha/models.py` dentro de
  V2.
- Se agrego `tests/test_v2_account_service.py`.

### Funcionalidades implementadas

- Crear cuenta.
- Editar cuenta.
- Eliminar cuenta sin movimientos asociados.
- Activar cuenta.
- Desactivar cuenta.
- Listar cuentas.
- Validar nombre, tipo, saldo real y duplicados.
- Bloquear eliminacion de cuentas con movimientos para no romper referencias.

### Integracion con perfiles

Cuentas usa `AccountService` inyectado desde `MainWindow`, por lo que opera
sobre el `data_dir` del perfil activo. Las pruebas verifican que Personal y
Demo no mezclan cuentas y que regenerar Demo no toca cuentas reales.

### Diagnostico Git

La carpeta `D:\Python\Programas\Avalancha_V2\.git` existe, pero esta incompleta:
no contiene `HEAD`, `config` ni `objects`. Por eso Git no reconoce el proyecto
como repositorio valido. No se inicializo Git porque requiere aprobacion
explicita.

### Pruebas agregadas

- `tests/test_v2_account_service.py`

### Riesgos pendientes

- La eliminacion fisica de cuentas usadas queda bloqueada; para esos casos se
  debe usar desactivacion.
- La conciliacion recalcula saldos desde movimientos, por lo que `saldo
  registrado` sigue siendo de lectura y controlado por servicios.

## Etapa 9 - Migracion completa de Conciliacion

### Objetivo

Migrar Conciliacion a PySide6 usando la arquitectura
`PySide6 -> ReconciliationService -> MovementService / AccountService ->
Core / Storage`.

### Avance realizado

- Se creo `core/models/conciliacion.py`.
- Se creo `services/account_service.py` como adaptador minimo de cuentas para
  integracion con conciliacion y movimientos.
- Se reemplazo `services/reconciliation_service.py` por un servicio funcional
  con CRUD, calculo de diferencia, estados y compatibilidad con metodos
  anteriores.
- Se creo `ui_pyside6/pages/reconciliation_dialog.py`.
- Se reemplazo el placeholder `ui_pyside6/pages/reconciliation_page.py` por
  una pantalla funcional.
- Se extendio `avalancha.models.CuentaFinanciera` dentro de V2 para persistir
  estado y observaciones de conciliacion sin duplicar archivos.

### Funcionalidades implementadas

- Ver conciliacion por cuenta.
- Ingresar saldo real.
- Calcular saldo registrado desde movimientos.
- Comparar saldo real contra saldo registrado.
- Calcular diferencia.
- Guardar fecha de conciliacion.
- Ver cuentas con diferencia.
- Marcar conciliacion como revisada.
- Crear, editar y eliminar datos de conciliacion.

### Integracion con Cuentas y Movimientos

- El saldo registrado se calcula desde `MovementService`.
- Las cuentas se leen y actualizan mediante `AccountService`.
- La interfaz no accede directamente al almacenamiento.
- No se crea una segunda fuente de datos para conciliacion.

### Validaciones migradas a services

- Cuenta obligatoria y existente.
- Saldo real numerico.
- Fecha valida.
- Estado valido.
- Duplicado por cuenta y fecha.

### Dependencias eliminadas

- Conciliacion V2 no usa Tkinter.
- `ReconciliationService` no depende de PySide6 ni Tkinter.
- El dialogo y la pagina PySide6 consumen solo servicios.

### Estado del modulo

Conciliacion queda funcional para el alcance V2 definido. El modulo Cuentas
todavia requiere su CRUD PySide6 completo, pero ya existe un `AccountService`
minimo para sostener la integracion requerida por conciliacion.

### Porcentaje aproximado migrado

- Conciliacion: 100% del alcance definido.
- Avalancha V2 total: 38% aproximado.

### Riesgos pendientes

- El storage definitivo sigue apoyado temporalmente en `BudgetRepository`
  heredado.
- Cuentas aun necesita UI PySide6 funcional para administrar cuentas desde V2.
- El historial de multiples conciliaciones por cuenta queda pendiente; esta
  etapa guarda el estado vigente de conciliacion en la cuenta.

### Pruebas agregadas

- `tests/test_v2_reconciliation_service.py`

## Etapa 10 - Migracion completa de Reportes

### Objetivo

Migrar Reportes a PySide6 usando la arquitectura
`PySide6 -> ReportService -> Services -> Core -> Storage`.

### Avance realizado

- Se reemplazo `services/report_service.py` por una fachada V2 funcional.
- Se reemplazo el placeholder `ui_pyside6/pages/reports_page.py`.
- Se creo `ui_pyside6/pages/report_viewer_dialog.py`.
- Se agrego `tests/test_v2_report_service.py`.
- Se ajusto `services/financial_summary_service.py` con un metodo reusable
  para indicadores mensuales completos.

### Funcionalidades implementadas

- Generar reporte mensual desde datos reales de V2.
- Visualizar reporte dentro de Avalancha V2.
- Guardar reporte cifrado.
- Abrir reporte cifrado desde la app.
- Listar reportes existentes.
- Eliminar reportes con confirmacion desde UI.
- Ver mes reportado, fecha de generacion, archivo y estado.

### Mecanismo de cifrado

Reportes reutiliza `GestorReportes` y `ProveedorClaveLocal`, con Fernet y
proteccion local de clave. Los archivos `.avr` y el indice `.avridx` quedan
cifrados; el texto financiero solo se descifra en memoria dentro de Avalancha
V2.

### Integracion aplicada

- `FinancialSummaryService`: indicadores financieros principales.
- `BudgetService`: ejecucion presupuestaria.
- `ReconciliationService`: conciliacion y diferencias por cuenta.
- `AccountService`: cuentas financieras.
- `MovementService`: movimientos reales del mes.
- `BudgetRepository`: storage temporal heredado como adaptador.

### Dependencias eliminadas

- Reportes V2 no usa Tkinter.
- La UI no genera calculos ni toca archivos directamente.
- `ReportService` no depende de PySide6.

### Estado del modulo

Reportes queda funcional para formato texto estructurado cifrado. No se
implementa PDF, Word ni exportacion externa en esta etapa.

### Porcentaje aproximado migrado

- Reportes: 100% del alcance definido.
- Avalancha V2 total: 45% aproximado.

### Riesgos pendientes

- La persistencia de reportes reutiliza el gestor heredado, aunque ya queda
  encapsulada detras de `ReportService`.
- El contenido ejecutivo puede enriquecerse cuando Dashboard, Cuentas y Perfil
  Demo esten completamente migrados.
- El borrado fisico de reportes existe en el servicio, pero la UI lo protege
  con confirmacion.

### Pruebas agregadas

- `tests/test_v2_report_service.py`

## Etapa 11 - Perfil Demo completo

### Objetivo

Crear un Perfil Demo Avalancha funcional, con datos ficticios y separado del
perfil personal, para mostrar la app sin exponer datos reales.

### Avance realizado

- Se reemplazo `services/profile_service.py` por un servicio persistente de
  perfiles locales.
- Se creo `services/demo_profile_service.py`.
- Se reemplazo `ui_pyside6/pages/profiles_page.py` por una pantalla funcional.
- Se creo `ui_pyside6/pages/profile_dialog.py`.
- Se conecto `ui_pyside6/main_window.py` al perfil activo real.
- Se agregaron vistas basicas funcionales de Dashboard y Cuentas para mostrar
  datos del perfil activo.

### Estructura de perfiles

- `data/perfiles/personal/data/`
- `data/perfiles/personal/reportes/`
- `data/perfiles/personal/config/`
- `data/perfiles/demo_avalancha/data/`
- `data/perfiles/demo_avalancha/reportes/`
- `data/perfiles/demo_avalancha/config/`

Cada perfil mantiene datos, reportes cifrados y configuracion separados.

### Datos demo creados

- Ingresos ficticios.
- Cuentas ficticias: cuenta corriente, ahorro, efectivo y tarjeta.
- Movimientos ficticios de arriendo, comida, transporte, salud, servicios,
  ocio, ahorro, mascota, deuda e imprevistos.
- Presupuestos por categoria.
- Deudas ficticias de tarjeta y crédito de consumo.
- Conciliaciones ficticias con una cuenta cuadrada y una con diferencia.
- Reporte demo cifrado.

### Servicios adaptados

- `ProfileService`: crea, lista y selecciona perfiles.
- `DemoProfileService`: genera y regenera datos demo.
- `MainWindow`: reconstruye servicios y paginas con rutas del perfil activo.
- `MovementService`, `AccountService`, `BudgetService`,
  `ReconciliationService` y `ReportService` se inyectan desde la ventana con
  las rutas del perfil activo.

### Pruebas agregadas

- `tests/test_v2_profile_demo.py`

### Riesgos pendientes

- Dashboard y Cuentas tienen vistas basicas, no el CRUD completo definitivo.
- El cambio de perfil reconstruye paginas, pero aun no existe una pantalla de
  configuracion avanzada de preferencias.
- La migracion completa de perfiles para todos los modulos futuros debe seguir
  usando `ProfileService` como fuente unica de rutas.

## Etapa 12 - Configuracion

### Objetivo

Implementar la primera version funcional de configuracion local para Avalancha
V2, manteniendo la arquitectura PySide6 -> Services -> Core -> Storage.

### Avance realizado

- Se creo el modelo puro `ConfiguracionAplicacion`.
- Se creo `SettingsService` para leer, validar y guardar configuracion.
- La configuracion se guarda por perfil en `config/settings.json`.
- La pantalla `SettingsPage` reemplaza el placeholder de Configuracion.
- `MainWindow` usa la carpeta de reportes configurada al crear
  `ReportService`.

### Opciones incluidas

- Carpeta de reportes.
- Moneda principal, con CLP como valor por defecto.
- Apariencia preparada para claro, oscuro o sistema.
- Cifrado de reportes como opcion persistida, sin romper el cifrado actual.
- Carpeta de respaldo local.
- Campo de sincronizacion preparado para una etapa futura.

### Archivos creados o modificados

- `core/models/configuracion.py`
- `services/settings_service.py`
- `ui_pyside6/pages/settings_page.py`
- `ui_pyside6/main_window.py`
- `tests/test_v2_settings_service.py`
- `tests/test_v2_architecture.py`

### Decisiones de arquitectura

- La configuracion es por perfil para evitar mezclar Personal y Demo.
- La UI no accede directo a storage ni valida reglas de negocio.
- Las carpetas configuradas se crean desde el servicio al guardar.
- El sistema de reportes sigue cifrado en esta etapa.

### Riesgos pendientes

- El modo oscuro queda preparado, pero aun no aplica un tema visual completo.
- La sincronizacion queda solo como bandera futura.
- El backup local queda con carpeta configurable, sin accion de respaldo manual.

## Etapa 13 - Deudas

### Motivo de seleccion

Tras revisar el estado posterior a Configuracion, Deudas era la brecha tecnica
mas relevante: reportes, resumen financiero y movimientos ya consumian
`deudas.json`, pero V2 no tenia un modulo propio para administrar esas deudas.

### Objetivo

Migrar la administracion de deudas a PySide6, manteniendo la arquitectura
PySide6 -> Services -> Core -> Storage y respetando perfiles activos.

### Avance realizado

- Se creo `services/debt_service.py` con CRUD completo.
- Se creo `ui_pyside6/pages/debt_dialog.py`.
- Se creo `ui_pyside6/pages/debts_page.py`.
- Se integro la seccion Deudas en `ui_pyside6/main_window.py`.
- Se exporto `DebtService` desde `services/__init__.py`.
- Se agrego `tests/test_v2_debt_service.py`.
- Se actualizo la prueba de arquitectura para importar `DebtService` sin UI.

### Funcionalidades implementadas

- Listar deudas del perfil activo.
- Crear deuda.
- Editar deuda.
- Eliminar deuda sin movimientos asociados.
- Activar deuda.
- Desactivar deuda.
- Ver saldo actual, saldo mes anterior, disminución mensual, pago mensual e
  interés estimado.

### Validaciones migradas a services

- Nombre obligatorio.
- Categoría válida.
- Saldo actual y saldo mes anterior numericos y no negativos.
- Pago mensual mayor que cero.
- Pago mínimo, cupo e interés no negativos.
- Nombre de deuda no duplicado.
- Bloqueo de eliminacion para deudas con movimientos o recurrentes asociados.

### Decisiones de arquitectura

- La UI no accede a JSON ni a `BudgetRepository`.
- Los cálculos de disminución e interés estimado viven en `DebtService`.
- La persistencia sigue usando `BudgetRepository` como adaptador temporal.
- La pagina recibe el servicio desde `MainWindow`, con rutas del perfil activo.

### Riesgos pendientes

- Movimientos todavia no expone en UI el campo `deuda_id` para registrar pagos
  asociados desde PySide6.
- El dashboard sigue siendo basico y debe consolidarse con los modulos ya
  migrados.
- El storage definitivo aun depende del paquete heredado `avalancha`.

## Etapa 14 - Visualización Financiera

### Objetivo

Convertir el Dashboard en un tablero financiero visual con tarjetas
semánticas, barras de comparación y alertas simples, manteniendo la
arquitectura `PySide6 -> Services -> Core -> Storage`.

### Subfase 14.0 - Sistema Visual Base

Se incorpora Avalancha Color System V1 para estandarizar colores semánticos,
paletas categóricas, escala Viridis y escala de riesgo. El objetivo es mejorar
la lectura visual de indicadores financieros y evitar colores arbitrarios.

El módulo quedó en `ui_pyside6/color_system.py` porque ya existe
`ui_pyside6/theme.py`; crear simultáneamente una carpeta `ui_pyside6/theme/`
obligaría a mover o borrar el archivo actual.

### Avance realizado

- Se creó `services/financial_alert_service.py`.
- Se creó `services/dashboard_visual_service.py`.
- Se creó `ui_pyside6/color_system.py`.
- Se reemplazó el Dashboard básico por tarjetas visuales, barras de gastos,
  comparación ingresos versus gastos, presupuesto versus gasto y alertas.
- Se agregó estado visual de deuda en `DebtService`.
- Se coloreó el estado de deudas desde datos entregados por el servicio.
- Se ajustó el semáforo de presupuestos al criterio 70/90/100.
- Se agregaron pruebas para Dashboard visual y alertas financieras.

### Decisiones de arquitectura

- Se usaron widgets nativos de PySide6 para gráficos de barras horizontales.
- No se agregó PyQtGraph ni Matplotlib para evitar dependencias nuevas en esta
  primera versión.
- La UI no accede a JSON ni a `BudgetRepository`.
- Las reglas de tarjetas, porcentajes, estados y alertas viven en Services.
- La traducción de estados y categorías a colores vive en `color_system.py`.

### Funcionalidades implementadas

- Tarjetas visuales: ingresos reales, gastos reales, flujo libre, deuda actual,
  patrimonio neto y gastos imprevistos.
- Gráfico de gastos por categoría.
- Gráfico ingresos versus gastos.
- Visualización de presupuesto versus gasto.
- Alertas por flujo negativo, gastos sobre ingresos, deuda alta, presupuesto
  excedido e imprevistos altos.

### Riesgos pendientes

- Los gráficos son barras nativas simples; si se requiere interacción avanzada,
  se evaluará PyQtGraph en una etapa posterior.
- El Dashboard todavía no muestra evolución histórica mensual.

## Etapa 14.1 - Dashboard con gráficos y alertas

### Objetivo

Consolidar el Dashboard como tablero visual de decisión, usando la base de
colores de la Etapa 14.0 y datos preparados desde Services.

### Avance realizado

- Se mantuvo `DashboardVisualService` como fuente de tarjetas, gastos por
  categoría, ingresos versus gastos, presupuesto versus gasto y alertas.
- Se agregó un gráfico vertical nativo de ingresos versus gastos.
- Se mantuvo el gráfico horizontal de gastos por categoría con colores por
  `get_category_color()`.
- Se dejó presupuesto versus gasto como barras de progreso por categoría usando
  `get_budget_usage_color()`.
- Se renombró el bloque visible a `Alertas financieras`.
- Se agregaron pruebas de deuda alta, aislamiento de perfiles temporales y
  ausencia de acceso directo a storage desde Dashboard.

### Decisión de librería gráfica

PyQtGraph no está instalado en el entorno actual. Para evitar una dependencia
nueva en esta primera versión, los gráficos se implementaron con widgets
nativos de PySide6. Si se requiere zoom, interacción avanzada o series
temporales más ricas, PyQtGraph puede evaluarse en una etapa posterior.

### Criterios cubiertos

- Gráfico visible de gastos por categoría.
- Gráfico visible ingresos versus gastos.
- Alertas financieras visibles.
- Presupuesto versus gasto en Dashboard.
- Tarjetas visuales con colores semánticos.
- UI sin acceso directo a JSON ni `BudgetRepository`.

### Ajuste final de Resumen

- El elemento visible `Dashboard` pasa a mostrarse como `Resumen` en el menu
  lateral.
- Se consolida el tablero con tarjetas superiores, grafico de gastos por
  categoria, grafico ingresos/gastos/flujo libre, evolucion de flujo libre,
  gastos por clase y alertas financieras.
- La evolucion usa historial disponible del perfil activo; si hay menos de dos
  meses, la interfaz muestra un mensaje sin fallar.
- La clase `Imprevisto` vuelve a ser visible en el resumen mediante tarjeta,
  grafico de gastos por clase y alertas deterministicas.
- Los graficos se mantienen nativos con PySide6/QPainter para no agregar
  dependencias pesadas en esta subfase.

### Ajuste fijo versus variable

- El bloque `Presupuesto vs gasto` se separa en `Presupuesto variable` y
  `Pagos fijos del mes`.
- La clasificacion inicial vive en `DashboardVisualService` y usa el reporte
  financiero existente: una categoria es fija si viene marcada con `is_fixed`
  o si el motor financiero la detecta por recurrentes activos. Como respaldo
  inicial, tambien reconoce nombres normalizados como `arriendo`, `chatgpt`,
  `spotify`, `internet`, `servicios`, `fondo solidario`,
  `tarjeta de credito` y `dante`.
- Las categorias variables mantienen estados `Bajo control`, `Atención`,
  `Crítico` y `Excedido`.
- Los pagos fijos usan estados de cumplimiento: `Pagado`, `Parcial` y
  `Pendiente`; pagar el 100% de una obligacion fija no genera alerta critica.
- Queda pendiente una etapa futura de obligaciones mensuales con vencimientos,
  cuenta sugerida, recurrencia configurable y alertas por atraso.
- Transferencias internas sigue pendiente. Cuando se implemente debera
  excluirse de ingresos, gastos, presupuesto, flujo libre y graficos para no
  contaminar metricas.

## Roadmap inmediato posterior a 14.1

Antes de avanzar hacia transferencias, pago de tarjetas o analisis temporal de
deudas, se detecto una pieza base pendiente: el usuario necesita administrar
categorias desde Avalancha V2. Por eso el orden inmediato queda:

| Etapa | Nombre |
| ----: | ------ |
| 14.1 | Resumen Visual |
| 14.2 | Gestion de Categorias |
| 14.3 | Transferencias internas |
| 14.4 | Pago correcto de deudas/tarjetas |
| 14.5 | Trazabilidad de deuda |
| 14.6 | Analisis temporal de deudas |

### Etapa 14.2 - Gestion de Categorias

Estado: implementada para revision, sin commit de cierre.

La etapa agrega administracion formal de categorias por perfil. La decision
tecnica fue mantener compatibilidad por nombre: movimientos y presupuestos
siguen guardando `categoria` como texto visible, mientras `CategoryService`
mantiene un catalogo formal en `categorias.json` dentro del `data_dir` del
perfil activo.

Modelo implementado:

- `id`
- `nombre`
- `tipo`: `ingreso`, `gasto`, `ambos`
- `clase`: `fija`, `variable`
- `activa`
- `color_key`
- `created_at`
- `updated_at`

Archivos principales:

- `core/models/categoria.py`
- `services/category_service.py`
- `ui_pyside6/pages/categories_page.py`
- `ui_pyside6/pages/category_dialog.py`
- `tests/test_v2_category_service.py`

Integraciones:

- `MovementService` valida categorias contra `CategoryService` y solo ofrece
  categorias activas compatibles con el tipo de movimiento. Al editar un
  movimiento antiguo permite conservar una categoria inactiva existente.
- `BudgetService` usa categorias activas de gasto o ambos y rechaza categorias
  solo ingreso. Al persistir presupuestos mantiene `is_fixed` sincronizado con
  la clase formal para compatibilidad con el motor heredado.
- `DashboardVisualService` aplica la clase formal antes del fallback por
  `is_fixed`, recurrentes o nombres normalizados.
- `FinancialAlertService` ignora categorias fijas formales al evaluar alertas
  de presupuesto variable.
- `DemoProfileService` sincroniza categorias demo ficticias despues de generar
  presupuestos, cuentas y deudas.
- `MainWindow` agrega la pagina `Categorias` al menu lateral.

Regla de historial:

- No se implementa borrado fisico destructivo en UI. La accion de eliminar
  desactiva la categoria, especialmente si tiene movimientos, presupuestos o
  recurrentes asociados.

Compatibilidad:

- Si no existe `categorias.json`, `CategoryService` crea categorias base y
  sincroniza nombres encontrados en presupuestos, movimientos y recurrentes
  existentes.
- Si una categoria formal no existe, Resumen Visual mantiene el fallback de la
  Etapa 14.1 para no romper datos antiguos.

### Etapa 14.3 - Transferencias internas

Estado: implementada para revision, sin commit de cierre.

Decision tecnica:

- Se usa un movimiento unico con `tipo = transferencia`.
- `cuenta_id` representa la cuenta origen por compatibilidad.
- `destination_account_id` / `cuenta_destino_id` representa la cuenta destino.
- La transferencia no usa categoria, no puede ser imprevisto y no se trata como
  recurrente.

Reglas implementadas:

- `MovementService` crea y edita transferencias internas validando monto,
  cuenta origen, cuenta destino, cuentas existentes y origen distinto de
  destino.
- `ReconciliationService` descuenta el monto de la cuenta origen y lo suma a la
  cuenta destino al calcular saldo registrado.
- `AccountService` protege eliminacion de cuentas usadas como origen o destino
  en transferencias historicas.
- `DashboardVisualService`, `FinancialMetrics`, `BudgetService` y
  `FinancialAlertService` mantienen las transferencias fuera de ingresos,
  gastos, flujo libre, presupuesto, imprevistos y alertas financieras.
- `ReportService` muestra las transferencias en una seccion separada:
  `TRANSFERENCIAS INTERNAS`.
- La UI de Movimientos permite seleccionar `Transferencia interna`, muestra
  cuenta origen y cuenta destino, y oculta categoria e imprevisto.
- La tabla de Movimientos muestra transferencias como `origen → destino` en la
  columna Cuenta.
- La pagina Cuentas permite abrir Movimientos filtrado por la cuenta
  seleccionada. El historial incluye movimientos normales y transferencias
  donde la cuenta sea origen o destino.

Compatibilidad:

- Los movimientos antiguos `ingreso` y `gasto` siguen usando `cuenta_id` y
  `categoria` sin migracion destructiva.
- Las transferencias nuevas conviven con el almacenamiento JSON existente.
- Personal y Demo siguen aislados mediante el `data_dir` del perfil activo.

Limitacion explicita:

- Pago de deuda o tarjeta queda resuelto en la etapa siguiente mediante
  `tipo = pago_deuda`, sin contar el pago como gasto nuevo.

## Etapa 14.4 - Pago correcto de deudas/tarjetas

Estado: implementada para revision, sin commit de cierre.

Decision tecnica:

- Se agrega movimiento unico `tipo = pago_deuda`.
- `cuenta_id` representa la cuenta origen desde donde sale el dinero.
- `deuda_id` representa la deuda o tarjeta pagada.
- El pago no requiere categoria, no puede ser imprevisto y no puede ser
  recurrente.
- El pago reduce el saldo actual de la deuda y baja el saldo registrado de la
  cuenta origen en conciliacion.
- El pago no aumenta gastos reales, no consume presupuesto, no aparece en
  gastos por categoria, no aparece en gastos por clase y no afecta
  imprevistos.
- Reportes muestra los pagos en la seccion separada `PAGOS DE DEUDA`.

Diferencia conceptual:

- Compra con tarjeta: es gasto real y debe afectar categoria, presupuesto y
  reporte de gastos.
- Pago de tarjeta o deuda: es salida de caja para reducir pasivo; no es gasto
  nuevo y no debe duplicar el gasto original.

Compatibilidad:

- Los movimientos antiguos `ingreso`, `gasto` y `transferencia` siguen siendo
  legibles.
- Los gastos antiguos con `debt_id` no se convierten automaticamente en
  `pago_deuda`.
- `BudgetRepository.debt_payment_totals()` se mantiene para compatibilidad con
  gastos historicos vinculados a deuda; los pagos nuevos reducen directamente
  el saldo de deuda.

Trazabilidad posterior:

- `Etapa 14.5 - Trazabilidad de deuda` agrega registros formales de pagos con
  saldo anterior, saldo posterior y snapshots de auditoria.
- El Dashboard aun usa flujo operativo (`ingresos - gastos`). Queda pendiente
  separar flujo operativo de flujo de caja real, donde los pagos de deuda
  saldrian explicitamente como compromisos financieros.

## Etapa 14.5 - Trazabilidad de deuda

Estado: implementada para revision, sin commit de cierre.

Objetivo:

Crear una bitacora formal para pagos de deuda sin cambiar la regla de 14.4: el
pago reduce pasivo y caja, pero no aumenta gastos ni consume presupuesto.

Implementado:

- `DebtPayment` en `avalancha/models.py`, vinculado al movimiento
  `pago_deuda`.
- `DebtSnapshot` en `avalancha/models.py`, con saldo anterior, saldo posterior
  y origen del evento.
- Persistencia en `debt_payments.json` y `debt_snapshots.json`.
- `MovementService` crea traza formal al registrar pagos de deuda.
- Editar un pago revierte la traza anterior y crea una nueva.
- Eliminar un pago remueve el pago activo, revierte saldo y conserva snapshot
  de reversa.
- `DebtService` consulta pagos y snapshots filtrados por deuda.
- `tests/test_v2_debt_traceability.py` cubre creacion, edicion, eliminacion y
  filtros.

Fuera de alcance:

- Graficos temporales de deuda.
- Separacion de capital versus interes real.
- Snapshots de cierre mensual por deuda.
- Servicio dedicado de analisis temporal.

## Roadmap futuro - Analisis temporal de deudas

### Diagnostico de factibilidad

El modelo actual ya registra pagos formales y snapshots por evento de pago, pero
todavia no debe usarse directamente para graficar curvas historicas de deuda por
deuda. Falta un servicio que consolide cierres mensuales, pagos y ajustes con
reglas explicitas de consulta.

`BudgetRepository.debt_payment_totals()` suma movimientos de gasto vinculados a
deudas. Esa informacion sirve como aproximacion de pagos acumulados, pero no
permite reconstruir con certeza:

- interes versus capital;
- pagos por fecha con trazabilidad completa;
- historial mensual confiable para graficos de linea.

### Datos actuales que sirven

- `DebtService` administra deudas activas e inactivas.
- `Debt` contiene saldo actual, saldo mes anterior, pago mensual, pago minimo,
  interes mensual, cupo y estado activo.
- `Movimiento` ya tiene `deuda_id` y `cuenta_id`.
- `MovementService` persiste movimientos asociados a cuenta financiera.
- `AccountService` permite identificar la cuenta origen.

### Datos faltantes

Antes de implementar graficos temporales se requiere modelar:

- consulta temporal sobre `debt_payments` y `debt_snapshots`.
- snapshots de cierre mensual por deuda.
- regla explicita para pago de tarjeta: compra con tarjeta es gasto; pago de
  tarjeta es reduccion de deuda, no gasto nuevo.

### Recomendacion tecnica

No implementar aun graficos temporales de deuda. Las etapas correctas previas
son:

- `Etapa 14.2 - Gestion de Categorias`.
- `Etapa 14.3 - Transferencias internas`.
- `Etapa 14.4 - Pago correcto de deudas/tarjetas` (implementada para revision).
- `Etapa 14.5 - Trazabilidad de deuda` (implementada para revision).

Esas etapas deben cerrar categorias administrables, transferencias internas,
registro formal de pagos, asociacion con cuenta origen, actualizacion de saldo,
snapshots y no duplicacion de gastos. Luego corresponde:

- `Etapa 14.6 - Analisis temporal de deudas`.

En esa etapa se podran agregar curvas de saldo por deuda, barras de pagos
mensuales, tendencias y resumen sintetico para el Dashboard.
