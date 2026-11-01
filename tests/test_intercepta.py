"""Tests de la interceptacion.

Esta es la pieza que cruza hilos: el motor se bloquea esperando a que la
interfaz decida, y la interfaz vive en otro bucle. Casi todo lo que se
prueba aqui es «que no se quede nadie colgado»:

  - si la interfaz no contesta, el motor sigue solo al cabo del timeout;
  - si la interceptacion se apaga, lo detenido sale de inmediato;
  - si la aplicacion cierra, nada queda esperando para siempre.

Y una regla que manda sobre todas: ante la duda, la peticion SALE. Perder
trafico del analista en silencio es peor que dejar pasar algo.
"""
from __future__ import annotations

import threading
import time

from luzxfer.core.tools import intercepta

CRUDO = "GET /x HTTP/1.1\r\nHost: o.com\r\n\r\n"


def _en_hilo(fn):
    caja = {}
    h = threading.Thread(target=lambda: caja.update(r=fn()), daemon=True)
    h.start()
    return caja, h


# ------------------------------------------------------- apagada, no estorba
def test_apagada_deja_pasar_sin_tocar_nada():
    i = intercepta.Interceptor()
    assert i.activa is False
    t = time.time()
    assert i.detener(CRUDO) == CRUDO
    assert time.time() - t < 0.05, "no debe bloquear ni un instante"
    assert i.pendientes() == []


# ------------------------------------------------------------ soltar
def test_encendida_detiene_hasta_que_se_suelta():
    i = intercepta.Interceptor()
    i.activa = True
    caja, h = _en_hilo(lambda: i.detener(CRUDO))

    for _ in range(100):
        if i.pendientes():
            break
        time.sleep(0.01)
    assert len(i.pendientes()) == 1
    assert "r" not in caja, "el motor sigue esperando, como debe"

    i.resolver(i.pendientes()[0].id, "soltar")
    h.join(timeout=3)
    assert caja["r"] == CRUDO
    assert i.pendientes() == []


def test_soltar_editada_manda_lo_editado():
    i = intercepta.Interceptor()
    i.activa = True
    caja, h = _en_hilo(lambda: i.detener(CRUDO))
    while not i.pendientes():
        time.sleep(0.01)

    editado = "GET /x?inyectado=1 HTTP/1.1\r\nHost: o.com\r\n\r\n"
    i.resolver(i.pendientes()[0].id, "soltar", editado)
    h.join(timeout=3)
    assert caja["r"] == editado


# --------------------------------------------------------- descartar
def test_descartar_devuelve_none_y_el_motor_no_manda_nada():
    i = intercepta.Interceptor()
    i.activa = True
    caja, h = _en_hilo(lambda: i.detener(CRUDO))
    while not i.pendientes():
        time.sleep(0.01)

    i.resolver(i.pendientes()[0].id, "descartar")
    h.join(timeout=3)
    assert caja["r"] is None


# ------------------------------------------------- nadie se queda colgado
def test_si_nadie_contesta_la_peticion_sale_al_cabo_del_timeout():
    """Ante la duda, SALE. Que el navegador se quede colgado para siempre
    porque el analista se fue a comer es peor que dejar pasar algo."""
    i = intercepta.Interceptor(timeout=0.3)
    i.activa = True
    t = time.time()
    assert i.detener(CRUDO) == CRUDO
    tardo = time.time() - t
    assert 0.25 < tardo < 2.0
    assert i.pendientes() == []


def test_apagar_la_interceptacion_suelta_todo_lo_detenido():
    i = intercepta.Interceptor()
    i.activa = True
    cajas = [_en_hilo(lambda: i.detener(CRUDO)) for _ in range(3)]
    while len(i.pendientes()) < 3:
        time.sleep(0.01)

    i.activa = False
    i.soltar_todas()
    for caja, h in cajas:
        h.join(timeout=3)
        assert caja["r"] == CRUDO
    assert i.pendientes() == []


def test_cerrar_suelta_todo_y_deja_de_detener():
    """Al cerrar la aplicacion no puede quedar un hilo del motor
    esperando una decision que ya no va a llegar nunca."""
    i = intercepta.Interceptor()
    i.activa = True
    caja, h = _en_hilo(lambda: i.detener(CRUDO))
    while not i.pendientes():
        time.sleep(0.01)

    i.cerrar()
    h.join(timeout=3)
    assert caja["r"] == CRUDO
    assert i.detener(CRUDO) == CRUDO       # ya no detiene nada mas


