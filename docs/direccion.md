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

### 3. IA: aplazada, y no por falta de ganas

**Decisión del 2026-10-31: no se implementa por ahora.** El esfuerzo va entero
a que la experiencia base iguale a Burp.

El motivo de aplazarla no es técnico — `urllib` de la stdlib habla HTTPS y el
adaptador remoto no costaba una dependencia nueva. Es que **mandar tráfico a
una API de terceros es sacar datos de un cliente fuera de su perímetro**, y en
un pentest con contrato eso puede ser una violación del acuerdo. Una
herramienta que lo hace fácil de activar lo hace fácil de activar por error.

Si se retoma, estas son las condiciones, ya decididas, para no rediscutirlas:

- Detrás de una interfaz abstracta, mismo patrón que `Engine`: cambiar de
  proveedor es cambiar una clase.
- Adaptador remoto por `urllib.request`, cero dependencias nuevas, clave por
  variable de entorno, **apagado por defecto**.
- Adaptador local como extra opcional, igual que `[mitm]`.
- **Opt-in explícito, visible en la interfaz mientras esté encendido, y
  documentado en el README.** Nunca silencioso.

Y la regla 6 de abajo sigue rigiendo: ni la IA ni el DAST confirman un
hallazgo. Eso es de un humano.

### 4. Orden: cimientos primero

Sin un concepto de alcance, disparar payloads es como se le pega a un host
fuera de contrato en un engagement real. **El scope no es una feature más: es
el prerrequisito de todo lo activo.** Y sin scope, interceptar significa pausar
en cada píxel de analítica y cada CDN — inusable.

```
1. Sesiones y deuda      → docs/superpowers/plans/2026-10-31-sesiones-y-deuda.md
2. Intruder                send_raw ya hace el trabajo sucio
3. Scope y sitemap         prerrequisito de 5
4. Interceptar y editar    la brecha mas grande con Burp
5. DAST con correa         necesita 3
6. Matriz WSTG y reporte   la razon de ser declarada
7. Adaptador mitmproxy     la interfaz Engine ya esta lista
8. API de plugins
9. Personalizacion: temas, colores, atajos configurables

   IA: aplazada sin fecha, por la decision 3.
```

La **personalización** es deliberadamente lo último: una herramienta que se
puede pintar de otro color pero no sabe interceptar una petición no es una
alternativa a Burp. Se planifica cuando el resto esté hecho.

**El Intruder subió al puesto 2 el 2026-10-31**, por encima de scope y de
interceptación, y conviene saber por qué para no revertirlo sin pensar:

- **Ya está casi construido.** `send_raw()` manda por socket crudo, habla TLS,
  conserva cabeceras duplicadas y acepta métodos no estándar; el repeater ya
  envía fuera del hilo de la interfaz. Un Intruder es eso en bucle, con un
  punto de inyección y una tabla de resultados.
- **No necesita scope**, al revés que el DAST. La regla 5 dice «nada que la
  herramienta origine *por su cuenta*»: el Intruder no dispara por su cuenta,
  el analista elige la petición y marca dónde. Es la misma autorización que
  ya tiene el repeater.

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

## Decisiones del Intruder (2026-10-31)

Tomadas antes de escribir una línea, para no rediscutirlas a mitad:

1. **Los cuatro modos de Burp** — sniper, ariete, horquilla, racimo. Comparten
   el mismo motor de envío y solo cambian en cómo combinan los conjuntos de
   payloads: una función con cuatro ramas, no cuatro implementaciones.
2. **Marcadores `§`, como Burp**, insertados con una tecla porque `§` no está
   en la mayoría de teclados. Así una petición copiada de Burp se pega y
   funciona.
3. **Ritmo prudente por defecto**: 4 concurrentes, tope de 10 peticiones por
   segundo, ritmo visible mientras corre y tecla para abortar. Subirlo es
   explícito. Un Intruder que por defecto tumba el entorno de un cliente es
   una llamada telefónica, no un hallazgo.
4. **Resultados en tabla aparte**, no en el historial. Dos razones concretas:
   10.000 filas vuelven el historial inservible para lo que es, y el detector
   correría sobre las 10.000 generando miles de candidatos basura. Lo que
   valga se promueve al historial a mano.

