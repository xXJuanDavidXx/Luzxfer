"""Tests de la entrega de flujos del motor al nucleo.

El fallo que originó esto: los dos motores hacían

    try:
        self.on_flow(flujo)
    except Exception:
        pass

Que el proxy sobreviva a un consumidor roto es lo correcto —si se cayera,
el navegador del analista dejaría de cargar a mitad de una prueba—. Pero
perder el flujo **callando** significa que, con el almacén bloqueado o el
disco lleno, el tráfico desaparece, el historial se queda vacío y el
analista concluye que el objetivo no habla. Un falso negativo fabricado
por la herramienta, que es la peor clase: no deja rastro.

Lo que se prueba aquí es que no se pierde el equilibrio: el proxy sigue
en pie **y** la pérdida se cuenta y se explica.
"""
from __future__ import annotations

import threading

import pytest

from luzxfer.core.engine.base import Engine, EngineInfo
from luzxfer.core.models import Flow, Request, Response


class _Motor(Engine):
    """Un motor de mentira: solo sirve para ejercitar `_emitir`."""

    @staticmethod
    def info() -> EngineInfo:
        return EngineInfo(name="prueba", tls=False, http2=False,
                          websockets=False)

    def start(self) -> None:
        self._running = True

    def stop(self) -> None:
        self._running = False


def _flujo(url: str = "http://o.com/x") -> Flow:
    return Flow(request=Request(method="GET", url=url,
                                headers=[("Host", "o.com")]),
                response=Response(status=200, body=b"ok"))


def test_un_flujo_entregado_llega():
    recibidos = []
    m = _Motor(recibidos.append)
    m._emitir(_flujo())
    assert len(recibidos) == 1
    assert m.perdidos == 0 and m.ultimo_fallo == ""


def test_un_consumidor_que_revienta_no_tumba_el_motor():
    """Si el proxy se cayera, el analista perderia mucho mas que un flujo:
    el navegador dejaria de cargar a mitad de una prueba."""
    def revienta(_f):
        raise RuntimeError("almacen bloqueado")

    m = _Motor(revienta)
    m.start()
    m._emitir(_flujo())          # si propagara, el test falla aqui
    assert m.running, "el motor sigue en pie despues del fallo"


def test_un_flujo_perdido_se_cuenta():
    """Lo que no puede pasar es que desaparezca sin dejar rastro."""
    def revienta(_f):
        raise RuntimeError("almacen bloqueado")

    m = _Motor(revienta)
    m._emitir(_flujo())
    assert m.perdidos == 1


def test_se_guarda_el_motivo():
    """Sin el motivo no se sabe si fue el disco, el almacen o un cierre."""
    def revienta(_f):
        raise RuntimeError("database is locked")

    m = _Motor(revienta)
    m._emitir(_flujo())
    assert "RuntimeError" in m.ultimo_fallo
    assert "database is locked" in m.ultimo_fallo


def test_se_cuentan_todos_los_perdidos():
    def revienta(_f):
        raise OSError("disco lleno")

    m = _Motor(revienta)
    for _ in range(5):
        m._emitir(_flujo())
    assert m.perdidos == 5


def test_el_motivo_es_el_del_ultimo():
    """Al diagnosticar interesa lo que pasa ahora, no lo primero que paso."""
    fallos = iter([RuntimeError("almacen bloqueado"), OSError("disco lleno")])

    def revienta(_f):
        raise next(fallos)

    m = _Motor(revienta)
    m._emitir(_flujo())
    m._emitir(_flujo())
    assert "disco lleno" in m.ultimo_fallo


def test_perder_uno_no_impide_entregar_el_siguiente():
    """Un fallo puntual —un bloqueo momentaneo del almacen— no puede
    dejar al analista sin el resto de la sesion."""
    recibidos = []
    estado = {"falla": True}

    def a_veces(f):
        if estado["falla"]:
            estado["falla"] = False
            raise RuntimeError("bloqueado un momento")
        recibidos.append(f)

    m = _Motor(a_veces)
    m._emitir(_flujo("http://o.com/1"))
    m._emitir(_flujo("http://o.com/2"))
    assert m.perdidos == 1
    assert len(recibidos) == 1, "el siguiente tiene que pasar"


def test_la_cuenta_aguanta_varios_hilos():
    """Los dos motores entregan desde hilos distintos: el integrado usa
    un ThreadingHTTPServer y mitmproxy su propio bucle. Una cuenta que
    se pierde bajo concurrencia subestima el dano, que es justo lo que
    no puede pasar en un contador de evidencia perdida."""
    def revienta(_f):
        raise RuntimeError("no")

    m = _Motor(revienta)
    hilos = [threading.Thread(target=lambda: [m._emitir(_flujo())
                                              for _ in range(50)])
             for _ in range(8)]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join()
    assert m.perdidos == 400


# ------------------------------------------- los motores de verdad
def test_los_dos_motores_heredan_la_entrega():
    """Si un motor se trae su propio `_emitir`, vuelve el fallo callado
    solo en ese motor, que es como se va una correccion sin que nadie
    lo note."""
    from luzxfer.core.engine.builtin import Builtin
    assert Builtin._emitir is Engine._emitir

    mitm = pytest.importorskip("luzxfer.core.engine.mitm",
                               reason="el extra [mitm] no esta instalado")
    assert mitm.Mitm._emitir is Engine._emitir


# ------------------------------------------------- lo que ve el analista
async def test_la_barra_avisa_de_los_flujos_perdidos():
    """Contar la perdida por dentro no sirve de nada si no se enseña.

    Este es el test que de verdad cierra el fallo: lo que estaba mal no
    era que se perdiera un flujo, era que el analista no podia saberlo.
    """
    from textual.widgets import Static

    from luzxfer.tui.app import LuzxferApp

    def revienta(_f):
        raise RuntimeError("database is locked")

    app = LuzxferApp(arrancar_motor=False)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        barra = app.query_one("#estado", Static)
        assert "PERDIDO" not in barra.render().plain, \
            "sin perdidas no se avisa de nada"

        app.engine = _Motor(revienta)
        app.engine.start()
        app.engine._emitir(_flujo())
        app.actualizar_estado()
        await pilot.pause()

        texto = barra.render().plain
        assert "1 PERDIDO" in texto, f"la barra no lo dice: {texto!r}"


async def test_el_aviso_dice_el_motivo_y_no_se_repite():
    """El contador dice cuantos; para arreglarlo hace falta el porque.

    Pero repetirlo en cada refresco taparia la pantalla, y la barra ya
    mantiene la cuenta visible.
    """
    from luzxfer.tui.app import LuzxferApp

    def revienta(_f):
        raise RuntimeError("database is locked")

    app = LuzxferApp(arrancar_motor=False)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.engine = _Motor(revienta)
        app.engine.start()
        app.engine._emitir(_flujo())

        avisos = []
        app.notify = lambda msg, **kw: avisos.append((msg, kw))

        app.actualizar_estado()
        app.actualizar_estado()
        app.actualizar_estado()
        await pilot.pause()

        assert len(avisos) == 1, f"se aviso {len(avisos)} veces"
        assert "database is locked" in avisos[0][0]
        assert avisos[0][1].get("severity") == "error"

        # una perdida NUEVA si vuelve a avisar: es informacion nueva
        app.engine._emitir(_flujo())
        app.actualizar_estado()
        await pilot.pause()
        assert len(avisos) == 2
