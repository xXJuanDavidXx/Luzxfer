"""Alcance: qué está dentro del contrato y qué no.

**El alcance filtra la vista y lo que la herramienta origina, nunca la
captura.** Descartar tráfico al capturarlo lo pierde para siempre, y en un
pentest el tráfico que tiraste es justo el que no puedes recuperar. Así
que el proxy sigue guardándolo todo y esto decide qué se enseña, qué
analiza el detector y, el día que exista, contra qué puede disparar el
DAST.

Se equivoca de dos formas y las dos son caras: dejar fuera algo que sí
estaba dentro es trabajo perdido, y dejar dentro algo ajeno es, en un
contrato, un problema legal y no un bug. De ahí las dos reglas:

  - **Excluir siempre gana.** Lo prohibido lo está aunque también encaje
    en algo permitido.
  - **Sin reglas, todo está dentro.** Una sesión recién abierta no puede
    esconder el tráfico; el alcance se estrecha a propósito, nunca por
    descuido.

Formato de una regla, pensado para teclearse:

    +objetivo.com            incluir ese host, cualquier puerto
    +*.objetivo.com          y sus subdominios, raíz incluida
    +objetivo.com:8080       solo ese puerto
    +objetivo.com/api/       solo bajo ese prefijo de ruta
    -admin.objetivo.com      excluir, gane quien gane
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from urllib.parse import urlsplit

# Un host de regla: '*', o un nombre de dominio con '*.' delante opcional.
# Sin esto, '+++' se colaba como un host llamado '++' y la regla parecia
# valida: una regla de alcance que no significa nada es peor que un error,
# porque deja creer que el alcance esta puesto.
_ETIQUETA = r"[a-z0-9_]([a-z0-9_\-]*[a-z0-9_])?"
_HOST_VALIDO = re.compile(rf"^(\*|(\*\.)?{_ETIQUETA}(\.{_ETIQUETA})*)$")


class ReglaInvalida(ValueError):
    """La línea no se puede leer como regla de alcance."""


@dataclass(slots=True)
class Regla:
    incluir: bool
    host: str                      # en minúsculas; puede empezar por "*."
    puerto: int | None = None      # None = cualquiera
    prefijo: str = ""              # prefijo de ruta; "" = cualquiera

    @classmethod
    def desde_texto(cls, texto: str) -> Regla:
        crudo = texto.strip()
        if not crudo:
            raise ReglaInvalida("regla vacia")

        incluir = True
        if crudo[0] in "+-":
            incluir = crudo[0] == "+"
            crudo = crudo[1:].strip()
        if not crudo:
            raise ReglaInvalida(f"regla sin objetivo: {texto!r}")

        autoridad, barra, resto = crudo.partition("/")
        prefijo = f"/{resto}" if barra else ""
        if not autoridad:
            raise ReglaInvalida(
                f"una regla necesita un host, no solo una ruta: {texto!r}")

        host, dos, puerto_txt = autoridad.rpartition(":")
        if dos:
            try:
                puerto = int(puerto_txt)
            except ValueError as e:
                raise ReglaInvalida(f"puerto invalido en {texto!r}") from e
        else:
            host, puerto = autoridad, None

        host = host.lower()
        if not _HOST_VALIDO.match(host):
            raise ReglaInvalida(
                f"host invalido en {texto!r}: se permiten letras, digitos, "
                f"punto, guion y guion bajo, con '*' o '*.' delante. "
                f"Las direcciones IPv6 entre corchetes no valen todavia."
            )
        return cls(incluir=incluir, host=host, puerto=puerto, prefijo=prefijo)

    def __str__(self) -> str:
        puerto = f":{self.puerto}" if self.puerto is not None else ""
        return f"{'+' if self.incluir else '-'}{self.host}{puerto}{self.prefijo}"

    def casa(self, host: str, puerto: int | None, ruta: str) -> bool:
        if self.puerto is not None and self.puerto != puerto:
            return False
        if not self._casa_host(host):
            return False
        # la ruta SI distingue mayusculas: en un servidor real /API y /api
        # pueden ser cosas distintas, y suponer que no lo son es como se
        # deja fuera media aplicacion
        return ruta.startswith(self.prefijo) if self.prefijo else True

    def _casa_host(self, host: str) -> bool:
        if self.host == "*":
            return True
        if self.host.startswith("*."):
            raiz = self.host[2:]
            # el comodin incluye el dominio raiz: quien escribe
            # *.objetivo.com casi nunca quiere dejar fuera objetivo.com
            return host == raiz or host.endswith("." + raiz)
        return host == self.host


@dataclass(slots=True)
class Alcance:
    reglas: list[Regla] = field(default_factory=list)

    @property
    def configurado(self) -> bool:
        return bool(self.reglas)

    def dentro(self, url: str) -> bool:
        """Si esa URL está dentro del alcance.

        Una URL que no se puede interpretar queda FUERA. Es la decisión
        prudente: ante la duda, no tocar.
        """
        try:
            p = urlsplit(url)
            host = (p.hostname or "").lower()
            puerto = p.port or (443 if p.scheme == "https" else 80)
        except ValueError:
            return False
        if not host:
            return False
        ruta = p.path or "/"

        incluyentes = [r for r in self.reglas if r.incluir]
        for r in self.reglas:
            if not r.incluir and r.casa(host, puerto, ruta):
                return False          # excluir gana, mire lo que mire el resto
        if not incluyentes:
            return True               # solo hay exclusiones: pasa el resto
        return any(r.casa(host, puerto, ruta) for r in incluyentes)

    # ------------------------------------------------------------------
    def texto(self) -> str:
        return "\n".join(str(r) for r in self.reglas)

    @classmethod
    def desde_texto(cls, texto: str) -> Alcance:
        alcance, errores = cls.desde_texto_tolerante(texto)
        if errores:
            raise ReglaInvalida("; ".join(errores))
        return alcance

    @classmethod
    def desde_texto_tolerante(cls, texto: str) -> tuple[Alcance, list[str]]:
        """Lo mismo, pero una línea mala no se lleva por delante el resto.

        El alcance se teclea a mano, y un dedazo no puede dejar sin
        alcance a toda la sesión. Las líneas malas se devuelven aparte
        para poder enseñarlas.
        """
        reglas: list[Regla] = []
        errores: list[str] = []
        for linea in texto.splitlines():
            limpia = linea.strip()
            if not limpia or limpia.startswith("#"):
                continue
            try:
                reglas.append(Regla.desde_texto(limpia))
            except ReglaInvalida as e:
                errores.append(str(e))
        return cls(reglas), errores
