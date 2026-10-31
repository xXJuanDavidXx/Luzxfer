"""Almacen en SQLite.

Es lo que permite cerrar la sesion, volver al dia siguiente y seguir donde
ibas, y lo que hace posible generar el reporte al final sin haber copiado
capturas a mano. Sin esto la herramienta seria un visor de trafico volatil.

Se usa sqlite3 de la stdlib a proposito: cero dependencias nativas, que es
lo que mantiene el proyecto instalable en Termux.
"""
from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path

from .models import Finding, Flow, Request, Response

ESQUEMA = """
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS flows (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    started       REAL    NOT NULL,
    duration_ms   INTEGER NOT NULL DEFAULT 0,
    source        TEXT    NOT NULL DEFAULT 'proxy',
    method        TEXT    NOT NULL,
    url           TEXT    NOT NULL,
    host          TEXT    NOT NULL,
    path          TEXT    NOT NULL,
    req_version   TEXT    NOT NULL DEFAULT 'HTTP/1.1',
    req_headers   TEXT    NOT NULL DEFAULT '[]',
    req_body      BLOB,
    status        INTEGER,
    reason        TEXT    NOT NULL DEFAULT '',
    resp_version  TEXT    NOT NULL DEFAULT 'HTTP/1.1',
    resp_headers  TEXT    NOT NULL DEFAULT '[]',
    resp_body     BLOB,
    content_type  TEXT    NOT NULL DEFAULT '',
    size          INTEGER NOT NULL DEFAULT 0,
    note          TEXT    NOT NULL DEFAULT '',
    marked        INTEGER NOT NULL DEFAULT 0,
    error         TEXT    NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS ix_flows_started ON flows(started DESC);
CREATE INDEX IF NOT EXISTS ix_flows_host    ON flows(host);
CREATE INDEX IF NOT EXISTS ix_flows_status  ON flows(status);

CREATE TABLE IF NOT EXISTS findings (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    created       REAL    NOT NULL,
    kind          TEXT    NOT NULL,
    detail        TEXT    NOT NULL,
    url           TEXT    NOT NULL,
    flow_ids      TEXT    NOT NULL DEFAULT '[]',
    wstg          TEXT    NOT NULL DEFAULT '[]',
    severity      TEXT    NOT NULL DEFAULT '',
    cvss_vector   TEXT    NOT NULL DEFAULT '',
    justification TEXT    NOT NULL DEFAULT '',
    confirmed     INTEGER NOT NULL DEFAULT 0,
    extra         TEXT    NOT NULL DEFAULT '{}',
    UNIQUE(kind, detail, url)
);

CREATE TABLE IF NOT EXISTS meta (
    clave TEXT PRIMARY KEY,
    valor TEXT NOT NULL
);

-- Los ataques del Intruder van en sus propias tablas y NO en flows. Un
-- ataque suelta facil diez mil peticiones: en el historial lo volverian
-- inservible para lo que es, y el detector correria sobre las diez mil
-- generando miles de candidatos basura. Lo que valga se promueve a mano.
CREATE TABLE IF NOT EXISTS ataques (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    creado    REAL    NOT NULL,
    modo      TEXT    NOT NULL,
    host      TEXT    NOT NULL,
    plantilla TEXT    NOT NULL,          -- la peticion cruda, con marcadores
    total     INTEGER NOT NULL DEFAULT 0,
    enviadas  INTEGER NOT NULL DEFAULT 0,
    abortado  INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS resultados (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    ataque_id INTEGER NOT NULL,
    n         INTEGER NOT NULL,
    payloads  TEXT    NOT NULL DEFAULT '[]',
    status    INTEGER,
    largo     INTEGER NOT NULL DEFAULT 0,
    ms        INTEGER NOT NULL DEFAULT 0,
    error     TEXT    NOT NULL DEFAULT '',
    grep      TEXT    NOT NULL DEFAULT '[]'
);

CREATE INDEX IF NOT EXISTS ix_res_ataque ON resultados(ataque_id);
CREATE INDEX IF NOT EXISTS ix_res_largo  ON resultados(ataque_id, largo);
"""


