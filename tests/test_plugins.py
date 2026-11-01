"""Tests de la API de plugins.

Un plugin es Python que corre con tus privilegios dentro de la
herramienta, asi que la mitad de estos tests son sobre contencion: que
uno roto no tumbe la aplicacion, que uno lento no congele nada que no
sea lo suyo, y que se vea siempre que hay plugins cargados.
"""
from __future__ import annotations

from luzxfer.core import plugins
from luzxfer.core.models import Flow, Request, Response


def _flujo(url="http://o.com/x", cuerpo=b"<html>hola</html>"):
    return Flow(request=Request(method="GET", url=url,
                                headers=[("Host", "o.com")]),
                response=Response(status=200, body=cuerpo,
                                  headers=[("Content-Type", "text/html")]))


def _escribir(carpeta, nombre, texto):
    carpeta.mkdir(parents=True, exist_ok=True)
    (carpeta / nombre).write_text(texto)


BUENO = '''
NOMBRE = "detector de saludos"

def registrar(api):
    api.detector(busca_hola)

def busca_hola(flujo):
    from luzxfer.core.models import Finding
    if b"hola" in (flujo.response.body if flujo.response else b""):
        return [Finding(kind="SALUDO", detail="dice hola",
                        url=flujo.request.url, wstg=["WSTG-INFO-05"])]
    return []
'''


# ------------------------------------------------------------- cargar
def test_sin_carpeta_no_hay_plugins_y_no_pasa_nada(tmp_path):
    reg, errores = plugins.cargar(tmp_path / "no-existe")
    assert reg.cargados == [] and errores == []
    assert reg.analizar(_flujo()) == []


def test_carga_un_plugin_y_lo_usa(tmp_path):
    _escribir(tmp_path, "saludos.py", BUENO)
    reg, errores = plugins.cargar(tmp_path)
    assert errores == []
    assert [p.nombre for p in reg.cargados] == ["detector de saludos"]

    hallazgos = reg.analizar(_flujo())
    assert len(hallazgos) == 1 and hallazgos[0].kind == "SALUDO"


def test_un_plugin_sin_nombre_usa_el_del_archivo(tmp_path):
    _escribir(tmp_path, "anonimo.py", "def registrar(api):\n    pass\n")
    reg, _ = plugins.cargar(tmp_path)
    assert [p.nombre for p in reg.cargados] == ["anonimo"]


def test_los_archivos_que_no_son_plugins_se_ignoran(tmp_path):
    _escribir(tmp_path, "notas.txt", "esto no es un plugin")
    _escribir(tmp_path, "_privado.py", "raise RuntimeError('no deberia correr')")
    reg, errores = plugins.cargar(tmp_path)
    assert reg.cargados == [] and errores == []


# ------------------------------------------- contencion: lo que importa
def test_un_plugin_que_revienta_al_cargar_no_tumba_nada(tmp_path):
    _escribir(tmp_path, "roto.py", "import no_existe_este_modulo\n")
    _escribir(tmp_path, "saludos.py", BUENO)
    reg, errores = plugins.cargar(tmp_path)
    assert len(errores) == 1 and "roto" in errores[0]
    assert [p.nombre for p in reg.cargados] == ["detector de saludos"], \
        "el bueno tiene que cargarse igual"


def test_un_plugin_sin_registrar_se_reporta(tmp_path):
    _escribir(tmp_path, "vacio.py", "NOMBRE = 'nada'\n")
    reg, errores = plugins.cargar(tmp_path)
    assert reg.cargados == []
    assert len(errores) == 1 and "registrar" in errores[0]


def test_un_detector_que_revienta_no_corta_el_analisis(tmp_path):
    """Un plugin de un tercero no puede dejar al analista sin detector."""
    _escribir(tmp_path, "explota.py", '''
def registrar(api):
    api.detector(boom)

def boom(flujo):
    raise RuntimeError("revienta")
''')
    _escribir(tmp_path, "saludos.py", BUENO)
    reg, _ = plugins.cargar(tmp_path)
    hallazgos = reg.analizar(_flujo())
    assert [h.kind for h in hallazgos] == ["SALUDO"]
    assert reg.fallos, "el fallo se anota, no se traga en silencio"


