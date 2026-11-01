# Ergonomía de Repeater e Intruder — Plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Que abrir una herramienta y mandarle una petición sean dos acciones distintas, que el Intruder cargue payloads y muestre el detalle de la petición, y que el cuerpo JSON se pueda formatear en el Repeater.

**Architecture:** Son retoques de interfaz sobre lógica que en su mayoría ya existe. Los cargadores de payloads (`desde_archivo`, `desde_rango`) y el formateo de JSON (`embellecer_json`) ya están en `core/`; lo que falta es que las pantallas lleguen a ellos. La separación abrir/enviar se hace en los `BINDINGS` y las acciones de `app.py`, sin tocar los motores ni el almacén. Ninguna interfaz habla con un motor directamente; nada en `core/` importa de `tui/`.

**Tech Stack:** Python 3.14, Textual, stdlib. Tests con `./venv/bin/python -m pytest` (única forma válida; el python del sistema no tiene textual).

**Spec:** El feedback del usuario del 2026-11-01, recogido en esta conversación. No hay documento de spec aparte; este plan es el acuerdo.

## Global Constraints

- Identificadores, docstrings y comentarios **en español sin tildes ni eñes** (el README es la excepción).
- Cero dependencias nativas nuevas: solo stdlib + Textual.
- **Lo que escribes es lo que viaja**: el Repeater manda lo que hay en el editor. El `Content-Length` lo recalcula `send_raw` por defecto (`recalcular_cl=True`), así que formatear el cuerpo no lo rompe; no reintroducir un recálculo manual.
- **Candidato no es hallazgo**: nada de esto confirma nada.
- Cada tarea deja la herramienta funcionando, con sus tests y `ruff` limpio. Verificar y commitear en órdenes separadas.
- Ramificar: una rama para todo el plan, fundir en `main` solo cuando esté estable. El push lo gatilla el usuario, nunca el plan.
- `./venv/bin/ruff check .` limpio antes de cada commit.

## Review Focus

Entradas que el feedback implica pero que conviene fijar con un test en la tarea dueña:

- **`R`/`I` sin ninguna fila seleccionada** → aviso «selecciona un flujo primero», no traceback (Tarea 1, Tarea 3).
- **Formatear un cuerpo que dice ser JSON y no lo es** → no se toca el editor y se avisa; no dejar el cuerpo a medio parsear (Tarea 2).
- **Formatear cuando no hay cuerpo, o el content-type no es JSON** → no hace nada visible y lo dice, en vez de vaciar el editor (Tarea 2).
- **Rango numérico al revés (`desde > hasta`) o archivo de diccionario inexistente** → el `ErrorAtaque` se enseña en la pantalla, no tumba el Intruder (Tarea 4).
- **Rango enorme** (p. ej. 1..10_000_000) → se respeta el `limite` existente y se avisa de lo que se recortó, en vez de congelar la interfaz (Tarea 4).

---

### Task 1: Separar abrir Repeater de enviarle una petición

**Files:**
- Modify: `src/luzxfer/tui/app.py` (BINDINGS, `action_repeater`; añadir `action_repeater_enviar`)
- Modify: `src/luzxfer/tui/teclas.py` (añadir id a `ACCIONES`)
- Modify: `src/luzxfer/tui/screens/ayuda.py` (clasificar el atajo nuevo en un grupo)
- Test: `tests/test_tui_enviar.py` (crear)

**Interfaces:**
- Consumes: `RepeaterScreen(store, nuevo: Flow | None = None)` (ya existe; con `nuevo=None` abre el banco sin añadir pestaña).
- Produces: acción `repeater` (abre, `r`) y acción `repeater_enviar` (envía el flujo seleccionado, `R`). Ambas con `id` configurable.

- [ ] **Step 1: Escribir el test que falla**

