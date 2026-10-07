"""Diagnóstico local seguro para errores de Avalancha V2."""

from __future__ import annotations

import json
import os
import re
import traceback
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


_CONTEXT_PATTERN = re.compile(r"^[A-Za-z0-9_.-]{1,80}$")
_MAX_FRAMES = 8
_MAX_LOG_SIZE = 1024 * 1024
_MAX_ROTATED_FILES = 3


class UserFacingError(ValueError):
    """Validación cuyo mensaje es seguro para mostrar en la interfaz."""


@dataclass(frozen=True, slots=True)
class ErrorNotice:
    """Mensaje público asociado a un incidente técnico local."""

    incident_id: str
    message: str


class SafeErrorReporter:
    """Registra metadatos técnicos sin guardar mensajes ni datos del usuario."""

    def __init__(self, log_dir: str | Path | None = None) -> None:
        """Inicializa el directorio local de diagnóstico."""
        self.log_dir = Path(log_dir) if log_dir is not None else self._default_log_dir()
        self.log_path = self.log_dir / "errors.jsonl"

    def report(
        self,
        exc: BaseException,
        *,
        context: str,
        user_message: str,
    ) -> ErrorNotice:
        """Registra un incidente sanitizado y devuelve un mensaje seguro."""
        incident_id = uuid4().hex[:12].upper()
        safe_context = context if _CONTEXT_PATTERN.fullmatch(context) else "invalid_context"
        event = {
            "timestamp_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "incident_id": incident_id,
            "context": safe_context,
            "exception_type": type(exc).__name__,
            "exception_chain": self._exception_chain(exc),
            "frames": self._safe_frames(exc),
        }
        self._write_event(event)
        return ErrorNotice(
            incident_id=incident_id,
            message=f"{user_message}\n\nCódigo de incidente: {incident_id}",
        )

    @staticmethod
    def _default_log_dir() -> Path:
        """Resuelve almacenamiento local fuera del repositorio y de los perfiles."""
        configured = os.environ.get("AVALANCHA_LOG_DIR", "").strip()
        if configured:
            return Path(configured)
        local_app_data = os.environ.get("LOCALAPPDATA", "").strip()
        base = Path(local_app_data) if local_app_data else Path.home()
        return base / "Avalancha" / "logs"

    @staticmethod
    def _exception_chain(exc: BaseException) -> list[str]:
        """Conserva sólo tipos de excepción, nunca mensajes ni argumentos."""
        result: list[str] = []
        current: BaseException | None = exc
        seen: set[int] = set()
        while current is not None and id(current) not in seen and len(result) < 4:
            seen.add(id(current))
            result.append(type(current).__name__)
            current = current.__cause__ or current.__context__
        return result

    @staticmethod
    def _safe_frames(exc: BaseException) -> list[dict[str, object]]:
        """Conserva ubicación de código sin rutas completas ni líneas fuente."""
        frames = traceback.extract_tb(exc.__traceback__)[-_MAX_FRAMES:]
        return [
            {
                "module": Path(frame.filename).name,
                "function": frame.name,
                "line": frame.lineno,
            }
            for frame in frames
        ]

    def _write_event(self, event: dict[str, object]) -> None:
        """Persiste JSONL best-effort; un fallo del log nunca rompe la aplicación."""
        try:
            self.log_dir.mkdir(parents=True, exist_ok=True)
            self._rotate_if_needed()
            with self.log_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(event, ensure_ascii=False, sort_keys=True))
                handle.write("\n")
        except OSError:
            return

    def _rotate_if_needed(self) -> None:
        """Acota el tamaño del diagnóstico local sin depender de logging global."""
        if not self.log_path.exists() or self.log_path.stat().st_size < _MAX_LOG_SIZE:
            return
        oldest = self.log_path.with_suffix(f".jsonl.{_MAX_ROTATED_FILES}")
        oldest.unlink(missing_ok=True)
        for number in range(_MAX_ROTATED_FILES - 1, 0, -1):
            source = self.log_path.with_suffix(f".jsonl.{number}")
            target = self.log_path.with_suffix(f".jsonl.{number + 1}")
            if source.exists():
                source.replace(target)
        self.log_path.replace(self.log_path.with_suffix(".jsonl.1"))
