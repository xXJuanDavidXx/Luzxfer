"""Tests de las pestañas del repeater.

Pedido del usuario: el repeater funcionaba bien pero perdia el trabajo
al cerrarlo. Una peticion que has pasado veinte minutos afinando es
exactamente lo que no se puede perder.
"""
from __future__ import annotations

from luzxfer.core.models import Flow, Request, Response
from luzxfer.core.store import Store


def _flujo(url="http://o.com/api?q=1", metodo="GET"):
    return Flow(request=Request(method=metodo, url=url,
                                headers=[("Host", "o.com")]),
                response=Response(status=200, body=b"ok"))


# ----------------------------------------------------------- almacen
def test_se_guardan_y_se_recuperan(tmp_path):
    st = Store(tmp_path / "s.db")
    assert st.list_repeticiones() == []
    rid = st.add_repeticion("GET /api", "GET /api HTTP/1.1\r\n\r\n", tls=False)
    st.add_repeticion("POST /login", "POST /login HTTP/1.1\r\n\r\n", tls=True)

    r = st.list_repeticiones()
    assert [x["titulo"] for x in r] == ["GET /api", "POST /login"]
    assert r[0]["id"] == rid and r[1]["tls"] == 1
    st.close()


def test_editar_una_pestaña_la_guarda(tmp_path):
    st = Store(tmp_path / "s.db")
    rid = st.add_repeticion("t", "GET /viejo HTTP/1.1\r\n\r\n", tls=False)
    st.set_repeticion(rid, "GET /nuevo HTTP/1.1\r\n\r\n")
    assert st.list_repeticiones()[0]["crudo"] == "GET /nuevo HTTP/1.1\r\n\r\n"
    st.close()


def test_sobreviven_al_reinicio(tmp_path):
    """El punto entero del pedido."""
    ruta = tmp_path / "s.db"
    st = Store(ruta)
    st.add_repeticion("GET /api", "GET /api?q=' OR 1=1-- HTTP/1.1\r\n\r\n",
                      tls=True)
    st.close()
    otra = Store(ruta)
    r = otra.list_repeticiones()
    assert len(r) == 1 and "OR 1=1" in r[0]["crudo"] and r[0]["tls"] == 1
    otra.close()


def test_borrar_una_no_toca_las_otras(tmp_path):
    st = Store(tmp_path / "s.db")
    a = st.add_repeticion("a", "GET /a HTTP/1.1\r\n\r\n", tls=False)
    b = st.add_repeticion("b", "GET /b HTTP/1.1\r\n\r\n", tls=False)
    st.borrar_repeticion(a)
    assert [x["id"] for x in st.list_repeticiones()] == [b]
    st.close()


# ---------------------------------------------------------- pantalla
async def _abrir(app, pilot, flujo=None):
    from textual.widgets import DataTable
    app._ingresar(flujo or _flujo())
    await pilot.pause()
    app.query_one("#flujos", DataTable).move_cursor(row=0)
    await pilot.pause()
    await pilot.press("r")
    await pilot.pause()


async def test_la_tecla_r_abre_una_pestaña_con_la_peticion():

    from luzxfer.tui.app import LuzxferApp
    from luzxfer.tui.screens.repeater import RepeaterScreen
    app = LuzxferApp(arrancar_motor=False)
    async with app.run_test(size=(120, 36)) as pilot:
        await _abrir(app, pilot)
        assert isinstance(app.screen, RepeaterScreen)
        assert "GET /api?q=1" in app.screen.editor_actual().text


async def test_abrir_otro_flujo_anade_otra_pestaña(tmp_path):
    from luzxfer.tui.app import LuzxferApp
    app = LuzxferApp(db=str(tmp_path / "s.db"), arrancar_motor=False)
    async with app.run_test(size=(120, 36)) as pilot:
        await _abrir(app, pilot, _flujo("http://o.com/uno"))
        await pilot.press("escape")
        await pilot.pause()
        await _abrir(app, pilot, _flujo("http://o.com/dos"))
        assert len(app.store.list_repeticiones()) == 2
        assert len(app.screen.pestanas()) == 2


