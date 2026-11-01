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
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Static, TextArea

from ..paleta import P


class DetalleResultadoScreen(ModalScreen[bool]):
    """La peticion reconstruida de una fila, de solo lectura y seleccionable.

    Devuelve True si se pide mandarla al repeater, False si solo se cierra.
    El detalle enseña la peticion; el repeater es donde se afina y se ve la
    respuesta entera, que aqui no se guarda.
    """

    BINDINGS = [
        Binding("escape", "cerrar", "cerrar"),
        Binding("q", "cerrar", "cerrar"),
        Binding("ctrl+r", "al_repeater", "mandar al repeater", priority=True),
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
                    ("   ctrl+r al repeater · esc cierra", P.tenue),
                ),
                id="det-titulo",
            )
            # seleccionable para copiarla con el raton; de solo lectura
            # porque esto es evidencia de lo que salio, no un editor
            yield TextArea(self.peticion, id="det-peticion", soft_wrap=False,
                           read_only=True)
            with Horizontal(id="det-barra"):
                yield Button("mandar al repeater", variant="primary",
                             id="det-repeater")
                yield Button("cerrar", id="det-cerrar")

    def on_button_pressed(self, ev: Button.Pressed) -> None:
        if ev.button.id == "det-repeater":
            self.action_al_repeater()
        elif ev.button.id == "det-cerrar":
            self.action_cerrar()

    def action_al_repeater(self) -> None:
        self.dismiss(True)

    def action_cerrar(self) -> None:
        self.dismiss(False)
