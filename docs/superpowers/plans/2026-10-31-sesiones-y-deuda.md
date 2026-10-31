# Sesiones con nombre y deuda de la 0.1.0 — Plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Que el historial no se pierda nunca — sesiones persistentes con nombre, retomables y listables desde la TUI — y cerrar los cinco cabos sueltos restantes de la 0.1.0.

**Architecture:** Un módulo nuevo `core/sesiones.py` resuelve el directorio de datos, valida nombres, lista sesiones con su resumen y recuerda cuál fue la última. `__main__.py` traduce `-s`/`--sesiones` a una ruta concreta y el default pasa de `:memory:` a un archivo real; `Store` no cambia de interfaz, solo recibe otra ruta. La TUI gana una pantalla selectora que lee resúmenes sin abrir el almacén en escritura. Nada de esto toca el motor ni la interfaz `Engine`.

**Tech Stack:** Python 3.10+, stdlib (`sqlite3`, `pathlib`, `os`), Textual 8.x. Sin dependencias nuevas.

**Spec:** `progress.md`, sección «Deuda y cabos sueltos detectados» (seis puntos, verificados el 2026-10-31), más la decisión de sesiones tomada en esta conversación: *nombradas con selector en la TUI*, con esta interfaz de línea de comandos acordada:

```
luzxfer                 # retoma la ultima sesion
luzxfer -s cliente-x    # abre o crea 'cliente-x'
luzxfer --sesiones      # lista y sale
```

## Alcance y orden

El plan tiene dos partes. **La Parte A (tareas 1–5) es software entregable por sí sola**: si se para ahí, el historial ya no se pierde. La Parte B (tareas 6–10) son correcciones independientes entre sí, en el orden en que conviene hacerlas.

El cabo suelto #3 de `progress.md` (truncado silencioso a 1000 flujos) vive en la Parte A, no en la B: es la misma preocupación que las sesiones. Guardar el historial y después no mostrarlo entero es perderlo igual.

## Global Constraints

Valores copiados del `pyproject.toml` y de las reglas de diseño del README. **Aplican a todas las tareas.**

- `requires-python = ">=3.10"`. Nada que no corra en 3.10.
- **Cero dependencias nuevas.** La única de runtime es `textual>=0.80`. Todo lo demás, stdlib. En particular **no usar `platformdirs`**: está instalado en el venv pero solo como dependencia transitiva de Textual, no está declarado, y el proyecto tiene que instalar en Termux sin arrastrar nada.
- **Nada en `core/` importa de `tui/`.**
- **Ninguna interfaz habla con un motor concreto**, solo con `Engine`.
- `ruff`: `line-length = 100`, reglas `E,F,I,UP,B`, `target-version = "py310"`.
- Identificadores, docstrings y comentarios **en español sin tildes**, como el resto del código. El README es el único archivo en inglés.
- Los tests corren **solo** con `./venv/bin/python -m pytest`: el python del sistema no tiene textual.
- Tras cada tarea: los 51 tests existentes siguen pasando y `ruff check src tests` sigue limpio.

## Review Focus

Cinco cosas que el spec implica y que ninguna tarea probaría si no se dijera aquí. Cada línea tiene su test asignado a la tarea que es dueña del código.

1. **Un nombre de sesión con `/`, `..` o un byte nulo escribiría fuera del directorio de sesiones.** Esto es una herramienta de seguridad; un traversal en su propio almacén es inaceptable. Un nombre inválido debe fallar con un mensaje, nunca crear el archivo. → test en Tarea 1.
2. **Un `.db` corrupto o ajeno dentro del directorio de sesiones** (lo deja cualquiera que copie un archivo ahí) debe salir listado como ilegible, no reventar el selector. → test en Tarea 2.
3. **El puntero a «última sesión» apuntando a una sesión ya borrada** debe arrancar igual, cayendo al nombre por defecto, no abortar. → test en Tarea 3.
4. **El directorio de datos no escribible** (o `XDG_DATA_HOME` apuntando a algo imposible) debe dar un mensaje claro en stderr y salir con código distinto de cero, no un traceback. → test en Tarea 3.
5. **Dos instancias sobre la misma sesión** deben dar un error de SQLite visible, no corrupción silenciosa del historial de un pentest. → test en Tarea 2.

---

## File Structure

**Crear:**

| archivo | responsabilidad |
| --- | --- |
| `src/luzxfer/core/sesiones.py` | Directorio de datos, validación de nombres, listado con resumen, puntero a la última. Sin tocar `Store`. |
| `src/luzxfer/tui/screens/sesiones.py` | Pantalla modal selectora de sesiones. |
| `src/luzxfer/tui/screens/nota.py` | Pantalla modal para la nota de un flujo. |
| `tests/test_sesiones.py` | Tests del módulo de sesiones y de la pantalla selectora. |

**Modificar:**

| archivo | qué cambia |
| --- | --- |
| `src/luzxfer/__main__.py` | Opciones `-s/--sesion` y `--sesiones`; default persistente; errores de arranque. |
| `src/luzxfer/core/store.py` | Extraer el constructor de `WHERE`; `count_flows()` con filtros; `set_confirmed()`. |
| `src/luzxfer/tui/app.py` | Nombre de sesión en el título; selector; nota; confirmar candidato; aviso de truncado; aviso de brotli. |
| `README.md` | Sección de sesiones; instalación desde fuente; claves nuevas. |
| `pyproject.toml` | URLs reales. |

**Borrar:** `src/luzxfer/tui/widgets/` (paquete vacío).

---

# Parte A — Sesiones

## Tarea 1: Directorio de datos y validación de nombres

El cimiento de todo lo demás, y donde vive la defensa contra traversal.

