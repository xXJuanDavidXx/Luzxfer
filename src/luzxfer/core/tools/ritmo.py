"""Acelerador: el tope de peticiones por segundo de todo un trabajo.

Vive aparte porque lo necesitan el Intruder y el DAST, y porque es la
pieza que impide que una herramienta de pruebas tumbe el entorno de un
cliente. Dos copias de esto que se separaran con el tiempo serian dos
topes distintos con el mismo nombre.
"""
from __future__ import annotations

import threading
import time


class Acelerador:
    """Un reloj compartido por todos los hilos de un trabajo.

    El tope es del trabajo entero, no de cada hilo. Con un sleep por
    hilo, cuatro hilos a diez por segundo mandarian cuarenta sin que
    nadie lo note, que es justo el accidente que el tope existe para
    evitar.

    La espera ocurre FUERA del lock: dentro solo se reparte el turno.
    """

    def __init__(self, por_segundo: float):
        self._intervalo = 1.0 / por_segundo if por_segundo > 0 else 0.0
        self._lock = threading.Lock()
        self._siguiente = 0.0

    def esperar(self) -> None:
        if not self._intervalo:
            return
        with self._lock:
            turno = max(time.monotonic(), self._siguiente)
            self._siguiente = turno + self._intervalo
        falta = turno - time.monotonic()
        if falta > 0:
            time.sleep(falta)
