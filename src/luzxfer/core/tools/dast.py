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
from urllib.parse import parse_qsl, urlencode

from ..models import Finding
from . import repeater
from .alcance import Alcance
from .ritmo import Acelerador

# Un marcador que no sale por casualidad en una respuesta y que no lleva
# nada peligroso: solo sirve para saber si vuelve entero o escapado.
MARCA = "lzx9q7z"


class FueraDeAlcance(RuntimeError):
    """El objetivo no está autorizado por el alcance."""


class SinPuntos(ValueError):
    """La petición no tiene parámetros donde inyectar."""


@dataclass(slots=True)
class Punto:
    nombre: str
    valor: str
    donde: str          # "query" o "cuerpo"
    indice: int         # cual, si el nombre se repite


@dataclass(slots=True)
class Prueba:
    nombre: str
    titulo: str
    payloads: list[str]
    wstg: list[str]
    # (cuerpo, estado, cabeceras_en_minuscula) -> motivo, o None
    evalua: Callable[[str, int, dict], str | None]


# ------------------------------------------------------- puntos y payload
def _partes(crudo: str):
    metodo, ruta, version, cabeceras, cuerpo = repeater.parse_raw(crudo)
    camino, _, consulta = ruta.partition("?")
    return metodo, camino, consulta, version, cabeceras, cuerpo


def _es_formulario(cabeceras: list[tuple[str, str]]) -> bool:
    for k, v in cabeceras:
        if k.lower() == "content-type":
            return "x-www-form-urlencoded" in v.lower()
    return False


def puntos(crudo: str) -> list[Punto]:
    """Dónde se puede inyectar: query y cuerpo de formulario.

    JSON todavía no: fingir que se sabe, partiéndolo como si fuera un
    formulario, mandaría basura al servidor y daría resultados que no
    significan nada.
    """
    try:
        _m, _c, consulta, _v, cabeceras, cuerpo = _partes(crudo)
    except repeater.ErrorPeticion:
        return []

    salida: list[Punto] = []
    for i, (k, v) in enumerate(parse_qsl(consulta, keep_blank_values=True)):
        salida.append(Punto(nombre=k, valor=v, donde="query", indice=i))
    if cuerpo and _es_formulario(cabeceras):
        texto = cuerpo.decode("utf-8", "replace")
        for i, (k, v) in enumerate(parse_qsl(texto, keep_blank_values=True)):
            salida.append(Punto(nombre=k, valor=v, donde="cuerpo", indice=i))
    return salida


def con_payload(crudo: str, punto: Punto, payload: str) -> str:
    """La misma petición con ese parámetro sustituido.

    Se codifica con urlencode: un payload con espacios o comillas
    partiría la línea de petición, y entonces no llegaría lo que se
    quería probar sino un trozo.
    """
    metodo, camino, consulta, version, cabeceras, cuerpo = _partes(crudo)

    def _cambiado(texto: str) -> str:
        pares = parse_qsl(texto, keep_blank_values=True)
        pares[punto.indice] = (punto.nombre, payload)
        return urlencode(pares)

    if punto.donde == "query":
        consulta = _cambiado(consulta)
    else:
        cuerpo = _cambiado(cuerpo.decode("utf-8", "replace")).encode()
        cabeceras = [(k, v) for k, v in cabeceras
                     if k.lower() != "content-length"]
        cabeceras.append(("Content-Length", str(len(cuerpo))))

    ruta = f"{camino}?{consulta}" if consulta else camino
    lineas = [f"{metodo} {ruta} {version}"]
    lineas += [f"{k}: {v}" for k, v in cabeceras]
    return "\r\n".join(lineas) + "\r\n\r\n" + cuerpo.decode("utf-8", "replace")


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

PRUEBAS: dict[str, Prueba] = {
    "reflejo": Prueba(
        nombre="reflejo",
        titulo="entrada reflejada sin escapar",
        payloads=list(_PAYLOADS_REFLEJO),
        wstg=["WSTG-INPV-01", "WSTG-INPV-02"],
        evalua=_eval_reflejo,
    ),
    "sqli_error": Prueba(
        nombre="sqli_error",
        titulo="error de SQL al romper la comilla",
        payloads=["'", '"', "')"],
        wstg=["WSTG-INPV-05"],
        evalua=_eval_sqli,
    ),
    "redireccion": Prueba(
        nombre="redireccion",
        titulo="redireccion abierta",
        payloads=[f"https://{_HOST_SONDA}/", f"//{_HOST_SONDA}/"],
        wstg=["WSTG-CLNT-04"],
        evalua=_eval_redireccion,
    ),
    "traversal": Prueba(
        nombre="traversal",
        titulo="traversal de ruta",
        payloads=["../../../../etc/passwd", "....//....//etc/passwd"],
        wstg=["WSTG-ATHZ-01"],
        evalua=_eval_traversal,
    ),
}


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

    puntos: list[Punto] = field(default_factory=list, init=False)
    total: int = field(default=0, init=False)
    enviadas: int = field(default=0, init=False)
    terminado: bool = field(default=False, init=False)
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
        self.total = len(self.puntos) * sum(
            len(p.payloads) for p in self.todas_las_pruebas)

    @property
    def todas_las_pruebas(self) -> list:
        return list(PRUEBAS.values()) + list(self.pruebas_extra)

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

        tareas = [(p, prueba, payload)
                  for p in self.puntos
                  for prueba in self.todas_las_pruebas
                  for payload in prueba.payloads]

        def trabajo(tarea):
            punto, prueba, payload = tarea
            if self._parar:
                return None
            acelerador.esperar()
            if self._parar:
                return None

            flujo = repeater.send_raw(con_payload(self.crudo, punto, payload),
                                      tls=self.tls, timeout=self.timeout)
            self.enviadas += 1
            if flujo.response is None:
                return None
            r = flujo.response
            cab = {k.lower(): v for k, v in r.headers}
            motivo = prueba.evalua(r.text(limite=400_000), r.status, cab)
            if motivo is None:
                return None
            return Finding(
                kind="DAST",
                detail=f"{prueba.titulo} en '{punto.nombre}': {motivo}",
                url=base,
                wstg=list(prueba.wstg),
                extra={"param": punto.nombre, "donde": punto.donde,
                       "prueba": prueba.nombre, "payload": payload},
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
