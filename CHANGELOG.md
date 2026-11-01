# Historial de cambios

Formato según [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/).
Versionado semántico, con una salvedad: en 0.x un cambio de comportamiento
por defecto sube la versión menor, porque es lo que de verdad cambia la
experiencia de quien ya usaba la herramienta.

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

## [No publicado]

Nada todavía.

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
