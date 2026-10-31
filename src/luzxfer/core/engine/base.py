"""Interfaz de motor.

Esta es la pieza que sostiene todo el diseno: ninguna interfaz habla con un
motor concreto. Cambiar el motor propio por mitmproxy es cambiar una clase,
no reescribir la herramienta. Es tambien lo que permite que la misma TUI
corra en el PC (con TLS) y en Termux (sin compilar nada).
"""
from __future__ import annotations

import abc
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

    @property
    def running(self) -> bool:
        return self._running

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
