"""Sacar una peticion de la herramienta: `curl` y crudo.

Es de lo que mas se usa a diario en Burp y lo que permite entregarle a un
cliente algo que puede ejecutar el mismo. Un hallazgo que solo existe
dentro de tu pantalla es dificil de defender; uno que se reproduce con
una linea pegada en una terminal, no.

La regla aqui es la del proyecto: **lo que sale tiene que reproducir lo
que viajo**. Un `curl` que se parece a la peticion pero manda otra cosa
es peor que no tener exportacion, porque el cliente lo ejecuta, no pasa
nada, y concluye que el hallazgo era falso.

De ahi tres decisiones que parecen raras y no lo son:

  - **Las cabeceras salen todas, incluida `Content-Length`.** curl
    calcularia la suya, pero quitarla haria que el comando mandara algo
    distinto de lo capturado en cuanto el servidor dependa de ella. Si
    editas el cuerpo, ajusta o borra esa cabecera: hay un aviso.
  - **`--data-raw`, nunca `-d` ni `--data-binary`.** Esto no es estilo:
    es la diferencia entre exportar una peticion y exportar una fuga de
    archivos. `-d` y `--data-binary` interpretan un `@` inicial como
    «lee este archivo del disco y mandalo». Un cuerpo capturado que
    empiece por `@` —`@/etc/passwd`, sin ir mas lejos— haria que el
    comando leyera ese archivo de la maquina de quien lo pegue y se lo
    enviara al objetivo. `--data-raw` es lo mismo sin esa
    interpretacion, y manda la cadena tal cual, saltos incluidos.
    Hay un test que lo comprueba ejecutando el comando de verdad.
  - **Un cuerpo que no es texto va en base64 y se descomprime en la
    tuberia.** Meter bytes crudos entre comillas de shell los rompe. El
    comando queda mas largo, pero manda los mismos bytes, que es el
    unico criterio que importa.
"""
from __future__ import annotations

import base64

from ..models import Flow, Request

# Cabeceras que curl pone solas y que, repetidas, se mandan dos veces.
# No se quita ninguna: se avisa. Decidir por el analista que una
# cabecera sobra es exactamente como un export deja de ser evidencia.
AVISO_LONGITUD = (
    "Lleva Content-Length de la peticion original: si editas el cuerpo, "
    "ajustala o borrala.")


def _citar(texto: str) -> str:
    """Entre comillas SIEMPRE, aunque shlex no lo creyera necesario.

    `shlex.quote` deja desnudo lo que no tiene metacaracteres, y entonces
    añadirle a mano un `&otro=1` —que es lo primero que hace cualquiera
    con un curl exportado— parte el comando en dos y manda el proceso al
    fondo. Con un cuerpo de peticion eso no es hipotetico: editarlo es
    justo para lo que se exporta.

    Asi que la forma no depende del contenido: lo que sale citado hoy
    sigue citado manana, y lo que el analista escriba dentro no cambia
    el significado de nada.
    """
    return "'" + texto.replace("'", "'\\''") + "'"


def _es_texto(datos: bytes) -> bool:
    """Si estos bytes se pueden poner entre comillas sin romperlos.

    No vale con que decodifiquen: un NUL pasa por utf-8 y el shell lo
    corta ahi, asi que el comando mandaria un cuerpo truncado sin decir
    nada.
    """
    if b"\x00" in datos:
        return False
    try:
        datos.decode("utf-8")
    except UnicodeDecodeError:
        return False
    return True


def a_curl(peticion: Request, *, insecure: bool = False) -> str:
    """La peticion como un comando `curl` que manda lo mismo.

    `insecure` añade `-k`. Esta apagado por defecto a proposito: debilitar
    la validacion de TLS sin que nadie lo haya pedido es la clase de
    ayuda que acaba en un informe que nadie puede reproducir.
    """
    partes = ["curl"]

    # -X solo cuando hace falta. Con cuerpo, curl asume POST, asi que un
    # GET con cuerpo —que existe, y es justo el caso interesante— hay que
    # forzarlo o saldria convertido en POST.
    metodo = peticion.method.upper()
    if metodo != "GET" or peticion.body:
        partes += ["-X", _citar(metodo)]

    if insecure:
        partes.append("-k")

    for nombre, valor in peticion.headers:
        partes += ["-H", _citar(f"{nombre}: {valor}")]

    cuerpo = peticion.body
    if cuerpo:
        if _es_texto(cuerpo):
            # --data-raw y no --data-binary: ver el encabezado del modulo.
            # Con --data-binary, un cuerpo que empiece por @ hace que curl
            # lea ese archivo del disco de quien pegue el comando.
            partes += ["--data-raw", _citar(cuerpo.decode("utf-8"))]
        else:
            # bytes crudos: no se pueden citar, asi que viajan en base64
            # y se deshacen en la tuberia. El comando manda los mismos
            # bytes, que es lo unico que importa.
            partes += ["--data-binary", "@-"]
            b64 = base64.b64encode(cuerpo).decode("ascii")
            partes.append(_citar(peticion.url))
            return f"printf %s {_citar(b64)} | base64 -d | " + \
                   " ".join(partes)

    partes.append(_citar(peticion.url))
    return " ".join(partes)


def avisos_curl(peticion: Request) -> list[str]:
    """Lo que conviene saber antes de pegar ese comando en otro sitio."""
    salida: list[str] = []
    if peticion.header("content-length") is not None and peticion.body:
        salida.append(AVISO_LONGITUD)
    if peticion.body and not _es_texto(peticion.body):
        salida.append(
            "El cuerpo no es texto, asi que va en base64 y se deshace con "
            "`base64 -d`. Necesita coreutils o busybox.")
    if peticion.http_version.upper().startswith("HTTP/2"):
        salida.append(
            "La original era HTTP/2 y curl negociara lo que pueda; añade "
            "`--http2` si el servidor lo necesita.")
    return salida


def a_crudo(flujo: Flow, *, lado: str = "peticion") -> str:
    """La peticion o la respuesta tal cual, para pegar en un informe.

    Es lo que ya sabe hacer el modelo; vive aqui para que la interfaz
    tenga un solo sitio al que pedir exportaciones en vez de llamar a
    `raw()` por su cuenta y que cada pantalla lo haga distinto.
    """
    if lado == "peticion":
        return flujo.request.raw()
    r = flujo.response
    if r is None:
        return "(sin respuesta)"
    # el cuerpo va descomprimido y con su charset: pegar gzip en un
    # informe no le sirve a nadie, y es el mismo fallo del brotli
    return r.raw_headers() + "\r\n\r\n" + r.text()
