# Historial de cambios

Formato según [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/).
Versionado semántico, con una salvedad: en 0.x un cambio de comportamiento
por defecto sube la versión menor, porque es lo que de verdad cambia la
experiencia de quien ya usaba la herramienta.

## [0.8.0] — 2026-11-01

Ergonomía de Repeater e Intruder, a partir del feedback del usuario.

### Añadido
- **`r` abre el repeater y `R` le manda el flujo seleccionado.** Antes `r`
  abría el banco metiendo dentro la petición marcada, que impedía mirarlo
  sin ensuciarlo. Abrir y enviar pasan a ser dos gestos. El Intruder no
  gana tecla gemela: ataca una sola petición y no tiene banco que abrir en
  vacío, así que `i` sigue abriendo sobre la marcada.
- **Formatear el cuerpo JSON en el repeater** con `ctrl+f` o un botón. Solo
  toca el cuerpo, nunca las cabeceras, y solo si es JSON válido; si no, lo
  dice y no toca nada. El `Content-Length` lo recalcula el envío, así que
  formatear no descuadra la petición.
- **El Intruder muestra la petición de cada resultado** al pulsar `enter`
  sobre su fila, reconstruida con la misma función que usó el ataque: es lo
  que viajó, no una aproximación. La respuesta no se guarda por fila a
  propósito (memoria acotada); para el cuerpo entero, se manda al repeater.
- **Cargar payloads desde la interfaz** (`ctrl+y` o botón «cargar»): un
  diccionario desde un archivo o un rango numérico de A a B, con paso y
  relleno de ceros. Lo cargado se añade a lo que ya haya. Los errores de
  ruta o de rango se avisan sin cerrar nada.

### Corregido
- **En el repeater «a veces no se veía la respuesta completa, se cortaba
  la parte de abajo»** (reportado por el usuario). No se cortaba: era
  inalcanzable. El foco arranca en el editor, `pagedown` y `end` van al
  editor, y al panel de respuesta solo se llega con `tab`, que no estaba
  documentado en ningún sitio.
  - Encima, los selectores de la hoja de estilos (`#rep-editor`,
    `#rep-scroll`, `#rep-salida`) apuntaban a ids que dejaron de existir
    cuando el repeater pasó a pestañas: los widgets reales se llaman
    `ed-1`, `scroll-1`, `out-1`. Las reglas no afectaban a nada, así que
    **ningún panel mostraba el foco** y no había manera de notar que se
    había movido ni de sospechar que la respuesta se podía desplazar.
  - Ahora los widgets llevan clases, las reglas enganchan, el panel con
    el foco se ve distinto y la pista del título empieza por
    `tab editor/respuesta`.
- **La barra de botones del repeater se dibujaba fuera del recuadro** (una
  fila por debajo del borde): los atajos funcionaban, pero los botones no
  se podían pulsar con el ratón. Faltaba acotar el alto de las pestañas.
- **La fila del rango del Intruder desbordaba a lo ancho** y empujaba su
  botón fuera de la pantalla. Los campos se estrechan; hay tests que
  comprueban que los botones de ambas pantallas caen dentro de su caja.

## [0.7.0] — 2026-11-01

### Corregido
- **El pie de la pantalla recortaba trece de veinte atajos sin avisar.**
  Textual solo pinta una fila y descarta en silencio lo que no cabe: a
  ochenta columnas —el ancho de cualquier terminal, y el único que hay en
  Termux— se veían siete. Interceptar, el barrido, la cobertura, el
  conversor, comparar, marcar, la nota y confirmar no aparecían nunca.
  Como no hay flecha ni puntos suspensivos, no había forma de notar que
  faltaban: las funciones que más costaron eran justo las invisibles.
  - El pie se queda con seis —`?`, `r`, `x`, `/`, `w`, `q`— y cabe entero
    a ochenta columnas. Hay un test que lo comprueba a 80, 100 y 140.
  - Apretar más teclas en el pie no era la solución: a ningún ancho caben
    las veinticuatro.
- El roadmap del README marcaba *Interceptar y editar en vuelo* como
  pendiente, con la función implementada y documentada doce secciones más
  arriba en el mismo archivo. Quien bajara al roadmap concluía que faltaba
  lo que más trabajo había costado.
