"""Interfaz de motor.

Esta es la pieza que sostiene todo el diseno: ninguna interfaz habla con un
motor concreto. Cambiar el motor propio por mitmproxy es cambiar una clase,
no reescribir la herramienta. Es tambien lo que permite que la misma TUI
corra en el PC (con TLS) y en Termux (sin compilar nada).
"""
from __future__ import annotations

import abc
import threading
from collections.abc import Callable
from dataclasses import dataclass

from ..models import Flow

FlowCallback = Callable[[Flow], None]


@dataclass(slots=True)
class EngineInfo:
    name: str
    tls: bool                 # intercepta HTTPS
    http2: bool
    websockets: bool
    needs: str = ""           # que hay que instalar, si falta algo

    def resumen(self) -> str:
        caps = [n for n, ok in
                (("TLS", self.tls), ("HTTP/2", self.http2), ("WS", self.websockets)) if ok]
        return f"{self.name} · {', '.join(caps) if caps else 'HTTP plano'}"


class Engine(abc.ABC):
    """Un motor captura trafico y entrega Flow al nucleo.

    Corre en su propio hilo o proceso. `on_flow` se llama DESDE ESE HILO,
    asi que quien lo reciba es responsable de saltar a su propio bucle
    (en Textual, con `call_from_thread`).
    """

    def __init__(self, on_flow: FlowCallback, *, host: str = "127.0.0.1", port: int = 8080):
        self.on_flow = on_flow
        self.host = host
        self.port = port
        self._running = False
        # Flujos que se capturaron pero no llegaron al nucleo. Ver _emitir.
        self._perdidos = 0
        self._ultimo_fallo = ""
        self._cerrojo = threading.Lock()

    @property
    def running(self) -> bool:
        return self._running

    # ------------------------------------------------------- entrega
    def _emitir(self, flujo: Flow) -> None:
        """Entrega un flujo al nucleo sin dejar que un fallo tumbe el proxy.

        Que el proxy sobreviva a un consumidor roto es lo correcto: si se
        cayera, el navegador del analista dejaria de cargar a mitad de una
        prueba y se perderia mucho mas que un flujo.

        Lo que no es correcto es perderlo **callando**, que es lo que se
        hacia antes. Si el almacen esta bloqueado, el disco lleno o la
        aplicacion cerrandose, el trafico desaparece, el historial se queda
        vacio y el analista culpa al objetivo: concluye que la aplicacion
        no habla cuando en realidad hablaba y nadie lo apunto. Eso es un
        falso negativo producido por la herramienta, que es la peor clase.

        Asi que se cuenta y se guarda el ultimo motivo, y la interfaz lo
        enseña. Un flujo perdido del que se sabe es un problema que se
        puede investigar; uno perdido en silencio es evidencia que no
        existe y que nadie echa de menos.
        """
        try:
            self.on_flow(flujo)
        except Exception as e:
            with self._cerrojo:
                self._perdidos += 1
                self._ultimo_fallo = f"{type(e).__name__}: {e}"

    @property
    def perdidos(self) -> int:
        """Cuantos flujos se capturaron y no llegaron al nucleo."""
        with self._cerrojo:
            return self._perdidos

    @property
    def ultimo_fallo(self) -> str:
        """Por que se perdio el ultimo. Vacio si no se ha perdido ninguno."""
        with self._cerrojo:
            return self._ultimo_fallo

    @staticmethod
    @abc.abstractmethod
    def info() -> EngineInfo: ...

    @staticmethod
    def available() -> bool:
        """Si el motor puede usarse en esta maquina."""
        return True

    @abc.abstractmethod
    def start(self) -> None: ...

    @abc.abstractmethod
    def stop(self) -> None: ...
