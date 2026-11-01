"""Tests del alcance.

El alcance decide que esta dentro del contrato y que no. Se equivoca de
dos formas y las dos son caras: dejar fuera algo que si estaba dentro
—trabajo perdido— o dejar dentro algo ajeno, que en un pentest con
contrato es un problema legal, no un bug.

Por eso: excluir siempre gana, y sin reglas todo esta dentro.
"""
from __future__ import annotations

import pytest

from luzxfer.core.tools import alcance


def _a(*reglas):
    return alcance.Alcance([alcance.Regla.desde_texto(r) for r in reglas])


# --------------------------------------------------- sin reglas, todo entra
def test_sin_reglas_todo_esta_dentro():
    """Una sesion recien abierta no puede esconder el trafico."""
    vacio = alcance.Alcance([])
    assert vacio.dentro("http://cualquiera.com/x")
    assert vacio.dentro("https://otro.org/")
    assert not vacio.configurado


# ------------------------------------------------------------- incluir
def test_un_host_exacto():
    a = _a("+objetivo.com")
    assert a.dentro("http://objetivo.com/x")
    assert a.dentro("https://objetivo.com/otra/ruta?q=1")
    assert not a.dentro("http://otro.com/x")
    assert a.configurado


def test_un_comodin_cubre_los_subdominios():
    a = _a("+*.objetivo.com")
    assert a.dentro("http://api.objetivo.com/x")
    assert a.dentro("http://a.b.objetivo.com/x")
    assert a.dentro("http://objetivo.com/x"), "el dominio raiz tambien cuenta"
    assert not a.dentro("http://objetivo.com.malo.net/x")
    assert not a.dentro("http://otro.com/x")


def test_el_comodin_solo_no_es_lo_mismo_que_sin_reglas():
    a = _a("+*")
    assert a.dentro("http://cualquiera.com/x")
    assert a.configurado


def test_un_prefijo_de_ruta():
    a = _a("+objetivo.com/api/")
    assert a.dentro("http://objetivo.com/api/usuarios")
    assert not a.dentro("http://objetivo.com/publico")


def test_el_puerto_cuenta_si_la_regla_lo_dice():
    a = _a("+objetivo.com:8080")
    assert a.dentro("http://objetivo.com:8080/x")
    assert not a.dentro("http://objetivo.com/x")


def test_sin_puerto_en_la_regla_entra_cualquier_puerto():
    a = _a("+objetivo.com")
    assert a.dentro("http://objetivo.com:8080/x")
    assert a.dentro("https://objetivo.com:8443/x")


# ------------------------------------------------------------- excluir
def test_excluir_gana_siempre():
    """Deny-wins. En un contrato, lo que esta prohibido lo esta aunque
    tambien encaje en algo permitido."""
    a = _a("+*.objetivo.com", "-admin.objetivo.com")
    assert a.dentro("http://api.objetivo.com/x")
    assert not a.dentro("http://admin.objetivo.com/x")


def test_excluir_sin_incluir_deja_pasar_el_resto():
    a = _a("-analitica.com")
    assert not a.dentro("http://analitica.com/pixel")
    assert a.dentro("http://objetivo.com/x")


def test_el_orden_de_las_reglas_no_importa():
    uno = _a("+*.objetivo.com", "-admin.objetivo.com")
    otro = _a("-admin.objetivo.com", "+*.objetivo.com")
    for url in ("http://api.objetivo.com/x", "http://admin.objetivo.com/x",
                "http://ajeno.com/x"):
        assert uno.dentro(url) == otro.dentro(url)


# --------------------------------------------------------------- texto
def test_una_regla_se_escribe_y_se_vuelve_a_leer_igual():
    for texto in ("+objetivo.com", "-admin.objetivo.com:8443",
                  "+*.objetivo.com/api/"):
        assert str(alcance.Regla.desde_texto(texto)) == texto


def test_sin_signo_se_asume_incluir():
    assert alcance.Regla.desde_texto("objetivo.com").incluir is True
    assert str(alcance.Regla.desde_texto("objetivo.com")) == "+objetivo.com"


def test_una_regla_vacia_se_rechaza():
    for malo in ("", "   ", "+", "-", "+/solo-ruta"):
        with pytest.raises(alcance.ReglaInvalida):
            alcance.Regla.desde_texto(malo)


def test_el_alcance_entero_va_y_vuelve_por_texto():
    a = _a("+*.objetivo.com", "-admin.objetivo.com", "+otro.org/api/")
    assert alcance.Alcance.desde_texto(a.texto()).texto() == a.texto()


def test_las_lineas_vacias_y_los_comentarios_se_ignoran():
    a = alcance.Alcance.desde_texto("+objetivo.com\n\n# un comentario\n-x.com\n")
    assert len(a.reglas) == 2