- `-H/--host` no estaba documentado. Es la única bandera que saca el proxy
  de loopback, y la sección de seguridad advertía sobre ello sin nombrarla,
  así que no se podía saber qué no había que tocar.

- **Los dos motores descartaban en silencio los flujos que no lograban
  entregar al núcleo.** El `except Exception: pass` protegía lo correcto
  —que un consumidor roto no tumbe el proxy, porque entonces el navegador
  del analista deja de cargar a mitad de una prueba— pero pagaba el precio
  equivocado: con el almacén bloqueado o el disco lleno, el tráfico
  desaparecía, el historial se quedaba vacío y la conclusión natural era
  que el objetivo no habla. Un falso negativo fabricado por la herramienta,
  que es la peor clase porque no deja rastro.
  - Ahora se cuentan y se guarda el motivo del último. La barra de estado
    muestra `N PERDIDOS` en rojo mientras haya alguno, y la primera vez
    salta un aviso con el error exacto.
  - El proxy sigue sin caerse, que era lo que el código viejo hacía bien.
  - La cuenta usa un cerrojo: los dos motores entregan desde hilos
    distintos, y un contador de evidencia perdida que se queda corto bajo
    concurrencia subestima justo lo que hay que no subestimar.

### Añadido
- **Pantalla de ayuda (`?`)**: las veinticuatro teclas agrupadas por para
  qué sirven —moverse, herramientas, el flujo elegido, la sesión—. Se
  construye de los atajos **activos**, no de una lista escrita a mano: una
  ayuda mantenida aparte del código se desincroniza en el primer cambio y
  entonces es peor que no tenerla, porque manda a probar teclas muertas.
  Si remapeaste un atajo en tu `config.ini`, ahí sale el tuyo.
  - Traduce los nombres de Textual a los del teclado: `slash` sale como
    `/`, `escape` como `esc`.
  - Un atajo que nadie clasificó aparece igual, al final, bajo «otros»:
    perderlo ahí sería repetir el fallo del pie, solo que más escondido.
    Hay un test que falla si alguien añade una tecla y no la coloca.
- `ayuda` es una acción configurable más, como el resto.
- `esc` (devolver el foco al historial) está documentado por primera vez.
- **Exportar (`u`)**: el flujo como comando `curl`, como petición cruda o
  como respuesta cruda, recorriéndolas con `tab`, y `ctrl+y` al
  portapapeles. Era una brecha real contra Burp —«Copy as curl command» es
  de lo que más se usa— y además es lo que permite entregarle a un cliente
  algo que puede ejecutar él mismo: un hallazgo que solo existe dentro de
  tu pantalla cuesta de defender.
  - El `curl` reproduce lo que viajó. Todo va entre comillas aunque no haga
    falta, porque editar el comando es para lo que se exporta y un `&` en
    un argumento desnudo lo parte en dos.
  - Las cabeceras salen todas, `Content-Length` incluida, con un aviso de
    que hay que ajustarla si editas el cuerpo. Decidir por el analista que
    una cabecera sobra es como un export deja de ser evidencia.
  - Un cuerpo que no es texto viaja en base64 y se deshace en la tubería.
  - El portapapeles no promete haber funcionado: OSC 52 lo ignoran muchos
    terminales sin decir nada, y por eso el texto está en un editor
    seleccionable.

### Cambiado
- `_emitir` vive una sola vez, en la clase `Engine`. Estaba duplicado en
  los dos motores, que es como una corrección se queda a medias sin que
  nadie lo note. Hay un test que falla si un motor vuelve a traerse el suyo.

### Seguridad
- El exportador usa **`--data-raw` y no `--data-binary`**. Los dos últimos
  interpretan un `@` inicial como «lee este archivo del disco y mándalo»:
  un cuerpo capturado que empezara por `@/etc/passwd` habría convertido el
  comando exportado en una fuga de archivos de la máquina de quien lo
  pegara, hacia el objetivo. Lo encontró el test que ejecuta el comando de
  verdad contra el servidor de eco, mientras el código aún usaba
  `--data-binary`: el eco recibió el `/etc/passwd` de esta máquina. El test
  se queda como garantía, y se ha comprobado que falla si se revierte.

