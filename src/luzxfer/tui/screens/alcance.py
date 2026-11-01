"""Pantalla del alcance: qué entra en el contrato.

Se edita como texto, una regla por línea, en vez de con una lista y
botones. Un alcance es algo que se copia del correo donde el cliente lo
definió, se pega, se retoca y a veces se guarda en el informe: como
texto eso funciona, y como formulario no.
"""
from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Static, TextArea

from ...core.tools import alcance as alc
from ..paleta import P

AYUDA = """\
+objetivo.com          incluir ese host, cualquier puerto
+*.objetivo.com        y sus subdominios, con la raiz dentro
+objetivo.com:8080     solo ese puerto
+objetivo.com/api/     solo bajo esa ruta
-admin.objetivo.com    excluir; excluir siempre gana

Sin ninguna regla, todo esta dentro."""


class AlcanceScreen(ModalScreen):
    BINDINGS = [
        Binding("escape", "cerrar", "descartar"),
        Binding("ctrl+s", "guardar", "guardar"),
        Binding("ctrl+f", "filtrar", "filtrar historial"),
    ]

    def __init__(self, texto: str, solo_alcance: bool, sugerencia: str = ""):
        super().__init__()
        # la sugerencia solo entra si no habia nada: pisar lo que el
        # analista ya escribio seria imperdonable
        self.texto_inicial = texto if texto.strip() else sugerencia
        self.solo_alcance = solo_alcance

    def compose(self) -> ComposeResult:
        with Vertical(id="alc-caja"):
            yield Static(
                Text.assemble(
                    ("alcance", f"bold {P.acento}"),
                    ("   ctrl+s guardar · ctrl+f filtrar historial · esc descartar",
                     P.tenue),
                ),
                id="alc-titulo",
            )
            yield TextArea(self.texto_inicial, id="alc-editor", soft_wrap=False)
            yield Static(Text(AYUDA, style=P.tenue), id="alc-ayuda")
            yield Static("", id="alc-aviso")

    def on_mount(self) -> None:
        self.query_one("#alc-editor", TextArea).focus()
        self._pintar_estado()

    # ------------------------------------------------------------------
    def _pintar_estado(self, extra: str = "", color: str = P.info) -> None:
        marca = "si" if self.solo_alcance else "no"
        base = f"filtrar el historial por alcance: {marca}"
        texto = f"{extra}\n{base}" if extra else base
        self.query_one("#alc-aviso", Static).update(
            Text(texto, style=color if extra else P.info))

    def action_filtrar(self) -> None:
        """Se aplica al momento, sin esperar a guardar.

        No es incoherente con que esc descarte: las reglas se estan
        editando y por eso necesitan un guardado explicito, pero esto es
        un interruptor, y un interruptor que no hace nada hasta que
        guardas no deja ver lo que hace. Asi el historial cambia detras
        del modal mientras decides.
        """
        self.solo_alcance = not self.solo_alcance
        self.app.poner_solo_alcance(self.solo_alcance)
        self._pintar_estado()

    def action_guardar(self) -> None:
        texto = self.query_one("#alc-editor", TextArea).text
        errores = self.app.poner_alcance(texto)
        self.app.poner_solo_alcance(self.solo_alcance)
        if errores:
            # no se cierra: las reglas buenas ya se aplicaron, pero hay
            # algo escrito que no significa nada y cerrar lo escondería
            self._pintar_estado("\n".join(errores), P.peligro)
            return
        self.dismiss()

    def action_cerrar(self) -> None:
        self.dismiss()


def sugerencia_desde(url: str) -> str:
    """La regla que casi siempre se quiere: el host que estás mirando.

    Sin el puerto a propósito. Una aplicación suele repartirse entre el
    80 y el 443, y un alcance atado a un puerto deja la mitad fuera sin
    avisar.
    """
    from urllib.parse import urlsplit

    host = (urlsplit(url).hostname or "").lower()
    if not host:
        return ""
    try:
        alc.Regla.desde_texto(f"+{host}")
    except alc.ReglaInvalida:
        return ""
    return f"+{host}"