```python
async def test_r_abre_el_repeater_sin_anadir_pestana():
    # con un flujo seleccionado, `r` abre el banco pero NO crea una pestaña nueva
    # (el reproche del usuario: abrir no es enviar)
    # abrir con el store vacio de repeticiones => 0 pestañas
    ...
    await pilot.press("r")
    assert isinstance(app.screen, RepeaterScreen)
    assert len(app.screen.pestanas()) == 0

async def test_R_manda_el_flujo_seleccionado_al_repeater():
    ...
    await pilot.press("R")
    assert isinstance(app.screen, RepeaterScreen)
    assert len(app.screen.pestanas()) == 1

async def test_R_sin_seleccion_avisa_y_no_abre():
    # sin fila seleccionada no hay traceback
    ...
    await pilot.press("R")
    assert not isinstance(app.screen, RepeaterScreen)
```

- [ ] **Step 2: Ejecutar y ver que fallan**

Run: `./venv/bin/python -m pytest tests/test_tui_enviar.py -q`
Expected: FAIL (hoy `r` siempre añade la pestaña del flujo actual).

- [ ] **Step 3: Cambiar el binding y las acciones en `app.py`**

`Binding("r", "repeater", "repeater", id="repeater")` abre el banco: `push_screen(RepeaterScreen(self.store))` (sin `nuevo`). Añadir `Binding("R", "repeater_enviar", "enviar al repeater", show=False, id="repeater_enviar")` y `action_repeater_enviar` que, con `self._flujo_actual`, hace `push_screen(RepeaterScreen(self.store, self._flujo_actual))`; sin flujo, `notify(... warning)` como el resto de acciones.

- [ ] **Step 4: Registrar la acción como configurable**

Añadir `"repeater_enviar"` a `ACCIONES` en `teclas.py` y clasificar el atajo en `GRUPOS` de `ayuda.py` (grupo «herramientas»). Esto es obligatorio: `test_todos_los_atajos_estan_clasificados` y `test_todas_las_teclas_de_la_app_son_configurables` fallan si no.

- [ ] **Step 5: Ejecutar los tests nuevos y la suite de teclas/ayuda**

Run: `./venv/bin/python -m pytest tests/test_tui_enviar.py tests/test_teclas.py tests/test_ayuda.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "feat(tui): r abre el repeater, R le manda el flujo seleccionado"
```

---

### Task 2: Formatear el cuerpo JSON en el editor del Repeater

**Files:**
- Modify: `src/luzxfer/core/tools/cuerpo.py` (añadir `formatear_cuerpo_crudo`)
- Modify: `src/luzxfer/tui/screens/repeater.py` (acción `formatear`, binding, botón)
- Modify: `src/luzxfer/tui/styles.tcss` si hace falta para el botón
- Test: `tests/test_cuerpo.py` (añadir), `tests/test_repeater_formato.py` (crear)

**Interfaces:**
- Consumes: `embellecer_json(texto) -> str | None` y `es_json(ctype) -> bool` (ya existen en `cuerpo.py`).
- Produces: `formatear_cuerpo_crudo(crudo: str) -> tuple[str, str]` — devuelve `(peticion_nueva, nota)`. Si el cuerpo es JSON válido, lo reorganiza y reensambla la petición cruda; si no hay cuerpo, no es JSON o el JSON es inválido, devuelve `(crudo, nota)` con `crudo` intacto y `nota` explicando por qué no se tocó.

- [ ] **Step 1: Escribir el test de `formatear_cuerpo_crudo`**

