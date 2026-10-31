"""Punto de entrada: luzxfer [opciones]."""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path


def _listar_sesiones() -> int:
    """Imprime las sesiones que hay y sale. No arranca nada."""
    from .core import sesiones

    filas = sesiones.listar()
    base = sesiones.dir_sesiones()
    if not filas:
        print(f"no hay sesiones todavia en {base}")
        return 0

    actual = sesiones.ultima()
    print(f"sesiones en {base}:")
    for s in filas:
        marca = "  <- ultima" if s.nombre == actual else ""
        if s.ilegible:
            print(f"  {s.nombre:<24} ilegible{marca}")
            continue
        cuando = time.strftime("%Y-%m-%d %H:%M", time.localtime(s.modificada))
        print(f"  {s.nombre:<24} {s.flujos:>7} flujos  {s.candidatos:>5} cand."
              f"  {cuando}{marca}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="luzxfer",
        description="Proxy de interceptacion y banco de trabajo de pentesting web, "
                    "para la terminal.",
        epilog="El motor integrado no intercepta HTTPS; para eso hace falta "
               "el motor de mitmproxy (pip install luzxfer[mitm]).",
    )
    ap.add_argument("-p", "--port", type=int, default=8080,
                    help="puerto del proxy (8080)")
    ap.add_argument("-H", "--host", default="127.0.0.1",
                    help="interfaz donde escuchar (127.0.0.1). No la abras "
                         "a la red: esta herramienta manda peticiones arbitrarias")
    ap.add_argument("-u", "--upstream", default=None, metavar="URL",
                    help="modo inverso: navega el puerto del proxy y el reenvia "
                         "a esta URL. Util para labs locales, porque los "
                         "navegadores no mandan localhost por el proxy")
    ap.add_argument("-s", "--sesion", default=None, metavar="NOMBRE",
                    help="sesion a abrir o crear. Sin esto se retoma la ultima "
                         "que usaste; el historial ya no se pierde al salir")
    ap.add_argument("--sesiones", action="store_true",
                    help="lista las sesiones guardadas y sale")
    ap.add_argument("-d", "--db", default=None, metavar="RUTA",
                    help="archivo de sesion en una ruta concreta, en vez de una "
                         "sesion con nombre. Gana sobre -s. Usa ':memory:' para "
                         "una sesion que se pierda al salir")
    ap.add_argument("--conservar-encoding", action="store_true",
                    help="no recortar el Accept-Encoding del cliente. Por "
                         "defecto se le quita lo que luzxfer no sabe deshacer "
                         "(brotli y zstd), porque si no el detector se queda "
                         "ciego buscando reflejos en bytes comprimidos")
    ap.add_argument("--conservar-cache", action="store_true",
                    help="no quitar If-None-Match ni If-Modified-Since. Por "
                         "defecto se quitan, porque con ellos el servidor "
                         "contesta 304 sin cuerpo y no hay nada que analizar. "
                         "Conservalos para probar envenenamiento de cache")
    ap.add_argument("--no-engine", action="store_true",
                    help="no arrancar el proxy: solo revisar una sesion guardada")
    ap.add_argument("--version", action="store_true")
    a = ap.parse_args(argv)

    if a.version:
        from . import __version__
        print(f"luzxfer {__version__}")
        return 0

    if a.sesiones:
        return _listar_sesiones()

    from .core import sesiones

    # -d es una ruta explicita y gana sobre -s: quien la pide sabe donde
    # quiere el archivo, y puede estar fuera del directorio de sesiones.
    if a.db:
        if a.db == ":memory:":
            ruta, nombre = ":memory:", "efimera"
        else:
            ruta = str(Path(a.db).expanduser())
            nombre = Path(ruta).stem
    else:
        try:
            nombre, p = sesiones.abrir(a.sesion)
            ruta = str(p)
        except sesiones.NombreInvalido as e:
            print(f"luzxfer: {e}", file=sys.stderr)
            return 2
        except OSError as e:
            print(f"luzxfer: no se pudo preparar {sesiones.dir_sesiones()}\n"
                  f"  {e}\n"
                  f"  Usa -d RUTA para poner la sesion en otro sitio.",
                  file=sys.stderr)
            return 2

    if a.host not in ("127.0.0.1", "localhost", "::1"):
        print(f"aviso: escuchando en {a.host}, fuera de loopback.\n"
              "  Esta herramienta reenvia peticiones arbitrarias: exponerla en una\n"
              "  red es regalar un proxy abierto. Usa un tunel SSH si necesitas\n"
              "  llegar desde otro equipo.\n", file=sys.stderr)

    from .tui.app import LuzxferApp

    app = LuzxferApp(
        db=ruta, sesion=nombre,
        host=a.host, port=a.port, upstream=a.upstream,
        arrancar_motor=not a.no_engine,
        filtrar_encoding=not a.conservar_encoding,
        filtrar_cache=not a.conservar_cache,
    )
    app.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