## Cómo se trabaja (2026-11-01)

Reglas de proceso que pidió el usuario, no de diseño:

1. **Una rama por cambio.** Se trabaja en una rama con nombre, y se funde a
   `main` **solo cuando todo está estable**: suite verde, `ruff` limpio y
   comprobado a mano cuando toca.
2. **`main` no se queda atrás.** La contrapartida de la regla 1, y nace de un
   susto real: el 2026-10-31 el usuario estuvo depurando un 304 ya corregido
   porque su árbol estaba en `main` mientras el arreglo vivía en una rama
   lateral, 17 commits por delante. Una rama que tarda en fundirse es una
   trampa, así que se funde en cuanto está verde y no «cuando acabe todo».
3. **La personalización va al final.** Temas, colores, atajos configurables:
   no es prioridad. Queda anotada en el roadmap para planificarla cuando el
   núcleo esté completo, y no antes.

## Bitácora

Una línea por iteración: qué se hizo y por qué eso y no otra cosa.

- **2026-10-31** — Dirección fijada (este archivo). Antes: `progress.md` con el
  estado real verificado (51 tests, ruff limpio) y el plan de sesiones y deuda.
- **2026-10-31** — IA aplazada sin fecha (decisión 3). Tareas 1 a 4 del plan
  hechas: sesiones con nombre, persistentes por defecto, con selector en la
  TUI. 103 tests. El historial ya no se pierde al salir.
- **2026-10-31** — Brotli, reportado por el usuario contra OWASP Juice Shop,
  reclasificado de cosmético a **grave y corregido fuera de turno**. No era
  «el cuerpo se ve feo»: `decoded_body()` devolvía los bytes comprimidos, así
  que el detector buscaba reflejos en basura binaria y no encontraba nada —
  falso negativo silencioso, en el caso común y no en el raro. El motor
  recorta ahora el `Accept-Encoding`, que es la única solución que también
  funciona en Termux. La lección para lo que viene: **todo lo que el detector
  no pueda leer tiene que gritarlo, nunca devolver lista vacía en silencio.**
- **2026-10-31** — Pedido de estilo del usuario, añadido al plan como Tarea 10:
  un botón al estilo Burp para ver petición y respuesta **juntas**, con la
  vista de pestañas de hoy intacta como opción. Primer uso de la tabla `meta`,
  que estaba en el esquema sin usarse desde la primera versión. A partir de
  aquí se versiona: la 0.2.0 sale con la Tarea 11, porque cambia un
  comportamiento por defecto (la 0.1.0 perdía el historial, la 0.2.0 no).
- **2026-11-01** — Auditoría de documentación contra la realidad, en rama
  propia. Resultado: la tabla de teclas del README estaba **completa y
  correcta** (los huecos que marcaban mis scripts eran artefactos del regex,
  no de la documentación), pero el **pie de la pantalla recortaba trece de
  veinte atajos a ochenta columnas**, en silencio, sin flecha ni puntos
  suspensivos. El mismo patrón que el brotli, el 304 y el `.woff`: la
  herramienta no fallaba, escondía la mitad de sí misma, y las funciones
  invisibles eran justo las que más costaron. Se añade `?` con la lista
  completa y se baja el pie a seis teclas.
  **La decisión de fondo:** no apretar más teclas en el pie. A ningún ancho
  caben las veinticuatro, así que el problema no era el espacio sino creer
  que el pie podía ser el catálogo. El pie es para lo diario; el catálogo
  tiene su pantalla. Y esa pantalla se construye de los atajos **activos**,
  nunca de una lista escrita a mano: una ayuda mantenida aparte del código
  se desincroniza en el primer cambio y manda a probar teclas muertas.
  **La lección, que es la misma de siempre:** lo que la interfaz no pueda
  mostrar tiene que decirlo, nunca descartarlo callando.
