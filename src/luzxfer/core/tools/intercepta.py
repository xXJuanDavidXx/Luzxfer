"""Interceptación: parar una petición antes de que salga.

Es la diferencia entre luzxfer y un visor de tráfico. Hasta ahora, cuando
veías una petición ya había llegado al servidor y el repeater mandaba una
*segunda*; contra un token de un solo uso, un CSRF que se quema o un pago
irrepetible, eso no sirve. Aquí la petición se detiene, la editas, y sale
la tuya o no sale ninguna.

**Cruza hilos.** `detener()` se llama desde el hilo del motor y bloquea;
la interfaz vive en otro bucle y resuelve desde allí. Todo lo delicado de
este módulo es que nadie se quede colgado:

  - si la interfaz no contesta, la petición sale sola al cabo del timeout;
  - si se apaga la interceptación, lo detenido sale de inmediato;
  - si la aplicación cierra, nada queda esperando una decisión que no va
    a llegar.

Y la regla que manda sobre todas: **ante la duda, la petición SALE.**
Dejar colgado el navegador del analista, o tragarse su tráfico en
silencio, es peor que dejar pasar algo que quizá quería mirar.
"""
from __future__ import annotations

import itertools
import threading
from collections.abc import Callable
from dataclasses import dataclass, field

SOLTAR = "soltar"
DESCARTAR = "descartar"

TIMEOUT_DEFECTO = 120.0


@dataclass(slots=True)
class Detenida:
    """Una petición parada, esperando decisión."""
    id: int
    crudo: str
    evento: threading.Event = field(default_factory=threading.Event)
    accion: str = SOLTAR
    editado: str | None = None

    @property
    def resultado(self) -> str | None:
        """Lo que el motor debe mandar, o None si se descarta."""
        if self.accion == DESCARTAR:
            return None
        return self.editado if self.editado is not None else self.crudo


class Interceptor:
    """Decide qué peticiones se paran y guarda las que están paradas.

    `al_detener` se llama DESDE EL HILO DEL MOTOR en cuanto algo se para,
    para que la interfaz se entere. Quien lo reciba es responsable de
    saltar a su propio bucle —en Textual con `call_from_thread`—, el
    mismo contrato que ya tienen `Engine.on_flow` y el Intruder.
    """

    def __init__(
        self,
        al_detener: Callable[[Detenida], None] | None = None,
        *,
        timeout: float = TIMEOUT_DEFECTO,
    ):
        self.activa = False
        self.timeout = timeout
        self.al_detener = al_detener
        self._paradas: dict[int, Detenida] = {}
        self._lock = threading.Lock()
        self._contador = itertools.count(1)
        self._cerrado = False

    # ------------------------------------------------- desde el motor
    def detener(self, crudo: str) -> str | None:
        """Para la petición y espera. Devuelve lo que hay que mandar.

        None significa descartarla. Llamar a esto con la interceptación
        apagada no cuesta nada y no bloquea.
        """
        if not self.activa or self._cerrado:
            return crudo

        d = Detenida(id=next(self._contador), crudo=crudo)
        with self._lock:
            self._paradas[d.id] = d

        if self.al_detener is not None:
            try:
                self.al_detener(d)
            except Exception:
                # el consumidor vive en otro hilo y puede fallar; si eso
                # se llevara la peticion por delante, un fallo de pintado
                # cortaria el trafico del analista
                pass

        if not d.evento.wait(timeout=self.timeout):
            # nadie contesto. Sale sin tocar: que el navegador se quede
            # colgado para siempre porque el analista se fue es peor que
            # dejar pasar algo
            with self._lock:
                self._paradas.pop(d.id, None)
            return crudo

        with self._lock:
            self._paradas.pop(d.id, None)
        return d.resultado

    # --------------------------------------------- desde la interfaz
    def pendientes(self) -> list[Detenida]:
        """Las paradas, en orden de llegada."""
        with self._lock:
            return [self._paradas[k] for k in sorted(self._paradas)]

    def resolver(self, id_: int, accion: str, editado: str | None = None) -> None:
        """Suelta o descarta una parada. Si ya no está, no hace nada.

        Puede no estar porque venció el timeout mientras se decidía, y
        eso no es un error: es la carrera normal entre las dos partes.
        """
        # se saca de la cola AQUI y no cuando el hilo del motor despierte.
        # Dejarselo a el abria una carrera: la interfaz repintaba antes
        # de que el otro hilo corriera, volvia a ver la misma peticion
        # arriba y parecia que soltar no hacia nada.
        with self._lock:
            d = self._paradas.pop(id_, None)
            if d is None:
                return
            d.accion = accion
            d.editado = editado
        d.evento.set()

    def soltar_todas(self) -> None:
        """Deja salir todo lo parado, sin tocarlo.

        Es lo que debe pasar al apagar la interceptación: lo que ya
        estaba esperando no tiene por qué quedarse ahí.
        """
        with self._lock:
            paradas = list(self._paradas.values())
            self._paradas.clear()
        for d in paradas:
            d.accion = SOLTAR
            d.editado = None
            d.evento.set()

    def cerrar(self) -> None:
        """Suelta todo y deja de detener. Para el cierre de la aplicación.

        Sin esto quedarían hilos del motor esperando una decisión que ya
        nadie va a tomar, y el proceso no terminaría de morirse.
        """
        self._cerrado = True
        self.activa = False
        self.soltar_todas()
