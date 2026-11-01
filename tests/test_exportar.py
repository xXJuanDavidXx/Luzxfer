"""Tests de la exportacion a `curl`.

Un `curl` que se parece a la peticion pero manda otra cosa es peor que no
tener exportacion: el cliente lo ejecuta, no pasa nada, y concluye que el
hallazgo era falso. Asi que lo que de verdad se prueba aqui no es que la
cadena tenga buena pinta, sino que **ejecutarla manda lo mismo**: los
tests que importan levantan el servidor de eco, corren el comando de
verdad y comparan lo que llego.

Comprobar la forma del texto sin ejecutarlo seria un test que pasa con el
cable cortado.
"""
from __future__ import annotations

import json
import shutil
import subprocess

import pytest

from luzxfer.core.models import Flow, Request, Response
from luzxfer.core.tools import exportar

hay_curl = pytest.mark.skipif(
    shutil.which("curl") is None, reason="no hay curl en esta maquina")


def _peticion(**kw) -> Request:
    base = dict(method="GET", url="http://o.com/x",
                headers=[("Host", "o.com")], body=b"")
    base.update(kw)
    return Request(**base)


def _ejecutar(comando: str) -> dict:
    """Corre el comando y devuelve el JSON que contesto el eco."""
    r = subprocess.run(comando, shell=True, capture_output=True, timeout=30)
    assert r.returncode == 0, f"curl fallo: {r.stderr.decode()[:400]}"
    return json.loads(r.stdout)


# ------------------------------------------------------------- la forma
def test_un_get_simple():
    c = exportar.a_curl(_peticion())
    assert c.startswith("curl ")
    assert c.endswith("'http://o.com/x'")
    assert "-X" not in c, "un GET sin cuerpo no necesita -X"


def test_el_metodo_sale_cuando_no_es_get():
    c = exportar.a_curl(_peticion(method="DELETE"))
    assert "-X 'DELETE'" in c


def test_un_get_con_cuerpo_fuerza_el_metodo():
    """Con cuerpo curl asume POST, asi que un GET con cuerpo —que existe,
    y es justo el caso interesante— saldria convertido si no se fuerza."""
    c = exportar.a_curl(_peticion(body=b"x=1"))
    assert "-X 'GET'" in c


def test_las_cabeceras_salen_todas():
    c = exportar.a_curl(_peticion(headers=[
        ("Host", "o.com"), ("Cookie", "s=abc"), ("X-Raro", "1")]))
    assert "'Host: o.com'" in c
    assert "'Cookie: s=abc'" in c
    assert "'X-Raro: 1'" in c


def test_se_usa_data_raw_y_no_d_ni_data_binary():
    """`-d` y `--data-binary` interpretan un `@` inicial como «lee este
    archivo del disco». Ver `test_un_cuerpo_con_arroba_no_lee_un_archivo`,
    que es donde se ve por que esto importa de verdad."""
    c = exportar.a_curl(_peticion(method="POST", body=b"@archivo"))
    assert "--data-raw" in c
    assert "--data-binary" not in c
    assert " -d " not in c


def test_las_comillas_del_cuerpo_no_rompen_el_comando():
    c = exportar.a_curl(_peticion(method="POST", body=b"a='1' b=\"2\""))
    # shlex se encarga; lo que importa es que no quede suelto
    assert c.count("--data-raw") == 1


def test_todo_va_siempre_entre_comillas():
    """Sin comillas, anadirle a mano un `&otro=1` —lo primero que hace
    cualquiera con un curl exportado— parte el comando en dos y manda el
    proceso al fondo. Con el cuerpo no es hipotetico: editarlo es justo
    para lo que se exporta."""
    c = exportar.a_curl(_peticion(method="POST", url="http://o.com/x",
                                  headers=[("X-A", "1")], body=b"u=admin"))
    assert "'http://o.com/x'" in c
    assert "--data-raw 'u=admin'" in c, "el cuerpo tambien"
    assert "-H 'X-A: 1'" in c, "y las cabeceras"
    assert "-X 'POST'" in c


def test_insecure_esta_apagado_por_defecto():
    """Debilitar TLS sin que nadie lo pida acaba en un informe que nadie
    puede reproducir."""
    assert " -k" not in exportar.a_curl(_peticion())
    assert " -k" in exportar.a_curl(_peticion(), insecure=True)


def test_un_cuerpo_binario_va_en_base64():
    c = exportar.a_curl(_peticion(method="POST", body=b"\x00\x01\xff"))
    assert "base64 -d" in c and "--data-binary @-" in c


