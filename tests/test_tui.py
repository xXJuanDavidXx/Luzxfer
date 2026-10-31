"""Tests de la TUI con el harness de pilotaje de Textual (sin pantalla)."""
from __future__ import annotations

import pytest
from textual.widgets import DataTable, Input, Static

from luzxfer.core.models import Flow, Request, Response
from luzxfer.tui.app import LuzxferApp, pinta_estado, tamano_legible


def _flujo(metodo="GET", url="http://ej.com/ruta?q=PRUEBA", status=200,
           cuerpo=b"<html>buscaste: PRUEBA</html>", cab=(("Content-Type", "text/html"),)):
    return Flow(
        request=Request(method=metodo, url=url, headers=[("Host", "ej.com")]),
        response=Response(status=status, reason="OK", headers=list(cab), body=cuerpo),
        duration_ms=7,
    )


def app_prueba() -> LuzxferApp:
    # sin motor: los tests inyectan los flujos a mano
    return LuzxferApp(arrancar_motor=False)


# --------------------------------------------------------------- utilidades
def test_tamano_legible():
    assert tamano_legible(512) == "512B"
    assert tamano_legible(2048) == "2.0K"
    assert tamano_legible(3 * 1024 * 1024) == "3.0M"


def test_pinta_estado_colorea_por_familia():
    assert "6fcf8f" in pinta_estado(200).style      # verde
    assert "e05c5c" in pinta_estado(500).style      # rojo
    assert pinta_estado(None).plain == "—"
    assert pinta_estado(None, error="boom").plain == "ERR"


# -------------------------------------------------------------------- app
async def test_arranca_y_compone():
    app = app_prueba()
    async with app.run_test() as pilot:
        await pilot.pause()
        assert app.query_one("#flujos", DataTable) is not None
        assert app.query_one("#filtro", Input) is not None
        # columnas de la tabla
        assert len(app.query_one("#flujos", DataTable).ordered_columns) == 7
        # el estado dice que el motor no esta
        assert "detenido" in app.query_one("#estado", Static).render().plain


async def test_un_flujo_aparece_en_la_tabla():
    app = app_prueba()
    async with app.run_test() as pilot:
        await pilot.pause()
        app._ingresar(_flujo())
        await pilot.pause()

        tabla = app.query_one("#flujos", DataTable)
        assert tabla.row_count == 1
        assert app.store.count_flows() == 1
        # el detector corrio: el reflejo de PRUEBA se marco
        assert app.store.count_findings() >= 1
        tipos = {h.kind for h in app.store.list_findings()}
        assert "REFLEJO" in tipos


async def test_seleccionar_pinta_el_detalle():
    app = app_prueba()
    async with app.run_test() as pilot:
        await pilot.pause()
        app._ingresar(_flujo())
        await pilot.pause()

        app.query_one("#flujos", DataTable).move_cursor(row=0)
        await pilot.pause()

        req = app.query_one("#panel-req", Static).render().plain
        resp = app.query_one("#panel-resp", Static).render().plain
        assert "GET /ruta?q=PRUEBA HTTP/1.1" in req
        assert "Host: ej.com" in req
        assert "buscaste: PRUEBA" in resp
        assert app._flujo_actual is not None


async def test_filtro_reduce_las_filas():
    app = app_prueba()
    async with app.run_test() as pilot:
        await pilot.pause()
        app._ingresar(_flujo(url="http://ej.com/alpha"))
        app._ingresar(_flujo(url="http://ej.com/beta"))
        await pilot.pause()
        assert app.query_one("#flujos", DataTable).row_count == 2

        app.query_one("#filtro", Input).value = "alpha"
        await pilot.pause()
        assert app.query_one("#flujos", DataTable).row_count == 1


async def test_tecla_marcar_marca_el_flujo():
    app = app_prueba()
    async with app.run_test() as pilot:
        await pilot.pause()
        app._ingresar(_flujo())
        await pilot.pause()
        app.query_one("#flujos", DataTable).move_cursor(row=0)
        await pilot.pause()

        await pilot.press("m")
        await pilot.pause()
        assert app.store.get_flow(1).marked is True

        await pilot.press("m")
        await pilot.pause()
        assert app.store.get_flow(1).marked is False


