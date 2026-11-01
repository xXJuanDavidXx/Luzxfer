"""Tests de la comparacion entre dos flujos.

«¿Que cambio entre estas dos respuestas?» es la pregunta que sigue a
casi todo lo que hace el Intruder. La trampa vuelve a ser la misma de
siempre: comparar los bytes guardados en vez de los descomprimidos
diria que dos respuestas gzip identicas son distintas, o al reves.
"""
from __future__ import annotations

import gzip

from luzxfer.core.models import Flow, Request, Response
from luzxfer.core.tools import comparar


def _f(cuerpo=b"", url="http://o.com/x", cab=(), status=200, metodo="GET",
       cuerpo_pet=b""):
    return Flow(
        request=Request(method=metodo, url=url,
                        headers=[("Host", "o.com")], body=cuerpo_pet),
        response=Response(status=status, reason="OK", body=cuerpo,
                          headers=[("Content-Type", "text/html"), *cab]),
    )


# ------------------------------------------------------------ basico
def test_dos_iguales_no_tienen_diferencias():
    a = _f(cuerpo=b"linea uno\nlinea dos")
    b = _f(cuerpo=b"linea uno\nlinea dos")
    d = comparar.diferencias(a, b, "respuesta")
    assert not any(t != " " for t, _ in d)
    assert comparar.cuantas(d) == (0, 0)


def test_una_linea_cambiada_sale_como_quitada_y_puesta():
    a = _f(cuerpo=b"hola\nmundo")
    b = _f(cuerpo=b"hola\nplaneta")
    d = comparar.diferencias(a, b, "respuesta")
    quitadas = [ln for t, ln in d if t == "-"]
    puestas = [ln for t, ln in d if t == "+"]
    assert any("mundo" in x for x in quitadas)
    assert any("planeta" in x for x in puestas)
    assert comparar.cuantas(d) == (1, 1)


def test_se_comparan_tambien_las_cabeceras():
    a = _f(cab=[("X-Pista", "uno")])
    b = _f(cab=[("X-Pista", "dos")])
    d = comparar.diferencias(a, b, "respuesta")
    assert any("uno" in ln for t, ln in d if t == "-")


def test_el_codigo_de_estado_se_ve():
    a = _f(status=200)
    b = _f(status=403)
    d = comparar.diferencias(a, b, "respuesta")
    texto = "\n".join(ln for _, ln in d)
    assert "200" in texto and "403" in texto


# ---------------------------------------------- la trampa de siempre
def test_compara_los_cuerpos_DESCOMPRIMIDOS():
    """Dos respuestas con el mismo contenido pueden tener bytes gzip
    distintos, y al reves. Comparar lo guardado diria cualquier cosa."""
    texto = b"<html>el mismo contenido exacto</html>"
    a = _f(cuerpo=gzip.compress(texto, mtime=1),
           cab=[("Content-Encoding", "gzip")])
    b = _f(cuerpo=gzip.compress(texto, mtime=999999),
           cab=[("Content-Encoding", "gzip")])
    assert a.response.body != b.response.body, "los bytes SI difieren"
    d = comparar.diferencias(a, b, "respuesta")
    assert comparar.cuantas(d) == (0, 0), "pero el contenido es el mismo"


def test_un_gzip_corrupto_no_rompe_la_comparacion():
    a = _f(cuerpo=b"no soy gzip", cab=[("Content-Encoding", "gzip")])
    b = _f(cuerpo=b"otra cosa")
    assert comparar.diferencias(a, b, "respuesta")


# ----------------------------------------------------------- peticion
def test_se_pueden_comparar_las_peticiones():
    a = _f(url="http://o.com/uno", metodo="GET")
    b = _f(url="http://o.com/dos", metodo="POST", cuerpo_pet=b"a=1")
    d = comparar.diferencias(a, b, "peticion")
    texto = "\n".join(ln for _, ln in d)
    assert "/uno" in texto and "/dos" in texto
    assert "POST" in texto


