# Instalador Windows de Avalancha

Este directorio contiene el contrato de distribución Windows de Avalancha.

## Frontera de 21B

El instalador consume exclusivamente el ejecutable frozen generado por 21A:

`dist/Avalancha.exe`

No instala el repositorio Python, dependencias de desarrollo, perfiles, claves,
reportes, respaldos ni otros datos financieros.

## Identidad del producto

La identidad de instalación es estable entre versiones:

`BE6AA14A-2F55-5EAD-8AF9-067C70318BF2`

No cambiar el `AppId` al aumentar la versión. La versión puede evolucionar; la
identidad del producto debe permanecer constante para que Windows reconozca las
actualizaciones como la misma aplicación.

## Versión técnica de 21B

Mientras la Etapa 22 no defina el contrato formal de versionado y migraciones,
21B reutiliza la versión técnica ya existente de la aplicación: `0.1.0`.

Esto no declara Avalancha Desktop 1.0.

## Rutas

Programa instalado:

`%LOCALAPPDATA%\Programs\Avalancha`

Datos persistentes del usuario en ejecución frozen:

`%LOCALAPPDATA%\Avalancha`

La segunda ruta pertenece al runtime de datos y queda fuera del alcance del
instalador y del desinstalador.

## Arquitectura

El ejecutable frozen de 21A fue verificado como PE x64/AMD64. El instalador se
compila por tanto con `SetupArchitecture=x64` y queda restringido por el
contrato de Inno Setup a Windows compatible con x64.

## Privilegios

La instalación es por usuario y no requiere privilegios administrativos.

## Build esperado

1. Construir primero `dist/Avalancha.exe` con el flujo PyInstaller aprobado.
2. Compilar `packaging/Avalancha.iss` con el compilador de Inno Setup aprobado
   por Forge.
3. Obtener `dist/Avalancha_Setup_0.1.0.exe`.

La aprobación de 21B exige además pruebas reales de instalación limpia,
arranque, desinstalación, reinstalación/actualización y conservación de datos.

## Invariantes

- El instalador no contiene datos financieros.
- El desinstalador no borra `%LOCALAPPDATA%\Avalancha`.
- El `AppId` permanece estable entre versiones.
- El instalador se actualiza sobre la misma identidad de producto.
- Una actualización no debe destruir perfiles, claves, reportes ni respaldos.
- Las migraciones de persistencia pertenecen a Etapa 22, no a 21B.
