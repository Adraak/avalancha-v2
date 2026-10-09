"""Lectura y escritura de documentos JSON con versión de esquema."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from core.json_file_store import JsonFileStore
from core.schema_versioning import SchemaVersionError, SchemaVersionPolicy


class VersionedJsonStore:
    """Combina el almacén JSON atómico con la política de versionado.

    Valida la versión inmediatamente después de leer y antes de reemplazar
    un documento existente, y marca cada escritura con la versión actual.
    """

    def __init__(
        self,
        store: JsonFileStore | None = None,
        policy: SchemaVersionPolicy | None = None,
    ) -> None:
        """Inicializa el almacén y la política, reemplazables en pruebas."""
        self._store = store or JsonFileStore()
        self._policy = policy or SchemaVersionPolicy()

    def read(self, path: str | Path) -> Any:
        """Lee un documento y rechaza versiones futuras o inválidas."""
        target = Path(path)
        document = self._store.read(target)
        self._validate(target, document)
        return document

    def check_existing(self, path: str | Path) -> None:
        """Rechaza reemplazar un documento existente de versión incompatible.

        Debe llamarse antes de cualquier efecto previo a la escritura, como
        un respaldo o la creación de carpetas. Un archivo que no es JSON
        legible no declara versión y conserva el comportamiento actual.
        """
        target = Path(path)
        if not target.exists():
            return
        try:
            document = self._store.read(target)
        except (json.JSONDecodeError, UnicodeDecodeError):
            return
        self._validate(target, document)

    def write(self, path: str | Path, document: dict[str, Any]) -> Path:
        """Reemplaza de forma atómica el documento con la versión actual."""
        target = Path(path)
        prepared = self._policy.prepare_for_write(document)
        self.check_existing(target)
        return self._store.write(target, prepared)

    def _validate(self, target: Path, document: Any) -> None:
        """Valida la versión y anota el nombre del archivo en el error."""
        try:
            self._policy.validate(document)
        except SchemaVersionError as error:
            error.document_name = target.name
            raise