async def test_limpiar_borra_historial_pero_conserva_candidatos():
    app = app_prueba()
    async with app.run_test() as pilot:
        await pilot.pause()
        app._ingresar(_flujo())
        await pilot.pause()
        antes = app.store.count_findings()
        assert antes > 0

        await pilot.press("c")
        await pilot.pause()
        assert app.store.count_flows() == 0
        assert app.store.count_findings() == antes      # la evidencia no se tira


async def test_tecla_f_enfoca_el_filtro():
    app = app_prueba()
    async with app.run_test() as pilot:
        await pilot.pause()
        app.query_one("#flujos", DataTable).focus()
        await pilot.pause()
        await pilot.press("f")
        await pilot.pause()
        assert app.focused is app.query_one("#filtro", Input)


async def test_repeater_se_abre_con_la_peticion_cargada():
    app = app_prueba()
    async with app.run_test() as pilot:
        await pilot.pause()
        app._ingresar(_flujo())
        await pilot.pause()
        app.query_one("#flujos", DataTable).move_cursor(row=0)
        await pilot.pause()

        await pilot.press("r")
        await pilot.pause()

        from textual.widgets import TextArea
        editor = app.screen.query_one("#rep-editor", TextArea)
        assert "GET /ruta?q=PRUEBA HTTP/1.1" in editor.text
        assert "Host: ej.com" in editor.text


async def test_repeater_sin_seleccion_avisa_y_no_abre():
    app = app_prueba()
    async with app.run_test() as pilot:
        await pilot.pause()
        pantalla_antes = app.screen
        await pilot.press("r")
        await pilot.pause()
        assert app.screen is pantalla_antes     # no se abrio nada


async def test_hallazgos_se_listan_en_su_pestana():
    app = app_prueba()
    async with app.run_test() as pilot:
        await pilot.pause()
        app._ingresar(_flujo(cab=(("Content-Type", "text/html"),
                                  ("Set-Cookie", "sid=1; Path=/"),
                                  ("Server", "nginx"))))
        await pilot.pause()
        hall = app.query_one("#hallazgos", DataTable)
        assert hall.row_count >= 3      # reflejo + cookie + cabeceras + fuga


@pytest.mark.parametrize("tecla", ["j", "k", "g", "G"])
async def test_navegacion_vim_no_revienta(tecla):
    app = app_prueba()
    async with app.run_test() as pilot:
        await pilot.pause()
        for i in range(3):
            app._ingresar(_flujo(url=f"http://ej.com/r{i}"))
        await pilot.pause()
        app.query_one("#flujos", DataTable).focus()
        await pilot.press(tecla)
        await pilot.pause()
        assert app.query_one("#flujos", DataTable).row_count == 3


async def test_repeater_envia_de_verdad_y_muestra_la_respuesta():
    """Comprueba el cableado completo: boton -> send_raw -> salida -> historial."""
    import http.server
    import threading

    class _Eco(http.server.BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *a):
            pass

        def do_GET(self):
            cuerpo = b"<html>respuesta del repeater</html>"
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(cuerpo)))
            self.end_headers()
            self.wfile.write(cuerpo)

    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Eco)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    host, puerto = srv.server_address

    app = app_prueba()
    try:
        async with app.run_test() as pilot:
            await pilot.pause()
            app._ingresar(_flujo(url=f"http://{host}:{puerto}/x"))
            await pilot.pause()
            app.query_one("#flujos", DataTable).move_cursor(row=0)
            await pilot.pause()
            await pilot.press("r")
            await pilot.pause()

            from textual.widgets import Button, TextArea
            editor = app.screen.query_one("#rep-editor", TextArea)
            editor.text = (f"GET /x HTTP/1.1\r\nHost: {host}:{puerto}\r\n"
                           f"Content-Length: 999\r\n\r\n")

            antes = app.store.count_flows()
            app.screen.query_one("#rep-enviar", Button).press()
            await pilot.pause()
            await pilot.pause()

            salida = app.screen.query_one("#rep-salida", Static).render().plain
            assert "200 OK" in salida
            assert "respuesta del repeater" in salida
            # el flujo del repeater queda en el historial como evidencia
            assert app.store.count_flows() == antes + 1
            assert app.store.list_flows()[0].source == "repeater"
    finally:
        srv.shutdown()
        srv.server_close()


