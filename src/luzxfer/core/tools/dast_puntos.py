"""Donde se puede inyectar: el modelo de puntos del DAST.

Un `Punto` es un sitio concreto de una peticion donde el escaner puede
poner un payload. Vivia dentro de `dast.py`; sale aqui porque va a crecer
—JSON, cabeceras, cookies, ruta, multipart— y porque el orquestador y el
modelo de puntos son dos cosas distintas.

La regla que manda, y que NO cambia al crecer: **lo que no se entiende no
se trocea**. Partir un cuerpo de tipo desconocido como si fuera un
formulario manda basura al servidor y produce resultados que no
significan nada. JSON se anade ahora solo porque se parsea de verdad.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from urllib.parse import parse_qsl, quote, unquote, urlencode

from . import repeater
from .cuerpo import es_json

# Lo que cuenta como hoja de un JSON. Un booleano o un null NO: meter una
# cadena donde habia `true` es un cambio de tipo, no una inyeccion, y
# produce ruido sin senal. `bool` se excluye a mano porque en Python es
# subclase de int y si no se colaria.
_TIPOS_HOJA = (str, int, float)

# Donde una inyeccion por cabecera es plausible. NO son todas a proposito:
# inyectar en cada cabecera multiplica el trafico y el ruido sin anadir
# senal, y el objetivo del DAST es senal por peticion enviada.
#   User-Agent, Referer -> acaban en logs, paneles y consultas SQL
#   X-Forwarded-*       -> los procesan proxies y la logica de la app
#
# `Host` NO esta, a proposito. Es la unica cabecera que toda peticion
# lleva, asi que incluirla convertiria «aqui no hay nada que inyectar» en
# «escanea siempre», multiplicando el trafico contra el sistema de un
# cliente sin que nadie lo pidiera. Ademas esta herramienta ya trata
# editar el Host como una prueba deliberada y no como una mutacion
# rutinaria (ver el motor y el Intruder). La inyeccion por Host es una
# clase propia de la matriz y se hara con su estrategia, no disparandola
# en cada GET.
CABECERAS_INYECTABLES = ("user-agent", "referer",
                         "x-forwarded-for", "x-forwarded-host")

# Cookies que NO se fuzzean. Medido contra DVWA: inyectar en PHPSESSID y
# en la cookie de configuracion se llevaba un tercio del trafico del
# barrido (36 de 108 peticiones) sin poder encontrar nada util, y la
# cookie `security` ademas CAMBIABA el nivel de dificultad a mitad del
# escaneo: se estaba probando algo distinto de lo que el analista creia.
#
# La exclusion es por nombre conocido y no «todas las cookies»: una cookie
# de la aplicacion —un idioma, un carrito, un id de tenant— es superficie
# legitima y de las mas olvidadas.
COOKIES_DE_SESION = frozenset({
    "phpsessid", "jsessionid", "asp.net_sessionid", "aspsessionid",
    "connect.sid", "laravel_session", "session", "sessionid", "session_id",
    "sid", "security",
    # anti-CSRF: mutarlas rompe la peticion sin probar nada
    "csrftoken", "csrf_token", "_csrf", "xsrf-token", "x-csrf-token",
})


class PayloadNoRepresentable(ValueError):
    """El payload no sobrevive a latin-1, que es como viaja una cabecera.

    `build_raw` codifica la cabeza con `errors="replace"`: un payload con
    acentos, CJK o emoji saldria mutado y lo que se probaria no seria lo
    que se quiso probar. Como el fuzzer muta a proposito, aqui se dice en
    vez de callarlo.
    """


@dataclass(slots=True)
class Punto:
    nombre: str
    valor: str
    donde: str          # "query" | "cuerpo" | "json"
    indice: int         # cual, si el nombre se repite
    # Solo para donde == "json":
    #   `ruta_json` es la ruta punteada, para ensenarla.
    #   `camino` es la de verdad, por la que se sustituye: una clave que
    #   lleve un punto dentro haria que la punteada apuntase a otro sitio.
    ruta_json: str | None = None
    camino: tuple = field(default_factory=tuple)


# ------------------------------------------------------------- utilidades
def _partes(crudo: str):
    metodo, ruta, version, cabeceras, cuerpo = repeater.parse_raw(crudo)
    camino, _, consulta = ruta.partition("?")
    return metodo, camino, consulta, version, cabeceras, cuerpo


def _tipo_contenido(cabeceras: list[tuple[str, str]]) -> str:
    for k, v in cabeceras:
        if k.lower() == "content-type":
            return v
    return ""


def _es_formulario(cabeceras: list[tuple[str, str]]) -> bool:
    return "x-www-form-urlencoded" in _tipo_contenido(cabeceras).lower()


def _hojas_json(obj, camino: tuple = ()):
    """(camino, valor) de cada hoja escalar, en orden de aparicion."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from _hojas_json(v, (*camino, k))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from _hojas_json(v, (*camino, i))
    elif isinstance(obj, _TIPOS_HOJA) and not isinstance(obj, bool):
        yield camino, obj


