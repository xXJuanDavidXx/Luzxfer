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
from ...core.tools import intruder

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
    ]

    def __init__(self, flujo: Flow):
        super().__init__()
        self.flujo = flujo
        self.ataque: intruder.Ataque | None = None
        self._ataque_id: int | None = None
        self._confirmado = False
        self._desc = False            # orden actual de la columna largo

    # ------------------------------------------------------------------
    def compose(self) -> ComposeResult:
        with Vertical(id="int-caja"):
            yield Static(
                Text.assemble(
                    ("intruder", "bold #f0a93b"),
                    (f"  ·  flujo {self.flujo.id}", "#7b8496"),
                    ("   ctrl+m marcar · ctrl+l lanzar · ctrl+x abortar · esc cerrar",
                     "#5c6578"),
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
            tls=self.flujo.request.url.startswith("https://"),
        )

    def _preparar(self) -> intruder.Ataque:
        """Construye el ataque. Lanza ErrorAtaque si algo no cuadra."""
        return intruder.Ataque(self.query_one("#int-editor", TextArea).text,
                               self._config())

    def _refrescar_total(self) -> None:
        """Dice cuantas peticiones saldrian, sin mandar ninguna."""
        try:
            a = self._preparar()
        except intruder.ErrorAtaque as e:
            self._estado(str(e), "#7b8496")
            return
        aviso = ""
        if a.avisos:
            aviso = (f"   ⚠ {len(a.avisos)} payload(s) no sobreviven a latin-1 "
                     f"y viajarian mutados")
        self._estado(f"{a.total} peticion(es){aviso}",
                     "#f0a93b" if a.avisos else "#a8b0c0")

    def _estado(self, texto: str, color: str = "#a8b0c0") -> None:
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
            self._estado(str(e), "#e05c5c")

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
            self._estado("no hay nada que marcar bajo el cursor", "#7b8496")
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
            self._estado("ya hay un ataque corriendo", "#f0a93b")
            return
        try:
            a = self._preparar()
        except intruder.ErrorAtaque as e:
            self._estado(str(e), "#e05c5c")
            return

        # ultima barrera antes de mandar peticiones a un sistema ajeno
        if a.total > AVISO_GRANDE and not self._confirmado:
            self._confirmado = True
            self._estado(f"son {a.total} peticiones. ctrl+l otra vez para "
                         f"confirmar", "#e05c5c")
            return

        self.ataque = a
        tabla = self.query_one("#int-resultados", DataTable)
        tabla.clear()
        self._ataque_id = self.app.store.add_ataque(
            a.cfg.modo.value, self.flujo.request.host,
            self.query_one("#int-editor", TextArea).text, a.total)
        self._estado(f"lanzando… 0/{a.total}", "#f0a93b")
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
        self._fila(r)
        if self.ataque is not None:
            self._estado(f"lanzando… {self.ataque.enviadas}/{self.ataque.total}",
                         "#f0a93b")

    def _fin(self, a: intruder.Ataque) -> None:
        if self._ataque_id is not None:
            self.app.store.cerrar_ataque(self._ataque_id, a.enviadas, a.abortado)
        self._estado(
            f"{'abortado' if a.abortado else 'terminado'}: "
            f"{a.enviadas} de {a.total}   ·   ctrl+o ordena por largo",
            "#e05c5c" if a.abortado else "#6fcf8f")

    def action_abortar(self) -> None:
        if self.ataque is not None and not self.ataque.terminado:
            self.ataque.abortar()
            self._estado("abortando: se esperan las peticiones en vuelo",
                         "#f0a93b")

    def action_cerrar(self) -> None:
        self.action_abortar()      # no dejar un ataque suelto al cerrar
        self.dismiss()

    def on_button_pressed(self, ev: Button.Pressed) -> None:
        if ev.button.id == "int-lanzar":
            self.action_lanzar()
        elif ev.button.id == "int-abortar":
            self.action_abortar()

    # --------------------------------------------------------- resultados
    COLOR_COD = {2: "#6fcf8f", 3: "#5fa8d3", 4: "#f0a93b", 5: "#e05c5c"}

    def _fila(self, r: intruder.Resultado) -> None:
        tabla = self.query_one("#int-resultados", DataTable)
        cod = (Text("ERR", style="#e05c5c") if r.status is None
               else Text(str(r.status),
                         style=f"bold {self.COLOR_COD.get(r.status // 100, '#d9dde5')}"))
        tabla.add_row(
            Text(str(r.n), style="#7b8496"),
            Text(" / ".join(r.payloads)[:30], style="#d9dde5"),
            cod,
            Text(str(r.largo), style="#a8b0c0"),
            Text(str(r.ms), style="#7b8496"),
            Text(", ".join(r.grep) if r.grep else (r.error[:40] if r.error else ""),
                 style="#6fcf8f" if r.grep else "#e05c5c"),
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
