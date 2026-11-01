"""Estado de cobertura WSTG y generación del informe.

Lo que convierte un historial en un entregable. Dos reglas mandan:

  - **La evidencia gana a la opinión.** Si hay un hallazgo confirmado con
    un ID, esa prueba FALLA aunque alguien la hubiera marcado como que
    pasa. Un informe que diga que una prueba pasó teniendo una
    vulnerabilidad confirmada debajo es inaceptable.
  - **No haber mirado y no aplicar no son lo mismo.** Se cuentan aparte y
    lo que no aplica sale del denominador: si una prueba no tiene sentido
    en este objetivo, no es trabajo pendiente, y meterla haría parecer
    que falta algo que no falta.

El informe sale en Markdown porque es lo que se pega en un correo, se
convierte a PDF o se mete en un repositorio sin pelearse con nada.
"""
from __future__ import annotations

import time

from ..models import Finding
from . import wstg


def calcular(hallazgos: list[Finding],
             manuales: dict[str, str]) -> dict[str, str]:
    """El estado de cada una de las 97 pruebas.

    `manuales` son los estados que puso una persona. Los IDs que no
    existen en el catálogo se ignoran: un hallazgo escrito a mano puede
    traer cualquier cosa, y eso no puede romper la matriz.
    """
    estados = {ident: wstg.NO_PROBADO for ident in wstg.CATALOGO}

    for ident, estado in manuales.items():
        if ident in estados and estado in wstg.ESTADOS:
            estados[ident] = estado

    for h in hallazgos:
        for ident in h.wstg:
            if ident not in estados:
                continue
            if h.confirmed:
                estados[ident] = wstg.FALLA          # la evidencia manda
            elif estados[ident] == wstg.NO_PROBADO:
                estados[ident] = wstg.PROBADO
    return estados


def resumen(estados: dict[str, str]) -> dict[str, int]:
    cuentas = dict.fromkeys(wstg.ESTADOS, 0)
    for e in estados.values():
        cuentas[e] = cuentas.get(e, 0) + 1
    return cuentas


def porcentaje(estados: dict[str, str]) -> float:
    """Qué parte del trabajo que aplica está hecha.

    Lo que no aplica sale del denominador. Y «hecho» no incluye
    PROBADO: tener un candidato no es haber dictaminado, y contarlo
    como cobertura es como una matriz empieza a mentir.
    """
    aplican = [e for e in estados.values() if e != wstg.NO_APLICA]
    if not aplican:
        return 0.0
    hechas = sum(1 for e in aplican if e in (wstg.PASA, wstg.FALLA))
    return round(hechas / len(aplican) * 100, 1)


# --------------------------------------------------------------- informe
_ETIQUETA = {
    wstg.NO_PROBADO: "no probado",
    wstg.PROBADO: "con candidatos",
    wstg.PASA: "pasa",
    wstg.FALLA: "FALLA",
    wstg.NO_APLICA: "no aplica",
}


def informe(
    *,
    sesion: str,
    hallazgos: list[Finding],
    estados: dict[str, str],
    alcance: str,
    flujos: int,
) -> str:
    """El informe completo en Markdown."""
    # se normaliza a las 97: que el informe reviente por una clave que
    # falta, justo al generar el entregable, seria el peor momento
    estados = {i: estados.get(i, wstg.NO_PROBADO) for i in wstg.CATALOGO}

    confirmados = [h for h in hallazgos if h.confirmed]
    candidatos = [h for h in hallazgos if not h.confirmed]
    cuentas = resumen(estados)
    hoy = time.strftime("%Y-%m-%d")

    p: list[str] = [
        f"# Informe de pruebas — {sesion}",
        "",
        f"Fecha: {hoy}  ·  Tráfico analizado: {flujos} flujos  ·  "
        f"Metodología: OWASP WSTG v4.2",
        "",
        "## Alcance",
        "",
    ]
    if alcance.strip():
        p += ["```", alcance.strip(), "```", ""]
    else:
        p += ["**Sin alcance declarado.** Este informe no debería "
              "entregarse así: sin alcance no consta contra qué se probó.",
              ""]

    p += [
        "## Resumen",
        "",
        "| estado | pruebas |",
        "| --- | --- |",
        f"| FALLA (hallazgo confirmado) | {cuentas[wstg.FALLA]} |",
        f"| Pasa | {cuentas[wstg.PASA]} |",
        f"| Con candidatos sin dictaminar | {cuentas[wstg.PROBADO]} |",
        f"| No probado | {cuentas[wstg.NO_PROBADO]} |",
        f"| No aplica | {cuentas[wstg.NO_APLICA]} |",
        "",
        f"Cobertura sobre lo que aplica: **{porcentaje(estados)} %**. "
        f"Un candidato sin dictaminar no cuenta como cobertura.",
        "",
        "## Hallazgos confirmados",
        "",
    ]
    if confirmados:
        for h in confirmados:
            ids = ", ".join(h.wstg) if h.wstg else "sin prueba WSTG asociada"
            p += [f"### {h.kind} — {h.detail}", "",
                  f"- **WSTG:** {ids}",
                  f"- **Dónde:** {h.url}"]
            if h.severity:
                p.append(f"- **Severidad:** {h.severity}")
            if h.flow_ids:
                p.append(f"- **Evidencia:** flujos {', '.join(str(i) for i in h.flow_ids)}")
            if h.justification:
                p += ["", h.justification]
            p.append("")
    else:
        p += ["Ninguno. Nada se ha confirmado todavía: lo que hay son "
              "candidatos, y están más abajo.", ""]

    p += ["## Cobertura WSTG", ""]
    for cat in wstg.CATEGORIAS:
        pruebas = wstg.por_categoria(cat.codigo)
        p += [f"### {cat.seccion} {cat.nombre} ({cat.codigo})", "",
              "| id | prueba | estado |", "| --- | --- | --- |"]
        for pr in pruebas:
            p.append(f"| {pr.id} | {pr.titulo} | {_ETIQUETA[estados[pr.id]]} |")
        p.append("")

    if candidatos:
        p += ["## Candidatos sin confirmar", "",
              "Esto **no son hallazgos**: son cosas que la herramienta "
              "señaló y que nadie ha validado todavía. Un reflejo puede "
              "estar perfectamente escapado en el contexto donde cae.",
              "",
              "| tipo | detalle | dónde | WSTG |", "| --- | --- | --- | --- |"]
        for h in candidatos:
            ids = ", ".join(h.wstg) if h.wstg else "—"
            detalle = h.detail.replace("|", "\\|")
            p.append(f"| {h.kind} | {detalle} | {h.url} | {ids} |")
        p.append("")

    p += ["---", "",
          "Generado por luzxfer. Los estados «pasa» y «no aplica» los puso "
          "una persona; «FALLA» viene de un hallazgo confirmado a mano."]

    # se juntan evitando lineas en blanco de mas: un Markdown con huecos
    # dobles se ve mal en cuanto alguien lo convierte a PDF
    texto = "\n".join(p)
    while "\n\n\n" in texto:
        texto = texto.replace("\n\n\n", "\n\n")
    return texto.rstrip() + "\n"