```python
def test_formatea_el_cuerpo_json_y_deja_las_cabeceras():
    crudo = 'POST /x HTTP/1.1\r\nContent-Type: application/json\r\n\r\n{"a":1,"b":2}'
    nuevo, nota = formatear_cuerpo_crudo(crudo)
    assert '"a": 1' in nuevo and "POST /x HTTP/1.1" in nuevo
    assert nota  # dice que lo reorganizo

def test_json_invalido_no_toca_nada():
    crudo = 'POST /x HTTP/1.1\r\nContent-Type: application/json\r\n\r\n{roto'
    nuevo, nota = formatear_cuerpo_crudo(crudo)
    assert nuevo == crudo and "no es JSON" in nota.lower() or "invalid" in nota.lower()

def test_sin_cuerpo_no_hace_nada():
    crudo = 'GET /x HTTP/1.1\r\nHost: o.com\r\n\r\n'
    nuevo, nota = formatear_cuerpo_crudo(crudo)
    assert nuevo == crudo

def test_content_type_no_json_no_toca_nada():
    crudo = 'POST /x HTTP/1.1\r\nContent-Type: text/plain\r\n\r\n{"a":1}'
    nuevo, nota = formatear_cuerpo_crudo(crudo)
    assert nuevo == crudo
```

- [ ] **Step 2: Ejecutar y ver que falla**

Run: `./venv/bin/python -m pytest tests/test_cuerpo.py -k formatear -q`
Expected: FAIL ("formatear_cuerpo_crudo not defined").

- [ ] **Step 3: Implementar `formatear_cuerpo_crudo(crudo: str) -> tuple[str, str]` en `cuerpo.py`**

Separar cabeceras de cuerpo por el primer `\r\n\r\n`; leer el content-type de las cabeceras; si `es_json(ctype)` y hay cuerpo, probar `embellecer_json(cuerpo)`; si devuelve texto, reensamblar `cabeceras + "\r\n\r\n" + cuerpo_bonito`. En cualquier otro caso devolver el crudo igual con una nota. No tocar `Content-Length` (lo recalcula `send_raw`).

- [ ] **Step 4: Ejecutar y ver que pasa**

Run: `./venv/bin/python -m pytest tests/test_cuerpo.py -k formatear -q`
Expected: PASS.

- [ ] **Step 5: Escribir el test de la pantalla**

```python
async def test_formatear_reorganiza_el_editor_actual():
    # abrir repeater con un POST JSON compacto, pulsar la accion, el editor queda indentado
    ...
    assert '"a": 1' in pant.editor_actual().text

async def test_formatear_json_invalido_avisa_y_no_vacia_el_editor():
    # el editor conserva su texto; sale una nota
    ...
```

- [ ] **Step 6: Añadir la acción, el binding y el botón en `repeater.py`**

`Binding("ctrl+f", "formatear", "formatear JSON", priority=True)`; `action_formatear` lee el editor actual, llama a `formatear_cuerpo_crudo`, reescribe el `TextArea` y enseña la nota con `notify`. Añadir un botón «formatear» a `#rep-barra` y atenderlo en `on_button_pressed`. Mencionar `ctrl+f` en la pista del título.

- [ ] **Step 7: Ejecutar la suite del repeater y ruff**

Run: `./venv/bin/python -m pytest tests/test_repeater_formato.py tests/test_repeticiones.py -q && ./venv/bin/ruff check .`
Expected: PASS y limpio.

- [ ] **Step 8: Commit**

```bash
git add -A
git commit -m "feat(repeater): formatear el cuerpo JSON con ctrl+f y boton"
```

---

### Task 3: Intruder — enviar por selección y ver el detalle de la petición

**Files:**
- Modify: `src/luzxfer/tui/app.py` (`action_intruder`: conservar `i` = abrir sobre el flujo seleccionado; aviso si no hay)
- Modify: `src/luzxfer/tui/screens/intruder.py` (panel de detalle de la petición)
- Modify: `src/luzxfer/tui/styles.tcss` (hueco del detalle)
- Test: `tests/test_intruder_detalle.py` (crear)

**Interfaces:**
- Consumes: `IntruderScreen(flujo: Flow)` (ya existe), `Flow.request.raw()`.
- Produces: en la pantalla del Intruder, un panel de solo lectura con la petición base (el `raw()`), visible junto al editor de posiciones.

