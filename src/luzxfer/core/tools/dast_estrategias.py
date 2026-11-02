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
                 *, oob=None):
        self.crudo = crudo
        self.punto = punto
        self._enviar = enviar_fn
        self.oob = oob
        self._baseline: Flow | None = None
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
        if self._baseline is None:
            self._baseline = self.enviar(self.punto.valor)
        return self._baseline


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
            cab = {k.lower(): v for k, v in r.headers}
            motivo = self.evalua(r.text(limite=400_000), r.status, cab)
            if motivo is not None:
                return Hallazgo(motivo=motivo, confianza=self.confianza,
                                payload=payload)
        return None


# El nombre de siempre, para los plugins que ya existen.
Prueba = EstrategiaPayloads