def _poner_en(obj, camino: tuple, valor):
    """Sustituye la hoja de `camino` por `valor`. Modifica `obj`."""
    for paso in camino[:-1]:
        obj = obj[paso]
    obj[camino[-1]] = valor


def _cuerpo_json(cabeceras, cuerpo: bytes):
    """El JSON del cuerpo, o None si no lo es o no se puede parsear."""
    if not cuerpo or not es_json(_tipo_contenido(cabeceras)):
        return None
    try:
        return json.loads(cuerpo.decode("utf-8", "replace"))
    except ValueError:
        # Un cuerpo que dice ser JSON y no lo es no se trocea a ciegas:
        # inventar puntos sobre basura daria resultados sin significado.
        return None


def _cookies_de(cabeceras) -> list[tuple[str, str]]:
    """(nombre, valor) de cada par del Cookie:, en orden."""
    for k, v in cabeceras:
        if k.lower() == "cookie":
            pares = []
            for trozo in v.split(";"):
                nombre, sep, valor = trozo.partition("=")
                if sep:
                    pares.append((nombre.strip(), valor.strip()))
            return pares
    return []


def _comprobar_latin1(payload: str) -> None:
    try:
        payload.encode("latin-1")
    except UnicodeEncodeError as e:
        raise PayloadNoRepresentable(
            f"el payload no se puede mandar en una cabecera: {payload!r} "
            f"no es representable en latin-1") from e


def _boundary(cabeceras) -> str:
    """El boundary del Content-Type multipart, o cadena vacia."""
    ctype = _tipo_contenido(cabeceras)
    if "multipart/form-data" not in ctype.lower():
        return ""
    for trozo in ctype.split(";"):
        clave, sep, valor = trozo.partition("=")
        if sep and clave.strip().lower() == "boundary":
            return valor.strip().strip('"')
    return ""


def _partes_multipart(cuerpo: str, boundary: str):
    """(nombre, valor, indice) de cada parte con nombre, en orden.

    Se parte por el boundary y se separa la cabecera de la parte de su
    valor por la linea en blanco, igual que manda el formato. Lo que no
    tenga `name=` no es un campo y no se toca.
    """
    sep = f"--{boundary}"
    for i, bloque in enumerate(cuerpo.split(sep)):
        if not bloque.strip() or bloque.startswith("--"):
            continue            # el preambulo y el cierre no son partes
        cabeza, marca, valor = bloque.partition("\r\n\r\n")
        if not marca:
            continue
        nombre = ""
        for trozo in cabeza.split(";"):
            clave, igual, v = trozo.partition("=")
            if igual and clave.strip().lower() == "name":
                nombre = v.strip().strip('"')
        if nombre:
            yield nombre, valor[:-2] if valor.endswith("\r\n") else valor, i


# ---------------------------------------------------------------- puntos
def puntos(crudo: str) -> list[Punto]:
    """Donde se puede inyectar: query, cuerpo de formulario y hojas JSON."""
    try:
        _m, _c, consulta, _v, cabeceras, cuerpo = _partes(crudo)
    except repeater.ErrorPeticion:
        return []

    salida: list[Punto] = []
    for i, (k, v) in enumerate(parse_qsl(consulta, keep_blank_values=True)):
        salida.append(Punto(nombre=k, valor=v, donde="query", indice=i))

    for i, (k, v) in enumerate(cabeceras):
        if k.lower() in CABECERAS_INYECTABLES:
            salida.append(Punto(nombre=k, valor=v, donde="cabecera", indice=i))

    for i, (k, v) in enumerate(_cookies_de(cabeceras)):
        if k.lower() in COOKIES_DE_SESION:
            continue
        salida.append(Punto(nombre=k, valor=v, donde="cookie", indice=i))

    # segmentos de la ruta: alimentan traversal y LFI, donde el parametro
    # no viaja en la query sino dentro del propio camino
    segmentos = [s for s in _c.split("/") if s]
    for i, s in enumerate(segmentos, start=1):
        salida.append(Punto(nombre=str(i), valor=unquote(s),
                            donde="ruta", indice=i))

    boundary = _boundary(cabeceras)
    if cuerpo and boundary:
        texto = cuerpo.decode("utf-8", "replace")
        for nombre, valor, idx in _partes_multipart(texto, boundary):
            salida.append(Punto(nombre=nombre, valor=valor,
                                donde="multipart", indice=idx))
        return salida

    if cuerpo and _es_formulario(cabeceras):
        texto = cuerpo.decode("utf-8", "replace")
        for i, (k, v) in enumerate(parse_qsl(texto, keep_blank_values=True)):
            salida.append(Punto(nombre=k, valor=v, donde="cuerpo", indice=i))
        return salida

    datos = _cuerpo_json(cabeceras, cuerpo)
    if datos is not None:
        for i, (camino, valor) in enumerate(_hojas_json(datos)):
            salida.append(Punto(
                nombre=str(camino[-1]) if camino else "(raiz)",
                valor=str(valor), donde="json", indice=i,
                ruta_json=".".join(str(x) for x in camino), camino=camino))
    return salida


