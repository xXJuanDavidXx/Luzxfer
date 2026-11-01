"""Pantalla de interceptación: la petición parada, antes de que salga.

Se queda abierta mientras la interceptación esté encendida, como la
pestaña Intercept de Burp: cuando sueltas una, aparece la siguiente de
la cola, y si no hay ninguna espera ahí.

Los atajos llevan `ctrl` y no son letras sueltas, aunque el boceto las
pedía: esto es un editor de texto, y una `f` suelta escribiría una `f`.
Van igual que `ctrl+s` del repeater y `ctrl+l` del Intruder, para no
tener tres convenciones distintas dentro del mismo programa.
"""
from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Static, TextArea

from ...core.tools import intercepta

VACIO = ("Esperando. La interceptacion esta encendida, asi que el navegador\n"
         "se queda parado hasta que sueltes cada peticion.\n\n"
         "ctrl+x la apaga y deja pasar todo.")


class InterceptaScreen(ModalScreen):
    # priority=True porque el TextArea reclama ctrl+d, ctrl+f y ctrl+x
    # para sus propias cosas, y aqui el editor esta siempre enfocado: sin
    # esto, soltar una peticion borraba un caracter.
    BINDINGS = [
        Binding("ctrl+f", "soltar", "soltar", priority=True),
        Binding("ctrl+d", "descartar", "descartar", priority=True),
        Binding("ctrl+x", "apagar", "apagar interceptacion", priority=True),
        Binding("escape", "cerrar", "cerrar"),
    ]

    def __init__(self, interceptor: intercepta.Interceptor):
        super().__init__()
        self.interceptor = interceptor
        self.actual: intercepta.Detenida | None = None
        self._insistido = False

    def compose(self) -> ComposeResult:
        with Vertical(id="itc-caja"):
            yield Static("", id="itc-titulo")
            yield TextArea("", id="int-crudo", soft_wrap=False)
            yield Static(
                Text("ctrl+f soltar · ctrl+d descartar · ctrl+x apagar · "
                     "esc cerrar (sigue encendida)", style="#5c6578"),
                id="itc-ayuda",
            )

    def on_mount(self) -> None:
        self.refrescar()
        self.query_one("#int-crudo", TextArea).focus()

    # ------------------------------------------------------------------
    def refrescar(self) -> None:
        """Enseña la primera de la cola, o el mensaje de espera."""
        pendientes = self.interceptor.pendientes()
        editor = self.query_one("#int-crudo", TextArea)

        if not pendientes:
            self.actual = None
            editor.text = VACIO
            editor.read_only = True
            self._titulo(0)
            return

        primera = pendientes[0]
        # solo se repinta al cambiar de peticion: machacar el editor
        # mientras alguien escribe le borraria lo que lleva hecho
        if self.actual is None or self.actual.id != primera.id:
            self.actual = primera
            self._insistido = False
            editor.read_only = False
            editor.text = primera.crudo
            self.query_one("#itc-ayuda", Static).update(
                Text(self.AYUDA, style="#5c6578"))
        self._titulo(len(pendientes))

    def _titulo(self, en_cola: int) -> None:
        self.query_one("#itc-titulo", Static).update(
            Text.assemble(
                ("[ INTERCEPTACION: ON ]", "bold #e05c5c"),
                (f"   cola: {en_cola}", "#f0a93b" if en_cola else "#5c6578"),
            )
        )

    # ------------------------------------------------------------------
    def _resolver(self, accion: str, editado: str | None) -> None:
        if self.actual is None:
            return
        self.interceptor.resolver(self.actual.id, accion, editado)
        self.actual = None
        self.refrescar()

    AYUDA = ("ctrl+f soltar · ctrl+d descartar · ctrl+x apagar · "
             "esc cerrar (sigue encendida)")

    def action_soltar(self) -> None:
        texto = self.query_one("#int-crudo", TextArea).text
        aviso = self._revisar(texto)
        if aviso and not self._insistido:
            # no se suelta a la primera: avisar y dejar corregir. Pero la
            # ultima palabra es del analista, asi que insistir la manda
            # igual —puede estar probando justo eso.
            self._insistido = True
            self.query_one("#itc-ayuda", Static).update(
                Text(f"{aviso}  ·  ctrl+f otra vez la manda igual",
                     style="#f0a93b"))
            return
        self._resolver(intercepta.SOLTAR, texto)

    @staticmethod
    def _revisar(texto: str) -> str:
        """Lo que se perderia al mandar, dicho antes de perderlo.

        Una linea de peticion HTTP son tres partes separadas por
        espacios. Si hay mas, el resto se queda por el camino al
        reenviar: correcto, pero en silencio seria inaceptable. Un
        payload con espacios se codifica con %20 o va en el cuerpo.
        """
        primera = texto.splitlines()[0] if texto.strip() else ""
        if len(primera.split()) > 3:
            return ("la linea de peticion lleva espacios de mas y se "
                    "cortaria; codificalos con %20")
        return ""

    def action_descartar(self) -> None:
        self._resolver(intercepta.DESCARTAR, None)

    def action_apagar(self) -> None:
        """Apaga y deja salir todo lo que estuviera esperando.

        Apagar y dejar las paradas colgadas seria lo peor de los dos
        mundos: el navegador seguiria bloqueado sin nadie mirando.
        """
        self.interceptor.activa = False
        self.interceptor.soltar_todas()
        self.dismiss()

    def action_cerrar(self) -> None:
        """Cierra la pantalla pero NO apaga: las que lleguen se siguen
        parando y se avisa. Es la diferencia con ctrl+x, y por eso lo
        dice la linea de ayuda."""
        self.dismiss()
