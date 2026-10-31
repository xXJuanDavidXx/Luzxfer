"""Piezas compartidas por los tests.

El servidor de eco vive aqui y no dentro de un archivo de tests para
que lo usen varios: las regresiones del proxy y del repeater, y los
ataques del Intruder. Duplicarlo seria tener dos objetivos que se van
separando sin que nadie se entere.
"""
from __future__ import annotations

import gzip
import http.server
import json
import threading
import time

import pytest


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

