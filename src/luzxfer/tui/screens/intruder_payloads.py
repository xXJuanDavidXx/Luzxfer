"""Cargar payloads: un diccionario de un archivo o un rango numerico.

La logica ya vive en core (`desde_archivo`, `desde_rango`); esto solo es
la forma de llegar a ella sin teclear a mano el convenio `@ruta` ni
escribir diez mil numeros. Acerca el Intruder al de Burp sin perder el
objetivo, que es ser mas rapido.

Devuelve la lista de payloads a insertar, o None si se cierra sin cargar.
Un archivo que no existe o un rango al reves no cierran la pantalla: se
avisa y se deja corregir, porque equivocarse al teclear una ruta es lo
normal, no la excepcion.
"""
from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Static

from ...core.tools import intruder
from ..paleta import P


class CargarPayloadsScreen(ModalScreen[list[str] | None]):
    """Pide un diccionario o un rango y devuelve los payloads."""

    BINDINGS = [Binding("escape", "cancelar", "cancelar")]

    def compose(self) -> ComposeResult:
        with Vertical(id="pay-caja"):
            yield Static(Text("cargar payloads", style=f"bold {P.acento}"),
                         id="pay-titulo")

            yield Static(Text("diccionario (un payload por linea)",
                              style=P.secundario))
            with Horizontal(classes="pay-fila"):
                yield Input(placeholder="ruta del archivo", id="pay-ruta")
                yield Button("cargar", id="pay-archivo")

            yield Static(Text("rango numerico", style=P.secundario))
            with Horizontal(classes="pay-fila"):
                yield Input(placeholder="desde", id="pay-desde")
                yield Input(placeholder="hasta", id="pay-hasta")
                yield Input(placeholder="paso", id="pay-paso", value="1")
                yield Input(placeholder="ceros", id="pay-ancho", value="0")
                yield Button("cargar", id="pay-rango")

            yield Static("", id="pay-aviso")
            yield Static(Text("esc cancela", style=P.tenue))

    # ------------------------------------------------------------------
    def _aviso(self, texto: str, color: str = P.peligro) -> None:
        self.query_one("#pay-aviso", Static).update(Text(texto, style=color))

    def _entero(self, id_campo: str, nombre: str) -> int:
        """El valor de un campo como entero, o ErrorAtaque si no lo es."""
        crudo = self.query_one(id_campo, Input).value.strip()
        try:
            return int(crudo)
        except ValueError:
            raise intruder.ErrorAtaque(
                f"'{nombre}' tiene que ser un numero entero") from None

    def _cargar_archivo(self) -> None:
        ruta = self.query_one("#pay-ruta", Input).value.strip()
        if not ruta:
            self._aviso("falta la ruta del archivo")
            return
        try:
            payloads = intruder.desde_archivo(ruta)
        except intruder.ErrorAtaque as e:
            self._aviso(str(e))
            return
        if not payloads:
            self._aviso("el archivo no tiene payloads utiles")
            return
        self.dismiss(payloads)

    def _cargar_rango(self) -> None:
        try:
            desde = self._entero("#pay-desde", "desde")
            hasta = self._entero("#pay-hasta", "hasta")
            paso = self._entero("#pay-paso", "paso")
            ancho = self._entero("#pay-ancho", "ceros")
            payloads = intruder.desde_rango(desde, hasta, paso, ancho=ancho)
        except intruder.ErrorAtaque as e:
            self._aviso(str(e))
            return
        self.dismiss(payloads)

    def on_button_pressed(self, ev: Button.Pressed) -> None:
        if ev.button.id == "pay-archivo":
            self._cargar_archivo()
        elif ev.button.id == "pay-rango":
            self._cargar_rango()

    def action_cancelar(self) -> None:
        self.dismiss(None)