def test_un_nul_cuenta_como_binario():
    """Un NUL pasa por utf-8 pero el shell corta ahi: el comando mandaria
    un cuerpo truncado sin decirlo."""
    assert not exportar._es_texto(b"hola\x00mundo")
    c = exportar.a_curl(_peticion(method="POST", body=b"hola\x00mundo"))
    assert "base64 -d" in c


# ------------------------------------------------------------- avisos
def test_avisa_de_content_length():
    p = _peticion(method="POST", body=b"x=1",
                  headers=[("Content-Length", "3")])
    assert any("Content-Length" in a for a in exportar.avisos_curl(p))


def test_no_avisa_de_content_length_sin_cuerpo():
    p = _peticion(headers=[("Content-Length", "0")])
    assert not any("Content-Length" in a for a in exportar.avisos_curl(p))


def test_avisa_del_base64():
    p = _peticion(method="POST", body=b"\x00\x01")
    assert any("base64" in a for a in exportar.avisos_curl(p))


def test_una_peticion_normal_no_avisa_de_nada():
    """Una lista de avisos que siempre tiene algo deja de leerse."""
    assert exportar.avisos_curl(_peticion()) == []


# --------------------------------------------- lo que de verdad importa
@hay_curl
def test_el_comando_manda_el_mismo_cuerpo(eco):
    """El test que cierra el asunto: se ejecuta y se compara lo que llego."""
    host, puerto = eco
    cuerpo = b"usuario=admin&clave=' OR '1'='1"
    p = _peticion(method="POST", url=f"http://{host}:{puerto}/eco",
                  headers=[("Content-Type",
                            "application/x-www-form-urlencoded")],
                  body=cuerpo)

    llego = _ejecutar(exportar.a_curl(p))
    assert llego["metodo"] == "POST"
    assert llego["cuerpo"] == cuerpo.decode()


@hay_curl
def test_el_comando_manda_las_mismas_cabeceras(eco):
    host, puerto = eco
    p = _peticion(method="POST", url=f"http://{host}:{puerto}/eco",
                  headers=[("X-Prueba", "valor con espacios"),
                           ("Cookie", "sesion=abc123; otra=2")],
                  body=b"x=1")

    llego = _ejecutar(exportar.a_curl(p))
    cabeceras = {k.lower(): v for k, v in llego["cabeceras"]}
    assert cabeceras["x-prueba"] == "valor con espacios"
    assert cabeceras["cookie"] == "sesion=abc123; otra=2"


@hay_curl
def test_un_cuerpo_con_comillas_y_saltos_llega_igual(eco):
    """Los saltos importan de verdad en pruebas de contrabando."""
    host, puerto = eco
    cuerpo = b"a='1'\nb=\"2\"\r\nc=$(id)`whoami`"
    p = _peticion(method="POST", url=f"http://{host}:{puerto}/eco",
                  body=cuerpo)

    llego = _ejecutar(exportar.a_curl(p))
    assert llego["cuerpo"] == cuerpo.decode(), \
        "el shell no puede tocar el cuerpo, ni expandir $() ni ``"


@hay_curl
def test_un_cuerpo_con_arroba_no_lee_un_archivo(eco):
    """La razon de usar --data-raw, y no es estilo.

    Con `-d` o `--data-binary`, curl interpreta un `@` inicial como «lee
    este archivo del disco y mandalo». Un cuerpo capturado que empiece
    por `@/etc/passwd` convertiria el comando exportado en una fuga: el
    archivo de la maquina de quien lo pegue, enviado al objetivo.

    Este test lo detecto cuando el codigo usaba --data-binary: el eco
    recibio el /etc/passwd de esta maquina.
    """
    host, puerto = eco
    p = _peticion(method="POST", url=f"http://{host}:{puerto}/eco",
                  body=b"@/etc/passwd")

    llego = _ejecutar(exportar.a_curl(p))
    assert llego["cuerpo"] == "@/etc/passwd", \
        "el comando leyo un archivo del disco en vez de mandar el cuerpo"
    assert "root:" not in llego["cuerpo"]


@hay_curl
def test_un_cuerpo_binario_llega_byte_a_byte(eco):
    """Un NUL manda el cuerpo por la rama de base64.

    Se usa un cuerpo con NUL y no bytes arbitrarios porque el servidor de
    eco decodifica como utf-8 estricto y reventaria el por su cuenta: lo
    que se prueba aqui es la tuberia de base64, no el eco.
    """
    host, puerto = eco
    cuerpo = b"antes\x00despues\n\ttabulado"
    assert not exportar._es_texto(cuerpo), "tiene que ir por base64"
    p = _peticion(method="POST", url=f"http://{host}:{puerto}/eco",
                  body=cuerpo)

    llego = _ejecutar(exportar.a_curl(p))
    assert llego["cuerpo"].encode() == cuerpo


