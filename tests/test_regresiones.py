"""Regresiones encontradas en la revision de la 0.1.0.

Cada test documenta un fallo real: se escribio primero, fallo contra el
codigo original, y despues se corrigio el codigo.
"""
from __future__ import annotations

import gzip
import http.server
import json
import time

import pytest
from textual.widgets import DataTable, Input, Static

from luzxfer.core.engine import Builtin
from luzxfer.core.models import (
    CODIFICACIONES_LEGIBLES,
    Flow,
    Request,
    Response,
)
from luzxfer.core.store import Store
from luzxfer.core.tools import detector, repeater
from luzxfer.tui.app import LuzxferApp


# ------------------------------------------------------------ 1. gzip
def test_detector_ve_reflejos_en_respuestas_comprimidas(eco):
    """Antes: el detector buscaba en los bytes comprimidos y no veia nada.
    Los objetivos reales comprimen casi todo lo que es HTML."""
    h, p = eco
    f = repeater.send_raw(f"GET /gzip?q=REFLEJOGZIP HTTP/1.1\r\nHost: {h}:{p}\r\n\r\n")
    assert f.response.header("content-encoding") == "gzip"
    assert b"REFLEJOGZIP" not in f.response.body            # crudo: comprimido
    assert "REFLEJOGZIP" in f.response.text()               # texto: descomprimido
    assert any(x.kind == "REFLEJO" for x in detector.analizar(f))


def test_cuerpo_corrupto_con_gzip_no_revienta():
    r = Response(status=200, headers=[("Content-Encoding", "gzip")], body=b"no es gzip")
    assert r.text() == "no es gzip"


# ------------------------------------------- 2. lo que escribes es lo que viaja
def test_repeater_conserva_cabeceras_duplicadas(eco):
    """Antes: dict(cabeceras) colapsaba duplicados. Mandar la misma cabecera
    dos veces es una tecnica de prueba, no un error a corregir."""
    h, p = eco
    f = repeater.send_raw(
        f"GET /x HTTP/1.1\r\nHost: {h}:{p}\r\n"
        "X-Prueba: uno\r\nX-Prueba: dos\r\n\r\n")
    recibidas = json.loads(f.response.text())["cabeceras"]
    assert [v for k, v in recibidas if k == "X-Prueba"] == ["uno", "dos"]


def test_repeater_no_inyecta_cabeceras_propias(eco):
    """Antes: http.client agregaba Accept-Encoding: identity por su cuenta."""
    h, p = eco
    f = repeater.send_raw(f"GET /x HTTP/1.1\r\nHost: {h}:{p}\r\n\r\n")
    nombres = [k.lower() for k, _ in json.loads(f.response.text())["cabeceras"]]
    assert nombres == ["host"]


def test_repeater_acepta_metodos_no_estandar(eco):
    h, p = eco
    f = repeater.send_raw(f"FOO /x HTTP/1.1\r\nHost: {h}:{p}\r\n\r\n")
    assert f.error == ""
    assert json.loads(f.response.text())["metodo"] == "FOO"


def test_repeater_head_no_se_cuelga_esperando_cuerpo(eco):
    h, p = eco
    t = time.time()
    f = repeater.send_raw(f"HEAD /x HTTP/1.1\r\nHost: {h}:{p}\r\n\r\n", timeout=5)
    assert time.time() - t < 3
    assert f.status == 200
    assert f.response.body == b""


# ------------------------------------------------------- 3. proxy
def _por_proxy(eco, peticion: bytes) -> dict:
    import socket
    h, p = eco
    motor = Builtin(lambda f: None, port=0, upstream=f"http://{h}:{p}")
    motor.start()
    puerto = motor._srv.server_address[1]
    try:
        s = socket.create_connection(("127.0.0.1", puerto), timeout=10)
        s.sendall(peticion)
        r = http.client.HTTPResponse(s)
        r.begin()
        cuerpo = r.read()
        s.close()
        return json.loads(cuerpo)
    finally:
        motor.stop()


