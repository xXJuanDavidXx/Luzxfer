"""Tests del framework de estrategias del DAST.

El modelo viejo era `(payloads, evalua(respuesta))`: una peticion, una
respuesta, una decision. Eso alcanza para lo que se ve en la propia
respuesta y no alcanza para nada mas. Una estrategia recibe un `Contexto`
y manda lo que necesite, que es lo que permite comparar.

Lo que se prueba aqui es el framework, no las familias: que el contexto
cuente y cachee, que una estrategia que pide un canal que no hay se
**omita y se anote** —nunca se cuente como «probada y limpia»— y que una
estrategia rota no se lleve por delante el barrido.
"""
from __future__ import annotations

import pytest

from luzxfer.core.models import Flow, Request, Response
from luzxfer.core.tools import alcance as alc
from luzxfer.core.tools import dast
from luzxfer.core.tools.dast_estrategias import (
    Contexto,
    EstrategiaPayloads,
    Hallazgo,
)

CRUDO = "GET /x?q=hola HTTP/1.1\r\nHost: objetivo.com\r\n\r\n"


def _dentro():
    return alc.Alcance.desde_texto("+objetivo.com")


def _flujo(cuerpo: bytes = b"ok", estado: int = 200, cab=None) -> Flow:
    return Flow(request=Request(method="GET", url="http://objetivo.com/x",
                                headers=[("Host", "objetivo.com")]),
                response=Response(status=estado, body=cuerpo,
                                  headers=cab or [("Content-Type",
                                                   "text/html")]))


def _ctx(respuesta: bytes = b"ok", *, oob=None, registro=None):
    punto = dast.puntos(CRUDO)[0]

    def enviar(payload):
        if registro is not None:
            registro.append(payload)
        return _flujo(respuesta)

    return Contexto(CRUDO, punto, enviar, oob=oob)


# ------------------------------------------------------------- Contexto
def test_el_contexto_cuenta_lo_que_manda():
    enviados = []
    ctx = _ctx(registro=enviados)
    ctx.enviar("A")
    ctx.enviar("B")
    assert enviados == ["A", "B"]
    assert len(ctx.flujos) == 2


def test_el_baseline_se_cachea():
    """Casi toda comparacion lo necesita; pedirlo una vez por estrategia
    multiplicaria el trafico sin anadir nada."""
    enviados = []
    ctx = _ctx(registro=enviados)
    a = ctx.baseline()
    b = ctx.baseline()
    assert a is b
    assert len(enviados) == 1


def test_el_baseline_manda_el_valor_original_del_punto():
    enviados = []
    ctx = _ctx(registro=enviados)
    ctx.baseline()
    assert enviados == ["hola"]


# -------------------------------------------------- EstrategiaPayloads
def test_para_en_cuanto_encuentra_y_no_agota_los_payloads():
    """Menos trafico contra el sistema del cliente para el mismo hallazgo."""
    enviados = []
    e = EstrategiaPayloads(nombre="x", titulo="t", payloads=["A", "B", "C"],
                           wstg=[], evalua=lambda c, s, h: "lo vi")
    h = e.probar(_ctx(registro=enviados))
    assert isinstance(h, Hallazgo) and h.payload == "A"
    assert enviados == ["A"], "no se mandan B ni C"


def test_sin_senal_devuelve_none_y_manda_todos():
    enviados = []
    e = EstrategiaPayloads(nombre="x", titulo="t", payloads=["A", "B"],
                           wstg=[], evalua=lambda c, s, h: None)
    assert e.probar(_ctx(registro=enviados)) is None
    assert enviados == ["A", "B"]


def test_peticiones_es_una_cota_de_peticiones_no_de_sondas():
    """Es el numero que se le ensena al analista antes de disparar contra
    un sistema ajeno: tiene que ser un techo, no una aproximacion."""
    e = EstrategiaPayloads(nombre="x", titulo="t", payloads=["A", "B", "C"],
                           wstg=[], evalua=lambda c, s, h: None)
    assert e.peticiones == 3


# ------------------------------------------------- gating por `requiere`
def _falsa_oob():
    return EstrategiaPayloads(
        nombre="falsa_oob", titulo="pide oob", payloads=["A"], wstg=[],
        evalua=lambda c, s, h: "no deberia correr",
        requiere=frozenset({"oob"}))


def test_una_estrategia_que_pide_oob_se_omite_sin_canal():
    """Y se ANOTA: omitirla en silencio seria un falso negativo disfrazado
    de «probado y limpio», que es la peor forma de equivocarse."""
    e = dast.Escaneo(CRUDO, _dentro(), pruebas_extra=[_falsa_oob()], oob=None)
    assert "falsa_oob" in {o.nombre for o in e.omitidas}
    assert "falsa_oob" not in {a.nombre for a in e.aplicables}


