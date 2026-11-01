"""Detalle de un resultado del Intruder: la peticion que de verdad salio.

En un fuzzing con cientos de filas, ver que una mide distinto no basta:
hay que poder mirar que se mando en esa fila. Aqui se reconstruye la
peticion exacta —la base con los payloads puestos en sus posiciones— con
la misma funcion que uso el ataque, asi que es lo que viajo, no una
aproximacion.

La respuesta no se guarda por fila a proposito: un ataque de un millon
de peticiones no puede retener un millon de cuerpos en memoria. Lo que
delata el acierto —codigo, largo, grep— ya esta en la tabla; para ver el
cuerpo entero de un caso concreto se manda esa peticion al repeater.
"""
from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Static, TextArea

from ..paleta import P


class DetalleResultadoScreen(ModalScreen):
    """La peticion reconstruida de una fila, de solo lectura y seleccionable."""

    BINDINGS = [
        Binding("escape", "cerrar", "cerrar"),
        Binding("q", "cerrar", "cerrar"),
    ]

    def __init__(self, titulo: str, peticion: str):
        super().__init__()
        self.titulo = titulo
        self.peticion = peticion

    def compose(self) -> ComposeResult:
        with Vertical(id="det-caja"):
            yield Static(
                Text.assemble(
                    ("detalle del resultado", f"bold {P.acento}"),
                    (f"   {self.titulo}", P.secundario),
                    ("   esc cierra", P.tenue),
                ),
                id="det-titulo",
            )
            # seleccionable para copiarla con el raton; de solo lectura
            # porque esto es evidencia de lo que salio, no un editor
            yield TextArea(self.peticion, id="det-peticion", soft_wrap=False,
                           read_only=True)

    def action_cerrar(self) -> None:
        self.dismiss()
