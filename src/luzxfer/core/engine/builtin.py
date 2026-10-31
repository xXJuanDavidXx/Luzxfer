"""Motor propio: solo libreria estandar, no compila nada.

Es el motor por defecto y el unico viable en Termux, donde no hay wheels
precompilados y cualquier extension en C o Rust se construye en el telefono.

Hace dos cosas:
  - proxy directo (regular): configuras el navegador para usarlo
  - proxy inverso: apuntas el navegador al puerto y el reenvia a un destino

Lo que NO hace, dicho sin rodeos: HTTPS. Interceptar TLS exige una CA propia
y generar certificados por host al vuelo, que es de donde sale la dependencia
pesada. Para eso esta el motor de mitmproxy. Ante un CONNECT responde 501
con el motivo, en vez de fallar en silencio.
"""
from __future__ import annotations

import http.client
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

from ..models import HOP_BY_HOP, Flow, Request, Response
from .base import Engine, EngineInfo

AVISO_CONNECT = (
    b"luzxfer: el motor integrado no intercepta HTTPS.\n\n"
    b"Interceptar TLS necesita una CA propia y generar certificados por host,\n"
    b"que es justo la dependencia pesada que este motor evita a proposito.\n\n"
    b"Para HTTPS usa el motor de mitmproxy:  pip install luzxfer[mitm]\n"
)


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "luzxfer"
    sys_version = ""

    # inyectados por el motor
    engine: Builtin = None  # type: ignore[assignment]

    def log_message(self, *a):   # el log va a la TUI, no al terminal
        pass

    # ------------------------------------------------------------------
    def do_CONNECT(self):
        self.send_response(501, "Not Implemented")
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(AVISO_CONNECT)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(AVISO_CONNECT)

    def _manejar(self):
        inicio = time.time()
        largo = int(self.headers.get("Content-Length") or 0)
        cuerpo = self.rfile.read(largo) if largo else b""

        destino, ruta, url = self.engine._resolver(self.path, self.headers.get("Host", ""))
        if destino is None:
            self._error_simple(400, "no se pudo resolver el destino de la peticion")
            return

        salida: list[tuple[str, str]] = []
        for k, v in self.headers.items():
            if k.lower() in HOP_BY_HOP:
                continue
            if k.lower() == "host":
                v = f"{destino[0]}:{destino[1]}" if destino[1] != 80 else destino[0]
            salida.append((k, v))

        req = Request(method=self.command, url=url, headers=salida, body=cuerpo,
                      http_version=self.request_version)

        try:
            con = http.client.HTTPConnection(destino[0], destino[1], timeout=30)
            con.request(self.command, ruta, body=cuerpo, headers=dict(salida))
            r = con.getresponse()
            datos = r.read()
            cab = [(k, v) for k, v in r.getheaders() if k.lower() not in HOP_BY_HOP]
            resp = Response(status=r.status, reason=r.reason, headers=cab, body=datos)
            con.close()
        except Exception as e:
            flujo = Flow(request=req, response=None, started=inicio,
                         duration_ms=int((time.time() - inicio) * 1000),
                         error=f"{type(e).__name__}: {e}")
            self.engine._emitir(flujo)
            self._error_simple(502, f"luzxfer no pudo conectar con {destino[0]}:{destino[1]}\n\n"
                                    f"{type(e).__name__}: {e}")
            return

        flujo = Flow(request=req, response=resp, started=inicio,
                     duration_ms=int((time.time() - inicio) * 1000))
        self.engine._emitir(flujo)

        self.send_response(resp.status, resp.reason)
        for k, v in resp.headers:
            if k.lower() == "content-length":
                continue
            self.send_header(k, v)
        self.send_header("Content-Length", str(len(resp.body)))
        self.end_headers()
        self.wfile.write(resp.body)

    def _error_simple(self, code: int, texto: str):
        datos = texto.encode()
        self.send_response(code)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(datos)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(datos)

    do_GET = do_POST = do_PUT = do_DELETE = _manejar
    do_PATCH = do_HEAD = do_OPTIONS = _manejar


class Builtin(Engine):
    """Motor integrado. `upstream` activa el modo inverso."""

    def __init__(self, on_flow, *, host="127.0.0.1", port=8080, upstream: str | None = None):
        super().__init__(on_flow, host=host, port=port)
        self.upstream = upstream
        self._srv: ThreadingHTTPServer | None = None
        self._hilo: threading.Thread | None = None

    @staticmethod
    def info() -> EngineInfo:
        return EngineInfo(name="integrado", tls=False, http2=False, websockets=False)

    # ------------------------------------------------------------------
    def _resolver(self, path: str, host_hdr: str):
        """Devuelve ((host, puerto), ruta, url_absoluta).

        Tres formas de llegar aqui: modo inverso (hay upstream), proxy
        directo (la ruta es una URL absoluta) o una peticion normal con Host.
        """
        if self.upstream:
            u = urlsplit(self.upstream)
            destino = (u.hostname or "127.0.0.1", u.port or 80)
            base = f"{u.scheme or 'http'}://{destino[0]}:{destino[1]}"
            return destino, path, f"{base}{path}"

        if path.startswith("http://"):
            u = urlsplit(path)
            destino = (u.hostname or "", u.port or 80)
            ruta = u.path + (f"?{u.query}" if u.query else "")
            return (destino if destino[0] else None), (ruta or "/"), path

        if host_hdr:
            if ":" in host_hdr:
                h, _, p = host_hdr.partition(":")
                destino = (h, int(p))
            else:
                destino = (host_hdr, 80)
            return destino, path, f"http://{host_hdr}{path}"

        return None, path, path

    def _emitir(self, flujo: Flow) -> None:
        try:
            self.on_flow(flujo)
        except Exception:
            pass          # un fallo del consumidor nunca tumba el proxy

    # ------------------------------------------------------------------
    def start(self) -> None:
        if self._running:
            return
        handler = type("_H", (_Handler,), {"engine": self})
        self._srv = ThreadingHTTPServer((self.host, self.port), handler)
        self._srv.daemon_threads = True
        self._hilo = threading.Thread(target=self._srv.serve_forever,
                                      name="luzxfer-engine", daemon=True)
        self._hilo.start()
        self._running = True

    def stop(self) -> None:
        if not self._running:
            return
        if self._srv:
            self._srv.shutdown()
            self._srv.server_close()
        self._srv = None
        self._hilo = None
        self._running = False


def puerto_libre(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind((host, port))
            return True
        except OSError:
            return False
