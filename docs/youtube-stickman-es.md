# YouTube stickman en español

`youtube_stickman_es` es un adaptador de producción **dentro de Kitok**. Conserva
shorts y documental; usa el mismo `EditorialPlan` y renderer Native/FFmpeg,
cámaras, transiciones, biblioteca musical y QA. No instala otro editor ni un
LLM en el render. Este flujo se ejecuta por terminal; aún no tiene formulario
específico en el estudio.

## Reparto del trabajo

El operador aporta tema, enfoque, título, guion definitivo y referencias. Codex
inspecciona principalmente **fotogramas interiores**, prepara la guía de estilo,
personajes, dirección visual por escena y genera imágenes con su herramienta
integrada. Las miniaturas de referencia sólo orientan el empaquetado. No se
investigan canales, eligen temas ni reescriben guiones desde este pipeline.

Kitok valida los archivos, calcula cortes, prepara solicitudes, conserva resultados
y monta. **No puede invocar una herramienta de la sesión de Codex desde Python**.
`produce` se detiene con un estado explícito cuando falta dirección, imágenes o
aprobación; no simula una generación exitosa ni cambia a una API de pago.

## Preparar un episodio

```bash
.venv/bin/python -m kitok.youtube_stickman_es init content/longform/mi_episodio
```

Aporta estos archivos, conservando el guion original:

```text
content/longform/mi_episodio/
  guion_final.txt
  titulo.txt
  configuracion.json
  referencias/
  voz.mp3                 # opcional: se reutiliza sin volver a pedir voz
  voz.srt                 # tiempos reales, transcript completo
```

La [plantilla de configuración](../examples/youtube_stickman_es/configuracion.json)
es orientativa, no un estilo aprobado. En `references`, identifica cada archivo
con `path`, `role` (`interior`, `thumbnail`, `character`) y notas. Define
`style_prompt` con técnica, contorno, paleta, fondo y composición observados;
`characters` contiene la ficha estable de cada personaje por ID. Codex completa
estos datos a partir de las referencias; Kitok no deduce el estilo abriendo un PNG.
Se guardan `guia_estilo.md` y `personajes.json`.

```bash
.venv/bin/python -m kitok.youtube_stickman_es prepare content/longform/mi_episodio
```

Con voz existente no hay síntesis. Si falta, configura `voice.reference_id`, modelo
y velocidad; autoriza explícitamente la generación con `prepare --generate-voice`.
Se reutiliza Fish y su caché; resultados inciertos bloquean otro POST automático.
Una voz ya generada se conserva aunque falle la preparación posterior.

No se fabrican tiempos por velocidad de lectura. Si falta SRT, sólo se deriva de
timestamps Fish reales cuyo transcript completo coincide. **Audio importado sin
SRT ni alineación compatible necesita un SRT alineado antes de continuar**; este
adaptador no incluye transcripción ASR/forced alignment local. Un SRT importado se
comprueba contra guion/duración y se fija por hashes, pero su sincronía acústica
sigue necesitando revisión. No se presenta esa comparación textual como ASR.

## Dirección y generación de ilustraciones

La planificación produce aproximadamente un plano cada cinco segundos: por
ejemplo, 600 s con subtítulos suficientemente granulares generan 120 escenas.
Cuando Fish aporta palabras completas y ordenadas, los cortes usan sus tiempos
reales aunque el SRT tenga bloques largos. Se elige una distribución global
factible próxima a cinco segundos, con máximo estricto y cuantización a 30 fps;
el último frame cubre el final de la voz sin recortarlo. Se conservan las palabras
con duración cero y no se eligen cortes que creen escenas vacías. Los segmentos
multipalabra sirven para SRT, pero no se subdividen inventando tiempos. Sin reloj
de palabras sigue disponible el modo SRT: si sus límites reales no permiten
respetar el máximo se solicita una alineación más granular.

## Reutilizar imágenes y un plan anterior

```bash
.venv/bin/python -m kitok.youtube_stickman_es prepare content/longform/mi_episodio --revision alineada --reuse-images
.venv/bin/python -m kitok.youtube_stickman_es produce content/longform/mi_episodio --revision alineada --reuse-images
```

El primer comando no renderiza ni consume proveedores. El segundo usa el motor
de Kitok para montaje, cámaras, transiciones, música y render, conservando la voz.
No hace falta un script para reparar SRT ni renombrar imágenes. Las miniaturas
que falten quedan pendientes y no bloquean el MP4.

`plan_visual.json` contiene `script_source`, `script_sha256` y `scenes`. Cada escena
declara `id`, `source_char_start` y `source_char_end` (fin exclusivo), `narration`,
`image_file`, `visual_description` y `scene_prompt`; opcionalmente `image_sha256`
y `characters`. Los offsets se refieren al texto exacto de `script_source`.
También se admite `planificacion_visual/plan_visual_prevoz.json` con
`visual_description_en`. Se comprueba la cobertura completa del guion, sin huecos
ni duplicados, y se ignoran los tiempos estimados. La imagen sigue asociada al
mismo fragmento; si necesita varios planos para respetar el máximo, se reutiliza
el mismo archivo. Los planes y prompts se preparan antes con Codex.

