"""Tests del foco y el desplazamiento en el repeater.

El fallo lo reporto el usuario como «a veces no se ve la respuesta
completa, se corta la parte de abajo». No se cortaba: era inalcanzable.
El foco arranca en el editor, `pagedown` y `end` van al editor, y al
panel de respuesta solo se llega con `tab` —que no estaba documentado en
ningun sitio—. Encima, los selectores de la hoja de estilos apuntaban a
ids que ya no existian desde que el repeater paso a pestañas, asi que
**ningun panel mostraba el foco**: no habia manera de notar que se habia
movido ni de sospechar que se podia desplazar.

El mismo patron de siempre: la herramienta no estaba rota, no decia lo
que sabia hacer.
"""
from __future__ import annotations

from textual.containers import VerticalScroll
from textual.widgets import DataTable, Static, TextArea

from luzxfer.core.models import Flow, Request, Response
from luzxfer.tui.app import LuzxferApp
from luzxfer.tui.screens.repeater import RepeaterScreen


async def _abrir(pilot, app):
    app._ingresar(Flow(
        request=Request(method="GET", url="http://o.com/x",
                        headers=[("Host", "o.com")]),
        response=Response(status=200, body=b"ok")))
    await pilot.pause()
    app.query_one("#flujos", DataTable).move_cursor(row=0)
    await pilot.pause()
    await pilot.press("r")
    await pilot.pause()
    assert isinstance(app.screen, RepeaterScreen)
    return app.screen


async def test_la_respuesta_larga_se_puede_alcanzar():
    """287 lineas de desplazamiento no sirven de nada si no se llega."""
    app = LuzxferApp(arrancar_motor=False)
    async with app.run_test(size=(120, 40)) as pilot:
        pant = await _abrir(pilot, app)
        sc = pant.query_one(VerticalScroll)
        pant.salida_actual().update("\n".join(f"L{i}" for i in range(300)))
        await pilot.pause()
        assert sc.max_scroll_y > 0, "hay contenido de sobra que desplazar"

        await pilot.press("tab")
        await pilot.pause()
        assert app.focused is sc, "tab tiene que llevar a la respuesta"

        await pilot.press("end")
        await pilot.pause()
        assert sc.scroll_y > 0, "y desde ahi tiene que desplazarse"


async def test_la_pista_dice_como_llegar_a_la_respuesta():
    """Si hace falta `tab` para ver el final de una respuesta, callarlo
    es lo que hace que parezca cortada."""
    app = LuzxferApp(arrancar_motor=False)
    async with app.run_test(size=(120, 40)) as pilot:
        pant = await _abrir(pilot, app)
        pista = pant.query_one("#rep-titulo", Static).render().plain
        assert "tab" in pista, f"la pista no menciona tab: {pista!r}"


async def test_los_estilos_del_repeater_se_aplican_de_verdad():
    """Los selectores apuntaban a ids que ya no existian desde que el
    repeater paso a pestañas: las reglas no afectaban a nada, y por eso
    el foco era invisible."""
    app = LuzxferApp(arrancar_motor=False)
    async with app.run_test(size=(120, 40)) as pilot:
        pant = await _abrir(pilot, app)
        ed = pant.query_one(TextArea)
        sc = pant.query_one(VerticalScroll)
        assert "rep-editor" in ed.classes
        assert "rep-scroll" in sc.classes
        # si la regla no enganchara, el borde seria el de por defecto
        assert ed.styles.border is not None
        assert sc.styles.border is not None


async def test_el_foco_se_ve_al_cambiar_de_panel():
    """El borde de foco es lo unico que le dice al analista donde esta."""
    app = LuzxferApp(arrancar_motor=False)
    async with app.run_test(size=(120, 40)) as pilot:
        pant = await _abrir(pilot, app)
        ed = pant.query_one(TextArea)
        sc = pant.query_one(VerticalScroll)

        assert app.focused is ed
        sin_foco = sc.styles.border_top
        await pilot.press("tab")
        await pilot.pause()
        assert app.focused is sc
        assert sc.styles.border_top != sin_foco, \
            "el panel con el foco tiene que verse distinto"
