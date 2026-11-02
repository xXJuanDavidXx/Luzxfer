"""Tests del DAST con correa.

Esto es lo unico de la herramienta que origina peticiones por su cuenta
contra un objetivo, asi que la mitad de los tests no son sobre que
encuentra sino sobre que NO hace: no sale del alcance, no dispara solo,
no confirma nada, y no pasa del ritmo que se le puso.
"""
from __future__ import annotations

import pytest

from luzxfer.core.tools import alcance as alc
from luzxfer.core.tools import dast

CRUDO = ("GET /buscar?q=hola&pagina=2 HTTP/1.1\r\n"
         "Host: objetivo.com\r\n\r\n")

POST = ("POST /login HTTP/1.1\r\nHost: objetivo.com\r\n"
        "Content-Type: application/x-www-form-urlencoded\r\n"
        "Content-Length: 25\r\n\r\nusuario=admin&clave=1234")


def _dentro():
    return alc.Alcance.desde_texto("+objetivo.com")


# ------------------------------------------------- puntos de inyeccion
def test_encuentra_los_parametros_de_la_query():
    # se filtra por `donde`: la lista total crece con cada clase de punto
    # (ruta, cabecera, cookie...), y clavarla aqui obligaria a tocar este
    # test en cada una sin que pruebe nada nuevo
    q = [(p.nombre, p.valor) for p in dast.puntos(CRUDO) if p.donde == "query"]
    assert q == [("q", "hola"), ("pagina", "2")]


def test_encuentra_los_parametros_del_cuerpo():
    c = [p.nombre for p in dast.puntos(POST) if p.donde == "cuerpo"]
    assert c == ["usuario", "clave"]


def test_sin_parametros_no_hay_donde_inyectar():
    assert dast.puntos("GET / HTTP/1.1\r\nHost: o.com\r\n\r\n") == []


def test_un_cuerpo_json_se_parsea_de_verdad_no_como_formulario():
    """Antes se rechazaba entero, porque trocearlo como un formulario
    mandaria basura. Ahora se parsea: una hoja por punto, con su ruta.
    Lo que no cambia es la regla de fondo —ver el test de abajo—."""
    crudo = ('POST /api HTTP/1.1\r\nHost: o.com\r\n'
             'Content-Type: application/json\r\n\r\n{"a":1,"b":2}')
    assert [p.ruta_json for p in dast.puntos(crudo)
            if p.donde == "json"] == ["a", "b"]


def test_un_cuerpo_de_tipo_desconocido_sigue_sin_trocearse():
    """La regla que no cambia: lo que no se entiende no se parte a ciegas."""
    crudo = ('POST /api HTTP/1.1\r\nHost: o.com\r\n'
             'Content-Type: application/octet-stream\r\n\r\n{"a":1,"b":2}')
    # la ruta si da puntos; lo que NO se parte es el cuerpo
    del_cuerpo = {"cuerpo", "json", "multipart"}
    assert [p for p in dast.puntos(crudo) if p.donde in del_cuerpo] == []


def test_sustituir_cambia_solo_ese_parametro():
    p = dast.puntos(CRUDO)[0]
    salida = dast.con_payload(CRUDO, p, "PAYLOAD")
    assert "q=PAYLOAD" in salida and "pagina=2" in salida


def test_sustituir_codifica_lo_que_rompería_la_url():
    p = dast.puntos(CRUDO)[0]
    salida = dast.con_payload(CRUDO, p, "' OR 1=1--")
    assert " " not in salida.splitlines()[0].split()[1], \
        "un espacio en la linea de peticion la cortaria"
    assert "%20" in salida or "+" in salida


def test_sustituir_en_el_cuerpo_recalcula_el_content_length():
    p = dast.puntos(POST)[1]
    salida = dast.con_payload(POST, p, "muchisimo-mas-largo")
    cabeza, _, cuerpo = salida.partition("\r\n\r\n")
    largo = next(int(ln.split(":")[1]) for ln in cabeza.splitlines()
                 if ln.lower().startswith("content-length"))
    assert largo == len(cuerpo.encode())


