"""Como se presenta un cuerpo de respuesta en pantalla.

Un JSON minificado de dos mil caracteres en una sola linea no se puede
leer, y cuarenta kilobytes de una fuente .woff volcados como texto son
peores que inutiles: tapan la pantalla. Esto decide que hacer con cada
cuerpo segun lo que es.

Se usa el json de la libreria estandar y no se invoca jq. El resultado
es el mismo y jq es un binario externo: depender de el romperia la regla
de cero dependencias, que es lo que mantiene esto instalable en Termux.

Tres reglas que no se rompen:

  1. Nunca mentir sobre lo que llego. Si se reorganiza, se dice.
  2. Un JSON roto es un dato del pentest, no un estorbo que disimular.
  3. Los bytes crudos estan siempre a una tecla.

Esto vive en core/ y no en tui/ porque el dia que haya generacion de
reportes va a querer exactamente lo mismo.
"""
from __future__ import annotations

import json

from ..models import charset_de

# Lo que se trata como texto aunque el tipo no empiece por text/.
MARCAS_DE_TEXTO = (
    "json", "xml", "javascript", "ecmascript", "csv",
    "x-www-form-urlencoded", "graphql", "yaml",
)

# Lo que es binario aunque no lo diga el nombre del subtipo.
PREFIJOS_BINARIOS = ("image/", "audio/", "video/", "font/", "model/")
MARCAS_BINARIAS = ("octet-stream", "pdf", "zip", "gzip", "protobuf",
                   "msgpack", "wasm", "woff")

BYTES_POR_LINEA = 16

# Cuantas veces el limite de pantalla puede medir un cuerpo y todavia
# valer la pena reorganizarlo. Indentar engorda el texto entre 1,5 y 3
# veces, asi que con 4 cabe el caso normal de sobra y se corta el abuso.
UMBRAL_EMBELLECER = 4


def es_json(ctype: str) -> bool:
    """Cubre application/json, text/json y los +json tipo problem+json."""
    return "json" in (ctype or "").lower()


def embellecer_json(texto: str, indent: int = 2) -> str | None:
    """El JSON indentado, o None si no es JSON valido.

    `ensure_ascii=False` a proposito: ver \\u00f1 en pantalla no le sirve
    a nadie, y menos a quien esta buscando un reflejo de su payload.
    """
    try:
        return json.dumps(json.loads(texto), indent=indent, ensure_ascii=False)
    except (ValueError, RecursionError):
        return None


def es_binario(ctype: str, datos: bytes) -> bool:
    """Si el cuerpo no es texto que tenga sentido volcar en pantalla."""
    c = (ctype or "").lower()
    if c.startswith("text/") or any(m in c for m in MARCAS_DE_TEXTO):
        return False
    if c.startswith(PREFIJOS_BINARIOS) or any(m in c for m in MARCAS_BINARIAS):
        return True

    # sin un Content-Type util, deciden los bytes
    muestra = datos[:1024]
    if not muestra:
        return False
    if b"\x00" in muestra:
        return True
    raros = sum(1 for b in muestra if b < 9 or 13 < b < 32)
    return raros / len(muestra) > 0.05


def resumen_binario(datos: bytes, ctype: str) -> str:
    miles = f"{len(datos):,}".replace(",", ".")
    return f"{miles} bytes de {ctype or 'tipo desconocido'} (binario)"


def volcado_hex(datos: bytes, *, limite: int = 2048) -> str:
    """Los primeros bytes en hexadecimal, con su columna legible.

    Es la forma cruda de mirar bytes que no son texto: con esto se ve una
    cabecera magica, un cuerpo cifrado o un relleno sospechoso, que es
    para lo que uno abre un binario en un pentest.
    """
    trozo = datos[:limite]
    lineas = []
    for i in range(0, len(trozo), BYTES_POR_LINEA):
        fila = trozo[i:i + BYTES_POR_LINEA]
        hexa = " ".join(f"{b:02x}" for b in fila).ljust(BYTES_POR_LINEA * 3 - 1)
        legible = "".join(chr(b) if 32 <= b < 127 else "." for b in fila)
        lineas.append(f"{i:08x}  {hexa}  {legible}")
    return "\n".join(lineas)


def presentar(
    datos: bytes,
    ctype: str,
    *,
    bonito: bool,
    limite: int = 200_000,
) -> tuple[str, str]:
    """Devuelve (lo que se muestra, una nota que explica que se hizo).

    La nota es la parte que impide mentir: si el cuerpo se reorganizo, se
    recorto o no se pudo leer, queda dicho encima de lo que se ve.
    """
    if not datos:
        return "", ""

    if es_binario(ctype, datos):
        # ni en modo crudo tiene sentido escupirlo como texto: en crudo,
        # la forma de mirar bytes es el hexadecimal
        nota = resumen_binario(datos, ctype)
        if len(datos) > limite:
            nota += f" · se vuelcan los primeros {limite} bytes"
        return volcado_hex(datos, limite=min(limite, 4096)), nota

    notas = []

    # Por encima del umbral no se reorganiza, y ni siquiera se decodifica
    # entero. Parsear el JSON completo y volver a serializarlo para
    # quedarse con los primeros 200.000 caracteres es trabajo no acotado
    # para una salida acotada: 51 MB costaban 3 s de interfaz congelada y
    # 215 MB de pico, solo por seleccionar un flujo. Y no se pierde nada,
    # porque un JSON recortado no se puede parsear de todas formas.
    enorme = len(datos) > limite * UMBRAL_EMBELLECER
    if enorme:
        notas.append("demasiado grande para reorganizarlo")
        datos = datos[:limite + 1]

    # el charset que declare el servidor, no utf-8 a ciegas: si no,
    # los acentos de un iso-8859-1 salen como caracter de reemplazo
    texto = datos.decode(charset_de(ctype), "replace")

    if bonito and es_json(ctype) and not enorme:
        mejor = embellecer_json(texto)
        if mejor is not None:
            texto = mejor
            notas.append("JSON reorganizado para leerlo · p para verlo crudo")
        else:
            notas.append("el servidor dijo JSON y no es JSON valido")

    if len(texto) > limite:
        texto = texto[:limite] + "\n\n…"
        notas.append(f"recortado a {limite} caracteres")

    return texto, " · ".join(notas)
