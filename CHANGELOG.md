# Historial de cambios

Formato según [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/).
Versionado semántico, con una salvedad: en 0.x un cambio de comportamiento
por defecto sube la versión menor, porque es lo que de verdad cambia la
experiencia de quien ya usaba la herramienta.

## [No publicado]

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

[0.3.0]: https://github.com/xXJuanDavidXx/Luzxfer/releases/tag/v0.3.0
[0.2.0]: https://github.com/xXJuanDavidXx/Luzxfer/releases/tag/v0.2.0
[0.1.0]: https://github.com/xXJuanDavidXx/Luzxfer/releases/tag/v0.1.0
