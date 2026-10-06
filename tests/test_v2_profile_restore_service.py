"""Pruebas de restauración segura con staging y rollback (Etapa 18E)."""

from __future__ import annotations

import json
import os
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest
from cryptography.fernet import Fernet

from avalancha.gestor_reportes import PREFIJO_DPAPI, ProveedorClaveLocal
from core.models.backup import (
    CryptoKeyIncompatibleError,
    ProfileMismatchError,
    RestorePreparationError,
    RestoreVerificationError,
    UnsafeBackupPathError,
)
from services.backup_service import MANIFEST_ENTRY_NAME, ProfileBackupService
from services.profile_restore_service import (
    ProfileRestoreService,
    _Journal,
)
from services.profile_service import PerfilAplicacion
from services.settings_service import SettingsService


FIXED_NOW = datetime(2026, 9, 29, 12, 0, 0)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def build_profile(
    tmp_path: Path,
    suffix: str,
    profile_id: str = "personal",
    nombre: str = "Personal",
) -> PerfilAplicacion:
    """Crea un perfil sintético con sus tres carpetas base."""
    raiz = tmp_path / "perfiles" / f"{profile_id}_{suffix}"
    profile = PerfilAplicacion(id=profile_id, nombre=nombre, raiz=raiz)
    profile.data_dir.mkdir(parents=True)
    profile.config_dir.mkdir(parents=True)
    profile.reports_dir.mkdir(parents=True)
    return profile


def build_settings_service(
    profile: PerfilAplicacion,
    backup_dir: Path,
    *,
    persist: bool = True,
) -> SettingsService:
    """Crea un SettingsService apuntando al perfil y carpeta de respaldo dados."""
    service = SettingsService(
        config_dir=profile.config_dir,
        reports_dir=profile.reports_dir,
        backup_dir=backup_dir,
    )
    if persist:
        service.guardar_configuracion(service.obtener_configuracion_por_defecto())
    return service


def write_financial_file(
    profile: PerfilAplicacion,
    name: str,
    content: str = "{}",
) -> Path:
    """Escribe un archivo financiero sintético bajo data/ del perfil."""
    path = profile.data_dir / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def clave_plain() -> bytes:
    """Genera una clave Fernet sintética sin ninguna protección DPAPI."""
    return Fernet.generate_key()


def clave_dpapi(clave_base: bytes | None = None) -> tuple[bytes, bytes]:
    """Genera una clave protegida con DPAPI del usuario actual (sintética)."""
    base = clave_base or Fernet.generate_key()
    protegida = PREFIJO_DPAPI + ProveedorClaveLocal._proteger_con_dpapi(base)
    return base, protegida


def reporte_cifrado(clave: bytes, secciones: list[Any] | None = None) -> bytes:
    """Cifra un reporte sintético mínimo y válido para el formato real."""
    cifrador = Fernet(clave)
    contenido = json.dumps(
        {"secciones": secciones or [], "encabezado": []},
    ).encode("utf-8")
    return cifrador.encrypt(contenido)


def indice_cifrado(clave: bytes, reportes: list[Any] | None = None) -> bytes:
    """Cifra un índice sintético mínimo y válido para el formato real."""
    cifrador = Fernet(clave)
    contenido = json.dumps(
        {"version": 1, "reportes": reportes or []},
    ).encode("utf-8")
    return cifrador.encrypt(contenido)


def crear_backup(
    origen: PerfilAplicacion,
    backup_dir: Path,
    *,
    now: datetime = FIXED_NOW,
):
    """Crea un backup real del perfil origen usando ProfileBackupService."""
    settings_service = build_settings_service(origen, backup_dir)
    return ProfileBackupService().crear_backup(origen, settings_service, now=now)


