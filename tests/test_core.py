"""Tests del nucleo: modelos, almacen, motor, repeater y detector."""
from __future__ import annotations

import http.server
import json
import sqlite3
import threading
import time
import urllib.request
from types import SimpleNamespace

import pytest

from luzxfer.core.engine import Builtin, puerto_libre
from luzxfer.core.models import Finding, Flow, Request, Response
from luzxfer.core.store import Store
from luzxfer.core.tools import detector, repeater


# --------------------------------------------------------------- servidor
class _Objetivo(http.server.BaseHTTPRequestHandler):
    """Servidor de pruebas: refleja la entrada y emite cabeceras flojas."""
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def _responder(self, code, cuerpo: bytes, ctype="text/html; charset=utf-8",
                   extra=()):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(cuerpo)))
        self.send_header("Server", "objetivo-test/1.0")
        self.send_header("X-Powered-By", "PruebaLang/9")
        for k, v in extra:
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(cuerpo)

    def do_GET(self):
        from urllib.parse import parse_qs, urlsplit
        p = urlsplit(self.path)
        if p.path == "/eco":
            q = parse_qs(p.query).get("q", [""])[0]
            self._responder(200, f"<html>buscaste: {q}</html>".encode())
        elif p.path == "/cookie":
            self._responder(200, b"<html>ok</html>",
                            extra=[("Set-Cookie", "sesion=abc123; Path=/")])
        elif p.path == "/boom":
            self._responder(500, b"<html>Traceback: linea 42</html>")
        else:
            self._responder(200, b"<html>raiz</html>")

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        cuerpo = self.rfile.read(n)
        self._responder(200, b"recibido:" + cuerpo, ctype="text/plain")


@pytest.fixture(scope="module")
def objetivo():
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Objetivo)
    hilo = threading.Thread(target=srv.serve_forever, daemon=True)
    hilo.start()
    yield srv.server_address          # (host, port)
    srv.shutdown()
    srv.server_close()


# ----------------------------------------------------------------- modelos
def test_request_raw_reconstruye_la_peticion():
    r = Request(method="POST", url="http://ej.com:8099/api/login",
                headers=[("Host", "ej.com:8099"), ("Content-Type", "application/json")],
                body=b'{"u":"a"}')
    crudo = r.raw()
    assert crudo.startswith("POST /api/login HTTP/1.1\r\n")
    assert "Host: ej.com:8099" in crudo
    assert crudo.endswith('{"u":"a"}')
    assert r.host == "ej.com:8099"
    assert r.path == "/api/login"


def test_response_headers_all_recoge_cookies_repetidas():
    p = Response(status=200, headers=[("Set-Cookie", "a=1"), ("Set-Cookie", "b=2")])
    assert p.headers_all("set-cookie") == ["a=1", "b=2"]
    assert p.header("SET-COOKIE") == "a=1"


# ----------------------------------------------------------------- almacen
def test_store_guarda_y_recupera_un_flujo():
    s = Store()
    f = Flow(
        request=Request(method="GET", url="http://ej.com/x?a=1",
                        headers=[("Host", "ej.com")]),
        response=Response(status=200, reason="OK",
                          headers=[("Content-Type", "text/html")],
                          body=b"<html>hola</html>"),
        duration_ms=12,
    )
    fid = s.add_flow(f)
    assert fid == 1

    vuelto = s.get_flow(fid)
    assert vuelto is not None
    assert vuelto.request.method == "GET"
    assert vuelto.request.host == "ej.com"
    assert vuelto.status == 200
    assert vuelto.response.body == b"<html>hola</html>"
    assert vuelto.duration_ms == 12
    s.close()


def test_store_filtra_por_texto_metodo_y_familia_de_estado():
    s = Store()
    for metodo, url, cod in [
        ("GET", "http://a.com/uno", 200),
        ("POST", "http://a.com/dos", 404),
        ("GET", "http://b.com/tres", 500),
    ]:
        s.add_flow(Flow(
            request=Request(method=metodo, url=url, headers=[("Host", url.split("/")[2])]),
            response=Response(status=cod),
        ))

    assert len(s.list_flows()) == 3
    assert len(s.list_flows(texto="a.com")) == 2
    assert len(s.list_flows(metodo="post")) == 1
    assert len(s.list_flows(estado="4xx")) == 1
    assert len(s.list_flows(estado="500")) == 1
    assert s.hosts() == ["a.com", "b.com"]
    s.close()