import http.client  # noqa: E402


def test_proxy_reenvia_cuerpos_chunked(eco):
    """Antes: sin Content-Length se leia un cuerpo vacio y el chunked se
    quedaba en el socket. Clientes de API y moviles mandan chunked."""
    peticion = (b"POST /api HTTP/1.1\r\nHost: x\r\nTransfer-Encoding: chunked\r\n\r\n"
                b"5\r\nhola \r\n5\r\nmundo\r\n0\r\n\r\n")
    datos = _por_proxy(eco, peticion)
    assert datos["cuerpo"] == "hola mundo"


def test_proxy_conserva_cabeceras_duplicadas(eco):
    peticion = (b"GET /x HTTP/1.1\r\nHost: x\r\n"
                b"X-Dup: a\r\nX-Dup: b\r\nConnection: close\r\n\r\n")
    datos = _por_proxy(eco, peticion)
    assert [v for k, v in datos["cabeceras"] if k == "X-Dup"] == ["a", "b"]


# ------------------------------------------------------- 4. TUI
def _f(i):
    return Flow(request=Request(method="GET", url=f"http://ej.com/r{i}",
                                headers=[("Host", "ej.com")]),
                response=Response(status=200, body=b"x"))


async def test_la_seleccion_no_salta_cuando_llega_trafico():
    """Antes: la tabla se reconstruia entera y se restauraba por INDICE.
    Con el orden mas-nuevo-arriba, cada flujo nuevo corria la seleccion
    a otro flujo distinto mientras el analista lo estaba leyendo."""
    app = LuzxferApp(arrancar_motor=False)
    async with app.run_test() as pilot:
        for i in range(5):
            app._ingresar(_f(i))
        await pilot.pause()
        tabla = app.query_one("#flujos", DataTable)
        tabla.move_cursor(row=1)
        await pilot.pause()
        elegido = app._flujo_actual.id

        for i in range(5, 8):
            app._ingresar(_f(i))
        await pilot.pause()

        fila = tabla.coordinate_to_cell_key((tabla.cursor_row, 0)).row_key.value
        assert int(fila) == elegido
        assert app._flujo_actual.id == elegido


async def test_sigue_el_trafico_si_estabas_al_final():
    app = LuzxferApp(arrancar_motor=False)
    async with app.run_test() as pilot:
        for i in range(3):
            app._ingresar(_f(i))
        await pilot.pause()
        tabla = app.query_one("#flujos", DataTable)
        tabla.move_cursor(row=tabla.row_count - 1)
        await pilot.pause()
        app._ingresar(_f(99))
        await pilot.pause()
        assert tabla.cursor_row == tabla.row_count - 1


async def test_el_repeater_no_congela_la_interfaz(eco):
    """Antes: send_raw corria en el hilo de la interfaz. Un objetivo lento
    congelaba toda la TUI hasta el timeout de 30 segundos."""
    h, p = eco
    app = LuzxferApp(arrancar_motor=False)
    async with app.run_test() as pilot:
        app._ingresar(Flow(request=Request(method="GET", url=f"http://{h}:{p}/lento",
                                           headers=[("Host", f"{h}:{p}")]),
                           response=Response(status=200)))
        await pilot.pause()
        app.query_one("#flujos", DataTable).move_cursor(row=0)
        await pilot.pause()
        await pilot.press("r")
        await pilot.pause()

        from textual.widgets import Button
        t = time.time()
        app.screen.query_one("#rep-enviar", Button).press()
        await pilot.pause()
        # la interfaz respondio de inmediato y muestra que esta enviando
        assert time.time() - t < 0.8
        assert "enviando" in app.screen.query_one("#rep-salida", Static).render().plain

        for _ in range(40):
            await pilot.pause(0.1)
            if "200" in app.screen.query_one("#rep-salida", Static).render().plain:
                break
        assert "200" in app.screen.query_one("#rep-salida", Static).render().plain


