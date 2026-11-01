"""Tests de como se presenta un cuerpo de respuesta.

La regla de todo este modulo: nunca mentir sobre lo que llego. Si se
reorganiza, se dice; si no se puede leer, se dice; y los bytes crudos
siempre estan a una tecla.
"""
from __future__ import annotations

import json

from luzxfer.core.tools import cuerpo


# ------------------------------------------------------------- es_json
def test_reconoce_los_tipos_json():
    assert cuerpo.es_json("application/json")
    assert cuerpo.es_json("application/json; charset=utf-8")
    assert cuerpo.es_json("application/problem+json")
    assert cuerpo.es_json("text/json")
    assert not cuerpo.es_json("text/html")
    assert not cuerpo.es_json("")


# -------------------------------------------------------- embellecer
def test_embellecer_indenta_un_json_minificado():
    crudo = '{"status":"success","data":{"id":6,"coupon":null}}'
    salida = cuerpo.embellecer_json(crudo)
    assert salida is not None
    assert '\n  "status": "success"' in salida
    assert json.loads(salida) == json.loads(crudo)      # mismo contenido


def test_embellecer_no_escapa_los_acentos():
    """ensure_ascii=False: ver \\u00f1 en pantalla no ayuda a nadie."""
    salida = cuerpo.embellecer_json('{"msg":"contraseña inválida"}')
    assert "contraseña inválida" in salida


def test_embellecer_devuelve_none_si_no_es_json_valido():
    """Un JSON roto es interesante en si mismo: no se disimula."""
    assert cuerpo.embellecer_json('{"a":1,}') is None
    assert cuerpo.embellecer_json("<html>no soy json</html>") is None
    assert cuerpo.embellecer_json("") is None


def test_embellecer_aguanta_un_json_enorme_y_anidado():
    hondo = json.dumps({"a": [{"b": {"c": list(range(500))}}]})
    assert cuerpo.embellecer_json(hondo) is not None


# ---------------------------------------------------------- binarios
def test_reconoce_los_tipos_binarios_por_content_type():
    assert cuerpo.es_binario("font/woff", b"wOFF\x00\x01")
    assert cuerpo.es_binario("image/png", b"\x89PNG")
    assert cuerpo.es_binario("application/pdf", b"%PDF-1.4")
    assert cuerpo.es_binario("application/octet-stream", b"cualquier cosa")


def test_el_texto_no_se_toma_por_binario():
    assert not cuerpo.es_binario("application/json", b'{"a":1}')
    assert not cuerpo.es_binario("text/html; charset=utf-8", b"<html>hola</html>")
    assert not cuerpo.es_binario("application/javascript", b"var a = 1;")
    assert not cuerpo.es_binario("text/css", b"body { color: red }")


def test_sin_content_type_se_miran_los_bytes():
    assert cuerpo.es_binario("", b"texto\x00con nulo")
    assert not cuerpo.es_binario("", b"solo texto normal\ncon saltos\n")
    assert not cuerpo.es_binario("", b"")


def test_el_resumen_binario_dice_cuanto_y_de_que():
    r = cuerpo.resumen_binario(b"x" * 40904, "font/woff")
    assert "40904" in r.replace(".", "").replace(",", "")
    assert "font/woff" in r


# ------------------------------------------------------------- hexdump
def test_el_volcado_hex_tiene_offset_hex_y_ascii():
    lineas = cuerpo.volcado_hex(b"ABCDEFGH" * 2).splitlines()
    assert lineas[0].startswith("00000000")
    assert "41 42 43 44" in lineas[0]          # ABCD
    assert lineas[0].rstrip().endswith("ABCDEFGHABCDEFGH")


def test_el_volcado_hex_respeta_el_limite():
    salida = cuerpo.volcado_hex(b"x" * 10_000, limite=64)
    assert len(salida.splitlines()) == 4        # 64 bytes / 16 por linea


def test_el_volcado_hex_de_nada_es_nada():
    assert cuerpo.volcado_hex(b"") == ""


# ----------------------------------------------------------- presentar
def test_presentar_json_bonito_dice_que_lo_reorganizo():
    texto, nota = cuerpo.presentar(b'{"a":1,"b":[2,3]}', "application/json",
                                   bonito=True)
    assert '"a": 1' in texto
    assert "reorganizado" in nota.lower()


def test_presentar_json_crudo_no_toca_nada():
    crudo = b'{"a":1,"b":[2,3]}'
    texto, nota = cuerpo.presentar(crudo, "application/json", bonito=False)
    assert texto == crudo.decode()
    assert nota == ""


def test_presentar_json_invalido_lo_dice_y_muestra_lo_que_llego():
    """Que el servidor conteste JSON roto es un dato, no un estorbo."""
    texto, nota = cuerpo.presentar(b'{"a":1,}', "application/json", bonito=True)
    assert texto == '{"a":1,}'
    assert "no es json valido" in nota.lower()


