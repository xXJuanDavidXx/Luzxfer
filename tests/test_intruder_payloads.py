"""Tests de cargar payloads desde la interfaz del Intruder.

La logica de `desde_archivo` y `desde_rango` ya esta probada en el core;
aqui se prueba que la interfaz llega a ella y que los errores de teclear
una ruta o un rango no tumban la pantalla, porque equivocarse al escribir
una ruta es lo normal.
"""
from __future__ import annotations

from textual.widgets import Button, DataTable, Input, TextArea

from luzxfer.core.models import Flow, Request, Response
from luzxfer.tui.app import LuzxferApp
from luzxfer.tui.screens.intruder import IntruderScreen
from luzxfer.tui.screens.intruder_payloads import CargarPayloadsScreen


def _flujo() -> Flow:
    return Flow(request=Request(method="GET", url="http://o.com/x?q=1",
                                headers=[("Host", "o.com")]),
                response=Response(status=200, body=b"ok"))


async def _abrir_cargador(pilot, app):
    app._ingresar(_flujo())
    await pilot.pause()
    app.query_one("#flujos", DataTable).move_cursor(row=0)
    await pilot.pause()
    await pilot.press("i")
    await pilot.pause()
    pant = app.screen
    assert isinstance(pant, IntruderScreen)
    await pilot.press("ctrl+y")
    await pilot.pause()
    assert isinstance(app.screen, CargarPayloadsScreen)
    return pant


async def test_cargar_un_rango_numerico_llena_los_payloads():
    app = LuzxferApp(arrancar_motor=False)
    async with app.run_test(size=(140, 44)) as pilot:
        pant = await _abrir_cargador(pilot, app)
        app.screen.query_one("#pay-desde", Input).value = "1"
        app.screen.query_one("#pay-hasta", Input).value = "5"
        await pilot.click(app.screen.query_one("#pay-rango", Button))
        await pilot.pause()
        assert isinstance(app.screen, IntruderScreen)
        texto = pant.query_one("#int-payloads", TextArea).text
        assert texto.split() == ["1", "2", "3", "4", "5"]


async def test_un_rango_con_ceros_a_la_izquierda():
    app = LuzxferApp(arrancar_motor=False)
    async with app.run_test(size=(140, 44)) as pilot:
        pant = await _abrir_cargador(pilot, app)
        app.screen.query_one("#pay-desde", Input).value = "1"
        app.screen.query_one("#pay-hasta", Input).value = "3"
        app.screen.query_one("#pay-ancho", Input).value = "3"
        await pilot.click(app.screen.query_one("#pay-rango", Button))
        await pilot.pause()
        assert pant.query_one("#int-payloads", TextArea).text.split() == \
            ["001", "002", "003"]


async def test_cargar_un_diccionario_desde_archivo(tmp_path):
    d = tmp_path / "dicc.txt"
    d.write_text("admin\nroot\n# comentario\n\nguest\n", encoding="utf-8")
    app = LuzxferApp(arrancar_motor=False)
    async with app.run_test(size=(140, 44)) as pilot:
        pant = await _abrir_cargador(pilot, app)
        app.screen.query_one("#pay-ruta", Input).value = str(d)
        await pilot.click(app.screen.query_one("#pay-archivo", Button))
        await pilot.pause()
        assert isinstance(app.screen, IntruderScreen)
        # las lineas vacias y las de # no entran
        assert pant.query_one("#int-payloads", TextArea).text.split() == \
            ["admin", "root", "guest"]


async def test_cargar_no_pisa_lo_que_ya_habia():
    app = LuzxferApp(arrancar_motor=False)
    async with app.run_test(size=(140, 44)) as pilot:
        pant = await _abrir_cargador(pilot, app)
        pant.query_one("#int-payloads", TextArea).text = "ya-estaba"
        app.screen.query_one("#pay-desde", Input).value = "1"
        app.screen.query_one("#pay-hasta", Input).value = "2"
        await pilot.click(app.screen.query_one("#pay-rango", Button))
        await pilot.pause()
        texto = pant.query_one("#int-payloads", TextArea).text
        assert "ya-estaba" in texto and "1" in texto and "2" in texto


async def test_un_rango_al_reves_avisa_y_no_cierra():
    app = LuzxferApp(arrancar_motor=False)
    async with app.run_test(size=(140, 44)) as pilot:
        await _abrir_cargador(pilot, app)
        app.screen.query_one("#pay-desde", Input).value = "9"
        app.screen.query_one("#pay-hasta", Input).value = "1"
        await pilot.click(app.screen.query_one("#pay-rango", Button))
        await pilot.pause()
        # sigue en el cargador, con un aviso, no en el intruder
        assert isinstance(app.screen, CargarPayloadsScreen)
        from textual.widgets import Static
        aviso = app.screen.query_one("#pay-aviso", Static).render().plain
        assert aviso.strip()


async def test_un_rango_no_numerico_avisa():
    app = LuzxferApp(arrancar_motor=False)
    async with app.run_test(size=(140, 44)) as pilot:
        await _abrir_cargador(pilot, app)
        app.screen.query_one("#pay-desde", Input).value = "x"
        app.screen.query_one("#pay-hasta", Input).value = "5"
        await pilot.click(app.screen.query_one("#pay-rango", Button))
        await pilot.pause()
        assert isinstance(app.screen, CargarPayloadsScreen)


async def test_un_archivo_inexistente_avisa_y_no_cierra():
    app = LuzxferApp(arrancar_motor=False)
    async with app.run_test(size=(140, 44)) as pilot:
        await _abrir_cargador(pilot, app)
        app.screen.query_one("#pay-ruta", Input).value = "/no/existe/nunca.txt"
        await pilot.click(app.screen.query_one("#pay-archivo", Button))
        await pilot.pause()
        assert isinstance(app.screen, CargarPayloadsScreen)


async def test_cancelar_no_toca_los_payloads():
    app = LuzxferApp(arrancar_motor=False)
    async with app.run_test(size=(140, 44)) as pilot:
        pant = await _abrir_cargador(pilot, app)
        pant.query_one("#int-payloads", TextArea).text = "intacto"
        await pilot.press("escape")
        await pilot.pause()
        assert isinstance(app.screen, IntruderScreen)
        assert pant.query_one("#int-payloads", TextArea).text == "intacto"


async def test_los_botones_del_cargador_caen_dentro_de_la_caja():
    """La fila del rango (cuatro campos + boton) desbordaba a lo ancho y
    empujaba el boton fuera: el raton no podia alcanzarlo."""
    app = LuzxferApp(arrancar_motor=False)
    async with app.run_test(size=(140, 44)) as pilot:
        await _abrir_cargador(pilot, app)
        caja = app.screen.query_one("#pay-caja")
        for boton in app.screen.query(Button):
            assert boton.region.right <= caja.region.right, \
                f"el boton '{boton.id}' se sale por la derecha"
