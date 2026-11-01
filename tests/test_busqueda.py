"""Tests de la busqueda en todo el trafico.

«¿Donde aparece este token?» es de las preguntas mas frecuentes en un
pentest, y el filtro solo miraba la URL. La trampa esta en los cuerpos
comprimidos: buscar con SQL sobre el BLOB no encuentra nada dentro de un
gzip, y no encontrarlo EN SILENCIO es el fallo que este proyecto lleva
toda la vida persiguiendo.
"""
from __future__ import annotations

import gzip

from luzxfer.core.models import Flow, Request, Response
from luzxfer.core.store import Store


def _f(url="http://o.com/x", cuerpo=b"", cab_resp=(), cuerpo_pet=b"",
       cab_pet=()):
    return Flow(
        request=Request(method="GET", url=url,
                        headers=[("Host", "o.com"), *cab_pet],
                        body=cuerpo_pet),
        response=Response(status=200, body=cuerpo,
                          headers=[("Content-Type", "text/html"), *cab_resp]),
    )


def test_encuentra_en_la_url():
    st = Store()
    st.add_flow(_f("http://o.com/buscar?q=AGUJA"))
    st.add_flow(_f("http://o.com/otra"))
    assert [f.request.path for f in st.buscar("AGUJA")] == ["/buscar?q=AGUJA"]
    st.close()


def test_encuentra_en_el_cuerpo_de_la_respuesta():
    st = Store()
    st.add_flow(_f(cuerpo=b"<html>token=AGUJA</html>"))
    st.add_flow(_f(cuerpo=b"<html>nada</html>"))
    assert len(st.buscar("AGUJA")) == 1
    st.close()


def test_encuentra_dentro_de_un_cuerpo_COMPRIMIDO():
    """La razon de que esto no se pueda hacer con un LIKE de SQL: el
    BLOB guardado son bytes gzip y la aguja no esta ahi en claro."""
    st = Store()
    st.add_flow(_f(cuerpo=gzip.compress(b"<html>token=AGUJA</html>"),
                   cab_resp=[("Content-Encoding", "gzip")]))
    assert len(st.buscar("AGUJA")) == 1
    st.close()


def test_encuentra_en_las_cabeceras():
    st = Store()
    st.add_flow(_f(cab_resp=[("X-Pista", "AGUJA")]))
    st.add_flow(_f(cab_pet=[("Authorization", "Bearer AGUJA")]))
    st.add_flow(_f())
    assert len(st.buscar("AGUJA")) == 2
    st.close()


def test_encuentra_en_el_cuerpo_de_la_peticion():
    st = Store()
    st.add_flow(_f(cuerpo_pet=b'{"clave":"AGUJA"}'))
    assert len(st.buscar("AGUJA")) == 1
    st.close()


def test_no_distingue_mayusculas():
    st = Store()
    st.add_flow(_f(cuerpo=b"<html>AgUjA</html>"))
    assert len(st.buscar("aguja")) == 1
    st.close()


def test_buscar_nada_no_devuelve_todo():
    """Una busqueda vacia que devolviera el historial entero haria
    pensar que todo coincide."""
    st = Store()
    st.add_flow(_f())
    assert st.buscar("") == []
    assert st.buscar("   ") == []
    st.close()


def test_el_limite_se_respeta_y_se_puede_saber_si_sobro():
    st = Store()
    for _ in range(30):
        st.add_flow(_f(cuerpo=b"AGUJA"))
    assert len(st.buscar("AGUJA", limite=10)) == 10
    assert st.contar_busqueda("AGUJA") == 30
    st.close()


def test_un_cuerpo_binario_no_rompe_la_busqueda():
    st = Store()
    st.add_flow(_f(cuerpo=b"\x89PNG\x00\x01\x02\xff\xfe",
                   cab_resp=[("Content-Type", "image/png")]))
    st.add_flow(_f(cuerpo=b"AGUJA"))
    assert len(st.buscar("AGUJA")) == 1
    st.close()


def test_un_gzip_corrupto_no_rompe_la_busqueda():
    st = Store()
    st.add_flow(_f(cuerpo=b"esto no es gzip",
                   cab_resp=[("Content-Encoding", "gzip")]))
    st.add_flow(_f(cuerpo=b"AGUJA"))
    assert len(st.buscar("AGUJA")) == 1
    st.close()


def test_el_orden_es_el_del_historial():
    st = Store()
    for i in range(3):
        st.add_flow(_f(url=f"http://o.com/r{i}", cuerpo=b"AGUJA"))
    assert [f.request.path for f in st.buscar("AGUJA", ascendente=True)] == \
        ["/r0", "/r1", "/r2"]
    st.close()


# ------------------------------------------------------- en la interfaz
async def test_la_tecla_barra_busca_en_todo():
    from textual.widgets import DataTable, Input

    from luzxfer.tui.app import LuzxferApp
    app = LuzxferApp(arrancar_motor=False)
    async with app.run_test() as pilot:
        app._ingresar(_f("http://o.com/uno", cuerpo=b"<html>AGUJA</html>"))
        app._ingresar(_f("http://o.com/dos", cuerpo=b"<html>nada</html>"))
        await pilot.pause()
        assert app.query_one("#flujos", DataTable).row_count == 2

        await pilot.press("slash")
        await pilot.pause()
        assert app.busqueda_profunda is True
        app.query_one("#filtro", Input).value = "AGUJA"
        await pilot.pause()
        assert app.query_one("#flujos", DataTable).row_count == 1


async def test_la_f_vuelve_a_filtrar_solo_por_url():
    from textual.widgets import DataTable, Input

    from luzxfer.tui.app import LuzxferApp
    app = LuzxferApp(arrancar_motor=False)
    async with app.run_test() as pilot:
        app._ingresar(_f("http://o.com/uno", cuerpo=b"<html>AGUJA</html>"))
        await pilot.pause()
        await pilot.press("slash")
        app.query_one("#filtro", Input).value = "AGUJA"
        await pilot.pause()
        assert app.query_one("#flujos", DataTable).row_count == 1

        await pilot.press("escape")
        await pilot.press("f")
        await pilot.pause()
        assert app.busqueda_profunda is False
        # la misma aguja ya no esta en ninguna URL
        assert app.query_one("#flujos", DataTable).row_count == 0


async def test_la_barra_dice_que_se_esta_buscando_en_todo():
    from textual.widgets import Input, Static

    from luzxfer.tui.app import LuzxferApp
    app = LuzxferApp(arrancar_motor=False)
    async with app.run_test() as pilot:
        app._ingresar(_f(cuerpo=b"AGUJA"))
        await pilot.pause()
        await pilot.press("slash")
        app.query_one("#filtro", Input).value = "AGUJA"
        await pilot.pause()
        barra = app.query_one("#estado", Static).render().plain
        assert "buscando" in barra.lower()
