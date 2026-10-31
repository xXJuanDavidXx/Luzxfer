"""Pantalla selectora de sesiones: ver que hay guardado, abrir y borrar.

Lee los resumenes con sesiones.listar(), que abre en solo lectura, asi que
asomarse aqui no modifica ninguna sesion ni crea una nueva por accidente.
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


class SesionesScreen(ModalScreen[str | None]):
    """Devuelve el nombre elegido, o None si se cerro sin elegir."""

    BINDINGS = [
        Binding("escape", "cerrar", "cerrar"),
        Binding("delete", "borrar", "borrar"),
    ]

    def __init__(self, actual: str = ""):
        super().__init__()
        self.actual = actual
        self._resumenes: dict[str, sesiones.ResumenSesion] = {}

    def compose(self) -> ComposeResult:
        with Vertical(id="ses-caja"):
            yield Static(
                Text.assemble(
                    ("sesiones", "bold #f0a93b"),
                    (f"  ·  {sesiones.dir_sesiones()}", "#5c6578"),
                ),
                id="ses-titulo",
            )
            yield DataTable(id="ses-tabla", cursor_type="row")
            yield Static(
                Text("enter abrir · supr borrar · esc cerrar", style="#5c6578"),
                id="ses-ayuda",
            )

    def on_mount(self) -> None:
        t = self.query_one("#ses-tabla", DataTable)
        t.add_column("sesion", width=28)
        t.add_column("flujos", width=9)
        t.add_column("candidatos", width=12)
        t.add_column("modificada", width=18)
        self._refrescar()
        t.focus()

    # ------------------------------------------------------------------
    def _refrescar(self) -> None:
        t = self.query_one("#ses-tabla", DataTable)
        t.clear()
        self._resumenes = {}
        for s in sesiones.listar():
            self._resumenes[s.nombre] = s
            abierta = s.nombre == self.actual
            nombre = Text(f"{'● ' if abierta else '  '}{s.nombre}",
                          style="bold #f0a93b" if abierta else "#d9dde5")
            if s.ilegible:
                # se lista igual: ocultarla haria pensar que no esta
                t.add_row(nombre, Text("ilegible", style="#e05c5c"),
                          Text("—", style="#5c6578"), Text("—", style="#5c6578"),
                          key=s.nombre)
                continue
            t.add_row(
                nombre,
                Text(str(s.flujos), style="#a8b0c0"),
                Text(str(s.candidatos),
                     style="#f0a93b" if s.candidatos else "#5c6578"),
                Text(time.strftime("%Y-%m-%d %H:%M", time.localtime(s.modificada)),
                     style="#7b8496"),
                key=s.nombre,
            )

        # aterrizar en la sesion abierta y no en la primera fila: el orden
        # es por fecha, asi que la primera puede ser cualquiera, incluso una
        # ilegible. Quien abre el selector espera verse a si mismo primero.
        if self.actual in self._resumenes:
            try:
                t.move_cursor(row=t.get_row_index(self.actual))
            except Exception:
                pass

    def _seleccionada(self) -> str | None:
        t = self.query_one("#ses-tabla", DataTable)
        if not t.row_count:
            return None
        try:
            return t.coordinate_to_cell_key((t.cursor_row, 0)).row_key.value
        except Exception:
            return None

    # ------------------------------------------------------------------
    def on_data_table_row_selected(self, ev: DataTable.RowSelected) -> None:
        nombre = self._seleccionada()
        if nombre is None:
            return
        s = self._resumenes.get(nombre)
        if s is not None and s.ilegible:
            self.notify(f"'{nombre}' no se puede leer: corrupta, ajena o de "
                        "otra version", severity="error")
            return
        self.dismiss(nombre)

    def action_cerrar(self) -> None:
        self.dismiss(None)

    def action_borrar(self) -> None:
        nombre = self._seleccionada()
        if nombre is None:
            return
        if nombre == self.actual:
            # borrar la sesion abierta dejaria al Store escribiendo en un
            # archivo que ya no esta, y el historial de hoy se perderia
            self.notify("no se borra la sesion que esta abierta",
                        severity="warning")
            return
        sesiones.borrar(nombre)
        self._refrescar()
        self.notify(f"sesion '{nombre}' borrada")
