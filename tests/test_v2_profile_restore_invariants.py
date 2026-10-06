"""Invariantes adversariales de restauracion criptografica — Etapa 18E."""

from __future__ import annotations

import hashlib

import pytest
from cryptography.fernet import Fernet

from avalancha.gestor_reportes import PREFIJO_DPAPI
from core.models.backup import (
    CryptoKeyIncompatibleError,
    RestorePreparationError,
)
from services.profile_restore_service import ProfileRestoreService
from tests.test_v2_profile_restore_service import (
    build_profile,
    build_zip_from_raw_manifest,
    raw_manifest_dict,
)


def _entry(path: str, data: bytes, role: str) -> dict[str, object]:
    return {
        "path": path,
        "size": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "role": role,
    }


def test_key_policy_missing_no_puede_declarar_reporte_key(tmp_path):
    """includes_reporte_key=False no puede coexistir con reporte.key fisica."""
    destino = build_profile(tmp_path, "destino")
    clave = Fernet.generate_key()
    zip_path = tmp_path / "contradiccion_key.zip"
    manifest = raw_manifest_dict(
        profile_id=destino.id,
        key_policy={
            "includes_reporte_key": False,
            "protection": "missing",
            "portable_across_windows_users": False,
        },
        files=[
            _entry("profile/config/reporte.key", clave, "crypto_key"),
        ],
    )
    build_zip_from_raw_manifest(
        zip_path,
        manifest,
        {"profile/config/reporte.key": clave},
    )

    with pytest.raises(RestorePreparationError):
        ProfileRestoreService().preparar(zip_path, destino)


def test_path_crypto_no_puede_disfrazarse_con_role_financial_data(tmp_path):
    """La semantica criptografica depende tambien de la ruta, no solo del role."""
    destino = build_profile(tmp_path, "destino")
    clave = Fernet.generate_key()
    zip_path = tmp_path / "key_role_falso.zip"
    manifest = raw_manifest_dict(
        profile_id=destino.id,
        key_policy={
            "includes_reporte_key": False,
            "protection": "missing",
            "portable_across_windows_users": False,
        },
        files=[
            _entry("profile/config/reporte.key", clave, "financial_data"),
        ],
    )
    build_zip_from_raw_manifest(
        zip_path,
        manifest,
        {"profile/config/reporte.key": clave},
    )

    with pytest.raises(RestorePreparationError):
        ProfileRestoreService().preparar(zip_path, destino)


def test_path_avr_no_puede_disfrazarse_con_role_financial_data(tmp_path):
    """Un .avr fisico requiere unidad criptografica aunque el role mienta."""
    destino = build_profile(tmp_path, "destino")
    contenido = b"reporte-adversarial"
    path = "profile/reportes/R2026-10.avr"
    zip_path = tmp_path / "avr_role_falso.zip"
    manifest = raw_manifest_dict(
        profile_id=destino.id,
        key_policy={
            "includes_reporte_key": False,
            "protection": "missing",
            "portable_across_windows_users": False,
        },
        files=[_entry(path, contenido, "financial_data")],
    )
    build_zip_from_raw_manifest(zip_path, manifest, {path: contenido})

    with pytest.raises(RestorePreparationError):
        ProfileRestoreService().preparar(zip_path, destino)


def test_key_policy_true_sin_reporte_key_se_rechaza(tmp_path):
    """includes_reporte_key=True exige una reporte.key declarada."""
    destino = build_profile(tmp_path, "destino")
    contenido = b"{}"
    path = "profile/data/cuentas.json"
    zip_path = tmp_path / "key_ausente.zip"
    manifest = raw_manifest_dict(
        profile_id=destino.id,
        key_policy={
            "includes_reporte_key": True,
            "protection": "plain",
            "portable_across_windows_users": True,
        },
        files=[_entry(path, contenido, "financial_data")],
    )
    build_zip_from_raw_manifest(zip_path, manifest, {path: contenido})

    with pytest.raises(RestorePreparationError):
        ProfileRestoreService().preparar(zip_path, destino)


def test_rol_criptografico_no_puede_usarse_en_data(tmp_path):
    """Un rol crypto_key no puede disfrazar un archivo financiero normal."""
    destino = build_profile(tmp_path, "destino")
    contenido = b"{}"
    path = "profile/data/cuentas.json"
    zip_path = tmp_path / "rol_crypto_fuera_de_scope.zip"
    manifest = raw_manifest_dict(
        profile_id=destino.id,
        key_policy={
            "includes_reporte_key": False,
            "protection": "missing",
            "portable_across_windows_users": False,
        },
        files=[_entry(path, contenido, "crypto_key")],
    )
    build_zip_from_raw_manifest(zip_path, manifest, {path: contenido})

    with pytest.raises(RestorePreparationError):
        ProfileRestoreService().preparar(zip_path, destino)


def test_index_no_puede_disfrazarse_con_role_financial_data(tmp_path):
    """index.avridx exige el rol report_index."""
    destino = build_profile(tmp_path, "destino")
    clave = Fernet.generate_key()
    key_path = "profile/config/reporte.key"
    index_path = "profile/reportes/index.avridx"
    contenido_index = b"indice-adversarial"
    zip_path = tmp_path / "index_role_falso.zip"
    manifest = raw_manifest_dict(
        profile_id=destino.id,
        key_policy={
            "includes_reporte_key": True,
            "protection": "plain",
            "portable_across_windows_users": True,
        },
        files=[
            _entry(key_path, clave, "crypto_key"),
            _entry(index_path, contenido_index, "financial_data"),
        ],
    )
    build_zip_from_raw_manifest(
        zip_path,
        manifest,
        {
            key_path: clave,
            index_path: contenido_index,
        },
    )

    with pytest.raises(RestorePreparationError):
        ProfileRestoreService().preparar(zip_path, destino)


def test_protection_dpapi_exige_prefijo_dpapi(tmp_path):
    """Una clave plain no puede declararse como DPAPI."""
    destino = build_profile(tmp_path, "destino")
    clave = Fernet.generate_key()
    path = "profile/config/reporte.key"
    zip_path = tmp_path / "dpapi_falso.zip"
    manifest = raw_manifest_dict(
        profile_id=destino.id,
        key_policy={
            "includes_reporte_key": True,
            "protection": "dpapi",
            "portable_across_windows_users": False,
        },
        files=[_entry(path, clave, "crypto_key")],
    )
    build_zip_from_raw_manifest(zip_path, manifest, {path: clave})

    with pytest.raises(CryptoKeyIncompatibleError):
        ProfileRestoreService().preparar(zip_path, destino)


def test_protection_plain_rechaza_bytes_dpapi(tmp_path):
    """Bytes con formato DPAPI no pueden aceptarse como clave plain."""
    destino = build_profile(tmp_path, "destino")
    contenido = PREFIJO_DPAPI + b"blob-sintetico-no-real"
    path = "profile/config/reporte.key"
    zip_path = tmp_path / "plain_falso.zip"
    manifest = raw_manifest_dict(
        profile_id=destino.id,
        key_policy={
            "includes_reporte_key": True,
            "protection": "plain",
            "portable_across_windows_users": True,
        },
        files=[_entry(path, contenido, "crypto_key")],
    )
    build_zip_from_raw_manifest(zip_path, manifest, {path: contenido})

    with pytest.raises(CryptoKeyIncompatibleError):
        ProfileRestoreService().preparar(zip_path, destino)
