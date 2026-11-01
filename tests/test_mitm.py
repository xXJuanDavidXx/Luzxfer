"""Tests del motor de mitmproxy.

Se arranca un proxy de verdad y se le manda trafico. Un adaptador
validado solo contra un doble es un adaptador que probablemente no
funciona, y eso ya ha pasado bastantes veces en este proyecto.

Se saltan si el extra no esta instalado: en Termux no se puede, que es
justo el motivo de que sea un extra.
"""
from __future__ import annotations

import http.client
import time

import pytest

from luzxfer.core.engine import mitm

pytestmark = pytest.mark.skipif(not mitm.disponible(),
                                reason="el extra [mitm] no esta instalado")


def test_se_anuncia_con_lo_que_de_verdad_hace():
    i = mitm.Mitm.info()
    assert i.name == "mitmproxy"
    assert i.tls and i.http2 and i.websockets
    assert "TLS" in i.resumen()


def test_cumple_la_interfaz_de_motor():
    """La promesa del primer commit: cambiar de motor es cambiar una
    clase. Si el segundo motor no encaja en la interfaz, la abstraccion
    no valia lo que prometia."""
    from luzxfer.core.engine.base import Engine
    assert issubclass(mitm.Mitm, Engine)
    for metodo in ("start", "stop", "info", "available"):
        assert hasattr(mitm.Mitm, metodo)


def test_captura_trafico_de_verdad(eco):
    h, p = eco
    capturados = []
    m = mitm.Mitm(capturados.append, port=0,
                  upstream=f"http://{h}:{p}")
    m.start()
    try:
        assert m.running
        puerto = m.puerto_real
        con = http.client.HTTPConnection("127.0.0.1", puerto, timeout=15)
        con.request("GET", "/eco?q=porelmitm")
        r = con.getresponse()
        cuerpo = r.read()
        con.close()
        assert r.status == 200 and b"porelmitm" in cuerpo

        for _ in range(100):
            if capturados:
                break
            time.sleep(0.05)
    finally:
        m.stop()

    assert capturados, "no llego ningun flujo a on_flow"
    f = capturados[0]
    assert f.request.method == "GET"
    assert "porelmitm" in f.request.url
    assert f.response is not None and f.response.status == 200
    assert b"porelmitm" in f.response.body


def test_los_flujos_que_produce_valen_para_el_resto_de_la_herramienta(eco):
    """La prueba que importa: el detector tiene que poder analizarlos
    igual que los del motor integrado, sin saber de donde salieron."""
    from luzxfer.core.tools import detector

    h, p = eco
    capturados = []
    m = mitm.Mitm(capturados.append, port=0, upstream=f"http://{h}:{p}")
    m.start()
    try:
        con = http.client.HTTPConnection("127.0.0.1", m.puerto_real, timeout=15)
        con.request("GET", "/refleja?q=REFLEJOPORMITM")
        con.getresponse().read()
        con.close()
        for _ in range(100):
            if capturados:
                break
            time.sleep(0.05)
    finally:
        m.stop()

    assert capturados
    f = capturados[0]
    f.id = 1
    assert any(x.kind == "REFLEJO" for x in detector.analizar(f))


def test_parar_y_arrancar_otra_vez_no_deja_el_hilo_colgado(eco):
    h, p = eco
    m = mitm.Mitm(lambda f: None, port=0, upstream=f"http://{h}:{p}")
    m.start()
    assert m.running
    m.stop()
    assert not m.running
    assert m._hilo is None


def test_parar_sin_haber_arrancado_no_revienta():
    m = mitm.Mitm(lambda f: None, port=0)
    m.stop()
    assert not m.running


# --------------------------------------------------- elegirlo desde fuera
def test_el_cli_acepta_elegir_motor():
    import subprocess
    r = subprocess.run(["./venv/bin/luzxfer", "--help"],
                       capture_output=True, text=True, timeout=30)
    assert "--motor" in r.stdout
    assert "mitm" in r.stdout


async def test_la_app_levanta_el_motor_elegido(eco):
    """El contrato del primer commit, comprobado de verdad: la misma
    aplicacion con otro motor."""
    from luzxfer.tui.app import LuzxferApp
    h, p = eco
    app = LuzxferApp(arrancar_motor=True, motor="mitm", port=0,
                     upstream=f"http://{h}:{p}")
    async with app.run_test() as pilot:
        await pilot.pause()
        assert isinstance(app.engine, mitm.Mitm)
        assert app.engine.running


async def test_por_defecto_sigue_siendo_el_integrado():
    """Lo que mantiene el proyecto instalable en Termux."""
    from luzxfer.core.engine import Builtin
    from luzxfer.tui.app import LuzxferApp
    app = LuzxferApp(arrancar_motor=True, port=0)
    async with app.run_test() as pilot:
        await pilot.pause()
        assert isinstance(app.engine, Builtin)


async def test_pedir_un_motor_que_no_esta_lo_explica(monkeypatch):
    from luzxfer.core.engine import mitm as mod
    from luzxfer.tui.app import LuzxferApp
    monkeypatch.setattr(mod, "disponible", lambda: False)
    app = LuzxferApp(arrancar_motor=True, motor="mitm", port=0)
    async with app.run_test() as pilot:
        await pilot.pause()
        assert app.engine is None or not app.engine.running