- **2026-11-01** — Auditoría del núcleo buscando el patrón que ha producido
  todos los fallos de este proyecto: el error silencioso. Aparecido en el
  sitio más caro posible, la entrega de flujos del motor al núcleo, donde
  los dos motores hacían `except Exception: pass`.
  **El equilibrio que había que encontrar:** el código viejo acertaba en que
  el proxy no puede caerse por un consumidor roto, y se equivocaba en lo que
  cobraba por ello. No son opciones excluyentes: se sobrevive al fallo *y*
  se cuenta. Ahora hay contador con cerrojo, motivo del último, `N PERDIDOS`
  en rojo en la barra y un aviso la primera vez.
  **La regla, ya por tercera vez:** lo que la herramienta no pueda hacer
  tiene que decirlo. Un detector que no lee un cuerpo, un pie que no pinta
  un atajo y un motor que no entrega un flujo son el mismo fallo —callar—
  y los tres producen la misma consecuencia: el analista concluye que no
  hay nada donde sí lo había.
- **2026-11-01** — Exportación a `curl` (`u`), que era una brecha real
  contra Burp: no había **ninguna** forma de sacar una petición de la
  herramienta, y un hallazgo que solo existe dentro de tu pantalla cuesta
  de defender ante un cliente.
  **Lo que enseñó este incremento no fue la función, fue el test.** Escribí
  el exportador con `--data-binary` creyendo que así el cuerpo viajaba
  intacto. El test que ejecuta el comando de verdad contra el servidor de
  eco falló enseñando el `/etc/passwd` de esta máquina: `-d` y
  `--data-binary` interpretan un `@` inicial como «lee este archivo». Es
  decir, el exportador convertía un cuerpo capturado que empezara por `@`
  en una fuga de archivos hacia el objetivo. El flag correcto es
  `--data-raw`.
  **La regla que queda:** un test que comprueba la *forma* del texto
  exportado habría pasado con ese fallo dentro. Lo que exporta la
  herramienta se prueba **ejecutándolo**, no mirándolo. Vale para el curl
  de hoy y para cualquier otro formato que salga de aquí.
- **2026-11-01** — Ergonomía de Repeater e Intruder, del feedback del
  usuario, con plan escrito en `docs/superpowers/plans/`. Dos decisiones
  que merecen quedar:
  **`r` abre, `R` envia; el Intruder no gana `I`.** Minuscula abre la
  herramienta, mayuscula le manda el flujo. El Repeater tiene banco de
  pestañas, asi que abrir y enviar son cosas distintas; el Intruder ataca
  una sola peticion y no tiene estado vacio que abrir, asi que forzar un
  `I` gemelo seria simetria por la simetria. La asimetria es la respuesta
  honesta.
  **Mitad del Intruder ya existia.** `desde_archivo`, `desde_rango`,
  `conjuntos_desde_texto`, `sustituir` estaban en core y probados. El
  trabajo fue interfaz, no logica: detalle de cada resultado reconstruido
  con `sustituir` (gratis y exacto, en vez de retener cuerpos que un
  ataque de un millon no puede guardar), y un cargador de payloads que
  llama a lo que ya habia.
  **Lo que volvio a aparecer: la interfaz que miente por maquetacion.** La
  barra del repeater y la fila del rango del intruder dibujaban sus
  botones fuera de la caja; los atajos funcionaban, asi que los tests de
  teclado no lo veian. Ahora hay tests que miden que los botones caen
  dentro. Un boton que no se puede pulsar es el mismo fallo que un atajo
  que el pie no muestra: existe y no se alcanza.
- **2026-11-01** — Auditoria del nucleo: encontrado que `parse_raw`
  normalizaba `\r\n` a `\n` en el cuerpo. Un multipart reenviado por el
  repeater o el intruder llegaba con los saltos cambiados y el servidor lo
  rechazaba. El mismo patron de siempre —corrupcion silenciosa de lo que
  viaja—, esta vez en la ruta que mas presume de fidelidad: «lo que
  escribes es lo que viaja». El cuerpo es dato; sus saltos no se tocan. La
  cabecera sigue parseandose con cualquiera de los dos. Confirmado antes
  de arreglar que el TextArea de Textual SI conserva los \r\n, asi que el
  arreglo en el nucleo basta para toda la ruta del editor.
- **2026-11-01** — El usuario fue a usar luzxfer contra un lab de
  PortSwigger (HTTPS) y choco con que la Opcion A —el motor mitm, que es
  el unico que intercepta TLS— no estaba documentada: ni como arrancarla
  ni, sobre todo, como confiar en la CA. Un motor que no se puede poner en
  marcha es como no tenerlo. Añadida guia paso a paso. La leccion no es de
  codigo: una funcion sin el camino para usarla es el mismo fallo de
  descubribilidad que el pie que escondia atajos, solo que en la
  documentacion.
