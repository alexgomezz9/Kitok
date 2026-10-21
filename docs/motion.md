# Documental enriquecido

Kitok conserva Native y FFmpeg. El repertorio usa filtros nativos, libass para
texto y vectores, y Pillow para fondos. No instala otro renderer ni llama a LLMs
por escena o fotograma. [Investigación y licencias](motion-research.md) explica
por qué Remotion, Motion Canvas, MotionCraft, MLT y frei0r se aplazan.

## Repertorio reutilizable

20 candidatos en `kitok.editing.motion_components.CATALOG`, agrupados por familia:

| Familia | Composiciones/tratamientos |
| --- | --- |
| Tipografía | Pregunta, frase en tres tiempos, palabra en contexto, capítulo |
| Contexto | Identidad, fecha, lugar, fecha mecanografiada con recuperación de foco |
| Datos | Cantidad explícita, comparación con dos valores, flujo con tres pasos |
| Documentos | Cita atribuida, fragmento textual resaltado |
| Stock | Congelación, acercamiento, reencuadre, desenfoque de entrada, color archivo |
| Transiciones | Disolución y barrido breves |

`MotionDesign` valida `effect`, `text`, `label`, `detail`, `emphasis`, `items`,
`values`, `symbols`, `display_text`, `preset`, `delay`, `hold` y reloj `elapsed`/`emphasis_delay`. `investigation`, `archive` y `signal` cambian
paleta y jerarquía. Los datos son aportados: no hay nombres ni cantidades históricas
por defecto. `display_text` permite un titular editorial breve explícito y conserva
`text` como fuente. No se recortan preguntas con regex: una cláusula puede ser
esencial. Sólo cantidades enteras sencillas en dólares/euros escritas con palabras
pueden mostrarse en dígitos, conservando calificador y escala; pounds, rangos y
fracciones quedan literales. Las comparaciones necesitan valores finitos no negativos y etiquetas;
el editor debe comprobar unidad, fuente y significado. Los diagramas/citas no se
convierten en evidencia documental por su apariencia.

La revisión visual añade títulos grandes con máscaras y aparición escalonada,
subrayados progresivos y diagramas de tres nodos con símbolos vectoriales
(`key`, `device`, `shield`, `database`, `lock`, `person`). Los símbolos son
decisiones explícitas del plan, no interpretación automática de cualquier guion.
El énfasis sobre stock usa un degradado y evita repetir la frase entera como
subtítulo. Si se convierte en placa completa, centra el concepto como título.
El reloj de crecimiento es lineal para conservar el mismo estado entre cortes.

Una escena del plan usa `graphic="motion"` y `motion_design` para una placa o
`asset` más `motion_design` para componer sobre stock. El render valida texto medido,
áreas seguras y duración; si no cabe, exige acortarlo. Escapa código ASS en texto.
Las disoluciones y barridos mezclan la fuente entrante con fotogramas de
continuación de la saliente, durante un máximo de 0,28 s. No se congela ni se
repite su cola. Si no hay margen de stock suficiente, el recibo registra un corte
seguro. La narración y el total de fotogramas se conservan.

`date_typewriter_focus` escribe caracteres sobre una imagen desenfocada; retira
la fecha y recupera el foco al final. `document` con `highlight_box=[x0,y0,x1,y1]`
resalta una zona normalizada de una imagen auténtica aportada, antes de aplicar
la cámara. No genera un supuesto documento histórico. Identidad admite nombre
más grande, detalle opcional y degradado discreto en lugar de un panel opaco.

`camera` ofrece `slow_push_in`, `slow_pull_out`, `pan_left`, `pan_right`, `pan_up`,
`pan_down`, `diagonal_drift`, `subtle_rotation`, `zoom_and_pan`, `focus_push` y
`static`. Los mismos filtros sirven para foto y vídeo. Parámetros en
[montaje](editing.md). `parallax` se rechaza: no se inventan capas de una imagen
plana. Transiciones nuevas: `slide`, `fade_black` y `focus`; `match_cut` conserva
un corte decidido editorialmente. Fundidos visuales configurables sin tocar voz
ni añadir segundos.

## Qué decide automáticamente

