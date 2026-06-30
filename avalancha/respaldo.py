"""Automatic ZIP backups for Avalancha local data."""

from __future__ import annotations

import json
import zipfile
from datetime import datetime
from pathlib import Path


class GestorRespaldos:
    """Create complete startup backups and enforce retention."""

    def __init__(
        self,
        data_dir: str | Path = "data",
        backup_dir: str | Path = "backup",
        reports_dir: str | Path = "reportes",
        retention: int = 20,
    ) -> None:
        """Inicializa las rutas configurables y la retención."""
        self.data_dir = Path(data_dir)
        self.backup_dir = Path(backup_dir)
        self.reports_dir = Path(reports_dir)
        self.retention = max(int(retention), 1)
        self.backup_dir.mkdir(parents=True, exist_ok=True)

    def crear_respaldo(self, now: datetime | None = None) -> Path:
        """Create a timestamped ZIP with current financial data."""
        current_time = now or datetime.now()
        stamp = current_time.strftime("%Y_%m_%d_%H%M%S")
        path = self.backup_dir / f"backup_{stamp}.zip"
        sequence = 1
        while path.exists():
            path = self.backup_dir / f"backup_{stamp}_{sequence}.zip"
            sequence += 1

        with zipfile.ZipFile(
            path,
            "w",
            compression=zipfile.ZIP_DEFLATED,
        ) as archive:
            self._add_global_file(archive, "deudas.json")
            self._add_global_file(archive, "cuentas.json")
            self._add_global_file(archive, "historial_mensual.json")
            for budget_path in sorted(
                self.data_dir.glob("presupuesto_????-??.json")
            ):
                archive.write(
                    budget_path,
                    f"presupuestos/{budget_path.name}",
                )
            self._add_compatibility_exports(archive)
            self._add_encrypted_reports(archive)

        self._enforce_retention()
        return path

    def _add_global_file(
        self,
        archive: zipfile.ZipFile,
        filename: str,
    ) -> None:
        """Add a global JSON file or an empty compatible placeholder."""
        source = self.data_dir / filename
        if source.exists():
            archive.write(source, filename)
        else:
            archive.writestr(filename, "{}\n")

    def _add_compatibility_exports(self, archive: zipfile.ZipFile) -> None:
        """Add consolidated files requested by the backup specification."""
        movements = []
        categories = []
        recurring = []
        for path in sorted(self.data_dir.glob("presupuesto_????-??.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            month = path.stem.replace("presupuesto_", "")
            movements.extend(
                {"mes": month, **item}
                for item in data.get("transactions", [])
            )
            categories.extend(
                {"mes": month, **item}
                for item in data.get("categories", [])
            )
            recurring.extend(
                {"mes": month, **item}
                for item in data.get("recurring_items", [])
            )
        archive.writestr(
            "movimientos.json",
            self._json_text({"movements": movements}),
        )
        archive.writestr(
            "categorias.json",
            self._json_text({"categories": categories}),
        )
        archive.writestr(
            "recurrentes.json",
            self._json_text({"recurring_items": recurring}),
        )

    def _add_encrypted_reports(self, archive: zipfile.ZipFile) -> None:
        """Agrega solo reportes e índice cifrados al respaldo."""
        if not self.reports_dir.exists():
            return
        allowed_suffixes = {".avr", ".avridx"}
        for path in sorted(self.reports_dir.iterdir()):
            if not path.is_file() or path.suffix not in allowed_suffixes:
                continue
            archive.write(path, f"reportes/{path.name}")

    def _enforce_retention(self) -> None:
        """Keep only the newest configured number of ZIP backups."""
        backups = sorted(
            self.backup_dir.glob("backup_*.zip"),
            key=lambda path: (path.stat().st_mtime_ns, path.name),
            reverse=True,
        )
        for obsolete in backups[self.retention:]:
            obsolete.unlink()

    @staticmethod
    def _json_text(data: dict[str, object]) -> str:
        """Return consistently formatted JSON text."""
        return (
            json.dumps(
                data,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n"
        )
