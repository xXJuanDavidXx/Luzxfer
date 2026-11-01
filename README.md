# luzxfer

Proxy de interceptación y banco de trabajo de pentesting web que vive en tu
terminal.

Construido alrededor de la [OWASP WSTG](https://owasp.org/www-project-web-security-testing-guide/)
y no alrededor de las peticiones: lleva la cuenta de qué pruebas has hecho
contra qué endpoints, ata los hallazgos al tráfico que los demuestra, y
conserva ese estado entre sesiones.

> **Estado: alfa.** Funcionan el núcleo, las sesiones con nombre, el
> historial, el repeater y el Intruder. Faltan el sitemap, el alcance, la
> interceptación en vuelo y la matriz de cobertura WSTG. Ver el roadmap,
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
| `f` | enfocar el filtro |
| `r` | abrir el repeater sobre el flujo seleccionado |
| `i` | abrir el Intruder sobre el flujo seleccionado |
| `t` | petición y respuesta lado a lado, y volver |
| `p` | alternar entre el cuerpo reorganizado y el crudo |
| `n` | escribir una nota en el flujo |
| `m` | marcar un flujo |
| `v` | confirmar el candidato seleccionado como hallazgo |
| `a` | alcance: qué entra en el contrato |
| `s` | sesiones |
| `c` | limpiar el historial (los candidatos se conservan) |
| `g` / `G` | primer / último flujo |
| `q` | salir |

`t` y el botón que está junto al filtro hacen lo mismo: petición y respuesta
en dos columnas en vez de dos pestañas, como Burp deja distribuirlas. La
pestaña de candidatos sigue alcanzable en los dos modos, y la elección se
recuerda con la sesión.

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

`ctrl+s` envía, `esc` cierra. El `Content-Length` se recalcula al enviar,
porque editar una petición cruda a mano y olvidarlo es el error más común que
existe.

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

## Motores

El núcleo nunca habla con un proxy directamente. Habla con una interfaz de
motor, así que cambiar de motor es cambiar una clase.

| motor | TLS | HTTP/2 | WebSockets | necesita |
| --- | --- | --- | --- | --- |
| `integrado` (por defecto) | no | no | no | nada, solo stdlib |
| `mitmproxy` | sí | sí | sí | `pip install 'luzxfer[mitm]'` |

El motor integrado contesta `CONNECT` con un 501 que explica el motivo, en
vez de fallar en silencio. Interceptar TLS necesita una CA propia y generar
certificados por host, que es justo la dependencia pesada que el motor
integrado evita.

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
- [ ] Árbol de sitemap
- [ ] Interceptar y editar en vuelo — la brecha real contra Burp hoy
- [ ] DAST con correa: exige alcance, disparo manual, ritmo limitado
- [ ] Matriz de cobertura WSTG y generación de informes
- [ ] Adaptador de motor mitmproxy
- [ ] API de plugins
- [ ] Personalización: temas, colores, atajos configurables

`docs/direccion.md` tiene el razonamiento detrás de ese orden, y por qué la
IA está aplazada en vez de planificada.

## Contribuir

Issues y pull requests bienvenidos. La regla de diseño que conviene conocer
antes de empezar: **ninguna interfaz habla con un motor directamente, y nada
en `core/` importa de `tui/`.** Esa separación es lo que mantiene posible un
segundo front end, o una ejecución sin interfaz.

## Licencia

Apache-2.0. Ver [LICENSE](LICENSE).
