"""La aplicacion. Historial, detalle, filtros y repeater."""
from __future__ import annotations

import sqlite3
from pathlib import Path

from rich.text import Text
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, VerticalScroll
from textual.widgets import (
    Button,
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
from ..core.tools import alcance as alc
from ..core.tools import cuerpo, detector, intercepta, sitemap
from .screens.alcance import AlcanceScreen, sugerencia_desde
from .screens.intercepta import InterceptaScreen
from .screens.intruder import IntruderScreen
from .screens.nota import NotaScreen
from .screens.repeater import RepeaterScreen
from .screens.sesiones import SesionesScreen
from .screens.sitemap import SitemapScreen

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
        Binding("i", "intruder", "intruder"),
        Binding("a", "alcance", "alcance"),
        Binding("e", "mapa", "mapa del sitio"),
        Binding("x", "interceptar", "interceptar"),
        Binding("f", "foco_filtro", "filtrar"),
        Binding("m", "marcar", "marcar"),
        Binding("n", "nota", "nota"),
        Binding("v", "confirmar", "confirmar"),
        Binding("t", "vista", "vista"),
        Binding("p", "cuerpo", "crudo/bonito"),
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
        filtrar_encoding: bool = True,
        filtrar_cache: bool = True,
    ):
        super().__init__()
        self.filtrar_encoding = filtrar_encoding
        self.filtrar_cache = filtrar_cache
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
        self.vista_combinada = False
        self.cuerpo_bonito = True
        self.alcance = alc.Alcance([])
        self.solo_alcance = False
        # apagada de salida: encenderla sola seria colgarle el
        # navegador a alguien que no lo pidio
        self.interceptor = intercepta.Interceptor(self._detenida_desde_hilo)

    # ------------------------------------------------------------------
    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal(id="barra"):
            yield Input(placeholder="filtrar por url…  (f)", id="filtro")
            yield Button("vista: separadas", id="btn-vista")
            yield Static("", id="estado")
        yield DataTable(id="flujos", cursor_type="row", zebra_stripes=False)
        with TabbedContent(id="detalle"):
            with TabPane("peticion", id="tab-req"):
                with VerticalScroll(classes="panel"):
                    yield Static("", id="panel-req")
            with TabPane("respuesta", id="tab-resp"):
                with VerticalScroll(classes="panel"):
                    yield Static("", id="panel-resp")
            # las cuatro pestanas existen siempre y el modo solo cambia
            # cuales se ven: nada se reconstruye al alternar, y candidatos
            # sigue alcanzable en los dos modos
            with TabPane("peticion + respuesta", id="tab-ambos"):
                with Horizontal(id="ambos"):
                    with VerticalScroll(classes="panel mitad"):
                        yield Static("", id="ambos-req")
                    with VerticalScroll(classes="panel mitad"):
                        yield Static("", id="ambos-resp")
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
        self._col_ok = hall.add_column("ok", width=3)
        hall.add_column("tipo", width=10)
        hall.add_column("detalle")
        hall.add_column("wstg", width=26)
        hall.add_column("donde", width=28)

        self._mostrar_vacio()
        self.refrescar_tabla()
        # la vista se lee aqui y no en __init__: ahi los widgets no existen
        self._aplicar_vista(self.store.get_meta("vista") == "juntas")
        self.cuerpo_bonito = self.store.get_meta("cuerpo", "bonito") != "crudo"
        self.alcance, _ = alc.Alcance.desde_texto_tolerante(
            self.store.get_meta("alcance"))
        self.solo_alcance = self.store.get_meta("solo_alcance") == "si"

        if self.arrancar_motor:
            self.arrancar()
        self.actualizar_estado()

    def _mostrar_vacio(self) -> None:
        vacio = Text("Selecciona un flujo de la tabla.", style="italic #5c6578")
        for wid in ("#panel-req", "#panel-resp", "#ambos-req", "#ambos-resp"):
            self.query_one(wid, Static).update(vacio)

    # ------------------------------------------------------------------
    def _aplicar_vista(self, combinada: bool) -> None:
        """Alterna entre pestanas separadas y las dos a la vez.

        Se muestra la pestana destino y se activa ANTES de esconder las
        otras: esconder la activa deja a Textual eligiendo cual queda, y
        no siempre la que uno quiere.
        """
        self.vista_combinada = combinada
        det = self.query_one("#detalle", TabbedContent)
        if combinada:
            det.show_tab("tab-ambos")
            det.active = "tab-ambos"
            det.hide_tab("tab-req")
            det.hide_tab("tab-resp")
        else:
            det.show_tab("tab-req")
            det.show_tab("tab-resp")
            det.active = "tab-req"
            det.hide_tab("tab-ambos")
        self.query_one("#btn-vista", Button).label = (
            "vista: juntas" if combinada else "vista: separadas")

    def action_cuerpo(self) -> None:
        """Alterna entre el cuerpo reorganizado y los bytes tal como
        llegaron. Un JSON indentado se lee; el crudo es la evidencia,
        y a veces el espaciado o una clave repetida son el hallazgo."""
        self.cuerpo_bonito = not self.cuerpo_bonito
        self.store.set_meta("cuerpo",
                            "bonito" if self.cuerpo_bonito else "crudo")
        if self._flujo_actual is not None:
            self._pintar_detalle(self._flujo_actual)

    def action_vista(self) -> None:
        self._aplicar_vista(not self.vista_combinada)
        self.store.set_meta("vista", "juntas" if self.vista_combinada else "separadas")
        if self._flujo_actual is not None:
            self._pintar_detalle(self._flujo_actual)

    def on_button_pressed(self, ev: Button.Pressed) -> None:
        if ev.button.id == "btn-vista":
            self.action_vista()

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
            filtrar_encoding=self.filtrar_encoding,
            filtrar_cache=self.filtrar_cache,
            interceptor=self.interceptor,
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
        try:
            self.store.add_flow(flujo)
            # el flujo se guarda SIEMPRE; lo que el alcance decide es si
            # vale la pena analizarlo. Los candidatos de un CDN o de
            # analitica son ruido que entierra lo que si importa, y
            # ademas no son del cliente.
            nuevos = []
            if not self.solo_analizar_alcance or self.alcance.dentro(flujo.request.url):
                nuevos = [h for h in detector.analizar(flujo)
                          if self.store.add_finding(h)]
        except sqlite3.Error as e:
            # otra instancia con la sesion tomada, disco lleno, archivo
            # borrado bajo los pies… Perder un flujo es malo; que la
            # excepcion suba al bucle de la interfaz y se lleve la sesion
            # entera por delante es mucho peor.
            self.notify(f"no se pudo guardar el flujo: {e}",
                        title="error de la sesion", severity="error", timeout=10)
            return

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
        if self.solo_alcance and not self.alcance.dentro(f.request.url):
            return False
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

    @staticmethod
    def _marca_ok(confirmado: bool) -> Text:
        return Text("✓" if confirmado else "", style="bold #6fcf8f")

    def _agregar_hallazgo(self, hall: DataTable, h) -> None:
        hall.add_row(
            self._marca_ok(h.confirmed),
            Text(h.kind, style=f"bold {self.COLOR_HALLAZGO.get(h.kind, '#d9dde5')}"),
            Text(h.detail, style="#d9dde5"),
            Text(", ".join(h.wstg), style="#6fcf8f"),
            Text(h.url, style="#7b8496"),
            # la clave es el id del hallazgo: sin ella no hay forma de saber
            # cual se esta confirmando
            key=str(h.id) if h.id is not None else None,
        )

    # ------------------------------------------------------------------
    def refrescar_tabla(self) -> None:
        """Reconstruccion completa: solo al filtrar, limpiar o arrancar.
        Restaura la seleccion por id de flujo, no por indice."""
        tabla = self.query_one("#flujos", DataTable)
        elegido = self._flujo_actual.id if self._flujo_actual else None
        tabla.clear()
        flujos = self.store.list_flows(texto=self._filtro, ascendente=True,
                                       limite=LIMITE_TABLA)
        if self.solo_alcance:
            flujos = [f for f in flujos if self.alcance.dentro(f.request.url)]
        for f in flujos:
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
        # se distinguen los dos motivos de ver menos de lo que hay: que
        # no quepa y que este fuera de alcance no son lo mismo, y un solo
        # mensaje para ambos haria pensar en el que no es
        if self.solo_alcance:
            piezas += [(f"solo alcance: {mostrados} de {total}", "#5fa8d3"),
                       ("  ·  ", "#39404f")]
        elif mostrados < total:
            piezas += [(f"mostrando {mostrados} de {total}", "#e05c5c"),
                       ("  ·  ", "#39404f")]

        if self.interceptor.activa:
            # tiene que verse: olvidarse de que esta encendida es
            # quedarse mirando un navegador que no carga
            n = len(self.interceptor.pendientes())
            piezas += [(f"INTERCEPTA{f' ({n})' if n else ''}", "bold #e05c5c"),
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
        partes_req = []
        if f.note:
            partes_req.append((f"✎ {f.note}\n\n", "#f0a93b"))
        partes_req.append((f.request.raw(), "#c7cdd9"))
        self._poner("req", Text.assemble(*partes_req))

        if f.error:
            self._poner("resp", Text(f"error de red\n\n{f.error}", style="#e05c5c"))
            return
        if f.response is None:
            self._poner("resp", Text("sin respuesta", style="italic #5c6578"))
            return

        r = f.response
        texto, nota = cuerpo.presentar(r.decoded_body(), r.content_type,
                                       bonito=self.cuerpo_bonito)

        partes = [(r.raw_headers() + "\n\n", "#7b8496")]
        if r.sin_decodificar():
            # callarlo hace parecer que el servidor contesto basura, y de
            # paso esconde que el detector no pudo leer este cuerpo
            partes.append((
                f"⚠ cuerpo en '{r.encoding}' sin decodificar: luzxfer no sabe\n"
                f"  deshacer esa compresion. Lo de abajo son los bytes crudos,\n"
                f"  y el detector tampoco pudo leerlos: aqui no busques\n"
                f"  candidatos, no los va a haber.\n"
                f"  Por el proxy no deberia pasar; si pasa, el servidor ignoro\n"
                f"  el Accept-Encoding. Solucion:  pip install 'luzxfer[br]'\n\n",
                "#f0a93b"))
        if nota:
            partes.append((f"— {nota}\n\n", "#5fa8d3"))
        partes.append((texto, "#c7cdd9"))
        self._poner("resp", Text.assemble(*partes))

    def _poner(self, lado: str, texto: Text) -> None:
        """Escribe en el panel de los DOS modos a la vez.

        Pintar siempre los dos cuesta un update de mas y a cambio alternar
        es instantaneo y nunca muestra lo del flujo anterior. El cuerpo ya
        viene recortado a 200.000 caracteres, asi que no es medible.
        """
        self.query_one(f"#panel-{lado}", Static).update(texto)
        self.query_one(f"#ambos-{lado}", Static).update(texto)

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

    def action_intruder(self) -> None:
        if self._flujo_actual is None:
            self.notify("selecciona un flujo primero", severity="warning")
            return
        self.push_screen(IntruderScreen(self._flujo_actual))

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

    @property
    def solo_analizar_alcance(self) -> bool:
        """Sin alcance puesto no se filtra nada: una sesion recien abierta
        no puede dejar de analizar por descuido."""
        return self.alcance.configurado

    def poner_alcance(self, texto: str) -> list[str]:
        """Cambia el alcance y lo guarda. Devuelve las lineas que no se
        pudieron leer, para poder enseniarlas sin perder las buenas."""
        nuevo, errores = alc.Alcance.desde_texto_tolerante(texto)
        self.alcance = nuevo
        self.store.set_meta("alcance", nuevo.texto())
        self.refrescar_tabla()
        self.actualizar_estado()
        return errores

    def action_interceptar(self) -> None:
        if self.interceptor.activa and self.interceptor.pendientes():
            # con cosas esperando, x es «enseñamelas» y no «apaga»:
            # apagar por error soltaria lo que ibas a editar
            self._mostrar_detenida()
            return
        self.interceptor.activa = not self.interceptor.activa
        if not self.interceptor.activa:
            self.interceptor.soltar_todas()
        else:
            self.notify("interceptacion encendida: el navegador se para "
                        "en cada peticion", title="x la apaga", timeout=6)
        self.actualizar_estado()

    def _detenida_desde_hilo(self, d) -> None:
        """Llamado DESDE el hilo del motor: hay que saltar al bucle."""
        self.call_from_thread(self._mostrar_detenida)

    def _mostrar_detenida(self) -> None:
        pantalla = self.screen
        if isinstance(pantalla, InterceptaScreen):
            pantalla.refrescar()
            return
        if pantalla is self.screen_stack[0]:
            self.push_screen(InterceptaScreen(self.interceptor))
        else:
            # hay otra pantalla encima; avisar es mejor que arrancarle al
            # analista lo que estuviera haciendo
            self.notify("hay una peticion detenida; x para verla",
                        severity="warning")

    def action_mapa(self) -> None:
        """El mapa se arma de lo que ya se capturo, sin pedirle nada al
        servidor: esto ordena, no rastrea."""
        flujos = self.store.list_flows(limite=LIMITE_TABLA)
        if self.solo_alcance:
            flujos = [f for f in flujos if self.alcance.dentro(f.request.url)]
        self.push_screen(SitemapScreen(sitemap.construir(flujos)),
                         self._ir_al_flujo)

    def _ir_al_flujo(self, fid: int | None) -> None:
        """Lleva el cursor del historial al flujo elegido en el mapa.

        Si esta fuera de la tabla —filtro de texto o de alcance— se dice,
        en vez de no hacer nada y parecer que la tecla no funciona.
        """
        if fid is None:
            return
        tabla = self.query_one("#flujos", DataTable)
        try:
            tabla.move_cursor(row=tabla.get_row_index(str(fid)))
        except Exception:
            self.notify(f"el flujo {fid} no esta en la tabla; quita el filtro "
                        f"o el alcance para verlo", severity="warning")
            return
        tabla.focus()

    def action_alcance(self) -> None:
        sug = (sugerencia_desde(self._flujo_actual.request.url)
               if self._flujo_actual is not None else "")
        self.push_screen(AlcanceScreen(self.alcance.texto(),
                                       self.solo_alcance, sug))

    def poner_solo_alcance(self, valor: bool) -> None:
        self.solo_alcance = valor
        self.store.set_meta("solo_alcance", "si" if valor else "no")
        self.refrescar_tabla()
        self.actualizar_estado()

    def action_nota(self) -> None:
        if self._flujo_actual is None or self._flujo_actual.id is None:
            self.notify("selecciona un flujo primero", severity="warning")
            return
        self.push_screen(NotaScreen(self._flujo_actual.note), self._guardar_nota)

    def _guardar_nota(self, nota: str | None) -> None:
        f = self._flujo_actual
        if nota is None or f is None or f.id is None:
            return                              # se cerro con esc: no se toca
        f.note = nota
        self.store.set_note(f.id, nota)
        self._pintar_detalle(f)

    def action_confirmar(self) -> None:
        """Convierte un candidato en hallazgo validado, o lo devuelve.

        Solo esto despierta la columna `confirmed`. La severidad, el vector
        CVSS y la justificacion siguen esperando al reporte a proposito:
        inventarles interfaz ahora seria construir contra un formato de
        entregable que todavia no esta decidido.
        """
        hall = self.query_one("#hallazgos", DataTable)
        if not hall.row_count:
            return
        try:
            clave = hall.coordinate_to_cell_key((hall.cursor_row, 0)).row_key
            hid = int(clave.value)
        except (TypeError, ValueError, AttributeError):
            return
        actual = next((h for h in self.store.list_findings() if h.id == hid), None)
        if actual is None:
            return
        nuevo = not actual.confirmed
        self.store.set_confirmed(hid, nuevo)
        hall.update_cell(clave.value, self._col_ok, self._marca_ok(nuevo))

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
        self.notify("historial limpiado · candidatos y ataques se conservan")

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
        # primero el interceptor: si quedara algo detenido, el hilo del
        # motor seguiria esperando una decision que ya nadie va a tomar
        self.interceptor.cerrar()
        if self.engine:
            self.engine.stop()
        self.store.close()
