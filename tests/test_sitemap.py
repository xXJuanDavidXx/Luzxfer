"""Tests del mapa del sitio.

El historial dice en que orden pasaron las cosas; el mapa dice que forma
tiene la aplicacion. Son dos preguntas distintas y por eso hay dos
vistas: mirando una lista de 3000 peticiones no se ve que hay un
/admin/ con tres rutas dentro.
"""
from __future__ import annotations

from luzxfer.core.models import Flow, Request, Response
from luzxfer.core.tools import sitemap


def _f(url, status=200, metodo="GET", fid=None):
    from urllib.parse import urlsplit
    f = Flow(request=Request(method=metodo, url=url,
                             headers=[("Host", urlsplit(url).netloc)]),
             response=Response(status=status) if status else None)
    f.id = fid
    return f


def test_sin_flujos_el_mapa_esta_vacio():
    assert sitemap.construir([]) == []


def test_agrupa_por_host():
    raiz = sitemap.construir([
        _f("http://uno.com/a"), _f("http://dos.com/b"), _f("http://uno.com/c")])
    assert [n.nombre for n in raiz] == ["dos.com", "uno.com"]   # alfabetico
    assert {n.nombre: n.total for n in raiz} == {"uno.com": 2, "dos.com": 1}


def test_parte_la_ruta_en_segmentos():
    raiz = sitemap.construir([_f("http://o.com/api/v1/users")])
    host = raiz[0]
    api = host.hijos[0]
    assert api.nombre == "api"
    assert api.hijos[0].nombre == "v1"
    assert api.hijos[0].hijos[0].nombre == "users"


def test_el_total_cuenta_todo_el_subarbol():
    raiz = sitemap.construir([
        _f("http://o.com/api/v1/users"),
        _f("http://o.com/api/v1/login"),
        _f("http://o.com/publico"),
    ])
    host = raiz[0]
    assert host.total == 3
    api = next(n for n in host.hijos if n.nombre == "api")
    assert api.total == 2


def test_la_raiz_tiene_su_propio_nodo():
    raiz = sitemap.construir([_f("http://o.com/"), _f("http://o.com/x")])
    host = raiz[0]
    assert "/" in [n.nombre for n in host.hijos]
    assert host.total == 2


def test_la_query_no_crea_ramas_pero_si_cuenta():
    """Tres busquedas distintas son tres peticiones a UNA ruta. Si cada
    query fuera una rama, el arbol tendria el mismo tamanio que el
    historial y no serviria de nada."""
    raiz = sitemap.construir([
        _f("http://o.com/buscar?q=uno"),
        _f("http://o.com/buscar?q=dos"),
        _f("http://o.com/buscar?q=tres"),
    ])
    buscar = raiz[0].hijos[0]
    assert buscar.nombre == "buscar"
    assert buscar.hijos == []
    assert buscar.total == 3
    assert buscar.pedido == 3


def test_recoge_los_codigos_y_los_metodos_vistos():
    raiz = sitemap.construir([
        _f("http://o.com/api/x", status=200),
        _f("http://o.com/api/x", status=401, metodo="POST"),
    ])
    x = raiz[0].hijos[0].hijos[0]
    assert x.estados == {200, 401}
    assert x.metodos == {"GET", "POST"}


def test_guarda_los_ids_de_los_flujos_para_poder_volver():
    raiz = sitemap.construir([_f("http://o.com/x", fid=7),
                              _f("http://o.com/x", fid=9)])
    assert raiz[0].hijos[0].flujos == [7, 9]


def test_un_flujo_sin_respuesta_cuenta_igual():
    """Un error de red tambien dice algo sobre la aplicacion."""
    raiz = sitemap.construir([_f("http://o.com/x", status=None)])
    assert raiz[0].total == 1
    assert raiz[0].hijos[0].estados == set()


def test_los_hijos_salen_ordenados():
    raiz = sitemap.construir([_f("http://o.com/zeta"), _f("http://o.com/alfa"),
                              _f("http://o.com/media")])
    assert [n.nombre for n in raiz[0].hijos] == ["alfa", "media", "zeta"]


def test_la_ruta_completa_de_cada_nodo():
    """Hace falta para poder abrir el repeater desde el arbol."""
    raiz = sitemap.construir([_f("http://o.com/api/v1/users")])
    users = raiz[0].hijos[0].hijos[0].hijos[0]
    assert users.ruta == "/api/v1/users"
    assert raiz[0].ruta == ""


def test_una_url_rara_no_tumba_el_mapa():
    raiz = sitemap.construir([_f("http://o.com/bien"), _f("no-es-una-url")])
    assert [n.nombre for n in raiz] == ["o.com"]


def test_las_barras_repetidas_no_crean_nodos_vacios():
    raiz = sitemap.construir([_f("http://o.com//api//x/")])
    api = raiz[0].hijos[0]
    assert api.nombre == "api"
    assert api.hijos[0].nombre == "x"


def test_contar_hojas_dice_cuantas_rutas_distintas_hay():
    raiz = sitemap.construir([
        _f("http://o.com/a"), _f("http://o.com/a"), _f("http://o.com/b/c")])
    assert sitemap.contar_rutas(raiz) == 2


# ------------------------------------------------- la pantalla (tecla e)
async def _app_con(urls, **kw):
    from luzxfer.tui.app import LuzxferApp
    app = LuzxferApp(arrancar_motor=False, **kw)
    return app


async def test_la_tecla_e_abre_el_mapa():
    from luzxfer.tui.screens.sitemap import SitemapScreen
    app = await _app_con([])
    async with app.run_test(size=(120, 36)) as pilot:
        app._ingresar(_f("http://o.com/x"))
        await pilot.pause()
        await pilot.press("e")
        await pilot.pause()
        assert isinstance(app.screen, SitemapScreen)


