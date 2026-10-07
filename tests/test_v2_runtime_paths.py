"""Pruebas de rutas persistentes para ejecución instalable."""

from __future__ import annotations

import sys
from pathlib import Path

from services.profile_service import ProfileService
from services.runtime_paths import RuntimePaths


def test_source_execution_keeps_project_data(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """Desde fuente los datos siguen junto al proyecto para no romper desarrollo."""
    monkeypatch.delenv("AVALANCHA_APP_DATA_DIR", raising=False)
    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    monkeypatch.delattr(sys, "frozen", raising=False)

    paths = RuntimePaths.current(source_root=tmp_path)

    assert paths.user_root == tmp_path.resolve()
    assert paths.profiles_root == tmp_path.resolve() / "data" / "perfiles"
    assert paths.legacy_data_dir == tmp_path.resolve() / "data"
    assert paths.legacy_reports_dir == tmp_path.resolve() / "reportes"
    assert paths.legacy_config_dir == tmp_path.resolve() / "config"


def test_frozen_execution_uses_local_app_data(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """Un ejecutable instalado no escribe datos al lado del binario."""
    local_app_data = tmp_path / "LocalAppData"
    monkeypatch.delenv("AVALANCHA_APP_DATA_DIR", raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(local_app_data))
    monkeypatch.setattr(sys, "frozen", True, raising=False)

    paths = RuntimePaths.current(source_root=tmp_path / "program")

    expected = (local_app_data / "Avalancha").resolve()
    assert paths.user_root == expected
    assert paths.profiles_root == expected / "data" / "perfiles"
    assert paths.user_root != (tmp_path / "program").resolve()


def test_explicit_app_data_override_has_priority(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """El override permite aislar runtime y pruebas sin depender del cwd."""
    override = tmp_path / "runtime"
    monkeypatch.setenv("AVALANCHA_APP_DATA_DIR", str(override))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "other"))
    monkeypatch.setattr(sys, "frozen", True, raising=False)

    paths = RuntimePaths.current(source_root=tmp_path / "program")

    assert paths.user_root == override.resolve()
    assert paths.profiles_root == override.resolve() / "data" / "perfiles"


def test_profile_service_defaults_follow_runtime_override(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """ProfileService sin rutas explícitas usa la raíz runtime central."""
    override = tmp_path / "runtime"
    monkeypatch.setenv("AVALANCHA_APP_DATA_DIR", str(override))

    service = ProfileService()

    assert service.profiles_root == override.resolve() / "data" / "perfiles"
    assert service.registry_path.parent == service.profiles_root
    assert service.registry_path.exists()
    assert service.active_path.exists()


def test_explicit_profile_paths_preserve_injection(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """Tests y consumidores pueden seguir inyectando rutas aisladas."""
    monkeypatch.setenv("AVALANCHA_APP_DATA_DIR", str(tmp_path / "ignored"))
    custom = tmp_path / "custom"

    service = ProfileService(
        profiles_root=custom / "perfiles",
        legacy_data_dir=custom / "legacy_data",
        legacy_reports_dir=custom / "legacy_reports",
        legacy_config_dir=custom / "legacy_config",
    )

    assert service.profiles_root == custom / "perfiles"
    assert service.legacy_data_dir == custom / "legacy_data"
    assert service.legacy_reports_dir == custom / "legacy_reports"
    assert service.legacy_config_dir == custom / "legacy_config"
