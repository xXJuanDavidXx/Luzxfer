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
from urllib.parse import parse_qsl, urlencode

from . import repeater
from .cuerpo import es_json

# Lo que cuenta como hoja de un JSON. Un booleano o un null NO: meter una
# cadena donde habia `true` es un cambio de tipo, no una inyeccion, y
# produce ruido sin senal. `bool` se excluye a mano porque en Python es
# subclase de int y si no se colaria.
_TIPOS_HOJA = (str, int, float)


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


def _con_largo(cabeceras, n: int) -> list[tuple[str, str]]:
    """Las cabeceras con el Content-Length puesto al dia, sin duplicarlo."""
    salida = [(k, v) for k, v in cabeceras if k.lower() != "content-length"]
    salida.append(("Content-Length", str(n)))
    return salida