def test_un_detector_que_devuelve_basura_se_ignora(tmp_path):
    _escribir(tmp_path, "raro.py", '''
def registrar(api):
    api.detector(lambda f: "esto no es una lista de hallazgos")
''')
    reg, _ = plugins.cargar(tmp_path)
    assert reg.analizar(_flujo()) == []


def test_solo_se_aceptan_hallazgos_de_verdad(tmp_path):
    _escribir(tmp_path, "mezcla.py", '''
def registrar(api):
    api.detector(mezcla)

def mezcla(flujo):
    from luzxfer.core.models import Finding
    return [Finding(kind="BUENO", detail="d", url="u"), "basura", 42]
''')
    reg, _ = plugins.cargar(tmp_path)
    hallazgos = reg.analizar(_flujo())
    assert [h.kind for h in hallazgos] == ["BUENO"]


# ------------------------------------------------------- pruebas DAST
def test_un_plugin_puede_anadir_una_prueba_activa(tmp_path):
    _escribir(tmp_path, "activa.py", '''
from luzxfer.core.tools.dast import Prueba

def registrar(api):
    api.prueba(Prueba(
        nombre="mia", titulo="prueba del plugin",
        payloads=["MIPAYLOAD"], wstg=["WSTG-INPV-01"],
        evalua=lambda cuerpo, estado, cab: (
            "aparece" if "MIPAYLOAD" in cuerpo else None),
    ))
''')
    reg, errores = plugins.cargar(tmp_path)
    assert errores == []
    assert [p.nombre for p in reg.pruebas] == ["mia"]


def test_una_prueba_con_un_wstg_inventado_se_rechaza(tmp_path):
    """Un plugin no puede meter IDs falsos en la matriz de cobertura: el
    informe va a un cliente que los va a buscar."""
    _escribir(tmp_path, "mala.py", '''
from luzxfer.core.tools.dast import Prueba

def registrar(api):
    api.prueba(Prueba(nombre="falsa", titulo="t", payloads=["x"],
                      wstg=["WSTG-INVENTADO-99"], evalua=lambda c, e, h: None))
''')
    reg, errores = plugins.cargar(tmp_path)
    assert reg.pruebas == []
    assert errores and "WSTG-INVENTADO-99" in errores[0]


def test_un_detector_que_devuelve_un_wstg_inventado_lo_pierde(tmp_path):
    """El hallazgo se queda; el ID falso no, para que no ensucie la
    matriz. Perder el hallazgo entero seria peor."""
    _escribir(tmp_path, "casi.py", '''
def registrar(api):
    api.detector(casi)

def casi(flujo):
    from luzxfer.core.models import Finding
    return [Finding(kind="X", detail="d", url="u",
                    wstg=["WSTG-INPV-01", "WSTG-FALSO-77"])]
''')
    reg, _ = plugins.cargar(tmp_path)
    h = reg.analizar(_flujo())[0]
    assert h.wstg == ["WSTG-INPV-01"]


# ------------------------------------------------- enchufado de verdad
async def test_la_app_carga_los_plugins_y_sus_detectores_corren(tmp_path, monkeypatch):
    from luzxfer.tui.app import LuzxferApp
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    _escribir(tmp_path / "luzxfer" / "plugins", "saludos.py", BUENO)

    app = LuzxferApp(arrancar_motor=False)
    async with app.run_test() as pilot:
        await pilot.pause()
        assert [p.nombre for p in app.plugins.cargados] == ["detector de saludos"]
        app._ingresar(_flujo())
        await pilot.pause()
        assert any(h.kind == "SALUDO" for h in app.store.list_findings())


async def test_los_detectores_de_siempre_siguen_corriendo(tmp_path, monkeypatch):
    """Un plugin suma, no reemplaza."""
    from luzxfer.tui.app import LuzxferApp
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    _escribir(tmp_path / "luzxfer" / "plugins", "saludos.py", BUENO)

    app = LuzxferApp(arrancar_motor=False)
    async with app.run_test() as pilot:
        await pilot.pause()
        app._ingresar(_flujo("http://o.com/b?q=REFLEJADO",
                             b"<html>hola REFLEJADO</html>"))
        await pilot.pause()
        tipos = {h.kind for h in app.store.list_findings()}
        assert "SALUDO" in tipos and "REFLEJO" in tipos


