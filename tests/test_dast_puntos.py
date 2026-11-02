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
    # contencion y no igualdad: la lista de puntos crece con cada tarea
    # (cabeceras, cookies, ruta…), y clavarla aqui obligaria a tocar este
    # test en cada una sin que pruebe nada nuevo
    assert {("query", "a"), ("cuerpo", "b")} <= donde


# ------------------------------------------------- cabeceras y cookies
def test_cookies_y_cabeceras_marcadas_son_puntos():
    crudo = ("GET / HTTP/1.1\r\nHost: o.com\r\n"
             "User-Agent: curl\r\nCookie: sid=abc; theme=dark\r\n\r\n")
    marcas = {(p.donde, p.nombre) for p in puntos(crudo)}
    assert ("cookie", "sid") in marcas
    assert ("cookie", "theme") in marcas
    assert ("cabecera", "User-Agent") in marcas


def test_solo_se_inyecta_en_las_cabeceras_marcadas():
    """Inyectar en TODAS multiplica el ruido y el trafico sin senal: se
    marca la lista donde una inyeccion es plausible."""
    crudo = ("GET / HTTP/1.1\r\nHost: o.com\r\nUser-Agent: curl\r\n"
             "Accept: */*\r\nX-Interno: no\r\n\r\n")
    nombres = {p.nombre for p in puntos(crudo) if p.donde == "cabecera"}
    assert "User-Agent" in nombres
    assert "Accept" not in nombres and "X-Interno" not in nombres


def test_el_host_no_es_un_punto_generico():
    """Toda peticion lleva Host: incluirlo convertiria «aqui no hay nada
    que inyectar» en «escanea siempre», multiplicando el trafico contra el
    sistema de un cliente. La inyeccion por Host es una clase propia y se
    hara con su estrategia, no disparandola en cada GET."""
    crudo = "GET / HTTP/1.1\r\nHost: o.com\r\n\r\n"
    assert puntos(crudo) == []


def test_sustituir_una_cabecera_deja_las_demas_igual():
    crudo = ("GET / HTTP/1.1\r\nHost: o.com\r\nUser-Agent: curl\r\n"
             "Accept: */*\r\n\r\n")
    p = next(x for x in puntos(crudo) if x.nombre == "User-Agent")
    nuevo = con_payload(crudo, p, "PAYLOAD")
    assert "User-Agent: PAYLOAD" in nuevo
    assert "Host: o.com" in nuevo and "Accept: */*" in nuevo


def test_sustituir_una_cookie_conserva_las_otras():
    crudo = ("GET / HTTP/1.1\r\nHost: o.com\r\n"
             "Cookie: sid=abc; theme=dark\r\n\r\n")
    p = next(x for x in puntos(crudo) if x.nombre == "sid")
    nuevo = con_payload(crudo, p, "PAYLOAD")
    linea = next(ln for ln in nuevo.splitlines() if ln.startswith("Cookie:"))
    assert "sid=PAYLOAD" in linea and "theme=dark" in linea


def test_payload_no_latin1_en_cookie_no_se_corrompe_en_silencio():
    """build_raw codifica a latin-1 con 'replace': un payload con acentos o
    emoji saldria mutado y el resultado no significaria nada. Como el fuzzer
    muta a proposito, aqui se dice en vez de callarlo."""
    import pytest

    from luzxfer.core.tools import dast_puntos
    crudo = "GET / HTTP/1.1\r\nHost: o.com\r\nCookie: a=1\r\n\r\n"
    p = next(x for x in puntos(crudo) if x.donde == "cookie")
    with pytest.raises(dast_puntos.PayloadNoRepresentable):
        con_payload(crudo, p, "piñata-☃")


def test_un_payload_latin1_en_cabecera_si_pasa():
    crudo = "GET / HTTP/1.1\r\nHost: o.com\r\nUser-Agent: curl\r\n\r\n"
    p = next(x for x in puntos(crudo) if x.nombre == "User-Agent")
    assert "User-Agent: ' OR 1=1--" in con_payload(crudo, p, "' OR 1=1--")


def test_sin_cookie_no_hay_puntos_de_cookie():
    crudo = "GET / HTTP/1.1\r\nHost: o.com\r\n\r\n"
    assert [p for p in puntos(crudo) if p.donde == "cookie"] == []


