"""Tests de la cobertura y del informe.

Dos reglas mandan aqui:

  - La evidencia gana a la opinion. Si hay un hallazgo confirmado con un
    ID, esa prueba FALLA aunque alguien la hubiera marcado como que pasa.
  - No haber mirado y no aplicar no son lo mismo, y el informe los cuenta
    aparte. Mezclarlos es como una matriz de cobertura miente.
"""
from __future__ import annotations

from luzxfer.core.models import Finding
from luzxfer.core.tools import cobertura, wstg


def _h(ident, confirmado=False, kind="REFLEJO", url="http://o.com/x"):
    return Finding(kind=kind, detail="lo que sea", url=url,
                   wstg=[ident], confirmed=confirmado)


# ------------------------------------------------------------- estados
def test_sin_nada_todo_esta_por_probar():
    est = cobertura.calcular([], {})
    assert len(est) == len(wstg.CATALOGO)
    assert set(est.values()) == {wstg.NO_PROBADO}


def test_un_candidato_deja_la_prueba_como_probada_no_como_fallada():
    """Un candidato es evidencia de que se miro, no de que haya nada."""
    est = cobertura.calcular([_h("WSTG-INPV-01")], {})
    assert est["WSTG-INPV-01"] == wstg.PROBADO
    assert est["WSTG-INPV-02"] == wstg.NO_PROBADO


def test_un_hallazgo_confirmado_hace_fallar_la_prueba():
    est = cobertura.calcular([_h("WSTG-INPV-05", confirmado=True)], {})
    assert est["WSTG-INPV-05"] == wstg.FALLA


def test_lo_manual_gana_a_un_simple_candidato():
    est = cobertura.calcular([_h("WSTG-INPV-01")],
                             {"WSTG-INPV-01": wstg.PASA})
    assert est["WSTG-INPV-01"] == wstg.PASA


def test_la_evidencia_gana_a_la_opinion():
    """Marcaste que pasaba y luego confirmaste un hallazgo con ese ID.
    Gana el hallazgo: un informe que diga que la prueba paso teniendo
    una vulnerabilidad confirmada debajo es inaceptable."""
    est = cobertura.calcular([_h("WSTG-INPV-05", confirmado=True)],
                             {"WSTG-INPV-05": wstg.PASA})
    assert est["WSTG-INPV-05"] == wstg.FALLA


def test_no_aplica_se_puede_poner_a_mano():
    est = cobertura.calcular([], {"WSTG-APIT-01": wstg.NO_APLICA})
    assert est["WSTG-APIT-01"] == wstg.NO_APLICA


def test_un_id_que_no_existe_se_ignora_sin_romper():
    """Los hallazgos manuales pueden traer cualquier cosa escrita a mano."""
    est = cobertura.calcular([_h("WSTG-FALSO-99", confirmado=True)],
                             {"TAMBIEN-FALSO": wstg.PASA})
    assert "WSTG-FALSO-99" not in est and "TAMBIEN-FALSO" not in est
    assert len(est) == len(wstg.CATALOGO)


def test_un_hallazgo_sin_wstg_no_afecta_a_nadie():
    """Los de endurecimiento sin prueba propia no deben inflar nada."""
    f = Finding(kind="CABECERA", detail="falta CSP", url="o.com", wstg=[])
    est = cobertura.calcular([f], {})
    assert set(est.values()) == {wstg.NO_PROBADO}


# ------------------------------------------------------------- resumen
def test_el_resumen_cuenta_por_estado():
    est = cobertura.calcular(
        [_h("WSTG-INPV-05", confirmado=True), _h("WSTG-INPV-01")],
        {"WSTG-APIT-01": wstg.NO_APLICA, "WSTG-SESS-02": wstg.PASA})
    r = cobertura.resumen(est)
    assert r[wstg.FALLA] == 1
    assert r[wstg.PROBADO] == 1
    assert r[wstg.PASA] == 1
    assert r[wstg.NO_APLICA] == 1
    assert r[wstg.NO_PROBADO] == len(wstg.CATALOGO) - 4


def test_el_porcentaje_de_cobertura_no_cuenta_lo_que_no_aplica():
    """Si una prueba no aplica, no es trabajo pendiente: contarla en el
    denominador haria parecer que falta algo que no falta."""
    est = {i: wstg.NO_PROBADO for i in wstg.CATALOGO}
    est["WSTG-APIT-01"] = wstg.NO_APLICA
    est["WSTG-INPV-01"] = wstg.PASA
    pct = cobertura.porcentaje(est)
    assert pct == round(1 / (len(wstg.CATALOGO) - 1) * 100, 1)


def test_cobertura_vacia_es_cero_y_no_una_division_por_cero():
    est = {i: wstg.NO_APLICA for i in wstg.CATALOGO}
    assert cobertura.porcentaje(est) == 0.0


# ------------------------------------------------------------- informe
def _informe(**kw):
    kw.setdefault("sesion", "cliente-x")
    kw.setdefault("hallazgos", [])
    kw.setdefault("estados", {})
    kw.setdefault("alcance", "+objetivo.com")
    kw.setdefault("flujos", 0)
    return cobertura.informe(**kw)