def raw_manifest_dict(
    *,
    profile_id: str = "personal",
    key_policy: dict[str, Any] | None = None,
    files: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Construye un dict de manifest crudo para escenarios adversariales."""
    return {
        "schema_version": 1,
        "app": "Avalancha V2",
        "created_at": FIXED_NOW.isoformat(timespec="seconds"),
        "backup_type": "profile",
        "profile_id": profile_id,
        "profile_name": "Personal",
        "key_policy": key_policy
        if key_policy is not None
        else {
            "includes_reporte_key": False,
            "protection": "missing",
            "portable_across_windows_users": False,
        },
        "files": files or [],
    }


def build_zip_from_raw_manifest(
    zip_path: Path,
    manifest_dict: dict[str, Any],
    file_contents: dict[str, bytes],
) -> None:
    """Construye un ZIP a mano a partir de un manifest crudo (sin validar)."""
    with zipfile.ZipFile(zip_path, "w") as archive:
        for name, data in file_contents.items():
            archive.writestr(name, data)
        archive.writestr(MANIFEST_ENTRY_NAME, json.dumps(manifest_dict))


# ---------------------------------------------------------------------------
# 1-3. Validación inicial, cero efectos
# ---------------------------------------------------------------------------


def test_restore_valido_aplica_completo(tmp_path: Path) -> None:
    """Un restore válido reemplaza, crea, elimina y preserva según el scope."""
    origen = build_profile(tmp_path, "origen")
    write_financial_file(origen, "cuentas.json", '{"cuentas": [1, 2, 3]}')
    write_financial_file(origen, "deudas.json", '{"deudas": []}')
    creado = crear_backup(origen, tmp_path / "backups")

    destino = build_profile(tmp_path, "destino")
    write_financial_file(destino, "cuentas.json", '{"cuentas": ["viejo"]}')
    write_financial_file(destino, "huerfano.json", '{"huerfano": true}')
    (destino.config_dir / "nota.txt").write_text("fuera de scope", encoding="utf-8")

    resultado = ProfileRestoreService().restaurar(creado.zip_path, destino)

    assert resultado.outcome == "APPLIED"
    assert resultado.error is None
    assert (destino.data_dir / "cuentas.json").read_text() == '{"cuentas": [1, 2, 3]}'
    assert (destino.data_dir / "deudas.json").exists()
    assert not (destino.data_dir / "huerfano.json").exists()
    assert (destino.config_dir / "nota.txt").exists()


def test_backup_invalido_sin_efectos(tmp_path: Path) -> None:
    """Un ZIP corrupto se rechaza sin tocar el perfil destino."""
    zip_invalido = tmp_path / "corrupto.zip"
    zip_invalido.write_bytes(b"esto no es un zip")
    destino = build_profile(tmp_path, "destino")
    write_financial_file(destino, "cuentas.json", "{}")
    antes = list(destino.data_dir.iterdir())

    with pytest.raises(Exception):
        ProfileRestoreService().preparar(zip_invalido, destino)

    assert list(destino.data_dir.iterdir()) == antes


def test_profile_mismatch_sin_efectos(tmp_path: Path) -> None:
    """Un backup de otro perfil se rechaza sin efectos."""
    origen = build_profile(tmp_path, "origen", profile_id="perfil_a")
    write_financial_file(origen, "cuentas.json", "{}")
    creado = crear_backup(origen, tmp_path / "backups")

    destino = build_profile(tmp_path, "destino", profile_id="perfil_b")
    write_financial_file(destino, "cuentas.json", '{"intacto": true}')

    with pytest.raises(ProfileMismatchError):
        ProfileRestoreService().preparar(creado.zip_path, destino)

    assert destino.data_dir.joinpath("cuentas.json").read_text() == (
        '{"intacto": true}'
    )


def test_fallo_antes_de_apply_sin_efectos(tmp_path: Path) -> None:
    """Si preparar() falla, aplicar() nunca se invoca y no hay efectos."""
    origen = build_profile(tmp_path, "origen")
    write_financial_file(origen, "cuentas.json", "{}")
    (origen.reports_dir / "R2026-09.avr").write_bytes(b"huerfano-sin-clave")
    creado = crear_backup(origen, tmp_path / "backups")

    destino = build_profile(tmp_path, "destino")

    with pytest.raises(RestorePreparationError):
        ProfileRestoreService().preparar(creado.zip_path, destino)

    assert list(destino.data_dir.iterdir()) == []
    assert list(destino.reports_dir.iterdir()) == []


# ---------------------------------------------------------------------------
# 4-8. Semántica exacta: reemplazo, creación, eliminación, preservación
# ---------------------------------------------------------------------------


def test_reemplaza_archivo_existente(tmp_path: Path) -> None:
    """Un archivo administrado existente se reemplaza con el contenido del backup."""
    origen = build_profile(tmp_path, "origen")
    write_financial_file(origen, "cuentas.json", '{"nuevo": true}')
    creado = crear_backup(origen, tmp_path / "backups")

    destino = build_profile(tmp_path, "destino")
    write_financial_file(destino, "cuentas.json", '{"viejo": true}')

    resultado = ProfileRestoreService().restaurar(creado.zip_path, destino)

    assert resultado.outcome == "APPLIED"
    assert (destino.data_dir / "cuentas.json").read_text() == '{"nuevo": true}'


def test_crea_archivo_nuevo(tmp_path: Path) -> None:
    """Un archivo del backup ausente en destino se crea."""
    origen = build_profile(tmp_path, "origen")
    write_financial_file(origen, "deudas.json", '{"deudas": []}')
    creado = crear_backup(origen, tmp_path / "backups")

    destino = build_profile(tmp_path, "destino")
    assert not (destino.data_dir / "deudas.json").exists()

    resultado = ProfileRestoreService().restaurar(creado.zip_path, destino)

    assert resultado.outcome == "APPLIED"
    assert (destino.data_dir / "deudas.json").exists()


def test_elimina_archivo_administrado_ausente(tmp_path: Path) -> None:
    """Un archivo administrado en destino ausente del backup se elimina."""
    origen = build_profile(tmp_path, "origen")
    write_financial_file(origen, "cuentas.json", "{}")
    creado = crear_backup(origen, tmp_path / "backups")

    destino = build_profile(tmp_path, "destino")
    write_financial_file(destino, "cuentas.json", "{}")
    write_financial_file(destino, "presupuesto_2026-01.json", '{"viejo": true}')

    resultado = ProfileRestoreService().restaurar(creado.zip_path, destino)

    assert resultado.outcome == "APPLIED"
    assert resultado.files_deleted == 1
    assert not (destino.data_dir / "presupuesto_2026-01.json").exists()


def test_preserva_archivo_config_desconocido(tmp_path: Path) -> None:
    """Un archivo desconocido en config/ (ni settings.json ni reporte.key) se preserva."""
    origen = build_profile(tmp_path, "origen")
    write_financial_file(origen, "cuentas.json", "{}")
    creado = crear_backup(origen, tmp_path / "backups")

    destino = build_profile(tmp_path, "destino")
    desconocido = destino.config_dir / "preferencias_locales.ini"
    desconocido.write_text("algo-no-administrado", encoding="utf-8")

    resultado = ProfileRestoreService().restaurar(creado.zip_path, destino)

    assert resultado.outcome == "APPLIED"
    assert desconocido.read_text() == "algo-no-administrado"


def test_preserva_archivo_reportes_desconocido(tmp_path: Path) -> None:
    """Un archivo en reportes/ que no sea .avr ni index.avridx se preserva."""
    origen = build_profile(tmp_path, "origen")
    write_financial_file(origen, "cuentas.json", "{}")
    creado = crear_backup(origen, tmp_path / "backups")

    destino = build_profile(tmp_path, "destino")
    desconocido = destino.reports_dir / "notas_manuales.txt"
    desconocido.write_text("nota manual del usuario", encoding="utf-8")

    resultado = ProfileRestoreService().restaurar(creado.zip_path, destino)

    assert resultado.outcome == "APPLIED"
    assert desconocido.read_text() == "nota manual del usuario"


def test_settings_restaurado(tmp_path: Path) -> None:
    """settings.json se restaura exactamente como estaba en el backup."""
    origen = build_profile(tmp_path, "origen")
    write_financial_file(origen, "cuentas.json", "{}")
    creado = crear_backup(origen, tmp_path / "backups", now=FIXED_NOW)
    contenido_original = (origen.config_dir / "settings.json").read_bytes()

    destino = build_profile(tmp_path, "destino")
    (destino.config_dir / "settings.json").write_text(
        '{"moneda_principal": "USD"}',
        encoding="utf-8",
    )

    resultado = ProfileRestoreService().restaurar(creado.zip_path, destino)

    assert resultado.outcome == "APPLIED"
    assert (destino.config_dir / "settings.json").read_bytes() == contenido_original


# ---------------------------------------------------------------------------
# 10-17. Unidad criptográfica: key plain/DPAPI, reportes, index
# ---------------------------------------------------------------------------


def test_key_plain_valida_permite_restore(tmp_path: Path) -> None:
    """Una reporte.key plain válida permite completar la restauración."""
    origen = build_profile(tmp_path, "origen")
    write_financial_file(origen, "cuentas.json", "{}")
    clave = clave_plain()
    origen.key_path.write_bytes(clave)
    creado = crear_backup(origen, tmp_path / "backups")

    destino = build_profile(tmp_path, "destino")

    resultado = ProfileRestoreService().restaurar(creado.zip_path, destino)

    assert resultado.outcome == "APPLIED"
    assert destino.key_path.read_bytes() == clave


def test_key_plain_invalida_rechazada_pre_apply(tmp_path: Path) -> None:
    """Una reporte.key sin prefijo DPAPI que no es Fernet válida se rechaza."""
    origen = build_profile(tmp_path, "origen")
    write_financial_file(origen, "cuentas.json", "{}")
    origen.key_path.write_bytes(b"esto-no-es-una-clave-fernet-valida")
    creado = crear_backup(origen, tmp_path / "backups")

    destino = build_profile(tmp_path, "destino")

    with pytest.raises(CryptoKeyIncompatibleError):
        ProfileRestoreService().preparar(creado.zip_path, destino)

    assert not destino.key_path.exists()


def test_key_dpapi_compatible_permite_restore(tmp_path: Path) -> None:
    """Una reporte.key DPAPI del usuario actual permite completar la restauración."""
    origen = build_profile(tmp_path, "origen")
    write_financial_file(origen, "cuentas.json", "{}")
    _, protegida = clave_dpapi()
    origen.key_path.write_bytes(protegida)
    creado = crear_backup(origen, tmp_path / "backups")

    destino = build_profile(tmp_path, "destino")

    resultado = ProfileRestoreService().restaurar(creado.zip_path, destino)

    assert resultado.outcome == "APPLIED"
    assert destino.key_path.read_bytes() == protegida


def test_key_dpapi_incompatible_rechazada_pre_apply(tmp_path: Path) -> None:
    """Una reporte.key DPAPI genuinamente incompatible se rechaza antes de aplicar."""
    origen = build_profile(tmp_path, "origen")
    write_financial_file(origen, "cuentas.json", "{}")
    protegida_falsa = PREFIJO_DPAPI + os.urandom(280)
    origen.key_path.write_bytes(protegida_falsa)
    creado = crear_backup(origen, tmp_path / "backups")

    destino = build_profile(tmp_path, "destino")

    with pytest.raises(CryptoKeyIncompatibleError):
        ProfileRestoreService().preparar(creado.zip_path, destino)

    assert not destino.key_path.exists()


def test_reportes_sin_key_bloqueados(tmp_path: Path) -> None:
    """Reportes cifrados sin reporte.key en el backup bloquean la preparación."""
    origen = build_profile(tmp_path, "origen")
    write_financial_file(origen, "cuentas.json", "{}")
    (origen.reports_dir / "R2026-09.avr").write_bytes(b"contenido-huerfano")
    creado = crear_backup(origen, tmp_path / "backups")
    assert creado.manifest.key_policy.includes_reporte_key is False

    destino = build_profile(tmp_path, "destino")

    with pytest.raises(RestorePreparationError):
        ProfileRestoreService().preparar(creado.zip_path, destino)


def test_key_y_avr_coherentes_permiten_restore(tmp_path: Path) -> None:
    """reporte.key + .avr + index.avridx coherentes se restauran completos."""
    origen = build_profile(tmp_path, "origen")
    write_financial_file(origen, "cuentas.json", "{}")
    clave = clave_plain()
    origen.key_path.write_bytes(clave)
    (origen.reports_dir / "R2026-09.avr").write_bytes(reporte_cifrado(clave))
    (origen.reports_dir / "index.avridx").write_bytes(indice_cifrado(clave))
    creado = crear_backup(origen, tmp_path / "backups")

    destino = build_profile(tmp_path, "destino")

    resultado = ProfileRestoreService().restaurar(creado.zip_path, destino)

    assert resultado.outcome == "APPLIED"
    assert (destino.reports_dir / "R2026-09.avr").exists()
    assert (destino.reports_dir / "index.avridx").exists()
    assert not os.access(destino.reports_dir / "R2026-09.avr", os.W_OK)


def test_key_y_avr_incoherentes_bloqueados(tmp_path: Path) -> None:
    """Un .avr cifrado con una clave distinta a la declarada bloquea el restore."""
    clave_del_manifest = clave_plain()
    clave_real_del_avr = clave_plain()
    contenido_avr = reporte_cifrado(clave_real_del_avr)

    manifest = raw_manifest_dict(
        key_policy={
            "includes_reporte_key": True,
            "protection": "plain",
            "portable_across_windows_users": True,
        },
        files=[
            {
                "path": "profile/config/reporte.key",
                "size": len(clave_del_manifest),
                "sha256": __import__("hashlib")
                .sha256(clave_del_manifest)
                .hexdigest(),
                "role": "crypto_key",
            },
            {
                "path": "profile/reportes/R2026-09.avr",
                "size": len(contenido_avr),
                "sha256": __import__("hashlib").sha256(contenido_avr).hexdigest(),
                "role": "encrypted_report",
            },
        ],
    )
    zip_path = tmp_path / "incoherente.zip"
    build_zip_from_raw_manifest(
        zip_path,
        manifest,
        {
            "profile/config/reporte.key": clave_del_manifest,
            "profile/reportes/R2026-09.avr": contenido_avr,
        },
    )

    destino = build_profile(tmp_path, "destino")

    with pytest.raises(CryptoKeyIncompatibleError):
        ProfileRestoreService().preparar(zip_path, destino)

    assert not destino.key_path.exists()
    assert list(destino.reports_dir.iterdir()) == []


# ---------------------------------------------------------------------------
# 18-22. Fallos durante la aplicación (fault injection)
# ---------------------------------------------------------------------------


def test_fallo_primer_write_rollback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Un fallo en el primer WRITE revierte sin dejar ningún efecto."""
    origen = build_profile(tmp_path, "origen")
    write_financial_file(origen, "cuentas.json", '{"nuevo": true}')
    creado = crear_backup(origen, tmp_path / "backups")

    destino = build_profile(tmp_path, "destino")
    write_financial_file(destino, "cuentas.json", '{"viejo": true}')

    service = ProfileRestoreService()
    plan = service.preparar(creado.zip_path, destino)

    contador = {"n": 0}
    original = ProfileRestoreService._aplicar_entrada

    def falla_primera(self, entry, plan):
        contador["n"] += 1
        if contador["n"] == 1:
            raise OSError("fallo simulado en el primer WRITE")
        return original(self, entry, plan)

    monkeypatch.setattr(ProfileRestoreService, "_aplicar_entrada", falla_primera)

    resultado = service.aplicar(plan)

    assert resultado.outcome == "FAILED_ROLLBACK_OK"
    assert (destino.data_dir / "cuentas.json").read_text() == '{"viejo": true}'


def test_fallo_write_intermedio_rollback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Un fallo a mitad de la aplicación revierte todo lo ya aplicado."""
    origen = build_profile(tmp_path, "origen")
    write_financial_file(origen, "cuentas.json", '{"nuevo-cuentas": true}')
    write_financial_file(origen, "deudas.json", '{"nuevo-deudas": true}')
    creado = crear_backup(origen, tmp_path / "backups")

    destino = build_profile(tmp_path, "destino")
    write_financial_file(destino, "cuentas.json", '{"viejo-cuentas": true}')

    service = ProfileRestoreService()
    plan = service.preparar(creado.zip_path, destino)
    assert len(plan.entries) == 3  # cuentas.json, deudas.json, settings.json

    contador = {"n": 0}
    original = ProfileRestoreService._aplicar_entrada

    def falla_segunda(self, entry, plan):
        contador["n"] += 1
        if contador["n"] == 2:
            raise OSError("fallo simulado intermedio")
        return original(self, entry, plan)

    monkeypatch.setattr(ProfileRestoreService, "_aplicar_entrada", falla_segunda)

    resultado = service.aplicar(plan)

    assert resultado.outcome == "FAILED_ROLLBACK_OK"
    assert (destino.data_dir / "cuentas.json").read_text() == '{"viejo-cuentas": true}'
    assert not (destino.data_dir / "deudas.json").exists()


def test_fallo_delete_rollback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Un fallo durante un DELETE revierte y recupera el archivo eliminado."""
    origen = build_profile(tmp_path, "origen")
    write_financial_file(origen, "cuentas.json", "{}")
    creado = crear_backup(origen, tmp_path / "backups")

    destino = build_profile(tmp_path, "destino")
    write_financial_file(destino, "cuentas.json", "{}")
    write_financial_file(destino, "huerfano.json", '{"dato": "importante"}')

    service = ProfileRestoreService()
    plan = service.preparar(creado.zip_path, destino)
    delete_entries = [e for e in plan.entries if e.action == "DELETE"]
    assert len(delete_entries) == 1

    original = ProfileRestoreService._aplicar_entrada

    def falla_en_delete(self, entry, plan):
        if entry.action == "DELETE":
            raise OSError("fallo simulado en DELETE")
        return original(self, entry, plan)

    monkeypatch.setattr(ProfileRestoreService, "_aplicar_entrada", falla_en_delete)

    resultado = service.aplicar(plan)

    assert resultado.outcome == "FAILED_ROLLBACK_OK"
    assert (destino.data_dir / "huerfano.json").read_text() == (
        '{"dato": "importante"}'
    )


def test_fallo_verificacion_final_rollback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Un fallo en la verificación final también dispara rollback completo."""
    origen = build_profile(tmp_path, "origen")
    write_financial_file(origen, "cuentas.json", '{"nuevo": true}')
    creado = crear_backup(origen, tmp_path / "backups")

    destino = build_profile(tmp_path, "destino")
    write_financial_file(destino, "cuentas.json", '{"viejo": true}')

    service = ProfileRestoreService()
    plan = service.preparar(creado.zip_path, destino)

    def falla_verificacion(self, plan):
        raise RestoreVerificationError("fallo simulado de verificación")

    monkeypatch.setattr(
        ProfileRestoreService,
        "_verificar_post_aplicacion",
        falla_verificacion,
    )

    resultado = service.aplicar(plan)

    assert resultado.outcome == "FAILED_ROLLBACK_OK"
    assert (destino.data_dir / "cuentas.json").read_text() == '{"viejo": true}'


# ---------------------------------------------------------------------------
# 23-26. Rollback: reemplazados, eliminados, creados, y rollback failure
# ---------------------------------------------------------------------------


def test_rollback_restaura_archivo_reemplazado(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """El rollback restaura exactamente los bytes previos de un reemplazo."""
    origen = build_profile(tmp_path, "origen")
    write_financial_file(origen, "cuentas.json", '{"nuevo": true}')
    write_financial_file(origen, "deudas.json", "{}")
    creado = crear_backup(origen, tmp_path / "backups")

    destino = build_profile(tmp_path, "destino")
    contenido_previo = '{"muy": "importante"}'
    write_financial_file(destino, "cuentas.json", contenido_previo)

    service = ProfileRestoreService()
    plan = service.preparar(creado.zip_path, destino)
    original = ProfileRestoreService._aplicar_entrada

    def falla_al_final(self, entry, plan, _contador={"n": 0}):
        _contador["n"] += 1
        if _contador["n"] == len(plan.entries):
            raise OSError("fallo en la ultima entrada")
        return original(self, entry, plan)

    monkeypatch.setattr(ProfileRestoreService, "_aplicar_entrada", falla_al_final)
    resultado = service.aplicar(plan)

    assert resultado.outcome == "FAILED_ROLLBACK_OK"
    assert (destino.data_dir / "cuentas.json").read_text() == contenido_previo


def test_rollback_recupera_archivo_eliminado(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """El rollback recupera, con bytes idénticos, un archivo que se eliminó."""
    origen = build_profile(tmp_path, "origen")
    write_financial_file(origen, "cuentas.json", "{}")
    creado = crear_backup(origen, tmp_path / "backups")

    destino = build_profile(tmp_path, "destino")
    write_financial_file(destino, "cuentas.json", "{}")
    contenido_huerfano = '{"dato": 12345}'
    write_financial_file(destino, "huerfano.json", contenido_huerfano)

    service = ProfileRestoreService()
    plan = service.preparar(creado.zip_path, destino)

    def siempre_falla(self, entry, plan):
        raise OSError("fallo forzado tras el delete")

    # Reemplazamos solo el paso de verificación para forzar rollback
    # DESPUES de que el DELETE ya se haya aplicado con éxito.
    original = ProfileRestoreService._aplicar_entrada
    aplicadas = []

    def aplicar_y_fallar_despues(self, entry, plan):
        aplicadas.append(entry)
        original(self, entry, plan)
        if entry.action == "DELETE":
            raise OSError("fallo forzado tras aplicar el delete")

    monkeypatch.setattr(
        ProfileRestoreService,
        "_aplicar_entrada",
        aplicar_y_fallar_despues,
    )

    resultado = service.aplicar(plan)

    assert resultado.outcome == "FAILED_ROLLBACK_OK"
    assert (destino.data_dir / "huerfano.json").read_text() == contenido_huerfano


def test_rollback_elimina_archivo_creado(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """El rollback elimina un archivo que el restore había creado."""
    origen = build_profile(tmp_path, "origen")
    write_financial_file(origen, "cuentas.json", "{}")
    write_financial_file(origen, "deudas.json", "{}")
    creado = crear_backup(origen, tmp_path / "backups")

    destino = build_profile(tmp_path, "destino")
    write_financial_file(destino, "cuentas.json", "{}")
    assert not (destino.data_dir / "deudas.json").exists()

    service = ProfileRestoreService()
    plan = service.preparar(creado.zip_path, destino)
    original = ProfileRestoreService._aplicar_entrada

    def falla_al_final(self, entry, plan, _contador={"n": 0}):
        _contador["n"] += 1
        if _contador["n"] == len(plan.entries):
            raise OSError("fallo en la ultima entrada")
        return original(self, entry, plan)

    monkeypatch.setattr(ProfileRestoreService, "_aplicar_entrada", falla_al_final)
    resultado = service.aplicar(plan)

    assert resultado.outcome == "FAILED_ROLLBACK_OK"
    assert not (destino.data_dir / "deudas.json").exists()


def test_rollback_failure_explicito(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Si el rollback mismo falla, el resultado es FAILED_ROLLBACK_FAILED."""
    origen = build_profile(tmp_path, "origen")
    write_financial_file(origen, "cuentas.json", '{"nuevo": true}')
    creado = crear_backup(origen, tmp_path / "backups")

    destino = build_profile(tmp_path, "destino")
    write_financial_file(destino, "cuentas.json", '{"viejo": true}')

    service = ProfileRestoreService()
    plan = service.preparar(creado.zip_path, destino)

    def falla_siempre(self, entry, plan):
        raise OSError("fallo simulado de aplicacion")

    def rollback_falla(self, entry):
        raise OSError("fallo simulado del propio rollback")

    monkeypatch.setattr(ProfileRestoreService, "_aplicar_entrada", falla_siempre)
    monkeypatch.setattr(ProfileRestoreService, "_revertir_entrada", rollback_falla)

    resultado = service.aplicar(plan)

    assert resultado.outcome == "FAILED_ROLLBACK_FAILED"
    assert resultado.staging_dir is not None
    assert resultado.staging_dir.exists()
    assert resultado.failed_rollback_paths != ()


# ---------------------------------------------------------------------------
# 27-31. Aislamiento: otros perfiles, registros globales, backup, ZIP fuente
# ---------------------------------------------------------------------------


def test_otro_perfil_intacto(tmp_path: Path) -> None:
    """Restaurar un perfil no toca el contenido de otro perfil distinto."""
    origen = build_profile(tmp_path, "origen", profile_id="personal")
    write_financial_file(origen, "cuentas.json", '{"a": 1}')
    creado = crear_backup(origen, tmp_path / "backups")

    destino = build_profile(tmp_path, "destino", profile_id="personal")
    otro_perfil = build_profile(tmp_path, "otro", profile_id="demo_avalancha")
    write_financial_file(otro_perfil, "cuentas.json", '{"intacto": true}')

    resultado = ProfileRestoreService().restaurar(creado.zip_path, destino)

    assert resultado.outcome == "APPLIED"
    assert (otro_perfil.data_dir / "cuentas.json").read_text() == '{"intacto": true}'


def test_no_toca_registros_globales(tmp_path: Path) -> None:
    """No se modifican perfiles.json ni perfil_activo.json del registro global."""
    origen = build_profile(tmp_path, "origen")
    write_financial_file(origen, "cuentas.json", "{}")
    creado = crear_backup(origen, tmp_path / "backups")

    destino = build_profile(tmp_path, "destino")
    registro = destino.raiz.parent / "perfiles.json"
    activo = destino.raiz.parent / "perfil_activo.json"
    registro.write_text('{"perfiles": []}', encoding="utf-8")
    activo.write_text('{"slug": "personal"}', encoding="utf-8")

    resultado = ProfileRestoreService().restaurar(creado.zip_path, destino)

    assert resultado.outcome == "APPLIED"
    assert registro.read_text() == '{"perfiles": []}'
    assert activo.read_text() == '{"slug": "personal"}'


def test_zip_origen_intacto(tmp_path: Path) -> None:
    """El ZIP fuente nunca se modifica durante la restauración."""
    origen = build_profile(tmp_path, "origen")
    write_financial_file(origen, "cuentas.json", "{}")
    creado = crear_backup(origen, tmp_path / "backups")
    bytes_antes = creado.zip_path.read_bytes()

    destino = build_profile(tmp_path, "destino")
    ProfileRestoreService().restaurar(creado.zip_path, destino)

    assert creado.zip_path.read_bytes() == bytes_antes


def test_carpeta_backups_intacta(tmp_path: Path) -> None:
    """La carpeta de backups no recibe ningún archivo nuevo durante el restore."""
    origen = build_profile(tmp_path, "origen")
    write_financial_file(origen, "cuentas.json", "{}")
    backup_dir = tmp_path / "backups"
    creado = crear_backup(origen, backup_dir)
    listado_antes = sorted(p.name for p in backup_dir.iterdir())

    destino = build_profile(tmp_path, "destino")
    ProfileRestoreService().restaurar(creado.zip_path, destino)

    assert sorted(p.name for p in backup_dir.iterdir()) == listado_antes


# ---------------------------------------------------------------------------
# 32-33. Defensa symlink/junction en el destino
# ---------------------------------------------------------------------------


def test_symlink_archivo_destino_rechazado(tmp_path: Path) -> None:
    """Un symlink de archivo en el destino que escapa del perfil se rechaza."""
    origen = build_profile(tmp_path, "origen")
    write_financial_file(origen, "cuentas.json", "{}")
    creado = crear_backup(origen, tmp_path / "backups")

    destino = build_profile(tmp_path, "destino")
    externo = tmp_path / "externo.json"
    externo.write_text("{}", encoding="utf-8")
    enlace = destino.data_dir / "cuentas.json"
    try:
        enlace.unlink()
        os.symlink(externo, enlace)
    except OSError:
        pytest.skip("El entorno no permite crear symlinks sin privilegios.")

    with pytest.raises(UnsafeBackupPathError):
        ProfileRestoreService().preparar(creado.zip_path, destino)

    assert externo.read_text() == "{}"


def test_junction_directorio_destino_rechazado(tmp_path: Path) -> None:
    """Una junction de directorio en el destino que escapa se rechaza."""
    origen = build_profile(tmp_path, "origen")
    write_financial_file(origen, "sub/archivo.json", "{}")
    creado = crear_backup(origen, tmp_path / "backups")

    destino = build_profile(tmp_path, "destino")
    externo = tmp_path / "externo_dir"
    externo.mkdir()
    (externo / "secreto.json").write_text('{"leak": true}', encoding="utf-8")
    junction = destino.data_dir / "sub"

    import subprocess

    resultado_mklink = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(junction), str(externo)],
        capture_output=True,
        check=False,
    )
    if resultado_mklink.returncode != 0:
        pytest.skip("El entorno no permite crear junctions NTFS.")

    with pytest.raises(UnsafeBackupPathError):
        ProfileRestoreService().preparar(creado.zip_path, destino)

    assert (externo / "secreto.json").read_text() == '{"leak": true}'