def test_un_flujo_sin_respuesta_se_dice_en_vez_de_reventar():
    a = Flow(request=Request(method="GET", url="http://o.com/x",
                             headers=[("Host", "o.com")]), response=None)
    d = comparar.diferencias(a, _f(), "respuesta")
    assert any("sin respuesta" in ln.lower() for _, ln in d)


def test_un_lado_que_no_es_valido_se_rechaza():
    import pytest
    with pytest.raises(ValueError):
        comparar.diferencias(_f(), _f(), "inventado")


# ------------------------------------------------------------ recorte
def test_una_diferencia_enorme_se_recorta_y_se_dice():
    a = _f(cuerpo=("\n".join(f"linea {i}" for i in range(5000))).encode())
    b = _f(cuerpo=("\n".join(f"otra {i}" for i in range(5000))).encode())
    d = comparar.diferencias(a, b, "respuesta", limite=200)
    assert len(d) <= 201
    assert any("recortad" in ln.lower() for _, ln in d)


def test_sin_recorte_no_se_inventa_el_aviso():
    a = _f(cuerpo=b"uno")
    b = _f(cuerpo=b"dos")
    d = comparar.diferencias(a, b, "respuesta", limite=200)
    assert not any("recortad" in ln.lower() for _, ln in d)


# --------------------------------------------------------- en la app
async def test_hacen_falta_exactamente_dos_marcados():
    from textual.widgets import DataTable

    from luzxfer.tui.app import LuzxferApp
    from luzxfer.tui.screens.comparar import CompararScreen
    app = LuzxferApp(arrancar_motor=False)
    async with app.run_test(size=(120, 36)) as pilot:
        for i in range(3):
            app._ingresar(_f(url=f"http://o.com/r{i}", cuerpo=f"c{i}".encode()))
        await pilot.pause()

        await pilot.press("y")
        await pilot.pause()
        assert not isinstance(app.screen, CompararScreen), "con 0 marcados, no"

        tabla = app.query_one("#flujos", DataTable)
        tabla.move_cursor(row=0)
        await pilot.press("m")
        await pilot.press("y")
        await pilot.pause()
        assert not isinstance(app.screen, CompararScreen), "con 1 marcado, no"

        tabla.move_cursor(row=1)
        await pilot.press("m")
        await pilot.press("y")
        await pilot.pause()
        assert isinstance(app.screen, CompararScreen), "con 2, si"


async def test_la_comparacion_muestra_la_diferencia():
    from textual.widgets import DataTable, Static

    from luzxfer.tui.app import LuzxferApp
    app = LuzxferApp(arrancar_motor=False)
    async with app.run_test(size=(120, 36)) as pilot:
        app._ingresar(_f(cuerpo=b"<html>admin</html>"))
        app._ingresar(_f(cuerpo=b"<html>invitado</html>"))
        await pilot.pause()
        tabla = app.query_one("#flujos", DataTable)
        for fila in (0, 1):
            tabla.move_cursor(row=fila)
            await pilot.press("m")
        await pilot.press("y")
        await pilot.pause()
        salida = app.screen.query_one("#cmp-salida", Static).render().plain
        assert "admin" in salida and "invitado" in salida


async def test_se_alterna_entre_peticion_y_respuesta():
    from textual.widgets import DataTable, Static

    from luzxfer.tui.app import LuzxferApp
    app = LuzxferApp(arrancar_motor=False)
    async with app.run_test(size=(120, 36)) as pilot:
        app._ingresar(_f(url="http://o.com/uno", cuerpo=b"igual"))
        app._ingresar(_f(url="http://o.com/dos", cuerpo=b"igual"))
        await pilot.pause()
        tabla = app.query_one("#flujos", DataTable)
        for fila in (0, 1):
            tabla.move_cursor(row=fila)
            await pilot.press("m")
        await pilot.press("y")
        await pilot.pause()
        assert app.screen.lado == "respuesta"

        await pilot.press("tab")
        await pilot.pause()
        assert app.screen.lado == "peticion"
        salida = app.screen.query_one("#cmp-salida", Static).render().plain
        assert "/uno" in salida and "/dos" in salida
