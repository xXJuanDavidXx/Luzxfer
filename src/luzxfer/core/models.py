"""Modelos del nucleo.

Todo lo que cruza la herramienta pasa por estas estructuras: el motor las
produce, el almacen las persiste y la TUI las muestra. Mantenerlas simples
y sin dependencias es lo que permite cambiar de motor sin tocar nada mas.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

# Cabeceras que pertenecen a la conexion y no al mensaje. No se reenvian.
HOP_BY_HOP = frozenset({
    "connection", "keep-alive", "proxy-authenticate", "proxy-authorization",
    "te", "trailers", "transfer-encoding", "upgrade",
})


@dataclass(slots=True)
class Request:
    method: str
    url: str
    http_version: str = "HTTP/1.1"
    headers: list[tuple[str, str]] = field(default_factory=list)
    body: bytes = b""

    def header(self, name: str) -> str | None:
        low = name.lower()
        for k, v in self.headers:
            if k.lower() == low:
                return v
        return None

    @property
    def path(self) -> str:
        """Ruta con query, que es lo que va en la linea de peticion."""
        from urllib.parse import urlsplit
        p = urlsplit(self.url)
        return p.path + (f"?{p.query}" if p.query else "") or "/"

    @property
    def host(self) -> str:
        from urllib.parse import urlsplit
        return urlsplit(self.url).netloc

    def raw(self) -> str:
        """La peticion tal como viaja. Es lo que se edita en el repeater."""
        lineas = [f"{self.method} {self.path} {self.http_version}"]
        lineas += [f"{k}: {v}" for k, v in self.headers]
        texto = "\r\n".join(lineas) + "\r\n\r\n"
        if self.body:
            texto += self.body.decode("utf-8", "replace")
        return texto


@dataclass(slots=True)
class Response:
    status: int
    reason: str = ""
    http_version: str = "HTTP/1.1"
    headers: list[tuple[str, str]] = field(default_factory=list)
    body: bytes = b""

    def header(self, name: str) -> str | None:
        low = name.lower()
        for k, v in self.headers:
            if k.lower() == low:
                return v
        return None

    def headers_all(self, name: str) -> list[str]:
        """Todas las apariciones. Set-Cookie puede venir varias veces."""
        low = name.lower()
        return [v for k, v in self.headers if k.lower() == low]

    @property
    def content_type(self) -> str:
        return (self.header("content-type") or "").split(";")[0].strip()

    def text(self, limite: int | None = None) -> str:
        datos = self.body if limite is None else self.body[:limite]
        return datos.decode("utf-8", "replace")

    def raw_headers(self) -> str:
        linea = f"{self.http_version} {self.status} {self.reason}".rstrip()
        return "\r\n".join([linea] + [f"{k}: {v}" for k, v in self.headers])


@dataclass(slots=True)
class Flow:
    """Una peticion con su respuesta. La unidad de todo el programa."""
    request: Request
    response: Response | None = None
    id: int | None = None
    started: float = field(default_factory=time.time)
    duration_ms: int = 0
    source: str = "proxy"        # proxy | repeater | intruder
    note: str = ""
    marked: bool = False
    error: str = ""

    @property
    def status(self) -> int | None:
        return self.response.status if self.response else None

    @property
    def size(self) -> int:
        return len(self.response.body) if self.response else 0


@dataclass(slots=True)
class Finding:
    """Un candidato o un hallazgo confirmado, atado a sus flujos de evidencia.

    `wstg` guarda los IDs de la OWASP WSTG que aplican. Esa es la pieza que
    convierte un historial en cobertura de metodologia.
    """
    kind: str                       # REFLEJO, COOKIE, CABECERA, FUGA, manual...
    detail: str
    url: str
    id: int | None = None
    flow_ids: list[int] = field(default_factory=list)
    wstg: list[str] = field(default_factory=list)
    severity: str = ""              # info, low, medium, high, critical
    cvss_vector: str = ""
    justification: str = ""
    confirmed: bool = False         # validado a mano, no solo detectado
    created: float = field(default_factory=time.time)
    extra: dict[str, Any] = field(default_factory=dict)