# ---------------------------------------------------------------------------
# 34-35. TOCTOU sobre archivos del perfil destino
# ---------------------------------------------------------------------------


def test_archivo_cambia_tras_snapshot_bloqueado(tmp_path: Path) -> None:
    """Si el archivo destino cambia después del snapshot, se aborta sin aplicar."""
    origen = build_profile(tmp_path, "origen")
    write_financial_file(origen, "cuentas.json", '{"nuevo": true}')
    creado = crear_backup(origen, tmp_path / "backups")

    destino = build_profile(tmp_path, "destino")
    write_financial_file(destino, "cuentas.json", '{"estado-al-snapshot": true}')

    service = ProfileRestoreService()
    plan = service.preparar(creado.zip_path, destino)

    # Simula una modificacion concurrente DESPUES del snapshot.
    write_financial_file(destino, "cuentas.json", '{"cambio-concurrente": true}')

    resultado = service.aplicar(plan)

    assert resultado.outcome == "FAILED_ROLLBACK_OK"
    assert (destino.data_dir / "cuentas.json").read_text() == (
        '{"cambio-concurrente": true}'
    )


def test_archivo_aparece_inesperadamente_bloqueado(tmp_path: Path) -> None:
    """Si un archivo nuevo aparece antes del WRITE, se aborta sin sobrescribir."""
    origen = build_profile(tmp_path, "origen")
    write_financial_file(origen, "deudas.json", '{"nuevo": true}')
    creado = crear_backup(origen, tmp_path / "backups")

    destino = build_profile(tmp_path, "destino")

    service = ProfileRestoreService()
    plan = service.preparar(creado.zip_path, destino)
    assert not (destino.data_dir / "deudas.json").exists()

    # Simula que algo mas crea el archivo justo antes de aplicar.
    write_financial_file(destino, "deudas.json", '{"aparecido": true}')

    resultado = service.aplicar(plan)

    assert resultado.outcome == "FAILED_ROLLBACK_OK"
    assert (destino.data_dir / "deudas.json").read_text() == '{"aparecido": true}'


