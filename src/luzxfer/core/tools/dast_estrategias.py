"""Como se confirma una vulnerabilidad: el framework de estrategias.

El modelo anterior era un par `(payloads, evalua(cuerpo, estado, cab))`:
manda un payload, mira la respuesta, decide. Eso alcanza para lo que se
ve en la propia respuesta —un reflejo, un error de SQL— y no alcanza para
nada mas.

Las clases que faltan necesitan **mandar mas de una peticion y
comparar**: un booleano ciego compara `1=1` contra `1=2`, un time-based
compara contra una linea base de tiempos, un OOB pregunta a un canal
aparte si llego algo. Por eso una estrategia recibe un `Contexto` con el
que manda lo que necesite, en vez de recibir una respuesta ya hecha.

Lo que NO cambia: una estrategia devuelve un candidato, nunca un hallazgo
confirmado. Confirmar es de un humano.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from ..models import Flow

# Cuanto se fia la estrategia de lo que vio. No es severidad: una clase
# critica detectada por un indicio debil sigue siendo un indicio debil, y
# mezclarlas es como un informe acaba diciendo que algo es seguro.
CONFIANZAS = ("baja", "media", "alta")


@dataclass(slots=True)
class Hallazgo:
    """Lo que devuelve una estrategia cuando ve algo. Candidato, no hallazgo."""
    motivo: str
    confianza: str = "media"
    payload: str = ""
    oob_id: str | None = None


class Contexto:
    """Lo que una estrategia usa para probar un punto.

    Manda a traves de `enviar`, que es quien respeta el ritmo y lleva la
    cuenta: una estrategia nunca abre un socket por su cuenta, porque
    entonces la correa dejaria de valer para ella.
    """

    def __init__(self, crudo: str, punto, enviar_fn: Callable[[str], Flow],
                 *, oob=None, cache_baseline: dict | None = None):
        self.crudo = crudo
        self.punto = punto
        self._enviar = enviar_fn
        self.oob = oob
        # compartido entre todas las estrategias del MISMO punto: varias lo
        # necesitan y pedirlo una vez por estrategia multiplicaria el
        # trafico mandando la misma peticion una y otra vez
        self._cache = cache_baseline if cache_baseline is not None else {}
        self.flujos: list[Flow] = []

    def enviar(self, payload: str) -> Flow:
        flujo = self._enviar(payload)
        self.flujos.append(flujo)
        return flujo

    def baseline(self) -> Flow:
        """La peticion con su valor original, cacheada.

        Se cachea porque casi toda comparacion la necesita y pedirla una
        vez por estrategia multiplicaria el trafico sin anadir nada.
        """
        if "base" not in self._cache:
            self._cache["base"] = self.enviar(self.punto.valor)
        return self._cache["base"]


@dataclass(slots=True)
class EstrategiaPayloads:
    """La estrategia clasica: manda payloads y mira cada respuesta.

    Subsume el `Prueba` de siempre, asi que los plugins que registran uno
    siguen funcionando sin cambiar nada.
    """
    nombre: str
    titulo: str
    payloads: list[str]
    wstg: list[str]
    # (cuerpo, estado, cabeceras_en_minuscula) -> motivo, o None
    evalua: Callable[[str, int, dict], str | None]
    severidad: str = "medium"
    confianza: str = "media"
    requiere: frozenset = field(default_factory=frozenset)
    # Si el payload convierte un recurso que funcionaba en un error, lo que
    # vuelve no es la aplicacion reflejando entrada: es la pagina de error
    # del SERVIDOR repitiendo la URL. Medido contra DVWA: fuzzear segmentos
    # de ruta da 404 de Apache que repiten lo pedido, y como fuzzear rutas
    # genera 404s por naturaleza, sin esto cada barrido saldria contaminado.
    ignorar_error_nuevo: bool = False

    @property
    def peticiones(self) -> int:
        """Cota de peticiones por punto.

        Importa que sea una cota de PETICIONES y no de sondas: es el
        numero que se le ensena al analista antes de disparar contra el
        sistema de otro, y un numero que significara otra cosa seria un
        aviso que miente.
        """
        return len(self.payloads)

    def probar(self, ctx: Contexto) -> Hallazgo | None:
        for payload in self.payloads:
            flujo = ctx.enviar(payload)
            r = flujo.response
            if r is None:
                continue
            if self.ignorar_error_nuevo and r.status >= 400:
                base = ctx.baseline().response
                if base is not None and base.status < 400:
                    continue
            cab = {k.lower(): v for k, v in r.headers}
            motivo = self.evalua(r.text(limite=400_000), r.status, cab)
            if motivo is not None:
                return Hallazgo(motivo=motivo, confianza=self.confianza,
                                payload=payload)
        return None


# El nombre de siempre, para los plugins que ya existen.
Prueba = EstrategiaPayloads


# --------------------------------------------------- booleano ciego
# Pares (condicion verdadera, condicion falsa). Se generan a partir del
# valor original porque hay dos formas de inyectar y las dos son comunes:
# sustituir el valor entero (tipico en un login) y anadir al que habia
# (tipico en una busqueda o un filtro).
def pares_booleanos(valor: str) -> list[tuple[str, str]]:
    return [
        ("' OR 1=1-- ", "' OR 1=2-- "),
        (f"{valor}' OR '1'='1", f"{valor}' OR '1'='2"),
        (f"{valor} OR 1=1", f"{valor} OR 1=2"),
    ]


def firma(flujo: Flow) -> tuple[int, int]:
    """Lo que se compara de una respuesta: estado y tamano.

    No se compara el cuerpo entero a proposito: casi cualquier pagina
    real trae algo que cambia solo —una hora, un token, un id— y comparar
    texto daria distinto siempre. Estado y tamano son groseros, y por eso
    mismo estables.
    """
    r = flujo.response
    return (0, -1) if r is None else (r.status, len(r.body))


def _parecidas(a: tuple[int, int], b: tuple[int, int], tolerancia: int) -> bool:
    return a[0] == b[0] and abs(a[1] - b[1]) <= tolerancia


@dataclass(slots=True)
class EstrategiaBooleana:
    """SQLi ciega por diferencia: compara condicion verdadera contra falsa.

    Es la familia que caza lo que no deja rastro en la respuesta. El caso
    que la justifica esta medido: el login de OWASP Juice Shop ES
    inyectable y ninguna de las familias que miran la respuesta podia
    verlo, porque no hay reflejo ni cadena de error SQL. Lo unico que lo
    delata es que con la condicion verdadera la respuesta CAMBIA.

    El riesgo de esta familia es el falso positivo, y viene de las
    paginas que cambian solas (un token, una hora, un contador). Por eso
    el protocolo es:

      1. tomar el baseline DOS veces y medir cuanto varia por su cuenta;
      2. si varia, no concluir nada —una pagina asi no se puede medir por
         diferencia, y forzarlo seria inventar;
      3. exigir que la condicion FALSA se parezca al baseline (si ya
         cambia, lo que altero la respuesta fue inyectar algo raro, no la
         condicion);
      4. exigir que la VERDADERA no se parezca a la falsa.

    Los cuatro pasos juntos son lo que separa «esto es inyectable» de
    «esta pagina es inquieta».
    """
    nombre: str = "sqli_boolean"
    titulo: str = "SQLi ciega por diferencia booleana"
    wstg: list = field(default_factory=lambda: ["WSTG-INPV-05"])
    severidad: str = "high"
    requiere: frozenset = field(default_factory=frozenset)
    # margen minimo de tolerancia, para no llamar «cambio» a un byte
    piso_tolerancia: int = 16

    @property
    def peticiones(self) -> int:
        # 2 baselines + un par (verdadera, falsa) por cada forma de inyectar
        return 2 + 2 * len(pares_booleanos(""))

    def probar(self, ctx: Contexto) -> Hallazgo | None:
        base1 = firma(ctx.baseline())
        base2 = firma(ctx.enviar(ctx.punto.valor))
        if base1[0] != base2[0]:
            return None                 # ni el estado es estable
        ruido = abs(base1[1] - base2[1])
        tolerancia = max(self.piso_tolerancia, ruido * 3)
        if ruido > max(self.piso_tolerancia, base1[1] // 4):
            return None                 # la pagina cambia sola demasiado

        for verdadera, falsa in pares_booleanos(ctx.punto.valor):
            f_falsa = firma(ctx.enviar(falsa))
            if not _parecidas(f_falsa, base1, tolerancia):
                continue                # inyectar ya la altero: no concluye
            f_verdadera = firma(ctx.enviar(verdadera))
            if not _parecidas(f_verdadera, f_falsa, tolerancia):
                return Hallazgo(
                    motivo=(f"la condicion verdadera cambia la respuesta "
                            f"(falsa {f_falsa[0]}/{f_falsa[1]}B, "
                            f"verdadera {f_verdadera[0]}/{f_verdadera[1]}B) "
                            f"y la falsa se parece a la original"),
                    confianza="alta", payload=verdadera)
        return None