# ------------------------------------------------------------- notas (n)
async def test_la_tecla_n_guarda_una_nota_en_el_flujo():
    app = app_prueba()
    async with app.run_test() as pilot:
        app._ingresar(_flujo())
        await pilot.pause()
        app.query_one("#flujos", DataTable).move_cursor(row=0)
        await pilot.pause()
        fid = app._flujo_actual.id

        await pilot.press("n")
        await pilot.pause()
        app.screen.query_one("#nota-input", Input).value = "parametro q sin escapar"
        await pilot.press("enter")
        await pilot.pause()

        assert app.store.get_flow(fid).note == "parametro q sin escapar"


async def test_esc_en_la_nota_no_guarda_nada():
    app = app_prueba()
    async with app.run_test() as pilot:
        app._ingresar(_flujo())
        await pilot.pause()
        app.query_one("#flujos", DataTable).move_cursor(row=0)
        await pilot.pause()
        fid = app._flujo_actual.id
        await pilot.press("n")
        await pilot.pause()
        app.screen.query_one("#nota-input", Input).value = "esto se descarta"
        await pilot.press("escape")
        await pilot.pause()
        assert app.store.get_flow(fid).note == ""


async def test_la_nota_se_ve_en_el_panel_de_peticion():
    app = app_prueba()
    async with app.run_test() as pilot:
        app._ingresar(_flujo())
        await pilot.pause()
        app.query_one("#flujos", DataTable).move_cursor(row=0)
        await pilot.pause()
        await pilot.press("n")
        await pilot.pause()
        app.screen.query_one("#nota-input", Input).value = "revisar en el reporte"
        await pilot.press("enter")
        await pilot.pause()
        panel = app.query_one("#panel-req", Static).render().plain
        assert "revisar en el reporte" in panel
        assert "GET /ruta?q=PRUEBA" in panel          # la peticion sigue ahi


async def test_la_nota_se_puede_editar_y_borrar():
    app = app_prueba()
    async with app.run_test() as pilot:
        app._ingresar(_flujo())
        await pilot.pause()
        app.query_one("#flujos", DataTable).move_cursor(row=0)
        await pilot.pause()
        fid = app._flujo_actual.id

        await pilot.press("n")
        await pilot.pause()
        app.screen.query_one("#nota-input", Input).value = "primera"
        await pilot.press("enter")
        await pilot.pause()

        await pilot.press("n")                        # se reabre con lo de antes
        await pilot.pause()
        assert app.screen.query_one("#nota-input", Input).value == "primera"
        app.screen.query_one("#nota-input", Input).value = ""
        await pilot.press("enter")
        await pilot.pause()
        assert app.store.get_flow(fid).note == ""


async def test_nota_sin_seleccion_avisa_y_no_abre():
    app = app_prueba()
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("n")
        await pilot.pause()
        assert app.screen is app.screen_stack[0]


# ------------------------------------------------ confirmar candidato (v)
async def test_la_tecla_v_confirma_el_candidato_resaltado():
    app = app_prueba()
    async with app.run_test() as pilot:
        app._ingresar(_flujo())
        await pilot.pause()
        app.query_one("#detalle").active = "tab-hall"
        await pilot.pause()
        hall = app.query_one("#hallazgos", DataTable)
        hall.focus()
        hall.move_cursor(row=0)
        await pilot.pause()
        await pilot.press("v")
        await pilot.pause()
        assert any(h.confirmed for h in app.store.list_findings())


async def test_la_tecla_v_tambien_desconfirma():
    app = app_prueba()
    async with app.run_test() as pilot:
        app._ingresar(_flujo())
        await pilot.pause()
        app.query_one("#detalle").active = "tab-hall"
        await pilot.pause()
        hall = app.query_one("#hallazgos", DataTable)
        hall.focus()
        hall.move_cursor(row=0)
        await pilot.pause()
        await pilot.press("v")
        await pilot.pause()
        await pilot.press("v")
        await pilot.pause()
        assert not any(h.confirmed for h in app.store.list_findings())


