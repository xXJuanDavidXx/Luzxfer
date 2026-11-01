"""Repeater con pestañas: peticiones crudas que sobreviven a cerrar.

Una peticion que has pasado veinte minutos afinando es exactamente lo
que no se puede perder al cerrar una pantalla. Se guarda la PETICION y
no la respuesta: lo que cuesta es lo que escribiste tu, y la respuesta
se vuelve a pedir en un segundo.
"""
from __future__ import annotations

from rich.text import Text
from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Static, TabbedContent, TabPane, TextArea

from ...core.models import Flow
from ...core.tools import cuerpo as fmt
from ...core.tools import repeater

MAX_SALTOS = 5


def titulo_de(crudo: str) -> str:
    """Un nombre corto para la pestaña: metodo y ruta."""
    primera = crudo.splitlines()[0] if crudo.strip() else "?"
    partes = primera.split()
    metodo = partes[0] if partes else "?"
    ruta = partes[1] if len(partes) > 1 else "/"
    if len(ruta) > 24:
        ruta = ruta[:23] + "…"
    return f"{metodo} {ruta}"


class RepeaterScreen(ModalScreen):
    BINDINGS = [
        Binding("escape", "cerrar", "cerrar"),
        Binding("ctrl+s", "enviar", "enviar", priority=True),
        Binding("ctrl+w", "cerrar_pestana", "cerrar pestaña", priority=True),
        Binding("ctrl+r", "alternar_saltos", "seguir redirecciones",
                priority=True),
    ]

    def __init__(self, store, nuevo: Flow | None = None):
        super().__init__()
        self.store = store
        self.nuevo = nuevo
        self.seguir = 0
        self._enviando: set[int] = set()

    # ------------------------------------------------------------------
    def compose(self) -> ComposeResult:
        with Vertical(id="rep-caja"):
            yield Static("", id="rep-titulo")
            yield TabbedContent(id="rep-tabs")
            with Horizontal(id="rep-barra"):
                yield Button("enviar", variant="primary", id="rep-enviar")
                yield Button("cerrar", id="rep-cerrar")

    def on_mount(self) -> None:
        if self.nuevo is not None:
            crudo = self.nuevo.request.raw()
            self.store.add_repeticion(
                titulo_de(crudo), crudo,
                self.nuevo.request.url.startswith("https://"))
        for fila in self.store.list_repeticiones():
            self._anadir_pane(fila)
        self._pintar_titulo()
        ed = self.editor_actual()
        if ed is not None:
            ed.focus()

    def _anadir_pane(self, fila: dict) -> None:
        rid = fila["id"]
        tabs = self.query_one("#rep-tabs", TabbedContent)
        pane = TabPane(fila["titulo"] or f"#{rid}", id=f"rep-{rid}")
        tabs.add_pane(pane)
        pane.mount(TextArea(fila["crudo"], id=f"ed-{rid}", soft_wrap=False))
        pane.mount(VerticalScroll(Static("", id=f"out-{rid}"),
                                  id=f"scroll-{rid}"))
        tabs.active = f"rep-{rid}"

    def _pintar_titulo(self) -> None:
        n = len(self.pestanas())
        saltos = (f"siguiendo hasta {self.seguir} redirecciones"
                  if self.seguir else "sin seguir redirecciones")
        self.query_one("#rep-titulo", Static).update(
            Text.assemble(
                ("repeater", "bold #f0a93b"),
                (f"  ·  {n} pestaña{'' if n == 1 else 's'}", "#7b8496"),
                (f"  ·  {saltos}", "#5fa8d3" if self.seguir else "#5c6578"),
                ("   ctrl+s enviar · ctrl+w cerrar pestaña · "
                 "ctrl+r redirecciones · esc cerrar", "#5c6578"),
            )
        )

    # ------------------------------------------------------- acceso
    def pestanas(self) -> list[int]:
        return [int(p.id.split("-")[1])
                for p in self.query(TabPane) if p.id and p.id.startswith("rep-")]

    def editores(self) -> list[TextArea]:
        return list(self.query(TextArea))

    def _activa(self) -> int | None:
        act = self.query_one("#rep-tabs", TabbedContent).active
        return int(act.split("-")[1]) if act else None

    def editor_actual(self) -> TextArea | None:
        rid = self._activa()
        return self.query_one(f"#ed-{rid}", TextArea) if rid else None

    def salida_actual(self) -> Static | None:
        rid = self._activa()
        return self.query_one(f"#out-{rid}", Static) if rid else None

    # ------------------------------------------------------- acciones
    def action_alternar_saltos(self) -> None:
        self.seguir = 0 if self.seguir else MAX_SALTOS
        self._pintar_titulo()

    def action_cerrar_pestana(self) -> None:
        rid = self._activa()
        if rid is None:
            return
        self.store.borrar_repeticion(rid)
        self.query_one("#rep-tabs", TabbedContent).remove_pane(f"rep-{rid}")
        if not self.store.list_repeticiones():
            # sin pestañas no hay repeater que enseñar
            self.dismiss()
            return
        self._pintar_titulo()

    def action_enviar(self) -> None:
        rid = self._activa()
        ed = self.editor_actual()
        if rid is None or ed is None or rid in self._enviando:
            return
        crudo = ed.text
        salida = self.salida_actual()
        try:
            repeater.parse_raw(crudo)       # validar antes de lanzar el hilo
        except repeater.ErrorPeticion as e:
            salida.update(Text(f"peticion invalida\n\n{e}", style="#e05c5c"))
            return
        # lo editado se guarda al enviar: si cierras despues, sigue ahi
        self.store.set_repeticion(rid, crudo)
        self._enviando.add(rid)
        salida.update(Text("enviando…", style="italic #f0a93b"))
        self._enviar_en_hilo(rid, crudo)

    @work(thread=True, exclusive=False)
    def _enviar_en_hilo(self, rid: int, crudo: str) -> None:
        """La red fuera del hilo de la interfaz: un objetivo lento no
        puede congelar la TUI hasta el timeout."""
        tls = None
        for fila in self.store.list_repeticiones():
            if fila["id"] == rid:
                tls = bool(fila["tls"])
                break
        try:
            flujo = repeater.send_raw(crudo, tls=tls, seguir=self.seguir)
        except repeater.ErrorPeticion as e:
            self.app.call_from_thread(self._mostrar_error, rid,
                                      f"peticion invalida\n\n{e}")
            return
        self.app.call_from_thread(self._mostrar, rid, flujo)

    def _mostrar_error(self, rid: int, texto: str) -> None:
        self._enviando.discard(rid)
        try:
            self.query_one(f"#out-{rid}", Static).update(
                Text(texto, style="#e05c5c"))
        except Exception:
            pass                        # la pestaña se cerro mientras tanto

    def _mostrar(self, rid: int, flujo: Flow) -> None:
        self._enviando.discard(rid)
        try:
            salida = self.query_one(f"#out-{rid}", Static)
        except Exception:
            return                      # la pestaña se cerro mientras tanto

        # el flujo del repeater entra al historial y pasa por el detector:
        # es evidencia, igual que el trafico del proxy
        if hasattr(self.app, "_ingresar"):
            self.app._ingresar(flujo)

        if flujo.error:
            salida.update(Text(f"error de red\n\n{flujo.error}", style="#e05c5c"))
            return

        r = flujo.response
        color = {2: "#6fcf8f", 3: "#5fa8d3", 4: "#f0a93b", 5: "#e05c5c"}.get(
            r.status // 100, "#d9dde5")
        texto, nota = fmt.presentar(r.decoded_body(), r.content_type,
                                    bonito=getattr(self.app, "cuerpo_bonito", True))
        enc = f"  ({r.encoding} sin decodificar)" if r.sin_decodificar() else ""
        partes = [
            (f"{r.status} {r.reason}", f"bold {color}"),
            (f"   {flujo.duration_ms}ms   {len(r.body)} bytes{enc}\n", "#7b8496"),
        ]
        if flujo.saltos:
            # por donde paso importa tanto como donde acabo
            partes.append((f"paso por: {' → '.join(flujo.saltos)}\n", "#5fa8d3"))
        partes.append(("\n" + r.raw_headers() + "\n\n", "#7b8496"))
        if nota:
            partes.append((f"— {nota}\n\n", "#5fa8d3"))
        partes.append((texto, "#c7cdd9"))
        salida.update(Text.assemble(*partes))

    def on_button_pressed(self, ev: Button.Pressed) -> None:
        if ev.button.id == "rep-enviar":
            self.action_enviar()
        elif ev.button.id == "rep-cerrar":
            self.action_cerrar()

    def action_cerrar(self) -> None:
        ed = self.editor_actual()
        rid = self._activa()
        if ed is not None and rid is not None:
            self.store.set_repeticion(rid, ed.text)   # no perder lo escrito
        self.dismiss()
