"""Tests de la paleta y de la configuracion.

Lo que importa aqui: que un dedazo en un archivo de texto no impida
arrancar la herramienta, y que los nombres sigan significando lo mismo
cambie el tema que cambie.
"""
from __future__ import annotations

from dataclasses import fields

from luzxfer.tui import paleta


def _escribir(tmp_path, texto):
    r = tmp_path / "config.ini"
    r.write_text(texto, encoding="utf-8")
    return r


def test_los_tres_temas_definen_todos_los_colores():
    nombres = {f.name for f in fields(paleta.Paleta)}
    for nombre, tema in paleta.TEMAS.items():
        puestos = {f.name for f in fields(tema) if getattr(tema, f.name)}
        assert puestos == nombres, f"al tema {nombre} le faltan colores"


def test_todos_los_colores_son_hex_validos():
    for nombre, tema in paleta.TEMAS.items():
        for f in fields(tema):
            v = getattr(tema, f.name)
            assert paleta._HEX.match(v), f"{nombre}.{f.name} = {v!r}"


def test_el_tema_claro_no_es_el_oscuro_invertido():
    """Sobre blanco hacen falta tonos mas oscuros y saturados para el
    mismo contraste; invertir deja los grises ilegibles."""
    assert paleta.CLARO.texto != paleta.OSCURO.texto
    # el texto del claro tiene que ser oscuro de verdad
    assert int(paleta.CLARO.texto[1:3], 16) < 0x40
    assert int(paleta.OSCURO.texto[1:3], 16) > 0xC0


def test_el_contraste_separa_bien_del_peligro():
    """Si alguien necesita alto contraste, lo ultimo que puede pasar es
    que el verde y el rojo se parezcan."""
    bien = paleta.CONTRASTE.bien
    peligro = paleta.CONTRASTE.peligro
    assert bien != peligro
    rb, gb = int(bien[1:3], 16), int(bien[3:5], 16)
    rp, gp = int(peligro[1:3], 16), int(peligro[3:5], 16)
    assert abs(rb - rp) > 0x80 or abs(gb - gp) > 0x80


# --------------------------------------------------------- configuracion
def test_sin_archivo_se_usa_el_oscuro(tmp_path):
    p, avisos = paleta.leer(tmp_path / "no-existe.ini")
    assert p is paleta.OSCURO and avisos == []


def test_se_elige_un_tema(tmp_path):
    p, avisos = paleta.leer(_escribir(tmp_path, "[tema]\nnombre = claro\n"))
    assert p is paleta.CLARO and avisos == []


def test_un_tema_desconocido_avisa_y_no_impide_arrancar(tmp_path):
    p, avisos = paleta.leer(_escribir(tmp_path, "[tema]\nnombre = unicornio\n"))
    assert p is paleta.OSCURO
    assert avisos and "unicornio" in avisos[0] and "oscuro" in avisos[0]


def test_se_puede_cambiar_un_color_suelto(tmp_path):
    p, avisos = paleta.leer(_escribir(
        tmp_path, "[tema]\nnombre = oscuro\n[colores]\npeligro = #ff00ff\n"))
    assert p.peligro == "#ff00ff"
    assert p.bien == paleta.OSCURO.bien, "lo demas no se toca"
    assert avisos == []


def test_un_color_suelto_se_aplica_sobre_el_tema_elegido(tmp_path):
    p, _ = paleta.leer(_escribir(
        tmp_path, "[tema]\nnombre = claro\n[colores]\nacento = #123456\n"))
    assert p.acento == "#123456" and p.texto == paleta.CLARO.texto


def test_un_color_que_no_existe_avisa_y_sigue(tmp_path):
    p, avisos = paleta.leer(_escribir(
        tmp_path, "[colores]\nazulito = #112233\npeligro = #ff0000\n"))
    assert p.peligro == "#ff0000", "el valido se aplica igual"
    assert avisos and "azulito" in avisos[0]


