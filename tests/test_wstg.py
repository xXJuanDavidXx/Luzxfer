"""Tests del catalogo WSTG.

Lo que se prueba aqui es sobre todo que los identificadores sean los de
verdad: un informe de cliente con IDs inventados es peor que no tener
matriz, porque el cliente los va a buscar en el documento oficial.
"""
from __future__ import annotations

import pytest

from luzxfer.core.tools import wstg


def test_las_doce_categorias_con_sus_cuentas():
    """Cuentas tomadas del documento oficial de la WSTG v4.2."""
    esperado = {"INFO": 10, "CONF": 11, "IDNT": 5, "ATHN": 10, "ATHZ": 4,
                "SESS": 9, "INPV": 19, "ERRH": 2, "CRYP": 4, "BUSL": 9,
                "CLNT": 13, "APIT": 1}
    reales = {c.codigo: len(wstg.por_categoria(c.codigo))
              for c in wstg.CATEGORIAS}
    assert reales == esperado
    assert len(wstg.CATALOGO) == sum(esperado.values()) == 97


def test_los_identificadores_tienen_la_forma_oficial():
    for ident, p in wstg.CATALOGO.items():
        assert ident == f"WSTG-{p.categoria}-{p.numero:02d}"
        assert p.titulo and p.titulo[0].isupper()


@pytest.mark.parametrize("ident,titulo", [
    ("WSTG-INFO-02", "Fingerprint Web Server"),
    ("WSTG-CONF-07", "Test HTTP Strict Transport Security"),
    ("WSTG-ATHZ-01", "Testing Directory Traversal File Include"),
    ("WSTG-SESS-02", "Testing for Cookies Attributes"),
    ("WSTG-INPV-01", "Testing for Reflected Cross Site Scripting"),
    ("WSTG-INPV-05", "Testing for SQL Injection"),
    ("WSTG-INPV-19", "Testing for Server-Side Request Forgery"),
    ("WSTG-ERRH-01", "Testing for Improper Error Handling"),
    ("WSTG-CLNT-09", "Testing for Clickjacking"),
    ("WSTG-APIT-01", "Testing GraphQL"),
])
def test_identificadores_concretos_contra_el_documento(ident, titulo):
    assert wstg.CATALOGO[ident].titulo == titulo


def test_la_seccion_se_puede_citar():
    assert wstg.CATALOGO["WSTG-INPV-05"].seccion == "4.7.5"
    assert wstg.CATALOGO["WSTG-APIT-01"].seccion == "4.12.1"


def test_no_existen_los_que_no_existen():
    for falso in ("WSTG-INFO-11", "WSTG-APIT-02", "WSTG-XXXX-01", "INPV-01"):
        assert not wstg.existe(falso)


def test_todos_los_ids_que_usa_la_herramienta_existen_de_verdad():
    """La auditoria que importa: si el detector o el DAST etiquetan con
    un ID inventado, la matriz miente sobre lo que se probo."""
    from luzxfer.core.tools import dast, detector

    usados = set()
    for ids in detector.WSTG.values():
        usados.update(ids)
    for p in dast.PRUEBAS.values():
        usados.update(p.wstg)

    inventados = sorted(i for i in usados if not wstg.existe(i))
    assert inventados == [], f"IDs que no estan en la WSTG: {inventados}"


# -------------------------- la auditoria semantica, no solo la ortografica
def test_las_cabeceras_de_seguridad_no_se_cuelgan_de_un_id_prestado():
    """CONF-07 es «Test HTTP Strict Transport Security». Usarlo porque
    falta un CSP diria en el informe que se probo HSTS cuando no se
    probo. Existir el ID no basta: tiene que ser el que corresponde."""
    from luzxfer.core.models import Flow, Request, Response
    from luzxfer.core.tools import detector

    f = Flow(
        request=Request(method="GET", url="https://o.com/", headers=[("Host", "o.com")]),
        response=Response(status=200, body=b"<html>x</html>",
                          headers=[("Content-Type", "text/html")]),
    )
    f.id = 1
    por_tipo = {}
    for h in detector.analizar(f):
        por_tipo.setdefault(h.kind, []).append(h)

    # clickjacking: ese SI tiene prueba propia en la WSTG
    clic = [h for h in por_tipo.get("CABECERA", []) if "WSTG-CLNT-09" in h.wstg]
    assert clic, "falta X-Frame-Options y eso es WSTG-CLNT-09"

    # HSTS sobre https: su prueba es CONF-07, y ahora si se comprueba
    hsts = [h for h in por_tipo.get("CABECERA", []) if "WSTG-CONF-07" in h.wstg]
    assert hsts, "sobre https, la ausencia de HSTS es WSTG-CONF-07"

    # el endurecimiento sin prueba propia NO toma prestado un ID ajeno
    sueltas = [h for h in por_tipo.get("CABECERA", []) if not h.wstg]
    assert sueltas, "CSP y X-Content-Type-Options no tienen prueba WSTG propia"
    assert any("sin prueba WSTG" in h.detail for h in sueltas)


def test_sobre_http_no_se_reclama_hsts():
    """HSTS no tiene sentido en claro: reclamarlo seria ruido."""
    from luzxfer.core.models import Flow, Request, Response
    from luzxfer.core.tools import detector

    f = Flow(request=Request(method="GET", url="http://o.com/",
                             headers=[("Host", "o.com")]),
             response=Response(status=200, body=b"<html>x</html>",
                               headers=[("Content-Type", "text/html")]))
    f.id = 1
    assert not any("WSTG-CONF-07" in h.wstg for h in detector.analizar(f))