- **2026-11-01** — El arreglo del cuerpo binario en la interceptacion
  (0.9.1) estaba solo en el motor integrado; el motor mitm tenia el mismo
  fallo en `_editar`, por el mismo `decode('replace')` de `_a_crudo`.
  Encontrado auditando a conciencia: la regla 1 dice que ninguna interfaz
  habla con un motor concreto, y el corolario es que un fallo de
  comportamiento en un motor casi seguro esta en el otro. Arreglado igual y
  con tests que fallan si se revierte. La leccion: cuando se arregla algo en
  un motor, hay que ir a mirar el otro en el acto.
- **2026-11-01** — El usuario uso el repeater contra un lab https de
  PortSwigger y choco con `SSL: WRONG_VERSION_NUMBER`. Causa: el puerto por
  defecto (80) se decidia antes que el TLS, asi que un Host sin puerto en una
  pestaña https hacia TLS contra el 80. Invertido: el TLS manda sobre el
  puerto. La leccion repetida —el valor de verdad sale de usar la
  herramienta contra un objetivo real; esto no lo cazo ningun test porque
  todos los tests traian el puerto en el Host.
- **2026-11-02** — Rama `termux` creada en `v0.11.1`, el ultimo commit estable
  verificado (675 tests, ruff limpio). Es un punto conocido-bueno para la
  version portatil, no un fork de desarrollo: **no se commitea en ella** salvo
  que algo no se pueda mantener detras de un extra.
  **El motivo de la reserva:** luzxfer ya corre en Termux sin `[mitm]` ni
  `[br]` gracias al mecanismo de extras. Si las costuras del DAST quedan tan
  limpias como exige su spec (`core/` stdlib, OOB detras de `[oob]`), la
  version de Termux *es* la misma rama sin extras instalados. Una rama que
  diverge de verdad significa arreglar cada bug dos veces.
  Entran al repo el spec y el plan del DAST 10/10
  (`docs/superpowers/{specs,plans}/2026-11-02-dast-10x*`). Quedan **dos
  decisiones abiertas** antes de empezar, anotadas aqui para no perderlas:
  si el servidor OOB por defecto debe ser el publico (el spec dice que si; yo
  sostengo que contradice la decision 3 de este documento, la que aplazo la
  IA por sacar datos del cliente de su perimetro), y si la FASE F
  (nuclei/nikto) se corta.
- **2026-11-02** — Resueltas las dos decisiones abiertas del DAST 10/10.
  Yo habia propuesto exigir self-host para el OOB; **el operador lo corrigio
  y tiene razon**: exigir montar un servidor excluye a quien no tiene tiempo
  ni dinero, y convierte una capacidad en un privilegio. Las **dos opciones
  existen** y elige el analista al activar: publico (bug bounty, labs,
  pentest con riesgo aceptado) o self-host (contrato que prohibe salir del
  perimetro).
  **Lo que si se conserva de la objecion:** el riesgo real de la decision 3
  no era que existiera la opcion, era que se activara *por descuido*. Asi
  que activar OOB es deliberado, el canal se elige explicitamente, y mientras
  este activo se ve en pantalla contra que servidor se trabaja. Esa
  visibilidad es la diferencia entre «lo decidio el analista» y «se activo
  solo».
  **FASE F cortada como estaba escrita:** nuclei y nikto eran ejemplos, y
  atar el diseno a dos binarios concretos era el error. El caso de uso
  —aprovechar herramientas que el analista ya tenga— se replantea desde cero
  y por la **API de plugins que ya existe**, no como fase del nucleo: un
  plugin que envuelve una herramienta es justo para lo que esa API se hizo,
  se instala solo si se quiere y su cobertura queda fuera del Youden por
  construccion.
  **La rama `termux` si tiene motivo para divergir algun dia**, y no es el
  que yo supuse: no son los extras, es la **UX en pantalla de telefono**.
  Eso se piensa aparte; hasta entonces la rama sigue siendo solo un punto
  conocido-bueno.
