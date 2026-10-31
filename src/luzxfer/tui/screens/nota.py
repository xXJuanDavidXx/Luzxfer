"""Pantalla de nota: lo que viste en este flujo, en tus palabras.

Una nota es evidencia tanto como el flujo. Al escribir el reporte, «aqui
el parametro q no se escapa» vale mas que volver a leer la respuesta.
"""
from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Input, Static


class NotaScreen(ModalScreen[str | None]):
    """Devuelve el texto escrito, o None si se cerro sin guardar."""

    BINDINGS = [Binding("escape", "cerrar", "descartar")]

    def __init__(self, nota_actual: str = ""):
        super().__init__()
        self.nota_actual = nota_actual

    def compose(self) -> ComposeResult:
        with Vertical(id="nota-caja"):
            yield Static(Text("nota del flujo", style="bold #f0a93b"),
                         id="nota-titulo")
            # se precarga la nota: abrir para editar y encontrarla vacia
            # seria perder lo escrito antes
            yield Input(value=self.nota_actual,
                        placeholder="que viste en este flujo…",
                        id="nota-input")
            yield Static(Text("enter guardar · esc descartar", style="#5c6578"),
                         id="nota-ayuda")

    def on_mount(self) -> None:
        self.query_one("#nota-input", Input).focus()

    def on_input_submitted(self, ev: Input.Submitted) -> None:
        self.dismiss(ev.value)         # vacio es valido: asi se borra una nota

    def action_cerrar(self) -> None:
        self.dismiss(None)
