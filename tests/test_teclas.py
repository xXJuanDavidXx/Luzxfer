"""Tests de los atajos configurables.

Lo que se prueba sobre todo es que una configuracion mala no deje la
herramienta inutilizable: un atajo que pisa a otro, uno que apunta a una
accion que no existe, o un archivo con un dedazo. Quedarse sin poder
salir de un programa por un error de tecleo seria el peor resultado.
"""
from __future__ import annotations

from luzxfer.tui import teclas


def _escribir(tmp_path, texto):
    r = tmp_path / "config.ini"
    r.write_text(texto, encoding="utf-8")
    return r


def test_sin_archivo_no_hay_cambios(tmp_path):
    mapa, avisos = teclas.leer(tmp_path / "no-existe.ini")
    assert mapa == {} and avisos == []


def test_se_lee_un_atajo(tmp_path):
    mapa, avisos = teclas.leer(_escribir(tmp_path, "[teclas]\nintruder = ctrl+i\n"))
    assert mapa == {"intruder": "ctrl+i"} and avisos == []


def test_una_accion_que_no_existe_avisa_y_se_ignora(tmp_path):
    mapa, avisos = teclas.leer(_escribir(
        tmp_path, "[teclas]\nvolar = ctrl+v\nintruder = ctrl+i\n"))
    assert mapa == {"intruder": "ctrl+i"}, "la buena se aplica igual"
    assert avisos and "volar" in avisos[0]


def test_el_aviso_dice_que_acciones_hay(tmp_path):
    """Sin la lista, el usuario tiene que ir al codigo a adivinar."""
    _, avisos = teclas.leer(_escribir(tmp_path, "[teclas]\nvolar = ctrl+v\n"))
    assert "intruder" in avisos[0] and "repeater" in avisos[0]


def test_una_tecla_vacia_se_ignora(tmp_path):
    mapa, avisos = teclas.leer(_escribir(tmp_path, "[teclas]\nintruder =\n"))
    assert mapa == {} and avisos


def test_dos_acciones_con_la_misma_tecla_avisan(tmp_path):
    """Pisar un atajo con otro deja una de las dos acciones muerta, y en
    silencio seria imposible de diagnosticar."""
    mapa, avisos = teclas.leer(_escribir(
        tmp_path, "[teclas]\nintruder = z\nbarrido = z\n"))
    assert avisos and "z" in avisos[0]
    # se queda solo una, y se dice cual
    assert len([k for k, v in mapa.items() if v == "z"]) == 1


def test_un_archivo_corrupto_no_impide_arrancar(tmp_path):
    mapa, avisos = teclas.leer(_escribir(tmp_path, "[[[ esto no es un ini\n"))
    assert mapa == {} and avisos


def test_las_acciones_declaradas_existen_de_verdad():
    """Si la lista de acciones configurables se desincroniza del codigo,
    el usuario configuraria atajos que no hacen nada."""
    from luzxfer.tui.app import LuzxferApp
    reales = {b.id for b in LuzxferApp.BINDINGS if getattr(b, "id", None)}
    assert teclas.ACCIONES <= reales, \
        f"declaradas y no existentes: {teclas.ACCIONES - reales}"


def test_todas_las_teclas_de_la_app_son_configurables():
    """Al reves: un atajo que no se puede cambiar es una excepcion que
    hay que justificar, no un olvido."""
    from luzxfer.tui.app import LuzxferApp
    reales = {b.id for b in LuzxferApp.BINDINGS if getattr(b, "id", None)}
    assert reales == teclas.ACCIONES


# ---------------------------------------------------- en la aplicacion
async def test_un_atajo_remapeado_funciona(tmp_path, monkeypatch):
    from textual.widgets import DataTable

    from luzxfer.core.models import Flow, Request, Response
    from luzxfer.tui.app import LuzxferApp
    from luzxfer.tui.screens.intruder import IntruderScreen

    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    (tmp_path / "luzxfer").mkdir(parents=True)
    (tmp_path / "luzxfer" / "config.ini").write_text(
        "[teclas]\nintruder = ctrl+j\n", encoding="utf-8")

    app = LuzxferApp(arrancar_motor=False)
    async with app.run_test(size=(140, 44)) as pilot:
        app._ingresar(Flow(
            request=Request(method="GET", url="http://o.com/x?q=1",
                            headers=[("Host", "o.com")]),
            response=Response(status=200, body=b"ok")))
        await pilot.pause()
        app.query_one("#flujos", DataTable).move_cursor(row=0)
        await pilot.pause()

        await pilot.press("ctrl+j")
        await pilot.pause()
        assert isinstance(app.screen, IntruderScreen), \
            "el atajo nuevo tiene que abrir el intruder"


async def test_el_pie_muestra_el_atajo_nuevo_y_no_el_viejo(tmp_path, monkeypatch):
    """El pie se genera de los atajos reales, asi que la ayuda no puede
    quedarse diciendo la tecla de antes."""
    from luzxfer.tui.app import LuzxferApp
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    (tmp_path / "luzxfer").mkdir(parents=True)
    (tmp_path / "luzxfer" / "config.ini").write_text(
        "[teclas]\nintruder = ctrl+j\n", encoding="utf-8")

    app = LuzxferApp(arrancar_motor=False)
    async with app.run_test(size=(140, 44)) as pilot:
        await pilot.pause()
        activos = {a.binding.key for a in app.active_bindings.values()
                   if a.binding.id == "intruder"}
        assert activos == {"ctrl+j"}


async def test_una_configuracion_mala_no_deja_sin_salir(tmp_path, monkeypatch):
    """El peor resultado posible: quedarse encerrado en el programa."""
    from luzxfer.tui.app import LuzxferApp
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    (tmp_path / "luzxfer").mkdir(parents=True)
    (tmp_path / "luzxfer" / "config.ini").write_text(
        "[teclas]\nvolar = x\nintruder = \n", encoding="utf-8")

    app = LuzxferApp(arrancar_motor=False)
    async with app.run_test() as pilot:
        await pilot.pause()
        salir = {a.binding.key for a in app.active_bindings.values()
                 if a.binding.id == "salir"}
        assert salir == {"q"}
        assert app._avisos_teclas, "los problemas se dicen"
