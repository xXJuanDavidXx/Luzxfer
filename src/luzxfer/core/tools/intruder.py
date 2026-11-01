"""Intruder: fuzzing dirigido sobre una peticion marcada a mano.

El analista elige la peticion y marca donde va cada payload; la
herramienta no busca puntos de inyeccion por su cuenta. Esa es la misma
autorizacion que ya tiene el repeater, y es la razon de que el Intruder
no necesite un concepto de alcance para ser responsable.

Los marcadores son § como en Burp, para que una peticion copiada de alli
se pegue y funcione. Como § no esta en la mayoria de teclados, la
interfaz lo inserta con una tecla y nunca hace falta escribirlo.

Este modulo no importa nada de tui/: el Intruder tiene que poder correr
sin interfaz.
"""
from __future__ import annotations

import itertools
import math
import threading
from collections.abc import Callable, Iterator
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from . import repeater
from .ritmo import Acelerador

MARCADOR = "§"


class Modo(str, Enum):
    """Como se reparten los payloads entre las posiciones marcadas.

    Los nombres son los de Burp traducidos, porque son los que el usuario
    ya tiene en la cabeza. Los cuatro comparten el mismo motor de envio:
    lo unico que cambia es esta combinatoria.
    """

    SNIPER = "sniper"          # una posicion a la vez, un solo conjunto
    ARIETE = "ariete"          # el mismo payload en todas a la vez
    HORQUILLA = "horquilla"    # los conjuntos en paralelo
    RACIMO = "racimo"          # producto cartesiano


class ErrorAtaque(ValueError):
    """La peticion o la configuracion no sirven para lanzar un ataque."""


def posiciones(crudo: str) -> list[tuple[int, int]]:
    """Los pares (inicio, fin) del contenido entre marcadores.

    Los indices son del texto tal cual, marcadores incluidos, y delimitan
    lo que hay DENTRO de cada par. Un numero impar de marcadores es un
    error y no una posicion a medias: un ataque silenciosamente raro es
    peor que uno que se niega a empezar.
    """
    trozos = crudo.split(MARCADOR)
    if len(trozos) % 2 == 0:
        raise ErrorAtaque(
            f"hay un numero impar de marcadores {MARCADOR}: "
            f"{crudo.count(MARCADOR)}. Cada posicion necesita uno al "
            f"principio y otro al final."
        )

    salida: list[tuple[int, int]] = []
    pos = 0
    # los trozos impares son los que estan dentro de un par
    for i, t in enumerate(trozos):
        if i % 2 == 1:
            salida.append((pos, pos + len(t)))
        pos += len(t) + len(MARCADOR)
    return salida


def valores_iniciales(crudo: str) -> list[str]:
    """Lo que hay dentro de cada par, que sirve de payload por defecto.

    En sniper las posiciones que no se estan atacando conservan esto, y
    por eso el ataque sigue siendo una peticion valida.
    """
    trozos = crudo.split(MARCADOR)
    if len(trozos) % 2 == 0:
        raise ErrorAtaque(f"hay un numero impar de marcadores {MARCADOR}")
    return [t for i, t in enumerate(trozos) if i % 2 == 1]


