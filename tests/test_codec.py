"""Tests del conversor.

Lo que mas importa aqui no es convertir —eso es libreria estandar— sino
NO MENTIR: decir que algo es base64 cuando al decodificarlo sale basura
binaria es peor que no ofrecerlo, porque manda al analista a perseguir
un fantasma.
"""
from __future__ import annotations

import pytest

from luzxfer.core.tools import codec


# ------------------------------------------------------------ base64
def test_base64_ida_y_vuelta():
    assert codec.codificar("hola mundo", "base64") == "aG9sYSBtdW5kbw=="
    assert codec.decodificar("aG9sYSBtdW5kbw==", "base64") == "hola mundo"


def test_base64_sin_relleno_tambien_se_lee():
    """Los JWT y media web mandan base64url sin '='."""
    assert codec.decodificar("aG9sYSBtdW5kbw", "base64") == "hola mundo"


def test_base64url_con_guiones():
    import base64
    crudo = base64.urlsafe_b64encode(b"\xfb\xff?y").decode().rstrip("=")
    assert "-" in crudo or "_" in crudo
    assert codec.decodificar(crudo, "base64") is not None


def test_base64_que_no_lo_es_devuelve_none():
    for malo in ("no es base64 !!", "", "   "):
        assert codec.decodificar(malo, "base64") is None


# --------------------------------------------------------------- url
def test_url_ida_y_vuelta():
    assert codec.codificar("a b&c=d", "url") == "a%20b%26c%3Dd"
    assert codec.decodificar("a%20b%26c%3Dd", "url") == "a b&c=d"


def test_url_con_mas_como_espacio():
    assert codec.decodificar("hola+mundo", "url") == "hola mundo"


# --------------------------------------------------------------- hex
def test_hex_ida_y_vuelta():
    assert codec.codificar("AB", "hex") == "4142"
    assert codec.decodificar("4142", "hex") == "AB"
    assert codec.decodificar("41 42", "hex") == "AB", "los espacios sobran"


def test_hex_impar_o_invalido_devuelve_none():
    assert codec.decodificar("414", "hex") is None
    assert codec.decodificar("zz", "hex") is None


# ------------------------------------------------------------- html
def test_html_ida_y_vuelta():
    assert codec.codificar("<a href='x'>", "html") == \
        "&lt;a href=&#x27;x&#x27;&gt;"
    assert codec.decodificar("&lt;script&gt;", "html") == "<script>"
    assert codec.decodificar("&#60;b&#62;", "html") == "<b>"


# -------------------------------------------------------------- jwt
def test_un_jwt_se_abre_en_cabecera_y_cuerpo():
    import base64
    import json

    def b64(d):
        return base64.urlsafe_b64encode(json.dumps(d).encode()).decode().rstrip("=")

    tok = f"{b64({'alg': 'HS256'})}.{b64({'sub': 'admin', 'exp': 1})}.firma"
    salida = codec.decodificar(tok, "jwt")
    assert salida is not None
    assert '"alg": "HS256"' in salida
    assert '"sub": "admin"' in salida
    assert "firma" in salida, "la firma se enseña, aunque no se valide"


def test_lo_que_no_es_jwt_no_lo_finge():
    for malo in ("a.b", "aG9sYQ==", "x.y.z", ""):
        assert codec.decodificar(malo, "jwt") is None


def test_el_jwt_no_dice_que_la_firma_sea_valida():
    """Decodificar no es verificar, y confundirlo en una herramienta de
    seguridad seria grave."""
    import base64
    import json
    b = base64.urlsafe_b64encode(json.dumps({"alg": "none"}).encode()).decode().rstrip("=")
    salida = codec.decodificar(f"{b}.{b}.", "jwt")
    assert salida is not None
    assert "no se comprueba" in salida.lower() or "sin verificar" in salida.lower()


# ----------------------------------------------------- que podria ser
def test_detecta_lo_que_parece_base64():
    opciones = dict(codec.detectar("aG9sYSBtdW5kbw=="))
    assert opciones["base64"] == "hola mundo"


def test_no_ofrece_base64_si_sale_basura_binaria():
    """Decir que algo es base64 cuando al abrirlo sale binario manda al
    analista a perseguir un fantasma."""
    opciones = dict(codec.detectar("Zm9vYmFy////"))
    assert "base64" not in opciones or opciones["base64"].isprintable()


def test_detecta_url_solo_si_cambia_algo():
    assert "url" in dict(codec.detectar("a%20b"))
    assert "url" not in dict(codec.detectar("texto normal")), \
        "si no cambia nada, ofrecerlo es ruido"


def test_detecta_un_jwt():
    import base64
    import json
    b = base64.urlsafe_b64encode(json.dumps({"alg": "HS256"}).encode()).decode().rstrip("=")
    assert "jwt" in dict(codec.detectar(f"{b}.{b}.firma"))


def test_texto_normal_no_ofrece_nada():
    assert codec.detectar("hola que tal") == []


def test_detectar_aguanta_cualquier_cosa():
    for raro in ("", "   ", "\x00\x01", "=" * 500, "%%%%"):
        assert isinstance(codec.detectar(raro), list)


# ----------------------------------------------------------- formatos
def test_todos_los_formatos_van_y_vienen():
    for formato in codec.FORMATOS:
        if formato == "jwt":
            continue            # el jwt no se codifica, solo se abre
        codificado = codec.codificar("prueba 123", formato)
        assert codec.decodificar(codificado, formato) == "prueba 123", formato


def test_un_formato_que_no_existe_se_rechaza():
    with pytest.raises(ValueError):
        codec.decodificar("x", "inventado")
    with pytest.raises(ValueError):
        codec.codificar("x", "inventado")


