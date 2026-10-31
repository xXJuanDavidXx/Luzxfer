"""Sesiones: donde vive el historial y como se llama.

El historial de un pentest es evidencia, asi que por defecto va a disco y no
a memoria. Este modulo resuelve donde va, valida el nombre que escribe el
usuario y mas adelante lista lo que ya hay. No abre el almacen: eso es de
Store, y esa separacion es la que permite listar sesiones sin tocarlas.

La lista blanca de nombres no es paranoia de mas. El nombre lo escribe el
usuario y se convierte en una ruta de archivo: sin ella, 'luzxfer -s ../otro'
escribe fuera del directorio de sesiones. En una herramienta de seguridad eso
es inaceptable, y una lista blanca es mas corta de leer y mas dificil de
equivocar que cualquier saneado.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

NOMBRE_DEFECTO = "predeterminada"
LARGO_MAXIMO = 64

# Letras, digitos, punto, guion bajo y guion, empezando por letra o digito.
# Sin '/' ni '\' ni bytes nulos no hay traversal posible, y exigir que el
# primer caracter sea alfanumerico descarta '..' y los ocultos de un golpe.
_PERMITIDO = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


class NombreInvalido(ValueError):
    """El nombre de sesion no se puede usar como nombre de archivo."""


def dir_datos() -> Path:
    """Donde guarda sus cosas luzxfer. No crea nada.

    XDG_DATA_HOME manda, pero solo si es absoluto: la especificacion dice
    que una ruta relativa ahi es invalida y que hay que ignorarla.
    """
    xdg = os.environ.get("XDG_DATA_HOME", "")
    if xdg and Path(xdg).is_absolute():
        return Path(xdg) / "luzxfer"
    return Path.home() / ".local" / "share" / "luzxfer"


def dir_sesiones() -> Path:
    """Donde viven los archivos de sesion. No crea nada."""
    return dir_datos() / "sesiones"


def valida_nombre(nombre: str) -> str:
    """Devuelve el nombre ya normalizado, o lanza NombreInvalido.

    El mensaje de error dice que se permite, porque lo va a leer alguien
    en una terminal y no un depurador.
    """
    limpio = nombre.strip()
    if not limpio or len(limpio) > LARGO_MAXIMO or not _PERMITIDO.match(limpio):
        raise NombreInvalido(
            f"nombre de sesion invalido: {nombre!r}. Se permiten letras, "
            f"digitos, punto, guion bajo y guion, empezando por letra o "
            f"digito, hasta {LARGO_MAXIMO} caracteres."
        )
    return limpio


def ruta_de(nombre: str) -> Path:
    """El archivo de esa sesion. Valida antes de construir la ruta."""
    return dir_sesiones() / f"{valida_nombre(nombre)}.db"