# ------------------------------------------------------------- varias
def test_varias_a_la_vez_se_resuelven_cada_una_por_su_lado():
    i = intercepta.Interceptor()
    i.activa = True
    crudos = [f"GET /r{n} HTTP/1.1\r\nHost: o.com\r\n\r\n" for n in range(3)]
    cajas = [_en_hilo(lambda c=c: i.detener(c)) for c in crudos]
    while len(i.pendientes()) < 3:
        time.sleep(0.01)

    por_ruta = {p.crudo: p for p in i.pendientes()}
    i.resolver(por_ruta[crudos[1]].id, "descartar")
    i.resolver(por_ruta[crudos[0]].id, "soltar")
    i.resolver(por_ruta[crudos[2]].id, "soltar", "GET /otro HTTP/1.1\r\n\r\n")

    for _caja, h in cajas:
        h.join(timeout=3)
    assert cajas[0][0]["r"] == crudos[0]
    assert cajas[1][0]["r"] is None
    assert cajas[2][0]["r"] == "GET /otro HTTP/1.1\r\n\r\n"


def test_llegan_en_orden_de_llegada():
    i = intercepta.Interceptor()
    i.activa = True
    for n in range(3):
        _en_hilo(lambda n=n: i.detener(f"GET /r{n} HTTP/1.1\r\n\r\n"))
        while len(i.pendientes()) < n + 1:
            time.sleep(0.01)
    assert [p.crudo.split()[1] for p in i.pendientes()] == ["/r0", "/r1", "/r2"]


# ----------------------------------------------------------- avisos
def test_avisa_a_la_interfaz_cuando_detiene_algo():
    vistas = []
    i = intercepta.Interceptor(al_detener=vistas.append)
    i.activa = True
    _, h = _en_hilo(lambda: i.detener(CRUDO))
    for _ in range(100):
        if vistas:
            break
        time.sleep(0.01)
    assert len(vistas) == 1 and vistas[0].crudo == CRUDO
    i.soltar_todas()
    h.join(timeout=3)


def test_un_aviso_que_revienta_no_tumba_el_proxy():
    """El consumidor del aviso vive en otro hilo y puede fallar. Si eso
    se llevara por delante la peticion, un fallo de pintado cortaria el
    trafico del analista."""
    def explota(_):
        raise RuntimeError("boom")

    i = intercepta.Interceptor(al_detener=explota, timeout=0.3)
    i.activa = True
    assert i.detener(CRUDO) == CRUDO


def test_resolver_algo_que_ya_no_esta_no_revienta():
    i = intercepta.Interceptor()
    i.resolver(9999, "soltar")
    i.resolver(9999, "descartar", "lo que sea")


# ------------------------------------------- el motor, parando de verdad
def _por_proxy(eco, peticion: bytes, interceptor=None, espera=10):
    """Manda una peticion por un proxy recien levantado y devuelve lo que
    vio el servidor de eco, o None si no llego nada."""
    import http.client
    import json
    import socket

    from luzxfer.core.engine import Builtin
    h, p = eco
    m = Builtin(lambda f: None, port=0, upstream=f"http://{h}:{p}",
                interceptor=interceptor)
    m.start()
    puerto = m._srv.server_address[1]
    try:
        s = socket.create_connection(("127.0.0.1", puerto), timeout=espera)
        s.sendall(peticion)
        r = http.client.HTTPResponse(s)
        try:
            r.begin()
            cuerpo = r.read()
        except Exception:
            return None            # el proxy corto: la peticion se descarto
        finally:
            s.close()
        return json.loads(cuerpo)
    finally:
        m.stop()


PETICION = b"GET /eco?q=original HTTP/1.1\r\nHost: x\r\nConnection: close\r\n\r\n"


def test_sin_interceptor_el_proxy_funciona_igual(eco):
    datos = _por_proxy(eco, PETICION)
    assert datos["ruta"] == "/eco?q=original"


def test_interceptor_apagado_no_cambia_nada(eco):
    i = intercepta.Interceptor()
    datos = _por_proxy(eco, PETICION, interceptor=i)
    assert datos["ruta"] == "/eco?q=original"


def test_soltar_sin_tocar_manda_la_original(eco):
    i = intercepta.Interceptor()
    i.activa = True
    threading.Thread(target=_resolver_cuando_llegue, args=(i, SOLTAR_TAL_CUAL),
                     daemon=True).start()
    datos = _por_proxy(eco, PETICION, interceptor=i)
    assert datos["ruta"] == "/eco?q=original"