# ---------------------------------------------------------------------------
# 36. Journal: INTENT sin APPLIED se trata como ambiguo
# ---------------------------------------------------------------------------


def test_journal_intent_sin_applied_se_trata_como_aplicado(
    tmp_path: Path,
) -> None:
    """Un INTENT sin su APPLIED se incluye igual entre los índices a revertir."""
    journal_path = tmp_path / "journal.jsonl"
    journal = _Journal(journal_path)
    journal.intent(0)
    journal.applied(0)
    journal.intent(1)  # sin APPLIED correspondiente: ambiguo
    journal.close()

    indices = _Journal.read_applied_indices(journal_path)

    assert indices == {0, 1}


# ---------------------------------------------------------------------------
# 37-38. Staging: limpieza al éxito, conservación ante rollback fallido
# ---------------------------------------------------------------------------


def test_staging_limpio_tras_exito(tmp_path: Path) -> None:
    """El directorio de staging se elimina por completo al terminar con éxito."""
    origen = build_profile(tmp_path, "origen")
    write_financial_file(origen, "cuentas.json", "{}")
    creado = crear_backup(origen, tmp_path / "backups")

    destino = build_profile(tmp_path, "destino")
    resultado = ProfileRestoreService().restaurar(creado.zip_path, destino)

    assert resultado.outcome == "APPLIED"
    perfiles_dir = tmp_path / "perfiles"
    restantes = [
        p for p in perfiles_dir.iterdir() if p.name.startswith(".avalancha_restore")
    ]
    assert restantes == []