def test_store_deduplica_hallazgos_iguales():
    """La restriccion UNIQUE es lo que evita el ruido de scanner."""
    s = Store()
    h1 = Finding(kind="FUGA", detail="server: nginx", url="ej.com")
    h2 = Finding(kind="FUGA", detail="server: nginx", url="ej.com")
    assert s.add_finding(h1) == 1
    assert s.add_finding(h2) is None          # repetido, se ignora
    assert s.count_findings() == 1
    s.close()


def test_store_persiste_entre_sesiones(tmp_path):
    ruta = tmp_path / "sesion.db"
    s1 = Store(ruta)
    s1.add_flow(Flow(request=Request(method="GET", url="http://x.com/",
                                     headers=[("Host", "x.com")]),
                     response=Response(status=200)))
    s1.close()

    s2 = Store(ruta)
    assert s2.count_flows() == 1
    assert s2.get_flow(1).request.url == "http://x.com/"
    s2.close()


def test_store_marcar_y_notas():
    s = Store()
    fid = s.add_flow(Flow(request=Request(method="GET", url="http://x.com/",
                                          headers=[("Host", "x.com")]),
                          response=Response(status=200)))
    s.set_mark(fid, True)
    s.set_note(fid, "revisar este")
    f = s.get_flow(fid)
    assert f.marked is True
    assert f.note == "revisar este"
    assert len(s.list_flows(solo_marcados=True)) == 1
    s.close()


# ----------------------------------------------------------------- motor
def test_motor_inverso_captura_el_trafico(objetivo):
    host, puerto = objetivo
    capturados: list[Flow] = []

    motor = Builtin(capturados.append, port=0, upstream=f"http://{host}:{puerto}")
    # puerto 0 deja que el SO elija uno libre
    motor.start()
    real = motor._srv.server_address[1]
    try:
        urllib.request.urlopen(f"http://127.0.0.1:{real}/eco?q=hola", timeout=10).read()
        time.sleep(0.3)
    finally:
        motor.stop()

    assert len(capturados) == 1
    f = capturados[0]
    assert f.request.method == "GET"
    assert f.request.path == "/eco?q=hola"
    assert f.status == 200
    assert b"buscaste: hola" in f.response.body
    assert f.duration_ms >= 0


def test_motor_rechaza_connect_con_motivo_claro():
    motor = Builtin(lambda f: None, port=0)
    motor.start()
    real = motor._srv.server_address[1]
    try:
        import http.client
        con = http.client.HTTPConnection("127.0.0.1", real, timeout=10)
        con.request("CONNECT", "ejemplo.com:443")
        r = con.getresponse()
        cuerpo = r.read()
        assert r.status == 501
        assert b"no intercepta HTTPS" in cuerpo
        assert b"mitmproxy" in cuerpo     # dice como resolverlo
        con.close()
    finally:
        motor.stop()


def test_puerto_libre_detecta_ocupado(objetivo):
    host, puerto = objetivo
    assert puerto_libre("127.0.0.1", puerto) is False
    assert puerto_libre("127.0.0.1", 0) is True


# --------------------------------------------------------------- repeater
def test_parse_raw_separa_bien():
    crudo = ("POST /api HTTP/1.1\r\n"
             "Host: ej.com:8099\r\n"
             "Content-Type: application/json\r\n"
             "\r\n"
             '{"a":1}')
    metodo, ruta, version, cab, cuerpo = repeater.parse_raw(crudo)
    assert (metodo, ruta, version) == ("POST", "/api", "HTTP/1.1")
    assert ("Host", "ej.com:8099") in cab
    assert cuerpo == b'{"a":1}'


def test_parse_raw_rechaza_basura():
    with pytest.raises(repeater.ErrorPeticion):
        repeater.parse_raw("")
    with pytest.raises(repeater.ErrorPeticion):
        repeater.parse_raw("solounapalabra\r\n\r\n")