# --------------------------------------------------------------- crudo
def test_a_crudo_peticion():
    f = Flow(request=_peticion())
    assert exportar.a_crudo(f).startswith("GET /x HTTP/1.1")


def test_a_crudo_respuesta():
    f = Flow(request=_peticion(),
             response=Response(status=200, reason="OK",
                               headers=[("Content-Type", "text/plain")],
                               body=b"hola"))
    salida = exportar.a_crudo(f, lado="respuesta")
    assert salida.startswith("HTTP/1.1 200 OK")
    assert salida.endswith("hola")


def test_a_crudo_sin_respuesta_lo_dice():
    """Devolver cadena vacia dejaria pensar que la respuesta era vacia."""
    assert exportar.a_crudo(Flow(request=_peticion()),
                            lado="respuesta") == "(sin respuesta)"


# ------------------------------------------------------ en la aplicacion
async def test_la_pantalla_abre_y_ensena_el_curl():
    from textual.widgets import DataTable, TextArea

    from luzxfer.tui.app import LuzxferApp
    from luzxfer.tui.screens.exportar import ExportarScreen

    app = LuzxferApp(arrancar_motor=False)
    async with app.run_test(size=(140, 44)) as pilot:
        app._ingresar(Flow(
            request=Request(method="POST", url="http://o.com/login",
                            headers=[("Host", "o.com")], body=b"u=admin"),
            response=Response(status=200, body=b"ok")))
        await pilot.pause()
        app.query_one("#flujos", DataTable).move_cursor(row=0)
        await pilot.pause()

        await pilot.press("u")
        await pilot.pause()
        assert isinstance(app.screen, ExportarScreen)

        texto = app.screen.query_one("#exp-texto", TextArea).text
        assert texto.startswith("curl ")
        assert "-X 'POST'" in texto and "--data-raw 'u=admin'" in texto


async def test_sin_flujo_elegido_avisa_en_vez_de_abrir():
    from luzxfer.tui.app import LuzxferApp
    from luzxfer.tui.screens.exportar import ExportarScreen

    app = LuzxferApp(arrancar_motor=False)
    async with app.run_test(size=(140, 44)) as pilot:
        await pilot.pause()
        await pilot.press("u")
        await pilot.pause()
        assert not isinstance(app.screen, ExportarScreen)


async def test_tab_recorre_las_tres_vistas():
    from textual.widgets import DataTable, TextArea

    from luzxfer.tui.app import LuzxferApp

    app = LuzxferApp(arrancar_motor=False)
    async with app.run_test(size=(140, 44)) as pilot:
        app._ingresar(Flow(
            request=Request(method="GET", url="http://o.com/x",
                            headers=[("Host", "o.com")]),
            response=Response(status=200, reason="OK", body=b"hola")))
        await pilot.pause()
        app.query_one("#flujos", DataTable).move_cursor(row=0)
        await pilot.pause()
        await pilot.press("u")
        await pilot.pause()

        editor = app.screen.query_one("#exp-texto", TextArea)
        assert editor.text.startswith("curl ")

        await pilot.press("tab")
        await pilot.pause()
        assert editor.text.startswith("GET /x HTTP/1.1")

        await pilot.press("tab")
        await pilot.pause()
        assert editor.text.startswith("HTTP/1.1 200 OK")

        await pilot.press("tab")
        await pilot.pause()
        assert editor.text.startswith("curl "), "vuelve al principio"


async def test_el_texto_se_puede_seleccionar():
    """Va en un TextArea y no en un Static para poder copiarlo con el
    raton: OSC 52 no funciona en todos los terminales."""
    from textual.widgets import DataTable, TextArea

    from luzxfer.tui.app import LuzxferApp

    app = LuzxferApp(arrancar_motor=False)
    async with app.run_test(size=(140, 44)) as pilot:
        app._ingresar(Flow(
            request=Request(method="GET", url="http://o.com/x",
                            headers=[("Host", "o.com")]),
            response=Response(status=200, body=b"ok")))
        await pilot.pause()
        app.query_one("#flujos", DataTable).move_cursor(row=0)
        await pilot.pause()
        await pilot.press("u")
        await pilot.pause()

        editor = app.screen.query_one("#exp-texto", TextArea)
        assert editor.read_only, "no se edita, pero se selecciona"