async def test_flujos_del_repeater_pasan_por_el_detector(eco):
    h, p = eco
    app = LuzxferApp(arrancar_motor=False)
    async with app.run_test() as pilot:
        app._ingresar(Flow(request=Request(method="GET", url=f"http://{h}:{p}/gzip?q=x",
                                           headers=[("Host", f"{h}:{p}")]),
                           response=Response(status=200)))
        await pilot.pause()
        app.query_one("#flujos", DataTable).move_cursor(row=0)
        await pilot.pause()
        await pilot.press("r")
        await pilot.pause()
        from textual.widgets import Button, TextArea
        app.screen.query_one("#rep-editor", TextArea).text = (
            f"GET /gzip?q=DESDEREPEATER HTTP/1.1\r\nHost: {h}:{p}\r\n\r\n")
        app.screen.query_one("#rep-enviar", Button).press()
        for _ in range(30):
            await pilot.pause(0.1)
            if any(x.kind == "REFLEJO" for x in app.store.list_findings()):
                break
        assert any(x.kind == "REFLEJO" for x in app.store.list_findings())


async def test_respuestas_largas_se_pueden_desplazar():
    """Antes: en el repeater la salida tenia height: 1fr dentro del
    contenedor con scroll; una respuesta de 400 lineas quedaba cortada al
    alto visible y no habia nada que desplazar."""
    from textual.containers import VerticalScroll

    largo = Flow(
        request=Request(method="GET", url="http://ej.com/x", headers=[("Host", "ej.com")]),
        response=Response(status=200, reason="OK", headers=[("Content-Type", "text/plain")],
                          body="\n".join(f"linea {i}" for i in range(400)).encode()),
    )
    app = LuzxferApp(arrancar_motor=False)
    async with app.run_test(size=(120, 40)) as pilot:
        app._ingresar(largo)
        await pilot.pause()
        app.query_one("#flujos", DataTable).move_cursor(row=0)
        await pilot.pause()

        # panel de respuesta de la pantalla principal
        app.query_one("#detalle").active = "tab-resp"
        await pilot.pause()
        panel = app.query_one("#panel-resp").parent
        assert isinstance(panel, VerticalScroll)
        assert panel.max_scroll_y > 0

        # salida del repeater
        await pilot.press("r")
        await pilot.pause()
        app.screen._mostrar(largo)
        await pilot.pause()
        assert app.screen.query_one("#rep-scroll", VerticalScroll).max_scroll_y > 0


# ------------------------------------------- 5. historial que no cabe entero
def test_count_flows_acepta_los_mismos_filtros_que_list_flows():
    st = Store()
    for i in range(6):
        st.add_flow(Flow(
            request=Request(method="GET" if i % 2 else "POST",
                            url=f"http://ej.com/r{i}", headers=[("Host", "ej.com")]),
            response=Response(status=200 if i < 4 else 500),
        ))
    assert st.count_flows() == 6                       # sin filtros: el total
    assert st.count_flows(metodo="GET") == 3
    assert st.count_flows(estado="5xx") == 2
    assert st.count_flows(texto="/r1") == 1
    st.close()


def test_count_flows_y_list_flows_no_se_contradicen():
    """Comparten el mismo constructor de WHERE a proposito: dos que se
    separen con el tiempo es como vuelve un conteo que no cuadra con lo
    que la tabla muestra."""
    st = Store()
    for i in range(20):
        st.add_flow(Flow(
            request=Request(method="GET" if i % 3 else "POST",
                            url=f"http://ej.com/r{i}", headers=[("Host", "ej.com")]),
            response=Response(status=200 if i % 2 else 404),
        ))
    for filtros in ({}, {"metodo": "GET"}, {"estado": "4xx"}, {"texto": "r1"},
                    {"metodo": "POST", "estado": "2xx"}):
        assert st.count_flows(**filtros) == len(st.list_flows(limite=10_000, **filtros))
    st.close()


