"""Pantalla de comparacion entre los dos flujos marcados.

Se eligen marcando con `m`, que ya existia: inventar otra forma de
elegir dos flujos cuando la herramienta ya tiene una seria dar dos
maneras de hacer lo mismo.
"""
from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Static

from ...core.models import Flow
from ...core.tools import comparar
from ..paleta import P


class CompararScreen(ModalScreen):
    BINDINGS = [
        Binding("escape", "cerrar", "cerrar"),
        Binding("tab", "alternar", "peticion / respuesta", priority=True),
    ]

    def __init__(self, a: Flow, b: Flow):
        super().__init__()
        self.a = a
        self.b = b
        self.lado = "respuesta"

    def compose(self) -> ComposeResult:
        with Vertical(id="cmp-caja"):
            yield Static("", id="cmp-titulo")
            with VerticalScroll(id="cmp-scroll"):
                yield Static("", id="cmp-salida")

    def on_mount(self) -> None:
        self._pintar()

    def action_alternar(self) -> None:
        self.lado = "peticion" if self.lado == "respuesta" else "respuesta"
        self._pintar()

    def _pintar(self) -> None:
        d = comparar.diferencias(self.a, self.b, self.lado)
        quitadas, puestas = comparar.cuantas(d)

        self.query_one("#cmp-titulo", Static).update(
            Text.assemble(
                ("comparar", f"bold {P.acento}"),
                (f"  ·  flujos {self.a.id} y {self.b.id}", P.secundario),
                (f"  ·  {self.lado}", P.info),
                (f"  ·  −{quitadas} +{puestas}" if quitadas or puestas
                 else "  ·  identicos",
                 P.peligro if (quitadas or puestas) else P.bien),
                ("   tab cambia de lado · esc cierra", P.tenue),
            )
        )

        if not (quitadas or puestas):
            self.query_one("#cmp-salida", Static).update(
                Text(f"Los dos lados «{self.lado}» son identicos.\n\n"
                     f"tab mira el otro lado.", style=P.secundario))
            return

        color = {"-": P.peligro, "+": P.bien, " ": P.tenue}
        partes = []
        for marca, linea in d:
            partes.append((f"{marca} {linea}\n", color.get(marca, P.tenue)))
        self.query_one("#cmp-salida", Static).update(Text.assemble(*partes))

    def action_cerrar(self) -> None:
        self.dismiss()
