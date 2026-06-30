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
