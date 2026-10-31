"""Regresiones encontradas en la revision de la 0.1.0.

Cada test documenta un fallo real: se escribio primero, fallo contra el
codigo original, y despues se corrigio el codigo.
"""
from __future__ import annotations

import gzip
import http.server
import json
import threading
import time

import pytest
from textual.widgets import DataTable, Static

from luzxfer.core.engine import Builtin
from luzxfer.core.models import Flow, Request, Response
from luzxfer.core.tools import detector, repeater
from luzxfer.tui.app import LuzxferApp


class _Eco(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def _leer_cuerpo(self) -> bytes:
        if "chunked" in (self.headers.get("Transfer-Encoding") or "").lower():
            datos = b""
            while True:
                tam = int(self.rfile.readline().strip(), 16)
                if tam == 0:
                    self.rfile.readline()
                    return datos
                datos += self.rfile.read(tam)
                self.rfile.readline()
        n = int(self.headers.get("Content-Length") or 0)
        return self.rfile.read(n) if n else b""

    def _json(self, obj, extra=()):
        cuerpo = json.dumps(obj).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(cuerpo)))
        for k, v in extra:
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(cuerpo)

    def do_GET(self):
        if self.path.startswith("/gzip"):
            q = self.path.split("q=", 1)[-1]
            cuerpo = gzip.compress(f"<html>buscaste: {q}</html>".encode())
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Encoding", "gzip")
            self.send_header("Content-Length", str(len(cuerpo)))
            self.end_headers()
            self.wfile.write(cuerpo)
        elif self.path.startswith("/lento"):
            time.sleep(1.0)
            self._json({"ok": True})
        else:
            self._json({"metodo": self.command, "ruta": self.path,
                        "cabeceras": list(self.headers.items())})

    def do_POST(self):
        cuerpo = self._leer_cuerpo()
        self._json({"metodo": "POST", "cuerpo": cuerpo.decode(),
                    "cabeceras": list(self.headers.items())})

    do_FOO = do_GET

    def do_HEAD(self):
        # anuncia un cuerpo de 50 bytes que no envia: si el cliente no sabe
        # que es HEAD, se queda esperandolos hasta el timeout
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", "50")
        self.end_headers()


@pytest.fixture(scope="module")
def eco():
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Eco)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield srv.server_address
    srv.shutdown()
    srv.server_close()


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