async def test_el_arbol_muestra_hosts_y_rutas():
    from textual.widgets import Tree
    app = await _app_con([])
    async with app.run_test(size=(120, 36)) as pilot:
        for u in ("http://o.com/api/v1/users", "http://o.com/api/v1/login",
                  "http://otro.net/"):
            app._ingresar(_f(u))
        await pilot.pause()
        await pilot.press("e")
        await pilot.pause()
        arbol = app.screen.query_one("#mapa", Tree)
        hosts = [str(n.label) for n in arbol.root.children]
        assert any("o.com" in h for h in hosts)
        assert any("otro.net" in h for h in hosts)


async def test_el_mapa_respeta_el_alcance_si_esta_filtrando():
    from textual.widgets import Tree
    app = await _app_con([])
    async with app.run_test(size=(120, 36)) as pilot:
        app._ingresar(_f("http://objetivo.com/a"))
        app._ingresar(_f("http://cdn.ajeno.net/b"))
        await pilot.pause()
        app.poner_alcance("+objetivo.com")
        app.poner_solo_alcance(True)
        await pilot.pause()
        await pilot.press("e")
        await pilot.pause()
        hosts = [str(n.label) for n in app.screen.query_one("#mapa", Tree).root.children]
        assert len(hosts) == 1 and "objetivo.com" in hosts[0]


async def test_el_titulo_dice_cuantas_rutas_distintas_hay():
    from textual.widgets import Static
    app = await _app_con([])
    async with app.run_test(size=(120, 36)) as pilot:
        for u in ("http://o.com/a", "http://o.com/a", "http://o.com/b"):
            app._ingresar(_f(u))
        await pilot.pause()
        await pilot.press("e")
        await pilot.pause()
        titulo = app.screen.query_one("#mapa-titulo", Static).render().plain
        assert "2 rutas" in titulo and "3 " in titulo


async def test_elegir_una_ruta_lleva_a_su_flujo_en_el_historial():
    """El gesto que hace util el mapa: ves la forma, eliges una rama y
    caes en el trafico que la produjo."""
    from textual.widgets import DataTable, Tree
    app = await _app_con([])
    async with app.run_test(size=(120, 36)) as pilot:
        app._ingresar(_f("http://o.com/primero"))
        app._ingresar(_f("http://o.com/segundo"))
        await pilot.pause()
        app.query_one("#flujos", DataTable).move_cursor(row=0)
        await pilot.pause()
        buscado = app.store.list_flows(texto="/segundo")[0].id

        await pilot.press("e")
        await pilot.pause()
        arbol = app.screen.query_one("#mapa", Tree)
        host = arbol.root.children[0]
        nodo = next(n for n in host.children if "segundo" in str(n.label))
        arbol.select_node(nodo)
        await pilot.pause()
        app.screen.action_abrir()
        await pilot.pause()

        assert app._flujo_actual is not None
        assert app._flujo_actual.id == buscado


async def test_un_tramo_nunca_pedido_se_distingue():
    """/api existe porque se pidio /api/v1/users, pero nadie pidio /api.
    Esa diferencia es justo lo que vale la pena probar a mano."""
    from textual.widgets import Tree
    app = await _app_con([])
    async with app.run_test(size=(120, 36)) as pilot:
        app._ingresar(_f("http://o.com/api/v1/users"))
        await pilot.pause()
        await pilot.press("e")
        await pilot.pause()
        arbol = app.screen.query_one("#mapa", Tree)
        api = arbol.root.children[0].children[0]
        assert "api" in str(api.label)
        assert "no pedido" in str(api.label)


async def test_el_mapa_vacio_lo_dice():
    from textual.widgets import Static
    app = await _app_con([])
    async with app.run_test(size=(120, 36)) as pilot:
        await pilot.pause()
        await pilot.press("e")
        await pilot.pause()
        assert "0 rutas" in app.screen.query_one("#mapa-titulo", Static).render().plain


async def test_el_contador_de_una_ruta_cuenta_esa_ruta_y_no_el_subarbol():
    """Mirando la salida real: «users 200 ×2» hacia pensar que /users se
    pidio dos veces, cuando se pidio UNA y la otra era /users/7. El mismo
    simbolo significando dos cosas segun la fila es peor que no ponerlo."""
    from textual.widgets import Tree
    app = await _app_con([])
    async with app.run_test(size=(120, 36)) as pilot:
        app._ingresar(_f("http://o.com/users"))
        app._ingresar(_f("http://o.com/users/7"))
        app._ingresar(_f("http://o.com/login"))
        app._ingresar(_f("http://o.com/login"))
        await pilot.pause()
        await pilot.press("e")
        await pilot.pause()
        host = app.screen.query_one("#mapa", Tree).root.children[0]
        etiquetas = {str(n.label).split()[0]: str(n.label) for n in host.children}

        assert "×" not in etiquetas["users"], "se pidio una vez: sin contador"
        assert "×2" in etiquetas["login"], "esa si se pidio dos veces"


async def test_un_tramo_no_pedido_si_dice_cuantas_hay_debajo():
    """Ahi el numero no es ambiguo: el tramo no se pidio, asi que todo lo
    que cuenta viene de abajo, y saber cuanto hay dice si vale la pena
    desplegarlo."""
    from textual.widgets import Tree
    app = await _app_con([])
    async with app.run_test(size=(120, 36)) as pilot:
        for i in range(3):
            app._ingresar(_f(f"http://o.com/api/r{i}"))
        await pilot.pause()
        await pilot.press("e")
        await pilot.pause()
        api = app.screen.query_one("#mapa", Tree).root.children[0].children[0]
        assert "no pedido" in str(api.label) and "×3" in str(api.label)