async def test_lo_confirmado_se_ve_en_la_tabla_de_candidatos():
    app = app_prueba()
    async with app.run_test() as pilot:
        app._ingresar(_flujo())
        await pilot.pause()
        app.query_one("#detalle").active = "tab-hall"
        await pilot.pause()
        hall = app.query_one("#hallazgos", DataTable)
        hall.focus()
        hall.move_cursor(row=0)
        await pilot.press("v")
        await pilot.pause()
        assert "✓" in str(hall.get_row_at(0)[0])


# ------------------------------------------- vista combinada (t / boton)
async def test_la_tecla_t_alterna_a_vista_combinada():
    app = app_prueba()
    async with app.run_test() as pilot:
        app._ingresar(_flujo())
        await pilot.pause()
        app.query_one("#flujos", DataTable).move_cursor(row=0)
        await pilot.pause()
        assert app.vista_combinada is False

        await pilot.press("t")
        await pilot.pause()
        assert app.vista_combinada is True
        assert app.query_one("#detalle").active == "tab-ambos"

        await pilot.press("t")
        await pilot.pause()
        assert app.vista_combinada is False
        assert app.query_one("#detalle").active == "tab-req"


async def test_la_vista_combinada_muestra_peticion_y_respuesta_a_la_vez():
    app = app_prueba()
    async with app.run_test(size=(140, 40)) as pilot:
        app._ingresar(_flujo())
        await pilot.pause()
        app.query_one("#flujos", DataTable).move_cursor(row=0)
        await pilot.press("t")
        await pilot.pause()
        izq = app.query_one("#ambos-req", Static).render().plain
        der = app.query_one("#ambos-resp", Static).render().plain
        assert "GET /ruta?q=PRUEBA" in izq
        assert "buscaste: PRUEBA" in der


async def test_los_candidatos_siguen_alcanzables_en_vista_combinada():
    """Esconder el TabbedContent entero habria dejado la pestana de
    candidatos inaccesible justo en el modo nuevo."""
    app = app_prueba()
    async with app.run_test() as pilot:
        app._ingresar(_flujo())
        await pilot.pause()
        await pilot.press("t")
        await pilot.pause()
        app.query_one("#detalle").active = "tab-hall"
        await pilot.pause()
        assert app.query_one("#hallazgos", DataTable).row_count > 0


async def test_el_boton_alterna_igual_que_la_tecla():
    from textual.widgets import Button
    app = app_prueba()
    async with app.run_test() as pilot:
        await pilot.pause()
        assert "separadas" in str(app.query_one("#btn-vista", Button).label)
        app.query_one("#btn-vista", Button).press()
        await pilot.pause()
        assert app.vista_combinada is True
        assert "juntas" in str(app.query_one("#btn-vista", Button).label)


async def test_la_vista_combinada_tambien_se_repinta_al_cambiar_de_flujo():
    app = app_prueba()
    async with app.run_test(size=(140, 40)) as pilot:
        app._ingresar(_flujo(url="http://ej.com/uno?q=UNO", cuerpo=b"<html>UNO</html>"))
        app._ingresar(_flujo(url="http://ej.com/dos?q=DOS", cuerpo=b"<html>DOS</html>"))
        await pilot.pause()
        await pilot.press("t")
        await pilot.pause()
        app.query_one("#flujos", DataTable).move_cursor(row=0)
        await pilot.pause()
        assert "/uno" in app.query_one("#ambos-req", Static).render().plain
        app.query_one("#flujos", DataTable).move_cursor(row=1)
        await pilot.pause()
        assert "/dos" in app.query_one("#ambos-req", Static).render().plain


async def test_la_vista_elegida_sobrevive_al_reinicio(tmp_path):
    ruta = str(tmp_path / "s.db")
    app = LuzxferApp(db=ruta, arrancar_motor=False)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("t")
        await pilot.pause()
        assert app.vista_combinada is True

    otra = LuzxferApp(db=ruta, arrancar_motor=False)
    async with otra.run_test() as pilot:
        await pilot.pause()
        assert otra.vista_combinada is True
        assert otra.query_one("#detalle").active == "tab-ambos"
