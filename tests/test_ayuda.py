"""Tests de la pantalla de ayuda y del pie que la hizo necesaria.

El fallo que origino esto era silencioso, como casi todos los que han
aparecido en este proyecto: el pie pintaba siete atajos de veinte a
ochenta columnas y Textual descartaba el resto sin una flecha, sin
puntos suspensivos y sin un aviso. La herramienta no estaba rota, solo
escondia la mitad de si misma.

El test que mas vale aqui es `test_el_pie_cabe_a_ochenta_columnas`:
codifica el fallo para que no pueda volver sin que alguien se entere.
"""
from __future__ import annotations

import pytest
from textual.widgets import Footer, Static

from luzxfer.tui.app import LuzxferApp
from luzxfer.tui.screens.ayuda import GRUPOS, AyudaScreen, nombre_tecla

# A ochenta columnas, que es el ancho de cualquier terminal y el unico
# que hay en Termux.
ANCHO_MINIMO = 80


def _teclas_del_pie(app):
    """Las teclas que el pie pinta de verdad, no las que cree tener."""
    pie = app.query_one(Footer)
    return [w for w in pie.query("FooterKey") if w.region.width > 0]


def _cortadas(app):
    pie = app.query_one(Footer)
    return [w for w in _teclas_del_pie(app)
            if w.region.right > pie.region.right]


async def test_el_pie_cabe_a_ochenta_columnas():
    """El fallo original: trece de veinte atajos se perdian en silencio.

    Un pie que recorta no avisa de nada, asi que el usuario no descubre
    que existen interceptar, el barrido o la cobertura.
    """
    app = LuzxferApp(arrancar_motor=False)
    async with app.run_test(size=(ANCHO_MINIMO, 30)) as pilot:
        await pilot.pause()
        cortadas = _cortadas(app)
        assert not cortadas, (
            "el pie recorta " + ", ".join(w.key for w in cortadas) +
            f" a {ANCHO_MINIMO} columnas; si hacen falta mas atajos a la "
            "vista, van en la pantalla de ayuda, no en el pie")


@pytest.mark.parametrize("ancho", [80, 100, 140])
async def test_el_pie_cabe_a_cualquier_ancho_razonable(ancho):
    app = LuzxferApp(arrancar_motor=False)
    async with app.run_test(size=(ancho, 30)) as pilot:
        await pilot.pause()
        assert not _cortadas(app), f"el pie recorta a {ancho} columnas"


async def test_el_pie_ensena_como_pedir_ayuda():
    """Si el pie esconde atajos, tiene que decir donde estan los demas."""
    app = LuzxferApp(arrancar_motor=False)
    async with app.run_test(size=(ANCHO_MINIMO, 30)) as pilot:
        await pilot.pause()
        visibles = {a.binding.id for a in app.active_bindings.values()
                    if a.binding.show}
        assert "ayuda" in visibles, \
            "con atajos escondidos, el acceso a la ayuda no puede esconderse"
        assert "salir" in visibles, "salir siempre se ve"


# ------------------------------------------------- la pantalla de ayuda
def _texto_de_la_ayuda(app) -> str:
    return app.screen.query_one("#ayuda-lista", Static).render().plain


async def test_la_ayuda_abre_con_interrogacion():
    app = LuzxferApp(arrancar_motor=False)
    async with app.run_test(size=(100, 40)) as pilot:
        await pilot.press("question_mark")
        await pilot.pause()
        assert isinstance(app.screen, AyudaScreen)


async def test_la_ayuda_lista_todos_los_atajos():
    """Ninguno puede faltar: perderlo aqui seria repetir el fallo del
    pie, solo que mas escondido."""
    app = LuzxferApp(arrancar_motor=False)
    async with app.run_test(size=(100, 40)) as pilot:
        await pilot.pause()
        esperados = {i: (t, d) for i, t, d in app.atajos()}
        await pilot.press("question_mark")
        await pilot.pause()

        texto = _texto_de_la_ayuda(app)
        faltan = [i for i, (_t, d) in esperados.items() if d not in texto]
        assert not faltan, f"la ayuda no menciona: {faltan}"


async def test_la_ayuda_ensena_lo_que_el_pie_esconde():
    """El caso concreto que motivo todo esto."""
    app = LuzxferApp(arrancar_motor=False)
    async with app.run_test(size=(100, 40)) as pilot:
        await pilot.press("question_mark")
        await pilot.pause()
        texto = _texto_de_la_ayuda(app)
        for tecla in ("b", "d", "y", "m", "n", "v"):
            assert f" {tecla} " in f" {texto} " or f"\n  {tecla}" in texto, \
                f"la tecla {tecla!r} no aparece en la ayuda"


async def test_la_ayuda_traduce_los_nombres_de_textual():
    """«slash» en una ayuda obliga a traducir mentalmente."""
    app = LuzxferApp(arrancar_motor=False)
    async with app.run_test(size=(100, 40)) as pilot:
        await pilot.press("question_mark")
        await pilot.pause()
        texto = _texto_de_la_ayuda(app)
        assert "slash" not in texto and "/" in texto
        assert "escape" not in texto and "esc" in texto


async def test_la_ayuda_sigue_al_atajo_remapeado(tmp_path, monkeypatch):
    """Una ayuda que se mantiene aparte del codigo manda a probar teclas
    que ya no hacen nada."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    (tmp_path / "luzxfer").mkdir(parents=True)
    (tmp_path / "luzxfer" / "config.ini").write_text(
        "[teclas]\nconversor = ctrl+j\n", encoding="utf-8")

    app = LuzxferApp(arrancar_motor=False)
    async with app.run_test(size=(100, 40)) as pilot:
        await pilot.press("question_mark")
        await pilot.pause()
        texto = _texto_de_la_ayuda(app)
        linea = next(ln for ln in texto.splitlines() if "conversor" in ln)
        assert "ctrl+j" in linea, "tiene que salir la tecla del usuario"


async def test_la_ayuda_se_cierra():
    app = LuzxferApp(arrancar_motor=False)
    async with app.run_test(size=(100, 40)) as pilot:
        await pilot.press("question_mark")
        await pilot.pause()
        assert isinstance(app.screen, AyudaScreen)
        await pilot.press("escape")
        await pilot.pause()
        assert not isinstance(app.screen, AyudaScreen)


def test_todos_los_atajos_estan_clasificados():
    """«otros» es una red de seguridad, no un sitio donde dejar cosas.

    Un atajo sin grupo sale igual, pero suelto al final y sin contexto;
    si aparece uno, es que alguien anadio una tecla y no la coloco.
    """
    clasificados = {i for _titulo, ids in GRUPOS for i in ids}
    reales = {b.id for b in LuzxferApp.BINDINGS if b.id}
    assert reales <= clasificados, \
        f"atajos sin grupo en la ayuda: {reales - clasificados}"


def test_ningun_grupo_nombra_un_atajo_que_no_existe():
    """Al reves: un grupo que nombra una tecla borrada no falla, pero
    deja un hueco que nadie ve hasta que lo busca."""
    clasificados = {i for _titulo, ids in GRUPOS for i in ids}
    reales = {b.id for b in LuzxferApp.BINDINGS if b.id}
    assert clasificados <= reales, \
        f"la ayuda agrupa atajos que ya no existen: {clasificados - reales}"


def test_nombre_tecla():
    assert nombre_tecla("slash") == "/"
    assert nombre_tecla("escape") == "esc"
    assert nombre_tecla("r") == "r", "lo que ya se lee bien no se toca"
