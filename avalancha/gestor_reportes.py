"""Almacenamiento cifrado e íntegro de reportes oficiales de Avalancha."""

from __future__ import annotations

import hashlib
import json
import os
import sys
from ctypes import (
    POINTER,
    Structure,
    byref,
    c_byte,
    cast,
    create_string_buffer,
    string_at,
    windll,
)
from ctypes.wintypes import DWORD
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from cryptography.fernet import Fernet, InvalidToken

from avalancha.reporte_mensual import ReporteEstructurado


PREFIJO_DPAPI = b"AVALANCHA-DPAPI-1\n"


class _DataBlob(Structure):
    """Representa un bloque de bytes usado por la API de Windows."""

    _fields_ = [
        ("cbData", DWORD),
        ("pbData", POINTER(c_byte)),
    ]


class ReporteInconsistenteError(ValueError):
    """Indica que un reporte fue modificado o no puede descifrarse."""


class ReporteDuplicadoError(ValueError):
    """Indica que el mes ya posee un reporte oficial."""


class ProveedorClaveLocal:
    """Administra una clave local con un origen reemplazable."""

    def __init__(
        self,
        ruta_clave: str | Path = "config/reporte.key",
    ) -> None:
        """Inicializa el proveedor sin incorporar claves al código fuente."""
        self.ruta_clave = Path(ruta_clave)

    def obtener_clave(self) -> bytes:
        """Carga la clave existente o crea una nueva con acceso restringido."""
        if self.ruta_clave.exists():
            almacenada = self.ruta_clave.read_bytes()
            clave = self._descifrar_clave_local(almacenada)
            self._validar_clave(clave)
            if (
                sys.platform.startswith("win")
                and not almacenada.startswith(PREFIJO_DPAPI)
            ):
                self._guardar_clave(clave)
            return clave
        self.ruta_clave.parent.mkdir(parents=True, exist_ok=True)
        clave = Fernet.generate_key()
        self._guardar_clave(clave)
        return clave

    @staticmethod
    def _validar_clave(clave: bytes) -> None:
        """Verifica que la clave pueda inicializar un cifrador Fernet."""
        try:
            Fernet(clave)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                "La clave local de reportes no es válida."
            ) from exc

    def _restringir_permisos(self) -> None:
        """Restringe la lectura de la clave cuando el sistema lo permite."""
        try:
            os.chmod(self.ruta_clave, 0o600)
        except OSError:
            return

    def _guardar_clave(self, clave: bytes) -> None:
        """Guarda la clave protegida por el usuario de Windows."""
        contenido = (
            PREFIJO_DPAPI + self._proteger_con_dpapi(clave)
            if sys.platform.startswith("win")
            else clave
        )
        self.ruta_clave.write_bytes(contenido)
        self._restringir_permisos()

    @staticmethod
    def _descifrar_clave_local(contenido: bytes) -> bytes:
        """Recupera una clave DPAPI o una clave heredada sin protección."""
        if contenido.startswith(PREFIJO_DPAPI):
            if not sys.platform.startswith("win"):
                raise ValueError(
                    "La clave de reportes requiere el usuario de Windows."
                )
            return ProveedorClaveLocal._desproteger_con_dpapi(
                contenido[len(PREFIJO_DPAPI):]
            )
        return contenido.strip()

    @staticmethod
    def _proteger_con_dpapi(contenido: bytes) -> bytes:
        """Protege bytes con las credenciales del usuario de Windows."""
        entrada, referencia = ProveedorClaveLocal._crear_blob(contenido)
        salida = _DataBlob()
        resultado = windll.crypt32.CryptProtectData(
            byref(entrada),
            "Avalancha",
            None,
            None,
            None,
            0,
            byref(salida),
        )
        del referencia
        if not resultado:
            raise OSError("Windows no pudo proteger la clave de reportes.")
        try:
            return string_at(salida.pbData, salida.cbData)
        finally:
            windll.kernel32.LocalFree(salida.pbData)

    @staticmethod
    def _desproteger_con_dpapi(contenido: bytes) -> bytes:
        """Descifra bytes protegidos para el usuario actual de Windows."""
        entrada, referencia = ProveedorClaveLocal._crear_blob(contenido)
        salida = _DataBlob()
        resultado = windll.crypt32.CryptUnprotectData(
            byref(entrada),
            None,
            None,
            None,
            None,
            0,
            byref(salida),
        )
        del referencia
        if not resultado:
            raise ValueError(
                "No se pudo recuperar la clave local de reportes."
            )
        try:
            return string_at(salida.pbData, salida.cbData)
        finally:
            windll.kernel32.LocalFree(salida.pbData)

    @staticmethod
    def _crear_blob(contenido: bytes) -> tuple[_DataBlob, object]:
        """Crea un bloque DPAPI y conserva vivo su búfer de memoria."""
        buffer = create_string_buffer(contenido)
        blob = _DataBlob(
            len(contenido),
            cast(buffer, POINTER(c_byte)),
        )
        return blob, buffer