MotionDirector conserva stock cuando no encuentra una intención soportada. Detecta
preguntas, cantidades literales numéricas o escritas, porcentajes, fechas,
presentaciones explícitas mediante named/called/llamado y un vocabulario acotado de
conceptos técnicos en contexto. No investiga ni entiende cualquier guion. No infiere
identidades a partir de una capitalización. Diagramas, citas documentales, capítulos,
lugares y comparaciones complejas requieren decisiones explícitas en un plan.

Busca las frases en timestamps Fish sólo si la alineación coincide con el transcript
expandido completo (incluidos guiones divididos y tokens de duración cero). Si no,
conserva tiempos estimados declarados. Cada decisión registra razón y método.
Preguntas y cantidades tienen prioridad sobre contexto opcional. Máximo 38% de tiempo con énfasis, separación mínima 3 s y memoria de las dos familias
recientes en 45 s. Una pregunta ocupa una placa continua; no reinicia animación por
cada corte de stock. Los efectos sobre stock conservan un reloj global al cruzar cortes, incluidos
entrada/salida y énfasis anclado a Fish; un fragmento demasiado corto puede
convertirse en placa continua sin extender ni agotar el stock. Una falta de cobertura bloquea el render.

El modo básico mantiene su recorrido anterior. El puente `render_motion_longform`
produce un plan y reutiliza la ejecución por escenas. No altera Buffer, shorts,
permisos YouTube ni cola. Three.js y póker siguen opcionales históricos, fuera de la
selección automática de este modo.

## Demostraciones locales y caché

Las pruebas viven bajo `outputs/motion-gallery/ID/`: `preview.mp4`, `baseline.mp4`
cuando corresponde, `contact.jpg`, `qa.json`, `CREDITS.md` y plan. Medios privados,
no versionados. El estudio sirve sólo nombres permitidos por ID; rechaza traversal
y symlinks. Consultar la galería no genera ni contacta proveedores. El vídeo se
carga al pulsar «Reproducir muestra» o «Reproducir referencia básica»; sólo hay
un reproductor activo. El contacto se ofrece como imagen estática en un desplegable,
nunca como poster del vídeo. Un error de reproducción muestra la descarga del
archivo afectado y no se presenta como prueba de corrupción del MP4.

Para reconstruir efectos con stock existente y fuente/licencia revisadas:

```bash
.venv/bin/python scripts/motion_gallery.py effects --stock cache/pexels/videos/ID.mp4 --source-url https://www.pexels.com/video/ID/ --credit "Autor y procedencia comprobados" --revision r2
```

`--revision` crea IDs nuevos y conserva las pruebas anteriores; sin revisión,
los archivos ya existentes se omiten.

Para un fragmento preparado localmente:

```bash
.venv/bin/python scripts/motion_gallery.py sample local/motion-phase/MI_MUESTRA.json
```

La configuración de muestra identifica guion/audio/alineación/timeline/referencia
existentes y un intervalo 3–40 s. No puede lanzar el documental completo. Reutiliza
Fish y stock, mezcla música cacheada y prepara A/B con audio idéntico para comparar
imagen. La referencia original permanece intacta. No se solicitan proveedores.

Caché por escena, datos, hash de recursos, ASS, código del compositor y encoder.
El ensamblado de mezclas aprobadas copia vídeo y audio AAC sin normalizar de nuevo.
Si el máster es WAV/PCM u otro códec, codifica el audio una vez a AAC para la
entrega MP4 y conserva el original; el recibo identifica esta conversión.
Las salidas nuevas son exclusivas; conserva originales y usa ID/revisión nueva.
El informe mide decodificación, geometría, duración, negros, LUFS/pico y audio A/B;
la hoja de contacto muestrea imágenes. No acredita audición subjetiva ni aprobación.

## Galería del editor final (21/10/2026)

La colección nueva se prepara con `collection="editor-final-20261021"`. Su
`active.json` selecciona únicamente esos ejemplos; los vídeos y metadatos
anteriores permanecen en disco. La interfaz distingue efectos nuevos/mejorados
de los existentes, con ejemplos renderizados de nuevo por el motor actual.
La lista concreta y su QA se actualizarán al terminar las demostraciones.
La historia de las muestras anteriores y su reparación de códec está enlazada
mediante [el índice de archivo](archive/README.md).