def test_repeater_recalcula_content_length(objetivo):
    """El error numero uno al editar a mano: dejar el Content-Length viejo."""
    host, puerto = objetivo
    crudo = (f"POST /eco HTTP/1.1\r\nHost: {host}:{puerto}\r\n"
             "Content-Type: text/plain\r\nContent-Length: 9999\r\n\r\nhola")
    f = repeater.send_raw(crudo)
    assert f.error == ""
    assert f.status == 200
    assert f.response.body == b"recibido:hola"
    assert f.source == "repeater"
    # la mentira no viajo
    assert dict(f.request.headers)["Content-Length"] == "4"


def test_repeater_sin_host_explica_el_problema():
    with pytest.raises(repeater.ErrorPeticion, match="Host"):
        repeater.send_raw("GET / HTTP/1.1\r\n\r\n")


def test_repeater_devuelve_error_de_red_sin_reventar():
    f = repeater.send_raw("GET / HTTP/1.1\r\nHost: 127.0.0.1:1\r\n\r\n")
    assert f.response is None
    assert f.error != ""


# --------------------------------------------------------------- detector
def _flujo(url, cuerpo=b"", cab_resp=(), status=200, ctype="text/html"):
    return Flow(
        request=Request(method="GET", url=url,
                        headers=[("Host", url.split("/")[2])]),
        response=Response(status=status, body=cuerpo,
                          headers=[("Content-Type", ctype), *cab_resp]),
    )


def test_detector_encuentra_reflejo():
    f = _flujo("http://ej.com/b?q=CADENAUNICA", b"<p>buscaste: CADENAUNICA</p>")
    tipos = [h.kind for h in detector.analizar(f)]
    assert "REFLEJO" in tipos
    refl = next(h for h in detector.analizar(f) if h.kind == "REFLEJO")
    assert refl.extra["param"] == "q"
    assert "WSTG-INPV-01" in refl.wstg


def test_detector_ignora_valores_de_ruido():
    """Valores cortos o comunes reflejados no son senal."""
    f = _flujo("http://ej.com/b?debug=true&n=1", b"<p>true 1</p>")
    assert [h for h in detector.analizar(f) if h.kind == "REFLEJO"] == []


def test_detector_ve_cookie_sin_atributos():
    f = _flujo("http://ej.com/", b"<html></html>",
               cab_resp=[("Set-Cookie", "sid=abc; Path=/")])
    c = next(h for h in detector.analizar(f) if h.kind == "COOKIE")
    assert "httponly" in c.detail and "secure" in c.detail and "samesite" in c.detail
    assert c.wstg == ["WSTG-SESS-02"]


def test_detector_registra_lo_del_servidor_por_host_no_por_url():
    """Repetir 'falta CSP' en cada ruta es el ruido que hace inutil un reporte."""
    f = _flujo("http://ej.com/una/ruta/larga", b"<html></html>",
               cab_resp=[("Server", "nginx")])
    hs = detector.analizar(f)
    cab = next(h for h in hs if h.kind == "CABECERA")
    fuga = next(h for h in hs if h.kind == "FUGA")
    assert cab.url == "ej.com"       # host, no la ruta completa
    assert fuga.url == "ej.com"


def test_detector_marca_error_de_servidor():
    f = _flujo("http://ej.com/boom", b"<html>Traceback</html>", status=500)
    e = next(h for h in detector.analizar(f) if h.kind == "ERROR")
    assert e.wstg == ["WSTG-ERRH-01"]


def test_detector_no_analiza_flujo_sin_respuesta():
    f = Flow(request=Request(method="GET", url="http://ej.com/",
                             headers=[("Host", "ej.com")]), response=None)
    assert detector.analizar(f) == []


def test_store_confirma_un_hallazgo_y_filtra_por_eso():
    st = Store()
    hid = st.add_finding(Finding(kind="REFLEJO", detail="q se refleja",
                                 url="http://ej.com/b", wstg=["WSTG-INPV-01"]))
    st.add_finding(Finding(kind="FUGA", detail="server: nginx", url="ej.com"))
    assert [h.confirmed for h in st.list_findings() if h.id == hid] == [False]

    st.set_confirmed(hid, True)
    assert [h.id for h in st.list_findings(solo_confirmados=True)] == [hid]
    assert len(st.list_findings()) == 2            # el filtro no es el default
    st.set_confirmed(hid, False)
    assert st.list_findings(solo_confirmados=True) == []
    st.close()