class GestorReportes:
    """Genera, cifra, indexa y recupera reportes oficiales."""

    VERSION = 1

    def __init__(
        self,
        carpeta_reportes: str | Path = "reportes",
        proveedor_clave: ProveedorClaveLocal | None = None,
    ) -> None:
        """Inicializa el almacén cifrado y su proveedor de clave."""
        self.carpeta_reportes = Path(carpeta_reportes)
        self.carpeta_reportes.mkdir(parents=True, exist_ok=True)
        self.ruta_indice = self.carpeta_reportes / "index.avridx"
        self.proveedor_clave = proveedor_clave or ProveedorClaveLocal()
        self.cifrador = Fernet(self.proveedor_clave.obtener_clave())

    def generar_reporte(
        self,
        reporte: ReporteEstructurado,
        mes: str,
        fecha_creacion: datetime | None = None,
    ) -> dict[str, Any]:
        """Convierte un reporte estructurado en un documento oficial."""
        fecha = fecha_creacion or datetime.now()
        return {
            "version": self.VERSION,
            "id": uuid4().hex,
            "mes": mes,
            "fecha_creacion": fecha.isoformat(timespec="seconds"),
            "encabezado": list(reporte.encabezado),
            "secciones": [
                {
                    "titulo": seccion.titulo,
                    "lineas": list(seccion.lineas),
                }
                for seccion in reporte.secciones
            ],
        }

    def serializar_reporte(self, reporte: dict[str, Any]) -> bytes:
        """Serializa el objeto estructurado antes de cifrarlo."""
        return json.dumps(
            reporte,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")

    def cifrar_reporte(self, contenido: bytes) -> bytes:
        """Cifra bytes usando autenticación simétrica Fernet."""
        return self.cifrador.encrypt(contenido)

    def guardar_reporte(
        self,
        reporte: ReporteEstructurado,
        mes: str,
        fecha_creacion: datetime | None = None,
    ) -> dict[str, Any]:
        """Guarda un reporte cifrado y registra su hash en el índice."""
        indice = self._leer_indice()
        if any(item.get("mes") == mes for item in indice):
            raise ReporteDuplicadoError(
                "Este mes ya posee un reporte oficial."
            )
        documento = self.generar_reporte(
            reporte,
            mes,
            fecha_creacion,
        )
        contenido = self.serializar_reporte(documento)
        cifrado = self.cifrar_reporte(contenido)
        nombre = f"R{mes}.avr"
        ruta = self.carpeta_reportes / nombre
        if ruta.exists():
            raise ReporteDuplicadoError(
                "El archivo oficial de este mes ya existe."
            )
        ruta.write_bytes(cifrado)
        self._proteger_archivo(ruta)
        entrada = {
            "id": documento["id"],
            "nombre": nombre,
            "mes": mes,
            "fecha_creacion": documento["fecha_creacion"],
            "ruta": nombre,
            "hash": self._calcular_hash(cifrado),
        }
        indice.append(entrada)
        indice.sort(key=lambda item: str(item.get("mes", "")), reverse=True)
        self._guardar_indice(indice)
        return dict(entrada)

    def descifrar_reporte(self, contenido: bytes) -> dict[str, Any]:
        """Descifra y valida la estructura interna de un reporte."""
        try:
            plano = self.cifrador.decrypt(contenido)
            reporte = json.loads(plano.decode("utf-8"))
        except (InvalidToken, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ReporteInconsistenteError(
                "El reporte presenta inconsistencias y no puede abrirse."
            ) from exc
        if not isinstance(reporte, dict) or "secciones" not in reporte:
            raise ReporteInconsistenteError(
                "El reporte presenta inconsistencias y no puede abrirse."
            )
        return reporte

    def abrir_reporte(self, reporte_id: str) -> dict[str, Any]:
        """Verifica la integridad y devuelve el reporte descifrado."""
        entrada = self._buscar_entrada(reporte_id)
        ruta = self.carpeta_reportes / str(entrada["ruta"])
        try:
            contenido = ruta.read_bytes()
        except OSError as exc:
            raise ReporteInconsistenteError(
                "El reporte presenta inconsistencias y no puede abrirse."
            ) from exc
        if self._calcular_hash(contenido) != entrada.get("hash"):
            raise ReporteInconsistenteError(
                "El reporte presenta inconsistencias y no puede abrirse."
            )
        reporte = self.descifrar_reporte(contenido)
        if reporte.get("id") != reporte_id:
            raise ReporteInconsistenteError(
                "El reporte presenta inconsistencias y no puede abrirse."
            )
        return reporte

    def listar_reportes(self) -> list[dict[str, Any]]:
        """Lista reportes desde el índice y calcula su estado de integridad."""
        resultado = []
        for entrada in self._leer_indice():
            actual = dict(entrada)
            actual["estado"] = self._obtener_estado(entrada)
            resultado.append(actual)
        return resultado

    def eliminar_reporte(self, reporte_id: str) -> None:
        """Elimina un reporte y su entrada después de confirmación externa."""
        indice = self._leer_indice()
        entrada = next(
            (
                item
                for item in indice
                if item.get("id") == reporte_id
            ),
            None,
        )
        if entrada is None:
            raise ValueError("No se encontró el reporte seleccionado.")
        ruta = self.carpeta_reportes / str(entrada["ruta"])
        if ruta.exists():
            self._habilitar_eliminacion(ruta)
            ruta.unlink()
        restante = [
            item for item in indice if item.get("id") != reporte_id
        ]
        self._guardar_indice(restante)

    def _leer_indice(self) -> list[dict[str, Any]]:
        """Descifra el índice interno o devuelve una colección vacía."""
        if not self.ruta_indice.exists():
            return []
        try:
            cifrado = self.ruta_indice.read_bytes()
            plano = self.cifrador.decrypt(cifrado)
            datos = json.loads(plano.decode("utf-8"))
        except (
            OSError,
            InvalidToken,
            UnicodeDecodeError,
            json.JSONDecodeError,
        ) as exc:
            raise ReporteInconsistenteError(
                "El índice de reportes presenta inconsistencias."
            ) from exc
        reportes = datos.get("reportes", [])
        if not isinstance(reportes, list):
            raise ReporteInconsistenteError(
                "El índice de reportes presenta inconsistencias."
            )
        return [
            item for item in reportes if isinstance(item, dict)
        ]

    def _guardar_indice(self, reportes: list[dict[str, Any]]) -> None:
        """Serializa y cifra el índice antes de reemplazarlo."""
        contenido = json.dumps(
            {
                "version": self.VERSION,
                "reportes": reportes,
            },
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        temporal = self.ruta_indice.with_suffix(".tmp")
        temporal.write_bytes(self.cifrador.encrypt(contenido))
        temporal.replace(self.ruta_indice)

    def _buscar_entrada(self, reporte_id: str) -> dict[str, Any]:
        """Busca una entrada del índice mediante su identificador."""
        entrada = next(
            (
                item
                for item in self._leer_indice()
                if item.get("id") == reporte_id
            ),
            None,
        )
        if entrada is None:
            raise ValueError("No se encontró el reporte seleccionado.")
        return entrada

    def _obtener_estado(self, entrada: dict[str, Any]) -> str:
        """Devuelve el estado de integridad sin descifrar el reporte."""
        ruta = self.carpeta_reportes / str(entrada.get("ruta", ""))
        try:
            contenido = ruta.read_bytes()
        except OSError:
            return "Inconsistente"
        if self._calcular_hash(contenido) != entrada.get("hash"):
            return "Inconsistente"
        return "Íntegro"

    @staticmethod
    def _proteger_archivo(ruta: Path) -> None:
        """Marca el reporte como solo lectura cuando el sistema lo permite."""
        try:
            os.chmod(ruta, 0o400)
        except OSError:
            return

    @staticmethod
    def _habilitar_eliminacion(ruta: Path) -> None:
        """Habilita escritura antes de una eliminación autorizada."""
        try:
            os.chmod(ruta, 0o600)
        except OSError:
            return

    @staticmethod
    def _calcular_hash(contenido: bytes) -> str:
        """Calcula el hash SHA256 de los bytes cifrados."""
        return hashlib.sha256(contenido).hexdigest()
