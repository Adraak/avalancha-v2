"""Contrato mínimo del ejecutable portable de Avalancha."""

from __future__ import annotations

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SPEC_PATH = PROJECT_ROOT / "packaging" / "Avalancha.spec"


def test_packaging_spec_targets_main_v2() -> None:
    """El artefacto portable parte exclusivamente desde la aplicación V2."""
    text = SPEC_PATH.read_text(encoding="utf-8")

    assert 'project_root / "main_v2.py"' in text
    assert 'name="Avalancha"' in text
    assert "console=False" in text


def test_packaging_spec_is_one_file() -> None:
    """21A produce un único ejecutable portable, no una distribución onedir."""
    text = SPEC_PATH.read_text(encoding="utf-8")

    assert "COLLECT(" not in text
    assert "analysis.binaries" in text
    assert "analysis.datas" in text


def test_packaging_spec_does_not_bundle_user_data() -> None:
    """Datos financieros, claves, reportes y respaldos quedan fuera del binario."""
    text = SPEC_PATH.read_text(encoding="utf-8")

    assert "datas=[]" in text
    for forbidden in (
        "data/perfiles",
        "data\\perfiles",
        "reportes/",
        "reportes\\",
        "config/",
        "config\\",
        "backup/",
        "backup\\",
        "backups/",
        "backups\\",
    ):
        assert forbidden not in text