def test_confirmar_sobrevive_al_reinicio(tmp_path):
    """La columna existia en el esquema desde la primera version y nada la
    escribia nunca: este es el primer ida y vuelta real."""
    ruta = tmp_path / "s.db"
    st = Store(ruta)
    hid = st.add_finding(Finding(kind="REFLEJO", detail="q", url="http://ej.com/b"))
    st.set_confirmed(hid, True)
    st.close()
    otra = Store(ruta)
    assert [h.confirmed for h in otra.list_findings() if h.id == hid] == [True]
    otra.close()


def test_store_guarda_y_lee_meta(tmp_path):
    """La tabla meta llevaba en el esquema desde la primera version sin
    que nada la usara. La vista combinada es su primer inquilino."""
    st = Store(tmp_path / "s.db")
    assert st.get_meta("vista", "separadas") == "separadas"
    assert st.get_meta("inexistente") == ""
    st.set_meta("vista", "juntas")
    assert st.get_meta("vista") == "juntas"
    st.set_meta("vista", "separadas")          # sobrescribe, no duplica
    assert st.get_meta("vista") == "separadas"
    st.close()


def test_meta_sobrevive_al_reinicio(tmp_path):
    ruta = tmp_path / "s.db"
    st = Store(ruta)
    st.set_meta("vista", "juntas")
    st.close()
    otra = Store(ruta)
    assert otra.get_meta("vista") == "juntas"
    otra.close()


# ----------------------------------------------- ataques del intruder
def _res(n, **kw):
    kw.setdefault("payloads", [f"p{n}"])
    kw.setdefault("status", 200)
    kw.setdefault("largo", 10 + n)
    kw.setdefault("ms", 5)
    kw.setdefault("error", "")
    kw.setdefault("grep", [])
    return SimpleNamespace(n=n, **kw)


def test_store_guarda_un_ataque_con_sus_resultados(tmp_path):
    st = Store(tmp_path / "s.db")
    aid = st.add_ataque("sniper", "o.com", "GET /?q=§X§ ...", total=3)
    for n in range(3):
        st.add_resultado(aid, _res(n, grep=["AGUJA"] if n == 1 else []))
    st.cerrar_ataque(aid, enviadas=3, abortado=False)

    ataques = st.list_ataques()
    assert len(ataques) == 1
    assert ataques[0]["total"] == 3 and ataques[0]["enviadas"] == 3
    assert ataques[0]["abortado"] == 0
    assert ataques[0]["modo"] == "sniper"

    r = st.list_resultados(aid)
    assert [x["n"] for x in r] == [0, 1, 2]
    assert json.loads(r[1]["grep"]) == ["AGUJA"]
    assert json.loads(r[0]["payloads"]) == ["p0"]
    st.close()


def test_los_resultados_no_entran_al_historial(tmp_path):
    """Decision de diseno: 10.000 filas volverian el historial inservible
    para lo que es, y el detector correria sobre las 10.000 generando
    miles de candidatos basura."""
    st = Store(tmp_path / "s.db")
    aid = st.add_ataque("sniper", "o.com", "x", total=1)
    st.add_resultado(aid, _res(0))
    assert st.count_flows() == 0
    assert st.count_findings() == 0
    st.close()


def test_un_ataque_abortado_queda_marcado(tmp_path):
    st = Store(tmp_path / "s.db")
    aid = st.add_ataque("racimo", "o.com", "x", total=500)
    st.add_resultado(aid, _res(0))
    st.cerrar_ataque(aid, enviadas=1, abortado=True)
    a = st.list_ataques()[0]
    assert a["abortado"] == 1 and a["enviadas"] == 1 and a["total"] == 500
    st.close()


def test_los_resultados_de_un_ataque_no_se_mezclan_con_los_de_otro(tmp_path):
    st = Store(tmp_path / "s.db")
    a1 = st.add_ataque("sniper", "o.com", "x", total=2)
    a2 = st.add_ataque("ariete", "o.com", "y", total=1)
    st.add_resultado(a1, _res(0))
    st.add_resultado(a1, _res(1))
    st.add_resultado(a2, _res(0))
    assert len(st.list_resultados(a1)) == 2
    assert len(st.list_resultados(a2)) == 1
    st.close()


