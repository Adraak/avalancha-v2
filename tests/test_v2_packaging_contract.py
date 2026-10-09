"""Contrato mínimo del ejecutable portable de Avalancha."""

from __future__ import annotations

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SPEC_PATH = PROJECT_ROOT / "packaging" / "Avalancha.spec"
LIGHT_LOGO_PATH = (
    PROJECT_ROOT
    / "assets"
    / "branding"
    / "antisimetria"
    / "antisimetria_logo_light.png"
)


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


def test_packaging_spec_bundles_only_the_light_institutional_logo() -> None:
    """El único dato declarado es el logo claro oficial de Antisimetría."""
    text = SPEC_PATH.read_text(encoding="utf-8")

    assert 'branding_directory = project_root / "assets" / "branding" / "antisimetria"' in text
    assert 'branding_directory / "antisimetria_logo_light.png"' in text
    assert text.count('"assets/branding/antisimetria"') == 1
    assert text.count(".png") == 1
    assert "datas=branding_datas" in text
    assert LIGHT_LOGO_PATH.is_file()


def test_packaging_spec_does_not_require_dark_logo() -> None:
    """El build no depende de un logo oscuro que Avalancha ya no usa."""
    text = SPEC_PATH.read_text(encoding="utf-8")

    assert "antisimetria_logo_dark.png" not in text
    assert "dark" not in text.lower()


def test_packaging_spec_does_not_bundle_whole_directories() -> None:
    """El spec declara archivos puntuales, nunca carpetas ni comodines."""
    text = SPEC_PATH.read_text(encoding="utf-8")

    assert "Tree(" not in text
    assert "collect_data_files" not in text
    assert "glob" not in text
    assert '(str(project_root / "assets")' not in text
    assert "(str(branding_directory)," not in text


def test_packaging_spec_does_not_bundle_user_data() -> None:
    """Datos financieros, perfiles, claves, reportes y respaldos quedan fuera."""
    text = SPEC_PATH.read_text(encoding="utf-8")

    assert "datas=branding_datas" in text
    for forbidden in (
        '"data"',
        "data/",
        "data\\",
        "perfiles",
        "reportes",
        "config/",
        "config\\",
        '"config"',
        "backup",
        ".key",
        ".json",
        ".csv",
        ".xlsx",
        ".zip",
    ):
        assert forbidden not in text