# --------------------------------------------------------- las pruebas
def test_el_reflejo_sin_escapar_se_distingue_del_escapado():
    """El detector pasivo ya ve reflejos. Lo que aporta el activo es
    saber si el marcador vuelve ENTERO: si vuelve escapado, no hay nada
    que explotar ahi y decirlo seria un falso positivo."""
    p = dast.PRUEBAS["reflejo"]
    marca = p.payloads[0]
    assert p.evalua(f"<div>{marca}</div>", 200, {}) is not None
    escapado = marca.replace("<", "&lt;").replace(">", "&gt;")
    assert p.evalua(f"<div>{escapado}</div>", 200, {}) is None
    assert p.evalua("<div>nada</div>", 200, {}) is None


def test_el_error_de_sql_reconoce_motores_distintos():
    p = dast.PRUEBAS["sqli_error"]
    for texto in ("You have an error in your SQL syntax",
                  "ORA-01756: quoted string not properly terminated",
                  "unterminated quoted string at or near",
                  "SQLITE_ERROR: unrecognized token"):
        assert p.evalua(texto, 500, {}) is not None
    assert p.evalua("todo bien por aqui", 200, {}) is None


def test_la_redireccion_abierta_mira_el_location_y_no_el_cuerpo():
    p = dast.PRUEBAS["redireccion"]
    assert p.evalua("", 302, {"location": "https://luzxfer-prueba.invalid/"}) is not None
    # una redireccion a si mismo no es abierta
    assert p.evalua("", 302, {"location": "/panel"}) is None
    assert p.evalua("https://luzxfer-prueba.invalid/", 200, {}) is None


def test_el_traversal_busca_senales_de_passwd():
    p = dast.PRUEBAS["traversal"]
    assert p.evalua("root:x:0:0:root:/root:/bin/bash", 200, {}) is not None
    assert p.evalua("nada que ver", 200, {}) is None


def test_todas_las_pruebas_traen_sus_ids_wstg():
    """Es la razon de ser del proyecto: sin WSTG, un hallazgo no alimenta
    la matriz de cobertura."""
    for nombre, p in dast.PRUEBAS.items():
        assert p.wstg, f"{nombre} no trae WSTG"
        assert all(w.startswith("WSTG-") for w in p.wstg)


# --------------------------------------------------- la correa, lo serio
def test_se_niega_a_correr_fuera_del_alcance():
    """La regla del proyecto: nada que la herramienta origine por su
    cuenta sale sin un alcance que lo autorice."""
    with pytest.raises(dast.FueraDeAlcance):
        dast.Escaneo("GET /x?a=1 HTTP/1.1\r\nHost: ajeno.net\r\n\r\n", _dentro())


def test_se_niega_si_no_hay_alcance_configurado():
    """Sin alcance todo esta «dentro» para mirar, pero no para disparar.
    Mirar de mas es ruido; disparar de mas puede ser el contrato."""
    with pytest.raises(dast.FueraDeAlcance) as e:
        dast.Escaneo(CRUDO, alc.Alcance([]))
    assert "alcance" in str(e.value).lower()


def test_dentro_del_alcance_si_arranca():
    e = dast.Escaneo(CRUDO, _dentro())
    assert e.total > 0
    assert e.enviadas == 0, "no dispara al construirse"


def test_el_total_se_sabe_antes_de_mandar_nada():
    e = dast.Escaneo(CRUDO, _dentro())
    puntos = len(dast.puntos(CRUDO))
    payloads = sum(len(p.payloads) for p in dast.PRUEBAS.values())
    assert e.total == puntos * payloads