# ------------------------------------- lo que vale la pena abrir de un flujo
def _flujo(cab=(), url="http://o.com/x"):
    from luzxfer.core.models import Flow, Request, Response
    return Flow(request=Request(method="GET", url=url,
                                headers=[("Host", "o.com"), *cab]),
                response=Response(status=200, body=b"ok"))


def _jwt():
    import base64
    import json

    def b64(d):
        return base64.urlsafe_b64encode(json.dumps(d).encode()).decode().rstrip("=")
    return f"{b64({'alg': 'HS256'})}.{b64({'sub': 'admin'})}.firma"


def test_el_candidato_prefiere_un_jwt_del_authorization():
    tok = _jwt()
    f = _flujo(cab=[("Authorization", f"Bearer {tok}")])
    valor, origen = codec.candidato(f)
    assert valor == tok and "authorization" in origen.lower()


def test_tambien_lo_busca_en_las_cookies():
    tok = _jwt()
    f = _flujo(cab=[("Cookie", f"sesion=abc; token={tok}")])
    valor, origen = codec.candidato(f)
    assert valor == tok and "cookie" in origen.lower()


def test_si_no_hay_jwt_coge_algo_que_parezca_codificado():
    f = _flujo(url="http://o.com/x?dato=aG9sYSBtdW5kbw%3D%3D")
    valor, origen = codec.candidato(f)
    assert valor and codec.decodificar(valor, "base64") == "hola mundo"


def test_sin_nada_interesante_no_se_inventa():
    valor, origen = codec.candidato(_flujo())
    assert valor == "" and origen == ""


def test_el_candidato_aguanta_un_flujo_raro():
    f = _flujo(cab=[("Cookie", "=;;=="), ("Authorization", "Bearer")])
    assert isinstance(codec.candidato(f), tuple)


# ------------------------------------------------------------- pantalla
async def test_la_tecla_d_abre_el_conversor():
    from textual.widgets import DataTable

    from luzxfer.tui.app import LuzxferApp
    from luzxfer.tui.screens.codec import ConversorScreen
    app = LuzxferApp(arrancar_motor=False)
    async with app.run_test(size=(120, 36)) as pilot:
        app._ingresar(_flujo())
        await pilot.pause()
        app.query_one("#flujos", DataTable).move_cursor(row=0)
        await pilot.pause()
        await pilot.press("d")
        await pilot.pause()
        assert isinstance(app.screen, ConversorScreen)


async def test_se_abre_con_el_token_del_flujo_dentro():
    from textual.widgets import DataTable, TextArea

    from luzxfer.tui.app import LuzxferApp
    app = LuzxferApp(arrancar_motor=False)
    tok = _jwt()
    async with app.run_test(size=(120, 36)) as pilot:
        app._ingresar(_flujo(cab=[("Authorization", f"Bearer {tok}")]))
        await pilot.pause()
        app.query_one("#flujos", DataTable).move_cursor(row=0)
        await pilot.pause()
        await pilot.press("d")
        await pilot.pause()
        assert app.screen.query_one("#cod-entrada", TextArea).text == tok


async def test_enseña_lo_que_podria_ser():
    from textual.widgets import Static, TextArea

    from luzxfer.tui.app import LuzxferApp
    app = LuzxferApp(arrancar_motor=False)
    async with app.run_test(size=(120, 36)) as pilot:
        app._ingresar(_flujo())
        await pilot.pause()
        await pilot.press("d")
        await pilot.pause()
        app.screen.query_one("#cod-entrada", TextArea).text = "aG9sYSBtdW5kbw=="
        await pilot.pause()
        salida = app.screen.query_one("#cod-salida", Static).render().plain
        assert "base64" in salida and "hola mundo" in salida


async def test_texto_normal_dice_que_no_parece_nada():
    from textual.widgets import Static, TextArea

    from luzxfer.tui.app import LuzxferApp
    app = LuzxferApp(arrancar_motor=False)
    async with app.run_test(size=(120, 36)) as pilot:
        app._ingresar(_flujo())
        await pilot.pause()
        await pilot.press("d")
        await pilot.pause()
        app.screen.query_one("#cod-entrada", TextArea).text = "hola que tal"
        await pilot.pause()
        salida = app.screen.query_one("#cod-salida", Static).render().plain
        assert "no parece" in salida.lower()


async def test_se_puede_codificar_a_un_formato():
    from textual.widgets import Static, TextArea

    from luzxfer.tui.app import LuzxferApp
    app = LuzxferApp(arrancar_motor=False)
    async with app.run_test(size=(120, 36)) as pilot:
        app._ingresar(_flujo())
        await pilot.pause()
        await pilot.press("d")
        await pilot.pause()
        app.screen.query_one("#cod-entrada", TextArea).text = "a b&c"
        await pilot.pause()
        app.screen.action_codificar()       # recorre los formatos
        await pilot.pause()
        salida = app.screen.query_one("#cod-salida", Static).render().plain
        assert "a%20b%26c" in salida or "YSBiJmM=" in salida


async def test_un_jwt_avisa_de_que_no_verifica():
    from textual.widgets import Static, TextArea

    from luzxfer.tui.app import LuzxferApp
    app = LuzxferApp(arrancar_motor=False)
    async with app.run_test(size=(120, 36)) as pilot:
        app._ingresar(_flujo())
        await pilot.pause()
        await pilot.press("d")
        await pilot.pause()
        app.screen.query_one("#cod-entrada", TextArea).text = _jwt()
        await pilot.pause()
        salida = app.screen.query_one("#cod-salida", Static).render().plain
        assert "no se comprueba" in salida.lower()
