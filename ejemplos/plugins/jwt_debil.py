"""Plugin de ejemplo: JWT con alg=none o firmado con HMAC.

Busca tokens JWT en las cabeceras y en las cookies, y mira la cabecera
del token. Es una comprobacion pasiva: no manda nada, solo lee lo que
ya paso.

Copialo a ~/.local/share/luzxfer/plugins/ para que se cargue.
"""
import base64
import json

from luzxfer.core.models import Finding

NOMBRE = "JWT debil"


def registrar(api):
    api.detector(mira_los_jwt)


def _cabecera_jwt(token: str) -> dict | None:
    partes = token.split(".")
    if len(partes) != 3:
        return None
    try:
        crudo = partes[0] + "=" * (-len(partes[0]) % 4)
        return json.loads(base64.urlsafe_b64decode(crudo))
    except Exception:
        return None


def _tokens(flujo):
    for k, v in flujo.request.headers:
        bajo = k.lower()
        if bajo == "authorization" and v.lower().startswith("bearer "):
            yield v[7:].strip()
        elif bajo == "cookie":
            for trozo in v.split(";"):
                _, _, valor = trozo.partition("=")
                valor = valor.strip()
                if valor.count(".") == 2 and valor.startswith("ey"):
                    yield valor


def mira_los_jwt(flujo):
    hallazgos = []
    vistos = set()
    for token in _tokens(flujo):
        cab = _cabecera_jwt(token)
        if cab is None:
            continue
        alg = str(cab.get("alg", "")).lower()
        if alg in vistos:
            continue
        vistos.add(alg)

        if alg in ("none", ""):
            hallazgos.append(Finding(
                kind="JWT", url=flujo.request.host,
                detail=f"token con alg={cab.get('alg')!r}: la firma no se "
                       f"comprueba y se puede forjar cualquier identidad",
                wstg=["WSTG-ATHN-04"],
                flow_ids=[flujo.id] if flujo.id else [],
            ))
        elif alg.startswith("hs"):
            hallazgos.append(Finding(
                kind="JWT", url=flujo.request.host,
                detail=f"token firmado con {cab.get('alg')}: clave simetrica, "
                       f"vale la pena probar fuerza bruta del secreto",
                wstg=["WSTG-ATHN-04"],
                flow_ids=[flujo.id] if flujo.id else [],
            ))
    return hallazgos