La revisión se guarda en `revisiones/alineada/`, con copias independientes de
inputs, referencias e imágenes y un manifiesto de hashes. No reemplaza recursos,
SRT, aprobaciones ni recibos de pago originales. Una reanudación rechaza cambios
en los inputs fijados. La alineación queda ligada al plan mediante su hash.
`--reuse-images` registra autorización del operador para montar esos recursos;
no marca imágenes como inspeccionadas ni crea una aprobación de estilo ficticia.
La revisión humana audiovisual y de derechos sigue pendiente. Sin este parámetro
se mantiene el flujo de muestras y aprobación del lote.

Primero aparecen `plan_imagenes.borrador.json`, `.md` y
`direcciones_plantilla.json`. Codex copia la plantilla a `direccion_visual.json`
y completa **cada ID** con `visual_description` concreta, `scene_prompt` detallado
en inglés y los IDs de personajes pertinentes. Puede sobrescribir la cámara.
No hay descripciones genéricas aceptadas automáticamente ni traducción por regex.

Ejecuta `prepare` otra vez: guarda `plan_imagenes.json` y `.md` con tiempos,
frase narrada, archivo, prompt de estilo separado del prompt de escena,
referencias y cámara. Los IDs, imágenes y decisiones mecánicas los genera Kitok;
el operador no necesita escribir ese plan a mano.

```bash
.venv/bin/python -m kitok.youtube_stickman_es request-next content/longform/mi_episodio
```

La respuesta contiene `id`, `attempt_id`, destino y los argumentos reales de
`image_gen.imagegen`: `prompt`, `transparent_background=false` y referencias
locales cuando existen. En esta instalación se expone como
`tools.image_gen__imagegen(...)` dentro de la sesión de Codex; **no existe un
comando shell equivalente**. El agente comprueba la herramienta disponible,
inspecciona referencias y llama una vez por ilustración. No se usa una API propia,
clave OpenAI ni proveedor de imágenes adicional. Guarda/importa el archivo real
que entregue la herramienta, sin asumir su nombre o inventar una ruta de salida:

```bash
.venv/bin/python -m kitok.youtube_stickman_es import-image content/longform/mi_episodio --image-id ID --attempt-id TOKEN --source RUTA_REAL.png --source-kind builtin_imagegen --reviewed
```

`--reviewed` registra una inspección visual realizada, no una comprobación de IA
automática. También puede importarse primero y usarse `review-image --image-id ID
--reviewer NOMBRE` después de verla. Imágenes aportadas manualmente usan
`--source-kind provided`. Se validan decode, dimensiones, 16:9, tamaño y duplicados;
el formato se normaliza a PNG sin inventar contenido.

Antes del lote sólo son elegibles las escenas primera, central y final (o las
disponibles si hay menos de tres). Preséntalas al operador. **Tras su aprobación**:

```bash
.venv/bin/python -m kitok.youtube_stickman_es approve-style content/longform/mi_episodio --reviewer NOMBRE
```

La aprobación fija plan, voz/SRT, personajes, referencias, conceptos y hashes de
la muestra. Importar el resto no la invalida. `request-next` recorre lo pendiente,
incluidas tres ilustraciones de miniatura, reutilizando las imágenes válidas.
El agente puede procesar grupos cortos; la aprobación no autoriza cambiar a otro
servicio de pago. No se promete un lote de 120 dentro de una sola cuota.

## Interrupciones, errores y correcciones

```bash
.venv/bin/python -m kitok.youtube_stickman_es status content/longform/mi_episodio
.venv/bin/python -m kitok.youtube_stickman_es resume content/longform/mi_episodio
```

Una solicitud reservada permanece `claimed` o `unknown`; nunca se reenvía sola.
`status` conserva el token para registrar un resultado recuperado. Si se alcanza
cuota o el resultado es ambiguo, registra `unknown --image-id ID --attempt-id TOKEN
--reason MOTIVO`. Revisa el resultado antes de autorizar `retry --image-id ID
--reason MOTIVO` (máximo tres reservas por imagen). Los intentos previos permanecen
en el historial; una reserva no demuestra que se haya llamado al generador.

`reject --image-id ID --reason MOTIVO` conserva la imagen rechazada y permite
reintentar sólo ese recurso. Los originales importados no se borran. Las muestras
de estilo ya aprobadas son inmutables: para cambiar ese estilo usa otra revisión
de episodio; un archivo perdido puede restaurarse desde su original idéntico.
Las composiciones de miniatura anteriores se archivan al corregir su fondo.
Se conservan costes reportados cuando existen; desconocido no se convierte en cero
ni se atribuye a todas las solicitudes el precio de la última imagen.