def test_mas_flujos_que_el_limite_no_se_pierden_en_silencio():
    """Antes: refrescar_tabla usaba el limite=1000 por defecto de
    list_flows sin pasar nada. Con mas de 1000 flujos, filtrar o limpiar
    dejaba ver solo los 1000 mas recientes, sin decirlo en ninguna parte."""
    from luzxfer.tui import app as modulo

    st = Store()
    for i in range(1200):
        st.add_flow(Flow(
            request=Request(method="GET", url=f"http://ej.com/r{i}",
                            headers=[("Host", "ej.com")]),
            response=Response(status=200),
        ))
    assert st.count_flows() == 1200
    # el limite de la tabla ya no es el default de list_flows
    assert modulo.LIMITE_TABLA > 1000
    assert len(st.list_flows(limite=modulo.LIMITE_TABLA)) == 1200
    st.close()


async def test_la_barra_de_estado_avisa_cuando_la_tabla_esta_truncada(monkeypatch):
    from luzxfer.tui import app as modulo
    monkeypatch.setattr(modulo, "LIMITE_TABLA", 10)

    app = modulo.LuzxferApp(arrancar_motor=False)
    async with app.run_test() as pilot:
        for i in range(14):
            app._ingresar(_f(i))
        await pilot.pause()
        app.refrescar_tabla()
        app.actualizar_estado()
        await pilot.pause()

        estado = app.query_one("#estado", Static).render().plain
        assert "14 flujos" in estado
        assert "mostrando 10 de 14" in estado
        assert app.query_one("#flujos", DataTable).row_count == 10


async def test_sin_truncado_la_barra_no_dice_nada_de_mas(monkeypatch):
    from luzxfer.tui import app as modulo
    monkeypatch.setattr(modulo, "LIMITE_TABLA", 10)

    app = modulo.LuzxferApp(arrancar_motor=False)
    async with app.run_test() as pilot:
        for i in range(3):
            app._ingresar(_f(i))
        await pilot.pause()
        app.actualizar_estado()
        await pilot.pause()
        assert "mostrando" not in app.query_one("#estado", Static).render().plain


async def test_el_aviso_de_truncado_respeta_el_filtro(monkeypatch):
    """Con filtro activo, el 'de M' tiene que ser el total FILTRADO, no el
    total de la sesion: si no, el aviso miente sobre lo que falta."""
    from luzxfer.tui import app as modulo
    monkeypatch.setattr(modulo, "LIMITE_TABLA", 5)

    app = modulo.LuzxferApp(arrancar_motor=False)
    async with app.run_test() as pilot:
        for i in range(20):
            app._ingresar(_f(i))                    # /r0 .. /r19
        await pilot.pause()
        app.query_one("#filtro", Input).value = "/r1"   # r1 y r10..r19 = 11
        await pilot.pause()
        app.actualizar_estado()
        await pilot.pause()
        assert "mostrando 5 de 11" in app.query_one("#estado", Static).render().plain


# ------------------------------------------------------------ 6. brotli
def _ae_que_vio_el_servidor(datos: dict) -> str:
    return next(v for k, v in datos["cabeceras"] if k.lower() == "accept-encoding")


SIN_BROTLI = "br" not in CODIFICACIONES_LEGIBLES


def test_el_proxy_no_pide_al_servidor_lo_que_no_sabe_deshacer(eco):
    """El fallo de verdad no es el cuerpo ilegible en pantalla: es que el
    detector busca reflejos en los bytes comprimidos y no encuentra NADA.
    Falso negativo silencioso, y con brotli por defecto en nginx, Cloudflare
    y Express, es el caso comun y no el raro."""
    datos = _por_proxy(eco, b"GET /eco HTTP/1.1\r\nHost: x\r\n"
                            b"Accept-Encoding: gzip, deflate, br, zstd\r\n"
                            b"Connection: close\r\n\r\n")
    ae = _ae_que_vio_el_servidor(datos)
    assert "zstd" not in ae, "eso no se sabe deshacer en ningun caso"
    assert "gzip" in ae and "deflate" in ae
    # con el extra [br] instalado SI se sabe deshacer brotli, asi que
    # recortarlo seria empobrecer la respuesta sin motivo. Lo que se
    # recorta es lo que no se puede leer, no una lista fija.
    assert ("br" not in ae) == SIN_BROTLI


