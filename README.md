# Avalancha

Aplicacion de escritorio en Python/Tkinter para seguimiento de presupuesto
mensual personal en CLP.

## Ejecutar

```powershell
python -m pip install -r requirements.txt
python main.py
```

## Probar el core

```powershell
python -m unittest discover -s tests
```

## Datos

Los meses se guardan en archivos JSON bajo `data/`:

```text
data/presupuesto_2026-06.json
data/presupuesto_2026-07.json
```

Las deudas globales se guardan en:

```text
data/deudas.json
```

Las cuentas usadas para conciliacion manual se guardan en:

```text
data/cuentas.json
```

Los cierres mensuales se guardan en:

```text
data/historial_mensual.json
```

Los reportes oficiales se guardan cifrados en:

```text
reportes/R2026-06.avr
reportes/index.avridx
```

La clave local se almacena fuera de la carpeta de reportes:

```text
config/reporte.key
```

Los reportes solo se descifran en memoria y se muestran desde la pestaña
`Reportes`. Avalancha no abre editores externos ni genera copias TXT.

Al iniciar la aplicacion se crea un respaldo ZIP completo en `backup/`. Se
mantienen los 20 respaldos mas recientes.

Antes de sobrescribir un JSON existente, la app crea un respaldo en
`data/backups/`.

La interfaz muestra y recibe fechas como `dd-mm-yyyy`; los JSON guardan las
fechas internamente como `yyyy-mm-dd` para facilitar ordenamiento y comparacion.

Al navegar hacia un mes que todavía no existe, Avalancha crea y guarda ese mes
automáticamente usando la configuración del último mes anterior. Se heredan:

- categorías y montos presupuestados;
- clasificación fija o variable;
- pagos recurrentes;
- cuentas, medios de pago y deudas asociados a los recurrentes.

Los movimientos reales no se copian. El nuevo mes comienza sin pagos
registrados, por lo que los compromisos recurrentes aparecen pendientes.

## Primera etapa incluida

- Ingresos y gastos reales.
- Categorias fijas y variables.
- Presupuesto mensual por categoria.
- Alertas por porcentaje de uso.
- Estados diferenciados: variables usan alerta porcentual; fijos o recurrentes
  usan `programado`, `pendiente`, `pagado`, `diferencia` o `sobrepasado`.
- El campo `Alerta %` solo aplica a categorias variables; se deshabilita para
  categorias fijas o recurrentes.
- Al guardar una categoria marcada como fija/recurrente con presupuesto mayor
  que cero, se crea una plantilla recurrente si no existia.
- El boton `Crear reales del mes` tambien crea plantillas faltantes para
  categorias de gasto fijas antes de crear movimientos reales.
- Movimientos editables con fecha, descripcion, monto y medio de pago.
- Movimientos marcables como `Imprevisto`.
- Tabla de movimientos con clase `Normal`, `Recurrente` o `Imprevisto`.
- Recurrentes mensuales que crean el movimiento real del mes activo.
- Selector de pago recurrente en movimientos, con monto sugerido.
- Lista reutilizable de medios/cuentas basada en valores predefinidos y pagos
  recurrentes guardados.
- Registro global de creditos, tarjetas y otras deudas en la pestana `Deudas`.
- Movimientos y recurrentes pueden vincularse a una deuda para disminuir su
  saldo actual.
- Indicadores de deuda: deuda total, deuda por categoria, variacion mensual,
  pago mensual, pago acumulado, flujo libre y patrimonio neto.
- Proyeccion simple de meses restantes y fecha de extincion por deuda, con
  simulador de pagos alternativos.
- Tabla comparativa de escenarios de pago para una deuda o todas las deudas,
  con opcion de considerar intereses y meses ganados respecto al pago actual.
- Conciliacion bancaria manual mediante saldo real, saldo registrado,
  diferencia por registrar, fecha y semaforo.
- El saldo registrado de cada cuenta se calcula automaticamente como saldo
  base interno mas ingresos asociados menos gastos asociados. El usuario solo
  ingresa el saldo real observado; Avalancha calcula la base al crear la cuenta.
- Indice de riesgo financiero de 0 a 100, con nivel, causa principal y accion
  recomendada.
- Ranking de prioridad de ataque de deudas segun interes, tipo, uso de cupo,
  saldo y capacidad de amortizacion.
- Reportes mensuales oficiales con cifrado Fernet, hash SHA256, índice
  cifrado y visor interno de solo lectura.
- Dashboard con resumen y grafico de gasto real versus presupuestado.
- Inteligencia mensual en Resumen:
  - diferencia pendiente de clasificar entre saldos reales y registrados;
  - resultado esperado de fin de mes con recurrentes pendientes;
  - cinco principales categorias de gasto;
  - dias de supervivencia segun saldos reales positivos;
  - semaforo financiero general con explicacion breve.
- Cierre mensual protegido contra duplicados.
- Evolucion historica de deuda, patrimonio y flujo libre.
- Tendencias mensuales y diagnostico financiero por nivel.
- Validaciones obligatorias para movimientos y deudas nuevas.
- Respaldo ZIP automatico al iniciar con retencion de 20 archivos.

## Preparado para etapas futuras

- Comparacion entre meses.
- Exportacion controlada a PDF o Word a partir del reporte estructurado.
- Cuentas separadas.
- Intereses, compras nuevas y cargos finos de tarjetas.
- Empaquetado como `.exe`.