def con_payload(crudo: str, punto: Punto, payload: str) -> str:
    """La misma peticion con ese punto sustituido.

    Query y formulario se codifican con urlencode: un payload con espacios
    o comillas partiria la linea de peticion y no llegaria lo que se queria
    probar sino un trozo. El JSON se re-serializa, asi que las comillas y
    las llaves del payload viajan como valor y no rompen la estructura.
    """
    metodo, camino_url, consulta, version, cabeceras, cuerpo = _partes(crudo)

    def _cambiado(texto: str) -> str:
        pares = parse_qsl(texto, keep_blank_values=True)
        pares[punto.indice] = (punto.nombre, payload)
        return urlencode(pares)

    if punto.donde == "query":
        consulta = _cambiado(consulta)
    elif punto.donde == "cabecera":
        _comprobar_latin1(payload)
        cabeceras = list(cabeceras)
        cabeceras[punto.indice] = (punto.nombre, payload)
    elif punto.donde == "cookie":
        _comprobar_latin1(payload)
        pares = _cookies_de(cabeceras)
        pares[punto.indice] = (punto.nombre, payload)
        junta = "; ".join(f"{k}={v}" for k, v in pares)
        # solo la PRIMERA Cookie, que es de la que se leyeron los pares.
        # Pisar todas borraria las demas y duplicaria esta: mandar la misma
        # cabecera dos veces es una tecnica de prueba, no un error.
        cabeceras = list(cabeceras)
        for i, (k, _v) in enumerate(cabeceras):
            if k.lower() == "cookie":
                cabeceras[i] = (k, junta)
                break
    elif punto.donde == "ruta":
        # se codifica el segmento: un payload con espacios partiria la
        # linea de peticion en tres y no llegaria lo que se queria probar
        trozos = camino_url.split("/")
        vistos = 0
        for i, s in enumerate(trozos):
            if not s:
                continue
            vistos += 1
            if vistos == punto.indice:
                trozos[i] = quote(payload, safe="")
                break
        camino_url = "/".join(trozos)
    elif punto.donde == "multipart":
        texto = cuerpo.decode("utf-8", "replace")
        boundary = _boundary(cabeceras)
        nuevo_cuerpo = _multipart_con(texto, boundary, punto, payload)
        if nuevo_cuerpo is not None:
            cuerpo = nuevo_cuerpo.encode()
            cabeceras = _con_largo(cabeceras, len(cuerpo))
    elif punto.donde == "json":
        datos = _cuerpo_json(cabeceras, cuerpo)
        if datos is not None and punto.camino:
            _poner_en(datos, punto.camino, payload)
            cuerpo = json.dumps(datos, ensure_ascii=False,
                                separators=(",", ":")).encode()
            cabeceras = _con_largo(cabeceras, len(cuerpo))
    else:
        cuerpo = _cambiado(cuerpo.decode("utf-8", "replace")).encode()
        cabeceras = _con_largo(cabeceras, len(cuerpo))

    ruta = f"{camino_url}?{consulta}" if consulta else camino_url
    lineas = [f"{metodo} {ruta} {version}"]
    lineas += [f"{k}: {v}" for k, v in cabeceras]
    return "\r\n".join(lineas) + "\r\n\r\n" + cuerpo.decode("utf-8", "replace")


def _multipart_con(texto: str, boundary: str, punto, payload: str):
    """El cuerpo multipart con el valor de esa parte sustituido.

    Se reconstruye por bloques en vez de con un reemplazo de texto: el
    valor viejo podria aparecer en otra parte, y cambiar la equivocada
    probaria algo distinto de lo que se quiso probar.
    """
    if not boundary:
        return None
    sep = f"--{boundary}"
    bloques = texto.split(sep)
    if not 0 <= punto.indice < len(bloques):
        return None
    bloque = bloques[punto.indice]
    cabeza, marca, valor = bloque.partition("\r\n\r\n")
    if not marca:
        return None
    cola = "\r\n" if valor.endswith("\r\n") else ""
    bloques[punto.indice] = cabeza + marca + payload + cola
    return sep.join(bloques)


def _con_largo(cabeceras, n: int) -> list[tuple[str, str]]:
    """Las cabeceras con el Content-Length puesto al dia, sin duplicarlo."""
    salida = [(k, v) for k, v in cabeceras if k.lower() != "content-length"]
    salida.append(("Content-Length", str(n)))
    return salida
