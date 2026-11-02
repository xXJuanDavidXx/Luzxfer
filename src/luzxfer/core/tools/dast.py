"""DAST con correa: probar activamente, sin soltar la herramienta.

Esto es lo ÚNICO de luzxfer que origina peticiones por su cuenta contra
un objetivo. Todo lo demás observa, o manda lo que el analista escribió.
Por eso lleva correa, y la correa son cuatro reglas:

  1. **Exige alcance.** Sin un alcance configurado no corre, y no corre
     contra nada que el alcance no autorice. Mirar de más es ruido;
     disparar de más puede ser el contrato.
  2. **Se dispara a mano**, sobre una petición que el analista eligió.
     No rastrea, no descubre, no se lanza solo.
  3. **Ritmo prudente de fábrica.** Un DAST que de serie tumba el
     entorno de un cliente es una llamada telefónica, no un hallazgo.
  4. **No confirma nada.** Lo que encuentra son candidatos con sus IDs
     de la WSTG, igual que los del detector pasivo. La raya entre
     candidato y hallazgo la cruza una persona, con `v`.

Lo que aporta frente al detector pasivo: el pasivo ve que un valor
vuelve; el activo manda un marcador propio y mira si vuelve ENTERO. Un
reflejo escapado no es explotable, y decir que sí lo es sería el falso
positivo que hace inútil la salida de un escáner.
"""
from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

from ..models import Finding
from . import repeater
from .alcance import Alcance
from .dast_estrategias import (
    Contexto,
    EstrategiaPayloads,
    Hallazgo,
    Prueba,
)
from .dast_puntos import Punto, _partes, con_payload, puntos
from .ritmo import Acelerador

# Un marcador que no sale por casualidad en una respuesta y que no lleva
# nada peligroso: solo sirve para saber si vuelve entero o escapado.
MARCA = "lzx9q7z"


# Lo que este modulo reexporta a proposito: un plugin importa `Prueba` y
# `Punto` desde aqui desde la primera version, y mudarlos de archivo no
# puede romper los plugins que ya existen.
__all__ = [
    "Contexto", "ESTRATEGIAS", "Escaneo", "EstrategiaPayloads",
    "FueraDeAlcance", "Hallazgo", "PRUEBAS", "Prueba", "Punto",
    "SinPuntos", "con_payload", "puntos",
]


class FueraDeAlcance(RuntimeError):
    """El objetivo no está autorizado por el alcance."""


class SinPuntos(ValueError):
    """La petición no tiene parámetros donde inyectar."""


# --------------------------------------------------------------- pruebas
_ERRORES_SQL = (
    "you have an error in your sql syntax",
    "warning: mysql", "unclosed quotation mark",
    "ora-01756", "ora-00933", "quoted string not properly terminated",
    "unterminated quoted string", "psql: error", "pg_query",
    "sqlite_error", "sqlite3::", "unrecognized token",
    "sqlstate[", "odbc microsoft access driver",
)

_HOST_SONDA = "luzxfer-prueba.invalid"


def _eval_reflejo(cuerpo: str, estado: int, cab: dict) -> str | None:
    for p in _PAYLOADS_REFLEJO:
        if p in cuerpo:
            return f"el marcador vuelve sin escapar: {p}"
    return None


def _eval_sqli(cuerpo: str, estado: int, cab: dict) -> str | None:
    bajo = cuerpo.lower()
    for e in _ERRORES_SQL:
        if e in bajo:
            return f"el servidor devuelve un error de SQL: {e!r}"
    return None


def _eval_redireccion(cuerpo: str, estado: int, cab: dict) -> str | None:
    destino = cab.get("location", "")
    if _HOST_SONDA in destino:
        return f"redirige a un destino que le dimos nosotros: {destino}"
    return None


def _eval_traversal(cuerpo: str, estado: int, cab: dict) -> str | None:
    if "root:x:0:0" in cuerpo or "[extensions]" in cuerpo.lower():
        return "la respuesta trae contenido de un archivo del sistema"
    return None


_PAYLOADS_REFLEJO = [f"<{MARCA}>", f'"{MARCA}"', f"'{MARCA}'"]

ESTRATEGIAS: dict[str, EstrategiaPayloads] = {
    "reflejo": EstrategiaPayloads(
        nombre="reflejo",
        titulo="entrada reflejada sin escapar",
        payloads=list(_PAYLOADS_REFLEJO),
        wstg=["WSTG-INPV-01", "WSTG-INPV-02"],
        evalua=_eval_reflejo,
        severidad="high", confianza="media",
    ),
    "sqli_error": EstrategiaPayloads(
        nombre="sqli_error",
        titulo="error de SQL al romper la comilla",
        payloads=["'", '"', "')"],
        wstg=["WSTG-INPV-05"],
        evalua=_eval_sqli,
        severidad="high", confianza="alta",
    ),
    "redireccion": EstrategiaPayloads(
        nombre="redireccion",
        titulo="redireccion abierta",
        payloads=[f"https://{_HOST_SONDA}/", f"//{_HOST_SONDA}/"],
        wstg=["WSTG-CLNT-04"],
        evalua=_eval_redireccion,
        severidad="medium", confianza="alta",
    ),
    "traversal": EstrategiaPayloads(
        nombre="traversal",
        titulo="traversal de ruta",
        payloads=["../../../../etc/passwd", "....//....//etc/passwd"],
        wstg=["WSTG-ATHZ-01"],
        evalua=_eval_traversal,
        severidad="high", confianza="alta",
    ),
}


# El nombre de siempre, para lo que ya lo importaba.
PRUEBAS = ESTRATEGIAS


