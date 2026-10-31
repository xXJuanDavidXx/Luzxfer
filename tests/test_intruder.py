"""Tests del Intruder.

Esto dispara peticiones contra sistemas ajenos, asi que casi todo lo que
se prueba aqui es «no hagas nada que el analista no pidio»: no mutar sus
payloads, no inventarse posiciones, no mandar mas de lo que dijo.
"""
from __future__ import annotations

import pytest

from luzxfer.core.tools import intruder

PET = ('POST /api/login HTTP/1.1\r\nHost: o.com\r\n\r\n'
       '{"user":"§admin§","pass":"§x§"}')


# --------------------------------------------------------- marcadores
def test_posiciones_encuentra_los_pares():
    assert len(intruder.posiciones(PET)) == 2
    assert intruder.valores_iniciales(PET) == ["admin", "x"]


def test_sin_marcadores_no_hay_posiciones():
    assert intruder.posiciones("GET / HTTP/1.1\r\nHost: o.com\r\n\r\n") == []
    assert intruder.valores_iniciales("GET / HTTP/1.1\r\n\r\n") == []


def test_marcadores_impares_fallan_con_mensaje():
    """Un ataque silenciosamente raro es peor que un error a la cara."""
    with pytest.raises(intruder.ErrorAtaque) as e:
        intruder.posiciones('GET /?q=§a§b§ HTTP/1.1\r\nHost: o\r\n\r\n')
    assert "marcador" in str(e.value).lower()


def test_una_posicion_vacia_es_valida():
    """§§ marca un hueco donde no habia nada. Es legitimo: asi se inyecta
    en un parametro que llega vacio."""
    crudo = 'GET /?q=§§ HTTP/1.1\r\nHost: o\r\n\r\n'
    assert len(intruder.posiciones(crudo)) == 1
    assert intruder.valores_iniciales(crudo) == [""]


def test_posiciones_en_cualquier_parte_de_la_peticion():
    crudo = '§GET§ /§ruta§ HTTP/1.1\r\nHost: §o.com§\r\nX-Y: §z§\r\n\r\n'
    assert intruder.valores_iniciales(crudo) == ["GET", "ruta", "o.com", "z"]


# -------------------------------------------------------- sustitucion
def test_sustituir_respeta_el_orden_y_el_resto_del_texto():
    salida = intruder.sustituir(PET, ["' OR 1=1--", "xyz"])
    assert '{"user":"\' OR 1=1--","pass":"xyz"}' in salida
    assert intruder.MARCADOR not in salida
    assert salida.startswith("POST /api/login HTTP/1.1")


def test_sustituir_exige_un_payload_por_posicion():
    with pytest.raises(intruder.ErrorAtaque):
        intruder.sustituir(PET, ["solo-uno"])
    with pytest.raises(intruder.ErrorAtaque):
        intruder.sustituir(PET, ["uno", "dos", "tres"])


def test_un_payload_que_contiene_el_marcador_no_corre_las_posiciones():
    """Si alguien mete § en un payload, no debe convertirse en una
    posicion nueva: la sustitucion se hace de una pasada."""
    salida = intruder.sustituir(PET, ["a§b", "c"])
    assert '{"user":"a§b","pass":"c"}' in salida


def test_sustituir_sin_posiciones_devuelve_lo_mismo():
    crudo = "GET / HTTP/1.1\r\nHost: o\r\n\r\n"
    assert intruder.sustituir(crudo, []) == crudo


# ------------------------------------------------------------- marcar
def test_marcar_envuelve_el_rango_pedido():
    crudo = "GET /?q=admin HTTP/1.1\r\nHost: o\r\n\r\n"
    i = crudo.index("admin")
    assert intruder.marcar(crudo, i, i + 5) == (
        "GET /?q=§admin§ HTTP/1.1\r\nHost: o\r\n\r\n")


def test_marcar_dos_veces_deja_dos_posiciones():
    crudo = "GET /?a=1&b=2 HTTP/1.1\r\nHost: o\r\n\r\n"
    crudo = intruder.marcar(crudo, crudo.index("1"), crudo.index("1") + 1)
    crudo = intruder.marcar(crudo, crudo.index("2"), crudo.index("2") + 1)
    assert intruder.valores_iniciales(crudo) == ["1", "2"]


def test_marcar_rechaza_un_rango_imposible():
    crudo = "GET / HTTP/1.1\r\n\r\n"
    for inicio, fin in ((5, 2), (-1, 3), (0, 999)):
        with pytest.raises(intruder.ErrorAtaque):
            intruder.marcar(crudo, inicio, fin)


# -------------------------------------------------------- codificacion
def test_avisa_de_payloads_que_no_sobreviven_a_latin1():
    """build_raw codifica en latin-1 con 'replace', asi que un payload en
    UTF-8 se muta solo. Un fuzzer que cambia tus payloads sin decirlo es
    peor que uno que se niega a mandarlos."""
    assert intruder.avisos_de_codificacion(["admin", "' OR 1=1--"]) == []
    assert intruder.avisos_de_codificacion(["señor"]) == []   # ñ si esta en latin-1
    malos = intruder.avisos_de_codificacion(["日本", "ok", "🔥"])
    assert "日本" in malos and "🔥" in malos and "ok" not in malos


def test_los_avisos_no_se_repiten():
    assert intruder.avisos_de_codificacion(["日本", "日本"]) == ["日本"]


# ------------------------------------------------------- los cuatro modos
def test_sniper_una_posicion_a_la_vez():
    """Las demas posiciones conservan su valor inicial, asi que cada
    peticion del ataque sigue siendo una peticion valida."""
    r = list(intruder.combinar(intruder.Modo.SNIPER, [["a", "b"]], 2, ["X", "Y"]))
    assert r == [["a", "Y"], ["b", "Y"], ["X", "a"], ["X", "b"]]


