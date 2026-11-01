"""Pantalla del Intruder: marcar, configurar, lanzar y mirar.

El orden de la pantalla es el orden del trabajo: arriba la peticion con
sus marcadores, en medio los payloads y el modo, abajo los resultados.

Ordenar por largo es el gesto central de la tabla, no un adorno: en un
fuzzing de credenciales o de IDOR lo que delata el acierto casi nunca es
el codigo de estado —suelen ser todos 200— sino que una respuesta mida
distinto a las demas.
"""
from __future__ import annotations

from rich.text import Text
from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, DataTable, Input, Select, Static, TextArea

from ...core.models import Flow
from ...core.tools import intruder, repeater
from ..paleta import P
from .intruder_detalle import DetalleResultadoScreen
from .intruder_payloads import CargarPayloadsScreen

AVISO_GRANDE = 1000


class IntruderScreen(ModalScreen):
    BINDINGS = [
        Binding("escape", "cerrar", "cerrar"),
        Binding("ctrl+m", "marcar", "marcar"),
        Binding("ctrl+l", "lanzar", "lanzar"),
        # ctrl+c no: en una terminal eso es salir, y abortar un ataque no
        # deberia parecerse a cerrar el programa
        Binding("ctrl+x", "abortar", "abortar"),
        Binding("ctrl+o", "ordenar", "ordenar por largo"),
        Binding("ctrl+y", "cargar_payloads", "cargar payloads", priority=True),
    ]

    def __init__(self, flujo: Flow):
        super().__init__()
        self.flujo = flujo
        self.ataque: intruder.Ataque | None = None
        self._ataque_id: int | None = None
        self._confirmado = False
        self._desc = False            # orden actual de la columna largo
        # los resultados de la tanda actual, por numero de fila, para poder
        # reconstruir la peticion que salio cuando se elige una fila
        self._resultados: dict[int, intruder.Resultado] = {}

    # ------------------------------------------------------------------
    def compose(self) -> ComposeResult:
        with Vertical(id="int-caja"):
            yield Static(
                Text.assemble(
                    ("intruder", f"bold {P.acento}"),
                    (f"  ·  flujo {self.flujo.id}", P.secundario),
                    ("   ctrl+m marcar · ctrl+y payloads · ctrl+l lanzar · "
                     "ctrl+x abortar · enter ver la peticion · esc cerrar",
                     P.tenue),
                ),
                id="int-titulo",
            )
            with Horizontal(id="int-arriba"):
                yield TextArea(self.flujo.request.raw(), id="int-editor",
                               soft_wrap=False)
                with Vertical(id="int-lado"):
                    yield Select(
                        [(m.value, m) for m in intruder.Modo],
                        value=intruder.Modo.SNIPER, allow_blank=False,
                        id="int-modo",
                    )
                    yield TextArea("", id="int-payloads", soft_wrap=False)
                    yield Input(placeholder="grep, separado por comas",
                                id="int-grep")
                    with Horizontal(id="int-botones"):
                        yield Button("lanzar", variant="primary", id="int-lanzar")
                        yield Button("cargar", id="int-cargar")
                        yield Button("abortar", id="int-abortar")
            yield Static("", id="int-estado")
            yield DataTable(id="int-resultados", cursor_type="row")

    def on_mount(self) -> None:
        t = self.query_one("#int-resultados", DataTable)
        t.add_column("#", width=6)
        t.add_column("payload", width=30)
        t.add_column("cod", width=5)
        # la clave, no la etiqueta: sort() la pide asi
        self._col_largo = t.add_column("largo", width=9)
        t.add_column("ms", width=7)
        t.add_column("grep")
        self.query_one("#int-editor", TextArea).focus()
        self._refrescar_total()

    # ------------------------------------------------------- configuracion
    def _config(self) -> intruder.Config:
        texto = self.query_one("#int-payloads", TextArea).text
        grep = [g.strip() for g in
                self.query_one("#int-grep", Input).value.split(",") if g.strip()]
        return intruder.Config(
            modo=self.query_one("#int-modo", Select).value,
            conjuntos=intruder.conjuntos_desde_texto(texto),
            grep=grep,
            tls=self._tls(),
        )

    def _destino(self) -> tuple[str, int] | None:
        """A donde va la peticion EDITADA, que no tiene por que ser a
        donde fue el flujo del que salimos."""
        try:
            _, _, _, cabeceras, _ = repeater.parse_raw(
                self.query_one("#int-editor", TextArea).text)
        except repeater.ErrorPeticion:
            return None
        return repeater.destino_de(cabeceras)

    def _tls(self) -> bool | None:
        """Si el ataque va por TLS. None = que lo decida el puerto.

        El esquema del flujo original solo se impone mientras el objetivo
        siga siendo el mismo. En cuanto editas el Host, de donde saliste
        ya no dice nada sobre a donde vas: un flujo http:// apuntado a un
        443 mandaria el ataque entero en claro contra un puerto TLS, y eso
        falla raro en vez de fallar claro.

        Un Host sin puerto no revela el esquema, y por eso no basta con
        mirar el puerto siempre: contra el mismo objetivo, el flujo es la
        mejor pista que hay.
        """
        destino = self._destino()
        original = self.flujo.request.host.split(":")[0]
        if destino is None or destino[0] == original:
            return self.flujo.request.url.startswith("https://")
        return None

    def _etiqueta_destino(self) -> str:
        """Contra quien se archiva el ataque: el destino real, no el del
        flujo original. Un ataque guardado contra el objetivo equivocado
        es evidencia de pentest mal atribuida."""
        destino = self._destino()
        if destino is None:
            return self.flujo.request.host
        host, puerto = destino
        return host if puerto in (80, 443) else f"{host}:{puerto}"

    def _preparar(self) -> intruder.Ataque:
        """Construye el ataque. Lanza ErrorAtaque si algo no cuadra."""
        return intruder.Ataque(self.query_one("#int-editor", TextArea).text,
                               self._config())

    def _refrescar_total(self) -> None:
        """Dice cuantas peticiones saldrian, sin mandar ninguna."""
        try:
            a = self._preparar()
        except intruder.ErrorAtaque as e:
            self._estado(str(e), P.secundario)
            return
        aviso = ""
        if a.avisos:
            aviso = (f"   ⚠ {len(a.avisos)} payload(s) no sobreviven a latin-1 "
                     f"y viajarian mutados")
        self._estado(f"{a.total} peticion(es){aviso}",
                     P.acento if a.avisos else P.atenuado)

    def _estado(self, texto: str, color: str = P.atenuado) -> None:
        self.query_one("#int-estado", Static).update(Text(texto, style=color))

    def on_text_area_changed(self, ev: TextArea.Changed) -> None:
        if ev.text_area.id in ("int-editor", "int-payloads"):
            self._confirmado = False      # cambio algo: vuelve a confirmarse
            self._refrescar_total()

    def on_select_changed(self, ev: Select.Changed) -> None:
        if ev.select.id == "int-modo":
            self._refrescar_total()

    # ------------------------------------------------------------ marcar
    def _marcar_rango(self, inicio: int, fin: int) -> None:
        ed = self.query_one("#int-editor", TextArea)
        try:
            ed.text = intruder.marcar(ed.text, inicio, fin)
        except intruder.ErrorAtaque as e:
            self._estado(str(e), P.peligro)

    def action_marcar(self) -> None:
        """Envuelve la seleccion en marcadores, o la palabra del cursor.

        Existe porque § no esta en la mayoria de teclados: el marcador es
        el de Burp para que una peticion copiada de alli se pegue y
        funcione, pero nadie deberia tener que teclearlo.
        """
        ed = self.query_one("#int-editor", TextArea)
        doc = ed.document
        inicio = doc.get_index_from_location(ed.selection.start)
        fin = doc.get_index_from_location(ed.selection.end)
        if inicio > fin:
            inicio, fin = fin, inicio
        if inicio == fin:
            inicio, fin = self._palabra_en(ed.text, inicio)
        if inicio == fin:
            self._estado("no hay nada que marcar bajo el cursor", P.secundario)
            return
        self._marcar_rango(inicio, fin)

    @staticmethod
    def _palabra_en(texto: str, i: int) -> tuple[int, int]:
        """Los limites de la palabra que toca el cursor.

        «Palabra» aqui es lo que suele ser un valor en una peticion: se
        corta en los separadores de HTTP y de los formatos que viajan
        dentro, no solo en los espacios.
        """
        cortes = ' \t\r\n"\'=&?/;:,{}[]<>'
        inicio = i
        while inicio > 0 and texto[inicio - 1] not in cortes:
            inicio -= 1
        fin = i
        while fin < len(texto) and texto[fin] not in cortes:
            fin += 1
        return inicio, fin

    # ------------------------------------------------------------ lanzar
    def action_lanzar(self) -> None:
        if self.ataque is not None and not self.ataque.terminado:
            self._estado("ya hay un ataque corriendo", P.acento)
            return
        try:
            a = self._preparar()
        except intruder.ErrorAtaque as e:
            self._estado(str(e), P.peligro)
            return

        # ultima barrera antes de mandar peticiones a un sistema ajeno
        if a.total > AVISO_GRANDE and not self._confirmado:
            self._confirmado = True
            self._estado(f"son {a.total} peticiones. ctrl+l otra vez para "
                         f"confirmar", P.peligro)
            return

        self.ataque = a
        tabla = self.query_one("#int-resultados", DataTable)
        tabla.clear()
        self._resultados.clear()      # empieza una tanda nueva
        self._ataque_id = self.app.store.add_ataque(
            a.cfg.modo.value, self._etiqueta_destino(),
            self.query_one("#int-editor", TextArea).text, a.total)
        self._estado(f"lanzando… 0/{a.total}", P.acento)
        self._correr(a)

    @work(thread=True, exclusive=True)
    def _correr(self, a: intruder.Ataque) -> None:
        """El ataque va fuera del hilo de la interfaz: mil peticiones no
        pueden congelar la TUI hasta que terminen."""
        a.correr(lambda r: self.app.call_from_thread(self._llego, r))
        self.app.call_from_thread(self._fin, a)

    def _llego(self, r: intruder.Resultado) -> None:
        if self._ataque_id is not None:
            self.app.store.add_resultado(self._ataque_id, r)
        self._resultados[r.n] = r
        self._fila(r)
        if self.ataque is not None:
            self._estado(f"lanzando… {self.ataque.enviadas}/{self.ataque.total}",
                         P.acento)

    def _fin(self, a: intruder.Ataque) -> None:
        if self._ataque_id is not None:
            self.app.store.cerrar_ataque(self._ataque_id, a.enviadas, a.abortado)
        self._estado(
            f"{'abortado' if a.abortado else 'terminado'}: "
            f"{a.enviadas} de {a.total}   ·   ctrl+o ordena por largo",
            P.peligro if a.abortado else P.bien)

    def action_abortar(self) -> None:
        if self.ataque is not None and not self.ataque.terminado:
            self.ataque.abortar()
            self._estado("abortando: se esperan las peticiones en vuelo",
                         P.acento)

    def action_cerrar(self) -> None:
        self.action_abortar()      # no dejar un ataque suelto al cerrar
        self.dismiss()

    def action_cargar_payloads(self) -> None:
        """Abre el cargador y mete lo que devuelva en el area de payloads."""
        self.app.push_screen(CargarPayloadsScreen(), self._insertar_payloads)

    def _insertar_payloads(self, payloads: list[str] | None) -> None:
        if not payloads:
            return                        # se cancelo, o no habia nada
        area = self.query_one("#int-payloads", TextArea)
        actual = area.text
        # no pisar lo que ya hay: se añade debajo, con un salto si hace falta
        nuevo = "\n".join(payloads)
        area.text = f"{actual}\n{nuevo}" if actual.strip() else nuevo
        self._refrescar_total()
        self.notify(f"{len(payloads)} payload(s) cargados", timeout=4)

    def on_button_pressed(self, ev: Button.Pressed) -> None:
        if ev.button.id == "int-lanzar":
            self.action_lanzar()
        elif ev.button.id == "int-cargar":
            self.action_cargar_payloads()
        elif ev.button.id == "int-abortar":
            self.action_abortar()

    # --------------------------------------------------------- resultados
    def on_data_table_row_selected(self, ev: DataTable.RowSelected) -> None:
        """Al elegir una fila, enseña la peticion que salio en ella.

        Se reconstruye con la misma funcion que uso el ataque sobre el
        crudo que se lanzo, asi que es lo que viajo, no una aproximacion.
        """
        if ev.data_table.id != "int-resultados" or self.ataque is None:
            return
        try:
            n = int(ev.row_key.value)
        except (TypeError, ValueError):
            return
        r = self._resultados.get(n)
        if r is None:
            return
        peticion = intruder.sustituir(self.ataque.crudo, r.payloads)
        cod = "ERR" if r.status is None else str(r.status)
        titulo = f"#{r.n} · {' / '.join(r.payloads)} · {cod} · {r.largo}B"
        self.app.push_screen(DetalleResultadoScreen(titulo, peticion))

    COLOR_COD = {2: P.bien, 3: P.info, 4: P.acento, 5: P.peligro}

    def _fila(self, r: intruder.Resultado) -> None:
        tabla = self.query_one("#int-resultados", DataTable)
        cod = (Text("ERR", style=P.peligro) if r.status is None
               else Text(str(r.status),
                         style=f"bold {self.COLOR_COD.get(r.status // 100, '{P.texto}')}"))
        tabla.add_row(
            Text(str(r.n), style=P.secundario),
            Text(" / ".join(r.payloads)[:30], style=P.texto),
            cod,
            Text(str(r.largo), style=P.atenuado),
            Text(str(r.ms), style=P.secundario),
            Text(", ".join(r.grep) if r.grep else (r.error[:40] if r.error else ""),
                 style=P.bien if r.grep else P.peligro),
            key=str(r.n),
        )

    def action_ordenar(self) -> None:
        self.ordenar_por_largo()

    def ordenar_por_largo(self) -> None:
        """De mayor a menor y al reves. Es el gesto que encuentra la aguja:
        con todas las respuestas en 200, lo que delata el acierto es que
        una mida distinto."""
        self._desc = not self._desc
        self.query_one("#int-resultados", DataTable).sort(
            self._col_largo, key=lambda v: int(str(v)), reverse=self._desc)