def test_presentar_un_binario_resume_y_vuelca_hex():
    texto, nota = cuerpo.presentar(b"wOFF\x00\x01\x02" * 100, "font/woff",
                                   bonito=True)
    assert "00000000" in texto                  # hay volcado
    assert "binario" in nota.lower()
    assert "font/woff" in nota


def test_presentar_un_binario_en_crudo_sigue_sin_volcarlo_como_texto():
    """Ni en modo crudo tiene sentido escupir 40 KB de basura: en crudo
    se ve el hexadecimal, que es la forma cruda de mirar bytes."""
    texto, _ = cuerpo.presentar(b"\x89PNG\x00\x01" * 50, "image/png",
                                bonito=False)
    assert "00000000" in texto


def test_presentar_texto_normal_lo_deja_igual():
    texto, nota = cuerpo.presentar(b"<html>hola</html>", "text/html", bonito=True)
    assert texto == "<html>hola</html>"
    assert nota == ""


def test_presentar_recorta_y_lo_avisa():
    texto, nota = cuerpo.presentar(b"x" * 5000, "text/plain", bonito=True,
                                   limite=100)
    assert len(texto) < 300
    assert "recortado" in nota.lower()


def test_presentar_un_cuerpo_vacio_no_revienta():
    for ctype in ("application/json", "text/html", "font/woff", ""):
        texto, nota = cuerpo.presentar(b"", ctype, bonito=True)
        assert texto == ""


# ------------------------------------------- trabajo acotado (regresion)
def test_un_cuerpo_enorme_no_se_parsea_entero_para_mostrar_un_trozo():
    """Regresion. presentar() parseaba el JSON completo y lo volvia a
    serializar para quedarse con los primeros 200.000 caracteres: 51 MB
    costaban 3 s de interfaz congelada y 215 MB de pico, solo por
    seleccionar un flujo. En Termux, que es un telefono, mucho peor.

    Por encima del umbral no se reorganiza: un JSON recortado no se puede
    parsear de todas formas, asi que embellecer un cuerpo enorme solo
    sirve para tirar el trabajo a la basura."""
    import time

    grande = json.dumps([{"id": i, "d": "x" * 200} for i in range(60_000)]).encode()
    assert len(grande) > 10_000_000

    t = time.time()
    texto, nota = cuerpo.presentar(grande, "application/json", bonito=True,
                                   limite=200_000)
    assert time.time() - t < 0.5
    assert len(texto) < 220_000
    assert "demasiado grande" in nota.lower()
    assert "recortado" in nota.lower()
    assert "reorganizado" not in nota.lower()


def test_un_json_que_cabe_si_se_reorganiza():
    """El umbral no debe castigar al caso normal."""
    normal = json.dumps([{"id": i} for i in range(50)]).encode()
    texto, nota = cuerpo.presentar(normal, "application/json", bonito=True,
                                   limite=200_000)
    assert '"id": 0' in texto
    assert "reorganizado" in nota.lower()


def test_un_binario_enorme_tampoco_se_decodifica_entero():
    import time
    enorme = (b"\x89PNG\x00\x01\x02\x03" * 2_000_000)      # 16 MB
    t = time.time()
    texto, nota = cuerpo.presentar(enorme, "image/png", bonito=True)
    assert time.time() - t < 0.5
    assert "00000000" in texto and "binario" in nota.lower()


# ---------------------------------- sospecha 7: charset que no es utf-8
def test_se_respeta_el_charset_que_declara_el_servidor():
    """Los acentos llegaban como el caracter de reemplazo: se decodificaba
    todo como utf-8 ignorando el Content-Type. Corrupcion silenciosa, y
    el detector usa el mismo camino, asi que un reflejo con acentos no se
    encontraba."""
    latin = '{"mensaje":"contraseña inválida"}'.encode("latin-1")
    texto, _ = cuerpo.presentar(latin, "application/json; charset=iso-8859-1",
                                bonito=True)
    assert "contraseña inválida" in texto
    assert "�" not in texto


def test_charset_de_lee_el_content_type():
    assert cuerpo.charset_de("text/html; charset=iso-8859-1") == "iso-8859-1"
    assert cuerpo.charset_de('text/html; charset="utf-8"') == "utf-8"
    assert cuerpo.charset_de("text/html;charset=Windows-1252") == "windows-1252"
    assert cuerpo.charset_de("application/json") == "utf-8"
    assert cuerpo.charset_de("") == "utf-8"


def test_un_charset_inventado_no_revienta():
    """El Content-Type lo escribe el servidor, que puede poner lo que
    quiera. Un charset inexistente cae a utf-8 en vez de lanzar."""
    assert cuerpo.charset_de("text/html; charset=no-existe-esto") == "utf-8"
    texto, _ = cuerpo.presentar(b"hola", "text/html; charset=inventado",
                                bonito=True)
    assert texto == "hola"


def test_sin_charset_declarado_se_asume_utf8():
    texto, _ = cuerpo.presentar("ñandú".encode(), "text/html", bonito=True)
    assert texto == "ñandú"
