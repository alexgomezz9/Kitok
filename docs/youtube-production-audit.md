# Auditoría del flujo de Trazo Maldito — 28/10/2026

Revisión del episodio Jason y del código actual. Los tiempos proceden del log de
su producción real, no de estimaciones ni de la suite. Reglas y comandos vigentes:
[guía](../GUIA.md), [flujo editorial](youtube-editorial.md), [voz](fish-voice.md),
[audio](audio.md). Conserva las mediciones del render anterior y la reparación
posterior. No se ha vuelto a renderizar el episodio completo ni publicado contenido.

## Orden real y reparto de trabajo

| Etapa | Agente/editor | Kitok determinista |
| --- | --- | --- |
| Idea e investigación | Decide personaje, continuidad, fuentes y promesa; no une versiones incompatibles. | Lector compacto recupera perfil y estado; no investiga por sí solo. |
| Guion | Escribe relato causal e inmersivo; títulos/canon quedan en notas. | Conserva texto y hashes. No escribe ni corrige hechos. |
| Enfoque visual nuevo | Propone tres enfoques stickman del mismo momento; operador elige, o agente si está delegado. | Importa anclas y conserva referencias; no inventa aprobación. |
| Voz | Decide interpretación y revisa pronunciación/anomalías. | Fish sólo con opción expresa si falta voz; caché y resultados inciertos conservados. ASR local con recortes de inserciones en copia y segunda comprobación antes de montaje; predeterminado en init nuevo. |
| Storyboard | Decide cortes semánticos, acción, composición, personajes y prompts. | Helper calcula cobertura, IDs, fragmentos y reloj desde palabras reales. |
| Imágenes | Invoca ImageGen integrado y revisa correspondencia de todos los recortes. | Prepara lotes, recorta, valida, registra hashes y conserva relación panel/escena. |
| Montaje | Entrega inputs fijados; revisa muestra y sólo cambia dirección cuando aporta. | Valida, mezcla, anima, transiciona, une, añade ASS y ejecuta QA. Sin LLM por plano ni fotograma. |
| Entrega | Fija miniatura, descripción, capítulos y créditos reales. | Empaquetado compacto de seis archivos con recibos/hashes, sin recodificar. |
| Limpieza | Decide cuándo deja de necesitar reusar cachés para reparaciones. | Comando explícito inspecciona/retira derivados comprobados y archiva revisiones cerradas con fuentes/hashes, con locks. |

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
  El control ASR local compara reconocimiento independiente con el texto. El modo
  nuevo recorta inserciones ancladas, reconoce de nuevo y bloquea omisiones o
  diferencias ambiguas. En la reparación real hubo24cortes automáticos,1corte
  editorial y2frases recuperadas con Fish: no fue una reparación100%automática.
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

La limpieza ya está aplicada. Cada episodio tiene un índice `LEEME.md`, entradas
visibles y las carpetas comunes de [organización](episode-files.md). Los vídeos
conservados se encuentran en `entrega/`, sin volver a codificarlos. Una referencia
histórica no se presenta como una entrega nueva aprobada.

El comando `organize` retiró1501derivados/láminas/crops en las revisiones cerradas
de Jason, Myers y Antigüedad; archivó fuentes únicas y metadatos, con duplicados
referidos por hash a sus originales. Se comprobaron419fuentes protegidas sin deriva.
Las pruebas de voz se movieron a `local/pruebas/`; los ZIP históricos están en
`local/archivo_episodios/`. La evidencia completa está en
`local/cleanup/2026-10-27-organizacion/`. La limpieza anterior se conserva en
`local/cleanup/2026-10-27-jason/`; no volver a aplicarla como si siguiera pendiente.

Se conservaron guiones, voz Fish cruda, voz reparada, PNG definitivos, referencias,
licencias, planes y hashes. Los clips retirados requieren renderizar otra vez si
se cambia el montaje. `--archive-revisions` bloquea una revisión consumida por
entradas actuales. No archiva ni borra automáticamente al guardar un borrador.

Jason queda en standby: futuro remake con estética nueva y >8min de duración útil.
El WAV reparado7:16 está visible en raíz; su vídeo anterior conserva errores.


## Diagnóstico inicial de voz, antes de la reparación actual

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

El diagnóstico inicial se conservó como evidencia; la reparación posterior está
en `local/pruebas/trazo_003_jason_voorhees/autocorreccion_audio_2026-10-27/`.
No confundir esas38diferencias iniciales con el resultado posterior0inserciones.
`final_video_ready` sigue enfalse; Jason está en pausa.
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

## Freddy — cierre del 28/10

Guion de 1.984 palabras con tres `[break]`, 124 escenas editoriales y 124 PNG
revisados. Kitok compiló 132 planos sobre marcas Fish reales: 630,533 s (10:30),
sin ralentizar ni alargar silencios. Las imágenes de atlas conservan tamaño
nativo de 541–542 × 297–298; la salida 1080p escala, sin crear detalle.
Última imagen individual: 1656×925. Miniatura: 1672×941 → 1280×720.
El registro por fases está en el `editorial/produccion.md` del episodio.

