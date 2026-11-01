"""Mapa del sitio: qué forma tiene la aplicación.

El historial dice en qué orden pasaron las cosas; el mapa dice cómo está
organizado el objetivo. Son dos preguntas distintas y por eso hacen falta
dos vistas: mirando una lista de tres mil peticiones no se ve que hay un
`/admin/` con tres rutas dentro, y eso es justo lo que uno busca.

Se construye del tráfico ya capturado, sin pedir nada al servidor. No es
un rastreador: solo ordena lo que ya pasó por el proxy.

Las query strings NO abren ramas. Tres búsquedas distintas son tres
peticiones a una ruta: si cada query fuera una rama, el árbol tendría el
mismo tamaño que el historial y no serviría para nada.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from urllib.parse import urlsplit

from ..models import Flow


@dataclass(slots=True)
class Nodo:
    nombre: str
    ruta: str = ""                                    # ruta completa, sin host
    hijos: list[Nodo] = field(default_factory=list)
    flujos: list[int] = field(default_factory=list)   # ids, si ya se guardaron
    pedido: int = 0                                   # veces que se pidio ESTA ruta
    total: int = 0                                    # peticiones de todo el subarbol
    estados: set[int] = field(default_factory=set)
    metodos: set[str] = field(default_factory=set)

    @property
    def es_hoja(self) -> bool:
        return not self.hijos

    @property
    def visitado(self) -> bool:
        """Si alguien pidio exactamente esta ruta.

        Un nodo puede existir solo como tramo intermedio: /api aparece
        porque se pidio /api/v1/users, sin que nadie pidiera /api. Esa
        diferencia importa, porque un tramo nunca visitado es justo lo
        que vale la pena probar a mano.

        Se mira `pedido` y no `flujos`: una ruta pedida lo fue aunque el
        flujo todavia no tenga id, y atar las dos cosas haria que el mapa
        de una sesion sin guardar saliera vacio.
        """
        return self.pedido > 0


def _segmentos(ruta: str) -> list[str]:
    """Los tramos de una ruta, sin vacios.

    Las barras repetidas no crean nodos vacios: //api//x es /api/x. Y una
    ruta que es solo "/" devuelve ["/"], para que la raiz tenga su nodo y
    no se pierda entre los demas.
    """
    partes = [p for p in ruta.split("/") if p]
    return partes or ["/"]


def construir(flujos: list[Flow]) -> list[Nodo]:
    """El mapa, una lista de nodos de host ordenados alfabeticamente."""
    hosts: dict[str, Nodo] = {}

    for f in flujos:
        p = urlsplit(f.request.url)
        host = (p.netloc or "").lower()
        if not host:
            continue                      # una URL que no se entiende se ignora

        nodo = hosts.get(host)
        if nodo is None:
            nodo = hosts[host] = Nodo(nombre=host)
        nodo.total += 1

        actual = nodo
        camino = ""
        for seg in _segmentos(p.path or "/"):
            camino = "/" if seg == "/" else f"{camino}/{seg}"
            hijo = next((h for h in actual.hijos if h.nombre == seg), None)
            if hijo is None:
                hijo = Nodo(nombre=seg, ruta=camino)
                actual.hijos.append(hijo)
            hijo.total += 1
            actual = hijo

        # solo el ultimo tramo recibe la peticion: es la ruta que se pidio
        actual.pedido += 1
        if f.id is not None:
            actual.flujos.append(f.id)
        actual.metodos.add(f.request.method)
        if f.response is not None:
            actual.estados.add(f.response.status)

    for nodo in hosts.values():
        _ordenar(nodo)
    return [hosts[h] for h in sorted(hosts)]


def _ordenar(nodo: Nodo) -> None:
    nodo.hijos.sort(key=lambda n: n.nombre)
    for h in nodo.hijos:
        _ordenar(h)


def contar_rutas(raiz: list[Nodo]) -> int:
    """Cuantas rutas distintas se han visto, que no es lo mismo que
    cuantas peticiones: eso ya lo dice el historial."""
    def _contar(n: Nodo) -> int:
        propio = 1 if n.visitado else 0
        return propio + sum(_contar(h) for h in n.hijos)
    return sum(_contar(h) for n in raiz for h in n.hijos)
