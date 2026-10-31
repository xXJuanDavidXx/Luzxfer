"""Tests de sesiones: directorio de datos, validacion de nombres y listado.

El historial de un pentest es evidencia. Perderlo al salir, o escribirlo
donde no se pidio, son los dos fallos que estos tests existen para evitar.
"""
from __future__ import annotations

import sqlite3
import time
from pathlib import Path

import pytest

from luzxfer.core import sesiones
from luzxfer.core.models import Flow, Request, Response
from luzxfer.core.store import Store


def _sesion(nombre: str, n_flujos: int = 0) -> Path:
    """Crea una sesion de verdad en el directorio, con n flujos dentro."""
    ruta = sesiones.ruta_de(nombre)
    st = Store(ruta)
    for i in range(n_flujos):
        st.add_flow(Flow(
            request=Request(method="GET", url=f"http://ej.com/{i}",
                            headers=[("Host", "ej.com")]),
            response=Response(status=200, body=b"x"),
        ))
    st.close()
    return ruta


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


# --------------------------------------------------------------- listado
def test_listar_vacio_si_no_existe_el_directorio(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "nada"))
    assert sesiones.listar() == []


def test_listar_devuelve_nombre_y_contadores(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    _sesion("cliente-x", n_flujos=3)
    r = sesiones.listar()
    assert len(r) == 1
    assert r[0].nombre == "cliente-x"
    assert r[0].flujos == 3
    assert r[0].ilegible is False


def test_listar_cuenta_tambien_los_candidatos(monkeypatch, tmp_path):
    from luzxfer.core.models import Finding

    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    ruta = _sesion("con-hallazgos", n_flujos=1)
    st = Store(ruta)
    st.add_finding(Finding(kind="FUGA", detail="server: nginx", url="ej.com"))
    st.close()
    assert sesiones.listar()[0].candidatos == 1


def test_listar_ordena_por_mas_reciente(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    _sesion("vieja", n_flujos=1)
    time.sleep(0.02)
    _sesion("nueva", n_flujos=1)
    assert [s.nombre for s in sesiones.listar()] == ["nueva", "vieja"]


def test_un_db_corrupto_sale_como_ilegible_y_no_revienta(monkeypatch, tmp_path):
    """Review Focus 2: cualquiera puede copiar un archivo al directorio."""
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    _sesion("buena", n_flujos=2)
    sesiones.dir_sesiones().joinpath("basura.db").write_bytes(b"esto no es sqlite")

    r = {s.nombre: s for s in sesiones.listar()}
    assert r["basura"].ilegible is True
    assert r["basura"].flujos == 0
    assert r["buena"].ilegible is False and r["buena"].flujos == 2


def test_listar_ignora_lo_que_no_sea_db(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    _sesion("real", n_flujos=1)
    sesiones.dir_sesiones().joinpath("notas.txt").write_text("hola")
    assert [s.nombre for s in sesiones.listar()] == ["real"]


def test_listar_no_crea_ni_modifica_la_sesion(monkeypatch, tmp_path):
    """Abrir en solo lectura: listar no debe tocar el archivo."""
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    ruta = _sesion("intacta", n_flujos=1)
    antes = ruta.stat().st_mtime_ns
    contenido = ruta.read_bytes()
    sesiones.listar()
    assert ruta.stat().st_mtime_ns == antes
    assert ruta.read_bytes() == contenido


def test_dos_instancias_sobre_la_misma_sesion_dan_error_visible(monkeypatch, tmp_path):
    """Review Focus 5: mejor un error de SQLite que corrupcion callada.

    Store acepta un timeout para que esto no tarde los 5 s del busy
    timeout por defecto de sqlite3. Ese parametro tambien sirve en la TUI:
    _ingresar() escribe desde el bucle de la interfaz, y cinco segundos
    bloqueado ahi son cinco segundos de interfaz congelada.
    """
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    ruta = sesiones.ruta_de("compartida")
    a = Store(ruta)
    b = Store(ruta, timeout=0.1)
    con = sqlite3.connect(ruta, isolation_level=None)
    con.execute("BEGIN EXCLUSIVE")
    try:
        with pytest.raises(sqlite3.Error):
            b.add_flow(Flow(request=Request(method="GET", url="http://ej.com/",
                                            headers=[("Host", "ej.com")])))
    finally:
        con.close()
        a.close()
        b.close()


def test_borrar_quita_el_db_y_sus_auxiliares(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    ruta = _sesion("temporal", n_flujos=1)
    sesiones.borrar("temporal")
    assert not ruta.exists()
    assert not ruta.with_suffix(".db-wal").exists()
    sesiones.borrar("temporal")          # idempotente, no lanza


def test_borrar_valida_el_nombre(monkeypatch, tmp_path):
    """Borrar es destructivo: con mas razon no acepta rutas raras."""
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    with pytest.raises(sesiones.NombreInvalido):
        sesiones.borrar("../algo")


def test_listar_funciona_con_el_directorio_de_solo_lectura(monkeypatch, tmp_path):
    """Asi se guarda evidencia: en un medio que no se puede escribir.

    Leer una base WAL necesita crear -shm, que ahi es imposible. Sin el
    respaldo con immutable=1, toda sesion sana saldria como ilegible, que
    es una mentira peor que no poder leerla.
    """
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    _sesion("evidencia", n_flujos=4)
    base = sesiones.dir_sesiones()
    base.chmod(0o500)
    try:
        r = sesiones.listar()
        assert len(r) == 1
        assert r[0].nombre == "evidencia"
        assert r[0].ilegible is False
        assert r[0].flujos == 4
    finally:
        base.chmod(0o700)


# ------------------------------------------------- retomar la ultima sesion
def test_abrir_sin_nombre_usa_el_default_la_primera_vez(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    nombre, ruta = sesiones.abrir(None)
    assert nombre == sesiones.NOMBRE_DEFECTO
    assert ruta.parent.is_dir()
    assert ruta.name == f"{sesiones.NOMBRE_DEFECTO}.db"


def test_abrir_no_crea_el_archivo_todavia(monkeypatch, tmp_path):
    """Crear el .db es de Store al conectarse, no de abrir()."""
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    _, ruta = sesiones.abrir("nueva")
    assert not ruta.exists()


def test_abrir_recuerda_y_retoma_la_ultima(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    sesiones.abrir("cliente-x")
    _sesion("cliente-x")                              # que exista en disco
    assert sesiones.ultima() == "cliente-x"
    assert sesiones.abrir(None)[0] == "cliente-x"


def test_un_nombre_explicito_gana_sobre_la_ultima(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    sesiones.abrir("cliente-x")
    _sesion("cliente-x")
    assert sesiones.abrir("lab-dvwa")[0] == "lab-dvwa"
    _sesion("lab-dvwa")
    assert sesiones.ultima() == "lab-dvwa"


def test_abrir_rechaza_un_nombre_invalido(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    with pytest.raises(sesiones.NombreInvalido):
        sesiones.abrir("../fuera")


def test_ultima_borrada_no_rompe_el_arranque(monkeypatch, tmp_path):
    """Review Focus 3: el puntero sobrevive a la sesion que nombra."""
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    sesiones.abrir("efimera")
    _sesion("efimera")
    sesiones.borrar("efimera")
    assert sesiones.ultima() is None
    assert sesiones.abrir(None)[0] == sesiones.NOMBRE_DEFECTO


def test_ultima_con_contenido_basura_se_ignora(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    sesiones.dir_datos().mkdir(parents=True, exist_ok=True)
    (sesiones.dir_datos() / "ultima").write_text("../../etc/passwd")
    assert sesiones.ultima() is None


def test_ultima_tolera_el_salto_de_linea(monkeypatch, tmp_path):
    """Un echo > ultima deja un \\n y no por eso se pierde la sesion."""
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    _sesion("cliente-x")
    (sesiones.dir_datos() / "ultima").write_text("cliente-x\n")
    assert sesiones.ultima() == "cliente-x"


def test_ultima_sin_puntero_es_none(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    assert sesiones.ultima() is None


# --------------------------------------------------------------------- CLI
def test_cli_nombre_invalido_sale_con_2_y_mensaje(monkeypatch, tmp_path, capsys):
    from luzxfer.__main__ import main

    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    assert main(["-s", "../fuera", "--no-engine"]) == 2
    assert "nombre de sesion" in capsys.readouterr().err.lower()


def test_cli_directorio_no_escribible_explica_y_no_revienta(monkeypatch, tmp_path, capsys):
    """Review Focus 4: mensaje claro, no un traceback."""
    from luzxfer.__main__ import main

    bloqueado = tmp_path / "bloqueado"
    bloqueado.mkdir()
    bloqueado.chmod(0o500)
    monkeypatch.setenv("XDG_DATA_HOME", str(bloqueado))
    try:
        assert main(["--no-engine"]) == 2
        assert "no se pudo" in capsys.readouterr().err.lower()
    finally:
        bloqueado.chmod(0o700)


def test_cli_sesiones_lista_y_sale(monkeypatch, tmp_path, capsys):
    from luzxfer.__main__ import main

    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    _sesion("cliente-x", n_flujos=2)
    assert main(["--sesiones"]) == 0
    salida = capsys.readouterr().out
    assert "cliente-x" in salida and "2" in salida


def test_cli_sesiones_sin_ninguna_lo_dice(monkeypatch, tmp_path, capsys):
    from luzxfer.__main__ import main

    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    assert main(["--sesiones"]) == 0
    assert "no hay sesiones" in capsys.readouterr().out.lower()


def test_cli_sesiones_marca_la_ilegible(monkeypatch, tmp_path, capsys):
    from luzxfer.__main__ import main

    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    _sesion("buena", n_flujos=1)
    sesiones.dir_sesiones().joinpath("rota.db").write_bytes(b"no soy sqlite")
    assert main(["--sesiones"]) == 0
    assert "ilegible" in capsys.readouterr().out.lower()
