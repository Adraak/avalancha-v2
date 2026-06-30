"""Servicio de almacenamiento JSON para presupuestos V2."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class BudgetStorageService:
    """Carga y guarda archivos JSON sin depender de la interfaz."""

    def __init__(self, data_dir: str | Path) -> None:
        """Inicializa la carpeta base de datos."""
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

    def budget_path(self, year: int, month: int) -> Path:
        """Devuelve la ruta del archivo mensual."""
        self._validar_mes(year, month)
        return self.data_dir / f"presupuesto_{year:04d}-{month:02d}.json"

    def load_json(self, path: Path) -> dict[str, Any]:
        """Carga un archivo JSON y devuelve un diccionario."""
        if not path.exists():
            return {}
        with path.open("r", encoding="utf-8") as file:
            return json.load(file)

    def save_json(self, path: Path, data: dict[str, Any]) -> Path:
        """Guarda datos JSON con formato estable."""
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as file:
            json.dump(
                data,
                file,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            file.write("\n")
        return path

    def list_months(self) -> list[str]:
        """Lista meses disponibles en la carpeta de datos."""
        meses = []
        for path in self.data_dir.glob("presupuesto_????-??.json"):
            meses.append(path.stem.replace("presupuesto_", ""))
        return sorted(meses)

    @staticmethod
    def _validar_mes(year: int, month: int) -> None:
        """Valida rango basico de año y mes."""
        if year < 2000 or year > 2100:
            raise ValueError("El año debe estar entre 2000 y 2100.")
        if month < 1 or month > 12:
            raise ValueError("El mes debe estar entre 1 y 12.")