def test_una_linea_mala_no_tumba_el_resto():
    """El alcance se teclea a mano: una linea mal escrita no puede dejar
    sin alcance a toda la sesion."""
    a, errores = alcance.Alcance.desde_texto_tolerante(
        "+objetivo.com\n+++\n-x.com")
    assert len(a.reglas) == 2
    assert len(errores) == 1 and "+++" in errores[0]


# ------------------------------------------------------- casos de verdad
def test_una_url_rara_no_revienta():
    a = _a("+objetivo.com")
    for url in ("", "no-es-una-url", "http://", "://x", "http://[::1]/x"):
        assert a.dentro(url) is False


def test_el_host_no_distingue_mayusculas():
    a = _a("+Objetivo.COM")
    assert a.dentro("http://objetivo.com/x")
    assert a.dentro("http://OBJETIVO.com/x")


def test_la_ruta_si_distingue_mayusculas():
    """En los servidores reales /API y /api pueden ser cosas distintas."""
    a = _a("+objetivo.com/api/")
    assert a.dentro("http://objetivo.com/api/x")
    assert not a.dentro("http://objetivo.com/API/x")


# ----------------------------------------------- el alcance en la aplicacion
def _flujo(url, cuerpo=b"<html>buscaste: PRUEBA</html>"):
    from urllib.parse import urlsplit

    from luzxfer.core.models import Flow, Request, Response
    host = urlsplit(url).netloc
    return Flow(request=Request(method="GET", url=url, headers=[("Host", host)]),
                response=Response(status=200, reason="OK", body=cuerpo,
                                  headers=[("Content-Type", "text/html")]))


async def test_el_trafico_fuera_de_alcance_se_captura_igual():
    """La decision de diseno: el alcance filtra la vista y lo activo, NUNCA
    la captura. El trafico que tiras al capturarlo no se recupera."""
    from luzxfer.tui.app import LuzxferApp
    app = LuzxferApp(arrancar_motor=False)
    async with app.run_test() as pilot:
        app.poner_alcance("+objetivo.com")
        await pilot.pause()
        app._ingresar(_flujo("http://objetivo.com/x?q=PRUEBA"))
        app._ingresar(_flujo("http://cdn.ajeno.net/x?q=PRUEBA"))
        await pilot.pause()
        assert app.store.count_flows() == 2


async def test_el_detector_no_analiza_lo_que_esta_fuera():
    """Los candidatos de un CDN o de analitica son ruido que entierra lo
    que si importa, y ademas no son del cliente."""
    from luzxfer.tui.app import LuzxferApp
    app = LuzxferApp(arrancar_motor=False)
    async with app.run_test() as pilot:
        app.poner_alcance("+objetivo.com")
        await pilot.pause()
        app._ingresar(_flujo("http://cdn.ajeno.net/x?q=PRUEBA"))
        await pilot.pause()
        assert app.store.count_findings() == 0

        app._ingresar(_flujo("http://objetivo.com/x?q=PRUEBA"))
        await pilot.pause()
        assert app.store.count_findings() > 0


async def test_sin_alcance_configurado_se_analiza_todo():
    from luzxfer.tui.app import LuzxferApp
    app = LuzxferApp(arrancar_motor=False)
    async with app.run_test() as pilot:
        await pilot.pause()
        app._ingresar(_flujo("http://cualquiera.net/x?q=PRUEBA"))
        await pilot.pause()
        assert app.store.count_findings() > 0


async def test_el_historial_puede_esconder_lo_que_esta_fuera():
    from textual.widgets import DataTable

    from luzxfer.tui.app import LuzxferApp
    app = LuzxferApp(arrancar_motor=False)
    async with app.run_test() as pilot:
        app.poner_alcance("+objetivo.com")
        await pilot.pause()
        app._ingresar(_flujo("http://objetivo.com/a"))
        app._ingresar(_flujo("http://cdn.ajeno.net/b"))
        await pilot.pause()
        tabla = app.query_one("#flujos", DataTable)
        assert tabla.row_count == 2             # por defecto se ve todo

        app.solo_alcance = True
        app.refrescar_tabla()
        await pilot.pause()
        assert tabla.row_count == 1


async def test_el_alcance_sobrevive_al_reinicio(tmp_path):
    from luzxfer.tui.app import LuzxferApp
    ruta = str(tmp_path / "s.db")
    app = LuzxferApp(db=ruta, arrancar_motor=False)
    async with app.run_test() as pilot:
        await pilot.pause()
        app.poner_alcance("+*.objetivo.com\n-admin.objetivo.com")
        await pilot.pause()

    otra = LuzxferApp(db=ruta, arrancar_motor=False)
    async with otra.run_test() as pilot:
        await pilot.pause()
        assert otra.alcance.dentro("http://api.objetivo.com/x")
        assert not otra.alcance.dentro("http://admin.objetivo.com/x")


