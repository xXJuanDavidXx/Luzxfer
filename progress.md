# Estado del proyecto

Bitácora de avance de **luzxfer 0.1.0**. Última verificación: **2026-10-31**.

Este archivo dice en qué punto está la herramienta de verdad: qué está hecho y
comprobado, qué está a medias, y qué falta. No repite lo que ya cuentan el
README (para qué sirve) ni el historial de git (cómo se llegó aquí).

---

## Verificado hoy

Todo esto se corrió en esta máquina, no es recuerdo de la última sesión:

| comprobación | resultado |
| --- | --- |
| `pytest` | **51 pasan**, 12,89 s, sin fallos ni saltados |
| `ruff check src tests` | **limpio**, `All checks passed!` |
| `luzxfer --version` | `luzxfer 0.1.0` |
| `luzxfer --help` | arranca y muestra las seis opciones |
| `git status` | limpio, sin cambios sin confirmar |

**Un hallazgo del entorno:** el `venv/` no tenía las dependencias de
desarrollo. Tenía `textual 8.2.8` y el paquete instalado en modo editable,
pero ni `pytest`, ni `pytest-asyncio`, ni `ruff` — así que los 51 tests que
declara el último commit no se podían correr sin instalarlos. Ya quedaron
puestos (`pytest 9.2.0`, `pytest-asyncio 1.4.1`, `ruff`). El `python3` del
sistema tiene pytest pero no textual, así que **los tests solo corren desde
`./venv/bin/python -m pytest`**, no con el pytest del sistema.

---

## Lo que funciona

### Núcleo (`core/`)

- **Modelos** (`models.py`, 161 líneas) — `Request`, `Response`, `Flow`,
  `Finding`. Sin dependencias, que es lo que permite cambiar de motor sin
  tocar nada más. `Response.decoded_body()` descomprime gzip y deflate para
  analizar, mientras `body` guarda los bytes tal como vinieron, que son la
  evidencia.
- **Almacén SQLite** (`store.py`, 257 líneas) — stdlib a propósito, cero
  dependencias nativas. WAL, índices por `started`/`host`/`status`, y
  `UNIQUE(kind, detail, url)` en `findings`, que es lo que evita el ruido de
  escáner. Sesión persistente entre arranques, o `:memory:` por defecto.
- **Interfaz de motor** (`engine/base.py`) — `Engine` abstracto +
  `EngineInfo` con las capacidades declaradas. Ninguna interfaz habla con un
  motor concreto.
- **Motor integrado** (`engine/builtin.py`, 228 líneas) — proxy directo e
  inverso, solo stdlib. Lee cuerpos `chunked`, conserva cabeceras duplicadas
  al reenviar, respeta `HEAD`, y contesta `CONNECT` con un 501 que explica el
  motivo en vez de fallar callado.
- **Repeater** (`tools/repeater.py`, 146 líneas) — socket crudo, no
  `http.client`: lo que escribes es lo que viaja. Conserva duplicados y orden
  de cabeceras, acepta métodos no estándar, habla TLS por su cuenta (así que
  llega a HTTPS aunque el motor no intercepte), y solo recalcula
  `Content-Length`.
- **Detector de candidatos** (`tools/detector.py`, 124 líneas) — reflejos,
  atributos de cookie, cabeceras de seguridad ausentes, fugas de versión,
  errores 5xx. Cada candidato trae sus IDs WSTG. Lo del servidor se registra
  **por host, no por URL**.

### Interfaz (`tui/`)

- **App** (`app.py`, 346 líneas) — historial en `DataTable` con filtro por
  URL, paneles de petición/respuesta, pestaña de candidatos, barra de estado
  con contadores y estado del motor. Inserción **incremental**: un flujo nuevo
  no reconstruye la tabla y no mueve la selección salvo que ya estuvieras al
  final. Navegación vim (`j`/`k`/`g`/`G`), marcar (`m`), limpiar (`c`).
- **Pantalla de repeater** (`screens/repeater.py`, 123 líneas) — modal con
  editor, envío en worker (la red nunca en el hilo de la interfaz), y salida
  desplazable. Sus flujos entran al historial y pasan por el detector.

### Tests (878 líneas, 51 casos en 3 archivos)

- `test_core.py` (24) — modelos, almacén, motor contra un servidor HTTP real,
  repeater, detector.
- `test_tui.py` (15) — TUI headless con el harness de pilotaje de Textual.
- `test_regresiones.py` (12) — uno por cada fallo corregido en la revisión,
  escritos primero y comprobados en rojo contra el código anterior.

