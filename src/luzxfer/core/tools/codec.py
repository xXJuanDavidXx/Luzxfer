"""Conversor: base64, url, hex, entidades HTML y JWT.

Lo que más importa aquí no es convertir —eso es librería estándar— sino
**no mentir**. Decir que algo es base64 cuando al abrirlo sale basura
binaria manda al analista a perseguir un fantasma, y una herramienta que
hace eso se usa una vez.

Por eso `decodificar()` devuelve `None` cuando no puede, en vez de
devolver algo que parezca un resultado, y `detectar()` solo ofrece una
interpretación si el resultado se puede leer y además **cambia algo**:
ofrecer «url» sobre un texto que no tiene nada que decodificar es ruido.
"""
from __future__ import annotations

import base64
import binascii
import html
import json
import re
from urllib.parse import quote, unquote_plus

FORMATOS = ("base64", "url", "hex", "html", "jwt")

_SOLO_HEX = re.compile(r"^[0-9a-fA-F]+$")
_PARECE_B64 = re.compile(r"^[A-Za-z0-9+/\-_]+={0,2}$")
_PARTE_JWT = re.compile(r"^[A-Za-z0-9\-_]+$")


def _legible(texto: str) -> bool:
    """Si el resultado es texto que una persona puede leer.

    No vale con que decodifique: casi cualquier cosa decodifica desde
    base64. Lo que decide si merece ofrecerse es si lo que sale se
    parece a texto.
    """
    if not texto:
        return False
    raros = sum(1 for c in texto if not c.isprintable() and c not in "\n\r\t")
    return raros / len(texto) < 0.05


# --------------------------------------------------------------- base64
def _dec_base64(texto: str) -> str | None:
    crudo = texto.strip()
    if not crudo or not _PARECE_B64.match(crudo):
        return None
    try:
        # el relleno sobra en base64url, que es lo que usan los JWT y
        # media web: se repone antes de decodificar
        datos = base64.urlsafe_b64decode(crudo + "=" * (-len(crudo) % 4))
    except (binascii.Error, ValueError):
        return None
    salida = datos.decode("utf-8", "replace")
    return salida if salida else None


def _cod_base64(texto: str) -> str:
    return base64.b64encode(texto.encode()).decode()


# ------------------------------------------------------------------ url
def _dec_url(texto: str) -> str | None:
    return unquote_plus(texto)


def _cod_url(texto: str) -> str:
    return quote(texto, safe="")


# ------------------------------------------------------------------ hex
def _dec_hex(texto: str) -> str | None:
    crudo = re.sub(r"[\s:]", "", texto)
    if not crudo or len(crudo) % 2 or not _SOLO_HEX.match(crudo):
        return None
    try:
        return bytes.fromhex(crudo).decode("utf-8", "replace")
    except ValueError:
        return None


def _cod_hex(texto: str) -> str:
    return texto.encode().hex()


# ----------------------------------------------------------------- html
def _dec_html(texto: str) -> str | None:
    return html.unescape(texto)


def _cod_html(texto: str) -> str:
    return html.escape(texto, quote=True)


# ------------------------------------------------------------------ jwt
AVISO_JWT = ("La firma NO se comprueba: esto solo abre el token. "
             "Que se lea no quiere decir que sea valido.")


def _dec_jwt(texto: str) -> str | None:
    partes = texto.strip().split(".")
    if len(partes) != 3 or not all(_PARTE_JWT.match(p) for p in partes[:2]):
        return None

    trozos = []
    for etiqueta, parte in (("cabecera", partes[0]), ("cuerpo", partes[1])):
        crudo = _dec_base64(parte)
        if crudo is None:
            return None
        try:
            bonito = json.dumps(json.loads(crudo), indent=2, ensure_ascii=False)
        except ValueError:
            return None             # un JWT lleva JSON en las dos partes
        trozos.append(f"--- {etiqueta} ---\n{bonito}")

    trozos.append(f"--- firma ---\n{partes[2] or '(vacia)'}")
    trozos.append(f"\n{AVISO_JWT}")
    return "\n\n".join(trozos)


_DECOD = {"base64": _dec_base64, "url": _dec_url, "hex": _dec_hex,
          "html": _dec_html, "jwt": _dec_jwt}
_COD = {"base64": _cod_base64, "url": _cod_url, "hex": _cod_hex,
        "html": _cod_html}


def decodificar(texto: str, formato: str) -> str | None:
    """Lo decodificado, o None si ese texto no es de ese formato."""
    if formato not in _DECOD:
        raise ValueError(f"formato desconocido: {formato!r}; "
                         f"hay: {', '.join(FORMATOS)}")
    return _DECOD[formato](texto)


def codificar(texto: str, formato: str) -> str:
    if formato not in _COD:
        raise ValueError(f"no se puede codificar a {formato!r}; "
                         f"hay: {', '.join(sorted(_COD))}")
    return _COD[formato](texto)


def detectar(texto: str) -> list[tuple[str, str]]:
    """Qué podría ser ese texto, con lo que saldría de cada cosa.

    Solo entra una interpretación si el resultado **se puede leer** y
    **cambia algo**. Un texto normal no ofrece nada, que es la respuesta
    correcta: una lista que siempre tiene opciones no informa.
    """
    crudo = texto.strip()
    if not crudo:
        return []

    salida: list[tuple[str, str]] = []
    # el jwt primero: es el mas especifico y el mas util de reconocer
    for formato in ("jwt", "base64", "url", "hex", "html"):
        try:
            r = _DECOD[formato](crudo)
        except Exception:
            continue
        if r is None or r == crudo or not _legible(r):
            continue
        salida.append((formato, r))
    return salida


# ------------------------------------- lo que vale la pena abrir de un flujo
def _trozos_de(flujo) -> list[tuple[str, str]]:
    """(origen, valor) de todo lo que podria estar codificado."""
    salida: list[tuple[str, str]] = []
    for k, v in flujo.request.headers:
        bajo = k.lower()
        if bajo == "authorization":
            # «Bearer xxx» o «Basic xxx»: lo que interesa es el segundo
            partes = v.split(None, 1)
            salida.append((k, partes[1].strip() if len(partes) > 1 else v))
        elif bajo == "cookie":
            for trozo in v.split(";"):
                _, _, valor = trozo.partition("=")
                if valor.strip():
                    salida.append((k, valor.strip()))

    from urllib.parse import parse_qsl, urlsplit
    for nombre, valor in parse_qsl(urlsplit(flujo.request.url).query):
        if valor:
            salida.append((f"parametro {nombre}", valor))
    return salida


def candidato(flujo) -> tuple[str, str]:
    """Lo mas prometedor que haya en una peticion, y de donde salio.

    Abrir el conversor vacio obliga a copiar y pegar a mano justo lo que
    la herramienta ya tiene delante. Se prefiere un JWT porque es lo mas
    especifico; si no hay, cualquier cosa que se reconozca.
    """
    opciones = _trozos_de(flujo)
    for origen, valor in opciones:
        if _dec_jwt(valor) is not None:
            return valor, origen
    for origen, valor in opciones:
        if detectar(valor):
            return valor, origen
    return "", ""
