# Auditoría del flujo de Trazo Maldito — 27/10/2026

Revisión del episodio Jason y del código actual. Los tiempos proceden del log de
su producción real, no de estimaciones ni de la suite. Reglas y comandos vigentes:
[guía](../GUIA.md), [flujo editorial](youtube-editorial.md), [voz](fish-voice.md),
[audio](audio.md). No se volvió a sintetizar voz ni renderizar el episodio completo
para esta auditoría. No se publica contenido.

## Orden real y reparto de trabajo

| Etapa | Agente/editor | Kitok determinista |
| --- | --- | --- |
| Idea e investigación | Decide personaje, continuidad, fuentes y promesa; no une versiones incompatibles. | Lector compacto recupera perfil y estado; no investiga por sí solo. |
| Guion | Escribe relato causal e inmersivo; títulos/canon quedan en notas. | Conserva texto y hashes. No escribe ni corrige hechos. |
| Enfoque visual nuevo | Propone tres enfoques stickman del mismo momento; operador elige, o agente si está delegado. | Importa anclas y conserva referencias; no inventa aprobación. |
| Voz | Decide interpretación y revisa pronunciación/anomalías. | Fish sólo con opción expresa si falta voz; caché y resultados inciertos conservados. Control ASR local opcional antes del montaje. |
| Storyboard | Decide cortes semánticos, acción, composición, personajes y prompts. | Helper calcula cobertura, IDs, fragmentos y reloj desde palabras reales. |
| Imágenes | Invoca ImageGen integrado y revisa correspondencia de todos los recortes. | Prepara lotes, recorta, valida, registra hashes y conserva relación panel/escena. |
| Montaje | Entrega inputs fijados; revisa muestra y sólo cambia dirección cuando aporta. | Valida, mezcla, anima, transiciona, une, añade ASS y ejecuta QA. Sin LLM por plano ni fotograma. |
| Entrega | Fija miniatura, descripción, capítulos y créditos reales. | Empaquetado compacto de seis archivos con recibos/hashes, sin recodificar. |
| Limpieza | Decide cuándo deja de necesitar reusar cachés para reparaciones. | Comando explícito simula y borra sólo derivados visuales permitidos, con locks. |

Las skills coordinan una sesión del agente; no son un servicio ejecutándose cuando
Codex está cerrado. El CLI stickman y sus herramientas existen; el frontend diario
no ofrece todavía toda esta coordinación editorial como un único formulario.
El perfil orienta al agente: añadir `local_asr` o `horror` al perfil NO cambia por
sí solo un `configuracion.json` antiguo ni activa una reparación retrospectiva.

## Qué hubo que hacer a mano en Jason

Trabajo editorial previsto: investigar, guion, 109 decisiones visuales, generar y
revisar 109 PNG, miniatura y metadatos. Los lotes integrados necesitan herramienta
del agente; Kitok Python no tiene acceso directo a ImageGen. Las imágenes pequeñas
se escalan durante el montaje, sin recuperar detalle perdido.

Intervenciones que pertenecen a ingeniería o control automático:

- El operador detectó habla ajena al guion que los subtítulos y QA técnico no
  advertían. Hubo que localizar un hueco, conservar originales, cortar sólo su
  interior y derivar reloj/subtítulos. La raíz modelo/voz/parámetros no está aislada.
  La anomalía está en la voz seca guardada por Fish, cuyo hash coincide con el
  recibo de la solicitud; el guion solicitado no contiene esas expresiones.
  El control ASR local añadido compara reconocimiento independiente con el texto;
  bloquea diferencias para revisión, no declara automáticamente segura una tijera.
- El mezclador había acortado un MP3 al negociar el reloj de muestras. La reparación
  ya incorporada en el motor conserva duración y margen AAC; no fue edición manual
  de cada plano. Se comprobó con la voz existente.
- Se ajustó la duración con `tempo=0.94` conservando tono y texto, autorizado para
  este episodio. En futuros vídeos se escribe suficiente historia útil para9–12 min;
  no se usa ralentización ni silencio como política de duración.
- El proceso terminó durante el último QA tras haber codificado los subtítulos.
  Se necesitó un script temporal para recuperar ese MP4 y ejecutar los controles
  originales. El exportador ahora guarda identidad y hash tras codificar y permite
  reanudar el QA sin otra pasada de codificación. Trabajos antiguos sin ese recibo
  siguen requiriendo revisión; no se adivinan artefactos válidos.
- La entrega y el estado habían quedado dispersos/obsoletos. Hay un comando de
  entrega compacto e inventario, pero aún debe invocarse expresamente cuando los
  metadatos finales estén fijados. No es un único `produce` que haga todo lo editorial.

El montaje de los115 planos lo ejecutó Kitok. Las reparaciones de código/recuperación
consumieron trabajo del agente que el flujo habitual no debería repetir. No hay
medición que permita atribuir un número de tokens ahorrados a estos cambios.

## Por qué tarda aunque NVIDIA esté activa

RTX 3050 Laptop 4 GB verificada; recibo del render con `h264_nvenc`. NVENC codifica,
pero en esta ruta `scale`, `zoompan`, `xfade` y `libass` son filtros de CPU. La cámara
escala cada imagen a3840×2160 para suavizar movimiento y después entrega1080p.
Los planos y sus comprobaciones se procesan en secuencia.

