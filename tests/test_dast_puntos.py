"""Tests del modelo de puntos de inyeccion del DAST.

Un punto es un sitio donde el escaner puede meter un payload. Hoy el DAST
solo sabe de query y cuerpo de formulario; un cuerpo JSON se rechazaba a
proposito, porque trocearlo como si fuera un formulario mandaria basura al
servidor y daria resultados que no significan nada.

Ahora se parsea de verdad. La regla que NO cambia: un Content-Type que no
se entiende sigue sin trocearse.
"""
from __future__ import annotations

import json

from luzxfer.core.tools.dast_puntos import con_payload, puntos


def _peticion(cuerpo: str, ctype: str = "application/json") -> str:
    return (f"POST /api HTTP/1.1\r\nHost: o.com\r\n"
            f"Content-Type: {ctype}\r\n"
            f"Content-Length: {len(cuerpo.encode())}\r\n\r\n{cuerpo}")


def _hojas(crudo: str):
    return [(p.ruta_json, p.valor) for p in puntos(crudo) if p.donde == "json"]


# ------------------------------------------------------------- deteccion
def test_json_produce_un_punto_por_hoja():
    crudo = _peticion('{"user":{"name":"ana"},"edad":30}')
    assert _hojas(crudo) == [("user.name", "ana"), ("edad", "30")]


def test_las_listas_tambien_son_hojas_con_su_indice():
    crudo = _peticion('{"ids":[7,8]}')
    assert _hojas(crudo) == [("ids.0", "7"), ("ids.1", "8")]


def test_un_json_que_es_una_lista_en_la_raiz():
    crudo = _peticion('["a","b"]')
    assert _hojas(crudo) == [("0", "a"), ("1", "b")]


def test_null_y_booleanos_no_son_puntos():
    """Meter una cadena donde habia un booleano o un null es un cambio de
    tipo, no una inyeccion: produce ruido sin senal."""
    crudo = _peticion('{"activo":true,"borrado":null,"q":"x"}')
    assert _hojas(crudo) == [("q", "x")]


def test_el_nombre_del_punto_es_la_ultima_clave():
    crudo = _peticion('{"user":{"name":"ana"}}')
    p = next(x for x in puntos(crudo) if x.donde == "json")
    assert p.nombre == "name"


def test_un_content_type_que_no_es_json_no_se_trocea():
    """La regla que no cambia: lo que no se entiende no se parte a ciegas."""
    crudo = _peticion('{"q":"x"}', ctype="application/octet-stream")
    assert _hojas(crudo) == []


def test_un_json_invalido_no_revienta_ni_inventa_puntos():
    crudo = _peticion('{"q": roto')
    assert _hojas(crudo) == []


def test_la_query_sigue_dando_puntos_con_un_cuerpo_json():
    crudo = ("POST /api?buscar=hola HTTP/1.1\r\nHost: o.com\r\n"
             "Content-Type: application/json\r\n\r\n" '{"q":"x"}')
    donde = [(p.donde, p.nombre) for p in puntos(crudo)]
    assert ("query", "buscar") in donde and ("json", "q") in donde


# ----------------------------------------------------------- sustitucion
def test_sustituir_en_json_reserializa_valido_y_no_rompe_la_estructura():
    """Un payload con comillas y llaves tiene que viajar como VALOR de la
    hoja, no partir el JSON en basura."""
    crudo = _peticion('{"q":"hola"}')
    p = next(x for x in puntos(crudo) if x.donde == "json")
    nuevo = con_payload(crudo, p, '"><b>')
    cuerpo = nuevo.split("\r\n\r\n", 1)[1]
    assert json.loads(cuerpo) == {"q": '"><b>'}


def test_sustituir_una_hoja_anidada_deja_el_resto_igual():
    crudo = _peticion('{"user":{"name":"ana","rol":"admin"},"edad":30}')
    p = next(x for x in puntos(crudo) if x.ruta_json == "user.name")
    cuerpo = con_payload(crudo, p, "PAYLOAD").split("\r\n\r\n", 1)[1]
    assert json.loads(cuerpo) == {"user": {"name": "PAYLOAD", "rol": "admin"},
                                  "edad": 30}


def test_una_clave_con_punto_no_confunde_la_ruta():
    """La ruta punteada es para enseñarla; sustituir usa el camino real,
    asi que una clave con un punto dentro no manda el payload a otro sitio."""
    crudo = _peticion('{"a.b":"uno","a":{"b":"dos"}}')
    p = next(x for x in puntos(crudo) if x.valor == "uno")
    cuerpo = con_payload(crudo, p, "X").split("\r\n\r\n", 1)[1]
    assert json.loads(cuerpo) == {"a.b": "X", "a": {"b": "dos"}}


def test_sustituir_recalcula_el_content_length():
    crudo = _peticion('{"q":"hola"}')
    p = next(x for x in puntos(crudo) if x.donde == "json")
    nuevo = con_payload(crudo, p, "un payload mucho mas largo que hola")
    cabeza, cuerpo = nuevo.split("\r\n\r\n", 1)
    declarado = next(ln.split(":", 1)[1].strip() for ln in cabeza.splitlines()
                     if ln.lower().startswith("content-length:"))
    assert int(declarado) == len(cuerpo.encode())


def test_un_numero_sustituido_viaja_como_cadena():
    """El payload es texto; meterlo donde habia un numero lo convierte en
    cadena, que es lo que de verdad va a viajar."""
    crudo = _peticion('{"edad":30}')
    p = next(x for x in puntos(crudo) if x.donde == "json")
    cuerpo = con_payload(crudo, p, "1 OR 1=1").split("\r\n\r\n", 1)[1]
    assert json.loads(cuerpo) == {"edad": "1 OR 1=1"}


# --------------------------------------------- lo de antes sigue igual
def test_query_y_formulario_siguen_funcionando():
    crudo = ("POST /x?a=1 HTTP/1.1\r\nHost: o.com\r\n"
             "Content-Type: application/x-www-form-urlencoded\r\n\r\nb=2")
    donde = {(p.donde, p.nombre) for p in puntos(crudo)}
    assert donde == {("query", "a"), ("cuerpo", "b")}