def _cab(texto: str) -> list[tuple[str, str]]:
    return [(k, v) for k, v in json.loads(texto)]


class Store:
    def __init__(self, ruta: str | Path = ":memory:", *, timeout: float = 5.0):
        """`timeout` son los segundos que se espera a que se libere un
        bloqueo antes de fallar. Importa porque add_flow() se llama desde
        el bucle de la interfaz: si otra instancia tiene la sesion tomada,
        ese tiempo es interfaz congelada."""
        self.ruta = str(ruta)
        if self.ruta != ":memory:":
            Path(self.ruta).parent.mkdir(parents=True, exist_ok=True)
        # check_same_thread=False + lock: el motor escribe desde hilos y la
        # TUI lee desde el bucle de asyncio.
        self._con = sqlite3.connect(self.ruta, check_same_thread=False, timeout=timeout)
        self._con.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        with self._lock:
            self._con.executescript(ESQUEMA)
            self._con.commit()

    def close(self) -> None:
        with self._lock:
            self._con.close()

    # ------------------------------------------------------------------
    def add_flow(self, flow: Flow) -> int:
        r, p = flow.request, flow.response
        with self._lock:
            cur = self._con.execute(
                "INSERT INTO flows (started, duration_ms, source, method, url, host, path,"
                " req_version, req_headers, req_body, status, reason, resp_version,"
                " resp_headers, resp_body, content_type, size, note, marked, error)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    flow.started, flow.duration_ms, flow.source,
                    r.method, r.url, r.host, r.path,
                    r.http_version, json.dumps(r.headers), r.body,
                    p.status if p else None,
                    p.reason if p else "",
                    p.http_version if p else "HTTP/1.1",
                    json.dumps(p.headers) if p else "[]",
                    p.body if p else None,
                    p.content_type if p else "",
                    len(p.body) if p else 0,
                    flow.note, int(flow.marked), flow.error,
                ),
            )
            self._con.commit()
            flow.id = int(cur.lastrowid)
            return flow.id

    def get_flow(self, fid: int) -> Flow | None:
        with self._lock:
            fila = self._con.execute("SELECT * FROM flows WHERE id=?", (fid,)).fetchone()
        return self._fila_a_flow(fila) if fila else None

    @staticmethod
    def _where(
        texto: str = "",
        metodo: str = "",
        estado: str = "",
        solo_marcados: bool = False,
    ) -> tuple[str, list[object]]:
        """El WHERE que comparten list_flows y count_flows.

        Uno solo a proposito. Dos constructores de filtro que se separen
        con el tiempo es exactamente como vuelve un contador que no cuadra
        con lo que la tabla muestra, y ese desacuerdo es peor que no tener
        contador: el analista cree que vio todo.
        """
        sql = ["WHERE 1=1"]
        args: list[object] = []
        if texto:
            sql.append("AND url LIKE ?")
            args.append(f"%{texto}%")
        if metodo:
            sql.append("AND method = ?")
            args.append(metodo.upper())
        if estado:
            if estado.endswith("xx") and estado[0].isdigit():
                lo = int(estado[0]) * 100
                sql.append("AND status >= ? AND status < ?")
                args += [lo, lo + 100]
            elif estado.isdigit():
                sql.append("AND status = ?")
                args.append(int(estado))
        if solo_marcados:
            sql.append("AND marked = 1")
        return " ".join(sql), args

    def list_flows(
        self,
        *,
        texto: str = "",
        metodo: str = "",
        estado: str = "",
        solo_marcados: bool = False,
        limite: int = 1000,
        ascendente: bool = False,
    ) -> list[Flow]:
        """Lista para la tabla. Los filtros son los que se usan de verdad:
        texto en la URL, metodo, familia de codigo de estado."""
        donde, args = self._where(texto, metodo, estado, solo_marcados)
        with self._lock:
            filas = self._con.execute(
                f"SELECT * FROM flows {donde} ORDER BY id DESC LIMIT ?",
                [*args, limite],
            ).fetchall()
        flujos = [self._fila_a_flow(f) for f in filas]
        # siempre se toman los N mas recientes; ascendente solo cambia el orden
        return flujos[::-1] if ascendente else flujos

    def count_flows(
        self,
        *,
        texto: str = "",
        metodo: str = "",
        estado: str = "",
        solo_marcados: bool = False,
    ) -> int:
        """Cuantos flujos hay. Sin argumentos, el total de la sesion.

        Acepta los mismos filtros que list_flows para poder comparar lo
        que se muestra con lo que hay, que es de donde sale el aviso de
        historial truncado.
        """
        donde, args = self._where(texto, metodo, estado, solo_marcados)
        with self._lock:
            fila = self._con.execute(
                f"SELECT COUNT(*) c FROM flows {donde}", args).fetchone()
        return int(fila["c"])

    def set_mark(self, fid: int, marcado: bool) -> None:
        with self._lock:
            self._con.execute("UPDATE flows SET marked=? WHERE id=?", (int(marcado), fid))
            self._con.commit()

    def set_note(self, fid: int, nota: str) -> None:
        with self._lock:
            self._con.execute("UPDATE flows SET note=? WHERE id=?", (nota, fid))
            self._con.commit()

    def clear_flows(self) -> None:
        with self._lock:
            self._con.execute("DELETE FROM flows")
            self._con.commit()

    def hosts(self) -> list[str]:
        with self._lock:
            filas = self._con.execute(
                "SELECT DISTINCT host FROM flows ORDER BY host").fetchall()
        return [f["host"] for f in filas]

    # ------------------------------------------------------------------
    def add_finding(self, hallazgo: Finding) -> int | None:
        """Devuelve el id, o None si ya existia (UNIQUE kind+detail+url).

        Esa restriccion es lo que evita el ruido de scanner: el mismo
        hallazgo en la misma URL no se repite.
        """
        with self._lock:
            cur = self._con.execute(
                "INSERT OR IGNORE INTO findings (created, kind, detail, url, flow_ids,"
                " wstg, severity, cvss_vector, justification, confirmed, extra)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (
                    hallazgo.created, hallazgo.kind, hallazgo.detail, hallazgo.url,
                    json.dumps(hallazgo.flow_ids), json.dumps(hallazgo.wstg),
                    hallazgo.severity, hallazgo.cvss_vector, hallazgo.justification,
                    int(hallazgo.confirmed), json.dumps(hallazgo.extra),
                ),
            )
            self._con.commit()
            if cur.rowcount == 0:
                return None
            hallazgo.id = int(cur.lastrowid)
            return hallazgo.id

    def set_confirmed(self, hid: int, confirmado: bool) -> None:
        """Marca un candidato como hallazgo validado a mano, o lo desmarca.

        Es la frontera que el README promete: lo que el detector senala es
        un candidato, y solo un humano lo convierte en hallazgo.
        """
        with self._lock:
            self._con.execute("UPDATE findings SET confirmed=? WHERE id=?",
                              (int(confirmado), hid))
            self._con.commit()

    def list_findings(self, *, kind: str = "",
                      solo_confirmados: bool = False) -> list[Finding]:
        sql = "SELECT * FROM findings WHERE 1=1"
        args: list[object] = []
        if kind:
            sql += " AND kind = ?"
            args.append(kind)
        if solo_confirmados:
            sql += " AND confirmed = 1"
        sql += " ORDER BY id DESC"
        with self._lock:
            filas = self._con.execute(sql, args).fetchall()
        return [
            Finding(
                id=f["id"], created=f["created"], kind=f["kind"], detail=f["detail"],
                url=f["url"], flow_ids=json.loads(f["flow_ids"]),
                wstg=json.loads(f["wstg"]), severity=f["severity"],
                cvss_vector=f["cvss_vector"], justification=f["justification"],
                confirmed=bool(f["confirmed"]), extra=json.loads(f["extra"]),
            )
            for f in filas
        ]

    def count_findings(self) -> int:
        with self._lock:
            return int(self._con.execute("SELECT COUNT(*) c FROM findings").fetchone()["c"])

    # ------------------------------------------------- ataques del intruder
    def add_ataque(self, modo: str, host: str, plantilla: str, total: int) -> int:
        with self._lock:
            cur = self._con.execute(
                "INSERT INTO ataques (creado, modo, host, plantilla, total)"
                " VALUES (?,?,?,?,?)",
                (time.time(), modo, host, plantilla, total),
            )
            self._con.commit()
            return int(cur.lastrowid)

    def add_resultado(self, ataque_id: int, r) -> None:
        """Guarda un resultado del Intruder.

        Toma `r` por sus atributos y no por su tipo: asi el almacen no
        importa intruder.py, y la herramienta puede cambiar sin arrastrar
        al almacen detras.
        """
        with self._lock:
            self._con.execute(
                "INSERT INTO resultados (ataque_id, n, payloads, status,"
                " largo, ms, error, grep) VALUES (?,?,?,?,?,?,?,?)",
                (ataque_id, r.n, json.dumps(list(r.payloads)), r.status,
                 r.largo, r.ms, r.error, json.dumps(list(r.grep))),
            )
            self._con.commit()

    def cerrar_ataque(self, ataque_id: int, enviadas: int, abortado: bool) -> None:
        with self._lock:
            self._con.execute(
                "UPDATE ataques SET enviadas=?, abortado=? WHERE id=?",
                (enviadas, int(abortado), ataque_id),
            )
            self._con.commit()

    def list_ataques(self) -> list[dict]:
        with self._lock:
            filas = self._con.execute(
                "SELECT * FROM ataques ORDER BY id DESC").fetchall()
        return [dict(f) for f in filas]

    def list_resultados(self, ataque_id: int, *, limite: int = 10_000) -> list[dict]:
        with self._lock:
            filas = self._con.execute(
                "SELECT * FROM resultados WHERE ataque_id=? ORDER BY n LIMIT ?",
                (ataque_id, limite),
            ).fetchall()
        return [dict(f) for f in filas]

    def borrar_ataque(self, ataque_id: int) -> None:
        """Se lleva el ataque y sus resultados.

        El borrado en cascada va a mano y no con ON DELETE CASCADE porque
        sqlite3 no activa las claves foraneas por defecto, y depender de
        un PRAGMA que alguien puede no poner seria dejar huerfanos.
        """
        with self._lock:
            self._con.execute("DELETE FROM resultados WHERE ataque_id=?", (ataque_id,))
            self._con.execute("DELETE FROM ataques WHERE id=?", (ataque_id,))
            self._con.commit()

    # ------------------------------------------------------------------
    def get_meta(self, clave: str, defecto: str = "") -> str:
        """Un ajuste guardado con la sesion. Inexistente: `defecto`."""
        with self._lock:
            fila = self._con.execute(
                "SELECT valor FROM meta WHERE clave=?", (clave,)).fetchone()
        return fila["valor"] if fila else defecto

    def set_meta(self, clave: str, valor: str) -> None:
        """Guarda un ajuste. El ON CONFLICT es lo que evita duplicar."""
        with self._lock:
            self._con.execute(
                "INSERT INTO meta (clave, valor) VALUES (?,?)"
                " ON CONFLICT(clave) DO UPDATE SET valor=excluded.valor",
                (clave, valor),
            )
            self._con.commit()

    # ------------------------------------------------------------------
    @staticmethod
    def _fila_a_flow(f: sqlite3.Row) -> Flow:
        req = Request(
            method=f["method"], url=f["url"], http_version=f["req_version"],
            headers=_cab(f["req_headers"]), body=bytes(f["req_body"] or b""),
        )
        resp = None
        if f["status"] is not None:
            resp = Response(
                status=int(f["status"]), reason=f["reason"],
                http_version=f["resp_version"], headers=_cab(f["resp_headers"]),
                body=bytes(f["resp_body"] or b""),
            )
        return Flow(
            id=f["id"], request=req, response=resp, started=f["started"],
            duration_ms=f["duration_ms"], source=f["source"], note=f["note"],
            marked=bool(f["marked"]), error=f["error"],
        )