def test_sin_puntos_de_inyeccion_no_hay_escaneo():
    with pytest.raises(dast.SinPuntos):
        dast.Escaneo("GET / HTTP/1.1\r\nHost: objetivo.com\r\n\r\n", _dentro())


def test_el_ritmo_por_defecto_es_prudente():
    e = dast.Escaneo(CRUDO, _dentro())
    assert e.por_segundo <= 5.0
    assert e.concurrencia <= 2


# ------------------------------------------------ escaneando de verdad
def _crudo_eco(h, p, ruta="/refleja?q=hola"):
    return f"GET {ruta} HTTP/1.1\r\nHost: {h}:{p}\r\n\r\n"


def _alc_eco(h):
    return alc.Alcance.desde_texto(f"+{h}")


def test_un_escaneo_real_encuentra_el_reflejo(eco):
    """/refleja decodifica el parametro y lo mete en el HTML sin
    escapar, como una aplicacion de verdad."""
    h, p = eco
    e = dast.Escaneo(_crudo_eco(h, p), _alc_eco(h), por_segundo=200)
    hallazgos = e.correr(lambda f: None)
    # `total` es una COTA, no una cuenta exacta: una estrategia para en
    # cuanto encuentra y no agota sus payloads, asi que se manda menos
    # trafico contra el sistema del cliente para el mismo hallazgo
    assert e.terminado and 0 < e.enviadas <= e.total
    reflejos = [f for f in hallazgos if f.extra["prueba"] == "reflejo"]
    assert reflejos, "el eco refleja la query entera"
    assert reflejos[0].kind == "DAST"
    assert "WSTG-INPV-01" in reflejos[0].wstg
    assert reflejos[0].extra["param"] == "q"


def test_no_inventa_hallazgos_donde_no_los_hay(eco):
    """El objetivo no tiene SQL, ni redirige, ni lee archivos. Sacar algo
    de eso seria un falso positivo, que es lo que hace inservible la
    salida de un escaner."""
    h, p = eco
    e = dast.Escaneo(_crudo_eco(h, p), _alc_eco(h), por_segundo=200)
    hallazgos = e.correr(lambda f: None)
    assert {f.extra["prueba"] for f in hallazgos} == {"reflejo"}


def test_un_reflejo_escapado_no_es_un_hallazgo(eco):
    """La diferencia que justifica el DAST activo frente al pasivo. En
    /escapa el valor vuelve, pero vuelve como &lt;...&gt;: no hay nada
    que explotar, y decir que si lo hay es el falso positivo clasico."""
    h, p = eco
    e = dast.Escaneo(_crudo_eco(h, p, "/escapa?q=hola"), _alc_eco(h),
                     por_segundo=200)
    hallazgos = e.correr(lambda f: None)
    assert [f for f in hallazgos if f.extra["prueba"] == "reflejo"] == []


def test_avisa_de_cada_hallazgo_segun_aparece(eco):
    h, p = eco
    e = dast.Escaneo(_crudo_eco(h, p), _alc_eco(h), por_segundo=200)
    vistos = []
    devueltos = e.correr(vistos.append)
    assert len(vistos) == len(devueltos) > 0


def test_el_tope_por_segundo_se_respeta(eco):
    import time
    h, p = eco
    e = dast.Escaneo(_crudo_eco(h, p, "/eco?q=1"), _alc_eco(h),
                     concurrencia=2, por_segundo=20.0)
    t = time.time()
    e.correr(lambda f: None)
    dur = time.time() - t
    assert dur > (e.total - 1) / 20.0 * 0.8, "fue mas rapido que su propio tope"


def test_abortar_corta_el_escaneo(eco):
    h, p = eco
    e = dast.Escaneo(_crudo_eco(h, p), _alc_eco(h),
                     concurrencia=1, por_segundo=50.0)
    vistos = []

    def al_llegar(f):
        vistos.append(f)
        e.abortar()

    e.correr(al_llegar)
    assert e.terminado
    assert e.enviadas < e.total, "no se detuvo"


