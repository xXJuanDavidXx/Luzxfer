# Estado del proyecto

Bitácora de avance de **luzxfer 0.3.0**. Última verificación: **2026-11-01**.

Este archivo dice en qué punto está la herramienta de verdad: qué está hecho y
comprobado, qué está a medias, y qué falta. No repite el README (qué es la
herramienta), `docs/direccion.md` (hacia dónde va y por qué) ni el historial de
git (cómo se llegó aquí).

---

## Verificado hoy

Todo esto se corrió en esta máquina, no es recuerdo de la última sesión:

| comprobación | resultado |
| --- | --- |
| `./venv/bin/python -m pytest` | **248 pasan**, ~53 s, sin fallos ni saltados |
| `./venv/bin/ruff check src tests` | **limpio**, `All checks passed!` |
| `luzxfer --version` | `luzxfer 0.3.0` |
| sesiones, de punta a punta | 7 flujos, salir, volver sin argumentos, 7 flujos |
| brotli, contra Juice Shop real | `br` ilegible → `gzip` legible al filtrar |
| vista combinada | izquierda x=2 ancho 66, derecha x=72 ancho 66 |

**Los tests solo corren desde `./venv/bin/python -m pytest`**: el `python3` del
sistema tiene pytest pero no textual, y el venv tiene las dos cosas.

---

## Qué cambió en la 0.3.0

- **Intruder completo**, cuatro modos, con ritmo prudente de fábrica y
  resultados en tablas aparte del historial. Ver `CHANGELOG.md`.
- **Presentación del cuerpo** según lo que es: JSON indentado, binarios
  resumidos, `p` para el crudo.
- **Cacería de bugs**, nueve sospechas: cuatro reales, tres descartadas con
  motivo por escrito, dos que eran agujeros de cobertura. La peor fue el
  charset ignorado, que hacía invisible cualquier reflejo con acentos.

El detalle versión por versión está en [CHANGELOG.md](CHANGELOG.md), que
hasta la 0.2.0 figuraba aquí como deuda.

## Qué cambió en la 0.2.0

La razón del salto de versión es un **cambio de comportamiento por defecto**: la
0.1.0 perdía el historial al salir y la 0.2.0 lo guarda.

### Sesiones (lo nuevo grande)

- El default deja de ser `:memory:`. Sin argumentos se retoma la última sesión;
  `-s NOMBRE` abre o crea una; `--sesiones` las lista y sale; `s` abre el
  selector dentro de la TUI.
- Los nombres pasan por una **lista blanca**, porque el nombre lo escribe el
  usuario y se vuelve una ruta de archivo. Sin eso, `-s ../otro` escribe fuera
  del directorio.
- El listado abre en **solo lectura**: asomarse no crea ni migra nada, y un
  `.db` corrupto sale marcado como ilegible en vez de tumbar el selector. Con
  el directorio de solo lectura —como se guarda evidencia— hay un respaldo con
  `immutable=1`, sin el cual toda sesión sana se reportaría como ilegible.
- **No se borra la sesión abierta**: el `Store` seguiría escribiendo en un
  archivo que ya no está.

### Los seis cabos sueltos de la 0.1.0, cerrados

1. ~~`Store.set_note()` sin forma de llamarse~~ → tecla `n`, con la nota
   precargada al reabrir y vacía para borrarla.
2. ~~`Finding` con cuatro campos que nada escribía~~ → `v` confirma un
   candidato. **`severity`, `cvss_vector` y `justification` siguen dormidos a
   propósito**, esperando al reporte: inventarles interfaz ahora sería
   construir contra un formato de entregable que no está decidido.
3. ~~Truncado silencioso a 1000 flujos~~ → límite explícito de 5000 y la barra
   dice `mostrando 5000 de 12431`, respetando el filtro activo.
4. ~~`tui/widgets/` vacío~~ → borrado.
5. ~~Brotli sin avisar~~ → ver abajo, resultó ser mucho más grave.
6. ~~README prometiendo PyPI y un GitHub inexistentes~~ → instalación desde
   fuente y URLs reales.

### Brotli: estaba mal clasificado

Lo tenía anotado como cosmético. El daño real era que `decoded_body()` devolvía
los bytes comprimidos, así que **el detector buscaba reflejos en basura binaria
y devolvía lista vacía** — falso negativo silencioso, el mismo fallo ya
corregido para gzip, y hoy el caso común porque brotli es el default de nginx,
Cloudflare y Express.

Tres respuestas: el motor recorta el `Accept-Encoding` (cero dependencias,
funciona en Termux), el extra `[br]` descomprime de verdad, y si ni lo uno ni
lo otro la interfaz lo dice **y avisa de que el detector tampoco pudo leer ese
cuerpo**.

### Otras

- Vista combinada de petición y respuesta con `t` o con el botón, al estilo
  Burp, con la preferencia guardada. Estrena la tabla `meta`, que llevaba en el
  esquema sin usarse desde la primera versión.
- `Store` acepta un `timeout`: `add_flow()` se llama desde el bucle de la
  interfaz, y cinco segundos esperando un bloqueo son cinco de TUI congelada.
