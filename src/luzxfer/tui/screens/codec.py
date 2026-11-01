"""Conversor: que es este texto, y en que lo convierto.

En una terminal gana enseñar de golpe QUE PODRIA SER el texto, en vez
de obligar a elegir un formato a ciegas y probar uno por uno. Si no se
reconoce nada, se dice: una lista que siempre tiene opciones no informa.

Se abre con el token mas prometedor de la peticion ya dentro, porque
abrirlo vacio obliga a copiar a mano justo lo que la herramienta tiene
delante.
"""
from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Static, TextArea

from ...core.tools import codec
from ..paleta import P

CODIFICABLES = ("base64", "url", "hex", "html")


class ConversorScreen(ModalScreen):
    BINDINGS = [
        Binding("escape", "cerrar", "cerrar"),
        Binding("ctrl+e", "codificar", "codificar", priority=True),
    ]

    def __init__(self, texto: str = "", origen: str = ""):
        super().__init__()
        self.texto_inicial = texto
        self.origen = origen
        self._formato = 0

    def compose(self) -> ComposeResult:
        with Vertical(id="cod-caja"):
            yield Static("", id="cod-titulo")
            yield TextArea(self.texto_inicial, id="cod-entrada", soft_wrap=True)
            with VerticalScroll(id="cod-scroll"):
                yield Static("", id="cod-salida")

    def on_mount(self) -> None:
        self._titulo()
        self._refrescar()
        self.query_one("#cod-entrada", TextArea).focus()

    def _titulo(self) -> None:
        de = f"  ·  de {self.origen}" if self.origen else ""
        self.query_one("#cod-titulo", Static).update(
            Text.assemble(
                ("conversor", f"bold {P.acento}"),
                (de, P.secundario),
                (f"   ctrl+e codifica ({CODIFICABLES[self._formato]}) · "
                 f"esc cierra", P.tenue),
            )
        )

    # ------------------------------------------------------------------
    def on_text_area_changed(self, ev: TextArea.Changed) -> None:
        if ev.text_area.id == "cod-entrada":
            self._refrescar()

    def _refrescar(self) -> None:
        texto = self.query_one("#cod-entrada", TextArea).text
        salida = self.query_one("#cod-salida", Static)
        if not texto.strip():
            salida.update(Text("Pega algo aqui arriba.", style=f"italic {P.tenue}"))
            return

        opciones = codec.detectar(texto)
        if not opciones:
            salida.update(Text(
                "No parece estar codificado en nada que se reconozca.\n"
                "ctrl+e codifica en el formato del titulo.",
                style=P.secundario))
            return

        partes = []
        for formato, resultado in opciones:
            partes.append((f"── {formato} ──\n", f"bold {P.info}"))
            partes.append((resultado + "\n\n", P.cuerpo))
        salida.update(Text.assemble(*partes))

    def action_codificar(self) -> None:
        """Codifica al siguiente formato. Recorrerlos con una sola tecla
        ahorra un menu que no aporta nada: son cuatro."""
        texto = self.query_one("#cod-entrada", TextArea).text
        if not texto:
            return
        formato = CODIFICABLES[self._formato]
        self._formato = (self._formato + 1) % len(CODIFICABLES)
        self._titulo()
        self.query_one("#cod-salida", Static).update(
            Text.assemble((f"── codificado a {formato} ──\n", f"bold {P.bien}"),
                          (codec.codificar(texto, formato), P.cuerpo)))

    def action_cerrar(self) -> None:
        self.dismiss()