## [0.6.0] — 2026-11-01

### Añadido
- **Comparar dos flujos** (`y`, sobre los marcados con `m`): diferencia
  línea a línea de peticiones o respuestas, con `tab` para alternar.
  Compara los cuerpos descomprimidos, porque dos gzip distintos pueden
  tener el mismo contenido.
- **Conversor** (`d`): base64, url, hex, entidades HTML y JWT. Enseña qué
  podría ser el texto en vez de pedir el formato a ciegas, y se abre con
  el token más prometedor de la petición ya dentro.
  - Solo ofrece una interpretación si el resultado se puede leer y
    cambia algo; si no reconoce nada, lo dice.
  - Al abrir un JWT avisa de que la firma **no** se comprueba.
- **Buscar en todo el tráfico** (`/`): url, cabeceras y cuerpos, de la
  petición y de la respuesta. Descomprime para buscar, porque un `LIKE`
  de SQL no encuentra nada dentro de un gzip y parecería funcionar.
- **Atajos configurables** en `~/.config/luzxfer/config.ini`, sección
  `[teclas]`, por nombre de acción. El pie se regenera solo, así que la
  ayuda no se desincroniza.
  - Un conflicto entre dos acciones avisa y dice cuál se queda; la otra
    conserva su tecla en vez de quedarse muerta.
  - `salir` sigue funcionando pase lo que pase.

## [0.5.0] — 2026-11-01

### Corregido
- **El coste por flujo volvía a crecer con el historial.** `move_cursor`
  al seguir el tráfico costaba el 94 % del tiempo de ingerir un flujo y
  en proporción al tamaño de la tabla: 325/s con 500 flujos, 225/s con
  2500. Los saltos se agrupan por ciclo de refresco: **~2100/s, plano**.
- Un detector de plugin que reventaba se anotaba y **no lo veía nadie**.
- Un `RowHighlighted` rezagado consultaba el `Store` ya cerrado y
  reventaba al salir de la herramienta.

### Añadido
- **Temas y color** (`--tema claro|oscuro|contraste`, o
  `~/.config/luzxfer/config.ini`). Los 166 colores que estaban a pelo
  repartidos por nueve archivos son ahora una paleta con nombres
  semánticos, y la hoja de estilos los recibe como variables.
  - Tema `contraste` pensado para accesibilidad, no como adorno.
  - Un color mal escrito avisa y se ignora; el resto se aplica.
- **Pestañas en el repeater**, y persisten con la sesión: cierras, sigues
  navegando, vuelves y tu petición afinada sigue ahí. `ctrl+w` cierra una.
- **Seguir redirecciones en el repeater** (`ctrl+r`), hasta cinco y
  apagado por defecto. La salida dice por dónde pasó. No sigue a otro
  host: eso dejaría que el objetivo saque la herramienta de su alcance.
- **La interceptación en vuelo funciona también con el motor de
  mitmproxy**, sin bloquear su bucle: varias peticiones pueden estar
  detenidas a la vez sin que el proxy se atasque.
- **Motor de mitmproxy** (`--motor mitm`): HTTPS, HTTP/2 y WebSockets. El
  integrado sigue siendo el de por defecto, porque es el único que corre
  en Termux.
  - El extra `[mitm]` trae brotli, así que con él los cuerpos en brotli se
    decodifican y el proxy deja de recortar `br`.
- **API de plugins**: un `.py` en `~/.local/share/luzxfer/plugins/` que
  define `registrar(api)` puede añadir comprobaciones pasivas y pruebas
  activas del barrido. Con ejemplo funcionando en `ejemplos/plugins/`.
  - Suman a las de serie, nunca las reemplazan.
  - Un plugin roto no impide que carguen los demás ni corta el análisis.
  - Los IDs WSTG inventados se descartan antes de llegar a la matriz.
  - `--sin-plugins` los desactiva; la barra dice cuántos hay cargados.

## [0.4.0] — 2026-11-01