def test_los_ataques_sobreviven_al_reinicio(tmp_path):
    ruta = tmp_path / "s.db"
    st = Store(ruta)
    aid = st.add_ataque("sniper", "o.com", "GET /?q=§X§", total=1)
    st.add_resultado(aid, _res(0, grep=["admin"]))
    st.cerrar_ataque(aid, enviadas=1, abortado=False)
    st.close()

    otra = Store(ruta)
    assert otra.list_ataques()[0]["plantilla"] == "GET /?q=§X§"
    assert json.loads(otra.list_resultados(aid)[0]["grep"]) == ["admin"]
    otra.close()


def test_borrar_un_ataque_se_lleva_sus_resultados(tmp_path):
    st = Store(tmp_path / "s.db")
    aid = st.add_ataque("sniper", "o.com", "x", total=1)
    st.add_resultado(aid, _res(0))
    st.borrar_ataque(aid)
    assert st.list_ataques() == []
    assert st.list_resultados(aid) == []
    st.close()


def test_una_sesion_de_la_0_2_0_se_abre_sin_migracion(tmp_path):
    """Las tablas nuevas van con IF NOT EXISTS: abrir una sesion vieja no
    debe fallar ni perder lo que ya tenia dentro."""
    ruta = tmp_path / "vieja.db"
    con = sqlite3.connect(ruta)
    con.executescript(
        "CREATE TABLE flows (id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "started REAL NOT NULL, duration_ms INTEGER NOT NULL DEFAULT 0, "
        "source TEXT NOT NULL DEFAULT 'proxy', method TEXT NOT NULL, "
        "url TEXT NOT NULL, host TEXT NOT NULL, path TEXT NOT NULL, "
        "req_version TEXT NOT NULL DEFAULT 'HTTP/1.1', "
        "req_headers TEXT NOT NULL DEFAULT '[]', req_body BLOB, "
        "status INTEGER, reason TEXT NOT NULL DEFAULT '', "
        "resp_version TEXT NOT NULL DEFAULT 'HTTP/1.1', "
        "resp_headers TEXT NOT NULL DEFAULT '[]', resp_body BLOB, "
        "content_type TEXT NOT NULL DEFAULT '', size INTEGER NOT NULL DEFAULT 0, "
        "note TEXT NOT NULL DEFAULT '', marked INTEGER NOT NULL DEFAULT 0, "
        "error TEXT NOT NULL DEFAULT '');"
        "INSERT INTO flows (started, method, url, host, path) "
        "VALUES (1.0, 'GET', 'http://o.com/x', 'o.com', '/x');"
    )
    con.commit()
    con.close()

    st = Store(ruta)
    assert st.count_flows() == 1          # lo viejo sigue ahi
    assert st.list_ataques() == []        # lo nuevo existe y esta vacio
    st.close()


def test_el_detector_encuentra_reflejos_con_acentos_en_latin1():
    """Sospecha 7, la cara que de verdad duele: el cuerpo se decodificaba
    como utf-8 pase lo que pase, asi que un reflejo con acentos sobre un
    servidor en iso-8859-1 no se encontraba nunca."""
    valor = "contraseña"
    f = Flow(
        request=Request(method="GET", url=f"http://o.com/b?q={valor}",
                        headers=[("Host", "o.com")]),
        response=Response(status=200,
                          body=f"<html>buscaste: {valor}</html>".encode("latin-1"),
                          headers=[("Content-Type",
                                    "text/html; charset=iso-8859-1")]),
    )
    f.id = 1
    assert any(h.kind == "REFLEJO" for h in detector.analizar(f))


def test_response_charset_lee_el_content_type():
    r = Response(status=200, headers=[("Content-Type", "text/html; charset=latin-1")])
    assert r.charset == "latin-1"
    assert Response(status=200).charset == "utf-8"


def test_count_resultados_acompana_al_limite(tmp_path):
    """Sospecha 4: list_resultados tiene limite=10.000, el mismo fallo
    del historial truncado en otro sitio. Todavia no lo llama nadie, pero
    sin un contador al lado el que lo llame no podra avisar."""
    st = Store(tmp_path / "s.db")
    aid = st.add_ataque("sniper", "o.com", "x", total=25)
    for n in range(25):
        st.add_resultado(aid, _res(n))
    assert st.count_resultados(aid) == 25
    assert len(st.list_resultados(aid, limite=10)) == 10
    assert st.count_resultados(aid + 99) == 0
    st.close()