async def test_una_regla_mal_escrita_avisa_y_conserva_las_buenas():
    from luzxfer.tui.app import LuzxferApp
    app = LuzxferApp(arrancar_motor=False)
    async with app.run_test() as pilot:
        await pilot.pause()
        errores = app.poner_alcance("+objetivo.com\n+++\n-x.com")
        await pilot.pause()
        assert len(errores) == 1
        assert len(app.alcance.reglas) == 2


# ----------------------------------------------- la pantalla (tecla a)
async def _abrir_alcance(app, pilot, url="http://objetivo.com/x"):
    from textual.widgets import DataTable
    app._ingresar(_flujo(url))
    await pilot.pause()
    app.query_one("#flujos", DataTable).move_cursor(row=0)
    await pilot.pause()
    await pilot.press("a")
    await pilot.pause()


async def test_la_tecla_a_abre_el_alcance():
    from luzxfer.tui.app import LuzxferApp
    from luzxfer.tui.screens.alcance import AlcanceScreen
    app = LuzxferApp(arrancar_motor=False)
    async with app.run_test(size=(120, 36)) as pilot:
        await _abrir_alcance(app, pilot)
        assert isinstance(app.screen, AlcanceScreen)


async def test_si_no_hay_alcance_se_propone_el_host_del_flujo():
    """Como el «Add to scope» de Burp: el gesto mas comun es meter el
    objetivo que ya estas mirando, y teclearlo entero sobra."""
    from textual.widgets import TextArea

    from luzxfer.tui.app import LuzxferApp
    app = LuzxferApp(arrancar_motor=False)
    async with app.run_test(size=(120, 36)) as pilot:
        await _abrir_alcance(app, pilot, "http://objetivo.com:3000/x")
        texto = app.screen.query_one("#alc-editor", TextArea).text
        assert "+objetivo.com" in texto


async def test_con_alcance_puesto_no_se_pisa_lo_escrito():
    from textual.widgets import TextArea

    from luzxfer.tui.app import LuzxferApp
    app = LuzxferApp(arrancar_motor=False)
    async with app.run_test(size=(120, 36)) as pilot:
        await pilot.pause()
        app.poner_alcance("+ya.estaba.com")
        await _abrir_alcance(app, pilot)
        assert app.screen.query_one("#alc-editor", TextArea).text.strip() == \
            "+ya.estaba.com"


async def test_guardar_aplica_el_alcance():
    from textual.widgets import TextArea

    from luzxfer.tui.app import LuzxferApp
    app = LuzxferApp(arrancar_motor=False)
    async with app.run_test(size=(120, 36)) as pilot:
        await _abrir_alcance(app, pilot)
        app.screen.query_one("#alc-editor", TextArea).text = "+nuevo.com"
        await pilot.press("ctrl+s")
        await pilot.pause()
        assert app.alcance.dentro("http://nuevo.com/x")
        assert not app.alcance.dentro("http://objetivo.com/x")


async def test_esc_no_guarda():
    from textual.widgets import TextArea

    from luzxfer.tui.app import LuzxferApp
    app = LuzxferApp(arrancar_motor=False)
    async with app.run_test(size=(120, 36)) as pilot:
        await pilot.pause()
        app.poner_alcance("+original.com")
        await _abrir_alcance(app, pilot)
        app.screen.query_one("#alc-editor", TextArea).text = "+descartado.com"
        await pilot.press("escape")
        await pilot.pause()
        assert app.alcance.dentro("http://original.com/x")
        assert not app.alcance.dentro("http://descartado.com/x")


async def test_una_regla_mala_se_señala_y_no_cierra():
    from textual.widgets import Static, TextArea

    from luzxfer.tui.app import LuzxferApp
    from luzxfer.tui.screens.alcance import AlcanceScreen
    app = LuzxferApp(arrancar_motor=False)
    async with app.run_test(size=(120, 36)) as pilot:
        await _abrir_alcance(app, pilot)
        app.screen.query_one("#alc-editor", TextArea).text = "+bueno.com\n+++"
        await pilot.press("ctrl+s")
        await pilot.pause()
        assert isinstance(app.screen, AlcanceScreen), "no cierra con errores"
        assert "host invalido" in app.screen.query_one("#alc-aviso",
                                                       Static).render().plain
        assert app.alcance.dentro("http://bueno.com/x")      # la buena se aplico


async def test_el_filtro_del_historial_se_alterna_y_se_guarda(tmp_path):
    from luzxfer.tui.app import LuzxferApp
    ruta = str(tmp_path / "s.db")
    app = LuzxferApp(db=ruta, arrancar_motor=False)
    async with app.run_test(size=(120, 36)) as pilot:
        await _abrir_alcance(app, pilot)
        assert app.solo_alcance is False
        await pilot.press("ctrl+f")
        await pilot.pause()
        assert app.solo_alcance is True
        await pilot.press("ctrl+s")
        await pilot.pause()

    otra = LuzxferApp(db=ruta, arrancar_motor=False)
    async with otra.run_test() as pilot:
        await pilot.pause()
        assert otra.solo_alcance is True