async def test_sin_plugins_no_se_carga_nada(tmp_path, monkeypatch):
    from luzxfer.tui.app import LuzxferApp
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    _escribir(tmp_path / "luzxfer" / "plugins", "saludos.py", BUENO)

    app = LuzxferApp(arrancar_motor=False, cargar_plugins=False)
    async with app.run_test() as pilot:
        await pilot.pause()
        assert app.plugins.cargados == []


async def test_un_plugin_roto_se_avisa_y_la_app_arranca(tmp_path, monkeypatch):
    from luzxfer.tui.app import LuzxferApp
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    _escribir(tmp_path / "luzxfer" / "plugins", "roto.py", "import no_existe\n")

    app = LuzxferApp(arrancar_motor=False)
    async with app.run_test() as pilot:
        await pilot.pause()
        assert app.is_running
        assert app._errores_plugins and "roto" in app._errores_plugins[0]


async def test_los_plugins_cargados_se_ven_en_la_barra(tmp_path, monkeypatch):
    """Que haya codigo de terceros corriendo no puede ser invisible."""
    from textual.widgets import Static

    from luzxfer.tui.app import LuzxferApp
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    _escribir(tmp_path / "luzxfer" / "plugins", "saludos.py", BUENO)

    app = LuzxferApp(arrancar_motor=False)
    async with app.run_test() as pilot:
        await pilot.pause()
        assert "plugin" in app.query_one("#estado", Static).render().plain.lower()


def test_el_dast_usa_las_pruebas_de_los_plugins(tmp_path):
    from luzxfer.core.tools import alcance as alc
    from luzxfer.core.tools import dast

    _escribir(tmp_path, "activa.py", '''
from luzxfer.core.tools.dast import Prueba

def registrar(api):
    api.prueba(Prueba(nombre="mia", titulo="t", payloads=["A", "B"],
                      wstg=["WSTG-INPV-01"],
                      evalua=lambda c, e, h: None))
''')
    reg, _ = plugins.cargar(tmp_path)
    crudo = "GET /x?a=1 HTTP/1.1\r\nHost: objetivo.com\r\n\r\n"
    sin = dast.Escaneo(crudo, alc.Alcance.desde_texto("+objetivo.com"))
    con = dast.Escaneo(crudo, alc.Alcance.desde_texto("+objetivo.com"),
                       pruebas_extra=reg.pruebas)
    assert con.total == sin.total + 2


# -------------------------------------- el ejemplo que trae el proyecto
def test_el_plugin_de_ejemplo_carga_y_funciona(tmp_path):
    """Un ejemplo que no se prueba es un ejemplo que se pudre."""
    import base64
    import json
    import shutil
    from pathlib import Path

    origen = Path(__file__).parent.parent / "ejemplos" / "plugins" / "jwt_debil.py"
    assert origen.is_file(), "el ejemplo tiene que existir"
    shutil.copy(origen, tmp_path / "jwt_debil.py")

    reg, errores = plugins.cargar(tmp_path)
    assert errores == []
    assert [p.nombre for p in reg.cargados] == ["JWT debil"]

    def _tok(alg):
        cab = base64.urlsafe_b64encode(
            json.dumps({"alg": alg, "typ": "JWT"}).encode()).decode().rstrip("=")
        return f"{cab}.eyJhIjoxfQ.firma"

    f = Flow(request=Request(method="GET", url="http://o.com/api",
                             headers=[("Host", "o.com"),
                                      ("Authorization", f"Bearer {_tok('none')}")]),
             response=Response(status=200))
    h = reg.analizar(f)
    assert len(h) == 1 and h[0].kind == "JWT" and "alg=" in h[0].detail
    assert h[0].wstg == ["WSTG-ATHN-04"]

    f2 = Flow(request=Request(method="GET", url="http://o.com/api",
                              headers=[("Host", "o.com"),
                                       ("Authorization", f"Bearer {_tok('HS256')}")]),
              response=Response(status=200))
    assert "simetrica" in reg.analizar(f2)[0].detail

    f3 = Flow(request=Request(method="GET", url="http://o.com/api",
                              headers=[("Host", "o.com"),
                                       ("Authorization", "Bearer no-es-un-jwt")]),
              response=Response(status=200))
    assert reg.analizar(f3) == []
