"""Marcador de candidatos.

No es un escaner y no confirma nada: senala donde mirar. Un reflejo puede
estar perfectamente escapado en el contexto donde cae, y una cabecera
ausente puede ser irrelevante segun el activo. La validacion manual sigue
siendo del analista; esto solo evita que algo se pase por alto mientras
exploras.

Cada candidato trae los IDs de la WSTG que le aplican, que es lo que
despues alimenta la matriz de cobertura.
"""
from __future__ import annotations

from urllib.parse import parse_qs, urlsplit

from ..models import Finding, Flow

CABECERAS_SEGURIDAD = (
    "content-security-policy",
    "x-content-type-options",
    "x-frame-options",
    "referrer-policy",
)

# Valores demasiado cortos o comunes generan ruido sin aportar senal.
MIN_REFLEJO = 4
RUIDO = frozenset({
    "true", "false", "null", "none", "undefined",
    "1", "0", "on", "off", "yes", "no", "es", "en", "http", "https",
})

WSTG = {
    "REFLEJO": ["WSTG-INPV-01", "WSTG-INPV-02"],
    "COOKIE": ["WSTG-SESS-02"],
    "CABECERA": ["WSTG-CONF-07"],
    "FUGA": ["WSTG-INFO-02", "WSTG-INFO-08"],
    "ERROR": ["WSTG-ERRH-01"],
}


def _valores_enviados(flow: Flow) -> list[tuple[str, str]]:
    """Todo lo que mando el cliente: query y cuerpo si es form-urlencoded."""
    salida: list[tuple[str, str]] = []
    q = urlsplit(flow.request.url).query
    for k, vs in parse_qs(q).items():
        salida += [(k, v) for v in vs]

    ctype = (flow.request.header("content-type") or "").lower()
    if flow.request.body and "x-www-form-urlencoded" in ctype:
        try:
            cuerpo = flow.request.body.decode("utf-8", "replace")
            for k, vs in parse_qs(cuerpo).items():
                salida += [(k, v) for v in vs]
        except Exception:
            pass
    return salida


def analizar(flow: Flow) -> list[Finding]:
    """Devuelve los candidatos de un flujo. El almacen deduplica."""
    if flow.response is None:
        return []

    hallazgos: list[Finding] = []
    url = flow.request.url
    base = url.split("?")[0]
    fid = [flow.id] if flow.id else []
    cuerpo = flow.response.text()

    # 1. reflejo de entrada
    for nombre, valor in _valores_enviados(flow):
        if not valor or len(valor) < MIN_REFLEJO or valor.lower() in RUIDO:
            continue
        if valor in cuerpo:
            hallazgos.append(Finding(
                kind="REFLEJO",
                detail=f"el parametro '{nombre}' se refleja sin modificar",
                url=base, flow_ids=fid, wstg=WSTG["REFLEJO"],
                extra={"param": nombre, "valor": valor[:120]},
            ))

    # 2. atributos de cookie
    for sc in flow.response.headers_all("set-cookie"):
        bajo = sc.lower()
        faltan = [a for a in ("httponly", "secure", "samesite") if a not in bajo]
        if faltan:
            hallazgos.append(Finding(
                kind="COOKIE",
                detail=f"'{sc.split('=')[0].strip()}' sin {', '.join(faltan)}",
                url=base, flow_ids=fid, wstg=WSTG["COOKIE"],
                extra={"faltan": faltan},
            ))

    # 3. cabeceras de seguridad. Solo en HTML: en cada imagen seria ruido.
    #    Se registra por host, no por URL, porque es el mismo hallazgo en
    #    todas las rutas (es lo que distingue un reporte util de uno de scanner).
    host = flow.request.host
    if "text/html" in flow.response.content_type:
        presentes = {k.lower() for k, _ in flow.response.headers}
        faltan = [h for h in CABECERAS_SEGURIDAD if h not in presentes]
        if faltan:
            hallazgos.append(Finding(
                kind="CABECERA", detail=f"faltan: {', '.join(faltan)}",
                url=host, flow_ids=fid, wstg=WSTG["CABECERA"],
                extra={"faltan": faltan},
            ))

    # 4. fugas de version, tambien por host
    for h in ("server", "x-powered-by", "x-aspnet-version"):
        v = flow.response.header(h)
        if v:
            hallazgos.append(Finding(
                kind="FUGA", detail=f"{h}: {v}", url=host,
                flow_ids=fid, wstg=WSTG["FUGA"],
            ))

    # 5. error del servidor: vale la pena mirar la traza
    if flow.response.status >= 500:
        hallazgos.append(Finding(
            kind="ERROR", detail=f"respuesta {flow.response.status}",
            url=base, flow_ids=fid, wstg=WSTG["ERROR"],
        ))

    return hallazgos
