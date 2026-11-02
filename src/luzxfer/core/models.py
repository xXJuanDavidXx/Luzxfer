"""Modelos del nucleo.

Todo lo que cruza la herramienta pasa por estas estructuras: el motor las
produce, el almacen las persiste y la TUI las muestra. Mantenerlas simples
y sin dependencias es lo que permite cambiar de motor sin tocar nada mas.
"""
from __future__ import annotations

import codecs
import gzip
import time
import zlib
from dataclasses import dataclass, field
from typing import Any

# Cabeceras que pertenecen a la conexion y no al mensaje. No se reenvian.
HOP_BY_HOP = frozenset({
    "connection", "keep-alive", "proxy-authenticate", "proxy-authorization",
    "te", "trailers", "transfer-encoding", "upgrade",
})

# Cabeceras con las que el cliente dice «ya tengo una copia». El servidor
# contesta 304 sin cuerpo, y un cuerpo vacio es un detector ciego: busca
# reflejos en la nada y devuelve cero sin explicar por que. En un pentest
# esto pasa en cada recarga, no es un caso raro.
#
# No se tocan If-Range (da 206, otro problema) ni Cache-Control, que el
# analista puede querer para otras cosas.
VALIDADORES_CACHE = frozenset({"if-none-match", "if-modified-since"})

try:                                    # extra opcional: pip install luzxfer[br]
    import brotli as _brotli
except ImportError:
    try:
        import brotlicffi as _brotli  # la variante cffi, misma interfaz
    except ImportError:
        _brotli = None                  # type: ignore[assignment]

try:
    # zstd entro en la stdlib en Python 3.14, sin compilar nada: encaja en
    # la regla de cero dependencias nativas. Los navegadores ya lo piden
    # (Accept-Encoding: ... zstd), asi que sin esto el detector se queda
    # ciego ante un servidor que lo use, igual que pasaba con brotli.
    from compression import zstd as _zstd
except ImportError:
    _zstd = None                        # type: ignore[assignment]

# Lo que luzxfer sabe deshacer, y la UNICA fuente de verdad sobre eso: el
# motor la usa para recortar el Accept-Encoding que manda al servidor, y la
# interfaz para avisar cuando un cuerpo quedo sin decodificar. Dos listas
# que se separen con el tiempo serian un cuerpo ilegible sin aviso.
CODIFICACIONES_LEGIBLES = frozenset(
    {"gzip", "x-gzip", "deflate", "identity"}
    | ({"br"} if _brotli else set())
    | ({"zstd"} if _zstd else set())
)


def charset_de(ctype: str) -> str:
    """El charset declarado en un Content-Type, o utf-8 si no hay.

    Importa mas de lo que parece: decodificarlo todo como utf-8 convierte
    los acentos de un servidor en iso-8859-1 en caracteres de reemplazo,
    en silencio. Y como el detector mira ese mismo texto, un reflejo con
    acentos dejaba de encontrarse.

    Un charset inexistente cae a utf-8 en vez de lanzar: el Content-Type
    lo escribe el servidor y puede poner lo que le de la gana.
    """
    for parte in (ctype or "").split(";")[1:]:
        clave, _, valor = parte.partition("=")
        if clave.strip().lower() == "charset":
            nombre = valor.strip().strip('"').strip("'").lower()
            try:
                codecs.lookup(nombre)
            except (LookupError, ValueError):
                return "utf-8"
            return nombre or "utf-8"
    return "utf-8"


def filtrar_accept_encoding(valor: str) -> str:
    """Recorta un Accept-Encoding a lo que luzxfer sabe deshacer.

    Sin esto, un servidor moderno contesta en brotli —el default de nginx,
    de Cloudflare y del middleware de compresion de Express— y el dano no
    es solo que el cuerpo salga ilegible en pantalla: el detector busca
    reflejos en los bytes comprimidos y no encuentra NADA. Es un falso
    negativo silencioso, el mismo fallo que ya se corrigio para gzip, y hoy
    es el caso comun y no el raro.

    Se recorta en vez de reemplazar, conservando orden y parametros q=:
    cuanto menos se toque la peticion del cliente, menos se cambia lo que
    el servidor decide. El comodin '*' no sobrevive, porque deja al
    servidor elegir y eso incluye justo lo que no sabemos leer.
    """
    partes = [
        p.strip() for p in valor.split(",")
        if p.split(";")[0].strip().lower() in CODIFICACIONES_LEGIBLES
    ]
    return ", ".join(partes) if partes else "identity"


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

    @property
    def encoding(self) -> str:
        return (self.header("content-encoding") or "").strip().lower()

    def decoded_body(self) -> bytes:
        """El cuerpo descomprimido, para leerlo y analizarlo.

        `body` se guarda tal como vino del servidor (es lo que se reenvia y
        es la evidencia). Pero buscar reflejos en bytes gzip no encuentra
        nada, y los objetivos reales comprimen casi todo el HTML.

        Brotli no esta en la stdlib. Hay dos respuestas y las dos estan
        puestas: el motor recorta el Accept-Encoding para que el servidor
        no lo use (filtrar_accept_encoding), y si ademas esta instalado el
        extra [br] se descomprime aqui. Si ni lo uno ni lo otro, el cuerpo
        queda tal cual y la interfaz lo dice en vez de callarlo.
        """
        enc = self.encoding
        if not enc or enc == "identity":
            return self.body
        try:
            if enc in ("gzip", "x-gzip"):
                return gzip.decompress(self.body)
            if enc == "deflate":
                try:
                    return zlib.decompress(self.body)
                except zlib.error:            # deflate crudo, sin cabecera zlib
                    return zlib.decompress(self.body, -zlib.MAX_WBITS)
            if enc == "br" and _brotli is not None:
                return _brotli.decompress(self.body)
            if enc == "zstd" and _zstd is not None:
                return _zstd.decompress(self.body)
        except Exception:
            # Amplio a proposito: esto procesa bytes de un servidor hostil, y
            # cada descompresor lanza lo suyo. Un cuerpo corrupto se muestra
            # tal cual; tumbar la interfaz seria el peor resultado posible.
            pass
        return self.body

    def sin_decodificar(self) -> bool:
        """Si el cuerpo quedo comprimido porque no sabemos deshacerlo."""
        return bool(self.encoding) and self.encoding not in CODIFICACIONES_LEGIBLES

    @property
    def charset(self) -> str:
        return charset_de(self.header("content-type") or "")

    def text(self, limite: int | None = None) -> str:
        datos = self.decoded_body()
        if limite is not None:
            datos = datos[:limite]
        return datos.decode(self.charset, "replace")

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
    # las rutas por las que paso una cadena de redirecciones, si se
    # siguio. Vacio es lo normal: por donde paso importa tanto como
    # donde acabo.
    saltos: list[str] = field(default_factory=list)

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