**Decisión (el usuario pidió escoger una de dos):** el Intruder es de una sola petición — no tiene banco de pestañas como el Repeater, así que no hay un estado «vacío» que abrir. Por eso `i` abre el Intruder **sobre la petición seleccionada** (modelo seleccionar-y-tecla, una de las dos opciones ofrecidas). No se añade `I`: sería redundante. Esta asimetría con el Repeater es deliberada y se documenta.

- [ ] **Step 1: Escribir el test del detalle**

```python
async def test_el_intruder_muestra_la_peticion_base():
    # con un flujo seleccionado, `i` abre el intruder y se ve el raw de la peticion
    ...
    assert isinstance(app.screen, IntruderScreen)
    detalle = app.screen.query_one("#int-detalle", Static).render().plain
    assert "GET /x" in detalle

async def test_i_sin_seleccion_avisa():
    ...
    await pilot.press("i")
    assert not isinstance(app.screen, IntruderScreen)
```

- [ ] **Step 2: Ejecutar y ver que falla**

Run: `./venv/bin/python -m pytest tests/test_intruder_detalle.py -q`
Expected: FAIL (no existe `#int-detalle`).

- [ ] **Step 3: Añadir el panel de detalle en `intruder.py`**

En `compose`, añadir un `Static(id="int-detalle")` (o un `VerticalScroll` con él dentro si la petición es larga) que muestre `self.flujo.request.raw()`. Rellenarlo en `on_mount`. Que `action_intruder` en `app.py` siga avisando si no hay flujo.

- [ ] **Step 4: Ejecutar y ver que pasa**

Run: `./venv/bin/python -m pytest tests/test_intruder_detalle.py -q`
Expected: PASS.

- [ ] **Step 5: Ejecutar la suite del intruder y ruff**

Run: `./venv/bin/python -m pytest tests/test_intruder.py tests/test_intruder_detalle.py -q && ./venv/bin/ruff check .`
Expected: PASS y limpio.

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "feat(intruder): muestra la peticion base; i abre sobre la seleccionada"
```

---

### Task 4: Intruder — cargar diccionario y rango numérico desde la interfaz

**Files:**
- Modify: `src/luzxfer/tui/screens/intruder.py` (pantalla modal de carga o controles; usar los cargadores del core)
- Modify: `src/luzxfer/tui/styles.tcss`
- Test: `tests/test_intruder_payloads.py` (crear)

**Interfaces:**
- Consumes: `desde_archivo(ruta, *, limite=1_000_000) -> list[str]`, `desde_rango(desde, hasta, paso=1, *, ancho=0) -> list[str]`, `ErrorAtaque` (todos ya existen en `core/tools/intruder.py`). `conjuntos_desde_texto` ya expande líneas `@ruta`.
- Produces: en la pantalla del Intruder, una forma de insertar en el área de payloads (`#int-payloads`) el resultado de un diccionario (archivo) o de un rango numérico, sin teclear a mano el convenio `@`.

- [ ] **Step 1: Escribir los tests**

```python
async def test_cargar_un_rango_numerico_llena_los_payloads():
    # pedir rango 1..5 => el area de payloads contiene 1,2,3,4,5 (una por linea)
    ...
    assert pant.query_one("#int-payloads", TextArea).text.split() == ["1","2","3","4","5"]

async def test_cargar_un_diccionario_desde_archivo(tmp_path):
    # escribir un archivo con 3 lineas; cargarlo deja 3 payloads
    ...

async def test_un_rango_al_reves_avisa_y_no_rompe():
    # desde=9 hasta=1 => ErrorAtaque capturado, aviso en pantalla, intruder sigue vivo
    ...
    assert isinstance(app.screen, IntruderScreen)

async def test_un_archivo_inexistente_avisa():
    ...
```

- [ ] **Step 2: Ejecutar y ver que fallan**

Run: `./venv/bin/python -m pytest tests/test_intruder_payloads.py -q`
Expected: FAIL.

