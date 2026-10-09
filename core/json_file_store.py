"""Almacén de documentos JSON con escritura atómica."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any


class JsonFileStore:
    """Lee y escribe documentos JSON sin conocer reglas de negocio.

    La escritura serializa a un temporal en la carpeta del destino y luego
    lo reemplaza con ``os.replace``: el destino queda con el contenido
    anterior o con el nuevo, nunca con una escritura a medias.
    """

    ENCODING = "utf-8"
    TEMP_SUFFIX = ".tmp"

    def read(self, path: str | Path) -> Any:
        """Devuelve la estructura JSON almacenada en la ruta indicada."""
        with Path(path).open("r", encoding=self.ENCODING) as file:
            return json.load(file)

    def write(self, path: str | Path, data: Any) -> Path:
        """Reemplaza de forma atómica el documento JSON de la ruta indicada."""
        target = Path(path)
        descriptor, temporary_name = tempfile.mkstemp(
            dir=target.parent,
            prefix=f".{target.name}.",
            suffix=self.TEMP_SUFFIX,
        )
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "w", encoding=self.ENCODING) as file:
                json.dump(
                    data,
                    file,
                    ensure_ascii=False,
                    indent=2,
                    sort_keys=True,
                )
                file.write("\n")
                file.flush()
                os.fsync(file.fileno())
            os.replace(temporary, target)
        except BaseException:
            self._discard(temporary)
            raise
        return target

    @staticmethod
    def _discard(temporary: Path) -> None:
        """Elimina el temporal sin ocultar el error que lo dejó huérfano."""
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            return
