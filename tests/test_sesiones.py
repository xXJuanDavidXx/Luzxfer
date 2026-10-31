"""Tests de sesiones: directorio de datos, validacion de nombres y listado.

El historial de un pentest es evidencia. Perderlo al salir, o escribirlo
donde no se pidio, son los dos fallos que estos tests existen para evitar.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from luzxfer.core import sesiones


# ------------------------------------------------------- directorio de datos
def test_dir_datos_respeta_xdg(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    assert sesiones.dir_datos() == tmp_path / "luzxfer"
    assert sesiones.dir_sesiones() == tmp_path / "luzxfer" / "sesiones"


def test_dir_datos_cae_a_local_share_sin_xdg(monkeypatch):
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    assert sesiones.dir_datos() == Path.home() / ".local" / "share" / "luzxfer"


def test_dir_datos_ignora_xdg_relativo(monkeypatch):
    # un XDG_DATA_HOME relativo no es valido segun la especificacion
    monkeypatch.setenv("XDG_DATA_HOME", "datos/aqui")
    assert sesiones.dir_datos() == Path.home() / ".local" / "share" / "luzxfer"


def test_dir_datos_no_crea_nada(monkeypatch, tmp_path):
    """Consultar donde van las sesiones no debe tener efectos."""
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    sesiones.dir_datos()
    sesiones.dir_sesiones()
    assert list(tmp_path.iterdir()) == []


# ----------------------------------------------------- validacion de nombres
def test_valida_nombre_acepta_lo_razonable():
    assert sesiones.valida_nombre("cliente-x") == "cliente-x"
    assert sesiones.valida_nombre("  lab_dvwa  ") == "lab_dvwa"
    assert sesiones.valida_nombre("2026-10-31.tarde") == "2026-10-31.tarde"


@pytest.mark.parametrize("malo", [
    "../../etc/passwd",      # traversal clasico
    "..",
    ".oculta",
    "cliente/x",
    "cliente\\x",
    "con\x00nulo",
    "con espacio",
    "",
    "   ",
    "a" * 65,
])
def test_valida_nombre_rechaza_lo_peligroso(malo):
    with pytest.raises(sesiones.NombreInvalido):
        sesiones.valida_nombre(malo)


def test_el_error_de_nombre_explica_que_se_permite():
    """Lo va a leer alguien en una terminal, no un depurador."""
    with pytest.raises(sesiones.NombreInvalido) as e:
        sesiones.valida_nombre("cliente/x")
    assert "nombre de sesion" in str(e.value).lower()


def test_ruta_de_nunca_sale_del_directorio(monkeypatch, tmp_path):
    """Review Focus 1: un nombre no puede escribir fuera de dir_sesiones()."""
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    base = sesiones.dir_sesiones().resolve()
    for nombre in ("cliente-x", "lab_dvwa", "a" * 64):
        assert sesiones.ruta_de(nombre).resolve().parent == base
    for malo in ("../fuera", "/etc/passwd", "sub/dir"):
        with pytest.raises(sesiones.NombreInvalido):
            sesiones.ruta_de(malo)


def test_ruta_de_usa_la_extension_db(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    assert sesiones.ruta_de("cliente-x").name == "cliente-x.db"


def test_hay_un_nombre_por_defecto_y_es_valido():
    assert sesiones.valida_nombre(sesiones.NOMBRE_DEFECTO) == sesiones.NOMBRE_DEFECTO