## Montar y volver a renderizar

```bash
.venv/bin/python -m kitok.youtube_stickman_es produce content/longform/mi_episodio
.venv/bin/python -m kitok.youtube_stickman_es render content/longform/mi_episodio --revision v2
```

`produce` monta cuando la muestra está aprobada y todas las ilustraciones están
completas/revisadas. `resume` conserva un MP4 terminado válido o retoma los planos
cacheados. `render --revision v2` guarda `video_final__v2.mp4` sin regenerar voz o
imágenes ni sobrescribir `video_final.mp4`. Guion/configuración/dirección ya fijados
son inmutables: cambiar esos inputs exige otro episodio/revisión, conservando el
anterior. No borres recibos para forzar reintentos.

Salida 1920×1080/30, imágenes a pantalla completa, cámaras discretas variadas,
disoluciones de 0,4 s acotadas al plano, cortes y fades visuales .6/.8 s dentro
del metraje. La voz no recibe fade-out. `music.mode` admite `auto`, `manual` y
`off`; usa la [biblioteca licenciada](audio.md), cachés y mezcla existentes con
ducking, SFX puntuales y normalización medida. Aquí no se descarga música.
Los SFX requieren mezcla musical habilitada. Se comprueba -16 LUFS ±1 y pico
verdadero máximo -1,5 dBTP en el MP4 real. Los subtítulos se conservan en SRT como
reloj y entrega; no se queman permanentemente sobre las ilustraciones.

## Entregables y control

Además de entradas, planes, `imagenes/` y MP4, quedan `montaje.json`, `qa.json`,
contacto, recibos de caché y `informe_produccion.json`. Se preparan tres conceptos
distintos de miniatura, tres fondos solicitados al generador y PNG 1280×720,
`descripcion_youtube.txt`, `capitulos.txt`, `metadata_youtube.json` y créditos.
`thumbnail_text` permite cero a tres palabras por variante A/B/C mediante fuente
real. `description` acepta copy editorial preparado; si se omite, se usa un
extracto declarado del guion, sin inventar un resumen, fuentes o patrocinios.

El informe `qa.json` se publica atómicamente una vez completados todos los
controles, con `technical_status: passed` o `rejected`. Durante las mediciones
pueden aparecer el MP4 y contactos antes del informe definitivo; espera a que
termine el comando. Si se interrumpe un control, no se publica un dictamen nuevo.

Los capítulos utilizan escenas reales y títulos explícitos o frases del guion;
el primero empieza en 00:00. Se aplica la [regla oficial de YouTube](https://support.google.com/youtube/answer/9884579?hl=en):
al menos tres y diez segundos por capítulo. Una prueba de quince segundos no
fabrica capítulos; un largo sin límites adecuados pide selección editorial.

QA valida cada imagen, cobertura, todos los PTS/frames/pixel format, decode
completo, duración, negros, sonoridad y hashes. Detecta intervalos de al menos
1,5 s por debajo de -45 dB en la narración original y en la mezcla final, para
que la música no oculte huecos de voz. Los marca para escuchar: una pausa puede
ser intencional y no rechaza automáticamente el vídeo. Los cortes más breves
también requieren escucha. Las deformaciones, significado,
letras accidentales, consistencia estilística, sincronía acústica, escucha y
legibilidad móvil se marcan para revisión visual/humana. No se declaran aprobadas
por pasar FFprobe. Faltantes de miniaturas se indican aunque el vídeo esté montado.
No hay publicación automática ni conexión nueva a YouTube.

## Prueba de configuración

```bash
.venv/bin/python scripts/stickman_smoke.py outputs/evaluation/mi_prueba_nueva --music
```

Crea sólo tres dibujos de diagnóstico y señal de audio **sin narración**, con una
copia aislada de música ya cacheada. Usa Kitok para render, reanudación y segundo
render con los mismos recursos; no consume Fish/ImageGen ni representa el estilo
final. Si la carpeta existe, pide otra; no borra la prueba previa. La aceptación
del formato necesita referencias interiores y una muestra real de producción.

La [documentación de generación integrada](https://learn.chatgpt.com/docs/image-generation)
confirma que consume uso de Codex. Esta integración no puede consultar tu cuota
restante ni garantizar que 120 dibujos sean baratos por ser sencillos. La forma
de medir viabilidad será la muestra aprobada y los datos que reporte la herramienta,
sin contratar una API alternativa automáticamente.

Para un artefacto audible de voz entre palabras, conserva el episodio original
y usa [la reparación local con cortes revisados](audio.md#quitar-ruidos-de-sintesis-confirmados).
La copia conserva evidencia de los tiempos derivados; no se presenta como
alineación Fish original ni se solicita otra voz.