def test_el_informe_lleva_lo_imprescindible():
    md = _informe()
    for trozo in ("# Informe", "cliente-x", "+objetivo.com",
                  "## Resumen", "## Cobertura WSTG"):
        assert trozo in md


def test_los_hallazgos_confirmados_salen_primero_y_con_su_id():
    md = _informe(hallazgos=[
        _h("WSTG-INPV-05", confirmado=True, kind="DAST"),
        _h("WSTG-INPV-01"),
    ])
    assert "## Hallazgos confirmados" in md
    assert "WSTG-INPV-05" in md
    assert md.index("## Hallazgos confirmados") < md.index("## Cobertura WSTG")


def test_los_candidatos_sin_confirmar_van_aparte_y_se_dice():
    md = _informe(hallazgos=[_h("WSTG-INPV-01")])
    assert "Candidatos sin confirmar" in md
    assert "no son hallazgos" in md.lower()


def test_sin_hallazgos_confirmados_el_informe_lo_dice_claro():
    md = _informe()
    assert "ninguno" in md.lower()


def test_la_matriz_lista_las_pruebas_no_probadas():
    """Lo que falta por hacer es la mitad del valor de una matriz."""
    md = _informe()
    assert "WSTG-INPV-19" in md
    assert "Server-Side Request Forgery" in md


def test_el_informe_dice_cuanto_trafico_lo_respalda():
    md = _informe(flujos=1234)
    assert "1234" in md


def test_un_informe_sin_alcance_lo_advierte():
    """Un informe sin alcance declarado no se puede entregar: no se sabe
    contra que se probo."""
    md = _informe(alcance="")
    assert "sin alcance" in md.lower()


def test_el_informe_es_markdown_valido_y_sin_lineas_vacias_de_mas():
    md = _informe(hallazgos=[_h("WSTG-INPV-05", confirmado=True)])
    assert md.startswith("# ")
    assert "\n\n\n" not in md


# ------------------------------------------------- persistencia y pantalla
def test_el_store_guarda_los_estados_puestos_a_mano(tmp_path):
    from luzxfer.core.store import Store
    st = Store(tmp_path / "s.db")
    assert st.get_cobertura() == {}
    st.set_cobertura("WSTG-INPV-01", wstg.PASA)
    st.set_cobertura("WSTG-APIT-01", wstg.NO_APLICA)
    assert st.get_cobertura() == {"WSTG-INPV-01": wstg.PASA,
                                  "WSTG-APIT-01": wstg.NO_APLICA}
    st.set_cobertura("WSTG-INPV-01", wstg.NO_PROBADO)
    assert st.get_cobertura()["WSTG-INPV-01"] == wstg.NO_PROBADO
    st.close()


def test_los_estados_sobreviven_al_reinicio(tmp_path):
    from luzxfer.core.store import Store
    ruta = tmp_path / "s.db"
    st = Store(ruta)
    st.set_cobertura("WSTG-SESS-02", wstg.PASA)
    st.close()
    otra = Store(ruta)
    assert otra.get_cobertura() == {"WSTG-SESS-02": wstg.PASA}
    otra.close()


async def test_la_tecla_w_abre_la_matriz():
    from luzxfer.tui.app import LuzxferApp
    from luzxfer.tui.screens.cobertura import CoberturaScreen
    app = LuzxferApp(arrancar_motor=False)
    async with app.run_test(size=(130, 40)) as pilot:
        await pilot.pause()
        await pilot.press("w")
        await pilot.pause()
        assert isinstance(app.screen, CoberturaScreen)


async def test_la_matriz_lista_las_97_pruebas():
    from textual.widgets import DataTable

    from luzxfer.tui.app import LuzxferApp
    app = LuzxferApp(arrancar_motor=False)
    async with app.run_test(size=(130, 40)) as pilot:
        await pilot.pause()
        await pilot.press("w")
        await pilot.pause()
        assert app.screen.query_one("#cob-tabla", DataTable).row_count == 97


async def test_la_matriz_refleja_los_candidatos_que_ya_hay():
    from textual.widgets import DataTable

    from luzxfer.tui.app import LuzxferApp
    app = LuzxferApp(arrancar_motor=False)
    async with app.run_test(size=(130, 40)) as pilot:
        await pilot.pause()
        app.store.add_finding(_h("WSTG-INPV-01"))
        await pilot.press("w")
        await pilot.pause()
        tabla = app.screen.query_one("#cob-tabla", DataTable)
        fila = next(f for f in range(tabla.row_count)
                    if "WSTG-INPV-01" in str(tabla.get_row_at(f)[0]))
        assert "candidato" in str(tabla.get_row_at(fila)[2])


