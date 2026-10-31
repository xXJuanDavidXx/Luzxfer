# Dirección del proyecto

Decisiones de rumbo, tomadas el **2026-10-31**. Este archivo existe porque el
trabajo avanza en iteraciones autónomas: es lo que mantiene el criterio
constante entre una sesión y la siguiente. No repite el README (qué es la
herramienta) ni `progress.md` (en qué punto está).

## El objetivo

Llegar a una experiencia **casi tan profesional como Burp Suite, en una TUI**.
No un visor de tráfico con extras: un banco de trabajo donde un pentest real se
pueda hacer de principio a fin sin salir de la terminal.

Método: **kaizen**. Mejora continua, en incrementos que siempre dejan la
herramienta funcionando y probada. Nunca una rama larga con medio subsistema a
medias.

## Las cuatro decisiones

### 1. La brecha con Burp que se cierra primero: interceptar y editar en vuelo

Hoy `builtin.py::_manejar()` lee la petición, la reenvía de inmediato y emite
el `Flow`. No hay pausa, ni cola, ni edición. **El README se llama
«Intercepting proxy» y la herramienta no intercepta** en el sentido de Burp:
observa y reenvía.

Capturar funciona bien, y eso no está en discusión. Lo que falta es *cuándo*
se puede meter mano:

| | hoy | con interceptación |
| --- | --- | --- |
| ver el tráfico | sí | sí |
| reenviar modificado | sí, con `r` — pero el original ya viajó | antes de que salga |
| que el servidor nunca vea el original | **no** | sí |

El repeater manda una *segunda* petición. Para un login de un solo uso, un
token CSRF que se quema o un flujo de pago irrepetible, esa diferencia es todo.

Forma acordada:

```
[ INTERCEPT: ON ]   cola: 3

POST /api/login HTTP/1.1
Host: objetivo.com
Content-Type: application/json

{"user":"admin","pass":"x"}

 f soltar   d descartar   e editar
 t apagar interceptacion
```

### 2. DAST: activo, pero con correa

El README dice hoy, literalmente, «It is not a scanner and it confirms
nothing». Eso cambia — de forma controlada, no abriendo la jaula:

- **Exige un scope definido.** Sin alcance no se manda nada.
- **Se dispara a mano** sobre un endpoint o una familia, nunca solo.
- **Pide confirmación** antes de payloads destructivos.
- **Respeta un límite de peticiones por segundo.**

El analista sigue decidiendo. La herramienta solo deja de hacerle perder
tiempo. La distinción *candidato* contra *hallazgo confirmado* que el README ya
promete se vuelve más importante, no menos.

### 3. IA: las dos opciones detrás de una sola interfaz

Mismo patrón que `Engine`, que es la pieza que ya sostiene el diseño: se define
una interfaz abstracta, y cambiar de proveedor es cambiar una clase.

- **Primero el adaptador remoto**, por `urllib.request` de la stdlib, que ya
  habla HTTPS. **Cero dependencias nuevas, Termux intacto.** Clave por variable
  de entorno, **apagado por defecto**.
- **El adaptador local** queda como extra opcional, igual que `[mitm]`. Rompe
  la regla de cero dependencias nativas, así que nunca en el camino por defecto.

**Advertencia que va en el README y en la interfaz, no solo aquí:** mandar
tráfico a una API de terceros es sacar datos de un cliente fuera de su
perímetro. En un pentest con contrato eso puede ser una violación. Tiene que
ser **opt-in explícito, visible mientras está encendido, y documentado**. La
interfaz local existe precisamente para quien no pueda permitirse la remota.

### 4. Orden: cimientos primero

Sin un concepto de alcance, disparar payloads es como se le pega a un host
fuera de contrato en un engagement real. **El scope no es una feature más: es
el prerrequisito de todo lo activo.** Y sin scope, interceptar significa pausar
en cada píxel de analítica y cada CDN — inusable.

```
1. Sesiones y deuda      → docs/superpowers/plans/2026-10-31-sesiones-y-deuda.md
2. Scope y sitemap         prerrequisito de 3 y de 5
3. Interceptar y editar    la brecha mas grande con Burp
4. Intruder                ya en el roadmap; Flow.source reserva "intruder"
5. DAST con correa         necesita 2
6. Interfaz de IA          remota primero, local como extra
7. Matriz WSTG y reporte   la razon de ser declarada
8. Adaptador mitmproxy     la interfaz Engine ya esta lista
9. API de plugins
```

Los pasos 1 y 2 no son deuda aburrida que se tolera: son lo que hace posible
todo lo de arriba sin convertir la herramienta en un peligro.

## Lo que no se negocia

Estas reglas ganan sobre cualquier feature nueva. Si una capacidad las rompe,
se rediseña la capacidad o va en un extra opcional.

1. **Ninguna interfaz habla con un motor concreto.** Se habla con `Engine`.
   Lo mismo aplicará a la interfaz de IA y a la de DAST.
2. **Nada en `core/` importa de `tui/`.** Es lo que deja posible un segundo
   front end o una corrida headless.
3. **Cero dependencias nativas en el camino por defecto.** stdlib más Textual.
   Lo que necesite compilar va en un extra, como `[mitm]`. El motivo es Termux,
   que es la razón de existir frente a Burp.
4. **Lo que escribes es lo que viaja.** El repeater no corrige la petición. Un
   repeater que la ordena no sirve para probar qué hace el servidor con la
   desordenada. Esto aplicará igual al editor de interceptación.
5. **Nada activo sin alcance.** Ninguna petición que la herramienta origine
   por su cuenta sale sin un scope que la autorice.
6. **Candidato no es hallazgo.** Nada se marca como confirmado sin que un
   humano lo confirme. Ni el DAST ni la IA pueden saltarse eso.
7. **Cada incremento deja la herramienta funcionando**, con sus tests y con
   `ruff` limpio. TDD: el test primero, comprobado en rojo.

## Bitácora

Una línea por iteración: qué se hizo y por qué eso y no otra cosa.

- **2026-10-31** — Dirección fijada (este archivo). Antes: `progress.md` con el
  estado real verificado (51 tests, ruff limpio) y el plan de sesiones y deuda.
  Pendiente de arranque: Tarea 1 del plan, validación de nombres de sesión.
