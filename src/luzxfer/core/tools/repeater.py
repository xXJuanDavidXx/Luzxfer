"""Repeater: manda una peticion HTTP cruda, editada a mano.

Es la herramienta que mas se usa en un pentest y la que mas se extrana
cuando no esta. La regla de diseno es una: lo que escribes es lo que viaja,
salvo Content-Length, que se recalcula porque editar a mano y olvidarlo es
el error numero uno.
"""
from __future__ import annotations

import http.client
import time

from ..models import HOP_BY_HOP, Flow, Request, Response


class ErrorPeticion(ValueError):
    """La peticion cruda no se pudo interpretar."""


def parse_raw(texto: str) -> tuple[str, str, str, list[tuple[str, str]], bytes]:
    """Separa una peticion cruda en (metodo, ruta, version, cabeceras, cuerpo)."""
    texto = texto.replace("\r\n", "\n")
    cabeza, _, cuerpo = texto.partition("\n\n")
    lineas = [ln for ln in cabeza.split("\n") if ln.strip()]
    if not lineas:
        raise ErrorPeticion("la peticion esta vacia")

    partes = lineas[0].split()
    if len(partes) < 2:
        raise ErrorPeticion(f"primera linea invalida: {lineas[0]!r}")
    metodo, ruta = partes[0], partes[1]
    version = partes[2] if len(partes) > 2 else "HTTP/1.1"

    cabeceras: list[tuple[str, str]] = []
    for ln in lineas[1:]:
        if ":" not in ln:
            raise ErrorPeticion(f"cabecera sin dos puntos: {ln!r}")
        k, v = ln.split(":", 1)
        cabeceras.append((k.strip(), v.strip()))

    return metodo, ruta, version, cabeceras, cuerpo.encode()


def destino_de(cabeceras: list[tuple[str, str]]) -> tuple[str, int] | None:
    for k, v in cabeceras:
        if k.lower() == "host":
            v = v.strip()
            if ":" in v:
                h, _, p = v.partition(":")
                try:
                    return h, int(p)
                except ValueError:
                    return h, 80
            return v, 80
    return None


def send_raw(
    texto: str,
    *,
    host: str | None = None,
    port: int | None = None,
    recalcular_cl: bool = True,
    timeout: float = 30.0,
) -> Flow:
    """Manda la peticion y devuelve el Flow, con error dentro si fallo."""
    metodo, ruta, version, cabeceras, cuerpo = parse_raw(texto)

    objetivo = (host, port) if host else destino_de(cabeceras)
    if not objetivo or not objetivo[0]:
        raise ErrorPeticion(
            "no hay cabecera Host y no se indico destino. "
            "Agrega 'Host: servidor:puerto' o pasa el destino aparte."
        )
    h, p = objetivo[0], (port or objetivo[1] or 80)

    enviar = [(k, v) for k, v in cabeceras if k.lower() not in HOP_BY_HOP]
    if recalcular_cl:
        enviar = [(k, v) for k, v in enviar if k.lower() != "content-length"]
        if cuerpo:
            enviar.append(("Content-Length", str(len(cuerpo))))

    url = f"http://{h}:{p}{ruta}" if p != 80 else f"http://{h}{ruta}"
    req = Request(method=metodo, url=url, http_version=version,
                  headers=enviar, body=cuerpo)

    inicio = time.time()
    try:
        con = http.client.HTTPConnection(h, p, timeout=timeout)
        con.request(metodo, ruta, body=cuerpo, headers=dict(enviar))
        r = con.getresponse()
        datos = r.read()
        cab = [(k, v) for k, v in r.getheaders() if k.lower() not in HOP_BY_HOP]
        resp = Response(status=r.status, reason=r.reason, headers=cab, body=datos)
        con.close()
        return Flow(request=req, response=resp, started=inicio,
                    duration_ms=int((time.time() - inicio) * 1000), source="repeater")
    except Exception as e:
        return Flow(request=req, response=None, started=inicio,
                    duration_ms=int((time.time() - inicio) * 1000),
                    source="repeater", error=f"{type(e).__name__}: {e}")
