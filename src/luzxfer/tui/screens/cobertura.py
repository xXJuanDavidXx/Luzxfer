"""Pantalla de la matriz de cobertura WSTG.

Es la vista que contesta la pregunta que Burp no contesta: que pruebas
de la metodologia le debes todavia al cliente.

Lo que una persona puede poner a mano es «pasa» y «no aplica». «FALLA» y
«con candidatos» salen de la evidencia y no se tocan: un informe que
diga que una prueba pasa teniendo una vulnerabilidad confirmada debajo
no se puede entregar.
"""
from __future__ import annotations

import time

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import DataTable, Static

from ...core import sesiones
from ...core.tools import cobertura as cob
from ...core.tools import wstg
from ..paleta import P

COLOR = {
    wstg.NO_PROBADO: P.secundario,
    wstg.PROBADO: P.acento,
    wstg.PASA: P.bien,
    wstg.FALLA: f"bold {P.peligro}",
    wstg.NO_APLICA: P.tenue,
}
ETIQUETA = {
    wstg.NO_PROBADO: "no probado",
    wstg.PROBADO: "con candidatos",
    wstg.PASA: "pasa",
    wstg.FALLA: "FALLA",
    wstg.NO_APLICA: "no aplica",
}


class CoberturaScreen(ModalScreen):
    BINDINGS = [
        Binding("escape", "cerrar", "cerrar"),
        Binding("space", "ciclar", "pasa / no aplica"),
        Binding("ctrl+g", "informe", "generar informe"),
    ]

    def compose(self) -> ComposeResult:
        with Vertical(id="cob-caja"):
            yield Static("", id="cob-titulo")
            yield DataTable(id="cob-tabla", cursor_type="row")
            yield Static("", id="cob-aviso")

    def on_mount(self) -> None:
        t = self.query_one("#cob-tabla", DataTable)
        t.add_column("id", width=16)
        t.add_column("prueba", width=62)
        self._col_estado = t.add_column("estado", width=16)
        self.refrescar()
        t.focus()
        self._aviso("espacio alterna pasa / no aplica  ·  ctrl+g genera el "
                    "informe  ·  esc cierra")

    # ------------------------------------------------------------------
    @property
    def estados(self) -> dict[str, str]:
        return cob.calcular(self.app.store.list_findings(),
                            self.app.store.get_cobertura())

    def refrescar(self) -> None:
        estados = self.estados
        t = self.query_one("#cob-tabla", DataTable)
        t.clear()
        for cat in wstg.CATEGORIAS:
            for pr in wstg.por_categoria(cat.codigo):
                e = estados[pr.id]
                t.add_row(
                    Text(pr.id, style=P.atenuado),
                    Text(pr.titulo, style=P.texto if e != wstg.NO_PROBADO
                         else P.secundario),
                    Text(ETIQUETA[e], style=COLOR[e]),
                    key=pr.id,
                )
        self._titulo(estados)

    def _titulo(self, estados: dict[str, str]) -> None:
        r = cob.resumen(estados)
        self.query_one("#cob-titulo", Static).update(
            Text.assemble(
                ("cobertura WSTG v4.2", f"bold {P.acento}"),
                (f"   {cob.porcentaje(estados)} % de lo que aplica", P.atenuado),
                (f"   ·  {r[wstg.FALLA]} FALLA", f"bold {P.peligro}"),
                (f"  ·  {r[wstg.PASA]} pasa", P.bien),
                (f"  ·  {r[wstg.PROBADO]} con candidatos", P.acento),
                (f"  ·  {r[wstg.NO_PROBADO]} sin probar", P.secundario),
            )
        )

    def _aviso(self, texto: str, color: str = P.tenue) -> None:
        self.query_one("#cob-aviso", Static).update(Text(texto, style=color))

    def _seleccionada(self) -> str | None:
        t = self.query_one("#cob-tabla", DataTable)
        if not t.row_count:
            return None
        try:
            return t.coordinate_to_cell_key((t.cursor_row, 0)).row_key.value
        except Exception:
            return None

    # ------------------------------------------------------------------
    def action_ciclar(self) -> None:
        ident = self._seleccionada()
        if ident is None:
            return
        actual = self.estados[ident]
        if actual in (wstg.FALLA, wstg.PROBADO):
            self._aviso(
                f"{ident} lo decide la evidencia, no el dedo. Hay "
                f"{'un hallazgo confirmado' if actual == wstg.FALLA else 'candidatos'} "
                f"con ese ID.", P.acento)
            return

        manual = self.app.store.get_cobertura().get(ident, wstg.NO_PROBADO)
        ciclo = wstg.CICLO_MANUAL
        siguiente = ciclo[(ciclo.index(manual) + 1) % len(ciclo)] \
            if manual in ciclo else wstg.PASA
        self.app.store.set_cobertura(ident, siguiente)
        self.refrescar()
        self.query_one("#cob-tabla", DataTable).move_cursor(
            row=self.query_one("#cob-tabla", DataTable).get_row_index(ident))

    def action_informe(self) -> None:
        carpeta = sesiones.dir_datos() / "informes"
        try:
            carpeta.mkdir(parents=True, exist_ok=True)
            nombre = (f"{self.app.sesion or 'sesion'}-"
                      f"{time.strftime('%Y%m%d-%H%M%S')}.md")
            ruta = carpeta / nombre
            ruta.write_text(cob.informe(
                sesion=self.app.sesion or "sin nombre",
                hallazgos=self.app.store.list_findings(),
                estados=self.estados,
                alcance=self.app.alcance.texto(),
                flujos=self.app.store.count_flows(),
            ), encoding="utf-8")
        except OSError as e:
            self._aviso(f"no se pudo escribir el informe: {e}", P.peligro)
            return
        self._aviso(f"informe escrito en {ruta}", P.bien)

    def action_cerrar(self) -> None:
        self.dismiss()

