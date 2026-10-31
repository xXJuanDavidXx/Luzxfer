"""Pantalla del repeater: editar la peticion cruda y reenviarla."""
from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Static, TextArea

from ...core.models import Flow
from ...core.tools import repeater


class RepeaterScreen(ModalScreen):
    BINDINGS = [
        Binding("escape", "cerrar", "cerrar"),
        Binding("ctrl+s", "enviar", "enviar"),
    ]

    def __init__(self, flujo: Flow):
        super().__init__()
        self.flujo = flujo

    def compose(self) -> ComposeResult:
        with Vertical(id="rep-caja"):
            yield Static(
                Text.assemble(
                    ("repeater", "bold #f0a93b"),
                    (f"  ·  flujo {self.flujo.id}", "#7b8496"),
                    ("   ctrl+s enviar · esc cerrar", "#5c6578"),
                ),
                id="rep-titulo",
            )
            yield TextArea(self.flujo.request.raw(), id="rep-editor", soft_wrap=False)
            with Horizontal(id="rep-barra"):
                yield Button("enviar", variant="primary", id="rep-enviar")
                yield Button("cerrar", id="rep-cerrar")
            with VerticalScroll():
                yield Static(
                    Text("La respuesta aparece aqui. El Content-Length se "
                         "recalcula solo.", style="italic #5c6578"),
                    id="rep-salida",
                )

    def on_mount(self) -> None:
        self.query_one("#rep-editor", TextArea).focus()

    # ------------------------------------------------------------------
    def on_button_pressed(self, ev: Button.Pressed) -> None:
        if ev.button.id == "rep-enviar":
            self.action_enviar()
        elif ev.button.id == "rep-cerrar":
            self.action_cerrar()

    def action_cerrar(self) -> None:
        self.dismiss()

    def action_enviar(self) -> None:
        crudo = self.query_one("#rep-editor", TextArea).text
        salida = self.query_one("#rep-salida", Static)
        try:
            flujo = repeater.send_raw(crudo)
        except repeater.ErrorPeticion as e:
            salida.update(Text(f"peticion invalida\n\n{e}", style="#e05c5c"))
            return

        if flujo.error:
            salida.update(Text(f"error de red\n\n{flujo.error}", style="#e05c5c"))
            return

        r = flujo.response
        color = {2: "#6fcf8f", 3: "#5fa8d3", 4: "#f0a93b", 5: "#e05c5c"}.get(
            r.status // 100, "#d9dde5")
        cuerpo = r.text(100_000)
        if len(r.body) > 100_000:
            cuerpo += "\n\n…(truncado)"
        salida.update(
            Text.assemble(
                (f"{r.status} {r.reason}", f"bold {color}"),
                (f"   {flujo.duration_ms}ms   {len(r.body)} bytes\n\n", "#7b8496"),
                (r.raw_headers() + "\n\n", "#7b8496"),
                (cuerpo, "#c7cdd9"),
            )
        )
        # el flujo del repeater tambien entra al historial: es evidencia
        app = self.app
        if hasattr(app, "store"):
            app.store.add_flow(flujo)
            app.refrescar_tabla()
            app.actualizar_estado()