# --------------------------------------------------------------- escaneo
@dataclass(slots=True)
class Escaneo:
    """Un escaneo preparado. No manda nada hasta que se llama a correr().

    Todo lo que puede impedirlo se comprueba en el constructor: el
    alcance y que haya donde inyectar. Descubrir que el objetivo estaba
    fuera del contrato en la petición número cien es tarde.
    """
    crudo: str
    alcance: Alcance
    concurrencia: int = 2
    por_segundo: float = 5.0
    tls: bool | None = None
    timeout: float = 15.0
    # las que anaden los plugins, sumadas a las de serie
    pruebas_extra: list = field(default_factory=list)
    # canal fuera de banda, si hay. None = las estrategias que lo pidan
    # se omiten, y se anotan: una omision silenciosa seria un falso
    # negativo disfrazado de "probado y limpio"
    oob: object | None = None

    puntos: list[Punto] = field(default_factory=list, init=False)
    total: int = field(default=0, init=False)
    enviadas: int = field(default=0, init=False)
    terminado: bool = field(default=False, init=False)
    omitidas: list = field(default_factory=list, init=False)
    _parar: bool = field(default=False, init=False)

    def __post_init__(self) -> None:
        if not self.alcance.configurado:
            raise FueraDeAlcance(
                "no hay alcance configurado. El DAST manda peticiones por su "
                "cuenta y no sale sin un alcance que lo autorice: pon uno "
                "con la tecla a."
            )
        url = _url_de(self.crudo)
        if not self.alcance.dentro(url):
            raise FueraDeAlcance(
                f"{url} esta fuera del alcance. Si de verdad entra en el "
                f"contrato, anadelo con la tecla a."
            )
        self.puntos = puntos(self.crudo)
        if not self.puntos:
            raise SinPuntos(
                "esta peticion no tiene parametros donde inyectar: ni query "
                "ni cuerpo de formulario."
            )
        self.omitidas = [e for e in self.todas_las_pruebas
                         if not self._aplicable(e)]
        # COTA de peticiones, no cuenta exacta: una estrategia para en
        # cuanto encuentra. Es el numero que se le ensena al analista
        # antes de disparar contra un sistema ajeno, asi que tiene que ser
        # un techo de verdad —nunca quedarse corto—, y por eso suma todos
        # los payloads aunque casi nunca se manden todos.
        self.total = len(self.puntos) * sum(
            e.peticiones for e in self.aplicables)

    @property
    def todas_las_pruebas(self) -> list:
        return list(ESTRATEGIAS.values()) + list(self.pruebas_extra)

    @property
    def capacidades(self) -> frozenset:
        """Lo que este escaneo puede hacer. Hoy solo el canal OOB."""
        return frozenset({"oob"}) if self.oob is not None else frozenset()

    def _aplicable(self, estrategia) -> bool:
        return getattr(estrategia, "requiere", frozenset()) <= self.capacidades

    @property
    def aplicables(self) -> list:
        return [e for e in self.todas_las_pruebas if self._aplicable(e)]

    def abortar(self) -> None:
        self._parar = True

    def correr(self, on_resultado: Callable[[Finding], None]) -> list[Finding]:
        """Lanza el escaneo. Bloquea: llamalo desde un hilo.

        `on_resultado` se invoca desde los hilos trabajadores, como en el
        Intruder y en el motor.
        """
        acelerador = Acelerador(self.por_segundo)
        hallazgos: list[Finding] = []
        base = _url_de(self.crudo).split("?")[0]

        # la unidad de trabajo es (punto, estrategia): cuantas peticiones
        # manda cada estrategia lo decide ella, que es justo lo que el
        # modelo viejo no permitia
        tareas = [(p, e) for p in self.puntos for e in self.aplicables]

        def enviar_para(punto):
            def enviar(payload: str):
                acelerador.esperar()
                flujo = repeater.send_raw(
                    con_payload(self.crudo, punto, payload),
                    tls=self.tls, timeout=self.timeout)
                self.enviadas += 1
                return flujo
            return enviar

        def trabajo(tarea):
            punto, estrategia = tarea
            if self._parar:
                return None
            ctx = Contexto(self.crudo, punto, enviar_para(punto), oob=self.oob)
            try:
                hallazgo = estrategia.probar(ctx)
            except Exception:
                # una estrategia rota —sobre todo de un plugin— no puede
                # llevarse por delante el resto del barrido
                return None
            if hallazgo is None or self._parar:
                return None
            return Finding(
                kind="DAST",
                detail=f"{estrategia.titulo} en '{punto.nombre}': "
                       f"{hallazgo.motivo}",
                url=base,
                wstg=list(estrategia.wstg),
                severity=getattr(estrategia, "severidad", ""),
                extra={"param": punto.nombre, "donde": punto.donde,
                       "prueba": estrategia.nombre,
                       "payload": hallazgo.payload,
                       "confianza": hallazgo.confianza},
            )

        try:
            with ThreadPoolExecutor(max_workers=max(1, self.concurrencia),
                                    thread_name_prefix="luzxfer-dast") as ex:
                for h in ex.map(trabajo, tareas):
                    if h is not None:
                        hallazgos.append(h)
                        on_resultado(h)
        finally:
            self.terminado = True
        return hallazgos


def _url_de(crudo: str) -> str:
    """La URL a la que iria esa peticion cruda."""
    try:
        _m, _c, _q, _v, cabeceras, _b = _partes(crudo)
    except repeater.ErrorPeticion:
        return ""
    destino = repeater.destino_de(cabeceras)
    if destino is None:
        return ""
    host, puerto = destino
    esquema = "https" if puerto == 443 else "http"
    autoridad = host if puerto in (80, 443) else f"{host}:{puerto}"
    ruta = repeater.parse_raw(crudo)[1]
    return f"{esquema}://{autoridad}{ruta}"