def test_dos_cabeceras_cookie_no_se_pisan_entre_si():
    """Mandar la misma cabecera dos veces es una tecnica de prueba, no un
    error a corregir (hay un test del repeater que lo fija). Sustituir en
    la primera no puede borrar la segunda ni duplicar la primera."""
    crudo = ("GET / HTTP/1.1\r\nHost: o.com\r\n"
             "Cookie: a=1\r\nCookie: b=2\r\n\r\n")
    p = next(x for x in puntos(crudo) if x.donde == "cookie")
    lineas = [ln for ln in con_payload(crudo, p, "X").splitlines()
              if ln.lower().startswith("cookie:")]
    assert lineas == ["Cookie: a=X", "Cookie: b=2"]


# --------------------------------------------------- ruta y multipart
def test_segmentos_de_ruta_son_puntos():
    """Alimenta traversal y LFI: el parametro no siempre esta en la query."""
    crudo = "GET /a/b/c HTTP/1.1\r\nHost: o.com\r\n\r\n"
    rutas = [(p.nombre, p.valor) for p in puntos(crudo) if p.donde == "ruta"]
    assert rutas == [("1", "a"), ("2", "b"), ("3", "c")]


def test_sustituir_un_segmento_conserva_los_demas():
    crudo = "GET /a/b/c HTTP/1.1\r\nHost: o.com\r\n\r\n"
    p = next(x for x in puntos(crudo) if x.donde == "ruta" and x.valor == "b")
    assert con_payload(crudo, p, "PAYLOAD").startswith("GET /a/PAYLOAD/c ")


def test_un_segmento_se_codifica_para_no_partir_la_linea():
    """Un payload con espacios partiria la linea de peticion en tres."""
    crudo = "GET /a HTTP/1.1\r\nHost: o.com\r\n\r\n"
    p = next(x for x in puntos(crudo) if x.donde == "ruta")
    primera = con_payload(crudo, p, "../../etc/passwd x").splitlines()[0]
    assert len(primera.split()) == 3, primera


def test_la_raiz_no_tiene_segmentos():
    crudo = "GET / HTTP/1.1\r\nHost: o.com\r\n\r\n"
    assert [p for p in puntos(crudo) if p.donde == "ruta"] == []


def test_la_query_no_se_cuela_como_segmento():
    crudo = "GET /a/b?q=1 HTTP/1.1\r\nHost: o.com\r\n\r\n"
    rutas = [p.valor for p in puntos(crudo) if p.donde == "ruta"]
    assert rutas == ["a", "b"]


_MULTI = (
    "POST /subir HTTP/1.1\r\nHost: o.com\r\n"
    "Content-Type: multipart/form-data; boundary=X\r\n"
    "Content-Length: 120\r\n\r\n"
    "--X\r\nContent-Disposition: form-data; name=\"q\"\r\n\r\nhola\r\n"
    "--X\r\nContent-Disposition: form-data; name=\"otro\"\r\n\r\ndos\r\n"
    "--X--\r\n"
)


def test_campos_multipart_son_puntos():
    campos = [(p.nombre, p.valor) for p in puntos(_MULTI) if p.donde == "multipart"]
    assert campos == [("q", "hola"), ("otro", "dos")]


def test_sustituir_un_campo_multipart_conserva_el_resto_y_los_crlf():
    p = next(x for x in puntos(_MULTI) if x.nombre == "q")
    nuevo = con_payload(_MULTI, p, "PAYLOAD")
    cuerpo = nuevo.split("\r\n\r\n", 1)[1]
    assert "\r\n\r\nPAYLOAD\r\n" in cuerpo, "el valor sustituido"
    assert "\r\n\r\ndos\r\n" in cuerpo, "el otro campo intacto"
    assert cuerpo.endswith("--X--\r\n")


def test_sustituir_multipart_recalcula_el_content_length():
    p = next(x for x in puntos(_MULTI) if x.nombre == "q")
    cabeza, cuerpo = con_payload(_MULTI, p, "mucho mas largo").split("\r\n\r\n", 1)
    declarado = next(ln.split(":", 1)[1].strip() for ln in cabeza.splitlines()
                     if ln.lower().startswith("content-length:"))
    assert int(declarado) == len(cuerpo.encode())


def test_un_multipart_sin_boundary_no_se_trocea():
    """Sin boundary no se puede partir sin inventar: no se inventa."""
    crudo = ("POST /x HTTP/1.1\r\nHost: o.com\r\n"
             "Content-Type: multipart/form-data\r\n\r\n--X\r\ncosas\r\n")
    assert [p for p in puntos(crudo) if p.donde == "multipart"] == []
