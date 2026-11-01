"""Tests de formatear el cuerpo JSON en el editor del repeater.

Leer un cuerpo JSON todo en una linea es incomodo justo cuando estas
buscando donde meter un payload. Lo que no puede pasar es que la
herramienta estropee lo que escribiste: si el cuerpo no es JSON valido o
no se declara JSON, el editor se queda como estaba y se dice por que.
"""
from __future__ import annotations

from textual.widgets import Button, DataTable

from luzxfer.core.models import Flow, Request, Response
from luzxfer.tui.app import LuzxferApp
from luzxfer.tui.screens.repeater import RepeaterScreen


async def _repeater_con(pilot, app, *, body: bytes, ctype: str):
    app._ingresar(Flow(
        request=Request(method="POST", url="http://o.com/x",
                        headers=[("Host", "o.com"), ("Content-Type", ctype)],
                        body=body),
        response=Response(status=200, body=b"ok")))
    await pilot.pause()
    app.query_one("#flujos", DataTable).move_cursor(row=0)
    await pilot.pause()
    await pilot.press("R")          # R manda la peticion al repeater
    await pilot.pause()
    assert isinstance(app.screen, RepeaterScreen)
    return app.screen


async def test_formatear_reorganiza_el_editor_actual():
    app = LuzxferApp(arrancar_motor=False)
    async with app.run_test(size=(140, 44)) as pilot:
        pant = await _repeater_con(pilot, app, body=b'{"a":1,"b":2}',
                                   ctype="application/json")
        assert '"a": 1' not in pant.editor_actual().text, "parte compacto"
        await pilot.press("ctrl+f")
        await pilot.pause()
        texto = pant.editor_actual().text
        assert '"a": 1' in texto and '"b": 2' in texto
        assert texto.startswith("POST /x HTTP/1.1"), "las cabeceras intactas"


async def test_formatear_json_invalido_no_vacia_el_editor():
    app = LuzxferApp(arrancar_motor=False)
    async with app.run_test(size=(140, 44)) as pilot:
        pant = await _repeater_con(pilot, app, body=b"{roto",
                                   ctype="application/json")
        antes = pant.editor_actual().text
        await pilot.press("ctrl+f")
        await pilot.pause()
        assert pant.editor_actual().text == antes, \
            "si no es JSON valido no se toca nada"


async def test_formatear_un_cuerpo_que_no_es_json_no_lo_toca():
    app = LuzxferApp(arrancar_motor=False)
    async with app.run_test(size=(140, 44)) as pilot:
        pant = await _repeater_con(pilot, app, body=b'{"a":1}',
                                   ctype="text/plain")
        antes = pant.editor_actual().text
        await pilot.press("ctrl+f")
        await pilot.pause()
        assert pant.editor_actual().text == antes


async def test_hay_boton_de_formatear_y_hace_lo_mismo():
    """El usuario pidio botones ademas de los atajos."""
    app = LuzxferApp(arrancar_motor=False)
    async with app.run_test(size=(140, 44)) as pilot:
        pant = await _repeater_con(pilot, app, body=b'{"a":1,"b":2}',
                                   ctype="application/json")
        boton = pant.query_one("#rep-formatear", Button)
        await pilot.click(boton)
        await pilot.pause()
        assert '"a": 1' in pant.editor_actual().text


async def test_la_pista_menciona_el_atajo():
    from textual.widgets import Static
    app = LuzxferApp(arrancar_motor=False)
    async with app.run_test(size=(140, 44)) as pilot:
        pant = await _repeater_con(pilot, app, body=b'{"a":1}',
                                   ctype="application/json")
        pista = pant.query_one("#rep-titulo", Static).render().plain
        assert "ctrl+f" in pista


async def test_la_barra_de_botones_cae_dentro_de_la_caja():
    """Los botones se dibujaban una fila por debajo del borde.

    El atajo seguia funcionando, asi que no se notaba en los tests: lo
    que no se podia era pulsarlos con el raton, que es justo para lo que
    estan. Sin acotar el alto de las pestañas, el TabbedContent crece con
    su contenido y empuja la barra fuera.
    """
    app = LuzxferApp(arrancar_motor=False)
    async with app.run_test(size=(140, 44)) as pilot:
        pant = await _repeater_con(pilot, app, body=b'{"a":1}',
                                   ctype="application/json")
        caja = pant.query_one("#rep-caja")
        for boton in pant.query(Button):
            assert boton.region.bottom <= caja.region.bottom, (
                f"el boton '{boton.id}' se sale de la caja: "
                f"{boton.region} fuera de {caja.region}")