async def test_espacio_recorre_los_estados_manuales(tmp_path):
    from textual.widgets import DataTable

    from luzxfer.tui.app import LuzxferApp
    app = LuzxferApp(db=str(tmp_path / "s.db"), arrancar_motor=False)
    async with app.run_test(size=(130, 40)) as pilot:
        await pilot.pause()
        await pilot.press("w")
        await pilot.pause()
        tabla = app.screen.query_one("#cob-tabla", DataTable)
        tabla.move_cursor(row=0)
        ident = str(tabla.get_row_at(0)[0])

        await pilot.press("space")
        await pilot.pause()
        assert app.store.get_cobertura()[ident] == wstg.PASA
        await pilot.press("space")
        await pilot.pause()
        assert app.store.get_cobertura()[ident] == wstg.NO_APLICA
        await pilot.press("space")
        await pilot.pause()
        assert app.store.get_cobertura()[ident] == wstg.NO_PROBADO


async def test_no_se_puede_marcar_a_mano_lo_que_decide_la_evidencia():
    """Una prueba con un hallazgo confirmado FALLA, y el espacio no la
    cambia: un informe que diga que pasa teniendo la vulnerabilidad
    confirmada debajo seria inaceptable."""
    from textual.widgets import DataTable, Static

    from luzxfer.tui.app import LuzxferApp
    app = LuzxferApp(arrancar_motor=False)
    async with app.run_test(size=(130, 40)) as pilot:
        await pilot.pause()
        hid = app.store.add_finding(_h("WSTG-INPV-05"))
        app.store.set_confirmed(hid, True)
        await pilot.press("w")
        await pilot.pause()
        tabla = app.screen.query_one("#cob-tabla", DataTable)
        fila = next(f for f in range(tabla.row_count)
                    if "WSTG-INPV-05" in str(tabla.get_row_at(f)[0]))
        tabla.move_cursor(row=fila)
        await pilot.press("space")
        await pilot.pause()
        assert "FALLA" in str(
            app.screen.query_one("#cob-tabla", DataTable).get_row_at(fila)[2])
        assert "evidencia" in app.screen.query_one("#cob-aviso",
                                                   Static).render().plain.lower()


async def test_ctrl_g_escribe_el_informe_y_dice_donde(tmp_path, monkeypatch):
    from textual.widgets import Static

    from luzxfer.tui.app import LuzxferApp
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    app = LuzxferApp(db=str(tmp_path / "s.db"), sesion="cliente-x",
                     arrancar_motor=False)
    async with app.run_test(size=(130, 40)) as pilot:
        await pilot.pause()
        app.poner_alcance("+objetivo.com")
        app.store.add_finding(_h("WSTG-INPV-01"))
        await pilot.press("w")
        await pilot.pause()
        await pilot.press("ctrl+g")
        await pilot.pause()

        aviso = app.screen.query_one("#cob-aviso", Static).render().plain
        assert ".md" in aviso
        ruta = next(p for p in (tmp_path / "luzxfer" / "informes").iterdir())
        texto = ruta.read_text()
        assert "cliente-x" in texto and "+objetivo.com" in texto
        assert "WSTG-INPV-01" in texto


# ------------------------------------------ integridad de las tablas del informe
def _fila_candidato(md: str, marca: str) -> str:
    """La fila de la tabla de candidatos que contiene `marca`."""
    return next(ln for ln in md.splitlines()
               if ln.startswith("| ") and marca in ln)


def test_un_url_con_pipe_no_rompe_la_tabla_de_candidatos():
    """El informe va a un cliente: una URL con '|' (valida en una query)
    partia la fila en una columna de mas, y el cliente lo abre roto."""
    h = Finding(kind="REFLEJO", detail="reflejo de q",
                url="http://o.com/x?a=1|2|3", wstg=["WSTG-INPV-01"])
    md = _informe(hallazgos=[h])
    fila = _fila_candidato(md, "REFLEJO")
    # una fila de 4 columnas son exactamente 5 barras SIN escapar
    assert fila.count("|") - fila.count("\\|") == 5, \
        f"la fila tiene columnas de mas: {fila!r}"
    assert "o.com" in fila


def test_un_salto_de_linea_en_el_detalle_no_parte_la_fila():
    """Contenido reflejado o un plugin pueden meter un \\n; sin escaparlo,
    la fila se parte en dos y la segunda mitad es basura."""
    h = Finding(kind="FUGA", detail="linea uno\nlinea dos",
                url="http://o.com/x", wstg=["WSTG-INFO-02"])
    md = _informe(hallazgos=[h])
    fila = _fila_candidato(md, "FUGA")
    assert "linea uno" in fila and "linea dos" in fila, \
        "las dos partes tienen que seguir en la misma fila"
    assert "\n" not in fila


def test_un_salto_de_linea_en_la_url_no_rompe_el_hallazgo_confirmado():
    h = Finding(kind="DAST", detail="sqli", url="http://o.com/x\nInjected",
                wstg=["WSTG-INPV-05"], confirmed=True)
    md = _informe(hallazgos=[h])
    linea = next(ln for ln in md.splitlines() if "Dónde" in ln)
    assert "Injected" in linea, "la url no puede derramarse a otra linea"
