"""Atajos configurables.

    [teclas]
    intruder = ctrl+i
    barrido  = B

La clave es el nombre de la accion —el `id` de su atajo— y el valor la
tecla. Textual lo aplica con su propio mecanismo de keymap, asi que el
pie de la pantalla se regenera solo: la ayuda nunca puede quedarse
diciendo la tecla de antes.

Lo que este modulo cuida es que una configuracion mala no deje la
herramienta inutilizable. Quedarse sin poder salir del programa por un
error de tecleo seria el peor resultado posible, asi que lo que no se
entiende se ignora y se dice.
"""
from __future__ import annotations

from pathlib import Path

from .ajustes import leer_ini

# Las acciones que se pueden remapear. Es la lista de ids de los atajos
# de la pantalla principal; hay un test que la compara con los de
# verdad, porque una lista que se desincroniza del codigo deja al
# usuario configurando atajos que no hacen nada.
ACCIONES = {
    "salir", "repeater", "intruder", "sesiones", "alcance", "mapa",
    "interceptar", "barrido", "cobertura", "marcar", "nota",
    "confirmar", "vista", "cuerpo", "limpiar", "arriba", "abajo",
    "foco_filtro", "buscar",
    "cursor_abajo", "cursor_arriba", "quitar_foco",
}


def leer(ruta: Path | None = None) -> tuple[dict[str, str], list[str]]:
    """El mapa accion -> tecla, y los problemas encontrados."""
    cfg, avisos = leer_ini(ruta)
    if cfg is None or not cfg.has_section("teclas"):
        return {}, avisos

    mapa: dict[str, str] = {}
    usadas: dict[str, str] = {}
    for accion, tecla in cfg.items("teclas"):
        accion = accion.strip().lower()
        tecla = tecla.strip()
        if accion not in ACCIONES:
            avisos.append(
                f"accion '{accion}' no existe; hay: "
                f"{', '.join(sorted(ACCIONES))}")
            continue
        if not tecla:
            avisos.append(f"accion '{accion}': falta la tecla")
            continue
        if tecla in usadas:
            # pisar un atajo con otro deja una de las dos acciones
            # muerta, y en silencio seria imposible de diagnosticar
            avisos.append(
                f"la tecla '{tecla}' se pide para '{accion}' y para "
                f"'{usadas[tecla]}'; se queda con '{usadas[tecla]}'")
            continue
        usadas[tecla] = accion
        mapa[accion] = tecla
    return mapa, avisos