def test_la_omitida_no_suma_al_total_de_peticiones():
    sin = dast.Escaneo(CRUDO, _dentro())
    con = dast.Escaneo(CRUDO, _dentro(), pruebas_extra=[_falsa_oob()])
    assert con.total == sin.total, "lo que no se va a mandar no se cuenta"


def test_con_canal_la_estrategia_si_entra():
    e = dast.Escaneo(CRUDO, _dentro(), pruebas_extra=[_falsa_oob()],
                     oob=object())
    assert "falsa_oob" in {a.nombre for a in e.aplicables}
    assert e.omitidas == []


def test_una_estrategia_sin_requisitos_siempre_entra():
    e = dast.Escaneo(CRUDO, _dentro())
    assert e.omitidas == []
    assert {a.nombre for a in e.aplicables} >= {"reflejo", "sqli_error"}


# --------------------------------------------- una estrategia que revienta
def test_una_estrategia_rota_no_tumba_el_barrido(eco):
    """Sobre todo si viene de un plugin: un tercero no puede dejar al
    analista sin el resto del barrido."""
    class _Rota:
        """Cumple el protocolo de Estrategia y revienta al probar."""
        nombre = "rota"
        titulo = "rota"
        wstg: list = []
        severidad = "low"
        requiere = frozenset()
        peticiones = 1

        def probar(self, ctx):
            raise RuntimeError("rota a proposito")

    rota = _Rota()

    h, p = eco
    crudo = f"GET /refleja?q=hola HTTP/1.1\r\nHost: {h}:{p}\r\n\r\n"
    e = dast.Escaneo(crudo, alc.Alcance.desde_texto(f"+{h}"),
                     pruebas_extra=[rota], por_segundo=200)
    hallazgos = e.correr(lambda f: None)
    assert e.terminado
    assert any(x.kind == "DAST" for x in hallazgos), \
        "las demas estrategias siguen encontrando"


# ------------------------------------------------ el Finding que produce
def test_el_hallazgo_sale_como_candidato_nunca_confirmado(eco):
    """Regla 6: candidato no es hallazgo. La maquina no confirma."""
    h, p = eco
    crudo = f"GET /refleja?q=hola HTTP/1.1\r\nHost: {h}:{p}\r\n\r\n"
    e = dast.Escaneo(crudo, alc.Alcance.desde_texto(f"+{h}"), por_segundo=200)
    hallazgos = e.correr(lambda f: None)
    assert hallazgos
    assert all(not x.confirmed for x in hallazgos)


def test_el_finding_lleva_la_confianza_y_el_payload(eco):
    h, p = eco
    crudo = f"GET /refleja?q=hola HTTP/1.1\r\nHost: {h}:{p}\r\n\r\n"
    e = dast.Escaneo(crudo, alc.Alcance.desde_texto(f"+{h}"), por_segundo=200)
    hallazgos = e.correr(lambda f: None)
    uno = next(x for x in hallazgos if x.extra.get("prueba") == "reflejo")
    assert uno.extra["confianza"] in ("baja", "media", "alta")
    assert uno.extra["payload"]
    assert uno.severity == "high"


def test_un_wstg_inventado_en_una_estrategia_lo_rechaza_el_plugin():
    """La validacion de plugins sigue viva tras el refactor: un ID que no
    existe acabaria en el informe de un cliente que va a buscarlo."""
    from luzxfer.core import plugins

    class _Api(plugins._Api):
        pass

    reg = plugins.Registro()
    api = _Api(reg, "prueba")
    mala = EstrategiaPayloads(nombre="m", titulo="t", payloads=["A"],
                              wstg=["WSTG-NOEXISTE-99"],
                              evalua=lambda c, s, h: None)
    with pytest.raises(ValueError):
        api.prueba(mala)


# ------------------------------------------------ booleano ciego (B3)
from luzxfer.core.tools.dast_estrategias import EstrategiaBooleana  # noqa: E402


def _ctx_guion(guion):
    """Contexto cuyo `enviar` responde segun un guion payload -> (estado, cuerpo).

    Permite escribir el comportamiento del servidor sin levantar nada, que
    es como se prueba un PROTOCOLO: lo que importa no es la red, es que la
    decision sea la correcta ante cada forma de responder.
    """
    punto = dast.puntos(CRUDO)[0]

    def enviar(payload):
        estado, cuerpo = guion(payload)
        return _flujo(cuerpo, estado)

    return Contexto(CRUDO, punto, enviar)


def _como_juice_shop(payload):
    """401 corto salvo que la condicion sea verdadera: 200 largo.

    Es el caso medido contra OWASP Juice Shop: el login es inyectable y
    NINGUNA de las cuatro familias viejas podia verlo, porque no hay
    reflejo ni cadena de error SQL. Lo unico que lo delata es que la
    respuesta cambia.
    """
    if "1=1" in payload or "'1'='1" in payload:
        return 200, b'{"authentication":{"token":"eyJ0eXAiOi' + b"x" * 700 + b'"}}'
    return 401, b"Invalid email or password."