**Files:**
- Create: `src/luzxfer/core/sesiones.py`
- Test: `tests/test_sesiones.py`

**Interfaces:**
- Consumes: nada.
- Produces:
  - `class NombreInvalido(ValueError)`
  - `def dir_datos() -> Path` — `$XDG_DATA_HOME/luzxfer` si la variable está puesta y es absoluta, si no `~/.local/share/luzxfer`. No crea nada.
  - `def dir_sesiones() -> Path` — `dir_datos() / "sesiones"`. No crea nada.
  - `def valida_nombre(nombre: str) -> str` — devuelve el nombre normalizado (`strip()`), o lanza `NombreInvalido` con un mensaje que dice qué se permite.
  - `def ruta_de(nombre: str) -> Path` — `dir_sesiones() / f"{valida_nombre(nombre)}.db"`.
  - `NOMBRE_DEFECTO = "predeterminada"`

**Reglas del nombre** (decididas aquí, no dejadas al implementador): tras `strip()`, entre 1 y 64 caracteres, solo `A-Z a-z 0-9 . _ -`, y no puede empezar por `.`. Cualquier otra cosa es `NombreInvalido`. Esa lista blanca es lo que hace imposible el traversal: sin `/`, sin `\`, sin nulos, y `..` queda fuera por la regla del punto inicial.

- [ ] **Step 1: Write the failing tests**

```python
import os
from pathlib import Path

import pytest

from luzxfer.core import sesiones