def test_un_color_mal_escrito_avisa_y_no_rompe(tmp_path):
    """Un dedazo en un archivo de texto no es razon para no arrancar
    una herramienta de trabajo."""
    for malo in ("rojo", "#xyz", "#12345", "ff0000", ""):
        p, avisos = paleta.leer(_escribir(
            tmp_path, f"[colores]\npeligro = {malo}\n"))
        assert p.peligro == paleta.OSCURO.peligro
        assert avisos, f"{malo!r} tendria que avisar"


def test_un_archivo_corrupto_no_impide_arrancar(tmp_path):
    p, avisos = paleta.leer(_escribir(tmp_path, "esto no es un ini [[[\n"))
    assert p is paleta.OSCURO and avisos


def test_la_ruta_respeta_xdg(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    assert paleta.ruta_config() == tmp_path / "luzxfer" / "config.ini"
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    from pathlib import Path
    assert paleta.ruta_config() == Path.home() / ".config" / "luzxfer" / "config.ini"


def test_cargar_cambia_la_paleta_del_programa(tmp_path):
    antes = paleta.ACTUAL
    try:
        avisos = paleta.cargar(_escribir(tmp_path, "[tema]\nnombre = contraste\n"))
        assert avisos == [] and paleta.ACTUAL is paleta.CONTRASTE
    finally:
        paleta.ACTUAL = antes


# ----------------------------------------- enchufado de verdad en la app
async def test_la_hoja_de_estilos_recibe_la_paleta():
    """Sin esto el tema cambiaria los colores del codigo pero no los de
    la hoja, y un tema claro quedaria con el fondo negro."""
    from luzxfer.tui.app import LuzxferApp
    app = LuzxferApp(arrancar_motor=False)
    async with app.run_test() as pilot:
        await pilot.pause()
        vars_ = app.get_css_variables()
        assert vars_["lx-peligro"] == paleta.ACTUAL.peligro
        assert vars_["lx-fondo"] == paleta.ACTUAL.fondo
        assert "lx-texto" in vars_ and "lx-modal" in vars_


async def test_cambiar_el_tema_cambia_lo_que_se_pinta():
    """La prueba que importa: que el tema llegue al pixel."""
    from textual.widgets import DataTable, Static

    from luzxfer.core.models import Flow, Request, Response
    from luzxfer.tui.app import LuzxferApp

    def flujo():
        return Flow(request=Request(method="GET", url="http://o.com/x",
                                    headers=[("Host", "o.com")]),
                    response=Response(status=200, reason="OK", body=b"ok",
                                      headers=[("Content-Type", "text/html")]))

    antes = paleta.ACTUAL
    try:
        colores = {}
        for nombre in ("oscuro", "claro"):
            paleta.ACTUAL = paleta.TEMAS[nombre]
            app = LuzxferApp(arrancar_motor=False)
            async with app.run_test() as pilot:
                app._ingresar(flujo())
                await pilot.pause()
                app.query_one("#flujos", DataTable).move_cursor(row=0)
                await pilot.pause()
                estilos = app.query_one("#estado", Static).render().spans
                colores[nombre] = {str(s.style) for s in estilos}
        assert colores["oscuro"] != colores["claro"], \
            "cambiar el tema no cambio nada de lo pintado"

        # Textual pinta en rgb(), no en hex: comparar la cadena hex
        # contra el span no casa nunca, y asi fue como este test paso
        # a dar un falso fallo la primera vez.
        def _rgb(hexa):
            return (f"rgb({int(hexa[1:3], 16)},{int(hexa[3:5], 16)},"
                    f"{int(hexa[5:7], 16)})")

        assert any(_rgb(paleta.CLARO.texto) == c for c in colores["claro"])
        assert any(_rgb(paleta.OSCURO.texto) == c for c in colores["oscuro"])
    finally:
        paleta.ACTUAL = antes


def test_el_cli_acepta_el_tema():
    import subprocess
    r = subprocess.run(["./venv/bin/luzxfer", "--help"],
                       capture_output=True, text=True, timeout=30)
    assert "--tema" in r.stdout
    for t in ("oscuro", "claro", "contraste"):
        assert t in r.stdout