def test_el_proxy_conserva_el_orden_y_los_q_de_accept_encoding(eco):
    """Se recorta, no se reemplaza: cuanto menos se toque la peticion del
    cliente, menos se cambia lo que el servidor decide."""
    datos = _por_proxy(eco, b"GET /eco HTTP/1.1\r\nHost: x\r\n"
                            b"Accept-Encoding: gzip;q=0.8, br;q=1.0, deflate;q=0.5\r\n"
                            b"Connection: close\r\n\r\n")
    ae = _ae_que_vio_el_servidor(datos)
    esperado = ("gzip;q=0.8, deflate;q=0.5" if SIN_BROTLI
                else "gzip;q=0.8, br;q=1.0, deflate;q=0.5")
    assert ae == esperado


def test_si_el_cliente_solo_pide_lo_ilegible_se_manda_identity(eco):
    ilegible = b"zstd" if not SIN_BROTLI else b"br"
    datos = _por_proxy(eco, b"GET /eco HTTP/1.1\r\nHost: x\r\n"
                            b"Accept-Encoding: " + ilegible +
                            b"\r\nConnection: close\r\n\r\n")
    assert _ae_que_vio_el_servidor(datos) == "identity"


def test_el_comodin_de_accept_encoding_no_pasa(eco):
    """'*' deja al servidor elegir, y eso incluye brotli."""
    datos = _por_proxy(eco, b"GET /eco HTTP/1.1\r\nHost: x\r\n"
                            b"Accept-Encoding: *\r\nConnection: close\r\n\r\n")
    assert _ae_que_vio_el_servidor(datos) == "identity"


def test_sin_accept_encoding_no_se_inventa_ninguno(eco):
    datos = _por_proxy(eco, b"GET /eco HTTP/1.1\r\nHost: x\r\n"
                            b"Connection: close\r\n\r\n")
    assert not any(k.lower() == "accept-encoding" for k, v in datos["cabeceras"])


def test_se_puede_conservar_el_accept_encoding_original(eco):
    """Para quien este probando justamente como responde el servidor a
    distintas codificaciones."""
    import socket
    h, p = eco
    motor = Builtin(lambda f: None, port=0, upstream=f"http://{h}:{p}",
                    filtrar_encoding=False)
    motor.start()
    puerto = motor._srv.server_address[1]
    try:
        s = socket.create_connection(("127.0.0.1", puerto), timeout=10)
        s.sendall(b"GET /eco HTTP/1.1\r\nHost: x\r\n"
                  b"Accept-Encoding: gzip, br\r\nConnection: close\r\n\r\n")
        r = http.client.HTTPResponse(s)
        r.begin()
        datos = json.loads(r.read())
        s.close()
    finally:
        motor.stop()
    assert "br" in _ae_que_vio_el_servidor(datos)


def test_filtrar_accept_encoding_es_la_unica_fuente_de_verdad():
    from luzxfer.core.models import CODIFICACIONES_LEGIBLES, filtrar_accept_encoding

    assert "gzip" in CODIFICACIONES_LEGIBLES and "deflate" in CODIFICACIONES_LEGIBLES
    for enc in CODIFICACIONES_LEGIBLES:
        assert filtrar_accept_encoding(enc) == enc
    assert filtrar_accept_encoding("") == "identity"


