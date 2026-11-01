"""Paleta con nombres, y de donde salen los colores.

Antes habia 166 colores a pelo repartidos por nueve archivos, y solo
doce distintos: cambiar uno era un grep por medio proyecto. Esto existe
primero por eso y solo despues por la personalizacion.

Los nombres son SEMANTICOS y no de color. `PELIGRO` sigue significando
peligro aunque en un tema claro no sea el mismo rojo; `ROJO` dejaria de
significar nada el dia que alguien ponga un tema donde el peligro sea
naranja. Esa es la diferencia entre una paleta y una lista de colores.

Se puede cambiar desde `~/.config/luzxfer/config.ini`:

    [tema]
    nombre = claro            # oscuro | claro | contraste

    [colores]                 # cualquiera, suelto, por encima del tema
    peligro = #ff0000
"""
from __future__ import annotations

import configparser
import os
import re
from dataclasses import dataclass, fields
from pathlib import Path

_HEX = re.compile(r"^#[0-9a-fA-F]{6}$")


@dataclass(frozen=True, slots=True)
class Paleta:
    # texto, de mas a menos presente
    texto: str          # lo que se lee primero
    cuerpo: str         # cuerpos de peticion y respuesta
    atenuado: str       # datos de apoyo
    secundario: str     # metadatos
    tenue: str          # pistas, atajos, lo que no estorba
    separador: str      # las rayas entre cosas

    # significado
    acento: str         # titulos, lo marcado, lo que pide atencion
    bien: str           # 2xx, pasa, confirmado
    info: str           # 3xx, notas, lo neutro
    peligro: str        # errores, 5xx, FALLA, lo que puede doler
    especial: str       # plugins y lo que viene de fuera
    claro: str          # acentos frios, metodos poco comunes
    acento_suave: str   # el acento cuando no debe gritar

    # superficies, de atras hacia delante. Van en la paleta porque sin
    # ellas un tema claro dejaria el texto oscuro sobre fondo negro, que
    # es peor que no tener temas.
    fondo: str          # el lienzo
    panel: str          # paneles y tablas
    modal: str          # las cajas que se abren encima
    elevado: str        # lo que destaca sobre un panel
    superficie: str     # cabeceras de tabla, barras
    borde: str          # rayas y marcos


OSCURO = Paleta(
    texto="#d9dde5", cuerpo="#c7cdd9", atenuado="#a8b0c0",
    secundario="#7b8496", tenue="#5c6578", separador="#39404f",
    acento="#f0a93b", bien="#6fcf8f", info="#5fa8d3",
    peligro="#e05c5c", especial="#c99bf0", claro="#9bd4f0",
    acento_suave="#ffc062",
    fondo="#0b0c10", panel="#14161c", modal="#0e1016",
    elevado="#1b1e26", superficie="#2a2f3d", borde="#262a35",
)

# Para terminales de fondo claro. No es el oscuro invertido: sobre
# blanco hacen falta tonos mas oscuros y saturados para el mismo
# contraste, y los grises claros desaparecen.
CLARO = Paleta(
    texto="#1c2026", cuerpo="#2b313a", atenuado="#4a5260",
    secundario="#626b7a", tenue="#8a93a1", separador="#c8cdd6",
    acento="#9a5b00", bien="#1b7f3d", info="#15548c",
    peligro="#b01818", especial="#6b2fa0", claro="#0f6b93",
    acento_suave="#7a4700",
    fondo="#fbfbfc", panel="#f2f3f5", modal="#ffffff",
    elevado="#e8eaee", superficie="#dfe2e7", borde="#c8cdd6",
)

# Alto contraste, para quien lo necesita de verdad. Los grises
# intermedios se colapsan: tener seis niveles de gris no sirve de nada
# si no se distinguen entre si.
CONTRASTE = Paleta(
    texto="#ffffff", cuerpo="#ffffff", atenuado="#e0e0e0",
    secundario="#c0c0c0", tenue="#a0a0a0", separador="#808080",
    acento="#ffd000", bien="#00e060", info="#40c0ff",
    peligro="#ff4040", especial="#e080ff", claro="#80e0ff",
    acento_suave="#ffe680",
    fondo="#000000", panel="#000000", modal="#000000",
    elevado="#101010", superficie="#1a1a1a", borde="#808080",
)

TEMAS = {"oscuro": OSCURO, "claro": CLARO, "contraste": CONTRASTE}

# La que usa el programa. `cargar()` la reemplaza al arrancar.
ACTUAL = OSCURO


class _Actual:
    """Acceso a la paleta vigente en el momento de leerla.

    Hace falta porque `from .paleta import ACTUAL` congelaria la paleta
    del arranque: el modulo se importa antes de leer la configuracion, y
    quien hubiera capturado la referencia se quedaria con el tema por
    defecto para siempre. Con esto `P.peligro` siempre pregunta.
    """

    def __getattr__(self, nombre: str) -> str:
        return getattr(ACTUAL, nombre)


P = _Actual()


def ruta_config() -> Path:
    """Donde vive la configuracion. No la crea."""
    xdg = os.environ.get("XDG_CONFIG_HOME", "")
    base = Path(xdg) if xdg and Path(xdg).is_absolute() else Path.home() / ".config"
    return base / "luzxfer" / "config.ini"


def leer(ruta: Path | None = None) -> tuple[Paleta, list[str]]:
    """La paleta configurada y los problemas encontrados.

    Los problemas se devuelven en vez de lanzarse: un color mal escrito
    es un dedazo en un archivo de texto, no una razon para no arrancar
    una herramienta de trabajo.
    """
    ruta = ruta or ruta_config()
    avisos: list[str] = []
    if not ruta.is_file():
        return OSCURO, avisos

    cfg = configparser.ConfigParser()
    try:
        cfg.read(ruta, encoding="utf-8")
    except (OSError, configparser.Error) as e:
        return OSCURO, [f"{ruta}: no se pudo leer — {e}"]

    nombre = cfg.get("tema", "nombre", fallback="oscuro").strip().lower()
    base = TEMAS.get(nombre)
    if base is None:
        avisos.append(f"tema '{nombre}' desconocido; se usa oscuro. "
                      f"Hay: {', '.join(sorted(TEMAS))}")
        base = OSCURO

    cambios: dict[str, str] = {}
    validos = {f.name for f in fields(Paleta)}
    for clave, valor in cfg.items("colores") if cfg.has_section("colores") else []:
        clave = clave.strip().lower()
        valor = valor.strip()
        if clave not in validos:
            avisos.append(f"color '{clave}' no existe; hay: "
                          f"{', '.join(sorted(validos))}")
            continue
        if not _HEX.match(valor):
            avisos.append(f"color '{clave}': '{valor}' no es un #rrggbb")
            continue
        cambios[clave] = valor

    return (base if not cambios else
            Paleta(**{**{f.name: getattr(base, f.name) for f in fields(Paleta)},
                      **cambios})), avisos


def cargar(ruta: Path | None = None) -> list[str]:
    """Pone la paleta configurada como la del programa."""
    global ACTUAL
    ACTUAL, avisos = leer(ruta)
    return avisos