def test_staging_conservado_ante_rollback_fallido(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """El staging se conserva íntegro cuando el propio rollback falla."""
    origen = build_profile(tmp_path, "origen")
    write_financial_file(origen, "cuentas.json", '{"nuevo": true}')
    creado = crear_backup(origen, tmp_path / "backups")

    destino = build_profile(tmp_path, "destino")
    write_financial_file(destino, "cuentas.json", '{"viejo": true}')

    service = ProfileRestoreService()
    plan = service.preparar(creado.zip_path, destino)
    staging_dir = plan.staging_dir

    monkeypatch.setattr(
        ProfileRestoreService,
        "_aplicar_entrada",
        lambda self, entry, plan: (_ for _ in ()).throw(
            OSError("fallo simulado"),
        ),
    )
    monkeypatch.setattr(
        ProfileRestoreService,
        "_revertir_entrada",
        lambda self, entry: (_ for _ in ()).throw(
            OSError("fallo simulado de rollback"),
        ),
    )

    resultado = service.aplicar(plan)

    assert resultado.outcome == "FAILED_ROLLBACK_FAILED"
    assert staging_dir.exists()
    assert (staging_dir / "journal.jsonl").exists()
    assert (staging_dir / "rollback").exists()


# ---------------------------------------------------------------------------
# 39-40. Sin extracción, sin efectos fuera de scope
# ---------------------------------------------------------------------------


def test_no_usa_extractall() -> None:
    """El módulo nunca usa ZipFile.extractall para materializar un backup."""
    import inspect

    import services.profile_restore_service as modulo

    codigo_fuente = inspect.getsource(modulo)
    assert "extractall" not in codigo_fuente


def test_sin_efectos_fuera_del_scope(tmp_path: Path) -> None:
    """Ningún archivo fuera de las cuatro raíces administradas se crea o borra."""
    origen = build_profile(tmp_path, "origen")
    write_financial_file(origen, "cuentas.json", "{}")
    creado = crear_backup(origen, tmp_path / "backups")

    destino = build_profile(tmp_path, "destino")
    marcador_raiz = destino.raiz / "no_administrado.txt"
    marcador_raiz.write_text("fuera de scope en la raiz", encoding="utf-8")

    resultado = ProfileRestoreService().restaurar(creado.zip_path, destino)

    assert resultado.outcome == "APPLIED"
    assert marcador_raiz.read_text() == "fuera de scope en la raiz"


# ---------------------------------------------------------------------------
# Extra: coherencia del descubrimiento de scope administrado
# ---------------------------------------------------------------------------


def test_descubrimiento_coincide_con_inventario_de_creacion(
    tmp_path: Path,
) -> None:
    """El descubrimiento de restore detecta el mismo scope que la creación."""
    perfil = build_profile(tmp_path, "unico")
    write_financial_file(perfil, "cuentas.json", "{}")
    write_financial_file(perfil, "deudas.json", "{}")
    creado = crear_backup(perfil, tmp_path / "backups")

    service = ProfileRestoreService()
    administrados = service._descubrir_administrados(
        perfil,
        perfil.raiz.resolve(),
    )

    assert set(administrados) == {entry.path for entry in creado.manifest.files}


# ---------------------------------------------------------------------------
# Corrección focal — unidad criptográfica: casos A-G (post-auditoría)
# ---------------------------------------------------------------------------


def test_cripto_caso_a_key_actual_se_preserva_byte_a_byte(tmp_path: Path) -> None:
    """A: backup sin key/reportes + destino con key -> key se preserva intacta."""
    origen = build_profile(tmp_path, "origen")
    write_financial_file(origen, "cuentas.json", "{}")
    creado = crear_backup(origen, tmp_path / "backups")
    assert creado.manifest.key_policy.includes_reporte_key is False

    destino = build_profile(tmp_path, "destino")
    write_financial_file(destino, "cuentas.json", "{}")
    clave_viva = b"clave-actual-del-destino-no-debe-borrarse"
    destino.key_path.write_bytes(clave_viva)

    resultado = ProfileRestoreService().restaurar(creado.zip_path, destino)

    assert resultado.outcome == "APPLIED"
    assert destino.key_path.read_bytes() == clave_viva


def test_cripto_caso_b_unidad_completa_destino_se_preserva(tmp_path: Path) -> None:
    """B: backup sin key/reportes + destino con key+avr+index -> todo se preserva."""
    origen = build_profile(tmp_path, "origen")
    write_financial_file(origen, "cuentas.json", "{}")
    creado = crear_backup(origen, tmp_path / "backups")

    destino = build_profile(tmp_path, "destino")
    write_financial_file(destino, "cuentas.json", "{}")
    clave_viva = b"clave-actual-del-destino-no-debe-borrarse"
    destino.key_path.write_bytes(clave_viva)
    contenido_avr_1 = b"reporte-antiguo-uno"
    contenido_avr_2 = b"reporte-antiguo-dos"
    contenido_indice = b"indice-antiguo-cifrado"
    (destino.reports_dir / "R2026-01.avr").write_bytes(contenido_avr_1)
    (destino.reports_dir / "R2026-02.avr").write_bytes(contenido_avr_2)
    (destino.reports_dir / "index.avridx").write_bytes(contenido_indice)

    resultado = ProfileRestoreService().restaurar(creado.zip_path, destino)

    assert resultado.outcome == "APPLIED"
    assert destino.key_path.read_bytes() == clave_viva
    assert (destino.reports_dir / "R2026-01.avr").read_bytes() == contenido_avr_1
    assert (destino.reports_dir / "R2026-02.avr").read_bytes() == contenido_avr_2
    assert (destino.reports_dir / "index.avridx").read_bytes() == contenido_indice


def test_cripto_caso_c_data_settings_se_restauran_con_cripto_intacta(
    tmp_path: Path,
) -> None:
    """C: backup sin key/reportes -> data/settings se restauran, crypto intacta."""
    origen = build_profile(tmp_path, "origen")
    write_financial_file(origen, "cuentas.json", '{"nuevo": true}')
    creado = crear_backup(origen, tmp_path / "backups")
    contenido_settings_backup = (origen.config_dir / "settings.json").read_bytes()

    destino = build_profile(tmp_path, "destino")
    write_financial_file(destino, "cuentas.json", '{"viejo": true}')
    (destino.config_dir / "settings.json").write_text(
        '{"moneda_principal": "USD"}',
        encoding="utf-8",
    )
    clave_viva = b"clave-actual-del-destino-no-debe-borrarse"
    destino.key_path.write_bytes(clave_viva)

    resultado = ProfileRestoreService().restaurar(creado.zip_path, destino)

    assert resultado.outcome == "APPLIED"
    assert (destino.data_dir / "cuentas.json").read_text() == '{"nuevo": true}'
    assert (destino.config_dir / "settings.json").read_bytes() == (
        contenido_settings_backup
    )
    assert destino.key_path.read_bytes() == clave_viva


def test_cripto_caso_d_reportes_sin_key_bloquea_cero_efectos(
    tmp_path: Path,
) -> None:
    """D: backup con reportes sin key -> bloqueo pre-apply, cero efectos."""
    origen = build_profile(tmp_path, "origen")
    write_financial_file(origen, "cuentas.json", "{}")
    (origen.reports_dir / "R2026-09.avr").write_bytes(b"contenido-huerfano")
    creado = crear_backup(origen, tmp_path / "backups")

    destino = build_profile(tmp_path, "destino")
    clave_viva = b"clave-actual-del-destino-no-debe-borrarse"
    destino.key_path.write_bytes(clave_viva)

    with pytest.raises(RestorePreparationError):
        ProfileRestoreService().preparar(creado.zip_path, destino)

    assert destino.key_path.read_bytes() == clave_viva
    assert list(destino.reports_dir.iterdir()) == []
    assert list(destino.data_dir.iterdir()) == []


def test_cripto_caso_e_key_del_backup_reemplaza_y_reportes_viejos_se_eliminan(
    tmp_path: Path,
) -> None:
    """E: backup con key sin reportes -> key del backup queda, reportes viejos fuera."""
    origen = build_profile(tmp_path, "origen")
    write_financial_file(origen, "cuentas.json", "{}")
    clave_nueva = clave_plain()
    origen.key_path.write_bytes(clave_nueva)
    creado = crear_backup(origen, tmp_path / "backups")
    assert creado.manifest.key_policy.includes_reporte_key is True

    destino = build_profile(tmp_path, "destino")
    write_financial_file(destino, "cuentas.json", "{}")
    destino.key_path.write_bytes(b"clave-vieja-del-destino")
    (destino.reports_dir / "R2026-01.avr").write_bytes(b"reporte-viejo")
    (destino.reports_dir / "index.avridx").write_bytes(b"indice-viejo")

    resultado = ProfileRestoreService().restaurar(creado.zip_path, destino)

    assert resultado.outcome == "APPLIED"
    assert destino.key_path.read_bytes() == clave_nueva
    assert not (destino.reports_dir / "R2026-01.avr").exists()
    assert not (destino.reports_dir / "index.avridx").exists()


def test_cripto_caso_f_solo_permanecen_reportes_definidos_por_backup(
    tmp_path: Path,
) -> None:
    """F: backup con key + subconjunto de reportes -> solo esos sobreviven."""
    origen = build_profile(tmp_path, "origen")
    write_financial_file(origen, "cuentas.json", "{}")
    clave = clave_plain()
    origen.key_path.write_bytes(clave)
    (origen.reports_dir / "R2026-09.avr").write_bytes(reporte_cifrado(clave))
    (origen.reports_dir / "index.avridx").write_bytes(indice_cifrado(clave))
    creado = crear_backup(origen, tmp_path / "backups")

    destino = build_profile(tmp_path, "destino")
    write_financial_file(destino, "cuentas.json", "{}")
    destino.key_path.write_bytes(b"clave-vieja-del-destino")
    (destino.reports_dir / "R2026-01.avr").write_bytes(b"reporte-adicional-viejo")
    (destino.reports_dir / "R2026-09.avr").write_bytes(b"sera-sobrescrito")

    resultado = ProfileRestoreService().restaurar(creado.zip_path, destino)

    assert resultado.outcome == "APPLIED"
    restantes = sorted(p.name for p in destino.reports_dir.iterdir())
    assert restantes == ["R2026-09.avr", "index.avridx"]
    assert destino.key_path.read_bytes() == clave


def test_cripto_caso_g_fallo_en_modo_b_revierte_unidad_completa(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """G: un fallo durante Modo B revierte key/reportes/index originales."""
    origen = build_profile(tmp_path, "origen")
    write_financial_file(origen, "cuentas.json", "{}")
    clave_nueva = clave_plain()
    origen.key_path.write_bytes(clave_nueva)
    (origen.reports_dir / "R2026-09.avr").write_bytes(reporte_cifrado(clave_nueva))
    (origen.reports_dir / "index.avridx").write_bytes(indice_cifrado(clave_nueva))
    creado = crear_backup(origen, tmp_path / "backups")

    destino = build_profile(tmp_path, "destino")
    write_financial_file(destino, "cuentas.json", "{}")
    clave_vieja = b"clave-vieja-original-del-destino"
    destino.key_path.write_bytes(clave_vieja)
    indice_viejo = b"indice-viejo-original"
    (destino.reports_dir / "index.avridx").write_bytes(indice_viejo)

    service = ProfileRestoreService()
    plan = service.preparar(creado.zip_path, destino)

    original = type(service)._aplicar_entrada
    contador = {"n": 0}

    def falla_al_final(self, entry, plan, _contador=contador):
        _contador["n"] += 1
        if _contador["n"] == len(plan.entries):
            raise OSError("fallo simulado en la ultima entrada de modo B")
        return original(self, entry, plan)

    monkeypatch.setattr(type(service), "_aplicar_entrada", falla_al_final)
    resultado = service.aplicar(plan)

    assert resultado.outcome == "FAILED_ROLLBACK_OK"
    assert destino.key_path.read_bytes() == clave_vieja
    assert (destino.reports_dir / "index.avridx").read_bytes() == indice_viejo
    assert not (destino.reports_dir / "R2026-09.avr").exists()


# ---------------------------------------------------------------------------
# Corrección focal — directorios creados: limpieza también en rollback
# ---------------------------------------------------------------------------


def test_directorio_nuevo_desaparece_tras_rollback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """1-4: WRITE crea subdirectorio, falla posterior, rollback lo deja vacío y lo elimina."""
    origen = build_profile(tmp_path, "origen")
    sub = origen.data_dir / "aaa_subdir_nuevo"
    sub.mkdir()
    (sub / "archivo_a.json").write_text("{}", encoding="utf-8")
    write_financial_file(origen, "zzz_archivo_b.json", "{}")
    creado = crear_backup(origen, tmp_path / "backups")

    destino = build_profile(tmp_path, "destino")
    assert not (destino.data_dir / "aaa_subdir_nuevo").exists()

    service = ProfileRestoreService()
    plan = service.preparar(creado.zip_path, destino)
    original = type(service)._aplicar_entrada
    contador = {"n": 0}

    def falla_en_la_segunda(self, entry, plan, _contador=contador):
        _contador["n"] += 1
        if _contador["n"] == 2:
            raise OSError("fallo simulado")
        return original(self, entry, plan)

    monkeypatch.setattr(type(service), "_aplicar_entrada", falla_en_la_segunda)
    resultado = service.aplicar(plan)

    assert resultado.outcome == "FAILED_ROLLBACK_OK"
    assert not (destino.data_dir / "aaa_subdir_nuevo").exists()
    assert not (destino.data_dir / "aaa_subdir_nuevo" / "archivo_a.json").exists()


def test_directorio_preexistente_nunca_se_elimina(tmp_path: Path) -> None:
    """5: un directorio que ya existía antes del restore nunca se elimina.

    Un directorio que el perfil ya tenía (no creado por esta restauración)
    nunca entra en `created_dirs`: aunque el DELETE de un archivo
    administrado en su interior lo deje vacío, el directorio en sí
    permanece, porque la limpieza solo actúa sobre directorios que la
    propia operación creó.
    """
    origen = build_profile(tmp_path, "origen")
    write_financial_file(origen, "cuentas.json", "{}")
    creado = crear_backup(origen, tmp_path / "backups")

    destino = build_profile(tmp_path, "destino")
    write_financial_file(destino, "cuentas.json", "{}")
    (destino.data_dir / "existente").mkdir()
    archivo_viejo = destino.data_dir / "existente" / "archivo_viejo.json"
    archivo_viejo.write_text('{"obsoleto": true}', encoding="utf-8")

    resultado = ProfileRestoreService().restaurar(creado.zip_path, destino)

    assert resultado.outcome == "APPLIED"
    assert not archivo_viejo.exists()
    assert (destino.data_dir / "existente").exists()


def test_directorio_creado_con_contenido_externo_no_se_vacia(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """6: un directorio nuevo con contenido externo inesperado no se vacía ni se borra."""
    origen = build_profile(tmp_path, "origen")
    sub = origen.data_dir / "aaa_subdir_nuevo"
    sub.mkdir()
    (sub / "archivo_a.json").write_text("{}", encoding="utf-8")
    write_financial_file(origen, "zzz_archivo_b.json", "{}")
    creado = crear_backup(origen, tmp_path / "backups")

    destino = build_profile(tmp_path, "destino")

    service = ProfileRestoreService()
    plan = service.preparar(creado.zip_path, destino)
    original = type(service)._aplicar_entrada
    contador = {"n": 0}
    marcador_externo = destino.data_dir / "aaa_subdir_nuevo" / "externo.txt"

    def falla_y_contamina(self, entry, plan, _contador=contador):
        _contador["n"] += 1
        resultado = original(self, entry, plan)
        if _contador["n"] == 1:
            # Algo externo deposita un archivo inesperado en el directorio
            # recien creado, justo despues de que la primera entrada (la que
            # vive en ese subdirectorio) se aplique con exito.
            marcador_externo.write_text("externo-inesperado", encoding="utf-8")
        if _contador["n"] == 2:
            raise OSError("fallo simulado tras la contaminacion externa")
        return resultado

    monkeypatch.setattr(type(service), "_aplicar_entrada", falla_y_contamina)
    resultado = service.aplicar(plan)

    assert resultado.outcome == "FAILED_ROLLBACK_FAILED"
    assert marcador_externo.exists()
    assert marcador_externo.read_text() == "externo-inesperado"
    assert resultado.staging_dir is not None


def test_nunca_se_invoca_rmtree_sobre_el_perfil() -> None:
    """7: el módulo nunca usa shutil.rmtree sobre nada dentro del perfil real.

    `shutil.rmtree` solo debe aparecer aplicado a `staging_dir` (el propio
    directorio de staging, fuera del perfil administrado), nunca sobre una
    ruta derivada de `profile`/`target`/`entry`.
    """
    import inspect

    import services.profile_restore_service as modulo

    codigo_fuente = inspect.getsource(modulo)
    llamadas_rmtree = [
        linea.strip()
        for linea in codigo_fuente.splitlines()
        if "rmtree(" in linea
    ]
    assert llamadas_rmtree, "se esperaba al menos una llamada a rmtree"
    for linea in llamadas_rmtree:
        assert "staging_dir" in linea
