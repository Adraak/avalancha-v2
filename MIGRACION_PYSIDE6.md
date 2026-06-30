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
- Interes mensual estimado.
- Amortizacion neta.
- Patrimonio neto.
- Activos liquidos.
- Pasivos totales.
- Gastos imprevistos.
- Principales gastos.
- Categorias sobrepasadas.
- Categorias sin presupuesto.
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
- Categoria existente para el tipo seleccionado.
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
- Categoria obligatoria.
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
- Deudas ficticias de tarjeta y credito de consumo.
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
- Ver saldo actual, saldo mes anterior, disminucion mensual, pago mensual e
  interes estimado.

### Validaciones migradas a services

- Nombre obligatorio.
- Categoria valida.
- Saldo actual y saldo mes anterior numericos y no negativos.
- Pago mensual mayor que cero.
- Pago minimo, cupo e interes no negativos.
- Nombre de deuda no duplicado.
- Bloqueo de eliminacion para deudas con movimientos o recurrentes asociados.

### Decisiones de arquitectura

- La UI no accede a JSON ni a `BudgetRepository`.
- Los calculos de disminucion e interes estimado viven en `DebtService`.
- La persistencia sigue usando `BudgetRepository` como adaptador temporal.
- La pagina recibe el servicio desde `MainWindow`, con rutas del perfil activo.

### Riesgos pendientes

- Movimientos todavia no expone en UI el campo `deuda_id` para registrar pagos
  asociados desde PySide6.
- El dashboard sigue siendo basico y debe consolidarse con los modulos ya
  migrados.
- El storage definitivo aun depende del paquete heredado `avalancha`.
