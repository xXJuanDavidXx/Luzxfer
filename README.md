# luzxfer

Proxy de interceptación y banco de trabajo de pentesting web que vive en tu
terminal.

Construido alrededor de la [OWASP WSTG](https://owasp.org/www-project-web-security-testing-guide/)
y no alrededor de las peticiones: lleva la cuenta de qué pruebas has hecho
contra qué endpoints, ata los hallazgos al tráfico que los demuestra, y
conserva ese estado entre sesiones.

> **Estado: alfa.** Funcionan el núcleo, las sesiones con nombre, el
> historial, el repeater, el Intruder, el alcance, el mapa del sitio y la
> interceptación en vuelo, el barrido activo y la matriz de cobertura WSTG
> con generación de informes. Ver el roadmap,
> y [CHANGELOG.md](CHANGELOG.md) para lo que cambió en cada versión.

---

## Por qué otro más

Burp es excelente y esto no pretende reemplazarlo. Existe por tres huecos:

- **Corre donde Burp no puede.** Una aplicación de terminal sin dependencias
  nativas funciona por SSH y en Android bajo Termux, donde ninguna
  herramienta con JVM va a funcionar.
- **Está organizado por metodología, no por herramienta.** Burp conoce tus
  peticiones; no sabe qué pruebas de la WSTG le debes todavía al cliente. Esa
  contabilidad suele acabar en una hoja de cálculo aparte.
- **La evidencia va pegada al hallazgo.** Un hallazgo guarda los flujos
  exactos que lo demuestran, así que la PoC no se reconstruye a mano a la
  hora del informe.

## Instalación

Todavía no está en PyPI. Desde las fuentes:

```bash
git clone https://github.com/xXJuanDavidXx/Luzxfer
cd Luzxfer
pip install -e .
```

Python 3.10+. La única dependencia de ejecución es
[Textual](https://textual.textualize.io/). Todo lo demás es librería estándar,
a propósito: eso es lo que lo mantiene instalable en Termux, donde no hay
*wheels* precompilados y cualquier extensión en C o Rust se compila en el
teléfono.

Hay dos extras opcionales. Los dos compilan y por eso ninguno funciona en
Termux — justamente por eso son extras y no dependencias:

```bash
pip install -e '.[mitm]'   # interceptación HTTPS
pip install -e '.[br]'     # leer cuerpos en brotli (ver Compresión)
```

## Uso

```bash
luzxfer                              # retoma tu última sesión, proxy en :8080
luzxfer -s acme-corp                 # abre o crea una sesión con nombre
luzxfer --sesiones                   # lista lo guardado y sale
luzxfer -p 9090                      # otro puerto
luzxfer -u http://127.0.0.1:8099     # modo inverso, para un lab local
luzxfer -s acme-corp --no-engine     # revisar una sesión sin levantar el proxy
luzxfer -d ~/trabajo/objetivo.db     # archivo de sesión en una ruta tuya
luzxfer -d :memory:                  # efímera, se pierde al salir
```

### Sesiones

**Cerrar luzxfer no pierde tu historial.** Las sesiones viven en
`~/.local/share/luzxfer/sesiones/` (o bajo `$XDG_DATA_HOME`), un archivo
SQLite cada una, con el tráfico, los candidatos, tus notas y tus marcas.
Arrancar sin argumentos reabre la última que usaste.

`s` abre el selector: qué hay guardado, cuánto tiene cada sesión, cuál está
abierta. Lee en solo lectura, así que asomarse no toca nada. No borra la
sesión que tienes abierta: el `Store` seguiría escribiendo en un archivo que
ya no está y perderías el trabajo del día.

Los nombres pasan por una lista blanca (letras, dígitos, `.`, `_`, `-`,
empezando por alfanumérico, 64 como máximo). El nombre se convierte en un
nombre de archivo, y una herramienta que reenvía peticiones arbitrarias no
tiene por qué escribir además rutas arbitrarias.

**El modo inverso importa más de lo que parece.** Los navegadores basados en
Chromium nunca mandan `localhost` ni `127.0.0.1` por un proxy configurado: es
una regla de exclusión implícita, por seguridad. Así que para mirar el
tráfico contra un lab local apuntas el navegador al puerto del propio proxy y
dejas que él reenvíe, en vez de configurar un proxy de sistema que sería
ignorado.

### Teclas

| tecla | hace |
| --- | --- |
| `j` / `k` o flechas | moverse por el historial |
| `f` | filtrar por url |
| `/` | buscar en url, cabeceras y cuerpos |
| `d` | conversor: base64, url, hex, html, JWT |
| `r` | abrir el repeater sobre el flujo seleccionado |
| `i` | abrir el Intruder sobre el flujo seleccionado |
| `t` | petición y respuesta lado a lado, y volver |
| `p` | alternar entre el cuerpo reorganizado y el crudo |
| `n` | escribir una nota en el flujo |
| `m` | marcar un flujo |
| `y` | comparar los dos flujos marcados |
| `u` | exportar: `curl`, petición cruda, respuesta cruda |
| `v` | confirmar el candidato seleccionado como hallazgo |
| `a` | alcance: qué entra en el contrato |
| `e` | mapa del sitio |
| `x` | interceptar: parar las peticiones antes de que salgan |
| `b` | barrido activo sobre el flujo seleccionado |
| `w` | matriz de cobertura WSTG e informe |
| `s` | sesiones |
| `c` | limpiar el historial (los candidatos se conservan) |
| `g` / `G` | primer / último flujo |
| `q` | salir |

`t` y el botón que está junto al filtro hacen lo mismo: petición y respuesta
en dos columnas en vez de dos pestañas, como Burp deja distribuirlas. La
pestaña de candidatos sigue alcanzable en los dos modos, y la elección se
recuerda con la sesión.

### Exportar

`u` saca el flujo de la herramienta en tres formas —`curl`, petición cruda y
respuesta cruda— que se recorren con `tab`. `ctrl+y` lo manda al
portapapeles; el texto está en un editor seleccionable porque el
portapapeles viaja por una secuencia de escape que muchos terminales
ignoran, y prometer que funcionó sería la manera de acabar pegando una
cadena vieja en un informe.

El `curl` reproduce lo que viajó, no algo parecido. De ahí tres decisiones
que parecen quisquillosas:

- **Todo va entre comillas**, aunque no haga falta. Editar el cuerpo del
  comando es justo para lo que se exporta, y un `&otro=1` añadido a mano a
  un argumento desnudo parte el comando en dos y manda el proceso al fondo.
- **`--data-raw`, nunca `-d` ni `--data-binary`.** Esto no es estilo: `-d` y
  `--data-binary` interpretan un `@` inicial como «lee este archivo del
  disco y mándalo». Un cuerpo capturado que empiece por `@/etc/passwd`
  convertiría el comando exportado en una fuga de archivos de la máquina de
  quien lo pegue. Hay un test que ejecuta el comando de verdad para
  comprobarlo — **y encontró este fallo** cuando el código usaba
  `--data-binary`.
- **Las cabeceras salen todas, `Content-Length` incluida.** curl calcularía
  la suya, pero quitarla haría que el comando mandase algo distinto de lo
  capturado. Si editas el cuerpo, ajústala o bórrala: sale un aviso
  recordándotelo.

Un cuerpo que no es texto —con un NUL, o que no decodifica— viaja en base64
y se deshace en la tubería con `base64 -d`. El comando queda más largo, pero
manda los mismos bytes, que es el único criterio que cuenta.

### Comparar

Marca dos flujos con `m` y pulsa `y`. «¿Qué cambió entre estas dos
respuestas?» es la pregunta que sigue a casi todo lo que hace el
Intruder: la misma petición con otro payload, o con otra sesión, y la
diferencia es el hallazgo.

```
comparar · flujos 1 y 2 · respuesta · −1 +1   tab cambia de lado

  HTTP/1.1 200 OK
  Content-Type: application/json

  {
    "usuario": "admin",
-   "rol": "administrador",
+   "rol": "invitado",
    "saldo": 1000
  }
```

`tab` alterna entre comparar las peticiones y las respuestas.

Se eligen con `m` porque ya existía: inventar otra forma de elegir dos
flujos cuando la herramienta ya tiene una sería dar dos maneras de hacer
lo mismo.

Se comparan los cuerpos **descomprimidos**. Dos respuestas con el mismo
contenido pueden tener bytes gzip distintos —basta con que el servidor
ponga otra marca de tiempo—, y comparar lo guardado diría que difieren
cuando son idénticas: te invitaría a buscar una diferencia que no existe.

### Conversor

`d` abre el conversor, y **no vacío**: busca en la petición el valor más
prometedor —un JWT en `Authorization`, una cookie, un parámetro que
parezca codificado— y lo trae ya dentro, diciendo de dónde salió.
Abrirlo vacío obliga a copiar a mano justo lo que la herramienta tiene
delante.

En vez de pedirte que elijas un formato a ciegas, enseña **qué podría
ser** el texto:

```
conversor  ·  de Authorization   ctrl+e codifica (base64) · esc cierra

── jwt ──
--- cabecera ---          --- cuerpo ---
{                         {
  "alg": "HS256",           "sub": "admin",
  "typ": "JWT"              "rol": "administrador"
}                         }

La firma NO se comprueba: esto solo abre el token.
```

Una interpretación solo se ofrece si el resultado **se puede leer** y
**cambia algo**. Decir que algo es base64 cuando al abrirlo sale basura
binaria manda a perseguir un fantasma, y una lista que siempre tiene
opciones no informa: si no se reconoce nada, lo dice.

`ctrl+e` codifica, recorriendo base64, url, hex y html.

### Buscar

`f` filtra por URL: es una consulta SQL y va en vivo mientras tecleas.

`/` busca el texto **en todo** — URL, cabeceras y cuerpos, de la petición
y de la respuesta, sin distinguir mayúsculas. Es la respuesta a «¿dónde
aparece este token?».

Van en teclas distintas porque cuestan distinto, y mezclarlas haría que
teclear en el filtro se volviera lento sin que se entienda por qué.

**Lo que no se puede hacer con un `LIKE` de SQL**, y esa es la razón de
que exista: el cuerpo guardado son los bytes tal como llegaron, así que
dentro de un gzip la aguja no está en claro. Un `LIKE` parecería
funcionar y se dejaría fuera casi todo el HTML de un objetivo real, en
silencio. Medido: buscar en 4001 respuestas comprimidas cuesta 0,07 s, y
el `LIKE` habría encontrado cero.

### Cómo se muestra un cuerpo

Un JSON minificado de dos mil caracteres en una línea no se puede leer, así
que se indenta. Un `.woff` de cuarenta kilobytes volcado como texto es peor
que inútil, así que se resume y se vuelca en hexadecimal. `p` alterna entre
eso y los bytes tal como llegaron.

**El crudo importa:** a veces el espaciado, una clave repetida o un escape
raro *son* el hallazgo, y eso solo se ve sin reorganizar. Y nunca se miente
sobre lo que llegó: si el cuerpo se reorganizó, si se recortó, o si el
servidor dijo JSON y mandó algo que no lo es, queda dicho encima.

### Repeater

`r` abre el repeater sobre el flujo seleccionado, **en una pestaña nueva**.

```
ctrl+s enviar · ctrl+w cerrar pestaña · ctrl+r seguir redirecciones · esc cerrar
```

**Las pestañas sobreviven a cerrar la pantalla y a cerrar la herramienta.**
Una petición que has pasado veinte minutos afinando es justo lo que no se
puede perder. Se guarda la petición y no la respuesta: lo que cuesta es lo
que escribiste tú, y la respuesta se vuelve a pedir en un segundo.

`ctrl+r` alterna seguir redirecciones, hasta cinco. Por defecto **no las
sigue**, igual que el proxy: un `30x` se enseña tal como lo mandó el
servidor, y seguirlo sin pedirlo escondería la respuesta que viniste a
mirar. Cuando las sigue, la salida dice por dónde pasó — el camino importa
tanto como el destino. Una redirección a **otro host** no se sigue nunca:
eso sería dejar que el objetivo saque la herramienta de su alcance.

El `Content-Length` se recalcula al enviar, porque editar una petición
cruda a mano y olvidarlo es el error más común que existe.

**Lo que escribes es lo que viaja.** El repeater escribe a un socket crudo en
vez de pasar por una librería HTTP, así que las cabeceras duplicadas siguen
duplicadas, no se añade ninguna a tus espaldas, y los métodos no estándar
salen tal como los escribiste. Un repeater que ordena tu petición no sirve
para probar qué hace el servidor con la desordenada. Además habla TLS por su
cuenta, así que llega a objetivos HTTPS aunque el motor integrado no los
intercepte. El envío va fuera del hilo de la interfaz: un objetivo lento
nunca congela la pantalla.

## Intruder

`i` abre el Intruder sobre el flujo seleccionado.

```
ctrl+m   envolver la selección (o la palabra bajo el cursor) en §
ctrl+l   lanzar       ctrl+x   abortar       ctrl+o   ordenar por largo
```

Los marcadores son `§`, como en Burp, para que una petición copiada de allí
se pegue y funcione. Como `§` no está en la mayoría de teclados, `ctrl+m` lo
inserta y nunca hace falta escribirlo.

**Los cuatro modos:**

| modo | conjuntos | qué hace |
| --- | --- | --- |
| `sniper` | 1 | una posición a la vez; las demás conservan su valor |
| `ariete` | 1 | el mismo payload en todas las posiciones a la vez |
| `horquilla` | uno por posición | los conjuntos en paralelo, en el mismo paso |
| `racimo` | uno por posición | producto cartesiano de todos |

En el cuadro de payloads, una línea con `---` separa un conjunto del
siguiente, y una línea que empieza por `@` es la ruta de un archivo de
payloads: pegar rockyou a mano no es viable.

**Ordenar por largo (`ctrl+o`) es el gesto central**, no un adorno. En un
fuzzing de credenciales o de IDOR lo que delata el acierto casi nunca es el
código de estado — suelen ser todos 200 — sino que una respuesta mida
distinto a las demás:

```
#   payload                      cod     largo     ms  grep
4   juice                        200     20367    248  apple, Juice
0   apple                        200      1617     13  apple, Juice
2   <script>alert(1)</script>    200        30    431
3   xyzzy                        200        30    335
1   ' OR 1=1--                   400         0    502
```

**El ritmo viene prudente de fábrica:** 4 peticiones concurrentes y un tope
de 10 por segundo, con el ritmo a la vista y `ctrl+x` para abortar. El tope
es del ataque entero y no de cada hilo, así que subir la concurrencia no lo
multiplica. Por encima de mil peticiones, `ctrl+l` pide confirmarse otra vez.
Esto se dispara contra sistemas de otros: un Intruder que de fábrica tumba el
entorno de un cliente es una llamada telefónica, no un hallazgo.

Los resultados **no entran al historial**: van a su propia tabla dentro de la
sesión. Diez mil peticiones volverían el historial inservible para lo que es,
y el detector correría sobre las diez mil generando miles de candidatos
basura.

## Interceptación

`x` la enciende y la apaga. **Arranca apagada**: encenderla sola sería
colgarte el navegador sin que lo hubieras pedido, porque una petición
detenida es una pestaña que no carga.

Con ella encendida, cada petición se para **después** de los retoques del
proxy y **antes** de salir, así que lo que ves es exactamente lo que va a
viajar:

```
[ INTERCEPTACION: ON ]   cola: 3

POST /api/login HTTP/1.1
Host: objetivo.com
Content-Type: application/json

{"user":"admin","pass":"x"}

ctrl+f soltar · ctrl+d descartar · ctrl+x apagar · esc cerrar
```

Los atajos llevan `ctrl` aunque sean más largos de teclear: esto es un
editor, y una `f` suelta escribiría una `f`.

Esto es lo que separa luzxfer de un visor de tráfico. El repeater manda
una **segunda** petición; contra un token de un solo uso, un CSRF que se
quema o un pago irrepetible, eso no sirve. Aquí el servidor nunca ve la
original.

**Editar el `Host` no cambia a dónde va la petición.** Es deliberado: así
se prueba inyección por Host header. **Descartar corta la conexión sin
contestar**, que es lo que descartar significa — inventar una respuesta
falsearía lo que el cliente cree que pasó.

Dos salvaguardas, porque una petición detenida es tráfico tuyo retenido:

- Si nadie contesta en 120 segundos, **la petición sale sola**. Dejarte el
  navegador colgado para siempre es peor que dejar pasar algo.
- Al apagar la interceptación o cerrar la herramienta, todo lo detenido
  sale. Nunca queda nada esperando una decisión que ya no va a llegar.

Una línea de petición HTTP son tres partes separadas por espacios, así que
un payload con espacios se corta al reenviar. Se avisa antes de mandarlo y
se puede insistir: la última palabra es tuya, puede que estés probando
justo eso.

## Mapa del sitio

`e` abre el árbol. El historial responde «qué pasó y en qué orden»; el
mapa responde «qué forma tiene el objetivo». Mirando tres mil filas no se
ve que existe un `/admin/` con tres rutas dentro, y eso es lo que uno vino
a buscar.

```
objetivo.com  ×9
  /  200
  admin  no pedido
    panel  302
  api  no pedido  ×4
    v1  no pedido  ×3
      basket  200
      users  200
        7  403
  login  200  401  ×2
```

**`no pedido` es la pista más barata que da el mapa:** `/admin` existe en
el árbol solo porque alguien pidió `/admin/panel`. Nadie ha tocado
`/admin` todavía, y a lo mejor contesta algo.

El contador dice cosas distintas según la fila, y por eso se elige uno
solo: en una ruta visitada, cuántas veces se pidió **esa** ruta; en un
tramo no pedido, cuánto hay debajo. `login ×2` significa que se pidió dos
veces, no que tenga dos hijos.

`enter` sobre una rama lleva al flujo que la produjo, en el historial. Ver
la forma no sirve de nada si volver al detalle cuesta.

El mapa se arma del tráfico que ya se capturó, sin pedirle nada al
servidor: esto ordena, no rastrea. Y respeta el alcance si lo tienes
filtrando.

## Alcance

`a` abre el alcance. Se edita como texto, una regla por línea, porque un
alcance se copia del correo donde el cliente lo definió, se pega, se
retoca y a veces acaba en el informe: como texto eso funciona, y como
formulario no.

```
+objetivo.com          incluir ese host, cualquier puerto
+*.objetivo.com        y sus subdominios, con la raíz dentro
+objetivo.com:8080     solo ese puerto
+objetivo.com/api/     solo bajo esa ruta
-admin.objetivo.com    excluir; excluir siempre gana
```

Si todavía no hay alcance, se propone el host del flujo que estés mirando
—el «Add to scope» de Burp—, sin el puerto: una aplicación suele repartirse
entre el 80 y el 443, y un alcance atado a un puerto deja la mitad fuera
sin avisar.

**El alcance filtra la vista y lo que la herramienta origina, nunca la
captura.** Descartar tráfico al capturarlo lo pierde para siempre, y en un
pentest el tráfico que tiraste es justo el que no puedes recuperar. El
proxy sigue guardándolo todo; lo que el alcance decide es qué se enseña
(`ctrl+f` dentro de la pantalla), qué analiza el detector, y contra qué
podrá disparar el DAST cuando exista.

Dos reglas, una por cada forma de equivocarse:

- **Excluir siempre gana.** Dejar dentro algo ajeno es, en un contrato, un
  problema legal y no un bug.
- **Sin reglas, todo está dentro.** Dejar fuera algo que sí estaba dentro es
  trabajo perdido. El alcance se estrecha a propósito, nunca por descuido.

El host no distingue mayúsculas y la ruta sí: en un servidor real `/API` y
`/api` pueden ser cosas distintas.

## Cobertura WSTG e informe

`w` abre la matriz. **Esto es la razón de ser del proyecto:** Burp conoce
tus peticiones, no sabe qué pruebas de la metodología le debes todavía al
cliente. Esa contabilidad suele acabar en una hoja de cálculo aparte.

Las 97 pruebas de la WSTG v4.2, con sus identificadores y títulos tomados
del documento oficial. Cada una tiene un estado:

| estado | de dónde sale |
| --- | --- |
| `no probado` | nadie la ha mirado — lo que falta por hacer |
| `con candidatos` | hay evidencia automática, nadie ha dictaminado |
| `pasa` | la pones tú, con espacio |
| `FALLA` | hay un hallazgo **confirmado** con ese ID |
| `no aplica` | la pones tú; sale del denominador |

**La evidencia gana a la opinión.** Si marcas una prueba como que pasa y
luego confirmas un hallazgo con ese ID, la matriz dice `FALLA` y el
espacio no la cambia. Un informe que diga que una prueba pasó teniendo
una vulnerabilidad confirmada debajo no se puede entregar.

**No haber mirado y no aplicar no son lo mismo.** Se cuentan aparte, y lo
que no aplica sale del porcentaje: si una prueba no tiene sentido en este
objetivo no es trabajo pendiente, y meterla en el denominador haría
parecer que falta algo que no falta. Un candidato sin dictaminar tampoco
cuenta como cobertura.

`ctrl+g` escribe el informe en Markdown a
`~/.local/share/luzxfer/informes/`: alcance, resumen por estado, hallazgos
confirmados con sus flujos de evidencia, la matriz entera y los candidatos
sin confirmar en un apéndice que dice en voz alta que **no son hallazgos**.

Un detalle que importa: hay cabeceras de seguridad —CSP,
`X-Content-Type-Options`, `Referrer-Policy`— que **no tienen prueba propia
en la v4.2**, y se reportan sin ID en vez de tomar prestado uno ajeno para
que la matriz parezca más completa.

## Barrido activo (DAST)

`b` lanza un barrido sobre el flujo que tengas seleccionado. **Es lo único
de luzxfer que manda peticiones por su cuenta**, así que lleva correa:

1. **Exige alcance.** Sin alcance configurado no corre, y no corre contra
   nada que el alcance no autorice. Mirar de más es ruido; disparar de más
   puede ser el contrato.
2. **Se dispara a mano**, sobre una petición que elegiste. No rastrea, no
   descubre, no se lanza solo. La primera `b` dice cuántas peticiones
   saldrían; la segunda las manda.
3. **Ritmo prudente:** 2 concurrentes y tope de 5 por segundo, del barrido
   entero y no por hilo.
4. **No confirma nada.** Lo que encuentra entra como candidato, con sus IDs
   WSTG. La raya la cruzas tú con `v`.

Prueba reflejo sin escapar, error de SQL, redirección abierta y traversal
de ruta, sobre los parámetros de la query y de un cuerpo de formulario.

**Lo que aporta frente al detector pasivo** es la diferencia entre ver que
un valor vuelve y saber si vuelve *entero*. El activo manda un marcador
propio: si vuelve escapado, no hay nada que explotar ahí, y decir que sí
lo hay es el falso positivo que hace inservible la salida de un escáner.

JSON todavía no se inyecta. Fingir que sí, troceándolo como si fuera un
formulario, mandaría basura al servidor y daría resultados que no
significan nada.

## Candidatos, no hallazgos

Mientras navegas, luzxfer señala cosas que vale la pena mirar: entrada
reflejada, cookies sin `HttpOnly` / `Secure` / `SameSite`, cabeceras de
seguridad ausentes, fugas de versión, errores de servidor. Cada una trae los
IDs de la WSTG que le aplican.

**No es un escáner y no confirma nada.** Un reflejo puede estar perfectamente
escapado en el contexto donde cae. Lo que es del servidor se registra una vez
por host y no una por URL: repetir el mismo hallazgo en cada ruta es el ruido
que hace inútil la salida de un escáner.

Confirmas tú, con `v`. Esa es la línea entre un candidato y un hallazgo, y no
la cruza nada que no sea una persona.

## Lo que el proxy reescribe

Dos cabeceras, las dos activas por defecto y las dos por el mismo motivo: sin
ellas llegan cuerpos que no se pueden leer, y **un cuerpo que el detector no
puede leer es un detector que no encuentra nada y no dice por qué.** Cada una
tiene su interruptor, porque las razones para quererlas de vuelta son
independientes.

### Validadores de caché

Un navegador que ya tiene la página manda `If-None-Match` o
`If-Modified-Since`, el servidor contesta `304 Not Modified`, y el cuerpo
llega vacío. Contra un objetivo real eso pasa en cada recarga, así que buena
parte de tu historial acaba siendo 304 sin nada dentro — y el detector marca
cero en todos.

Por eso el proxy quita esas dos cabeceras. Medido contra OWASP Juice Shop:

```
con el validador:     304 Not Modified      0 bytes    0 candidatos
validador quitado:    200 OK             9984 bytes    1 candidato
```

`--conservar-cache` las deja pasar, que es lo que quieres cuando lo que estás
probando es envenenamiento de caché o *cache deception*: ahí esas cabeceras
son el experimento, no un estorbo.

**El proxy no sigue redirecciones, y es deliberado.** Un `30x` se muestra tal
como lo mandó el servidor; seguirlo escondería la respuesta que viniste a
mirar. El navegador ya las sigue por su cuenta.

### Compresión

El detector lee el cuerpo *decodificado*, porque buscar un reflejo en bytes
gzip no encuentra nada. gzip y deflate están en la librería estándar. Brotli
no — y brotli es lo que ponen por defecto nginx, Cloudflare y el middleware
de compresión de Express, así que en un objetivo moderno es el caso común y
no el raro.

Por eso el proxy recorta `br` (y cualquier otra cosa que no sepa deshacer)
del `Accept-Encoding` del cliente antes de reenviar. Lo recorta en vez de
reemplazarlo, conservando el orden y los valores `q=` que mandó el cliente.
Sin esto el detector se queda ciego en silencio: busca en bytes comprimidos,
no encuentra nada, y no reporta nada — un falso negativo que no deja rastro.

`--conservar-encoding` apaga el recorte, para cuando lo que pruebas es cómo
responde el servidor a cada codificación. `pip install '.[br]'` decodifica
brotli de verdad. Y si aun así llega un cuerpo en algo ilegible, el panel de
respuesta lo dice y avisa de que el detector tampoco pudo leerlo, en vez de
mostrarte binario y callarse.

## Temas y color

```bash
luzxfer --tema claro        # oscuro (por defecto) · claro · contraste
```

O de forma permanente en `~/.config/luzxfer/config.ini`:

```ini
[tema]
nombre = claro

[colores]
peligro = #cc0000       # cualquier color suelto, por encima del tema
```

Los nombres de color son **semánticos, no de color**: `peligro` sigue
significando peligro aunque en otro tema no sea el mismo rojo. `rojo`
dejaría de significar nada el día que alguien ponga un tema donde el
peligro sea naranja. Son `texto`, `cuerpo`, `atenuado`, `secundario`,
`tenue`, `separador`, `acento`, `acento_suave`, `bien`, `info`,
`peligro`, `especial`, `claro`, y las superficies `fondo`, `panel`,
`modal`, `elevado`, `superficie`, `borde`.

El tema `contraste` existe para quien lo necesita de verdad, no como
adorno: los grises intermedios se colapsan —seis niveles de gris no
sirven de nada si no se distinguen— y el verde y el rojo se separan todo
lo posible.

Un color mal escrito **avisa y se ignora**; el resto del archivo se
aplica igual. Un dedazo en un archivo de texto no es razón para no poder
arrancar una herramienta de trabajo.

### Atajos

En el mismo archivo, por nombre de acción:

```ini
[teclas]
intruder = ctrl+i
barrido  = ctrl+b
```

Las acciones son las de la pantalla principal: `salir`, `repeater`,
`intruder`, `sesiones`, `alcance`, `mapa`, `interceptar`, `barrido`,
`cobertura`, `foco_filtro`, `marcar`, `nota`, `confirmar`, `vista`,
`cuerpo`, `limpiar`, `arriba`, `abajo`, `cursor_arriba`, `cursor_abajo`,
`quitar_foco`. **El pie de la pantalla se regenera solo**, así que la
ayuda nunca se queda diciendo la tecla de antes.

Si dos acciones piden la misma tecla, se avisa y se dice **cuál se
queda**; la otra conserva la suya en vez de quedarse muerta. Una acción
que no existe se ignora con la lista de las que sí. Nada de esto impide
arrancar, y `salir` sigue funcionando pase lo que pase: quedarte
encerrado en el programa por un error de tecleo sería el peor resultado
posible.

## Plugins

Un plugin es un `.py` en `~/.local/share/luzxfer/plugins/` que define
`registrar(api)`:

```python
NOMBRE = "mi detector"

def registrar(api):
    api.detector(busca_algo)      # comprobación pasiva
    api.prueba(Prueba(...))       # comprobación activa del barrido

def busca_algo(flujo):
    return [Finding(...)]         # o [] si no hay nada
```

Hay un ejemplo que funciona en [`ejemplos/plugins/jwt_debil.py`](ejemplos/plugins/jwt_debil.py):
busca tokens JWT con `alg=none` o firmados con HMAC. Cópialo a la carpeta
de plugins y se carga.

> **Un plugin es código que corre con tus privilegios dentro de la
> herramienta.** No hay caja de arena y no va a haberla: en Python no sale
> ni barata ni honesta. Instala solo los que hayas leído, igual que harías
> con cualquier cosa que metes en tu `~/.bashrc`. `--sin-plugins` los
> desactiva, y la barra de estado dice siempre cuántos hay cargados.

Lo que sí se hace es contener los accidentes, que es distinto de contener
a un atacante: un plugin que revienta al cargar no impide que carguen los
demás, un detector que revienta no te deja sin los otros detectores, y lo
que un plugin devuelve se valida. **Un ID de la WSTG que no existe se
descarta**: la matriz alimenta un informe que va a un cliente, y el
cliente va a buscar ese ID.

Los plugins **suman** a las comprobaciones de serie, nunca las
reemplazan: instalar uno no puede dejarte con menos de lo que tenías.

## Motores

El núcleo nunca habla con un proxy directamente. Habla con una interfaz de
motor, así que cambiar de motor es cambiar una clase.

| motor | TLS | HTTP/2 | WebSockets | necesita |
| --- | --- | --- | --- | --- |
| `integrado` (por defecto) | no | no | no | nada, solo stdlib |
| `mitm` | sí | sí | sí | `pip install 'luzxfer[mitm]'` |

```bash
luzxfer --motor mitm        # HTTPS, HTTP/2 y WebSockets
```

El motor integrado contesta `CONNECT` con un 501 que explica el motivo, en
vez de fallar en silencio. Interceptar TLS necesita una CA propia y generar
certificados por host, que es justo la dependencia pesada que el motor
integrado evita — y por eso **el integrado sigue siendo el de por defecto**:
la razón de ser de esto frente a Burp es correr donde Burp no corre.

El extra `[mitm]` trae brotli de regalo, así que con él instalado los
cuerpos en brotli se leen de verdad y el proxy deja de recortar `br` del
`Accept-Encoding`: lo que se recorta es lo que no se puede leer, no una
lista fija.

La interceptación en vuelo (`x`) funciona con los dos motores. Con
mitmproxy va por otro camino: su hook de petición corre en su propio
bucle y bloquearlo pararía **todos** los flujos a la vez, así que la
petición se marca con `flow.intercept()`, la espera ocurre en un hilo
aparte y se reanuda desde el bucle. Puedes tener varias detenidas a la
vez sin que el proxy se atasque.

## Seguridad

Esta herramienta reenvía peticiones arbitrarias. **Mantenla en loopback.**
Atarla a una interfaz enrutable es regalarle un proxy abierto a cualquiera de
tu red. Si necesitas llegar desde otra máquina, haz un túnel por SSH.

## Roadmap

- [x] Núcleo, almacén SQLite, interfaz de motor
- [x] Motor HTTP integrado (directo e inverso)
- [x] Historial con filtros, paneles de detalle, candidatos
- [x] Repeater
- [x] Sesiones con nombre, persistentes por defecto, con selector
- [x] Notas, hallazgos confirmados, petición y respuesta lado a lado
- [x] Intruder, cuatro modos, con grep-match sobre los resultados
- [x] Alcance: reglas de inclusión y exclusión, filtro del historial
- [x] Árbol de sitemap
- [ ] Interceptar y editar en vuelo — la brecha real contra Burp hoy
- [x] DAST con correa: exige alcance, disparo manual, ritmo limitado
- [x] Matriz de cobertura WSTG y generación de informes
- [x] Adaptador de motor mitmproxy
- [x] API de plugins
- [x] Personalización: temas, colores y atajos configurables

`docs/direccion.md` tiene el razonamiento detrás de ese orden, y por qué la
IA está aplazada en vez de planificada.

## Contribuir

Issues y pull requests bienvenidos. La regla de diseño que conviene conocer
antes de empezar: **ninguna interfaz habla con un motor directamente, y nada
en `core/` importa de `tui/`.** Esa separación es lo que mantiene posible un
segundo front end, o una ejecución sin interfaz.

## Licencia

Apache-2.0. Ver [LICENSE](LICENSE).