| Fase observada | Tiempo aproximado |
| --- | --- |
| Preparar/validar entradas |3 s|
| Mezclar audio local |2m34s|
| Animar115 planos, incluidas continuaciones/transiciones |16m50s|
| Unir clips ya renderizados |8 s|
| Validar montaje |2 s|
| QA base |3m54s|
| Empaquetado y comprobaciones antes de subtítulos |1m3 s|
| Quemar subtítulos en segunda pasada |2m41s|
| QA subtitulado |Se interrumpió; no hay duración final comparable|

El recibo marca1021.70 s para planos/unión/validación, sin mezcla ni QA. El final
subtitulado recuperado pasa QA:497.733333 s,14932 frames,1920×1080/30 fps,
−16.03LUFS y−1.75dBTP; audio decodificado idéntico al base. No equivale a ausencia
de habla añadida ni a escucha humana completa.

La unión de8 s ya usa copia de streams; cambiar esa etapa no resolvería el coste
principal. Tampoco hay doble normalización de la mezcla: el motor reconoce audio
final y copia el AAC aprobado. Sí hay una segunda pasada completa de vídeo por ASS.

Una prueba limitada de4 s/120 frames con el mismo NVENC dio1.79 s estático,
2.89 s cámara actual2x y1.62 s cámara candidata1x. No se adoptó el cambio: quitar el
supersampling puede introducir saltos y falta revisión visual. No se extrapola al
episodio. No se encontraron artefactos GTA6/leak en content/outputs para comparar
con el vídeo citado por el operador; atribuirle una velocidad concreta sería inventar.

## Archivos y espacio

Jason tenía1616 archivos en su árbol antes de la entrega compacta. `.editorial-work`
concentra764 archivos/~1.17 GB: clips, continuaciones, láminas preparadas y recibos.
Algunos nombres grandes comparten inode; sumarlos duplicaría el espacio reclamable.
Por ejemplo, la revisión `.stickman` representa548 MB lógicos pero sólo unos15.8 MB
adicionales tras descontar hardlinks ya contados.

`entrega/` muestra seis archivos: vídeo, miniatura, descripción, créditos, informe
y LEEME. El vídeo comparte bytes con el máster; textos y miniatura son copias
independientes. Los archivos técnicos quedan fuera, conservando reanudación y fuentes.

La simulación inicial identificó403 derivados visuales y1,170,948,096 bytes físicos
recuperables (~1.09GiB). No se ha aplicado mientras la investigación de voz pueda
requerir editar el montaje. Se conservan voz original/reparada, imágenes/atlas,
fuentes, licencias, planes, ASS, recibos, muestras útiles y vídeos finales. Tras
limpiar, una reedición necesitará renderizar otra vez los clips eliminados.

## Comprobación real de voz

Se transcribieron completos el original y la versión con corte/tempo mediante
Whisper small CPU/int8, sin proporcionar el guion al reconocedor y sin subir audio.
El original tardó93.03s; el derivado65.52s en esta ejecución. El derivado produce
38diferencias:26inserciones,10sustituciones y2omisiones. Algunas son nombres/cifras;
no contar cada diferencia como un defecto de Fish. Reconoce «montantani…» en
261.82–265.06s y278.62–280.30s, y«montantanini» en480.34–481.10s. La actividad
fuera de marcas señala11ventanas adicionales de revisión, no11pruebas de habla.

Un contraste local de la zona original393.72–401.78s encuentra pseudo-habla antes
del corte antiguo. Una frase de14palabras que Fish marca allí tampoco se recupera
al reconocer el original completo ni en una ventana aislada. Apunta a posible
sustitución/omisión durante síntesis, pendiente de escucha; no demuestra que el
corte retirara narración auténtica. Cortar inserciones no reconstruye palabras
que falten. El reconocimiento puede fallar y requiere criterio acústico/editorial.

Los reportes y el índice de escucha están en el episodio, bajo
`editorial/auditoria_audio_2026-10-27/`. Se conservan originales y derivado;
`final_video_ready` sigue enfalse. No se sintetizó ni cortó audio en esta auditoría.
El entorno/modelo local ocupa~0.94GB una vez, compartido entre episodios.

## Optimización por prioridad

1. Detectar voz incorrecta antes de imágenes y render: evita repetir fases caras.
2. Usar el perfil horror y el estilo/ancla elegidos desde el inicio: evita corrección
   editorial tardía. Voz limpia y control local antes de aprobar una muestra.
3. Reanudar subtítulos ya codificados tras interrupciónQA: implementado con identidad
   y hash duraderos; no requiere el script temporal de recuperación para trabajos nuevos.
4. Entrega compacta e inventario: implementados como comandos explícitos. La política
   automática de retención/limpieza por episodio sigue pendiente; no borrar cachés de
   trabajos activos ni fuentes para aparentar menos archivos.
5. Diseñar y validar un modo de cámara más económico y evitar transiciones que
   recodifiquen sin beneficio visual. Aún propuesta, no mejora general demostrada.
6. Valorar ASS dentro del render por plano y consolidar análisis compatibles del
   QA, conservando el reloj global y los controles fuertes. Requiere diseño/prueba;
   no se implementó fusionando filtros a ciegas en este episodio.

La música baja de terror y las imágenes más inquietantes son decisiones editoriales
coherentes con el canal, no una prueba de mayor retención. La claridad del narrador,
una amenaza comprensible y variación de tensión deben prevalecer sobre subir volumen,
añadir sangre continuamente o multiplicar efectos.