async def test_las_pestañas_vuelven_al_reabrir(tmp_path):
    """Cierras el repeater, sigues navegando, vuelves: tu trabajo sigue."""
    from luzxfer.tui.app import LuzxferApp
    ruta = str(tmp_path / "s.db")
    app = LuzxferApp(db=ruta, arrancar_motor=False)
    async with app.run_test(size=(120, 36)) as pilot:
        await _abrir(app, pilot)
        app.screen.editor_actual().text = "GET /afinado HTTP/1.1\r\nHost: o.com\r\n\r\n"
        await pilot.press("escape")
        await pilot.pause()

    otra = LuzxferApp(db=ruta, arrancar_motor=False)
    async with otra.run_test(size=(120, 36)) as pilot:
        await _abrir(otra, pilot)
        textos = [e.text for e in otra.screen.editores()]
        assert any("/afinado" in t for t in textos), \
            "la peticion afinada tiene que seguir ahi al dia siguiente"


async def test_ctrl_w_cierra_la_pestaña_y_la_borra(tmp_path):
    from luzxfer.tui.app import LuzxferApp
    app = LuzxferApp(db=str(tmp_path / "s.db"), arrancar_motor=False)
    async with app.run_test(size=(120, 36)) as pilot:
        await _abrir(app, pilot, _flujo("http://o.com/uno"))
        await pilot.press("escape")
        await pilot.pause()
        await _abrir(app, pilot, _flujo("http://o.com/dos"))
        assert len(app.store.list_repeticiones()) == 2

        await pilot.press("ctrl+w")
        await pilot.pause()
        assert len(app.store.list_repeticiones()) == 1


async def test_cerrar_la_ultima_pestaña_cierra_la_pantalla(tmp_path):
    from luzxfer.tui.app import LuzxferApp
    from luzxfer.tui.screens.repeater import RepeaterScreen
    app = LuzxferApp(db=str(tmp_path / "s.db"), arrancar_motor=False)
    async with app.run_test(size=(120, 36)) as pilot:
        await _abrir(app, pilot)
        await pilot.press("ctrl+w")
        await pilot.pause()
        assert not isinstance(app.screen, RepeaterScreen)


async def test_enviar_de_verdad_desde_una_pestaña(eco):

    from luzxfer.tui.app import LuzxferApp
    h, p = eco
    app = LuzxferApp(arrancar_motor=False)
    async with app.run_test(size=(120, 36)) as pilot:
        await _abrir(app, pilot, _flujo(f"http://{h}:{p}/eco?q=desdepestaña"))
        app.screen.editor_actual().text = (
            f"GET /eco?q=desdepestaña HTTP/1.1\r\nHost: {h}:{p}\r\n\r\n")
        await pilot.press("ctrl+s")
        for _ in range(60):
            await pilot.pause(0.1)
            if "200" in app.screen.salida_actual().render().plain:
                break
        assert "200" in app.screen.salida_actual().render().plain


async def test_ctrl_r_alterna_seguir_redirecciones(eco):

    from luzxfer.tui.app import LuzxferApp
    h, p = eco
    app = LuzxferApp(arrancar_motor=False)
    async with app.run_test(size=(120, 36)) as pilot:
        await _abrir(app, pilot, _flujo(f"http://{h}:{p}/salta?n=2"))
        assert app.screen.seguir == 0
        await pilot.press("ctrl+r")
        await pilot.pause()
        assert app.screen.seguir > 0

        app.screen.editor_actual().text = (
            f"GET /salta?n=2 HTTP/1.1\r\nHost: {h}:{p}\r\n\r\n")
        await pilot.press("ctrl+s")
        for _ in range(60):
            await pilot.pause(0.1)
            if "200" in app.screen.salida_actual().render().plain:
                break
        salida = app.screen.salida_actual().render().plain
        assert "200" in salida and "salta" in salida, \
            "tiene que decir por donde paso"
