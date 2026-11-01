"""Donde vive la configuracion y como se lee.

Un solo sitio que sepa abrir el archivo, para que la paleta y los
atajos no acaben con dos lectores que se van separando.
"""
from __future__ import annotations

import configparser
import os
from pathlib import Path


def ruta_config() -> Path:
    """`~/.config/luzxfer/config.ini`, o bajo XDG_CONFIG_HOME. No la crea."""
    xdg = os.environ.get("XDG_CONFIG_HOME", "")
    base = Path(xdg) if xdg and Path(xdg).is_absolute() else Path.home() / ".config"
    return base / "luzxfer" / "config.ini"


def leer_ini(ruta: Path | None = None) -> tuple[configparser.ConfigParser | None,
                                                list[str]]:
    """El archivo leido, o (None, avisos) si no esta o no se entiende.

    Un archivo corrupto no impide arrancar: es un archivo de texto que
    se edita a mano, y un dedazo no puede dejar sin herramienta a nadie.
    """
    ruta = ruta or ruta_config()
    if not ruta.is_file():
        return None, []
    cfg = configparser.ConfigParser()
    try:
        cfg.read(ruta, encoding="utf-8")
    except (OSError, configparser.Error) as e:
        return None, [f"{ruta}: no se pudo leer — {e}"]
    return cfg, []
