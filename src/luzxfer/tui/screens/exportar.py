"""Pantalla de exportacion: sacar la peticion de la herramienta.

Un hallazgo que solo existe dentro de tu pantalla cuesta de defender.
Uno que se reproduce pegando una linea en una terminal, no. Es lo que
hace «Copy as curl command» en Burp, y es de lo que mas se usa.

El texto va en un `TextArea` y no en un `Static` **a proposito**: asi se
puede seleccionar con el raton y copiar con el mecanismo del terminal de
cada cual. Se intenta ademas copiar al portapapeles, pero eso viaja por
una secuencia de escape (OSC 52) que muchos terminales ignoran sin decir
nada, asi que el mensaje no promete que haya funcionado: ofrecer una
certeza que no se tiene es como el analista pega una cadena vieja en un
informe.
"""
from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Static, TextArea

from ...core.models import Flow
from ...core.tools import exportar
from ..paleta import P

# (clave, etiqueta). El orden es el de uso: el curl es lo que se quiere
# nueve de cada diez veces.
VISTAS = (
    ("curl", "curl"),
    ("peticion", "peticion cruda"),
    ("respuesta", "respuesta cruda"),
)


class ExportarScreen(ModalScreen):
    """El flujo como `curl` o en crudo, listo para copiar."""

    BINDINGS = [
        Binding("escape", "cerrar", "cerrar"),
        Binding("tab", "siguiente", "cambiar de vista", priority=True),
        Binding("ctrl+y", "copiar", "copiar", priority=True),
    ]

    def __init__(self, flujo: Flow):
        super().__init__()
        self.flujo = flujo
        self.vista = "curl"

    def compose(self) -> ComposeResult:
        with Vertical(id="exp-caja"):
            yield Static("", id="exp-titulo")
            yield TextArea("", id="exp-texto", soft_wrap=True,
                           read_only=True)
            yield Static("", id="exp-avisos")

    def on_mount(self) -> None:
        self._pintar()

    # ------------------------------------------------------------------
    def _contenido(self) -> str:
        if self.vista == "curl":
            return exportar.a_curl(self.flujo.request)
        return exportar.a_crudo(self.flujo, lado=self.vista)

    def _avisos(self) -> list[str]:
        if self.vista != "curl":
            return []
        return exportar.avisos_curl(self.flujo.request)

    def _pintar(self) -> None:
        etiqueta = dict(VISTAS)[self.vista]
        self.query_one("#exp-titulo", Static).update(Text.assemble(
            ("exportar", f"bold {P.acento}"),
            (f"  ·  flujo {self.flujo.id}" if self.flujo.id else "",
             P.secundario),
            (f"  ·  {etiqueta}", P.info),
            ("   tab cambia · ctrl+y copia · esc cierra", P.tenue),
        ))
        self.query_one("#exp-texto", TextArea).text = self._contenido()

        avisos = self._avisos()
        caja = self.query_one("#exp-avisos", Static)
        if avisos:
            caja.update(Text("\n".join(f"· {a}" for a in avisos),
                             style=P.peligro))
            caja.display = True
        else:
            # una caja de avisos siempre presente se deja de leer
            caja.display = False

    # ------------------------------------------------------------------
    def action_siguiente(self) -> None:
        claves = [c for c, _e in VISTAS]
        self.vista = claves[(claves.index(self.vista) + 1) % len(claves)]
        self._pintar()

    def action_copiar(self) -> None:
        self.app.copy_to_clipboard(self._contenido())
        # no se promete que haya llegado: OSC 52 lo ignoran muchos
        # terminales sin decir nada, y prometerlo es como se acaba
        # pegando una cadena vieja en un informe
        self.notify("enviado al portapapeles; si tu terminal no lo "
                    "permite, selecciona el texto a mano",
                    title="copiar", timeout=6)

    def action_cerrar(self) -> None:
        self.dismiss()
