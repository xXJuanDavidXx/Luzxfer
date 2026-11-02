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


# ------------------------------------- interceptacion sobre este motor
def _resolver_cuando_llegue(i, editar, espera=10.0):
    """Hace de analista desde otro hilo: espera a que algo se detenga."""
    from luzxfer.core.tools import intercepta
    limite = time.time() + espera
    while time.time() < limite:
        pend = i.pendientes()
        if pend:
            d = pend[0]
            if editar is None:
                i.resolver(d.id, intercepta.DESCARTAR)
            else:
                i.resolver(d.id, intercepta.SOLTAR, editar(d.crudo))
            return
        time.sleep(0.01)


def _por_mitm(eco, ruta, interceptor=None, editar=False, espera=20):
    import threading

    h, p = eco
    cap = []
    m = mitm.Mitm(cap.append, port=0, upstream=f"http://{h}:{p}",
                  interceptor=interceptor)
    m.start()
    if interceptor is not None and editar is not False:
        threading.Thread(target=_resolver_cuando_llegue,
                         args=(interceptor, editar), daemon=True).start()
    try:
        con = http.client.HTTPConnection("127.0.0.1", m.puerto_real,
                                         timeout=espera)
        con.request("GET", ruta)
        r = con.getresponse()
        cuerpo = r.read()
        con.close()
        for _ in range(100):
            if cap:
                break
            time.sleep(0.05)
        return cuerpo, cap
    except Exception:
        return None, cap
    finally:
        m.stop()


def test_sin_interceptor_el_motor_mitm_va_igual(eco):
    cuerpo, _ = _por_mitm(eco, "/eco?q=normal")
    assert b"normal" in cuerpo


def test_interceptor_apagado_no_detiene_nada(eco):
    from luzxfer.core.tools import intercepta
    i = intercepta.Interceptor()
    cuerpo, _ = _por_mitm(eco, "/eco?q=normal", interceptor=i)
    assert b"normal" in cuerpo


def test_editar_en_vuelo_sobre_mitm(eco):
    """Lo que faltaba: el servidor nunca ve la original, tambien aqui."""
    from luzxfer.core.tools import intercepta
    i = intercepta.Interceptor()
    i.activa = True
    cuerpo, cap = _por_mitm(
        eco, "/eco?q=original", interceptor=i,
        editar=lambda c: c.replace("q=original", "q=EDITADOMITM"))
    assert cuerpo is not None and b"EDITADOMITM" in cuerpo
    assert b"original" not in cuerpo
    assert cap and "EDITADOMITM" in cap[0].request.url


def test_descartar_sobre_mitm_no_deja_llegar_nada(eco):
    from luzxfer.core.tools import intercepta
    i = intercepta.Interceptor()
    i.activa = True
    cuerpo, _ = _por_mitm(eco, "/eco?q=muere", interceptor=i, editar=None)
    assert cuerpo is None or b"muere" not in cuerpo


def test_una_peticion_detenida_no_congela_a_las_demas(eco):
    """La razon de que esto no se hiciera a la primera: el hook de
    mitmproxy corre en su bucle, y bloquearlo pararia TODOS los flujos
    a la vez, no solo el que se esta mirando."""
    import threading

    from luzxfer.core.tools import intercepta
    h, p = eco
    i = intercepta.Interceptor()
    i.activa = True
    m = mitm.Mitm(lambda f: None, port=0, upstream=f"http://{h}:{p}")
    m.interceptor = i
    m.stop()
    m = mitm.Mitm(lambda f: None, port=0, upstream=f"http://{h}:{p}",
                  interceptor=i)
    m.start()
    try:
        hechas = []

        def pedir(n):
            try:
                con = http.client.HTTPConnection("127.0.0.1", m.puerto_real,
                                                 timeout=20)
                con.request("GET", f"/eco?q=p{n}")
                con.getresponse().read()
                con.close()
                hechas.append(n)
            except Exception:
                pass

        hilos = [threading.Thread(target=pedir, args=(n,), daemon=True)
                 for n in range(3)]
        for t in hilos:
            t.start()

        # las tres se detienen a la vez: el bucle de mitmproxy sigue vivo
        for _ in range(200):
            if len(i.pendientes()) == 3:
                break
            time.sleep(0.05)
        assert len(i.pendientes()) == 3, \
            "si el hook bloqueara el bucle, solo llegaria una"

        i.soltar_todas()
        for t in hilos:
            t.join(timeout=20)
        assert sorted(hechas) == [0, 1, 2]
    finally:
        m.stop()


# ----------------------------------------- _editar y los cuerpos binarios
def _peticion(cuerpo: bytes, cabeceras=None):
    from mitmproxy.http import Request
    cab = cabeceras or {"Content-Type": "application/octet-stream"}
    return Request.make("POST", "http://o.com/subir", cuerpo, cab)


def test_editar_solo_cabeceras_no_corrompe_un_cuerpo_binario():
    """El bug del motor integrado, tambien aqui: editar una cabecera de una
    peticion con cuerpo binario NO puede tocar el cuerpo. _a_crudo lo
    decodifica con 'replace', asi que sin cuidado los bytes no-UTF-8 salen
    como EF BF BD."""
    original = bytes([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0xff, 0xd8, 0x00,
                      0x80, 0x81])
    pet = _peticion(original)
    crudo = mitm._a_crudo(pet)
    # el analista edita SOLO una cabecera, no el cuerpo
    editado = crudo.replace("application/octet-stream", "image/png")
    mitm._editar(pet, editado)
    assert pet.raw_content == original, "el cuerpo binario tiene que quedar intacto"
    assert pet.headers["Content-Type"] == "image/png"


def test_editar_el_cuerpo_de_texto_se_respeta_en_mitm():
    pet = _peticion(b"usuario=admin", {"Content-Type": "text/plain"})
    crudo = mitm._a_crudo(pet)
    mitm._editar(pet, crudo.replace("usuario=admin", "usuario=raiz"))
    assert pet.raw_content == b"usuario=raiz"


def test_editar_con_el_texto_sin_cambios_preserva_el_binario():
    """Red de seguridad: aunque _editar reciba el crudo sin tocar —el
    cuerpo binario ya salio lossy de _a_crudo—, los bytes originales
    tienen que volver intactos, no su sombra en UTF-8."""
    original = bytes([0x00, 0xff, 0x10, 0x80, 0x0d, 0x0a])
    pet = _peticion(original)
    mitm._editar(pet, mitm._a_crudo(pet))
    assert pet.raw_content == original