def test_ariete_el_mismo_payload_en_todas():
    r = list(intruder.combinar(intruder.Modo.ARIETE, [["a", "b"]], 2, ["X", "Y"]))
    assert r == [["a", "a"], ["b", "b"]]


def test_horquilla_va_en_paralelo_y_para_en_el_mas_corto():
    r = list(intruder.combinar(intruder.Modo.HORQUILLA,
                               [["a", "b", "c"], ["1", "2"]], 2, ["X", "Y"]))
    assert r == [["a", "1"], ["b", "2"]]


def test_racimo_es_el_producto_cartesiano():
    r = list(intruder.combinar(intruder.Modo.RACIMO,
                               [["a", "b"], ["1", "2", "3"]], 2, ["X", "Y"]))
    assert len(r) == 6
    assert ["a", "1"] in r and ["b", "3"] in r


@pytest.mark.parametrize("modo,conjuntos,n,esperado", [
    (intruder.Modo.SNIPER,    [["a", "b", "c"]],             2, 6),
    (intruder.Modo.SNIPER,    [["a"]],                       1, 1),
    (intruder.Modo.ARIETE,    [["a", "b", "c"]],             2, 3),
    (intruder.Modo.HORQUILLA, [["a", "b", "c"], ["1", "2"]], 2, 2),
    (intruder.Modo.RACIMO,    [["a", "b"], ["1", "2", "3"]], 2, 6),
])
def test_cuantas_coincide_con_lo_que_se_genera(modo, conjuntos, n, esperado):
    assert intruder.cuantas(modo, conjuntos, n) == esperado
    assert len(list(intruder.combinar(modo, conjuntos, n, ["X"] * n))) == esperado


def test_un_racimo_grande_no_se_materializa():
    """Tres listas de 100 son un millon de peticiones. El total tiene que
    saberse ANTES de lanzar, para poder avisar, y sin construirlo."""
    conjuntos = [[str(i) for i in range(100)] for _ in range(3)]
    assert intruder.cuantas(intruder.Modo.RACIMO, conjuntos, 3) == 1_000_000
    it = intruder.combinar(intruder.Modo.RACIMO, conjuntos, 3, ["X"] * 3)
    assert next(iter(it)) == ["0", "0", "0"]


def test_los_modos_de_varios_conjuntos_exigen_uno_por_posicion():
    for modo in (intruder.Modo.HORQUILLA, intruder.Modo.RACIMO):
        with pytest.raises(intruder.ErrorAtaque):
            list(intruder.combinar(modo, [["a"]], 2, ["X", "Y"]))
        with pytest.raises(intruder.ErrorAtaque):
            intruder.cuantas(modo, [["a"]], 2)


def test_sin_posiciones_o_sin_payloads_no_hay_ataque():
    with pytest.raises(intruder.ErrorAtaque):
        intruder.cuantas(intruder.Modo.SNIPER, [["a"]], 0)
    with pytest.raises(intruder.ErrorAtaque):
        intruder.cuantas(intruder.Modo.SNIPER, [[]], 1)
    with pytest.raises(intruder.ErrorAtaque):
        intruder.cuantas(intruder.Modo.SNIPER, [], 1)


# ---------------------------------------------------- fuentes de payloads
def test_desde_archivo_ignora_vacias_y_comentarios(tmp_path):
    f = tmp_path / "w.txt"
    f.write_text("admin\n\n# comentario\nroot\n  \npassword\n")
    assert intruder.desde_archivo(f) == ["admin", "root", "password"]


def test_desde_archivo_aguanta_bytes_que_no_son_utf8(tmp_path):
    """Las listas de payloads de verdad no son utf-8 limpio."""
    f = tmp_path / "w.txt"
    f.write_bytes(b"admin\n\xff\xfe\nroot\n")
    salida = intruder.desde_archivo(f)
    assert salida[0] == "admin" and "root" in salida


def test_desde_archivo_respeta_el_limite(tmp_path):
    f = tmp_path / "w.txt"
    f.write_text("\n".join(str(i) for i in range(500)))
    assert len(intruder.desde_archivo(f, limite=10)) == 10


def test_desde_archivo_conserva_los_espacios_internos(tmp_path):
    """' or 1=1 -- ' lleva espacios a proposito; solo se quita el salto."""
    f = tmp_path / "w.txt"
    f.write_text("' or 1=1 -- \nnormal\n")
    assert intruder.desde_archivo(f)[0] == "' or 1=1 -- "


def test_desde_archivo_que_no_existe_lo_dice(tmp_path):
    with pytest.raises(intruder.ErrorAtaque):
        intruder.desde_archivo(tmp_path / "no-esta.txt")


def test_desde_rango_con_y_sin_relleno():
    assert intruder.desde_rango(1, 5) == ["1", "2", "3", "4", "5"]
    assert intruder.desde_rango(1, 3, ancho=5) == ["00001", "00002", "00003"]
    assert intruder.desde_rango(0, 10, paso=5) == ["0", "5", "10"]


def test_desde_rango_rechaza_lo_imposible():
    with pytest.raises(intruder.ErrorAtaque):
        intruder.desde_rango(5, 1)
    with pytest.raises(intruder.ErrorAtaque):
        intruder.desde_rango(1, 5, paso=0)


def test_desde_texto_una_por_linea():
    assert intruder.desde_texto("a\nb\n\nc\n") == ["a", "b", "c"]
    assert intruder.desde_texto("") == []
