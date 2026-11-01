"""API de plugins: añadir comprobaciones sin tocar el núcleo.

Un plugin es un `.py` en `~/.local/share/luzxfer/plugins/` que define una
función `registrar(api)`:

    NOMBRE = "mi detector"

    def registrar(api):
        api.detector(busca_algo)        # comprobación pasiva
        api.prueba(Prueba(...))         # comprobación activa del DAST

    def busca_algo(flujo):
        return [Finding(...)]           # o [] si no hay nada

**Un plugin es código que corre con tus privilegios dentro de la
herramienta.** No hay caja de arena y no la va a haber: en Python no sale
barata ni honesta. Instala solo los que hayas leído, igual que harías con
cualquier cosa que metes en tu `~/.bashrc`. `--sin-plugins` los desactiva.

Lo que sí hace este módulo es contener los accidentes, que es distinto de
contener a un atacante:

  - un plugin que revienta al cargar no impide que carguen los demás;
  - un detector que revienta no deja al analista sin los otros detectores;
  - lo que un plugin devuelve se valida: solo pasan `Finding` de verdad;
  - **un ID de la WSTG que no existe se descarta.** La matriz alimenta un
    informe que va a un cliente, y el cliente va a buscar ese ID.
"""
from __future__ import annotations

import importlib.util
import traceback
from dataclasses import dataclass, field
from pathlib import Path

from .models import Finding
from .tools import wstg


@dataclass(slots=True)
class Cargado:
    nombre: str
    ruta: Path
    detectores: int = 0
    pruebas: int = 0


class _Api:
    """Lo que un plugin recibe en `registrar(api)`."""

    def __init__(self, registro: Registro, origen: str):
        self._reg = registro
        self._origen = origen

    def detector(self, fn) -> None:
        """Registra una comprobación pasiva: fn(flujo) -> list[Finding]."""
        if not callable(fn):
            raise TypeError("api.detector() necesita una funcion")
        self._reg._detectores.append((self._origen, fn))

    def prueba(self, prueba) -> None:
        """Registra una comprobación activa para el barrido DAST."""
        malos = [w for w in getattr(prueba, "wstg", []) if not wstg.existe(w)]
        if malos:
            raise ValueError(
                f"la prueba '{getattr(prueba, 'nombre', '?')}' usa IDs que no "
                f"existen en la WSTG v4.2: {', '.join(malos)}"
            )
        self._reg.pruebas.append(prueba)


@dataclass(slots=True)
class Registro:
    cargados: list[Cargado] = field(default_factory=list)
    pruebas: list = field(default_factory=list)
    fallos: list[str] = field(default_factory=list)
    _detectores: list = field(default_factory=list)

    def analizar(self, flujo) -> list[Finding]:
        """Lo que ven los detectores de los plugins sobre un flujo.

        Un plugin de un tercero no puede dejar al analista sin detector,
        así que cada uno se llama por separado y lo que falle se anota.
        """
        salida: list[Finding] = []
        for origen, fn in self._detectores:
            try:
                resultado = fn(flujo)
            except Exception as e:
                self._anotar(f"{origen}: {type(e).__name__}: {e}")
                continue
            if not isinstance(resultado, (list, tuple)):
                self._anotar(f"{origen}: devolvio {type(resultado).__name__}, "
                             f"se esperaba una lista de Finding")
                continue
            for h in resultado:
                if not isinstance(h, Finding):
                    continue
                # los IDs inventados se caen aqui y no en el informe del
                # cliente; el hallazgo se queda, que perderlo seria peor
                h.wstg = [w for w in h.wstg if wstg.existe(w)]
                salida.append(h)
        return salida

    def _anotar(self, texto: str) -> None:
        if texto not in self.fallos:
            self.fallos.append(texto)


def cargar(carpeta: str | Path) -> tuple[Registro, list[str]]:
    """Carga los plugins de esa carpeta. Devuelve (registro, errores).

    Los errores se devuelven en vez de lanzarse: un plugin roto es un
    problema del plugin, no de la herramienta, y hay que poder
    enseñárselo al usuario sin dejar de arrancar.
    """
    reg = Registro()
    errores: list[str] = []
    base = Path(carpeta)
    if not base.is_dir():
        return reg, errores

    for ruta in sorted(base.glob("*.py")):
        # guion bajo delante = no es un plugin, es un modulo de apoyo
        if ruta.name.startswith("_"):
            continue
        try:
            modulo = _importar(ruta)
        except Exception as e:
            errores.append(f"{ruta.name}: no se pudo cargar — "
                           f"{type(e).__name__}: {e}")
            continue

        registrar = getattr(modulo, "registrar", None)
        if not callable(registrar):
            errores.append(f"{ruta.name}: no define registrar(api), "
                           f"asi que no hay nada que registrar")
            continue

        nombre = str(getattr(modulo, "NOMBRE", "") or ruta.stem)
        antes_d, antes_p = len(reg._detectores), len(reg.pruebas)
        try:
            registrar(_Api(reg, nombre))
        except Exception as e:
            errores.append(f"{ruta.name}: fallo al registrar — "
                           f"{type(e).__name__}: {e}")
            # se deshace lo que hubiera metido antes de fallar, para no
            # dejar medio plugin activo
            del reg._detectores[antes_d:]
            del reg.pruebas[antes_p:]
            continue

        reg.cargados.append(Cargado(
            nombre=nombre, ruta=ruta,
            detectores=len(reg._detectores) - antes_d,
            pruebas=len(reg.pruebas) - antes_p,
        ))
    return reg, errores


def _importar(ruta: Path):
    spec = importlib.util.spec_from_file_location(f"luzxfer_plugin_{ruta.stem}",
                                                  ruta)
    if spec is None or spec.loader is None:
        raise ImportError(f"no se pudo preparar {ruta}")
    modulo = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(modulo)
    except Exception:
        # la traza completa importa: quien escribe el plugin la necesita
        raise ImportError(traceback.format_exc(limit=3).strip()) from None
    return modulo