### Añadido
- **Alcance** (`a`): reglas de inclusión y exclusión escritas como texto,
  con comodín de subdominios, puerto y prefijo de ruta opcionales.
  - Filtra la vista del historial (`ctrl+f`) y lo que analiza el detector,
    **nunca la captura**: el tráfico fuera de alcance se guarda igual.
  - Excluir siempre gana; sin reglas, todo está dentro.
  - Propone el host del flujo que estés mirando cuando aún no hay alcance.
  - Una línea mal escrita se señala sin tumbar las demás.
- **Mapa del sitio** (`e`): árbol de hosts y rutas construido del
  tráfico ya capturado, sin pedirle nada al servidor. Marca los tramos
  `no pedido` —existen porque algo más abajo se pidió— que son los que
  vale la pena probar a mano. `enter` lleva al flujo en el historial.
  Respeta el alcance si está filtrando.
- **Interceptación en vuelo** (`x`): parar una petición antes de que salga,
  editarla y soltarla, o descartarla. Es lo que separa la herramienta de un
  visor de tráfico: el repeater manda una *segunda* petición, y contra un
  token de un solo uso eso no sirve.
  - Arranca apagada; una petición detenida es una pestaña que no carga.
  - Si nadie contesta en 120 s la petición sale sola, y al apagar o cerrar
    se suelta todo lo detenido: nunca queda nadie colgado.
  - Editar el `Host` no cambia el destino, para poder probar inyección por
    Host header. Descartar corta la conexión sin contestar.
  - Avisa antes de perder en silencio un payload con espacios en la línea
    de petición.
- **Barrido activo / DAST** (`b`): reflejo sin escapar, error de SQL,
  redirección abierta y traversal, sobre query y cuerpo de formulario.
  - Exige alcance configurado y se niega contra lo que no autorice.
  - Doble pulsación para lanzarlo: la primera dice cuántas peticiones.
  - 2 concurrentes, tope de 5/s del barrido entero.
  - Los hallazgos entran como candidatos sin confirmar.
- **Matriz de cobertura WSTG e informes** (`w`): las 97 pruebas de la v4.2
  con sus identificadores y títulos tomados del documento oficial.
  - `FALLA` y `con candidatos` salen de la evidencia; `pasa` y `no aplica`
    las pone una persona. La evidencia gana a la opinión.
  - Lo que no aplica sale del denominador del porcentaje, y un candidato
    sin dictaminar no cuenta como cobertura.
  - `ctrl+g` genera el informe en Markdown con alcance, resumen,
    hallazgos confirmados con sus flujos de evidencia, la matriz entera y
    los candidatos en un apéndice.

### Corregido
- **El detector reclamaba `WSTG-CONF-07` por cualquier cabecera de
  seguridad ausente**, y CONF-07 es «Test HTTP Strict Transport Security»:
  el informe habría dicho que se probó HSTS porque faltaba un CSP. Ahora
  `X-Frame-Options` va a `WSTG-CLNT-09`, HSTS a `WSTG-CONF-07` y solo
  sobre https, y las que no tienen prueba propia en la v4.2 se reportan
  **sin ID**. El detector gana además la comprobación de HSTS.

## [0.3.0] — 2026-11-01

### Añadido
- **Intruder** (`i`), con los cuatro modos de Burp: sniper, ariete,
  horquilla y racimo. Marcadores `§` compatibles con peticiones copiadas de
  Burp, insertados con `ctrl+m` porque `§` no está en la mayoría de
  teclados. Payloads escritos a mano, por rango numérico o desde archivo
  con `@ruta`; varios conjuntos separados por una línea `---`.
  - Ritmo prudente de fábrica: 4 concurrentes y tope de 10 peticiones por
    segundo. El tope es del ataque entero y no de cada hilo, así que subir
    la concurrencia no lo multiplica.
  - Por encima de 1000 peticiones, `ctrl+l` pide confirmarse otra vez.
  - `ctrl+o` ordena por largo de respuesta, que es lo que delata el acierto
    cuando todas las respuestas son 200.
  - Los resultados van a sus propias tablas en la sesión, **no al
    historial**: diez mil peticiones lo volverían inservible y el detector
    correría sobre las diez mil.
- **Presentación del cuerpo según lo que es** (`p` alterna con el crudo):
  JSON indentado, binarios resumidos con volcado hexadecimal, texto tal
  cual. Nunca se miente sobre lo que llegó: si se reorganizó, se recortó o
  no se pudo leer, queda dicho encima.
