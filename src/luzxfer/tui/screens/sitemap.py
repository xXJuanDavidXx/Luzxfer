"""Pantalla del mapa del sitio.

El historial responde «qué pasó y en qué orden»; esto responde «qué forma
tiene el objetivo». Mirando tres mil filas no se ve que existe un
`/admin/` con tres rutas dentro, y eso es lo que uno vino a buscar.

El gesto que la hace útil es elegir una rama y caer en el tráfico que la
produjo: ver la forma no sirve de nada si volver al detalle cuesta.
"""
from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Static, Tree

from ...core.tools import sitemap

COLOR_ESTADO = {2: "#6fcf8f", 3: "#5fa8d3", 4: "#f0a93b", 5: "#e05c5c"}


def _etiqueta(n: sitemap.Nodo) -> Text:
    """Lo que se lee de un nodo de un vistazo."""
    t = Text()
    t.append(n.nombre, style="#d9dde5" if n.visitado else "#7b8496")

    if not n.visitado:
        # un tramo que existe solo porque algo mas abajo se pidio. Es la
        # pista mas barata que da el mapa: nadie ha tocado /api, y a lo
        # mejor contesta algo
        t.append("  no pedido", style="italic #5c6578")
    else:
        for codigo in sorted(n.estados):
            t.append(f"  {codigo}",
                     style=f"bold {COLOR_ESTADO.get(codigo // 100, '#d9dde5')}")
        if not n.estados:
            t.append("  ERR", style="#e05c5c")
        if len(n.metodos) > 1 or n.metodos - {"GET"}:
            t.append(f"  {'/'.join(sorted(n.metodos))}", style="#a8b0c0")

    # El contador significa cosas distintas segun la fila, asi que se
    # elige uno solo y se dice cual. En un nodo visitado, cuantas veces
    # se pidio ESA ruta —«users ×2» tiene que querer decir que se pidio
    # dos veces, no que debajo hay dos cosas—. En un tramo no pedido no
    # hay ambiguedad posible: todo lo que cuenta viene de abajo, y saber
    # cuanto dice si vale la pena desplegarlo.
    cuenta = n.pedido if n.visitado else n.total
    if cuenta > 1:
        t.append(f"  ×{cuenta}", style="#5c6578")
    return t


class SitemapScreen(ModalScreen):
    BINDINGS = [
        Binding("escape", "cerrar", "cerrar"),
        Binding("enter", "abrir", "ir al flujo"),
    ]

    def __init__(self, raiz: list[sitemap.Nodo]):
        super().__init__()
        self.raiz = raiz

    def compose(self) -> ComposeResult:
        peticiones = sum(n.total for n in self.raiz)
        rutas = sitemap.contar_rutas(self.raiz)
        with Vertical(id="mapa-caja"):
            yield Static(
                Text.assemble(
                    ("mapa del sitio", "bold #f0a93b"),
                    (f"   {rutas} rutas distintas de {peticiones} peticiones",
                     "#a8b0c0"),
                    ("   enter va al flujo · esc cierra", "#5c6578"),
                ),
                id="mapa-titulo",
            )
            yield Tree("objetivos", id="mapa")

    def on_mount(self) -> None:
        arbol = self.query_one("#mapa", Tree)
        arbol.show_root = False
        for host in self.raiz:
            rama = arbol.root.add(
                Text.assemble((host.nombre, "bold #d9dde5"),
                              (f"  ×{host.total}", "#5c6578")),
                data=host, expand=True)
            self._colgar(rama, host)
        arbol.focus()

    def _colgar(self, rama, nodo: sitemap.Nodo) -> None:
        for hijo in nodo.hijos:
            # se expande solo mientras el arbol sea estrecho: abrirlo
            # entero en un objetivo grande llena la pantalla de ruido y
            # esconde justamente la forma que se vino a ver
            sub = rama.add(_etiqueta(hijo), data=hijo,
                           expand=len(nodo.hijos) <= 8)
            self._colgar(sub, hijo)

    # ------------------------------------------------------------------
    def action_abrir(self) -> None:
        """Devuelve el id del flujo de la rama elegida, si tiene alguno.

        Se toma el ultimo: es el mas reciente, que es casi siempre el que
        interesa mirar cuando una ruta se pidio varias veces.
        """
        arbol = self.query_one("#mapa", Tree)
        nodo = arbol.cursor_node
        datos = nodo.data if nodo is not None else None
        if datos is None or not datos.flujos:
            return
        self.dismiss(datos.flujos[-1])

    def action_cerrar(self) -> None:
        self.dismiss(None)