Las solicitudes nuevas Fish colapsan espacios sin quitar etiquetas; conservan
el guion fuente y guardan el hash del texto realmente enviado. La revisión larga
continua dejó cinco discrepancias ASR y cero huecos energéticos. Las ventanas
locales automáticas resolvieron cuatro: una palabra fantasma del ASR, diez
palabras omitidas por el ASR y dos uniones de clíticos. No se recortó audio para
hacer coincidir el guion. Krueger/Kruger siguió pendiente y se aceptó mediante
revisión documental de otra ventana que recuperaba literalmente el nombre.
Los informes y tiempos originales permanecen. No hubo escucha humana ni se
promete reparar cualquier fallo de Fish. Se verificaron 64 pruebas focales,
revisión independiente y reutilización de caché sin otra ejecución ASR.

El adjunto de GTA coincide al leer texto con el guion de `1_gta6`, incluidos
muchos saltos y etiquetas. Es inglés y la configuración actual usa Loose Thread;
no hay recibo histórico para atribuir modelo o parámetros exactos. La prueba
previa con Loose Thread leyendo español no equivale a ese vídeo. La documentación
oficial de Fish no aporta evidencia de degradación deliberada del plan gratis.
Tampoco se demostró que los saltos fueran la única causa del fallo.

Intervenciones adicionales del agente:

- Corregir un salto final introducido al escribir a mano el archivo limpio: debe
  generarlo el compilador. Corregir claves incorrectas de miniatura que preparó
  el agente; la configuración ahora las rechaza antes de solicitar voz.
- Adaptar tres viñetas a consecuencias sin heridas tras rechazo del generador y
  regenerar sólo la casilla 124 que salió vacía. Los demás PNG se conservaron.
- Reanudar el comando fuera del sandbox: allí NVML estaba bloqueado, mientras la
  RTX 3050 de 4 GB funcionaba fuera. El FFmpeg y el recibo definitivo confirmaron
  `h264_nvenc`. No es una carencia de NVIDIA del uso diario de Kitok.
- Exportar a la carpeta común los seis archivos del bundle creado por Kitok;
  vídeo mediante hardlink, textos y miniatura mediante copias independientes.
  El montaje de planos, mezcla, unión y subtítulos fue íntegramente de Kitok.

| Fase medida | Tiempo |
| --- | --- |
| Mezcla | 2:47 |
| Render, unión y reloj de 132 planos | 16:40 (1000,42 s) |
| QA base | 4:04 |
| Preparación de exportación | 1:07 |
| Incrustar ASS con NVENC | 2:57 |
| QA subtitulado | 4:44 |
| Comando completo | 32:17 |

La unión propiamente dicha duró unos diez segundos. Los filtros y varios
recorridos del QA siguen en CPU. No se adoptó una cámara más económica sin
prueba visual suficiente; las propuestas anteriores siguen siendo propuestas.

Ambos QA pasaron: 18.916 fotogramas, 1920×1080/30 fps, −16,02 LUFS y −2,24 dBTP.
El audio del subtitulado coincide con el base. Se vieron contactos y muestras de
transición, inicio, medio y cierre. Chromium completó el archivo a 4× silenciado,
con saltos de fotogramas; tramo a velocidad normal 0–80,174 s con 2.406 frames y
cero perdidos. No equivale a escuchar ni comprobar fluidez a 1× de todo el vídeo.
Revisión independiente de entrega sin inconsistencias materiales; no repitió
ASR, render ni decodificación.

Entrega: `content/longform/trazo_004_freddy_krueger/entrega/`, seis archivos.
Vídeo de 599.627.106 bytes. Limpieza: 869 auxiliares retirados (1457,8 MiB lógicos)
y 266 rutas fuente con SHA intacto. No se midió liberación física con otros
hardlinks. Se conservan la revisión activa, originales, másteres, PNG, prompts,
recibos y licencias. El operador comunicó después feedback muy positivo del vídeo y audio, y pidió
reforzar aún más las figuras stickman y su crecimiento en próximos episodios.
No se ha publicado nada.

### Coste del cierre del agente

El QA del subtitulado consumió 4:44 después de codificarlo. Además transcurrieron
20:56 entre terminar el comando y el último commit documental de la entrega
(comparación del mtime de montage_exitcode y la fecha del commit 43e55c3).
Ese intervalo incluyó comprobaciones de navegador, empaquetado, limpieza,
revisión independiente y documentación; no fue sólo espera del QA.
Las intervenciones del agente consumen tokens aunque los procesos locales
no necesiten llamadas a un modelo de lenguaje. No hay una medición de tokens
de ese cierre. Para producción repetida, preparar el registro durante las fases,
reducir consultas a progreso compacto y reservar auditorías adicionales para
cambios/fallos. El cierre automático es la primera prioridad de la [hoja de ruta](roadmap.md).