def test_editar_en_vuelo_cambia_lo_que_ve_el_servidor(eco):
    """La razon de ser de todo esto: el servidor NUNCA ve la original."""
    i = intercepta.Interceptor()
    i.activa = True

    def editar(crudo):
        return crudo.replace("q=original", "q=EDITADO")

    threading.Thread(target=_resolver_cuando_llegue, args=(i, editar),
                     daemon=True).start()
    datos = _por_proxy(eco, PETICION, interceptor=i)
    assert datos["ruta"] == "/eco?q=EDITADO"


def test_descartar_no_deja_llegar_nada_al_servidor(eco):
    i = intercepta.Interceptor()
    i.activa = True
    threading.Thread(target=_resolver_cuando_llegue, args=(i, None),
                     daemon=True).start()
    assert _por_proxy(eco, PETICION, interceptor=i) is None


def test_editar_el_cuerpo_recalcula_el_content_length(eco):
    """Mismo error numero uno del repeater: editas el cuerpo a mano y el
    Content-Length viejo deja al servidor esperando bytes que no llegan."""
    i = intercepta.Interceptor()
    i.activa = True

    def alargar(crudo):
        return crudo.replace("q=1", "q=muchisimo-mas-largo-que-antes")

    threading.Thread(target=_resolver_cuando_llegue, args=(i, alargar),
                     daemon=True).start()
    peticion = (b"POST /eco HTTP/1.1\r\nHost: x\r\n"
                b"Content-Type: application/x-www-form-urlencoded\r\n"
                b"Content-Length: 3\r\nConnection: close\r\n\r\nq=1")
    datos = _por_proxy(eco, peticion, interceptor=i)
    assert datos["cuerpo"] == "q=muchisimo-mas-largo-que-antes"


def test_editar_el_host_no_cambia_a_donde_va(eco):
    """Es deliberado: asi se prueba inyeccion por Host header. Cambiar a
    donde va una peticion del navegador a mitad de vuelo seria otra cosa
    y bastante mas sorprendente."""
    i = intercepta.Interceptor()
    i.activa = True

    def cambiar_host(crudo):
        import re
        return re.sub(r"Host: [^\r\n]*", "Host: inyectado.malvado.com", crudo)

    threading.Thread(target=_resolver_cuando_llegue, args=(i, cambiar_host),
                     daemon=True).start()
    datos = _por_proxy(eco, PETICION, interceptor=i)
    assert datos is not None, "llego al servidor de eco, no al host inventado"
    assert any(k.lower() == "host" and v == "inyectado.malvado.com"
               for k, v in datos["cabeceras"])


def test_una_peticion_rara_editada_a_mano_viaja_tal_cual(eco):
    """Lo que escribes es lo que viaja, tambien aqui.

    Este test nacio al reves —«ante la duda, sale la original»— y estaba
    mal: romper una peticion a proposito es una tecnica, no un dedazo.
    Probar diferencias de parser o request smuggling exige que la
    porqueria llegue tal cual. Una herramienta que te arregla la
    peticion no sirve para ver que hace el servidor con la rota."""
    i = intercepta.Interceptor()
    i.activa = True
    threading.Thread(
        target=_resolver_cuando_llegue,
        args=(i, lambda c: c.replace("GET /eco?q=original HTTP/1.1",
                                     "GET /eco?q=raro HTTP/9.9")),
        daemon=True).start()
    datos = _por_proxy(eco, PETICION, interceptor=i)
    assert datos["ruta"] == "/eco?q=raro"


def test_una_edicion_que_no_se_puede_leer_manda_la_original(eco):
    """La excepcion a lo anterior: si no queda NADA que interpretar no
    hay nada que mandar, y tragarse el trafico en silencio seria peor
    que dejar salir lo que ya habia."""
    i = intercepta.Interceptor()
    i.activa = True
    threading.Thread(target=_resolver_cuando_llegue, args=(i, lambda c: ""),
                     daemon=True).start()
    datos = _por_proxy(eco, PETICION, interceptor=i)
    assert datos["ruta"] == "/eco?q=original"


SOLTAR_TAL_CUAL = object()


def _resolver_cuando_llegue(i, que_hacer, espera=8.0):
    """Espera a que algo se detenga y lo resuelve. None = descartar."""
    limite = time.time() + espera
    while time.time() < limite:
        pend = i.pendientes()
        if pend:
            d = pend[0]
            if que_hacer is None:
                i.resolver(d.id, intercepta.DESCARTAR)
            elif que_hacer is SOLTAR_TAL_CUAL:
                i.resolver(d.id, intercepta.SOLTAR)
            else:
                i.resolver(d.id, intercepta.SOLTAR, que_hacer(d.crudo))
            return
        time.sleep(0.01)