- [ ] **Step 3: Implementar los controles de carga en `intruder.py`**

Añadir una acción (binding + botón) que abra un modal pequeño o pida los datos: para rango, campos `desde`/`hasta`/`paso`/`ancho` → `desde_rango(...)`; para diccionario, un campo de ruta → `desde_archivo(...)`. El resultado se **inserta** en `#int-payloads` (una por línea), respetando lo ya escrito y el separador `---` de conjuntos. Capturar `ErrorAtaque` y enseñarlo con `_estado(...)` o `notify(... error)`; nunca dejar que tumbe la pantalla. Respetar el `limite` existente y, si se recorta, decirlo.

- [ ] **Step 4: Ejecutar y ver que pasan**

Run: `./venv/bin/python -m pytest tests/test_intruder_payloads.py -q`
Expected: PASS.

- [ ] **Step 5: Ejecutar la suite del intruder y ruff**

Run: `./venv/bin/python -m pytest tests/test_intruder.py tests/test_intruder_payloads.py -q && ./venv/bin/ruff check .`
Expected: PASS y limpio.

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "feat(intruder): cargar diccionario y rango numerico desde la interfaz"
```

---

### Task 5: Documentación y versión

**Files:**
- Modify: `README.md` (secciones Repeater, Intruder; tabla de teclas con `R`; `ctrl+f`)
- Modify: `CHANGELOG.md` (entrada nueva)
- Modify: `docs/direccion.md` (bitácora: la decisión abrir/enviar y la asimetría del Intruder)
- Modify: `pyproject.toml`, `src/luzxfer/__init__.py` (subir versión)

**Interfaces:**
- Consumes: todo lo de las tareas 1–4.
- Produces: nada que consuma otra tarea; es el cierre.

- [ ] **Step 1: Actualizar el README**

Tabla de teclas: `r` abre el Repeater, `R` le manda el flujo, `i` abre el Intruder sobre el seleccionado. Sección Repeater: `ctrl+f` formatea el cuerpo JSON, y la respuesta se alcanza con `tab` (ya arreglado). Sección Intruder: el detalle de la petición, y cómo cargar diccionario y rango. Explicar la asimetría `R` vs `i` en una línea.

- [ ] **Step 2: Actualizar CHANGELOG y bitácora**

Entrada por cada tarea. En `direccion.md`, el porqué de minúscula-abre / mayúscula-envía y por qué el Intruder no gana `I`.

- [ ] **Step 3: Subir versión**

A `0.8.0` en `pyproject.toml` y `__init__.py` (hay funciones nuevas que cambian atajos: sube la menor).

- [ ] **Step 4: Verificación final**

Run: `./venv/bin/ruff check . && ./venv/bin/python -m pytest -q`
Expected: todo verde, ruff limpio.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "docs: version 0.8.0, ergonomia de repeater e intruder"
```

---

## Notas de autorrevisión

- **Cobertura del feedback:** `r`/`R` → Tarea 1. Botones → plegados en Tareas 2 (repeater) y 4 (intruder), donde su deliverable los necesita. Formateo JSON → Tarea 2. Intruder «cómo se mandan las peticiones» → Tarea 3 (decidido: seleccionar-y-`i`). Detalle de la petición → Tarea 3. Cargar payloads (diccionario + rango) → Tarea 4. DAST queda fuera: el usuario aún no lo ha probado.
- **Asimetría `R` (repeater) vs `i` (intruder):** deliberada y documentada. El Repeater tiene banco persistente de pestañas, así que «abrir» y «enviar» son dos cosas; el Intruder es de una sola petición y no tiene estado vacío que abrir.
- **Lo que ya existía:** `desde_archivo`, `desde_rango`, `conjuntos_desde_texto`, `embellecer_json`, `recalcular_cl`. El plan conecta la interfaz a lógica probada, no la reescribe.