async def test_el_panel_avisa_si_el_cuerpo_quedo_sin_decodificar():
    """Antes el repeater avisaba y el panel principal mostraba los bytes
    crudos sin decir nada, asi que parecia una respuesta rota del servidor."""
    from luzxfer.core.models import CODIFICACIONES_LEGIBLES
    if "br" in CODIFICACIONES_LEGIBLES:
        pytest.skip("brotli instalado: aqui el cuerpo si se decodifica")

    f = Flow(
        request=Request(method="GET", url="http://ej.com/x", headers=[("Host", "ej.com")]),
        response=Response(status=200, reason="OK", body=b"\x1b\x0e\x00\x00basura",
                          headers=[("Content-Type", "text/html"),
                                   ("Content-Encoding", "br")]),
    )
    app = LuzxferApp(arrancar_motor=False)
    async with app.run_test() as pilot:
        app._ingresar(f)
        await pilot.pause()
        app.query_one("#flujos", DataTable).move_cursor(row=0)
        await pilot.pause()
        assert "sin decodificar" in app.query_one("#panel-resp", Static).render().plain


async def test_gzip_no_genera_aviso_porque_si_se_decodifica():
    f = Flow(
        request=Request(method="GET", url="http://ej.com/x", headers=[("Host", "ej.com")]),
        response=Response(status=200, reason="OK",
                          body=gzip.compress(b"<html>hola</html>"),
                          headers=[("Content-Type", "text/html"),
                                   ("Content-Encoding", "gzip")]),
    )
    app = LuzxferApp(arrancar_motor=False)
    async with app.run_test() as pilot:
        app._ingresar(f)
        await pilot.pause()
        app.query_one("#flujos", DataTable).move_cursor(row=0)
        await pilot.pause()
        panel = app.query_one("#panel-resp", Static).render().plain
        assert "hola" in panel and "sin decodificar" not in panel


# ------------------------------------------- 7. validadores de cache (304)
def test_el_proxy_quita_los_validadores_de_cache(eco):
    """Un navegador con la pagina en cache manda If-None-Match y el
    servidor contesta 304 sin cuerpo. El detector busca reflejos en un
    cuerpo vacio y devuelve cero: mismo falso negativo silencioso que
    brotli, y en un pentest pasa en cada recarga."""
    datos = _por_proxy(eco, b"GET /eco HTTP/1.1\r\nHost: x\r\n"
                            b'If-None-Match: W/"abc123"\r\n'
                            b"If-Modified-Since: Sat, 31 Oct 2026 21:45:30 GMT\r\n"
                            b"Connection: close\r\n\r\n")
    vistas = {k.lower() for k, _ in datos["cabeceras"]}
    assert "if-none-match" not in vistas
    assert "if-modified-since" not in vistas
    assert "host" in vistas                      # lo demas sigue pasando


def test_se_pueden_conservar_para_probar_cache_poisoning(eco):
    """Quien este probando envenenamiento o cache deception necesita que
    las cabeceras de cache lleguen intactas: ahi son el objeto de la
    prueba, no un estorbo."""
    import socket
    h, p = eco
    motor = Builtin(lambda f: None, port=0, upstream=f"http://{h}:{p}",
                    filtrar_cache=False)
    motor.start()
    puerto = motor._srv.server_address[1]
    try:
        s = socket.create_connection(("127.0.0.1", puerto), timeout=10)
        s.sendall(b"GET /eco HTTP/1.1\r\nHost: x\r\n"
                  b'If-None-Match: W/"abc123"\r\nConnection: close\r\n\r\n')
        r = http.client.HTTPResponse(s)
        r.begin()
        datos = json.loads(r.read())
        s.close()
    finally:
        motor.stop()
    assert any(k.lower() == "if-none-match" for k, _ in datos["cabeceras"])


def test_una_peticion_sin_validadores_no_cambia(eco):
    datos = _por_proxy(eco, b"GET /eco HTTP/1.1\r\nHost: x\r\n"
                            b"X-Propia: valor\r\nConnection: close\r\n\r\n")
    assert any(k == "X-Propia" and v == "valor" for k, v in datos["cabeceras"])


