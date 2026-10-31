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
import sqlite3
from dataclasses import dataclass
from pathlib import Path

NOMBRE_DEFECTO = "predeterminada"
LARGO_MAXIMO = 64

# Puntero a la ultima sesion abierta. Va junto a dir_sesiones(), no dentro,
# porque es estado global y no una sesion mas.
_ARCHIVO_ULTIMA = "ultima"

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


@dataclass(slots=True)
class ResumenSesion:
    """Lo que hace falta para elegir una sesion sin abrirla."""
    nombre: str
    ruta: Path
    flujos: int = 0
    candidatos: int = 0
    modificada: float = 0.0
    ilegible: bool = False


def _contar(ruta: Path, extra: str = "") -> tuple[int, int]:
    """(flujos, candidatos) de una sesion, abierta en solo lectura."""
    con = sqlite3.connect(f"file:{ruta}?mode=ro{extra}", uri=True)
    try:
        return (
            int(con.execute("SELECT COUNT(*) FROM flows").fetchone()[0]),
            int(con.execute("SELECT COUNT(*) FROM findings").fetchone()[0]),
        )
    finally:
        con.close()


def resumen(ruta: Path) -> ResumenSesion:
    """Cuenta flujos y candidatos SIN abrir la sesion en escritura.

    Va por mode=ro y no por Store a proposito: Store ejecuta el esquema al
    conectar, asi que listar el directorio convertiria cualquier archivo
    suelto en una sesion vacia recien creada.

    Pero mode=ro no es gratis: leer una base en modo WAL necesita el indice
    de memoria compartida, asi que SQLite crea -shm y -wal aunque solo se
    lea, y una conexion de solo lectura no puede borrarlos al cerrar. Los
    limpia la siguiente conexion de escritura. Es basura inofensiva y es el
    precio de leer una sesion que otra instancia puede tener abierta: con
    el WAL a la vista los contadores salen correctos, y con immutable=1
    saldrian viejos.

    El respaldo con immutable=1 es para cuando el directorio no se puede
    escribir — sesiones en un medio de solo lectura, que es como se guarda
    evidencia. Ahi no hay -shm posible, y sin este segundo intento toda
    sesion sana se reportaria como ilegible, que es una mentira peor que
    la basura.

    Un archivo que no es SQLite no falla al conectar sino al consultar, asi
    que el try cubre las consultas y no solo el connect.
    """
    try:
        modificada = ruta.stat().st_mtime
    except OSError:
        modificada = 0.0

    r = ResumenSesion(nombre=ruta.stem, ruta=ruta, modificada=modificada)
    for extra in ("", "&immutable=1"):
        try:
            r.flujos, r.candidatos = _contar(ruta, extra)
            return r
        except sqlite3.Error:
            continue
    r.ilegible = True              # corrupto, ajeno o de otra version
    return r


def listar() -> list[ResumenSesion]:
    """Las sesiones que hay, de la mas reciente a la mas vieja."""
    base = dir_sesiones()
    if not base.is_dir():
        return []
    salida = [resumen(p) for p in base.glob("*.db") if p.is_file()]
    salida.sort(key=lambda s: s.modificada, reverse=True)
    return salida


def ultima() -> str | None:
    """El nombre de la ultima sesion abierta, si todavia existe.

    None si el puntero no esta, si tiene basura o si nombra una sesion ya
    borrada. El puntero sobrevive al archivo que nombra, y que haya
    quedado huerfano no es razon para no poder arrancar.
    """
    try:
        crudo = (dir_datos() / _ARCHIVO_ULTIMA).read_text(encoding="utf-8")
    except OSError:
        return None
    try:
        nombre = valida_nombre(crudo)          # tambien quita el salto de linea
    except NombreInvalido:
        return None
    return nombre if ruta_de(nombre).is_file() else None


def recordar_ultima(nombre: str) -> None:
    """Anota cual fue la ultima sesion abierta."""
    nombre = valida_nombre(nombre)
    base = dir_datos()
    base.mkdir(parents=True, exist_ok=True)
    (base / _ARCHIVO_ULTIMA).write_text(nombre, encoding="utf-8")


def abrir(nombre: str | None = None) -> tuple[str, Path]:
    """Decide que sesion usar, prepara el directorio y la recuerda.

    Sin nombre explicito retoma la ultima; si no hay ninguna, el nombre
    por defecto. No crea el archivo de la sesion: eso es de Store al
    conectarse, y asi una sesion recien nombrada no deja un .db vacio si
    el usuario se arrepiente.

    Puede lanzar NombreInvalido, u OSError si el directorio no se puede
    crear. Las dos las traduce __main__ a un mensaje y un codigo de salida.
    """
    efectivo = valida_nombre(nombre) if nombre else (ultima() or NOMBRE_DEFECTO)
    dir_sesiones().mkdir(parents=True, exist_ok=True)
    recordar_ultima(efectivo)
    return efectivo, ruta_de(efectivo)


def borrar(nombre: str) -> None:
    """Borra la sesion y los auxiliares del WAL. Inexistente: no hace nada.

    Valida el nombre igual que todo lo demas. Es la operacion destructiva
    del modulo, asi que con mas razon.
    """
    ruta = ruta_de(nombre)
    for p in (ruta, ruta.with_suffix(".db-wal"), ruta.with_suffix(".db-shm")):
        p.unlink(missing_ok=True)