- README en español.

### Corregido
- **Los validadores de caché dejaban al detector sin nada que leer.** Un
  navegador con la página en caché manda `If-None-Match`, el servidor
  contesta `304` sin cuerpo, y el detector marcaba cero sin decir por qué.
  Ahora el proxy los quita; `--conservar-cache` los conserva para probar
  envenenamiento de caché.
- **El charset declarado se ignoraba.** Todo se decodificaba como utf-8, así
  que un servidor en `iso-8859-1` mostraba `contrase?a` y **un reflejo con
  acentos no se encontraba nunca**.
- **El Intruder confiaba en el flujo de origen y no en lo que editaste.** Al
  cambiar el `Host:` a un objetivo HTTPS, el ataque salía en claro contra un
  puerto TLS; y el ataque se archivaba contra el host equivocado.
- **Un error del almacén tumbaba la aplicación.** Con otra instancia
  escribiendo en la misma sesión, la excepción subía por el bucle de la
  interfaz. Ahora se avisa y la herramienta sigue sirviendo.
- **Trabajo no acotado al mostrar un cuerpo grande.** Se parseaba el JSON
  entero para enseñar 200.000 caracteres: 51 MB costaban 3 s de interfaz
  congelada y 215 MB de pico. Ahora 0,00 s y 1 MB.
- El aviso de limpiar el historial decía que se conservan los candidatos y
  callaba que también los ataques.

### Añadido (pruebas)
- Cacería de bugs de nueve sospechas concretas: cuatro reales, tres
  descartadas por escrito con su motivo, dos que eran agujeros de cobertura.
- Test del cableado real entre la aplicación y el motor. Hasta ahora todos
  los tests construían el motor a mano, así que probaban que *sabe* filtrar
  una cabecera, no que la aplicación se lo *pida*.

## [0.2.0] — 2026-10-31

### Añadido
- **Sesiones con nombre, persistentes por defecto.** `luzxfer` sin
  argumentos retoma la última; `-s NOMBRE` abre o crea; `--sesiones` lista;
  `s` abre el selector dentro de la interfaz. Los nombres pasan por una
  lista blanca, porque el nombre se convierte en una ruta de archivo.
- Notas por flujo (`n`) y confirmar un candidato como hallazgo (`v`).
- Vista combinada de petición y respuesta (`t`), al estilo Burp, con la
  preferencia guardada.
- Aviso cuando el historial no cabe entero en la tabla.

### Cambiado
- **El historial ya no se pierde al salir.** Es el cambio que justifica la
  versión: la 0.1.0 usaba `:memory:` por defecto. Para la sesión volátil de
  antes queda `-d :memory:`, ahora explícito.

### Corregido
- **Brotli dejaba ciego al detector.** No era que el cuerpo se viera feo:
  `decoded_body()` devolvía los bytes comprimidos y el detector buscaba
  reflejos en basura binaria. El motor recorta ahora el `Accept-Encoding`.
- Los cinco cabos sueltos restantes de la revisión de la 0.1.0.

## [0.1.0] — 2026-10-30

Primera versión: núcleo, almacén SQLite, interfaz de motor, motor HTTP
integrado (directo e inverso), historial con filtros, detector de
candidatos con IDs de la WSTG, y repeater por socket crudo.

Revisión posterior con siete fallos reales corregidos, cada uno con su test
de regresión escrito primero.

[0.6.0]: https://github.com/xXJuanDavidXx/Luzxfer/releases/tag/v0.6.0
[0.5.0]: https://github.com/xXJuanDavidXx/Luzxfer/releases/tag/v0.5.0
[0.4.0]: https://github.com/xXJuanDavidXx/Luzxfer/releases/tag/v0.4.0
[0.3.0]: https://github.com/xXJuanDavidXx/Luzxfer/releases/tag/v0.3.0
[0.2.0]: https://github.com/xXJuanDavidXx/Luzxfer/releases/tag/v0.2.0
[0.1.0]: https://github.com/xXJuanDavidXx/Luzxfer/releases/tag/v0.1.0