def test_el_booleano_caza_el_caso_de_juice_shop():
    """Criterio de aceptacion de B3, tomado de un objetivo real."""
    h = EstrategiaBooleana().probar(_ctx_guion(_como_juice_shop))
    assert h is not None
    assert h.confianza == "alta"
    assert "1=1" in h.payload


def test_un_endpoint_que_no_inyecta_no_da_positivo():
    """Responde igual pase lo que pase."""
    h = EstrategiaBooleana().probar(
        _ctx_guion(lambda p: (200, b"siempre lo mismo")))
    assert h is None


def test_una_pagina_que_varia_sola_no_da_positivo():
    """El riesgo real del diferencial: un token CSRF o un timestamp hacen
    que cada respuesta mida distinto. Sin medir esa variacion natural,
    CUALQUIER payload pareceria haber cambiado algo."""
    import itertools
    contador = itertools.count()

    def varia(payload):
        n = next(contador)
        return 200, f"<token>{'x' * (n * 97)}</token>".encode()

    assert EstrategiaBooleana().probar(_ctx_guion(varia)) is None


def test_un_cambio_solo_de_tamano_tambien_cuenta():
    """No hace falta que cambie el codigo de estado: en muchas apps la
    condicion verdadera devuelve mas filas con el mismo 200."""
    def por_tamano(payload):
        if "1=1" in payload or "'1'='1" in payload:
            return 200, b"resultado " * 200
        return 200, b"sin resultados"

    h = EstrategiaBooleana().probar(_ctx_guion(por_tamano))
    assert h is not None


def test_si_la_condicion_falsa_ya_cambia_la_respuesta_no_se_concluye():
    """Si el payload falso YA altera la respuesta, lo que cambio no fue la
    condicion sino el hecho de inyectar algo raro: no es un booleano."""
    def rompe_con_cualquier_cosa(payload):
        if payload == "hola":
            return 200, b"normal"
        return 500, b"error generico"

    assert EstrategiaBooleana().probar(_ctx_guion(rompe_con_cualquier_cosa)) is None


def test_la_cota_de_peticiones_es_real():
    e = EstrategiaBooleana()
    enviados = []
    punto = dast.puntos(CRUDO)[0]
    ctx = Contexto(CRUDO, punto,
                   lambda p: (enviados.append(p), _flujo(b"igual"))[1])
    e.probar(ctx)
    assert len(enviados) <= e.peticiones, \
        f"mando {len(enviados)} y declara {e.peticiones}"


# ------------------------------- reflejo: no confundir con un 404 del servidor
def test_un_reflejo_en_un_404_no_es_un_hallazgo():
    """Medido contra DVWA: fuzzear un segmento de ruta da un 404 de Apache
    que REPITE la URL pedida. El marcador vuelve, pero no lo refleja la
    aplicacion: lo refleja la pagina de error del servidor. Como fuzzear
    rutas genera 404s por naturaleza, sin esta guarda cada barrido saldria
    contaminado."""
    def guion(payload):
        if payload == "hola":
            return 200, b"<html>pagina normal</html>"
        return 404, f"<h1>Not Found</h1><p>The requested URL {payload} ...".encode()

    assert dast.ESTRATEGIAS["reflejo"].probar(_ctx_guion(guion)) is None


def test_un_reflejo_en_la_pagina_de_verdad_si_es_un_hallazgo():
    """La guarda no puede tragarse la senal buena."""
    def guion(payload):
        return 200, f"<html>buscaste: {payload}</html>".encode()

    h = dast.ESTRATEGIAS["reflejo"].probar(_ctx_guion(guion))
    assert h is not None


def test_un_reflejo_en_un_500_que_ya_estaba_si_cuenta():
    """Si el baseline YA era un error, el error no lo causo el payload: la
    aplicacion esta respondiendo asi y reflejar ahi sigue siendo senal."""
    def guion(payload):
        return 500, f"<html>error: {payload}</html>".encode()

    assert dast.ESTRATEGIAS["reflejo"].probar(_ctx_guion(guion)) is not None


def test_el_baseline_se_comparte_entre_estrategias_del_mismo_punto():
    """Cada estrategia que lo pida no puede costar una peticion mas: el
    baseline es el mismo para todas las del mismo punto."""
    enviados = []
    punto = dast.puntos(CRUDO)[0]
    compartido: dict = {}

    def enviar(p):
        enviados.append(p)
        return _flujo(b"igual")

    c1 = Contexto(CRUDO, punto, enviar, cache_baseline=compartido)
    c2 = Contexto(CRUDO, punto, enviar, cache_baseline=compartido)
    c1.baseline()
    c2.baseline()
    assert enviados == ["hola"], "el segundo reusa el del primero"
