"""La aplicacion. Historial, detalle, filtros y repeater."""
from __future__ import annotations

from pathlib import Path

from rich.text import Text
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, VerticalScroll
from textual.widgets import (
    DataTable,
    Footer,
    Header,
    Input,
    Static,
    TabbedContent,
    TabPane,
)

from ..core.engine import Builtin, puerto_libre
from ..core.models import Flow
from ..core.store import Store
from ..core.tools import detector
from .screens.repeater import RepeaterScreen
from .screens.sesiones import SesionesScreen

# Cuantos flujos se pintan en la tabla al reconstruirla. No es un limite
# del almacen: el historial completo sigue en la sesion y se puede filtrar
# para llegar a el. Existe porque pintar decenas de miles de filas de golpe
# cuesta, y cuando recorta se dice en la barra de estado.
LIMITE_TABLA = 5000

COLOR_ESTADO = {2: "#6fcf8f", 3: "#5fa8d3", 4: "#f0a93b", 5: "#e05c5c"}
COLOR_METODO = {
    "GET": "#5fa8d3", "POST": "#f0a93b", "PUT": "#c99bf0",
    "DELETE": "#e05c5c", "PATCH": "#9bd4f0",
}


def pinta_estado(status: int | None, error: str = "") -> Text:
    if status is None:
        return Text("ERR" if error else "—", style="#e05c5c" if error else "#5c6578")
    return Text(str(status), style=f"bold {COLOR_ESTADO.get(status // 100, '#d9dde5')}")


def pinta_metodo(metodo: str) -> Text:
    return Text(metodo, style=f"bold {COLOR_METODO.get(metodo, '#a8b0c0')}")


def tamano_legible(n: int) -> str:
    if n < 1024:
        return f"{n}B"
    if n < 1024 * 1024:
        return f"{n / 1024:.1f}K"
    return f"{n / 1048576:.1f}M"


