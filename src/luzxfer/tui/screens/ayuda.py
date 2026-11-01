"""Pantalla de ayuda: todas las teclas, agrupadas por para que sirven.

Existe porque el pie miente por omision. Textual descarta en silencio
los atajos que no caben en una fila, y con veinte atajos a ochenta
columnas —el ancho de cualquier terminal, y el unico que hay en
Termux— se veian siete. Las funciones que mas costaron eran justo las
invisibles: interceptar, el barrido, la cobertura, el conversor.

La solucion no fue apretar mas teclas en el pie, que a ningun ancho
caben todas, sino dejar en el pie lo que se usa a diario y poner aqui
la lista completa.

**Esta pantalla se construye de los atajos activos de la aplicacion,
nunca de una lista escrita a mano.** Una ayuda que se mantiene aparte
del codigo se desincroniza en el primer cambio, y entonces es peor que
no tenerla: manda a probar teclas que ya no hacen nada. Si alguien
remapea un atajo en su `config.ini`, aqui sale el suyo.
"""
from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Static

from ..paleta import P

# Como se agrupan los atajos. El orden es el de la pregunta que se hace
# quien abre esto: primero moverse, luego abrir una herramienta, luego
# hacerle algo al flujo que tiene delante.
GRUPOS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("moverse por el trafico",
     ("cursor_arriba", "cursor_abajo", "arriba", "abajo",
      "foco_filtro", "buscar", "quitar_foco")),
    ("herramientas",
     ("repeater", "repeater_enviar", "intruder", "interceptar",
      "barrido", "mapa", "alcance", "cobertura", "conversor",
      "comparar")),
    ("el flujo elegido",
     ("marcar", "nota", "confirmar", "vista", "cuerpo", "exportar")),
    ("la sesion",
     ("sesiones", "limpiar", "ayuda", "salir")),
)

# Las teclas que Textual nombra de una forma y el teclado tiene escrita
# de otra. Poner "slash" en una ayuda obliga a traducir mentalmente.
NOMBRES = {
    "slash": "/",
    "escape": "esc",
    "question_mark": "?",
    "comma": ",",
    "full_stop": ".",
    "space": "espacio",
}


def nombre_tecla(tecla: str) -> str:
    """La tecla como la lee una persona, no como la nombra Textual."""
    return NOMBRES.get(tecla, tecla)


class AyudaScreen(ModalScreen):
    """La lista completa de atajos. Se cierra con esc, q o ?."""

    BINDINGS = [
        Binding("escape", "cerrar", "cerrar"),
        Binding("q", "cerrar", "cerrar"),
        Binding("question_mark", "cerrar", "cerrar"),
    ]

    def __init__(self, atajos: list[tuple[str, str, str]]):
        """`atajos` son ternas (id, tecla, descripcion) ya resueltas."""
        super().__init__()
        self.atajos = atajos

    def compose(self) -> ComposeResult:
        with Vertical(id="ayuda-caja"):
            yield Static(
                Text.assemble(
                    ("teclas", f"bold {P.acento}"),
                    (f"   {len(self.atajos)} atajos", P.secundario),
                    ("   esc cierra", P.tenue),
                ),
                id="ayuda-titulo")
            with VerticalScroll(id="ayuda-scroll"):
                yield Static(self._texto(), id="ayuda-lista")

    def _texto(self) -> Text:
        por_id = {ident: (tecla, desc) for ident, tecla, desc in self.atajos}
        agrupados = set()
        partes: list[tuple[str, str]] = []

        for titulo, ids in GRUPOS:
            filas = [(i, *por_id[i]) for i in ids if i in por_id]
            if not filas:
                continue
            agrupados.update(i for i, _t, _d in filas)
            partes += self._grupo(titulo, filas)

        # Lo que no este en ningun grupo sale igual, al final. Un atajo
        # nuevo que nadie clasifico tiene que aparecer: perderlo aqui
        # seria repetir el fallo del pie, solo que mas escondido.
        sueltos = [(i, *por_id[i]) for i in por_id if i not in agrupados]
        if sueltos:
            partes += self._grupo("otros", sueltos)

        return Text.assemble(*partes)

    def _grupo(self, titulo: str,
               filas: list[tuple[str, str, str]]) -> list[tuple[str, str]]:
        partes: list[tuple[str, str]] = [(f"{titulo}\n", f"bold {P.acento}")]
        ancho = max(len(nombre_tecla(t)) for _i, t, _d in filas)
        for _ident, tecla, desc in filas:
            partes.append((f"  {nombre_tecla(tecla):<{ancho}}  ", P.info))
            partes.append((f"{desc}\n", P.texto))
        partes.append(("\n", P.tenue))
        return partes

    def action_cerrar(self) -> None:
        self.dismiss()
