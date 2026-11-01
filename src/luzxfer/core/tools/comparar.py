"""Comparar dos flujos: que cambio entre uno y otro.

«¿Que cambio entre estas dos respuestas?» es la pregunta que sigue a
casi todo lo que hace el Intruder: la misma peticion con otro payload,
o con otra sesion, y la diferencia es el hallazgo.

Se comparan los cuerpos DESCOMPRIMIDOS, por la misma razon que la
busqueda descomprime: dos respuestas con el mismo contenido pueden
tener bytes gzip distintos —basta con que el servidor ponga otra marca
de tiempo— y comparar lo guardado diria que difieren cuando son
iguales. El fallo es menos llamativo que los de antes pero igual de
traicionero: invita a buscar una diferencia que no existe.
"""
from __future__ import annotations

import difflib

from ..models import Flow

LADOS = ("peticion", "respuesta")


def _texto_de(flujo: Flow, lado: str) -> list[str]:
    """Las lineas que se comparan de un lado de un flujo."""
    if lado == "peticion":
        r = flujo.request
        lineas = [f"{r.method} {r.path} {r.http_version}"]
        lineas += [f"{k}: {v}" for k, v in r.headers]
        lineas.append("")
        lineas += r.body.decode("utf-8", "replace").splitlines()
        return lineas

    p = flujo.response
    if p is None:
        return [f"(sin respuesta{': ' + flujo.error if flujo.error else ''})"]
    lineas = [f"{p.http_version} {p.status} {p.reason}".rstrip()]
    lineas += [f"{k}: {v}" for k, v in p.headers]
    lineas.append("")
    lineas += p.decoded_body().decode("utf-8", "replace").splitlines()
    return lineas


def diferencias(a: Flow, b: Flow, lado: str,
                limite: int = 2000) -> list[tuple[str, str]]:
    """(marca, linea) por cada linea: ' ' igual, '-' solo en a, '+' solo en b.

    Se recorta a `limite` lineas y se dice: una diferencia de diez mil
    lineas no se lee, y pintarla entera solo cuesta tiempo.
    """
    if lado not in LADOS:
        raise ValueError(f"lado desconocido: {lado!r}; hay: {', '.join(LADOS)}")

    izq, der = _texto_de(a, lado), _texto_de(b, lado)
    salida: list[tuple[str, str]] = []
    for linea in difflib.Differ().compare(izq, der):
        marca, _, resto = linea[0], linea[1], linea[2:]
        if marca == "?":
            continue            # las guias de Differ estorban mas que ayudan
        salida.append((marca, resto))
        if len(salida) >= limite:
            salida.append((" ", f"… (recortado a {limite} lineas)"))
            break
    return salida


def cuantas(d: list[tuple[str, str]]) -> tuple[int, int]:
    """(quitadas, puestas)."""
    return (sum(1 for t, _ in d if t == "-"),
            sum(1 for t, _ in d if t == "+"))