- `count_flows()` acepta los mismos filtros que `list_flows()` y comparten un
  único `_where()`.
- El aviso de «truncado» medía el cuerpo comprimido: mentía con cualquier gzip.

---

## Lo que falta

El orden y su razonamiento están en `docs/direccion.md`. Resumido:

1. **Intruder**, cuatro modos con grep-match. Subió al primer puesto: `send_raw`
   ya manda por socket crudo con TLS y el repeater ya envía fuera del hilo de
   la interfaz, así que está casi construido, y no necesita scope porque no
   dispara por su cuenta.
2. **Sitemap y scope.** Hoy el proxy captura todo sin filtro de alcance.
3. **Interceptar y editar en vuelo.** La brecha más grande con Burp:
   `builtin.py::_manejar()` reenvía la petición de inmediato, así que cuando la
   ves ya llegó al servidor. Contra un token de un solo uso, el repeater no
   sirve: manda una *segunda* petición.
4. **DAST con correa**, que necesita el 2.
5. **Matriz WSTG y reporte**, la razón de ser declarada del proyecto.
6. mitmproxy, plugins.

**IA: aplazada sin fecha**, y no por razones técnicas. Ver la decisión 3 de
`docs/direccion.md`.

---

## Pedido por el usuario, pendiente

Detectado probando la 0.2.0 contra OWASP Juice Shop el **2026-10-31**. Se
atiende cuando mejor encaje con el desarrollo, no de inmediato.

**Dos de los tres se resolvieron** en la 0.3.0: el `.woff` (ahora los
binarios se resumen con volcado hexadecimal) y las redirecciones, que
resultaron ser 304 de caché y no redirecciones. Queda:

1. **Pestañas del repeater.** Hoy es un modal que pierde el estado al
   cerrarlo. Burp guarda una pestaña numerada por petición, con su respuesta,
   y las conserva. Encaja natural después del Intruder, porque las dos
   pantallas quieren lo mismo: guardar trabajo en curso dentro de la sesión.
2. **Seguir redirecciones, pero solo en el repeater.** En el proxy sería un
   error —escondería lo que el servidor contestó— y Burp tampoco lo hace ahí.
   En el repeater es una opción útil y pequeña; va con el punto 1.
3. **Mostrar los binarios como binarios.** Una respuesta `font/woff` de 40 KB
   se pinta como 40 KB de basura. **No es un fallo de decodificación** —el
   usuario ya sospechó que era un falso positivo y acertó—, es un archivo
   binario mostrado como texto. Debería decir `40.904 bytes de font/woff
   (binario)` y ofrecer un volcado hexadecimal, en vez de llenar el panel.
   Mismo principio que el aviso de brotli: si no se puede leer, decirlo.

## Deuda conocida que sigue abierta

1. **Cambiar de sesión en caliente no está implementado.** Elegir otra en el
   selector te dice qué comando la abre. Reemplazar el `Store` vivo con el
   motor corriendo y flujos entrando es un problema distinto del de no perder
   el historial.
2. **`severity`, `cvss_vector` y `justification` siguen sin escribirse.**
   Esperan al reporte, a propósito.
3. **La preferencia de vista es por sesión, no global.** Cuando aparezca la
   segunda preferencia global —el límite de peticiones del DAST, o si la
   interceptación arranca encendida— esto gradúa a `dir_datos()/config`.
4. **`listar()` deja `-shm` y `-wal` detrás.** Leer una base WAL necesita el
   índice de memoria compartida aunque solo se lea, y una conexión de solo
   lectura no puede borrarlo. Basura inofensiva que limpia la siguiente
   conexión de escritura; documentada en el docstring de `resumen()`.
5. **El detector lee el cuerpo entero sin límite.** 50 MB cuestan 0,07 s pero
   131 MB de pico. **Se deja así a propósito:** recortar crearía falsos
   negativos —un reflejo más allá del corte dejaría de verse—, que es la
   clase de fallo contra la que pelea medio proyecto. Documentado, no
   arreglado.

---

## Reglas de diseño que no se negocian

Las siete están en `docs/direccion.md` con su razonamiento. En corto: nadie
habla con un motor concreto, `core/` no importa de `tui/`, cero dependencias
nativas en el camino por defecto, lo que escribes es lo que viaja, nada activo
sin alcance, candidato no es hallazgo, y cada incremento deja la herramienta
funcionando con sus tests y `ruff` limpio.

---

## Cómo trabajar en esto

```bash
cd /home/davy/HERRAMIENTAS/luzxfer

./venv/bin/python -m pytest -q          # 136 tests, ~34 s
./venv/bin/ruff check src tests         # linter
./venv/bin/luzxfer --sesiones           # que hay guardado
./venv/bin/luzxfer -s lab -u http://127.0.0.1:8099   # modo inverso
```

Para probar contra un lab local hay que usar **modo inverso**, porque los
navegadores basados en Chromium nunca mandan `localhost` ni `127.0.0.1` por un
proxy configurado. Y el motor integrado **no intercepta HTTPS**: un `CONNECT`
contesta 501 explicando por qué.