def test_dir_datos_respeta_xdg(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    assert sesiones.dir_datos() == tmp_path / "luzxfer"
    assert sesiones.dir_sesiones() == tmp_path / "luzxfer" / "sesiones"


def test_dir_datos_cae_a_local_share_sin_xdg(monkeypatch):
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    assert sesiones.dir_datos() == Path.home() / ".local" / "share" / "luzxfer"


def test_dir_datos_ignora_xdg_relativo(monkeypatch):
    # un XDG_DATA_HOME relativo no es valido segun la especificacion
    monkeypatch.setenv("XDG_DATA_HOME", "datos/aqui")
    assert sesiones.dir_datos() == Path.home() / ".local" / "share" / "luzxfer"


def test_valida_nombre_acepta_lo_razonable():
    assert sesiones.valida_nombre("cliente-x") == "cliente-x"
    assert sesiones.valida_nombre("  lab_dvwa  ") == "lab_dvwa"
    assert sesiones.valida_nombre("2026-10-31.tarde") == "2026-10-31.tarde"


@pytest.mark.parametrize("malo", [
    "../../etc/passwd",      # traversal clasico
    "..",
    ".oculta",
    "cliente/x",
    "cliente\\x",
    "con\x00nulo",
    "con espacio",
    "",
    "   ",
    "a" * 65,
])
def test_valida_nombre_rechaza_lo_peligroso(malo):
    with pytest.raises(sesiones.NombreInvalido):
        sesiones.valida_nombre(malo)


def test_ruta_de_nunca_sale_del_directorio(monkeypatch, tmp_path):
    """Review Focus 1: un nombre no puede escribir fuera de dir_sesiones()."""
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    base = sesiones.dir_sesiones().resolve()
    for nombre in ("cliente-x", "lab_dvwa", "a" * 64):
        assert sesiones.ruta_de(nombre).resolve().parent == base
    for malo in ("../fuera", "/etc/passwd", "sub/dir"):
        with pytest.raises(sesiones.NombreInvalido):
            sesiones.ruta_de(malo)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `./venv/bin/python -m pytest tests/test_sesiones.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'luzxfer.core.sesiones'`

- [ ] **Step 3: Implement `sesiones.py` with the signatures in the Interfaces block**

Usar una expresión regular compilada a nivel de módulo para la lista blanca. El mensaje de `NombreInvalido` debe decir qué caracteres se permiten, porque lo va a leer alguien en una terminal.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `./venv/bin/python -m pytest tests/test_sesiones.py -v`
Expected: PASS (todos)

- [ ] **Step 5: Commit**

```bash
git add src/luzxfer/core/sesiones.py tests/test_sesiones.py
git commit -m "feat(sesiones): directorio de datos y validacion de nombres"
```

---

## Tarea 2: Listado de sesiones con resumen

Lo que alimenta el selector y `--sesiones`. Lee en **solo lectura**: listar no debe crear ni migrar nada.

**Files:**
- Modify: `src/luzxfer/core/sesiones.py`
- Test: `tests/test_sesiones.py`

**Interfaces:**
- Consumes: `dir_sesiones()`, `valida_nombre()`, `ruta_de()` de la Tarea 1; `Store` de `core/store.py` (solo en los tests, para fabricar sesiones).
- Produces:
  - `@dataclass(slots=True) class ResumenSesion` con campos `nombre: str`, `ruta: Path`, `flujos: int`, `candidatos: int`, `modificada: float`, `ilegible: bool = False`
  - `def listar() -> list[ResumenSesion]` — todos los `*.db` de `dir_sesiones()`, ordenados por `modificada` descendente. Directorio inexistente → lista vacía.
  - `def resumen(ruta: Path) -> ResumenSesion` — abre con `sqlite3.connect(f"file:{ruta}?mode=ro", uri=True)`. Ante `sqlite3.Error` devuelve el resumen con `ilegible=True` y los contadores en 0.
  - `def borrar(nombre: str) -> None` — borra el `.db` y sus `-wal`/`-shm`. Inexistente → no hace nada.

- [ ] **Step 1: Write the failing tests**

```python
import sqlite3
import time

from luzxfer.core.models import Flow, Request, Response
from luzxfer.core.store import Store


def _sesion(tmp_path, nombre, n_flujos=0):
    """Crea una sesion de verdad en el directorio, con n flujos dentro."""
    ruta = sesiones.ruta_de(nombre)
    st = Store(ruta)
    for i in range(n_flujos):
        st.add_flow(Flow(
            request=Request(method="GET", url=f"http://ej.com/{i}",
                            headers=[("Host", "ej.com")]),
            response=Response(status=200, body=b"x"),
        ))
    st.close()
    return ruta


def test_listar_vacio_si_no_existe_el_directorio(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "nada"))
    assert sesiones.listar() == []


def test_listar_devuelve_nombre_y_contadores(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    _sesion(tmp_path, "cliente-x", n_flujos=3)
    r = sesiones.listar()
    assert len(r) == 1
    assert r[0].nombre == "cliente-x"
    assert r[0].flujos == 3
    assert r[0].ilegible is False


def test_listar_ordena_por_mas_reciente(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    _sesion(tmp_path, "vieja", n_flujos=1)
    time.sleep(0.01)
    _sesion(tmp_path, "nueva", n_flujos=1)
    assert [s.nombre for s in sesiones.listar()] == ["nueva", "vieja"]


def test_un_db_corrupto_sale_como_ilegible_y_no_revienta(monkeypatch, tmp_path):
    """Review Focus 2: cualquiera puede copiar un archivo al directorio."""
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    _sesion(tmp_path, "buena", n_flujos=2)
    sesiones.dir_sesiones().joinpath("basura.db").write_bytes(b"esto no es sqlite")

    r = {s.nombre: s for s in sesiones.listar()}
    assert r["basura"].ilegible is True
    assert r["basura"].flujos == 0
    assert r["buena"].ilegible is False and r["buena"].flujos == 2


def test_listar_no_crea_ni_modifica_la_sesion(monkeypatch, tmp_path):
    """Abrir en solo lectura: listar no debe tocar el archivo."""
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    ruta = _sesion(tmp_path, "intacta", n_flujos=1)
    antes = ruta.stat().st_mtime_ns
    sesiones.listar()
    assert ruta.stat().st_mtime_ns == antes


def test_dos_instancias_sobre_la_misma_sesion_dan_error_visible(monkeypatch, tmp_path):
    """Review Focus 5: mejor un error de SQLite que corrupcion callada.

    Tarda ~5 s a proposito: es el busy timeout por defecto de sqlite3
    agotandose antes de lanzar. Si molesta en la suite, la solucion es
    darle a Store un parametro de timeout, no borrar el test.
    """
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    ruta = sesiones.ruta_de("compartida")
    a = Store(ruta)
    b = Store(ruta)
    con = sqlite3.connect(ruta, isolation_level=None)
    con.execute("BEGIN EXCLUSIVE")
    try:
        with pytest.raises(sqlite3.Error):
            b.add_flow(Flow(request=Request(method="GET", url="http://ej.com/",
                                            headers=[("Host", "ej.com")])))
    finally:
        con.close()
        a.close()
        b.close()


def test_borrar_quita_el_db_y_sus_auxiliares(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    ruta = _sesion(tmp_path, "temporal", n_flujos=1)
    sesiones.borrar("temporal")
    assert not ruta.exists()
    assert not ruta.with_suffix(".db-wal").exists()
    sesiones.borrar("temporal")          # idempotente, no lanza
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `./venv/bin/python -m pytest tests/test_sesiones.py -v`
Expected: FAIL — `AttributeError: module 'luzxfer.core.sesiones' has no attribute 'listar'`

- [ ] **Step 3: Implement `ResumenSesion`, `listar()`, `resumen()` and `borrar()` in `sesiones.py`**

`resumen()` consulta `SELECT COUNT(*) FROM flows` y `SELECT COUNT(*) FROM findings`. Un archivo que no es SQLite no falla al conectar sino al consultar, así que el `try` tiene que envolver las consultas, no solo el `connect`.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `./venv/bin/python -m pytest tests/test_sesiones.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/luzxfer/core/sesiones.py tests/test_sesiones.py
git commit -m "feat(sesiones): listado con resumen en solo lectura"
```

---

## Tarea 3: El default deja de ser `:memory:`

Aquí es donde se cumple lo que pidió el usuario: salir de la herramienta ya no pierde el historial.

**Files:**
- Modify: `src/luzxfer/core/sesiones.py`
- Modify: `src/luzxfer/__main__.py`
- Test: `tests/test_sesiones.py`

**Interfaces:**
- Consumes: todo lo de las tareas 1 y 2.
- Produces:
  - `def ultima() -> str | None` — lee `dir_datos() / "ultima"`. Si no existe, si el nombre es inválido, o si la sesión ya no está en disco, devuelve `None`.
  - `def recordar_ultima(nombre: str) -> None` — escribe ese archivo, creando `dir_datos()` si falta.
  - `def abrir(nombre: str | None) -> tuple[str, Path]` — resuelve el nombre efectivo (`nombre`, si no `ultima()`, si no `NOMBRE_DEFECTO`), crea `dir_sesiones()`, llama a `recordar_ultima()` y devuelve `(nombre, ruta)`.
- En `__main__.py`: `-s/--sesion NOMBRE` y `--sesiones`. `-d/--db` sigue existiendo y **gana** sobre `-s` (ruta explícita, para quien quiera el archivo donde él diga). `main()` devuelve `2` ante `NombreInvalido` u `OSError` al preparar el directorio.
  - `LuzxferApp.__init__` acepta un parámetro nuevo `sesion: str = ""` y lo muestra en `self.sub_title`. Se define aquí porque es esta tarea la que cablea `__main__`; la Tarea 4 solo lo consume.

- [ ] **Step 1: Write the failing tests**

```python
from luzxfer.__main__ import main


def test_abrir_sin_nombre_usa_el_default_la_primera_vez(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    nombre, ruta = sesiones.abrir(None)
    assert nombre == sesiones.NOMBRE_DEFECTO
    assert ruta.parent.is_dir()


def test_abrir_recuerda_y_retoma_la_ultima(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    sesiones.abrir("cliente-x")
    Store(sesiones.ruta_de("cliente-x")).close()      # que exista en disco
    assert sesiones.ultima() == "cliente-x"
    assert sesiones.abrir(None)[0] == "cliente-x"


def test_ultima_borrada_no_rompe_el_arranque(monkeypatch, tmp_path):
    """Review Focus 3: el puntero sobrevive a la sesion que apunta."""
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    sesiones.abrir("efimera")
    Store(sesiones.ruta_de("efimera")).close()
    sesiones.borrar("efimera")
    assert sesiones.ultima() is None
    assert sesiones.abrir(None)[0] == sesiones.NOMBRE_DEFECTO


def test_ultima_con_contenido_basura_se_ignora(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    sesiones.dir_datos().mkdir(parents=True, exist_ok=True)
    (sesiones.dir_datos() / "ultima").write_text("../../etc/passwd")
    assert sesiones.ultima() is None


def test_cli_nombre_invalido_sale_con_2_y_mensaje(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    assert main(["-s", "../fuera", "--no-engine"]) == 2
    assert "nombre de sesion" in capsys.readouterr().err.lower()


def test_cli_directorio_no_escribible_explica_y_no_revienta(monkeypatch, tmp_path, capsys):
    """Review Focus 4: mensaje claro, no traceback."""
    bloqueado = tmp_path / "bloqueado"
    bloqueado.mkdir()
    bloqueado.chmod(0o500)
    monkeypatch.setenv("XDG_DATA_HOME", str(bloqueado))
    try:
        assert main(["--no-engine"]) == 2
        assert "no se pudo" in capsys.readouterr().err.lower()
    finally:
        bloqueado.chmod(0o700)


def test_cli_sesiones_lista_y_sale(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    sesiones.abrir("cliente-x")
    _sesion(tmp_path, "cliente-x", n_flujos=2)
    assert main(["--sesiones"]) == 0
    salida = capsys.readouterr().out
    assert "cliente-x" in salida and "2" in salida
```

Nota: `test_cli_*` no arrancan la TUI — `--no-engine` sigue construyendo la app, así que estos tres casos deben salir **antes** de `app.run()`. Si al implementar resulta que el camino inválido llega a `run()`, mover la validación arriba es parte de la tarea.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `./venv/bin/python -m pytest tests/test_sesiones.py -v`
Expected: FAIL — `AttributeError: ... has no attribute 'abrir'` y `SystemExit: 2` de argparse por `-s` desconocido

- [ ] **Step 3: Implement `ultima()`, `recordar_ultima()`, `abrir()` and wire `-s`/`--sesiones` into `__main__.py`**

En `__main__.py`: resolver la sesión antes de importar la TUI, envolver `abrir()` en `try/except (NombreInvalido, OSError)` y escribir el motivo en `stderr`. `--sesiones` imprime una línea por sesión con nombre, flujos, candidatos y fecha, marcando las ilegibles, y devuelve `0` sin construir la app. Pasar a `LuzxferApp` también el nombre, para el título.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `./venv/bin/python -m pytest tests/test_sesiones.py -v && ./venv/bin/python -m pytest -q`
Expected: PASS, y los 51 tests previos siguen pasando

- [ ] **Step 5: Verify by hand that the history survives**

```bash
./venv/bin/luzxfer -s prueba-plan --no-engine   # abrir y salir con q
./venv/bin/luzxfer --sesiones                   # 'prueba-plan' aparece listada
```

- [ ] **Step 6: Commit**

```bash
git add src/luzxfer/core/sesiones.py src/luzxfer/__main__.py tests/test_sesiones.py
git commit -m "feat(sesiones): persistir por defecto y retomar la ultima"
```

---

## Tarea 4: Pantalla selectora de sesiones

**Files:**
- Create: `src/luzxfer/tui/screens/sesiones.py`
- Modify: `src/luzxfer/tui/app.py`
- Modify: `src/luzxfer/tui/styles.tcss`
- Test: `tests/test_sesiones.py`

**Interfaces:**
- Consumes: `sesiones.listar()`, `sesiones.borrar()`, `ResumenSesion`.
- Produces: `class SesionesScreen(ModalScreen[str | None])` — se abre con `s`, `dismiss(nombre)` al elegir con Enter, `dismiss(None)` con `esc`. `supr` borra la sesión resaltada, nunca la que está abierta. **Enter sobre una sesión ilegible no hace nada** (ni la elige ni cierra la pantalla): no hay nada que abrir ahí.
- En `app.py`: `Binding("s", "sesiones", "sesiones")` y `action_sesiones()`. El parámetro `sesion` de `LuzxferApp` ya lo definió la Tarea 3; aquí solo se lee.

**Cambiar de sesión en caliente no entra en esta tarea.** Elegir otra sesión notifica qué comando reabre la herramienta ahí; reemplazar el `Store` vivo con el motor corriendo es un problema distinto y no hace falta para que el historial no se pierda. Mantenerlo fuera es lo que deja esta tarea revisable por separado.

- [ ] **Step 1: Write the failing tests**

```python
from textual.widgets import DataTable

from luzxfer.tui.app import LuzxferApp
from luzxfer.tui.screens.sesiones import SesionesScreen


async def test_la_tecla_s_abre_el_selector(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    _sesion(tmp_path, "cliente-x", n_flujos=2)
    app = LuzxferApp(arrancar_motor=False, sesion="cliente-x")
    async with app.run_test() as pilot:
        await pilot.press("s")
        await pilot.pause()
        assert isinstance(app.screen, SesionesScreen)


async def test_el_selector_lista_las_sesiones_con_sus_contadores(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    _sesion(tmp_path, "cliente-x", n_flujos=3)
    _sesion(tmp_path, "lab-dvwa", n_flujos=1)
    app = LuzxferApp(arrancar_motor=False, sesion="cliente-x")
    async with app.run_test() as pilot:
        await pilot.press("s")
        await pilot.pause()
        tabla = app.screen.query_one("#ses-tabla", DataTable)
        assert tabla.row_count == 2
        texto = " ".join(
            str(c) for f in range(tabla.row_count)
            for c in tabla.get_row_at(f)
        )
        assert "cliente-x" in texto and "lab-dvwa" in texto


async def test_esc_cierra_el_selector_sin_elegir(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    _sesion(tmp_path, "cliente-x", n_flujos=1)
    app = LuzxferApp(arrancar_motor=False, sesion="cliente-x")
    async with app.run_test() as pilot:
        await pilot.press("s")
        await pilot.pause()
        await pilot.press("escape")
        await pilot.pause()
        assert not isinstance(app.screen, SesionesScreen)


async def test_el_selector_no_borra_la_sesion_abierta(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    _sesion(tmp_path, "abierta", n_flujos=1)
    app = LuzxferApp(arrancar_motor=False, sesion="abierta")
    async with app.run_test() as pilot:
        await pilot.press("s")
        await pilot.pause()
        app.screen.query_one("#ses-tabla", DataTable).move_cursor(row=0)
        await pilot.press("delete")
        await pilot.pause()
        assert sesiones.ruta_de("abierta").exists()


async def test_una_sesion_ilegible_se_lista_y_no_se_puede_elegir(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    _sesion(tmp_path, "buena", n_flujos=1)
    sesiones.dir_sesiones().joinpath("rota.db").write_bytes(b"no soy sqlite")
    app = LuzxferApp(arrancar_motor=False, sesion="buena")
    async with app.run_test() as pilot:
        await pilot.press("s")
        await pilot.pause()
        tabla = app.screen.query_one("#ses-tabla", DataTable)
        assert tabla.row_count == 2

        # buscar la fila de la rota sin asumir el orden
        fila = next(
            f for f in range(tabla.row_count)
            if "rota" in str(tabla.get_row_at(f)[0])
        )
        tabla.move_cursor(row=fila)
        await pilot.press("enter")
        await pilot.pause()
        # sigue abierto: elegir una sesion ilegible no hace nada
        assert isinstance(app.screen, SesionesScreen)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `./venv/bin/python -m pytest tests/test_sesiones.py -k selector -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'luzxfer.tui.screens.sesiones'`

- [ ] **Step 3: Implement `SesionesScreen` and hook `action_sesiones()` into `app.py`**

`DataTable` con `id="ses-tabla"` y columnas nombre / flujos / candidatos / modificada, siguiendo el estilo de pintado de `app.py` (`rich.text.Text` con los colores ya definidos ahí; las ilegibles en el rojo `#e05c5c`). Los estilos de `#ses-caja` imitan los de `#rep-caja` que ya existen en `styles.tcss`.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `./venv/bin/python -m pytest tests/test_sesiones.py -q && ./venv/bin/python -m pytest -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/luzxfer/tui/screens/sesiones.py src/luzxfer/tui/app.py \
        src/luzxfer/tui/styles.tcss tests/test_sesiones.py
git commit -m "feat(tui): pantalla selectora de sesiones"
```

---

## Tarea 5: Historial grande sin truncado silencioso

Cabo suelto #3. Guardar el historial y después no mostrarlo entero es perderlo igual, así que cierra la Parte A.

**Files:**
- Modify: `src/luzxfer/core/store.py`
- Modify: `src/luzxfer/tui/app.py`
- Test: `tests/test_regresiones.py`

**Interfaces:**
- Consumes: `Store.list_flows()` tal como está hoy.
- Produces:
  - `Store._where(texto, metodo, estado, solo_marcados) -> tuple[str, list[object]]` — privado, extraído del cuerpo actual de `list_flows()`, que pasa a usarlo.
  - `Store.count_flows(*, texto: str = "", metodo: str = "", estado: str = "", solo_marcados: bool = False) -> int` — mismos filtros que `list_flows()`. **La llamada sin argumentos tiene que seguir devolviendo el total**, porque `actualizar_estado()` ya la usa así.
  - En `app.py`: `LIMITE_TABLA = 5000`; `refrescar_tabla()` lo pasa explícito, y `actualizar_estado()` añade `mostrando N de M` cuando lo que se muestra es menos que el total filtrado.

- [ ] **Step 1: Write the failing tests**

```python
def test_count_flows_acepta_los_mismos_filtros_que_list_flows():
    st = Store()
    for i in range(6):
        st.add_flow(Flow(
            request=Request(method="GET" if i % 2 else "POST",
                            url=f"http://ej.com/r{i}", headers=[("Host", "ej.com")]),
            response=Response(status=200 if i < 4 else 500),
        ))
    assert st.count_flows() == 6                       # sin filtros: el total
    assert st.count_flows(metodo="GET") == 3
    assert st.count_flows(estado="5xx") == 2
    assert st.count_flows(texto="/r1") == 1
    st.close()


def test_mas_flujos_que_el_limite_no_se_pierden_en_silencio():
    """Antes: refrescar_tabla usaba el limite=1000 por defecto de
    list_flows sin pasar nada. Con mas de 1000 flujos, filtrar o limpiar
    dejaba ver solo los 1000 mas recientes, sin decirlo en ninguna parte."""
    from luzxfer.tui import app as modulo

    st = Store()
    for i in range(modulo.LIMITE_TABLA + 25):
        st.add_flow(Flow(
            request=Request(method="GET", url=f"http://ej.com/r{i}",
                            headers=[("Host", "ej.com")]),
            response=Response(status=200),
        ))
    assert st.count_flows() == modulo.LIMITE_TABLA + 25
    assert len(st.list_flows(limite=modulo.LIMITE_TABLA)) == modulo.LIMITE_TABLA
    st.close()


async def test_la_barra_de_estado_avisa_cuando_la_tabla_esta_truncada(monkeypatch):
    from luzxfer.tui import app as modulo
    monkeypatch.setattr(modulo, "LIMITE_TABLA", 10)

    app = modulo.LuzxferApp(arrancar_motor=False)
    async with app.run_test() as pilot:
        for i in range(14):
            app._ingresar(_f(i))
        await pilot.pause()
        app.refrescar_tabla()
        app.actualizar_estado()
        await pilot.pause()

        estado = app.query_one("#estado", Static).render().plain
        assert "14 flujos" in estado
        assert "mostrando 10 de 14" in estado
        assert app.query_one("#flujos", DataTable).row_count == 10


async def test_sin_truncado_la_barra_no_dice_nada_de_mas(monkeypatch):
    from luzxfer.tui import app as modulo
    monkeypatch.setattr(modulo, "LIMITE_TABLA", 10)

    app = modulo.LuzxferApp(arrancar_motor=False)
    async with app.run_test() as pilot:
        for i in range(3):
            app._ingresar(_f(i))
        await pilot.pause()
        app.actualizar_estado()
        await pilot.pause()
        assert "mostrando" not in app.query_one("#estado", Static).render().plain
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `./venv/bin/python -m pytest tests/test_regresiones.py -k "limite or count_flows or truncada" -v`
Expected: FAIL — `TypeError: count_flows() got an unexpected keyword argument 'metodo'` y `AttributeError: module ... has no attribute 'LIMITE_TABLA'`

- [ ] **Step 3: Extract `_where()`, extend `count_flows()`, and add the notice in `app.py`**

`list_flows()` y `count_flows()` tienen que compartir el mismo `_where()`: dos constructores de `WHERE` que se separen con el tiempo es cómo se vuelve a colar un conteo que no coincide con lo que la tabla muestra. En `actualizar_estado()`, el aviso se calcula con `count_flows(texto=self._filtro)` para que respete el filtro activo.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `./venv/bin/python -m pytest -q`
Expected: PASS, 51 previos incluidos

- [ ] **Step 5: Commit**

```bash
git add src/luzxfer/core/store.py src/luzxfer/tui/app.py tests/test_regresiones.py
git commit -m "fix(tui): avisar cuando el historial no cabe entero en la tabla"
```

---

# Parte B — Los cinco cabos sueltos restantes

Independientes entre sí. Cada una se puede hacer, revisar y soltar sola.

## Tarea 6: Notas con atajo de teclado

Cabo suelto #1: `Store.set_note()` existe, está probado y ninguna tecla lo llama.

**Files:**
- Create: `src/luzxfer/tui/screens/nota.py`
- Modify: `src/luzxfer/tui/app.py`
- Modify: `src/luzxfer/tui/styles.tcss`
- Test: `tests/test_tui.py`

**Interfaces:**
- Consumes: `Store.set_note(fid, nota)`, `Store.get_flow(fid)`.
- Produces: `class NotaScreen(ModalScreen[str | None])` — recibe `nota_actual: str`, un `Input` con `id="nota-input"`, `enter` hace `dismiss(valor)`, `esc` hace `dismiss(None)`. En `app.py`: `Binding("n", "nota", "nota")` y `action_nota()`.

La nota se muestra como primera línea del panel de petición, en el ámbar `#f0a93b` que ya usa `app.py` para lo marcado. Sin columna nueva en la tabla: el ancho ya está repartido.

- [ ] **Step 1: Write the failing tests**

```python
async def test_la_tecla_n_guarda_una_nota_en_el_flujo():
    from textual.widgets import Input
    app = app_prueba()
    async with app.run_test() as pilot:
        app._ingresar(_flujo())
        await pilot.pause()
        app.query_one("#flujos", DataTable).move_cursor(row=0)
        await pilot.pause()
        fid = app._flujo_actual.id

        await pilot.press("n")
        await pilot.pause()
        app.screen.query_one("#nota-input", Input).value = "parametro q sin escapar"
        await pilot.press("enter")
        await pilot.pause()

        assert app.store.get_flow(fid).note == "parametro q sin escapar"


async def test_esc_en_la_nota_no_guarda_nada():
    from textual.widgets import Input
    app = app_prueba()
    async with app.run_test() as pilot:
        app._ingresar(_flujo())
        await pilot.pause()
        app.query_one("#flujos", DataTable).move_cursor(row=0)
        await pilot.pause()
        fid = app._flujo_actual.id
        await pilot.press("n")
        await pilot.pause()
        app.screen.query_one("#nota-input", Input).value = "esto se descarta"
        await pilot.press("escape")
        await pilot.pause()
        assert app.store.get_flow(fid).note == ""


async def test_la_nota_se_ve_en_el_panel_de_peticion():
    from textual.widgets import Input
    app = app_prueba()
    async with app.run_test() as pilot:
        app._ingresar(_flujo())
        await pilot.pause()
        app.query_one("#flujos", DataTable).move_cursor(row=0)
        await pilot.pause()
        await pilot.press("n")
        await pilot.pause()
        app.screen.query_one("#nota-input", Input).value = "revisar en el reporte"
        await pilot.press("enter")
        await pilot.pause()
        assert "revisar en el reporte" in app.query_one("#panel-req", Static).render().plain


async def test_nota_sin_seleccion_avisa_y_no_abre():
    app = app_prueba()
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("n")
        await pilot.pause()
        assert app.screen is app.screen_stack[0]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `./venv/bin/python -m pytest tests/test_tui.py -k nota -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'luzxfer.tui.screens.nota'`

- [ ] **Step 3: Implement `NotaScreen` and `action_nota()`**

`action_nota()` sigue el patrón que `action_repeater()` ya usa para el caso sin selección: `notify(..., severity="warning")` y volver sin apilar pantalla. Al volver con un valor, guardar y repintar el detalle con `_pintar_detalle()`.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `./venv/bin/python -m pytest -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/luzxfer/tui/screens/nota.py src/luzxfer/tui/app.py \
        src/luzxfer/tui/styles.tcss tests/test_tui.py
git commit -m "feat(tui): atajo n para anotar un flujo"
```

---

## Tarea 7: Confirmar un candidato

Cabo suelto #2. `Finding` persiste cuatro campos que nada escribe. Esta tarea despierta **solo `confirmed`**, que es la distinción que el README ya promete («Candidates, not findings»). `severity`, `cvss_vector` y `justification` siguen esperando al reporte **a propósito**: inventarles interfaz ahora es construir contra un formato de entregable que no está decidido.

**Files:**
- Modify: `src/luzxfer/core/store.py`
- Modify: `src/luzxfer/tui/app.py`
- Test: `tests/test_core.py`, `tests/test_tui.py`

**Interfaces:**
- Consumes: `Store.list_findings()`, la tabla `#hallazgos`.
- Produces:
  - `Store.set_confirmed(hid: int, confirmado: bool) -> None`
  - `Store.list_findings(*, kind: str = "", solo_confirmados: bool = False) -> list[Finding]` — parámetro nuevo, el default no cambia nada.
  - En `app.py`: `Binding("v", "confirmar", "confirmar")`, activo cuando la pestaña `tab-hall` tiene el foco. Una columna nueva al principio de `#hallazgos` con `✓` para los confirmados.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_core.py
def test_store_confirma_un_hallazgo_y_filtra_por_eso():
    st = Store()
    hid = st.add_finding(Finding(kind="REFLEJO", detail="q se refleja",
                                 url="http://ej.com/b", wstg=["WSTG-INPV-01"]))
    st.add_finding(Finding(kind="FUGA", detail="server: nginx", url="ej.com"))
    assert [h.confirmed for h in st.list_findings() if h.id == hid] == [False]

    st.set_confirmed(hid, True)
    assert [h.id for h in st.list_findings(solo_confirmados=True)] == [hid]
    st.set_confirmed(hid, False)
    assert st.list_findings(solo_confirmados=True) == []
    st.close()


def test_confirmar_sobrevive_al_reinicio(tmp_path):
    ruta = tmp_path / "s.db"
    st = Store(ruta)
    hid = st.add_finding(Finding(kind="REFLEJO", detail="q", url="http://ej.com/b"))
    st.set_confirmed(hid, True)
    st.close()
    otra = Store(ruta)
    assert [h.confirmed for h in otra.list_findings() if h.id == hid] == [True]
    otra.close()
```

```python
# tests/test_tui.py
async def test_la_tecla_v_confirma_el_candidato_resaltado():
    app = app_prueba()
    async with app.run_test() as pilot:
        app._ingresar(_flujo())
        await pilot.pause()
        app.query_one("#detalle").active = "tab-hall"
        await pilot.pause()
        app.query_one("#hallazgos", DataTable).focus()
        app.query_one("#hallazgos", DataTable).move_cursor(row=0)
        await pilot.pause()
        await pilot.press("v")
        await pilot.pause()
        assert any(h.confirmed for h in app.store.list_findings())
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `./venv/bin/python -m pytest tests/test_core.py -k confirm tests/test_tui.py -k tecla_v -v`
Expected: FAIL — `AttributeError: 'Store' object has no attribute 'set_confirmed'`

- [ ] **Step 3: Implement `set_confirmed()`, the `solo_confirmados` filter, and `action_confirmar()`**

`_agregar_hallazgo()` necesita guardar el `id` del hallazgo como `key` de la fila, igual que `_agregar_fila()` hace con los flujos: sin eso no hay forma de saber cuál se está confirmando. Reusar `update_cell()` con el patrón que `action_marcar()` ya tiene.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `./venv/bin/python -m pytest -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/luzxfer/core/store.py src/luzxfer/tui/app.py \
        tests/test_core.py tests/test_tui.py
git commit -m "feat: confirmar un candidato con v"
```

---

## Tarea 8: Avisar del cuerpo sin decodificar en el panel principal

Cabo suelto #5. El repeater avisa cuando la codificación no es gzip ni deflate; el panel de respuesta de la pantalla principal muestra los bytes crudos sin decir nada, y alguien busca un reflejo en brotli y concluye que no hay.

**Files:**
- Modify: `src/luzxfer/tui/app.py`
- Test: `tests/test_regresiones.py`

**Interfaces:**
- Consumes: `Response.encoding`, `Response.decoded_body()`.
- Produces: nada nuevo; cambia el cuerpo de `LuzxferApp._pintar_detalle()`.

- [ ] **Step 1: Write the failing tests**

```python
async def test_el_panel_avisa_si_el_cuerpo_quedo_sin_decodificar():
    """brotli no esta en la stdlib. El repeater ya lo avisaba; el panel
    principal mostraba bytes crudos y se quedaba callado."""
    f = Flow(
        request=Request(method="GET", url="http://ej.com/x", headers=[("Host", "ej.com")]),
        response=Response(status=200, reason="OK", body=b"\x1b\x0e\x00\x00br",
                          headers=[("Content-Type", "text/html"),
                                   ("Content-Encoding", "br")]),
    )
    app = LuzxferApp(arrancar_motor=False)
    async with app.run_test() as pilot:
        app._ingresar(f)
        await pilot.pause()
        app.query_one("#flujos", DataTable).move_cursor(row=0)
        await pilot.pause()
        assert "sin decodificar" in app.query_one("#panel-resp", Static).render().plain


async def test_gzip_no_genera_aviso_porque_si_se_decodifica():
    import gzip
    f = Flow(
        request=Request(method="GET", url="http://ej.com/x", headers=[("Host", "ej.com")]),
        response=Response(status=200, reason="OK",
                          body=gzip.compress(b"<html>hola</html>"),
                          headers=[("Content-Type", "text/html"),
                                   ("Content-Encoding", "gzip")]),
    )
    app = LuzxferApp(arrancar_motor=False)
    async with app.run_test() as pilot:
        app._ingresar(f)
        await pilot.pause()
        app.query_one("#flujos", DataTable).move_cursor(row=0)
        await pilot.pause()
        panel = app.query_one("#panel-resp", Static).render().plain
        assert "hola" in panel and "sin decodificar" not in panel
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `./venv/bin/python -m pytest tests/test_regresiones.py -k decodificar -v`
Expected: FAIL — `assert "sin decodificar" in ...`

- [ ] **Step 3: Add the notice in `_pintar_detalle()`**

Misma condición que `screens/repeater.py` usa ya en `_mostrar()`: codificación presente y fuera de `("gzip", "x-gzip", "deflate", "identity")`. Vale la pena que las dos lean la misma constante en vez de repetir la tupla.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `./venv/bin/python -m pytest -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/luzxfer/tui/app.py src/luzxfer/tui/screens/repeater.py \
        tests/test_regresiones.py
git commit -m "fix(tui): avisar del cuerpo sin decodificar en el panel principal"
```

---

## Tarea 9: Borrar el paquete vacío `tui/widgets/`

Cabo suelto #4. YAGNI: un paquete vacío es una promesa de estructura que nadie pidió.

**Files:**
- Delete: `src/luzxfer/tui/widgets/`

- [ ] **Step 1: Confirm nothing imports it**

Run: `grep -rn "widgets" src tests --include=*.py | grep -v "textual.widgets"`
Expected: sin resultados. **Si aparece algo, parar**: el paquete está en uso y este cabo suelto estaba mal diagnosticado.

- [ ] **Step 2: Delete it and run the suite**

```bash
git rm -r src/luzxfer/tui/widgets
./venv/bin/python -m pytest -q
```
Expected: 51+ PASS

- [ ] **Step 3: Commit**

```bash
git commit -m "chore: borrar el paquete vacio tui/widgets"
```

---

## Tarea 10: Documentación honesta

Cabo suelto #6. El README manda a `pip install luzxfer`, que no está en PyPI, y el `pyproject.toml` apunta a `github.com/jdavid/luzxfer`, que no es la cuenta de este repo — que además no tiene remoto ni tags. Tres referencias a cosas que no existen, en el primer archivo que alguien lee.

**Supuesto a corregir si está mal:** la cuenta de GitHub es `xXJuanDavidXx`, tomada de `git config user.name`. Si es otra, cambiarla en este paso.

**Files:**
- Modify: `README.md`
- Modify: `pyproject.toml`
- Modify: `progress.md`

- [ ] **Step 1: Fix the install instructions and the URLs**

En `README.md`, la sección **Install** pasa a instalar desde fuente, y dice en una línea que PyPI llega cuando la 0.1.0 salga. En `pyproject.toml`, `Homepage` e `Issues` apuntan a `github.com/xXJuanDavidXx/luzxfer`.

- [ ] **Step 2: Document sessions and the new keys**

En **Use**, los tres comandos acordados (`luzxfer`, `-s cliente-x`, `--sesiones`), diciendo que **el historial ya no se pierde al salir** y dónde viven las sesiones. En la tabla **Keys**, las tres nuevas: `s` sesiones, `n` nota, `v` confirmar candidato. En el roadmap, marcar sesiones como hecho.

- [ ] **Step 3: Update `progress.md`**

Tachar los seis cabos sueltos resueltos y dejar anotado lo que sigue abierto a propósito: `severity`, `cvss_vector` y `justification` esperan al reporte, y cambiar de sesión en caliente no está implementado.

- [ ] **Step 4: Verify the commands in the README actually work**

```bash
./venv/bin/luzxfer --help       # las opciones -s y --sesiones aparecen
./venv/bin/luzxfer --sesiones   # lista
```

- [ ] **Step 5: Commit**

```bash
git add README.md pyproject.toml progress.md
git commit -m "docs: sesiones, claves nuevas y referencias que existen de verdad"
```

---

## Cierre

- [ ] `./venv/bin/python -m pytest -q` — todo verde, tres corridas seguidas (los tests de la TUI tienen temporizadores; una sola corrida no prueba que sean estables)
- [ ] `./venv/bin/ruff check src tests` — limpio
- [ ] Prueba a mano del motivo de todo esto: abrir una sesión con `-s`, generar tráfico, salir, volver a entrar sin argumentos y comprobar que el historial está ahí