def test_un_objetivo_caido_no_revienta_el_escaneo():
    e = dast.Escaneo("GET /x?a=1 HTTP/1.1\r\nHost: 127.0.0.1:1\r\n\r\n",
                     alc.Alcance.desde_texto("+127.0.0.1"),
                     por_segundo=200, timeout=1.0)
    assert e.correr(lambda f: None) == []
    assert e.terminado


# --------------------------------------------------- la tecla b, en la app
def _flujo(url):
    from urllib.parse import urlsplit

    from luzxfer.core.models import Flow, Request, Response
    return Flow(request=Request(method="GET", url=url,
                                headers=[("Host", urlsplit(url).netloc)]),
                response=Response(status=200, body=b"ok",
                                  headers=[("Content-Type", "text/html")]))


async def _con_flujo(app, pilot, url):
    from textual.widgets import DataTable
    app._ingresar(_flujo(url))
    await pilot.pause()
    app.query_one("#flujos", DataTable).move_cursor(row=0)
    await pilot.pause()


async def test_sin_alcance_la_tecla_b_se_niega_y_lo_explica():
    from luzxfer.tui.app import LuzxferApp
    app = LuzxferApp(arrancar_motor=False)
    async with app.run_test() as pilot:
        await _con_flujo(app, pilot, "http://objetivo.com/x?q=1")
        await pilot.press("b")
        await pilot.pause()
        assert app._escaneo is None, "no puede haber disparado nada"


async def test_fuera_del_alcance_tampoco_dispara():
    from luzxfer.tui.app import LuzxferApp
    app = LuzxferApp(arrancar_motor=False)
    async with app.run_test() as pilot:
        await _con_flujo(app, pilot, "http://ajeno.net/x?q=1")
        app.poner_alcance("+objetivo.com")
        await pilot.pause()
        await pilot.press("b")
        await pilot.pause()
        assert app._escaneo is None


async def test_dentro_del_alcance_pide_confirmacion_antes_de_disparar(eco):
    """Es lo unico que manda peticiones por su cuenta: que no salga de
    un roce de tecla."""
    from textual.widgets import Static

    from luzxfer.tui.app import LuzxferApp
    h, p = eco
    app = LuzxferApp(arrancar_motor=False)
    async with app.run_test() as pilot:
        await _con_flujo(app, pilot, f"http://{h}:{p}/refleja?q=hola")
        app.poner_alcance(f"+{h}")
        await pilot.pause()

        await pilot.press("b")
        await pilot.pause()
        assert app._escaneo is None, "la primera b solo avisa"
        estado = app.query_one("#estado", Static).render().plain
        assert "peticion" in estado.lower() and "b" in estado.lower()

        await pilot.press("b")
        for _ in range(100):
            await pilot.pause(0.05)
            if app._escaneo is not None and app._escaneo.terminado:
                break
        assert app._escaneo is not None and app._escaneo.terminado
        assert any(f.kind == "DAST" for f in app.store.list_findings())


async def test_los_hallazgos_del_dast_no_se_confirman_solos(eco):
    """Regla del proyecto: la raya entre candidato y hallazgo la cruza
    una persona, tambien aqui."""
    from luzxfer.tui.app import LuzxferApp
    h, p = eco
    app = LuzxferApp(arrancar_motor=False)
    async with app.run_test() as pilot:
        await _con_flujo(app, pilot, f"http://{h}:{p}/refleja?q=hola")
        app.poner_alcance(f"+{h}")
        await pilot.pause()
        await pilot.press("b")
        await pilot.pause()
        await pilot.press("b")
        for _ in range(100):
            await pilot.pause(0.05)
            if app._escaneo is not None and app._escaneo.terminado:
                break
        await pilot.pause(0.2)
        dast_f = [f for f in app.store.list_findings() if f.kind == "DAST"]
        assert dast_f and not any(f.confirmed for f in dast_f)
