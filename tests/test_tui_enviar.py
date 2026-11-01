"""Tests de separar «abrir» de «enviar» en Repeater e Intruder.

El reproche del usuario: pulsar `r` abria el repeater metiendo dentro la
peticion del historial que estuviera marcada en ese momento. Abrir una
herramienta y mandarle trabajo son dos cosas distintas, y mezclarlas hace
que no se pueda abrir el banco de trabajo sin ensuciarlo.

Ahora `r` abre el banco tal como esta y `R` manda la peticion
seleccionada a una pestaña nueva. El Intruder, que ataca una sola
peticion y no tiene banco, abre con `i` directamente sobre la marcada.
"""
from __future__ import annotations

from textual.widgets import DataTable

from luzxfer.core.models import Flow, Request, Response
from luzxfer.tui.app import LuzxferApp
from luzxfer.tui.screens.intruder import IntruderScreen
from luzxfer.tui.screens.repeater import RepeaterScreen


def _flujo(url: str = "http://o.com/x") -> Flow:
    return Flow(request=Request(method="GET", url=url,
                                headers=[("Host", "o.com")]),
                response=Response(status=200, body=b"ok"))


async def _con_flujo_marcado(pilot, app):
    app._ingresar(_flujo())
    await pilot.pause()
    app.query_one("#flujos", DataTable).move_cursor(row=0)
    await pilot.pause()


async def test_r_abre_el_repeater_sin_anadir_pestana():
    """Abrir no es enviar: el banco aparece como estaba."""
    app = LuzxferApp(arrancar_motor=False)
    async with app.run_test(size=(140, 44)) as pilot:
        await _con_flujo_marcado(pilot, app)
        await pilot.press("r")
        await pilot.pause()
        assert isinstance(app.screen, RepeaterScreen)
        assert len(app.screen.pestanas()) == 0, \
            "abrir el repeater no debe meter el flujo marcado"


async def test_R_manda_el_flujo_marcado_al_repeater():
    app = LuzxferApp(arrancar_motor=False)
    async with app.run_test(size=(140, 44)) as pilot:
        await _con_flujo_marcado(pilot, app)
        await pilot.press("R")
        await pilot.pause()
        assert isinstance(app.screen, RepeaterScreen)
        assert len(app.screen.pestanas()) == 1, \
            "R tiene que crear la pestaña con la peticion"


async def test_R_sin_seleccion_avisa_y_no_abre():
    """Sin fila marcada no puede haber traceback."""
    app = LuzxferApp(arrancar_motor=False)
    async with app.run_test(size=(140, 44)) as pilot:
        await pilot.pause()
        await pilot.press("R")
        await pilot.pause()
        assert not isinstance(app.screen, RepeaterScreen)


async def test_i_abre_el_intruder_sobre_el_flujo_marcado():
    app = LuzxferApp(arrancar_motor=False)
    async with app.run_test(size=(140, 44)) as pilot:
        await _con_flujo_marcado(pilot, app)
        await pilot.press("i")
        await pilot.pause()
        assert isinstance(app.screen, IntruderScreen)


async def test_i_sin_seleccion_avisa_y_no_abre():
    app = LuzxferApp(arrancar_motor=False)
    async with app.run_test(size=(140, 44)) as pilot:
        await pilot.pause()
        await pilot.press("i")
        await pilot.pause()
        assert not isinstance(app.screen, IntruderScreen)