---

## Lo que falta

Del roadmap del README, en el orden en que tiene sentido hacerlo:

- [ ] **Intruder** — cuatro modos, con grep-match sobre los resultados.
      `Flow.source` ya reserva el valor `"intruder"`, pero no hay nada detrás.
- [ ] **Sitemap y alcance** — árbol de rutas por host y un concepto de
      *scope*. Hoy el proxy captura todo lo que pasa, sin filtro de alcance.
- [ ] **Matriz de cobertura WSTG y generación de reporte** — es la razón de
      ser del proyecto y es lo único grande que todavía no existe. El detector
      ya etiqueta con IDs WSTG, así que la mitad de los datos está; falta la
      matriz que diga qué pruebas se deben todavía, y el reporte que las
      convierta en entregable.
- [ ] **Adaptador de motor mitmproxy** — TLS, HTTP/2 y WebSockets. La
      interfaz `Engine` ya está hecha para esto; es implementar una clase.
- [ ] **API de plugins.**

---

## Deuda y cabos sueltos detectados

Cosas que encontré leyendo el código hoy y que no están en el roadmap. Ninguna
rompe nada ahora mismo, pero todas van a estorbar después:

1. **`Store.set_note()` no tiene forma de llamarse desde la interfaz.**
   Existe, está probado, y no hay ninguna tecla que agregue una nota a un
   flujo. Camino muerto hasta que se le ponga un atajo.
2. **`Finding` guarda `severity`, `cvss_vector`, `justification` y
   `confirmed`, pero nada los escribe.** Están en el modelo y en el esquema
   SQL esperando a la matriz de cobertura y al reporte. Hasta entonces, todo
   candidato se persiste con esos cuatro campos vacíos.
3. **`list_flows()` tiene `limite=1000` por defecto**, y `refrescar_tabla()`
   lo usa sin pasar nada. Con más de 1000 flujos en la sesión, filtrar o
   limpiar deja ver solo los 1000 más recientes, en silencio. Hace falta o
   paginación o un aviso.
4. **`tui/widgets/` es un paquete vacío.** Solo tiene el `__init__.py`.
5. **Brotli queda sin decodificar** — no está en la stdlib, y meterlo rompería
   la regla de cero dependencias nativas. Está documentado en el docstring de
   `decoded_body()`, pero en la interfaz solo se avisa en el repeater, no en
   el panel de respuesta de la pantalla principal.
6. **El README promete cosas que todavía no existen fuera de esta máquina:**
   `pip install luzxfer` (no está publicado en PyPI) y
   `github.com/jdavid/luzxfer` como Homepage e Issues en el `pyproject.toml`.
   El repo **no tiene remoto configurado ni tags**. O se publica, o esas tres
   referencias deberían decir que el proyecto es local por ahora.

---

## Reglas de diseño que no se negocian

Antes de tocar nada, estas dos son las que sostienen todo lo demás:

1. **Ninguna interfaz habla con un motor directamente.** Se habla con
   `Engine`. Es lo que hace que mitmproxy sea una clase nueva y no una
   reescritura.
2. **Nada en `core/` importa de `tui/`.** Es lo que deja posible un segundo
   front end o una corrida headless.

Y dos más que vienen del propósito de la herramienta:

3. **Cero dependencias nativas en el camino por defecto.** Todo stdlib excepto
   Textual, porque el objetivo es que instale en Termux, donde no hay wheels
   precompilados y cualquier extensión en C o Rust se compila en el teléfono.
   Lo que necesite compilar va en un extra opcional, como `[mitm]`.
4. **El repeater no corrige lo que escribes.** Un repeater que ordena la
   petición no sirve para probar qué hace el servidor con la desordenada.

---

## Cómo trabajar en esto

```bash
cd /home/davy/HERRAMIENTAS/luzxfer

./venv/bin/python -m pytest -q          # 51 tests, ~13 s
./venv/bin/ruff check src tests         # linter
./venv/bin/luzxfer --no-engine -d sesion.db   # revisar una sesión guardada
```

Los tests **solo** corren con el python del venv: el del sistema no tiene
textual. Las dependencias de desarrollo ya están instaladas ahí.

Para probar contra un lab local hay que usar **modo inverso**
(`-u http://127.0.0.1:8099`), porque los navegadores basados en Chromium
nunca mandan `localhost` ni `127.0.0.1` por un proxy configurado.
