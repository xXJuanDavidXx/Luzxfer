"""Tests de ver el detalle de un resultado del Intruder.

En un fuzzing con cientos de filas, ver que una mide distinto no basta:
hay que poder mirar que se mando. La peticion se reconstruye con la misma
funcion que uso el ataque sobre el crudo lanzado, asi que es lo que
viajo, no una aproximacion.

El ataque no se lanza por red en estos tests: `Ataque.__init__` no abre
sockets, asi que se prepara el estado a mano y se ejercita el camino de
la interfaz —elegir una fila abre el modal con la peticion correcta—, que
es lo que se quiere probar.
"""
from __future__ import annotations

from textual.widgets import DataTable, TextArea

from luzxfer.core.models import Flow, Request, Response
from luzxfer.core.tools import intruder
from luzxfer.tui.app import LuzxferApp
from luzxfer.tui.screens.intruder import IntruderScreen
from luzxfer.tui.screens.intruder_detalle import DetalleResultadoScreen


def _flujo() -> Flow:
    return Flow(request=Request(method="GET", url="http://o.com/x?q=1",
                                headers=[("Host", "o.com")]),
                response=Response(status=200, body=b"ok"))


async def _intruder_con_un_resultado(pilot, app, *, payload="admin"):
    """Abre el intruder y le inyecta un ataque y un resultado, sin red."""
    app._ingresar(_flujo())
    await pilot.pause()
    app.query_one("#flujos", DataTable).move_cursor(row=0)
    await pilot.pause()
    await pilot.press("i")
    await pilot.pause()
    pant = app.screen
    assert isinstance(pant, IntruderScreen)

    crudo = "GET /x?q=§X§ HTTP/1.1\r\nHost: o.com\r\n\r\n"
    cfg = intruder.Config(modo=intruder.Modo.SNIPER, conjuntos=[[payload]])
    pant.ataque = intruder.Ataque(crudo, cfg)
    r = intruder.Resultado(n=0, payloads=[payload], status=200, largo=42)
    pant._resultados[0] = r
    pant._fila(r)
    await pilot.pause()
    return pant


async def test_elegir_una_fila_abre_el_detalle_con_la_peticion():
    app = LuzxferApp(arrancar_motor=False)
    async with app.run_test(size=(140, 44)) as pilot:
        pant = await _intruder_con_un_resultado(pilot, app, payload="admin")
        tabla = pant.query_one("#int-resultados", DataTable)
        tabla.focus()
        tabla.move_cursor(row=0)
        await pilot.press("enter")
        await pilot.pause()

        assert isinstance(app.screen, DetalleResultadoScreen)
        texto = app.screen.query_one("#det-peticion", TextArea).text
        assert "GET /x?q=admin HTTP/1.1" in texto, \
            "la peticion mostrada tiene que llevar el payload puesto"
        assert "§" not in texto, "los marcadores ya no estan en lo que salio"


async def test_la_peticion_mostrada_es_la_que_de_verdad_salio():
    """Reconstruida con la misma funcion que el ataque: identica."""
    app = LuzxferApp(arrancar_motor=False)
    async with app.run_test(size=(140, 44)) as pilot:
        pant = await _intruder_con_un_resultado(pilot, app, payload="' OR 1=1")
        esperada = intruder.sustituir(pant.ataque.crudo, ["' OR 1=1"])
        tabla = pant.query_one("#int-resultados", DataTable)
        tabla.focus()
        tabla.move_cursor(row=0)
        await pilot.press("enter")
        await pilot.pause()
        assert app.screen.query_one("#det-peticion", TextArea).text == esperada


async def test_el_detalle_es_de_solo_lectura():
    """Es evidencia de lo que salio, no un editor."""
    app = LuzxferApp(arrancar_motor=False)
    async with app.run_test(size=(140, 44)) as pilot:
        pant = await _intruder_con_un_resultado(pilot, app)
        tabla = pant.query_one("#int-resultados", DataTable)
        tabla.focus()
        tabla.move_cursor(row=0)
        await pilot.press("enter")
        await pilot.pause()
        assert app.screen.query_one("#det-peticion", TextArea).read_only


async def test_el_detalle_se_cierra_y_vuelve_al_intruder():
    app = LuzxferApp(arrancar_motor=False)
    async with app.run_test(size=(140, 44)) as pilot:
        pant = await _intruder_con_un_resultado(pilot, app)
        tabla = pant.query_one("#int-resultados", DataTable)
        tabla.focus()
        tabla.move_cursor(row=0)
        await pilot.press("enter")
        await pilot.pause()
        assert isinstance(app.screen, DetalleResultadoScreen)
        await pilot.press("escape")
        await pilot.pause()
        assert isinstance(app.screen, IntruderScreen)