# --------------------------- 8. el cableado entre la app y el motor
def _pedir_por(puerto: int, extra: bytes) -> dict:
    """Una peticion por el proxy, desde un hilo aparte.

    Tiene que ir en otro hilo: _manejar() llama a _emitir() ANTES de
    escribir la respuesta, y _emitir salta al bucle de la interfaz con
    call_from_thread. Si el test leyera el socket desde ese mismo bucle,
    las dos partes se esperarian para siempre.
    """
    import socket
    s = socket.create_connection(("127.0.0.1", puerto), timeout=10)
    s.sendall(b"GET /eco HTTP/1.1\r\nHost: x\r\n" + extra +
              b"Connection: close\r\n\r\n")
    r = http.client.HTTPResponse(s)
    r.begin()
    cuerpo = r.read()
    s.close()
    return json.loads(cuerpo)


async def test_la_app_arranca_el_motor_con_sus_banderas(eco):
    """Humo del camino de verdad: LuzxferApp.arrancar() construyendo el
    Builtin, que es lo que ocurre al abrir luzxfer.

    OJO con lo que este test NO prueba. Comprobado borrando
    `filtrar_cache=self.filtrar_cache` de arrancar(): este test SIGUE
    PASANDO, porque Builtin tiene filtrar_cache=True por defecto y el
    defecto disimula la bandera que falta. El que de verdad prueba el
    cableado es el siguiente, con las banderas en False.

    Se queda porque sirve de humo —que el motor arranca, escucha y
    reenvia por el camino real— pero no como red contra un cable suelto.
    """
    import asyncio

    h, p = eco
    app = LuzxferApp(upstream=f"http://{h}:{p}", port=0, arrancar_motor=True)
    async with app.run_test() as pilot:
        await pilot.pause()
        assert app.engine is not None and app.engine.running
        puerto = app.engine._srv.server_address[1]

        datos = await asyncio.to_thread(
            _pedir_por, puerto,
            b'If-None-Match: W/"abc"\r\n'
            b"If-Modified-Since: Sat, 31 Oct 2026 21:45:30 GMT\r\n"
            b"Accept-Encoding: gzip, deflate, br, zstd\r\n",
        )

    vistas = {k.lower(): v for k, v in datos["cabeceras"]}
    assert "if-none-match" not in vistas, "la app no le paso filtrar_cache al motor"
    assert "if-modified-since" not in vistas
    # zstd no se sabe deshacer con extra ni sin el, asi que su ausencia
    # prueba el cableado sin depender de que este instalado brotli
    assert "zstd" not in vistas.get("accept-encoding", ""), \
        "la app no le paso filtrar_encoding al motor"


async def test_la_app_respeta_que_le_pidan_no_filtrar(eco):
    """Este es el que prueba el cableado de verdad.

    Con las banderas en False, el defecto del motor no puede disimular:
    si arrancar() no las pasa, el motor filtra igualmente y el test cae.
    Comprobado borrando esa linea: este test falla y los otros 235 no.

    Y el fallo que atrapa es el peor de los dos. Si el cable se suelta,
    las banderas vuelven a su defecto —filtrar— asi que nadie ve 304s y
    todo parece bien; lo que se rompe en silencio es --conservar-cache,
    o sea probar envenenamiento de cache creyendo que las cabeceras
    viajan cuando no viajan."""
    import asyncio

    h, p = eco
    app = LuzxferApp(upstream=f"http://{h}:{p}", port=0, arrancar_motor=True,
                     filtrar_cache=False, filtrar_encoding=False)
    async with app.run_test() as pilot:
        await pilot.pause()
        puerto = app.engine._srv.server_address[1]
        datos = await asyncio.to_thread(
            _pedir_por, puerto,
            b'If-None-Match: W/"abc"\r\nAccept-Encoding: gzip, br\r\n')

    vistas = {k.lower(): v for k, v in datos["cabeceras"]}
    assert "if-none-match" in vistas
    assert "br" in vistas.get("accept-encoding", "")
