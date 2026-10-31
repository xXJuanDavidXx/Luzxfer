"""Tests del Intruder.

Esto dispara peticiones contra sistemas ajenos, asi que casi todo lo que
se prueba aqui es «no hagas nada que el analista no pidio»: no mutar sus
payloads, no inventarse posiciones, no mandar mas de lo que dijo.
"""
from __future__ import annotations

import time

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


# ---------------------------------------------------- el motor de ataque
def _cfg(**kw):
    kw.setdefault("modo", intruder.Modo.SNIPER)
    kw.setdefault("por_segundo", 1000)          # sin freno salvo donde se mida
    return intruder.Config(**kw)


def test_un_ataque_sniper_completo_contra_un_servidor_real(eco):
    h, p = eco
    crudo = f"GET /eco?q=§X§ HTTP/1.1\r\nHost: {h}:{p}\r\n\r\n"
    a = intruder.Ataque(crudo, _cfg(conjuntos=[["uno", "dos", "tres"]]))
    assert a.total == 3
    salida = []
    a.correr(salida.append)
    assert len(salida) == 3
    assert {r.payloads[0] for r in salida} == {"uno", "dos", "tres"}
    assert all(r.status == 200 and r.error == "" for r in salida)
    assert a.terminado and a.enviadas == 3


def test_content_length_se_recalcula_por_payload(eco):
    """Cada payload cambia el largo del cuerpo. Es el fallo numero uno del
    repeater, aqui multiplicado por cada iteracion: con el Content-Length
    viejo el servidor se queda esperando bytes que no llegan."""
    h, p = eco
    crudo = (f"POST /eco HTTP/1.1\r\nHost: {h}:{p}\r\n"
             f"Content-Type: application/x-www-form-urlencoded\r\n"
             f"Content-Length: 99\r\n\r\nq=§X§")
    salida = []
    intruder.Ataque(crudo, _cfg(conjuntos=[["a", "muchomaslargo"]])).correr(salida.append)
    assert all(r.status == 200 for r in salida)
    assert {r.payloads[0] for r in salida} == {"a", "muchomaslargo"}


def test_los_resultados_llegan_numerados_y_sin_perderse(eco):
    h, p = eco
    crudo = f"GET /eco?q=§X§ HTTP/1.1\r\nHost: {h}:{p}\r\n\r\n"
    a = intruder.Ataque(crudo, _cfg(conjuntos=[[str(i) for i in range(20)]],
                                    concurrencia=4))
    salida = []
    a.correr(salida.append)
    assert sorted(r.n for r in salida) == list(range(20))


def test_el_tope_por_segundo_se_respeta_entre_hilos(eco):
    """El reloj es del ataque entero, no de cada hilo. Con un sleep por
    hilo, 4 hilos a 10/s mandarian 40/s sin que nadie lo note, que es
    justo el accidente que el tope existe para evitar."""
    h, p = eco
    crudo = f"GET /eco?q=§X§ HTTP/1.1\r\nHost: {h}:{p}\r\n\r\n"
    a = intruder.Ataque(crudo, intruder.Config(
        modo=intruder.Modo.SNIPER, conjuntos=[[str(i) for i in range(10)]],
        concurrencia=4, por_segundo=20.0))
    t = time.time()
    a.correr(lambda r: None)
    assert time.time() - t > 0.4          # 10 a 20/s no bajan de ~0,45 s


def test_abortar_corta_el_ataque(eco):
    h, p = eco
    crudo = f"GET /eco?q=§X§ HTTP/1.1\r\nHost: {h}:{p}\r\n\r\n"
    a = intruder.Ataque(crudo, intruder.Config(
        modo=intruder.Modo.SNIPER, conjuntos=[[str(i) for i in range(500)]],
        concurrencia=2, por_segundo=200.0))
    salida = []

    def al_llegar(r):
        salida.append(r)
        if len(salida) >= 5:
            a.abortar()

    a.correr(al_llegar)
    assert a.terminado and a.abortado
    assert 5 <= len(salida) < 500


def test_abortar_antes_de_empezar_no_manda_nada(eco):
    h, p = eco
    a = intruder.Ataque(f"GET /eco?q=§X§ HTTP/1.1\r\nHost: {h}:{p}\r\n\r\n",
                        _cfg(conjuntos=[["a", "b", "c"]]))
    a.abortar()
    a.abortar()                               # idempotente
    salida = []
    a.correr(salida.append)
    assert salida == [] and a.terminado


def test_grep_match_marca_las_respuestas_que_contienen_el_texto(eco):
    h, p = eco
    crudo = f"GET /eco?q=§X§ HTTP/1.1\r\nHost: {h}:{p}\r\n\r\n"
    a = intruder.Ataque(crudo, _cfg(conjuntos=[["AGUJA", "pajar"]],
                                    grep=["AGUJA"]))
    salida = {}
    a.correr(lambda r: salida.update({r.payloads[0]: r}))
    assert salida["AGUJA"].grep == ["AGUJA"]
    assert salida["pajar"].grep == []


def test_un_error_de_red_no_tumba_el_ataque():
    """Un objetivo que no responde da un resultado con error, no una
    excepcion que se lleve por delante las peticiones que faltan."""
    crudo = "GET /x?q=§X§ HTTP/1.1\r\nHost: 127.0.0.1:1\r\n\r\n"
    a = intruder.Ataque(crudo, _cfg(conjuntos=[["a", "b"]], timeout=2.0))
    salida = []
    a.correr(salida.append)
    assert len(salida) == 2
    assert all(r.error and r.status is None for r in salida)


def test_una_peticion_sin_marcadores_no_es_un_ataque():
    with pytest.raises(intruder.ErrorAtaque):
        intruder.Ataque("GET / HTTP/1.1\r\nHost: o.com\r\n\r\n",
                        _cfg(conjuntos=[["a"]]))


def test_el_ataque_valida_antes_de_abrir_un_socket():
    """Descubrir que la configuracion esta mal en la peticion 300 es tarde
    cuando esas 300 ya salieron hacia el sistema de un cliente."""
    with pytest.raises(intruder.ErrorAtaque):
        intruder.Ataque("GET /?q=§a§&r=§b§ HTTP/1.1\r\nHost: o\r\n\r\n",
                        _cfg(modo=intruder.Modo.RACIMO, conjuntos=[["x"]]))


def test_el_ataque_avisa_de_los_payloads_que_se_mutarian():
    a = intruder.Ataque("GET /?q=§X§ HTTP/1.1\r\nHost: o\r\n\r\n",
                        _cfg(conjuntos=[["ok", "日本"]]))
    assert a.avisos == ["日本"]


def test_el_total_se_sabe_sin_lanzar():
    a = intruder.Ataque("GET /?q=§a§&r=§b§ HTTP/1.1\r\nHost: o\r\n\r\n",
                        _cfg(modo=intruder.Modo.RACIMO,
                             conjuntos=[[str(i) for i in range(100)]] * 2))
    assert a.total == 10_000
    assert a.enviadas == 0 and not a.terminado
