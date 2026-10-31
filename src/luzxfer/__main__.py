"""Punto de entrada: luzxfer [opciones]."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path


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
    ap.add_argument("-d", "--db", default=None, metavar="RUTA",
                    help="archivo de sesion (por defecto en memoria, se pierde al salir)")
    ap.add_argument("--no-engine", action="store_true",
                    help="no arrancar el proxy: solo revisar una sesion guardada")
    ap.add_argument("--version", action="store_true")
    a = ap.parse_args(argv)

    if a.version:
        from . import __version__
        print(f"luzxfer {__version__}")
        return 0

    if a.host not in ("127.0.0.1", "localhost", "::1"):
        print(f"aviso: escuchando en {a.host}, fuera de loopback.\n"
              "  Esta herramienta reenvia peticiones arbitrarias: exponerla en una\n"
              "  red es regalar un proxy abierto. Usa un tunel SSH si necesitas\n"
              "  llegar desde otro equipo.\n", file=sys.stderr)

    from .tui.app import LuzxferApp

    app = LuzxferApp(
        db=str(Path(a.db).expanduser()) if a.db else ":memory:",
        host=a.host, port=a.port, upstream=a.upstream,
        arrancar_motor=not a.no_engine,
    )
    app.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
