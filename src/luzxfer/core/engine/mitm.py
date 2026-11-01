"""Motor de mitmproxy: HTTPS, HTTP/2 y WebSockets.

El segundo motor, y la prueba de si la interfaz `Engine` valia lo que
prometia: cambiar de motor tenia que ser cambiar una clase, y esto lo
comprueba o lo desmiente.

Va en un extra opcional (`pip install 'luzxfer[mitm]'`) porque arrastra
cryptography, que compila. En un PC se instala sin problema; en Termux
no, y por eso el motor integrado sigue siendo el de por defecto: la
razon de ser de este proyecto frente a Burp es correr donde Burp no
corre.

mitmproxy es asincrono y tiene su propio bucle, asi que corre en un hilo
con un bucle propio. Los Flow salen de ahi y llegan a `on_flow` desde
ese hilo, igual que en el motor integrado: quien los reciba es
responsable de saltar a su propio bucle.
"""
from __future__ import annotations

import asyncio
import threading
import time

from ..models import Flow, Request, Response
from .base import Engine, EngineInfo


def disponible() -> bool:
    """Si el extra esta instalado en esta maquina."""
    try:
        import mitmproxy.tools.dump  # noqa: F401
    except Exception:
        return False
    return True


class _Captura:
    """Addon de mitmproxy: convierte sus flujos en los nuestros."""

    def __init__(self, emitir):
        self.emitir = emitir

    def response(self, flow) -> None:          # mitmproxy.http.HTTPFlow
        try:
            self.emitir(_a_flujo(flow))
        except Exception:
            # un fallo del consumidor nunca tumba el proxy, igual que en
            # el motor integrado
            pass


def _a_flujo(f) -> Flow:
    """De un HTTPFlow de mitmproxy a un Flow nuestro."""
    pet = f.request
    req = Request(
        method=pet.method,
        url=pet.pretty_url,
        http_version=pet.http_version,
        headers=[(k, v) for k, v in pet.headers.items(multi=True)],
        body=pet.raw_content or b"",
    )
    resp = None
    inicio = getattr(pet, "timestamp_start", None) or time.time()
    duracion = 0
    if f.response is not None:
        r = f.response
        resp = Response(
            status=r.status_code,
            reason=r.reason or "",
            http_version=r.http_version,
            headers=[(k, v) for k, v in r.headers.items(multi=True)],
            body=r.raw_content or b"",
        )
        fin = getattr(r, "timestamp_end", None)
        if fin:
            duracion = int((fin - inicio) * 1000)

    return Flow(request=req, response=resp, started=inicio,
                duration_ms=duracion,
                error=str(f.error) if f.error else "")


class Mitm(Engine):
    """Motor sobre mitmproxy. Intercepta TLS; necesita el extra [mitm].

    La interceptacion en vuelo de luzxfer todavia NO pasa por aqui: el
    `request` hook de mitmproxy corre en su bucle, y bloquearlo
    detendria todos los demas flujos a la vez. Hacerlo bien necesita
    flow.intercept() y reanudar desde el bucle, y eso es un trabajo
    aparte. Queda dicho en vez de fingir que funciona.
    """

    def __init__(self, on_flow, *, host="127.0.0.1", port=8080,
                 upstream: str | None = None, **_ignorados):
        super().__init__(on_flow, host=host, port=port)
        self.upstream = upstream
        self._hilo: threading.Thread | None = None
        self._bucle: asyncio.AbstractEventLoop | None = None
        self._maestro = None
        self._listo = threading.Event()
        self.error: str = ""

    @staticmethod
    def info() -> EngineInfo:
        return EngineInfo(name="mitmproxy", tls=True, http2=True,
                          websockets=True,
                          needs="" if disponible()
                          else "pip install 'luzxfer[mitm]'")

    @staticmethod
    def available() -> bool:
        return disponible()

    # ------------------------------------------------------------------
    def start(self) -> None:
        if self._running:
            return
        if not disponible():
            raise RuntimeError(
                "el motor de mitmproxy no esta instalado: "
                "pip install 'luzxfer[mitm]'")
        self._listo.clear()
        self._hilo = threading.Thread(target=self._correr,
                                      name="luzxfer-mitm", daemon=True)
        self._hilo.start()
        # No basta con que el bucle arranque: DumpMaster.run() ata el
        # socket despues, y devolver aqui diria «escuchando en :8080»
        # con nada atado todavia. Se espera a que haya direccion de
        # verdad, que es lo unico que significa estar escuchando.
        self._listo.wait(timeout=20)
        if self.error:
            raise RuntimeError(self.error)
        limite = time.time() + 20
        while time.time() < limite:
            if self._direcciones():
                break
            if self.error:
                raise RuntimeError(self.error)
            time.sleep(0.02)
        else:
            self.stop()
            raise RuntimeError("mitmproxy no llego a escuchar en 20 s")
        self._running = True

    def _direcciones(self) -> list:
        try:
            return list(self._maestro.addons.get("proxyserver").listen_addrs())
        except Exception:
            return []

    def _correr(self) -> None:
        from mitmproxy import options
        from mitmproxy.tools.dump import DumpMaster

        bucle = asyncio.new_event_loop()
        asyncio.set_event_loop(bucle)
        self._bucle = bucle
        try:
            modo = ([f"reverse:{self.upstream}"] if self.upstream
                    else ["regular"])
            opts = options.Options(listen_host=self.host,
                                   listen_port=self.port, mode=modo)
            # sin termlog ni dumper: la salida va a la TUI, y mitmproxy
            # escribiendo en el terminal la destrozaria
            self._maestro = DumpMaster(opts, loop=bucle,
                                       with_termlog=False, with_dumper=False)
            self._maestro.addons.add(_Captura(self._emitir))
            bucle.call_soon(self._listo.set)
            bucle.run_until_complete(self._maestro.run())
        except Exception as e:
            self.error = f"{type(e).__name__}: {e}"
            self._listo.set()
        finally:
            self._running = False

    def _emitir(self, flujo: Flow) -> None:
        try:
            self.on_flow(flujo)
        except Exception:
            pass

    @property
    def puerto_real(self) -> int:
        """El puerto que acabo escuchando. Con port=0 lo elige el sistema."""
        dirs = self._direcciones()
        return dirs[0][1] if dirs else self.port

    def stop(self) -> None:
        if self._maestro is not None and self._bucle is not None:
            self._bucle.call_soon_threadsafe(self._maestro.shutdown)
        if self._hilo is not None:
            self._hilo.join(timeout=10)
        self._maestro = None
        self._bucle = None
        self._hilo = None
        self._running = False