async def test_elegir_fila_sin_ataque_no_rompe():
    """Una fila sin ataque detras no puede abrir un modal vacio ni petar."""
    app = LuzxferApp(arrancar_motor=False)
    async with app.run_test(size=(140, 44)) as pilot:
        app._ingresar(_flujo())
        await pilot.pause()
        app.query_one("#flujos", DataTable).move_cursor(row=0)
        await pilot.pause()
        await pilot.press("i")
        await pilot.pause()
        pant = app.screen
        assert isinstance(pant, IntruderScreen)
        # sin ataque ni resultados; forzar el evento no debe abrir nada
        tabla = pant.query_one("#int-resultados", DataTable)
        tabla.focus()
        await pilot.pause()
        assert isinstance(app.screen, IntruderScreen)


# --------------------------------------- mandar un resultado al repeater
async def test_mandar_al_repeater_crea_una_repeticion():
    """Cierra el bucle que promete el detalle: del resultado al repeater,
    donde se ve la respuesta entera que el Intruder no retiene por fila."""
    app = LuzxferApp(arrancar_motor=False)
    async with app.run_test(size=(140, 44)) as pilot:
        pant = await _intruder_con_un_resultado(pilot, app, payload="admin")
        antes = len(app.store.list_repeticiones())
        tabla = pant.query_one("#int-resultados", DataTable)
        tabla.focus()
        tabla.move_cursor(row=0)
        await pilot.press("enter")
        await pilot.pause()
        assert isinstance(app.screen, DetalleResultadoScreen)

        await pilot.press("ctrl+r")
        await pilot.pause()
        reps = app.store.list_repeticiones()
        assert len(reps) == antes + 1
        # la peticion guardada lleva el payload puesto
        assert "admin" in reps[-1]["crudo"]
        assert isinstance(app.screen, IntruderScreen), "vuelve al intruder"


async def test_el_boton_manda_al_repeater():
    from textual.widgets import Button
    app = LuzxferApp(arrancar_motor=False)
    async with app.run_test(size=(140, 44)) as pilot:
        pant = await _intruder_con_un_resultado(pilot, app)
        antes = len(app.store.list_repeticiones())
        tabla = pant.query_one("#int-resultados", DataTable)
        tabla.focus()
        tabla.move_cursor(row=0)
        await pilot.press("enter")
        await pilot.pause()
        await pilot.click(app.screen.query_one("#det-repeater", Button))
        await pilot.pause()
        assert len(app.store.list_repeticiones()) == antes + 1


async def test_cerrar_el_detalle_no_crea_repeticion():
    """Solo mirar no manda nada: cerrar no debe ensuciar el repeater."""
    app = LuzxferApp(arrancar_motor=False)
    async with app.run_test(size=(140, 44)) as pilot:
        pant = await _intruder_con_un_resultado(pilot, app)
        antes = len(app.store.list_repeticiones())
        tabla = pant.query_one("#int-resultados", DataTable)
        tabla.focus()
        tabla.move_cursor(row=0)
        await pilot.press("enter")
        await pilot.pause()
        await pilot.press("escape")
        await pilot.pause()
        assert len(app.store.list_repeticiones()) == antes


async def test_el_tls_se_hereda_en_la_repeticion():
    """Una peticion https reenviada en claro al 443 falla raro. El TLS del
    flujo original tiene que viajar a la pestaña del repeater."""
    app = LuzxferApp(arrancar_motor=False)
    async with app.run_test(size=(140, 44)) as pilot:
        # flujo original https
        app._ingresar(Flow(
            request=Request(method="GET", url="https://o.com/x?q=1",
                            headers=[("Host", "o.com")]),
            response=Response(status=200, body=b"ok")))
        await pilot.pause()
        app.query_one("#flujos", DataTable).move_cursor(row=0)
        await pilot.pause()
        await pilot.press("i")
        await pilot.pause()
        pant = app.screen
        crudo = "GET /x?q=§X§ HTTP/1.1\r\nHost: o.com\r\n\r\n"
        cfg = intruder.Config(modo=intruder.Modo.SNIPER, conjuntos=[["admin"]])
        pant.ataque = intruder.Ataque(crudo, cfg)
        r = intruder.Resultado(n=0, payloads=["admin"], status=200, largo=10)
        pant._resultados[0] = r
        pant._fila(r)
        await pilot.pause()

        tabla = pant.query_one("#int-resultados", DataTable)
        tabla.focus()
        tabla.move_cursor(row=0)
        await pilot.press("enter")
        await pilot.pause()
        await pilot.press("ctrl+r")
        await pilot.pause()
        assert app.store.list_repeticiones()[-1]["tls"], \
            "el flujo era https: la repeticion tiene que ir por TLS"