def sustituir(crudo: str, payloads: list[str]) -> str:
    """Reemplaza cada par de marcadores por su payload.

    De una sola pasada, reconstruyendo desde los trozos: si un payload
    contiene un § no se vuelve una posicion nueva.
    """
    trozos = crudo.split(MARCADOR)
    if len(trozos) % 2 == 0:
        raise ErrorAtaque(f"hay un numero impar de marcadores {MARCADOR}")
    n = len(trozos) // 2
    if len(payloads) != n:
        raise ErrorAtaque(
            f"hacen falta {n} payload(s), uno por posicion, y llegaron "
            f"{len(payloads)}"
        )

    partes = []
    for i, t in enumerate(trozos):
        partes.append(payloads[i // 2] if i % 2 == 1 else t)
    return "".join(partes)


def marcar(crudo: str, inicio: int, fin: int) -> str:
    """Envuelve ese rango en marcadores. Es lo que hace la tecla."""
    if not 0 <= inicio <= fin <= len(crudo):
        raise ErrorAtaque(
            f"rango invalido ({inicio}, {fin}) sobre un texto de "
            f"{len(crudo)} caracteres"
        )
    return (f"{crudo[:inicio]}{MARCADOR}{crudo[inicio:fin]}"
            f"{MARCADOR}{crudo[fin:]}")


def avisos_de_codificacion(payloads: list[str]) -> list[str]:
    """Los payloads que no sobreviven al viaje, sin repetir.

    build_raw() codifica la peticion en latin-1 con errors='replace', asi
    que un payload con CJK o emoji llegaria mutado al servidor. Un fuzzer
    que cambia tus payloads sin decirlo es peor que uno que se niega a
    mandarlos: el resultado parece valido y no lo es.
    """
    malos: list[str] = []
    for p in payloads:
        try:
            p.encode("latin-1")
        except UnicodeEncodeError:
            if p not in malos:
                malos.append(p)
    return malos


# ---------------------------------------------------------------------
def _validar(modo: Modo, conjuntos: list[list[str]], n_pos: int) -> None:
    """Todo lo que puede estar mal, comprobado de una vez.

    Se llama antes de generar nada y antes de abrir ningun socket:
    descubrir que la configuracion estaba mal en la peticion 300 es tarde
    cuando las 300 ya salieron hacia el sistema de un cliente.
    """
    if n_pos < 1:
        raise ErrorAtaque(
            f"no hay ninguna posicion marcada. Envuelve en {MARCADOR} lo "
            f"que quieras fuzzear."
        )
    if not conjuntos or any(not c for c in conjuntos):
        raise ErrorAtaque("hay un conjunto de payloads vacio")
    if modo in (Modo.HORQUILLA, Modo.RACIMO) and len(conjuntos) != n_pos:
        raise ErrorAtaque(
            f"{modo.value} necesita un conjunto de payloads por posicion: "
            f"hay {n_pos} posicion(es) y {len(conjuntos)} conjunto(s)."
        )


def cuantas(modo: Modo, conjuntos: list[list[str]], n_pos: int) -> int:
    """Cuantas peticiones saldrian, SIN generarlas.

    Existe para poder avisar antes de lanzar: un racimo de tres listas de
    cien son un millon de peticiones, y eso hay que verlo antes y no
    cuando ya van por la mitad.
    """
    _validar(modo, conjuntos, n_pos)
    if modo is Modo.SNIPER:
        return len(conjuntos[0]) * n_pos
    if modo is Modo.ARIETE:
        return len(conjuntos[0])
    if modo is Modo.HORQUILLA:
        return min(len(c) for c in conjuntos)
    return math.prod(len(c) for c in conjuntos)


def combinar(
    modo: Modo,
    conjuntos: list[list[str]],
    n_pos: int,
    base: list[str],
) -> Iterator[list[str]]:
    """Las sustituciones del ataque, una lista de n_pos payloads cada vez.

    Perezoso a proposito: un racimo grande no cabe en memoria y tampoco
    hace falta, porque se envia segun se genera.

    `base` son los valores iniciales de cada posicion, que sniper conserva
    en las posiciones que no esta atacando.
    """
    _validar(modo, conjuntos, n_pos)

    if modo is Modo.SNIPER:
        def gen() -> Iterator[list[str]]:
            for i in range(n_pos):
                for p in conjuntos[0]:
                    fila = list(base)
                    fila[i] = p
                    yield fila
        return gen()

    if modo is Modo.ARIETE:
        return ([p] * n_pos for p in conjuntos[0])

    if modo is Modo.HORQUILLA:
        # strict=False es la semantica de horquilla, no un descuido: con
        # listas de distinto largo el ataque para en la mas corta, igual
        # que en Burp. Con strict=True reventaria en vez de parar.
        return (list(fila) for fila in zip(*conjuntos, strict=False))

    return (list(fila) for fila in itertools.product(*conjuntos))


# ------------------------------------------------- fuentes de payloads
def desde_archivo(ruta: str | Path, *, limite: int = 1_000_000) -> list[str]:
    """Una linea, un payload. Ignora vacias y las que empiezan por '#'.

    Se lee con errors='replace' porque las listas de payloads de verdad
    —rockyou, SecLists— no son utf-8 limpio, y negarse a abrirlas por un
    byte suelto seria inutil.

    Solo se quita el salto de linea, no los espacios: en "' or 1=1 -- "
    el espacio final es parte del payload.
    """
    p = Path(ruta)
    try:
        texto = p.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        raise ErrorAtaque(f"no se pudo leer {p}: {e}") from e

    salida: list[str] = []
    for linea in texto.splitlines():
        limpia = linea.rstrip("\r")
        if not limpia.strip() or limpia.lstrip().startswith("#"):
            continue
        salida.append(limpia)
        if len(salida) >= limite:
            break
    return salida


def desde_rango(desde: int, hasta: int, paso: int = 1, *, ancho: int = 0) -> list[str]:
    """Numeros de `desde` a `hasta`, ambos incluidos.

    `ancho` rellena con ceros a la izquierda, para IDs tipo 00042 que es
    como los escriben muchas aplicaciones.
    """
    if paso == 0:
        raise ErrorAtaque("el paso no puede ser cero")
    if hasta < desde:
        raise ErrorAtaque(f"el rango va al reves: {desde} > {hasta}")
    return [str(n).zfill(ancho) for n in range(desde, hasta + 1, paso)]


def desde_texto(texto: str) -> list[str]:
    """Una por linea, que es lo que se teclea en la pantalla."""
    return [ln for ln in texto.splitlines() if ln.strip()]


# ---------------------------------------------------- el motor de ataque
@dataclass(slots=True)
class Resultado:
    """Una peticion del ataque y lo que contesto el servidor."""
    n: int
    payloads: list[str]
    status: int | None = None
    largo: int = 0
    ms: int = 0
    error: str = ""
    grep: list[str] = field(default_factory=list)


@dataclass(slots=True)
class Config:
    """Como se lanza el ataque.

    Los valores por defecto son prudentes a proposito: esto se dispara
    contra sistemas de otros. Un Intruder que de fabrica tumba el entorno
    de un cliente es una llamada telefonica, no un hallazgo. Subirlo es
    una decision que el analista toma a la vista del objetivo.
    """
    modo: Modo
    conjuntos: list[list[str]]
    concurrencia: int = 4
    por_segundo: float = 10.0
    grep: list[str] = field(default_factory=list)
    tls: bool | None = None
    timeout: float = 15.0


class Ataque:
    """Un ataque configurado y listo para lanzar.

    Todo lo que puede estar mal se comprueba en el constructor, antes de
    abrir ningun socket: la peticion, los marcadores, los conjuntos y el
    total. `total` y `avisos` estan disponibles sin lanzar, que es lo que
    permite enseniarlos y pedir confirmacion antes de mandar nada.
    """

    def __init__(self, crudo: str, cfg: Config):
        self.crudo = crudo
        self.cfg = cfg
        self.base = valores_iniciales(crudo)        # valida los marcadores
        self._n_pos = len(self.base)
        self.total = cuantas(cfg.modo, cfg.conjuntos, self._n_pos)
        self.avisos = avisos_de_codificacion(
            [p for c in cfg.conjuntos for p in c])
        self.enviadas = 0
        self.terminado = False
        self._parar = threading.Event()
        self._lock = threading.Lock()

    @property
    def abortado(self) -> bool:
        return self._parar.is_set()

    def abortar(self) -> None:
        """Corta el ataque. Idempotente y seguro desde cualquier hilo.

        No se matan los sockets que ya estan en vuelo: se dejan terminar
        con su timeout. Cortar a mitad dejaria la peticion enviada y la
        respuesta sin leer, que es el estado que uno menos quiere en el
        sistema de un cliente.
        """
        self._parar.set()

    def correr(self, on_resultado: Callable[[Resultado], None]) -> None:
        """Lanza el ataque. Bloquea: llamalo desde un hilo.

        `on_resultado` se invoca desde los hilos trabajadores, pero
        serializado bajo un lock, asi que no hace falta que sea seguro
        entre hilos. Lo que SI hace falta, en una interfaz, es saltar al
        propio bucle —en Textual con call_from_thread—, el mismo contrato
        que ya tiene Engine.on_flow.
        """
        acelerador = Acelerador(self.cfg.por_segundo)
        combos = combinar(self.cfg.modo, self.cfg.conjuntos,
                          self._n_pos, self.base)
        obreros = max(1, self.cfg.concurrencia)

        def trabajo(n: int, payloads: list[str]) -> None:
            if self._parar.is_set():
                return
            acelerador.esperar()
            if self._parar.is_set():       # pudo abortarse durante la espera
                return

            flujo = repeater.send_raw(
                sustituir(self.crudo, payloads),
                tls=self.cfg.tls, timeout=self.cfg.timeout,
            )
            r = Resultado(n=n, payloads=payloads, error=flujo.error,
                          ms=flujo.duration_ms)
            if flujo.response is not None:
                r.status = flujo.response.status
                r.largo = len(flujo.response.body)
                if self.cfg.grep:
                    cuerpo = flujo.response.text()
                    r.grep = [g for g in self.cfg.grep if g in cuerpo]
            with self._lock:
                self.enviadas += 1
                on_resultado(r)

        # Se mantienen pocos futuros vivos a la vez en vez de encolarlo
        # todo: un racimo de un millon no cabe ni como lista de futuros.
        tope = obreros * 4
        pendientes: set[Future] = set()
        try:
            with ThreadPoolExecutor(max_workers=obreros,
                                    thread_name_prefix="luzxfer-intruder") as ex:
                for n, payloads in enumerate(combos):
                    if self._parar.is_set():
                        break
                    pendientes.add(ex.submit(trabajo, n, payloads))
                    if len(pendientes) >= tope:
                        _, pendientes = wait(pendientes,
                                             return_when=FIRST_COMPLETED)
                wait(pendientes)
        finally:
            self.terminado = True


SEPARADOR_CONJUNTOS = "---"


def conjuntos_desde_texto(texto: str, *, limite: int = 1_000_000) -> list[list[str]]:
    """Los conjuntos de payloads tal como se escriben en la pantalla.

    Una linea con solo '---' separa un conjunto del siguiente, que es lo
    que hace falta para horquilla y racimo sin montar una interfaz con un
    cuadro por posicion.

    Una linea que empieza por '@' es la ruta de un archivo y se expande
    ahi mismo: pegar rockyou a mano en un cuadro de texto no es viable.
    """
    conjuntos: list[list[str]] = []
    actual: list[str] = []
    for linea in texto.splitlines():
        if linea.strip() == SEPARADOR_CONJUNTOS:
            if actual:
                conjuntos.append(actual)
            actual = []
            continue
        if linea.startswith("@"):
            actual.extend(desde_archivo(linea[1:].strip(), limite=limite))
            continue
        if linea.strip():
            actual.append(linea)
    if actual:
        conjuntos.append(actual)
    return conjuntos