class LuzxferApp(App):
    """Proxy de interceptacion y banco de trabajo, en la terminal."""

    CSS_PATH = Path(__file__).parent / "styles.tcss"
    TITLE = "luzxfer"

    BINDINGS = [
        Binding("q", "quit", "salir"),
        Binding("r", "repeater", "repeater"),
        Binding("s", "sesiones", "sesiones"),
        Binding("f", "foco_filtro", "filtrar"),
        Binding("m", "marcar", "marcar"),
        Binding("c", "limpiar", "limpiar"),
        Binding("g", "arriba", "inicio", show=False),
        Binding("G", "abajo", "final", show=False),
        Binding("j", "cursor_abajo", "abajo", show=False),
        Binding("k", "cursor_arriba", "arriba", show=False),
        Binding("escape", "quitar_foco", "", show=False),
    ]

    def __init__(
        self,
        *,
        db: str = ":memory:",
        sesion: str = "",
        host: str = "127.0.0.1",
        port: int = 8080,
        upstream: str | None = None,
        arrancar_motor: bool = True,
    ):
        super().__init__()
        self.store = Store(db)
        self.sesion = sesion
        if sesion:
            # en el encabezado, para no confundir dos sesiones abiertas a la vez
            self.sub_title = sesion
        self.host_proxy = host
        self.port_proxy = port
        self.upstream = upstream
        self.arrancar_motor = arrancar_motor
        self.engine: Builtin | None = None
        self._flujo_actual: Flow | None = None
        self._filtro = ""

    # ------------------------------------------------------------------
    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal(id="barra"):
            yield Input(placeholder="filtrar por url…  (f)", id="filtro")
            yield Static("", id="estado")
        yield DataTable(id="flujos", cursor_type="row", zebra_stripes=False)
        with TabbedContent(id="detalle"):
            with TabPane("peticion", id="tab-req"):
                with VerticalScroll(classes="panel"):
                    yield Static("", id="panel-req")
            with TabPane("respuesta", id="tab-resp"):
                with VerticalScroll(classes="panel"):
                    yield Static("", id="panel-resp")
            with TabPane("candidatos", id="tab-hall"):
                yield DataTable(id="hallazgos", cursor_type="row")
        yield Footer()

    # ------------------------------------------------------------------
    def on_mount(self) -> None:
        tabla = self.query_one("#flujos", DataTable)
        self._col_id = tabla.add_column("#", width=6)
        tabla.add_column("met", width=7)
        tabla.add_column("cod", width=5)
        tabla.add_column("host", width=22)
        tabla.add_column("ruta")
        tabla.add_column("tam", width=8)
        tabla.add_column("ms", width=6)
        tabla.focus()

        hall = self.query_one("#hallazgos", DataTable)
        hall.add_column("tipo", width=10)
        hall.add_column("detalle")
        hall.add_column("wstg", width=26)
        hall.add_column("donde", width=28)

        self._mostrar_vacio()
        self.refrescar_tabla()

        if self.arrancar_motor:
            self.arrancar()
        self.actualizar_estado()

    def _mostrar_vacio(self) -> None:
        self.query_one("#panel-req", Static).update(
            Text("Selecciona un flujo de la tabla.", style="italic #5c6578"))
        self.query_one("#panel-resp", Static).update(
            Text("Selecciona un flujo de la tabla.", style="italic #5c6578"))

    # ------------------------------------------------------------------
    def arrancar(self) -> None:
        if not puerto_libre(self.host_proxy, self.port_proxy):
            self.notify(
                f"el puerto {self.port_proxy} ya esta ocupado",
                title="no se pudo arrancar el motor", severity="error", timeout=8)
            return
        self.engine = Builtin(
            self._flujo_desde_hilo,
            host=self.host_proxy, port=self.port_proxy, upstream=self.upstream,
        )
        self.engine.start()
        destino = f" → {self.upstream}" if self.upstream else ""
        self.notify(
            f"escuchando en {self.host_proxy}:{self.port_proxy}{destino}",
            title="motor integrado", timeout=4)

    def _flujo_desde_hilo(self, flujo: Flow) -> None:
        """Llamado DESDE el hilo del motor: hay que saltar al bucle de la TUI."""
        self.call_from_thread(self._ingresar, flujo)

    def _ingresar(self, flujo: Flow) -> None:
        """Entra un flujo nuevo. Incremental: no reconstruye la tabla.

        El historial va en orden ascendente, como el de Burp. Asi un flujo
        nuevo se agrega al final sin mover los indices de los anteriores, y
        lo que el analista tiene seleccionado no salta mientras llega trafico.
        """
        self.store.add_flow(flujo)
        nuevos = [h for h in detector.analizar(flujo) if self.store.add_finding(h)]

        tabla = self.query_one("#flujos", DataTable)
        if self._coincide(flujo):
            al_final = tabla.row_count == 0 or tabla.cursor_row >= tabla.row_count - 1
            self._agregar_fila(tabla, flujo)
            if al_final:                        # seguir el trafico solo si ya lo seguias
                tabla.move_cursor(row=tabla.row_count - 1)

        hall = self.query_one("#hallazgos", DataTable)
        for h in nuevos:
            self._agregar_hallazgo(hall, h)
        self.actualizar_estado()

    def _coincide(self, f: Flow) -> bool:
        return not self._filtro or self._filtro.lower() in f.request.url.lower()

    @staticmethod
    def _agregar_fila(tabla: DataTable, f: Flow) -> None:
        tabla.add_row(
            Text(f"{'●' if f.marked else ''}{f.id}",
                 style="#f0a93b" if f.marked else "#7b8496"),
            pinta_metodo(f.request.method),
            pinta_estado(f.status, f.error),
            Text(f.request.host or "—", style="#a8b0c0"),
            Text(f.request.path, style="#d9dde5"),
            Text(tamano_legible(f.size), style="#7b8496"),
            Text(str(f.duration_ms), style="#7b8496"),
            key=str(f.id),
        )

    COLOR_HALLAZGO = {"REFLEJO": "#e05c5c", "COOKIE": "#f0a93b",
                      "CABECERA": "#5fa8d3", "FUGA": "#7b8496", "ERROR": "#c99bf0"}

    def _agregar_hallazgo(self, hall: DataTable, h) -> None:
        hall.add_row(
            Text(h.kind, style=f"bold {self.COLOR_HALLAZGO.get(h.kind, '#d9dde5')}"),
            Text(h.detail, style="#d9dde5"),
            Text(", ".join(h.wstg), style="#6fcf8f"),
            Text(h.url, style="#7b8496"),
        )

    # ------------------------------------------------------------------
    def refrescar_tabla(self) -> None:
        """Reconstruccion completa: solo al filtrar, limpiar o arrancar.
        Restaura la seleccion por id de flujo, no por indice."""
        tabla = self.query_one("#flujos", DataTable)
        elegido = self._flujo_actual.id if self._flujo_actual else None
        tabla.clear()
        for f in self.store.list_flows(texto=self._filtro, ascendente=True,
                                       limite=LIMITE_TABLA):
            self._agregar_fila(tabla, f)
        if tabla.row_count:
            fila = tabla.row_count - 1
            if elegido is not None:
                try:
                    fila = tabla.get_row_index(str(elegido))
                except Exception:
                    pass                        # el elegido quedo fuera del filtro
            tabla.move_cursor(row=fila)

        hall = self.query_one("#hallazgos", DataTable)
        hall.clear()
        for h in reversed(self.store.list_findings()):
            self._agregar_hallazgo(hall, h)

    def actualizar_estado(self) -> None:
        motor = "detenido"
        if self.engine and self.engine.running:
            motor = f"{self.host_proxy}:{self.port_proxy}"
        n = self.store.count_flows()
        c = self.store.count_findings()
        piezas = [
            (f"{n} flujo{'' if n == 1 else 's'}", "#d9dde5"), ("  ·  ", "#39404f"),
            (f"{c} candidato{'' if c == 1 else 's'}", "#f0a93b"), ("  ·  ", "#39404f"),
        ]

        # si la tabla no alcanza a mostrar todo lo que hay, decirlo. Callarlo
        # es hacerle creer al analista que ya vio el historial entero.
        mostrados = self.query_one("#flujos", DataTable).row_count
        total = self.store.count_flows(texto=self._filtro) if self._filtro else n
        if mostrados < total:
            piezas += [(f"mostrando {mostrados} de {total}", "#e05c5c"),
                       ("  ·  ", "#39404f")]

        piezas.append(
            (motor, "#6fcf8f" if self.engine and self.engine.running else "#e05c5c"))
        self.query_one("#estado", Static).update(Text.assemble(*piezas))

    # ------------------------------------------------------------------
    def on_data_table_row_highlighted(self, ev: DataTable.RowHighlighted) -> None:
        if ev.data_table.id != "flujos" or ev.row_key is None:
            return
        try:
            fid = int(ev.row_key.value)
        except (TypeError, ValueError):
            return
        flujo = self.store.get_flow(fid)
        if flujo:
            self._flujo_actual = flujo
            self._pintar_detalle(flujo)

    def _pintar_detalle(self, f: Flow) -> None:
        self.query_one("#panel-req", Static).update(
            Text(f.request.raw(), style="#c7cdd9"))

        if f.error:
            self.query_one("#panel-resp", Static).update(
                Text(f"error de red\n\n{f.error}", style="#e05c5c"))
            return
        if f.response is None:
            self.query_one("#panel-resp", Static).update(
                Text("sin respuesta", style="italic #5c6578"))
            return

        cuerpo = f.response.text(200_000)
        if len(f.response.body) > 200_000:
            cuerpo += "\n\n…(truncado)"
        self.query_one("#panel-resp", Static).update(
            Text.assemble(
                (f.response.raw_headers() + "\n\n", "#7b8496"),
                (cuerpo, "#c7cdd9"),
            )
        )

    def on_input_changed(self, ev: Input.Changed) -> None:
        if ev.input.id == "filtro":
            self._filtro = ev.value.strip()
            self.refrescar_tabla()
            self.actualizar_estado()       # el aviso de truncado depende del filtro

    def on_input_submitted(self, ev: Input.Submitted) -> None:
        if ev.input.id == "filtro":
            self.query_one("#flujos", DataTable).focus()

    # ------------------------------------------------------------------ acciones
    def action_foco_filtro(self) -> None:
        self.query_one("#filtro", Input).focus()

    def action_quitar_foco(self) -> None:
        self.query_one("#flujos", DataTable).focus()

    def action_repeater(self) -> None:
        if self._flujo_actual is None:
            self.notify("selecciona un flujo primero", severity="warning")
            return
        self.push_screen(RepeaterScreen(self._flujo_actual))

    def action_sesiones(self) -> None:
        self.push_screen(SesionesScreen(self.sesion), self._tras_elegir_sesion)

    def _tras_elegir_sesion(self, nombre: str | None) -> None:
        """Cambiar de sesion en caliente no esta implementado a proposito.

        Reemplazar el Store vivo con el motor corriendo y flujos entrando
        es un problema distinto del de no perder el historial, y mezclarlo
        aqui habria arrastrado los dos. Por ahora se dice que comando abre
        la que se eligio.
        """
        if not nombre or nombre == self.sesion:
            return
        self.notify(f"luzxfer -s {nombre}", title="para abrir esa sesion",
                    timeout=10)

    def action_marcar(self) -> None:
        if self._flujo_actual is None or self._flujo_actual.id is None:
            return
        f = self._flujo_actual
        f.marked = not f.marked
        self.store.set_mark(f.id, f.marked)
        try:
            self.query_one("#flujos", DataTable).update_cell(
                str(f.id), self._col_id,
                Text(f"{'●' if f.marked else ''}{f.id}",
                     style="#f0a93b" if f.marked else "#7b8496"))
        except Exception:
            pass                                # la fila no esta visible con el filtro

    def action_limpiar(self) -> None:
        self.store.clear_flows()
        self._flujo_actual = None
        self._mostrar_vacio()
        self.refrescar_tabla()
        self.actualizar_estado()
        self.notify("historial limpiado (los candidatos se conservan)")

    def action_cursor_abajo(self) -> None:
        self.query_one("#flujos", DataTable).action_cursor_down()

    def action_cursor_arriba(self) -> None:
        self.query_one("#flujos", DataTable).action_cursor_up()

    def action_arriba(self) -> None:
        t = self.query_one("#flujos", DataTable)
        if t.row_count:
            t.move_cursor(row=0)

    def action_abajo(self) -> None:
        t = self.query_one("#flujos", DataTable)
        if t.row_count:
            t.move_cursor(row=t.row_count - 1)

    # ------------------------------------------------------------------
    def on_unmount(self) -> None:
        if self.engine:
            self.engine.stop()
        self.store.close()
