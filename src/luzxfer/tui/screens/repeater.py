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
from ..paleta import P

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
        Binding("ctrl+f", "formatear", "formatear JSON", priority=True),
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
                yield Button("formatear JSON", id="rep-formatear")
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
        # las clases son lo que engancha con la hoja de estilos: el id
        # lleva el numero de pestaña, asi que un selector por id solo
        # vale para una. Cuando el repeater paso a pestañas, el CSS se
        # quedo apuntando a #rep-editor y companiia y dejo de aplicarse
        # a nada, que es por lo que la respuesta salia cortada.
        pane.mount(TextArea(fila["crudo"], id=f"ed-{rid}", soft_wrap=False,
                            classes="rep-editor"))
        pane.mount(VerticalScroll(
            Static("", id=f"out-{rid}", classes="rep-salida"),
            id=f"scroll-{rid}", classes="rep-scroll"))
        tabs.active = f"rep-{rid}"

    def _pintar_titulo(self) -> None:
        n = len(self.pestanas())
        saltos = (f"siguiendo hasta {self.seguir} redirecciones"
                  if self.seguir else "sin seguir redirecciones")
        self.query_one("#rep-titulo", Static).update(
            Text.assemble(
                ("repeater", f"bold {P.acento}"),
                (f"  ·  {n} pestaña{'' if n == 1 else 's'}", P.secundario),
                (f"  ·  {saltos}", P.info if self.seguir else P.tenue),
                # `tab` va primero a proposito: sin saberlo, una
                # respuesta mas alta que el panel parece cortada, porque
                # el foco se queda en el editor y no hay forma de
                # desplazarla
                ("   tab editor/respuesta · ctrl+s enviar · "
                 "ctrl+f formatear JSON · ctrl+w cerrar pestaña · "
                 "ctrl+r redirecciones · esc cerrar", P.tenue),
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
            salida.update(Text(f"peticion invalida\n\n{e}", style=P.peligro))
            return
        # lo editado se guarda al enviar: si cierras despues, sigue ahi
        self.store.set_repeticion(rid, crudo)
        self._enviando.add(rid)
        salida.update(Text("enviando…", style=f"italic {P.acento}"))
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
                Text(texto, style=P.peligro))
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
            salida.update(Text(f"error de red\n\n{flujo.error}", style=P.peligro))
            return

        r = flujo.response
        color = {2: P.bien, 3: P.info, 4: P.acento, 5: P.peligro}.get(
            r.status // 100, P.texto)
        texto, nota = fmt.presentar(r.decoded_body(), r.content_type,
                                    bonito=getattr(self.app, "cuerpo_bonito", True))
        enc = f"  ({r.encoding} sin decodificar)" if r.sin_decodificar() else ""
        partes = [
            (f"{r.status} {r.reason}", f"bold {color}"),
            (f"   {flujo.duration_ms}ms   {len(r.body)} bytes{enc}\n", P.secundario),
        ]
        if flujo.saltos:
            # por donde paso importa tanto como donde acabo
            partes.append((f"paso por: {' → '.join(flujo.saltos)}\n", P.info))
        partes.append(("\n" + r.raw_headers() + "\n\n", P.secundario))
        if nota:
            partes.append((f"— {nota}\n\n", P.info))
        partes.append((texto, P.cuerpo))
        salida.update(Text.assemble(*partes))

    def action_formatear(self) -> None:
        ed = self.editor_actual()
        if ed is None:
            return
        nuevo, nota = fmt.formatear_cuerpo_crudo(ed.text)
        if nuevo != ed.text:
            ed.text = nuevo
        self.notify(nota, timeout=4)

    def on_button_pressed(self, ev: Button.Pressed) -> None:
        if ev.button.id == "rep-enviar":
            self.action_enviar()
        elif ev.button.id == "rep-formatear":
            self.action_formatear()
        elif ev.button.id == "rep-cerrar":
            self.action_cerrar()

    def action_cerrar(self) -> None:
        ed = self.editor_actual()
        rid = self._activa()
        if ed is not None and rid is not None:
            self.store.set_repeticion(rid, ed.text)   # no perder lo escrito
        self.dismiss()
